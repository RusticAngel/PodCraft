import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from src.video_generator import PodCraftVideoGenerator, generate_video_from_pack
from src.episode_meta import generate_episode_title, generate_cover_art


def _make_pack(path, tmp_path):
    """Build a minimal production pack ZIP with a manifest + one WAV."""
    import wave
    import struct

    wav_path = str(tmp_path / "speech_abc123.wav")
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<8000h", *[0] * 8000))

    manifest = {
        "script_analysis": {
            "speakers": ["HOST", "GUEST"],
            "full_text": "HOST: hi GUEST: hello",
            "genre": "technology",
            "mood": "excited",
        },
        "audio_production": {
            "audio_files": [
                {"index": 0, "speaker": "HOST", "text": "hi", "audio_path": wav_path},
                {"index": 1, "speaker": "GUEST", "text": "hello", "audio_path": wav_path},
            ],
            "music_path": None,
            "total_segments": 2,
        },
        "status": "success",
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("production_manifest.json", json.dumps(manifest))
        zf.write(wav_path, "speech_abc123.wav")
    return path


def test_manifest_parsing(tmp_path):
    pack = _make_pack(str(tmp_path / "pack.zip"), tmp_path)
    gen = PodCraftVideoGenerator(pack)
    assert gen.manifest["status"] == "success"
    assert len(gen._ordered_segments()) == 2


def test_episode_title_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    meta = generate_episode_title(
        {"full_text": "HOST: hi", "mood": "excited"}, "technology"
    )
    assert meta["title"] and meta["method"] == "fallback"


def test_cover_art(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    path = generate_cover_art("Test Title", mood="excited", output_dir=str(tmp_path))
    assert path and os.path.exists(path) and path.endswith(".png")


def test_generate_video_from_pack_requires_playable_audio(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    pack = _make_pack(str(tmp_path / "pack.zip"), tmp_path)

    # Simulate moviepy unavailable -> should raise ImportError cleanly
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "moviepy":
            raise ImportError("moviepy not installed (test)")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError):
        generate_video_from_pack(pack, output_path=str(tmp_path / "out.mp4"))


def test_speaker_color_is_deterministic():
    gen = PodCraftVideoGenerator("unused.zip")
    assert gen._speaker_color("HOST") == gen._speaker_color("host")
    assert isinstance(gen._speaker_color("HOST"), tuple)


def test_segment_plan_maps_x_range(tmp_path):
    gen = PodCraftVideoGenerator(str(tmp_path / "pack.zip"))
    gen._manifest = {
        "script_analysis": {"genre": "technology"},
        "audio_production": {
            "audio_files": [
                {"index": 0, "speaker": "HOST", "text": "hi",
                 "audio_path": str(tmp_path / "a.wav")},
                {"index": 1, "speaker": "GUEST", "text": "hello",
                 "audio_path": str(tmp_path / "b.wav")},
            ],
            "music_path": None,
        },
    }
    timed = [(0.0, 5.0, gen._ordered_segments()[0]),
             (5.0, 5.0, gen._ordered_segments()[1])]
    plan = gen._segment_plan(timed, total=10.0)
    assert len(plan) == 2
    assert plan[0]["x0"] == 0
    assert plan[0]["x1"] < plan[1]["x1"]
    assert plan[1]["x1"] == 960
    assert plan[0]["banner"].shape == (540, 960, 4)
    assert plan[0]["subtitle"] is not None


def test_frame_at_renders_playhead_and_banner(tmp_path):
    import numpy as np

    gen = PodCraftVideoGenerator(str(tmp_path / "pack.zip"))
    base = np.zeros((540, 960, 3), dtype=np.uint8)
    plan = [{
        "start": 0.0, "end": 5.0, "entry": {"speaker": "HOST", "text": "hi"},
        "name": "HOST", "color": (88, 166, 255),
        "x0": 0, "x1": 480,
        "banner": np.zeros((540, 960, 4), dtype=np.uint8),
        "subtitle": None,
    }]
    title_overlay = np.zeros((540, 960, 4), dtype=np.uint8)
    frame = gen._frame_at(2.0, base, plan, title_overlay, intro_seconds=0.0, total=10.0)
    assert frame.shape == (540, 960, 3)
    # White playhead drawn near t=2 of 10 -> x ~192 (2px wide)
    assert frame[270, 192].tolist() == [255, 255, 255]
    assert frame[270, 193].tolist() == [255, 255, 255]


def test_precomputed_backgrounds_match_slow_path(tmp_path):
    """The render-speed optimization must be pixel-identical to the
    per-frame compositing it replaced."""
    import numpy as np

    gen = PodCraftVideoGenerator(str(tmp_path / "pack.zip"))
    rng = np.random.default_rng(7)
    base = rng.integers(0, 255, size=(540, 960, 3), dtype=np.uint8)

    banner = np.zeros((540, 960, 4), dtype=np.uint8)
    banner[:, :, :3] = (200, 100, 50)
    banner[:, :, 3] = 255
    subtitle = np.zeros((540, 960, 4), dtype=np.uint8)
    subtitle[:, :, :3] = (10, 10, 10)
    subtitle[:, :, 3] = 180
    plan = [{
        "start": 0.0, "end": 5.0, "entry": {"speaker": "HOST", "text": "hi"},
        "name": "HOST", "color": (88, 166, 255),
        "x0": 0, "x1": 480,
        "banner": banner,
        "subtitle": subtitle,
    }]
    title_overlay = np.zeros((540, 960, 4), dtype=np.uint8)
    title_overlay[:100, :, :3] = (250, 250, 250)
    title_overlay[:100, :, 3] = 255

    bgs = gen._precompute_backgrounds(base, plan)
    assert len(bgs) == 1

    for t in (0.5, 2.0, 4.99):
        fast = gen._frame_at(t, base, plan, title_overlay,
                             intro_seconds=6.0, total=10.0, backgrounds=bgs)
        slow = gen._frame_at(t, base, plan, title_overlay,
                             intro_seconds=6.0, total=10.0)
        assert np.array_equal(fast, slow), f"fast path diverged at t={t}"

    # Playhead advances across frames sharing one cached background.
    early = gen._frame_at(1.0, base, plan, title_overlay,
                          intro_seconds=0.0, total=10.0, backgrounds=bgs)
    late = gen._frame_at(8.0, base, plan, title_overlay,
                         intro_seconds=0.0, total=10.0, backgrounds=bgs)
    assert not np.array_equal(early[270], late[270])


def test_video_generator_builds_pack_files(tmp_path):
    pack = _make_pack(str(tmp_path / "pack.zip"), tmp_path)
    gen = PodCraftVideoGenerator(pack)
    files = gen._pack_files()
    assert "production_manifest.json" in files
    assert "speech_abc123.wav" in files
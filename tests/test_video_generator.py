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
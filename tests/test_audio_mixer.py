import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tools.audio_mixer import AudioMixer, volume_from_duck_db
from src.tools.audio_utils import synth_placeholder_wav


def test_segment_ordering():
    """Segments are ordered correctly by script index."""
    segments = [
        {"speaker": "Guest", "order": 2},
        {"speaker": "Host", "order": 1},
        {"speaker": "Outro", "order": 3},
    ]
    ordered = AudioMixer.order_segments(segments)
    assert [s["speaker"] for s in ordered] == ["Host", "Guest", "Outro"]


def test_segment_ordering_by_index():
    """Manifest 'index' keys (the real pack field) win over 'order'."""
    segments = [
        {"speaker": "B", "index": 1, "order": 0},
        {"speaker": "A", "index": 0, "order": 9},
    ]
    ordered = AudioMixer.order_segments(segments)
    assert ordered[0]["speaker"] == "A"
    assert ordered[1]["speaker"] == "B"


def test_ducking_volume_mapping():
    """Ducking in dB maps to a clamped linear volume exactly like the video mix."""
    v = volume_from_duck_db(-18)
    assert v is not None
    assert abs(v - 10 ** (-18 / 20)) < 1e-4
    v0 = volume_from_duck_db(0)
    assert v0 is not None and abs(v0 - 1.0) < 1e-6
    v40 = volume_from_duck_db(-40)
    assert v40 is not None and 0.0 <= v40 <= 1.0
    assert volume_from_duck_db(None) is None
    assert volume_from_duck_db("boom") is None


def test_mix_episode_produces_mp3(tmp_path):
    """Two segments + a music bed yield a combined MP3 of their total length."""
    seg_a = synth_placeholder_wav("neutral", duration_seconds=2)
    seg_b = synth_placeholder_wav("calm", duration_seconds=3)
    music = synth_placeholder_wav("sad", duration_seconds=4)

    mixer = AudioMixer.__new__(AudioMixer)  # skip pack_path plumbing for the unit test
    mixer.music_volume = 0.15
    segs = [
        {"path": seg_a, "speaker": "Host", "index": 0},
        {"path": seg_b, "speaker": "Guest", "index": 1},
    ]
    out = tmp_path / "full.mp3"
    mp3 = mixer.mix_episode(segs, music, output_path=str(out))

    assert os.path.exists(mp3)
    assert os.path.getsize(mp3) > 500
    from moviepy import AudioFileClip

    with AudioFileClip(mp3) as clip:
        assert 4.5 <= clip.duration <= 5.6


def test_export_adds_mp3_to_pack(tmp_path):
    """run() writes full_episode.mp3 into the pack, idempotently."""
    seg = synth_placeholder_wav("calm", duration_seconds=2)
    music = synth_placeholder_wav("nervous", duration_seconds=3)
    manifest = {
        "audio_production": {
            "audio_files": [{"speaker": "Host", "index": 0, "text": "hi", "audio_path": seg}],
            "music_path": music,
        }
    }
    pack = tmp_path / "p.zip"
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("production_manifest.json", json.dumps(manifest))
        zf.write(seg, os.path.basename(seg))
        zf.write(music, os.path.basename(music))

    out = AudioMixer(str(pack), music_volume=0.1).run()
    assert os.path.exists(out["mp3_path"])
    with zipfile.ZipFile(out["pack_path"]) as zf:
        names = zf.namelist()
    assert names.count("full_episode.mp3") == 1

    # Second run must not duplicate the MP3 entry.
    AudioMixer(str(pack), music_volume=0.1).run()
    with zipfile.ZipFile(out["pack_path"]) as zf:
        assert zf.namelist().count("full_episode.mp3") == 1
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.phase4_adk_agents.director_agent import DirectorAgent
from src.phase4_adk_agents.researcher_agent import ResearcherAgent
from src.phase4_adk_agents.audio_producer_agent import AudioProducerAgent
from src.phase4_adk_agents.orchestrator import PodcastOrchestrator
from src.tools.audio_utils import synth_placeholder_wav, audio_duration
from scripts.make_demo_pdf import build_pdf

import tempfile

SAMPLE_SCRIPT = {
    "full_text": "HOST: Welcome to the show. GUEST: This is amazing, thanks.",
    "speakers": ["host", "guest"],
    "dialogue_segments": [
        {"speaker": "HOST", "text": "Welcome to the show."},
        {"speaker": "GUEST", "text": "This is amazing, thanks."},
    ],
    "topics": ["ai", "podcast"],
    "mood": "happy",
    "estimated_duration": 2,
    "genre": "technology",
}


def _write_demo_pdf(path):
    with open(path, "wb") as f:
        f.write(build_pdf([
            "PODCAST: TEST", "INT. STUDIO",
            "HOST: Welcome to the show, this is exciting",
            "GUEST: Thanks for having me, the tools are amazing today",
            "HOST: Let's talk about AI production pipelines",
        ]))
    return path


def test_director_fallback_without_vertex(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    director = DirectorAgent()
    result = director.run(SAMPLE_SCRIPT)
    assert "structure" in result
    assert result["tone"] is not None


def test_director_structure_tool():
    director = DirectorAgent()
    structure = director._analyze_structure(SAMPLE_SCRIPT)
    assert structure["segments"] == 2
    assert structure["speakers"] == ["HOST", "GUEST"]


def test_researcher_fallback_without_keys(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    researcher = ResearcherAgent()
    result = researcher.run(SAMPLE_SCRIPT, {"topics": ["ai"]})
    assert "market_data" in result
    assert "recommendations" in result


def test_audio_producer_fallback_produces_outputs(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    producer = AudioProducerAgent()
    result = producer.run(SAMPLE_SCRIPT, {"tone": "happy", "pacing": {}, "structure": {}})
    assert result["total_segments"] == 2
    assert result["music_path"]
    assert result["sentiment_analysis"]["overall_tone"] in ("positive", "neutral", "negative")
    # Without keys, speech generation returns None but must not crash.
    for entry in result["audio_files"]:
        assert entry["audio_path"] is None


def test_placeholder_wav_generates():
    path = synth_placeholder_wav("calm", duration_seconds=1)
    assert os.path.exists(path)
    dur = audio_duration(path)
    assert dur is not None and dur > 0.5


def test_placeholder_wav_is_tonal_not_static():
    """The music fallback must sound like a tone/pad, not white noise.
    A clean tone has low zero-crossing rate and a strong tonal RMS."""
    import math
    import struct
    import wave

    path = synth_placeholder_wav("happy", duration_seconds=3)
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        samples = struct.unpack("<%dh" % w.getnframes(), w.readframes(w.getnframes()))
    n = len(samples)
    rms = math.sqrt(sum(x * x for x in samples) / n)
    zc = sum(1 for i in range(1, n) if (samples[i - 1] < 0) != (samples[i] < 0))
    zc_per_sec = zc / (n / rate)
    # A 261 Hz tone + harmonics stays well under ~1000 crossings/sec;
    # white noise would be in the tens of thousands.
    assert zc_per_sec < 2000
    assert rms > 100


def test_orchestrator_e2e_without_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)

    pdf = _write_demo_pdf(str(tmp_path / "demo.pdf"))
    orch = PodcastOrchestrator()
    result = orch.process_script(pdf, "technology")
    assert result["status"] == "success"
    assert result["script_analysis"]["speakers"]
    assert result["audio_production"]["music_path"]
    assert isinstance(result["recommendations"], list)
    assert result["director_notes"]["tone"] is not None


def test_pick_segments_full_list():
    producer = AudioProducerAgent()
    segs = [{"speaker": f"S{i}"} for i in range(7)]
    all_segs, idx = producer._pick_segments(segs, None)
    assert all_segs == segs
    assert idx == list(range(7))


def test_pick_segments_lite_includes_first_and_last():
    producer = AudioProducerAgent()
    segs = [{"speaker": f"S{i}"} for i in range(7)]
    picked, idx = producer._pick_segments(segs, 3)
    assert idx[0] == 0 and idx[-1] == 6
    assert len(picked) == 3
    assert [s["speaker"] for s in picked] == ["S0", "S3", "S6"]


def test_pick_segments_single():
    producer = AudioProducerAgent()
    segs = [{"speaker": f"S{i}"} for i in range(5)]
    picked, idx = producer._pick_segments(segs, 1)
    assert picked == [segs[0]] and idx == [0]


def test_pick_segments_lite_flag(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    producer = AudioProducerAgent()
    segs = [{"speaker": f"S{i}", "text": f"Segment {i} text"} for i in range(7)]
    result = producer._produce_audio({
        "dialogue_segments": segs, "speakers": [], "tone": "neutral",
        "max_segments": 3,
    })
    assert result["lite_mode"] is True
    assert result["total_segments"] == 3


def test_speaker_identifier_respects_overrides():
    from src.phase2_document_processing.speaker_identifier import SpeakerIdentifier

    ident = SpeakerIdentifier()
    profiles = ident.identify(
        ["host", "guest"],
        [{"speaker": "HOST"}, {"speaker": "GUEST"}],
        voice_overrides={"host": "Aoede", "guest": "Fenrir"},
    )
    by_name = {p["speaker"]: p["voice"] for p in profiles}
    assert by_name["host"] == "Aoede"
    assert by_name["guest"] == "Fenrir"


def test_assign_voice_override_wins():
    from src.phase2_document_processing.speaker_identifier import SpeakerIdentifier

    ident = SpeakerIdentifier()
    profiles = ident.identify(["host", "guest"], [{"speaker": "HOST"}, {"speaker": "GUEST"}])
    assert ident.assign_voice("HOST", profiles, {"host": "Zephyr"}) == "Zephyr"
    # Case-insensitive lookup
    assert ident.assign_voice("host", profiles, {"HOST": "Kore"}) == "Kore"
    # No override -> falls back to the profile assignment
    assigned = ident.assign_voice("HOST", profiles, {})
    assert assigned in ("Puck", "Charon", "Kore", "Fenrir", "Aoede", "Zephyr")


def test_audio_producer_uses_overrides(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    producer = AudioProducerAgent()
    segs = [{"speaker": "HOST", "text": "Hello"}, {"speaker": "GUEST", "text": "Hi"}]
    result = producer._produce_audio({
        "dialogue_segments": segs,
        "speakers": ["HOST", "GUEST"],
        "tone": "neutral",
        "max_segments": None,
        "voice_overrides": {"HOST": "Aoede", "GUEST": "Kore"},
    })
    assert result["speaker_profiles"][0]["voice"] == "Aoede"
    assert result["speaker_profiles"][1]["voice"] == "Kore"
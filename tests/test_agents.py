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
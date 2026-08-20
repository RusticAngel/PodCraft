import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.phase2_document_processing.pdf_parser import PDFScriptParser
from src.phase2_document_processing.script_analyzer import ScriptAnalyzer
from src.phase2_document_processing.speaker_identifier import SpeakerIdentifier
from scripts.make_demo_pdf import build_pdf


@pytest.fixture(scope="module")
def sample_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(build_pdf([
            "PODCAST: TEST",
            "INT. STUDIO",
            "",
            "HOST: Hello and welcome to the show",
            "GUEST: Thanks for having me, this is amazing",
            "HOST: Let's talk about AI today",
        ]))
        path = tmp.name
    yield path
    os.unlink(path)


def test_parse_returns_expected_keys(sample_pdf):
    data = PDFScriptParser().parse(sample_pdf)
    assert set(["full_text", "speakers", "dialogue_segments", "topics", "mood", "scene_breaks", "estimated_duration"]).issubset(data.keys())
    assert "HOST" in [s.upper() for s in data["speakers"]]
    assert data["scene_breaks"] >= 1


def test_dialogue_segments(sample_pdf):
    data = PDFScriptParser().parse(sample_pdf)
    speakers = [seg["speaker"] for seg in data["dialogue_segments"]]
    assert "HOST" in speakers
    assert all(seg["text"] for seg in data["dialogue_segments"])


def test_duration_estimate_positive(sample_pdf):
    data = PDFScriptParser().parse(sample_pdf)
    assert data["estimated_duration"] >= 0


def test_script_analyzer(sample_pdf):
    data = PDFScriptParser().parse(sample_pdf)
    analysis = ScriptAnalyzer().analyze(data)
    assert "structure" in analysis
    assert "production_cues" in analysis
    assert analysis["segment_count"] == len(data["dialogue_segments"])


def test_speaker_identifier_assigns_voices(sample_pdf):
    data = PDFScriptParser().parse(sample_pdf)
    profiles = SpeakerIdentifier().identify(data["speakers"], data["dialogue_segments"])
    assert profiles
    assert all(p["voice"] and p["role"] for p in profiles)
    # Two profiles for two speakers
    assert len(profiles) == len(data["speakers"])


def test_speaker_identifier_distinct_voices():
    identifier = SpeakerIdentifier()
    profiles = [
        {"speaker": "a", "voice": "v1"},
        {"speaker": "b", "voice": "v2"},
    ]
    assert identifier.assign_voice("A", profiles) == "v1"
    assert identifier.assign_voice("b", profiles) == "v2"
    assert identifier.assign_voice("unknown", profiles) == identifier.default_voice


def test_speaker_role_inference_parenthesized_and_support():
    """'OUTRO (Narrator)' must be inferred as a support role, not host:
    the parenthesized label must not leak into hint matching."""
    identifier = SpeakerIdentifier()
    assert identifier._infer_role("OUTRO (Narrator)") == "support"
    assert identifier._infer_role("Intro (Producer)") == "support"
    assert identifier._infer_role("HOST") == "host"
    assert identifier._infer_role("Narrator") == "host"
    assert identifier._infer_role("GUEST") == "guest"


def test_parser_skips_metadata_and_handles_parenthesized_speakers():
    """FORMAT:/TOPIC: headers must not become speakers; 'OUTRO (Narrator):'
    with a parenthetical must be recognized as a speaker."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(build_pdf([
            "PODCAST TITLE: THE CREATOR'S CUT",
            "FORMAT: INTERVIEW",
            "DURATION: 3 MINUTES",
            "INT. STUDIO - MORNING",
            "",
            "HOST: Welcome back!",
            "GUEST: Thanks for having me.",
            "HOST: Let's dig in.",
            "OUTRO (Narrator): Thanks for listening!",
        ]))
        path = tmp.name
    try:
        data = PDFScriptParser().parse(path)
    finally:
        os.unlink(path)

    speakers = data["speakers"]
    assert "format" not in speakers
    assert "duration" not in speakers
    assert "outro (narrator)" in speakers

    seg_speakers = [seg["speaker"] for seg in data["dialogue_segments"]]
    assert seg_speakers == ["HOST", "GUEST", "HOST", "OUTRO (Narrator)"]
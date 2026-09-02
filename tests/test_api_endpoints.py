import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _demo_pdf():
    with open("static/demo_script.pdf", "rb") as f:
        return f.read()


def _wait_job(client, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.5)
    raise TimeoutError(f"job {job_id} did not finish")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_root(client):
    assert client.get("/").json()["status"] == "running"


def test_vibes_endpoint(client):
    r = client.get("/vibes")
    assert r.status_code == 200
    vibes = r.json()["vibes"]
    assert len(vibes) >= 5
    assert all(v["id"] and v["name"] and v["emoji"] and v["genre"] for v in vibes)
    assert all(len(v["colors"]) >= 2 for v in vibes)


def test_voices_endpoint(client):
    r = client.get("/voices")
    assert r.status_code == 200
    voices = r.json()["voices"]
    assert len(voices) >= 4
    names = [v["name"] for v in voices]
    assert "Puck" in names and "Kore" in names
    assert all(v["name"] in {"Puck", "Charon", "Kore", "Fenrir", "Aoede", "Zephyr"} for v in voices)


def test_upload_rejects_unsupported_type(client):
    r = client.post("/upload", files={"file": ("x.doc", b"hi", "application/msword")})
    assert r.status_code == 400
    assert "Supported formats" in r.json()["detail"]


def test_analyze_accepts_txt(client):
    script = "HOST: Hello there.\nGUEST: Great to be here."
    r = client.post("/analyze", files={"file": ("s.txt", script.encode("utf-8"), "text/plain")})
    assert r.status_code == 200
    speakers = r.json()["script_analysis"]["speakers"]
    assert "host" in speakers and "guest" in speakers


def test_analyze_accepts_docx(client):
    import io

    import docx as docx_lib

    buffer = io.BytesIO()
    document = docx_lib.Document()
    document.add_paragraph("HOST: Hello there.")
    document.add_paragraph("GUEST: Great to be here.")
    document.save(buffer)
    r = client.post("/analyze", files={
        "file": ("s.docx", buffer.getvalue(),
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    })
    assert r.status_code == 200
    speakers = r.json()["script_analysis"]["speakers"]
    assert "host" in speakers and "guest" in speakers


def test_upload_rejects_invalid_voice_override(client):
    r = client.post(
        "/upload",
        files={"file": ("demo.pdf", _demo_pdf(), "application/pdf")},
        params={"voice_overrides": '{"HOST": "NotARealVoice"}'},
    )
    assert r.status_code == 400
    assert "Unknown voice" in r.json()["detail"]


def test_upload_rejects_malformed_voice_override(client):
    r = client.post(
        "/upload",
        files={"file": ("demo.pdf", _demo_pdf(), "application/pdf")},
        params={"voice_overrides": "not-json"},
    )
    assert r.status_code == 400


def test_upload_accepts_valid_voice_override(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post(
        "/upload",
        files={"file": ("demo.pdf", _demo_pdf(), "application/pdf")},
        params={"voice_overrides": '{"host": "Puck", "guest": "Kore"}',
                "max_segments": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    by_name = {p["speaker"]: p["voice"] for p in body["data"]["speaker_profiles"]}
    assert by_name.get("host") == "Puck"
    assert by_name.get("guest") == "Kore"


def test_analyze_endpoint(client):
    r = client.post("/analyze", files={"file": ("demo.pdf", _demo_pdf(), "application/pdf")})
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    assert r.json()["script_analysis"]["speakers"]


def test_job_upload_and_poll(client, monkeypatch):
    # Without keys, the pipeline uses cached TTS + placeholder music fallbacks.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)

    r = client.post(
        "/jobs/upload",
        files={"file": ("demo.pdf", _demo_pdf(), "application/pdf")},
        params={"genre": "technology", "max_segments": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "started"
    assert body["job_id"]

    job = _wait_job(client, body["job_id"])
    assert job["status"] == "done"
    result = job["result"]
    assert result["status"] == "success"
    assert result["pack_token"]
    data = result["data"]
    assert data["audio_production"]["total_segments"] <= 3
    assert data["audio_production"]["lite_mode"] is True
    assert data["episode_meta"]["title"]
    # Without a key, speech is skipped but the placeholder music WAV is always
    # generated and should be present in the pack.
    with zipfile.ZipFile(f"outputs/podcraft_pack_{result['pack_token']}.zip") as zf:
        names = zf.namelist()
    assert any(n.endswith(".wav") for n in names)


def test_job_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_rss_escapes_special_chars(client):
    r = client.get("/rss")
    assert r.status_code == 200
    assert "rss+xml" in r.headers["content-type"]
    # A raw '&' must never appear in item text (would break XML)
    assert "<item>" in r.text
    # Ensure well-formed XML
    import xml.etree.ElementTree as ET

    ET.fromstring(r.text)


def test_pack_download(client):
    r = client.post(
        "/jobs/upload",
        files={"file": ("demo.pdf", _demo_pdf(), "application/pdf")},
        params={"genre": "technology", "max_segments": 2},
    ).json()
    job = _wait_job(client, r["job_id"])
    token = job["result"]["pack_token"]

    r = client.get(f"/pack/{token}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert len(r.content) > 0


def test_export_episode_endpoint(client):
    """Export mixes a pack into full_episode.mp3 and serves the updated pack."""
    from src.tools.audio_utils import synth_placeholder_wav

    seg = synth_placeholder_wav("calm", duration_seconds=2)
    music = synth_placeholder_wav("sad", duration_seconds=3)
    result = {
        "audio_production": {
            "audio_files": [{"speaker": "Host", "index": 0, "text": "hi", "audio_path": seg}],
            "music_path": music,
        }
    }
    from src.main import _build_pack

    pack_path = _build_pack(os.path.join("uploads", "export_pack_test.pdf"), result)
    token = os.path.basename(pack_path).replace("podcraft_pack_", "").replace(".zip", "")

    r = client.post("/export/episode", params={"pack_token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["download_url"] == f"/pack/{token}"
    assert "mp3_url" in body

    mp3 = client.get(body["mp3_url"])
    assert mp3.status_code == 200
    assert len(mp3.content) > 500

    import io

    with zipfile.ZipFile(io.BytesIO(client.get(f"/pack/{token}").content)) as zf:
        assert "full_episode.mp3" in zf.namelist()


def test_export_episode_unknown_token(client):
    r = client.post("/export/episode", params={"pack_token": "does-not-exist-123"})
    assert r.status_code == 404
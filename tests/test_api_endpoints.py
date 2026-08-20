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


def test_upload_rejects_non_pdf(client):
    r = client.post("/upload", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 400


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
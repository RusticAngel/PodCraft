import mimetypes
import os
import shutil
import threading
import zipfile
import json
import uuid
from xml.sax.saxutils import escape
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from src.phase4_adk_agents.orchestrator import PodcastOrchestrator
from src.phase2_document_processing.pdf_parser import PDFScriptParser
from src.config import Config
from src.utils.file_handlers import safe_filename, safe_join, ensure_dirs, stable_token
from src.video_generator import generate_video_from_pack
from src.episode_meta import generate_episode_title, generate_cover_art

app = FastAPI(
    title="PodCraft - Podcast-to-Production Agent",
    description="Multi-agent system for automated podcast production",
    version="1.0.0",
)

# Browser blocks credentials+wildcard, so credentials must be disabled with
# a wide-open origin policy (hackathon API, not holding auth).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy orchestrator so the app boots minus API keys.
_ORCHESTRATOR = None

# Background job registry (in-memory). Jobs are keyed by a UUID; each entry
# holds status, result/error, and the pack token for follow-up downloads.
_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()


def _submit_job(kind: str, fn, token: str = None) -> str:
    """Register a background job and run it on a daemon thread."""
    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"id": job_id, "kind": kind, "status": "running",
                         "result": None, "error": None, "token": token}

    def _run():
        try:
            result = fn()
            with _JOBS_LOCK:
                _JOBS[job_id]["result"] = result
                _JOBS[job_id]["status"] = "done"
        except Exception as e:
            with _JOBS_LOCK:
                _JOBS[job_id]["error"] = str(e)
                _JOBS[job_id]["status"] = "error"

    threading.Thread(target=_run, daemon=True).start()
    return job_id


def _get_job(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(404, f"Job not found: {job_id}")
        return dict(job)


def get_orchestrator() -> PodcastOrchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = PodcastOrchestrator()
    return _ORCHESTRATOR


def _save_upload(file: UploadFile) -> str:
    ensure_dirs(Config.UPLOAD_DIR)
    filename = safe_filename(file.filename, prefix="upload_")
    upload_path = os.path.join(Config.UPLOAD_DIR, filename)
    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return upload_path


def _process_pipeline(upload_path: str, genre: str, max_segments: Optional[int]) -> dict:
    """Run the full production pipeline and return the /upload response body.

    Extracted from the endpoint so both sync and background/job flows share
    one implementation.
    """
    orchestrator = get_orchestrator()
    result = orchestrator.process_script(upload_path, genre, max_segments)

    for entry in (result.get("audio_production") or {}).get("audio_files") or []:
        path = entry.get("audio_path")
        if path:
            entry["download_url"] = f"/download/{os.path.basename(os.path.normpath(path))}"

    meta = _pack_title(result, genre)
    result["episode_meta"] = meta

    pack_path = _build_pack(upload_path, result)
    if meta.get("cover_path"):
        _add_to_pack(pack_path, meta["cover_path"])

    return {
        "status": "success",
        "data": result,
        "message": "Podcast production complete!",
        "download_url": f"/download/{os.path.basename(pack_path)}",
        "pack_token": os.path.basename(pack_path).replace("podcraft_pack_", "").replace(".zip", ""),
    }


def _run_video_job(token: str, title: str = None) -> dict:
    """Generate video assets from a pack token; returns the /video response body."""
    pack_path = _find_pack(token)
    ensure_dirs(Config.OUTPUT_DIR)

    with zipfile.ZipFile(pack_path) as zf:
        manifest = json.loads(zf.read("production_manifest.json"))
    resolved_title = title or (manifest.get("episode_meta") or {}).get("title") or "PodCraft Episode"

    outputs = generate_video_from_pack(pack_path, title=resolved_title)
    _add_to_pack(
        pack_path,
        outputs.get("video_path"),
        outputs.get("mp3_path"),
        outputs.get("srt_path"),
    )

    return {
        "status": "success",
        "message": "Video generation complete!",
        "data": {
            "video": outputs.get("video_path"),
            "mp3": outputs.get("mp3_path"),
            "srt": outputs.get("srt_path"),
            "title": resolved_title,
        },
        "video_url": f"/download/{os.path.basename(outputs['video_path'])}",
        "mp3_url": f"/download/{os.path.basename(outputs['mp3_path'])}",
        "srt_url": f"/download/{os.path.basename(outputs['srt_path'])}",
        "download_url": f"/download/{os.path.basename(pack_path)}",
    }


def _build_pack(upload_path: str, result: dict) -> str:
    """Zip the produced audio assets plus a manifest into outputs/podcraft_pack_<token>.zip.

    Returns the absolute path of the pack. Purely file-based so it works on
    any container; used by /upload's download_url and GET /download/{name}.
    """
    ensure_dirs(Config.OUTPUT_DIR)
    token = stable_token(os.path.basename(upload_path))
    pack_name = f"podcraft_pack_{token}.zip"
    pack_path = os.path.join(Config.OUTPUT_DIR, pack_name)

    audio = result.get("audio_production") or {}
    paths = []
    for entry in audio.get("audio_files") or []:
        path = entry.get("audio_path")
        if path:
            paths.append(path)
    if audio.get("music_path"):
        paths.append(audio.get("music_path"))
    paths = sorted({os.path.normpath(p) for p in paths if p})

    manifest = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    with zipfile.ZipFile(pack_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("production_manifest.json", manifest)
        for path in paths:
            name = os.path.basename(path)
            if os.path.exists(path):
                zf.write(path, name)
            else:
                zf.writestr(f"missing/{name}", f"file was not present on this instance: {path}")
    return pack_path


def _find_pack(token: str) -> str:
    """Return the absolute path of an existing pack ZIP by its token."""
    ensure_dirs(Config.OUTPUT_DIR)
    name = f"podcraft_pack_{token}.zip"
    path = safe_join(Config.OUTPUT_DIR, name)
    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Pack not found: {name}")
    return path


def _add_to_pack(pack_path: str, *paths: str) -> None:
    """Append generated artifacts (video/mp3/srt/cover) into an existing pack."""
    with zipfile.ZipFile(pack_path, "a", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if path and os.path.exists(path):
                zf.write(path, os.path.basename(path))


def _pack_title(result: dict, genre: str) -> dict:
    """Generate (and cache) the episode title + cover art for a production."""
    try:
        meta = generate_episode_title(result.get("script_analysis") or {}, genre)
        mood = (result.get("script_analysis") or {}).get("mood", "excited")
        cover = generate_cover_art(meta["title"], mood)
        if cover:
            meta["cover_path"] = cover
        return meta
    except Exception as e:
        print(f"Episode meta error: {e}")
        return {"title": genre.title() + " Episode", "method": "fallback", "generated_by": "heuristic"}


@app.get("/")
async def root():
    return {"message": "PodCraft API", "status": "running"}


@app.post("/upload")
def upload_script(
    file: UploadFile = File(...),
    genre: str = Query("general", description="Podcast genre for market research"),
    max_segments: Optional[int] = Query(
        None, ge=1, description="Lite mode: render at most N dialogue segments to save TTS quota"
    ),
):
    """Upload a podcast script PDF and run the full pipeline synchronously."""
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "File must be a PDF")
        upload_path = _save_upload(file)
        return JSONResponse(_process_pipeline(upload_path, genre, max_segments))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/jobs/upload")
def start_upload_job(
    file: UploadFile = File(...),
    genre: str = Query("general"),
    max_segments: Optional[int] = Query(None, ge=1),
):
    """Start the full pipeline as a background job; returns a job id to poll."""
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "File must be a PDF")
        upload_path = _save_upload(file)
        job_id = _submit_job(
            "upload",
            lambda: _process_pipeline(upload_path, genre, max_segments),
        )
        return {"status": "started", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/jobs/video")
def start_video_job(
    token: str = Query(..., description="Pack token from /upload response"),
    title: str = Query(None),
):
    """Start video generation as a background job; returns a job id to poll."""
    try:
        _find_pack(token)  # validate early
        job_id = _submit_job("video", lambda: _run_video_job(token, title), token=token)
        return {"status": "started", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Poll a background job. Returns status + result once complete."""
    job = _get_job(job_id)
    body = {"id": job["id"], "kind": job["kind"], "status": job["status"]}
    if job["status"] == "done":
        body["result"] = job["result"]
    elif job["status"] == "error":
        body["error"] = job["error"]
    return body


@app.post("/analyze")
def analyze_script_only(file: UploadFile = File(...)):
    """Analyze script without generating audio."""
    try:
        upload_path = _save_upload(file)
        parser = PDFScriptParser()
        script_data = parser.parse(upload_path)
        return JSONResponse({
            "status": "success",
            "script_analysis": script_data,
            "message": "Script analysis complete",
        })
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download generated files (audio segments, music, or the production pack)."""
    path = safe_join(Config.OUTPUT_DIR, filename)
    if path and os.path.exists(path):
        media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type, filename=os.path.basename(path))
    raise HTTPException(404, "File not found")


@app.get("/pack/{token}")
async def download_pack(token: str):
    """Download an existing production pack by token."""
    path = safe_join(Config.OUTPUT_DIR, f"podcraft_pack_{token}.zip")
    if path and os.path.exists(path):
        return FileResponse(path, media_type="application/zip", filename=os.path.basename(path))
    raise HTTPException(404, "Pack not found")


@app.post("/video")
def generate_video(
    token: str = Query(..., description="Pack token from /upload response"),
    title: str = Query(None, description="Optional episode title for the video overlay"),
):
    """Generate an MP4 (waveform + speaker banners) from an existing pack.

    Also emits a combined MP3 + SRT and appends video/mp3/srt to the pack.
    """
    try:
        return JSONResponse(_run_video_job(token, title))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/rss")
def podcast_rss():
    """Serve a minimal RSS feed of the latest production pack(s)."""
    ensure_dirs(Config.OUTPUT_DIR)
    packs = sorted(
        (f for f in os.listdir(Config.OUTPUT_DIR) if f.startswith("podcraft_pack_") and f.endswith(".zip")),
        reverse=True,
    )
    items = []
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    for pack_name in packs[:5]:
        pack_path = os.path.join(Config.OUTPUT_DIR, pack_name)
        try:
            with zipfile.ZipFile(pack_path) as zf:
                manifest = json.loads(zf.read("production_manifest.json"))
        except Exception:
            continue
        title = (manifest.get("episode_meta") or {}).get("title") or pack_name
        description = ((manifest.get("script_analysis") or {}).get("full_text") or "")[:300]
        enclosure = ""
        if base_url:
            enclosure = (
                f'<enclosure url="{base_url}/download/{pack_name}" '
                f'type="application/zip" length="0"/>'
            )
        items.append(
            f"<item><title>{escape(title)}</title>"
            f"<description>{escape(description)}</description>{enclosure}"
            f"<guid>{escape(pack_name)}</guid></item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel><title>PodCraft Productions</title>'
        "<link>https://github.com/RusticAngel/PodCraft</link>"
        "<description>AI-generated podcast episodes from PodCraft</description>"
        + "".join(items)
        + "</channel></rss>"
    )
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/health")
async def health_check():
    from src.tools.gemini_tts import GeminiTTSTool
    from src.tools.lyria_music import LyriaMusicTool
    from src.tools.sentiment_analyzer import SentimentAnalyzerTool
    from src.phase3_partner_integration.parallel_search import ParallelResearchTool

    tools = {
        "Gemini/TTS": GeminiTTSTool().configured,
        "Lyria": LyriaMusicTool().configured,
        "Sentiment": SentimentAnalyzerTool().configured,
        "Parallel": ParallelResearchTool().configured,
    }
    return {"status": "healthy", "services": list(tools.keys()), "configured": tools}


if __name__ == "__main__":
    import uvicorn
    import os

    ensure_dirs(Config.UPLOAD_DIR, Config.OUTPUT_DIR, Config.STATIC_DIR)
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
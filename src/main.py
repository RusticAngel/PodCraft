import mimetypes
import os
import shutil
import zipfile
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy orchestrator so the app boots minus API keys.
_ORCHESTRATOR = None


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
async def upload_script(
    file: UploadFile = File(...),
    genre: str = Query("general", description="Podcast genre for market research"),
    max_segments: Optional[int] = Query(
        None, ge=1, description="Lite mode: render at most N dialogue segments to save TTS quota"
    ),
):
    """Upload a podcast script PDF and start production."""
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "File must be a PDF")

        upload_path = _save_upload(file)

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

        return JSONResponse({
            "status": "success",
            "data": result,
            "message": "Podcast production complete!",
            "download_url": f"/download/{os.path.basename(pack_path)}",
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/analyze")
async def analyze_script_only(file: UploadFile = File(...)):
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
async def generate_video(
    token: str = Query(..., description="Pack token from /upload response"),
    title: str = Query(None, description="Optional episode title for the video overlay"),
):
    """Generate an MP4 (waveform + speaker banners) from an existing pack.

    Also emits a combined MP3 + SRT and appends video/mp3/srt to the pack.
    """
    try:
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

        return JSONResponse({
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
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/rss")
async def podcast_rss():
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
            f"<item><title>{title}</title><description>{description}</description>{enclosure}"
            f"<guid>{pack_name}</guid></item>"
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
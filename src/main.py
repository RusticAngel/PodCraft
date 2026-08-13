import mimetypes
import os
import shutil
import zipfile
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from src.phase4_adk_agents.orchestrator import PodcastOrchestrator
from src.phase2_document_processing.pdf_parser import PDFScriptParser
from src.config import Config
from src.utils.file_handlers import safe_filename, safe_join, ensure_dirs, stable_token

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

        pack_path = _build_pack(upload_path, result)

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
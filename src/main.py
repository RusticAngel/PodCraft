import mimetypes
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
import shutil

from src.phase4_adk_agents.orchestrator import PodcastOrchestrator
from src.phase2_document_processing.pdf_parser import PDFScriptParser
from src.config import Config
from src.utils.file_handlers import safe_filename, safe_join, ensure_dirs

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

        return JSONResponse({
            "status": "success",
            "data": result,
            "message": "Podcast production complete!",
            "download_url": f"/download/{os.path.basename(upload_path)}",
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
    """Download generated audio files."""
    path = safe_join(Config.OUTPUT_DIR, filename)
    if path and os.path.exists(path):
        media_type = mimetypes.guess_type(path)[0] or "audio/wav"
        return FileResponse(path, media_type=media_type)
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
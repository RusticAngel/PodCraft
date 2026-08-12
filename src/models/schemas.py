from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ScriptRequest(BaseModel):
    genre: Optional[str] = "general"


class UploadResponse(BaseModel):
    status: str
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    download_url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    status: str
    script_analysis: Dict[str, Any]
    message: str = ""


class ProcessResponse(BaseModel):
    status: str
    script_analysis: Dict[str, Any]
    director_notes: Dict[str, Any]
    market_research: Dict[str, Any]
    audio_production: Dict[str, Any]
    recommendations: List[str]
    download_url: str


class HealthResponse(BaseModel):
    status: str = "healthy"
    services: List[str] = Field(default_factory=list)
    configured: Dict[str, bool] = Field(default_factory=dict)


class AudioFileInfo(BaseModel):
    index: int
    speaker: str
    text: str
    audio_path: str
    voice: str


class SpeakerProfile(BaseModel):
    speaker: str
    role: str
    voice: str
    utterance_count: int
    is_primary: bool
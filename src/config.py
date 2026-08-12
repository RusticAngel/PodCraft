import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Google Cloud
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
    CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    GEMINI_TTS_MODEL = os.getenv(
        "GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"
    )

    # Lyria 3 (music) - uses the SAME Gemini API key
    LYRIA_MODEL = os.getenv("LYRIA_MODEL", "lyria-3-clip-preview")

    # Parallel
    PARALLEL_API_KEY = os.getenv("PARALLEL_API_KEY")

    # TTS voices (Gemini-native audio output voices)
    DEFAULT_VOICE = os.getenv("DEFAULT_TTS_VOICE", "Puck")
    SECONDARY_VOICE = os.getenv("SECONDARY_TTS_VOICE", "Charon")

    # Directories
    UPLOAD_DIR = "./uploads"
    OUTPUT_DIR = "./outputs"
    STATIC_DIR = "./static"
    DEMO_SCRIPT = os.path.join(STATIC_DIR, "demo_script.pdf")
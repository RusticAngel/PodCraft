import os
from typing import Optional
from src.config import Config
from src.tools.audio_utils import synth_placeholder_wav
from src.utils.file_handlers import stable_token, ensure_dirs
from src.utils.api_retry import call_with_retry


class LyriaMusicTool:
    """Generate background music using Lyria 3 via the Gemini API.

    Lyria 3 models (`lyria-3-clip-preview`, `lyria-3-pro-preview`) are
    accessed through the Gemini API with the same GEMINI_API_KEY (paid
    tier required). Falls back to a mood-tinted placeholder WAV so the
    pipeline stays demo-able without a paid key.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = Config.LYRIA_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate_music(self, mood: str = "calm", duration_seconds: int = 30) -> Optional[str]:
        """Generate background music matching the mood."""
        ensure_dirs(Config.OUTPUT_DIR)

        real = self._generate_lyria(mood, duration_seconds)
        if real:
            return real

        print("Music: using placeholder generation (Lyria key not configured or unavailable)")
        return synth_placeholder_wav(mood, duration_seconds)

    def _generate_lyria(self, mood: str, duration_seconds: int) -> Optional[str]:
        if not self.configured:
            return None
        try:
            client = self._get_client()
            prompt = (
                f"Create a {duration_seconds}-second {mood} background music bed "
                "for a podcast, gentle piano and soft strings, no vocals, "
                "professional mastering quality."
            )
            response = call_with_retry(lambda: client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"response_modalities": ["AUDIO"]},
            ))

            audio_data = None
            mime_type = "audio/mpeg"
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    audio_data = part.inline_data.data
                    mime_type = getattr(part.inline_data, "mime_type", "audio/mpeg") or "audio/mpeg"
                    break
            if not audio_data:
                return None

            ext = ".mp3" if mime_type == "audio/mpeg" else ".wav"
            filename = f"music_{stable_token(mood, duration_seconds)}{ext}"
            output_path = os.path.join(Config.OUTPUT_DIR, filename)
            with open(output_path, "wb") as f:
                f.write(audio_data)
            return output_path

        except Exception as e:
            print(f"Lyria error: {e}")
            return None
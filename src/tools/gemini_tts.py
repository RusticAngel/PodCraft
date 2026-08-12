import os
import re
import wave
from typing import Optional
from src.config import Config
from src.utils.file_handlers import stable_token, ensure_dirs
from src.utils.api_retry import call_with_retry


class GeminiTTSTool:
    """Generate speech using Gemini TTS (native audio output modality).

    Gemini TTS returns raw 16-bit PCM (`audio/L16;codec=pcm;rate=24000`)
    by default; this tool wraps it into a standard WAV container so the
    output is directly playable. Client is created lazily so the app boots
    without a GEMINI_API_KEY.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = Config.GEMINI_TTS_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate_speech(self, text: str, voice: str = None) -> Optional[str]:
        """Generate speech audio from text. Returns a WAV/MP3 path or None.

        Caches by (text, voice): if a matching file already exists on disk
        it is reused, so repeated runs don't consume daily TTS quota.
        """
        if not self.configured:
            print("TTS skipped: GEMINI_API_KEY not configured")
            return None

        voice = voice or Config.DEFAULT_VOICE
        ensure_dirs(Config.OUTPUT_DIR)

        token = stable_token(text, voice)
        cached = os.path.join(Config.OUTPUT_DIR, f"speech_{token}.wav")
        if os.path.exists(cached):
            print("TTS: using cached audio")
            return cached

        try:
            client = self._get_client()
            response = call_with_retry(lambda: client.models.generate_content(
                model=self.model,
                contents=text,
                config={
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": voice,
                            }
                        }
                    },
                },
            ))

            mime_type = None
            audio_data = None
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    audio_data = part.inline_data.data
                    mime_type = getattr(part.inline_data, "mime_type", None) or ""
                    break

            if not audio_data:
                print("TTS response contained no audio data")
                return None

            return self._write_audio(audio_data, mime_type, token)

        except Exception as e:
            print(f"TTS error: {e}")
            return None

    @staticmethod
    def _write_audio(audio_data: bytes, mime_type: str, token: str) -> str:
        """Persist audio bytes to disk in the right container."""
        if mime_type.startswith("audio/L16"):
            rate = GeminiTTSTool._pcm_rate(mime_type, default=24000)
            return GeminiTTSTool._write_pcm_wav(audio_data, rate, token)

        if "mpeg" in mime_type:
            output_path = os.path.join(Config.OUTPUT_DIR, f"speech_{token}.mp3")
            with open(output_path, "wb") as f:
                f.write(audio_data)
            return output_path

        ext = ".wav" if "wav" in mime_type else ".bin"
        output_path = os.path.join(Config.OUTPUT_DIR, f"speech_{token}{ext}")
        with open(output_path, "wb") as f:
            f.write(audio_data)
        return output_path

    @staticmethod
    def _pcm_rate(mime_type: str, default: int = 24000) -> int:
        match = re.search(r"rate=(\d+)", mime_type)
        return int(match.group(1)) if match else default

    @staticmethod
    def _write_pcm_wav(pcm_data: bytes, sample_rate: int, token: str) -> str:
        """Wrap raw mono 16-bit PCM into a playable WAV file."""
        output_path = os.path.join(Config.OUTPUT_DIR, f"speech_{token}.wav")
        with wave.open(output_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm_data)
        return output_path
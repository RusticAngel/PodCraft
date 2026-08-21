from typing import Any, Dict
import time

from .base_agent import BaseAgent
from src.tools.gemini_tts import GeminiTTSTool
from src.tools.lyria_music import LyriaMusicTool
from src.tools.sentiment_analyzer import SentimentAnalyzerTool
from src.phase2_document_processing.speaker_identifier import SpeakerIdentifier

AUDIO_PRODUCER_SYSTEM_INSTRUCTION = """
You are an Audio Production AI. Your role is to generate high-quality audio assets for podcast production.

TASKS:
1. Convert script text to speech using Gemini TTS (multi-speaker)
2. Generate appropriate background music using Lyria 3
3. Perform sentiment analysis on audio vs. script
4. Ensure audio quality and timing
5. Output complete audio files

OUTPUT FORMAT:
Return a JSON with:
- audio_files: dict with paths to generated audio
- music_files: dict with paths to background music
- sentiment_analysis: dict with tone comparisons
- production_notes: dict with timing and quality metrics
"""


class AudioProducerAgent(BaseAgent):
    """Generates audio assets using Gemini TTS and Lyria 3."""

    def __init__(self, model_name: str = None):
        super().__init__(model_name)
        self.tts_tool = GeminiTTSTool()
        self.music_tool = LyriaMusicTool()
        self.sentiment_tool = SentimentAnalyzerTool()
        self.speaker_identifier = SpeakerIdentifier()

    def create_agent(self) -> Any:
        config = {
            "name": "audio_producer_agent",
            "model": self.model_name,
            "system_instruction": AUDIO_PRODUCER_SYSTEM_INSTRUCTION,
            "tools": [self._produce_audio],
        }
        return self._coerce_config(config)

    def run(self, script_data: Dict, director_analysis: Dict, max_segments: int = None,
            voice_overrides: Dict = None) -> Any:
        """Generate audio assets from script and analysis.

        max_segments limits how many dialogue segments get rendered to
        speech ("lite demo mode") so free-tier daily TTS quota is preserved.
        voice_overrides maps a speaker name to a preferred TTS voice.
        """
        input_payload = {
            "dialogue_segments": script_data.get("dialogue_segments", []),
            "speakers": script_data.get("speakers", []),
            "tone": (director_analysis or {}).get("tone", "neutral"),
            "pacing": (director_analysis or {}).get("pacing", {}),
            "structure": (director_analysis or {}).get("structure", {}),
            "max_segments": max_segments,
            "voice_overrides": voice_overrides or {},
        }

        if not self.uses_agent_engine:
            return self._fallback(input_payload)

        agent = self.create_agent()
        try:
            return agent.run(input_payload)
        except Exception as e:
            print(f"Audio producer agent error: {e}")
            return self._fallback(input_payload)

    def _fallback(self, payload: Dict) -> Dict:
        return self._produce_audio(payload)

    def _produce_audio(self, production_params: Dict) -> Dict:
        """Tool function for audio production."""
        segments = production_params.get("dialogue_segments", [])
        speakers = production_params.get("speakers", [])
        tone = production_params.get("tone", "neutral")
        max_segments = production_params.get("max_segments")
        voice_overrides = production_params.get("voice_overrides") or {}

        selected, original_indices = self._pick_segments(segments, max_segments)

        speaker_profiles = self.speaker_identifier.identify(
            speakers, selected, voice_overrides=voice_overrides
        )

        audio_files = []
        for index, segment in zip(original_indices, selected):
            speaker = segment.get("speaker", "Narrator")
            text = segment.get("text", "")
            if not text:
                continue

            voice = self.speaker_identifier.assign_voice(
                speaker, speaker_profiles, voice_overrides=voice_overrides
            )
            audio_path = self.tts_tool.generate_speech(text, voice)
            audio_files.append({
                "index": index,
                "speaker": speaker,
                "text": text,
                "audio_path": audio_path,
                "voice": voice,
            })

        audio_files = self._retry_failed_segments(audio_files)

        music_path = self.music_tool.generate_music(tone, duration_seconds=30)

        sentiment = self.sentiment_tool.analyze_sentiment(
            script_text=" ".join([s.get("text", "") for s in segments if s.get("text")])
        )

        return {
            "audio_files": audio_files,
            "music_path": music_path,
            "sentiment_analysis": sentiment,
            "speaker_profiles": speaker_profiles,
            "total_segments": len(audio_files),
            "failed_segments": sum(1 for a in audio_files if not a.get("audio_path")),
            "lite_mode": max_segments is not None and max_segments < len(segments),
        }

    def _retry_failed_segments(self, audio_files: list, pause_seconds: float = 20.0) -> list:
        """Second-chance pass: re-attempt segments whose TTS failed.

        A transient 429/5xx mid-job used to leave a silent hole in the
        episode even though every later segment succeeded. Wait briefly
        (lets a per-minute quota window roll over), then retry each
        failed segment once via the disk cache or a fresh call.
        """
        failed = [entry for entry in audio_files if not entry.get("audio_path")]
        if not failed:
            return audio_files

        print(f"Audio producer: {len(failed)} segment(s) missing audio; "
              f"retrying once after {pause_seconds:.0f}s cooldown")
        time.sleep(pause_seconds)
        for entry in failed:
            retry_path = self.tts_tool.generate_speech(entry["text"], entry["voice"])
            if retry_path:
                print(f"Audio producer: recovered segment {entry['index']} on retry")
                entry["audio_path"] = retry_path
        return audio_files

    @staticmethod
    def _pick_segments(segments: list, max_segments: int = None):
        """Sample dialogue segments across the episode when max_segments
        limits the render. Always includes the first and last segments and
        spaces the rest evenly so different speakers stay represented."""
        if max_segments is None or max_segments >= len(segments) or len(segments) == 0:
            return segments, list(range(len(segments)))

        n = max(1, int(max_segments))
        if n == 1:
            idx = [0]
        else:
            idx = sorted(set(round(i * (len(segments) - 1) / (n - 1)) for i in range(n)))
        return [segments[i] for i in idx], idx
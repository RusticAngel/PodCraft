from typing import Any, Dict
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

    def run(self, script_data: Dict, director_analysis: Dict) -> Any:
        """Generate audio assets from script and analysis."""
        input_payload = {
            "dialogue_segments": script_data.get("dialogue_segments", []),
            "speakers": script_data.get("speakers", []),
            "tone": (director_analysis or {}).get("tone", "neutral"),
            "pacing": (director_analysis or {}).get("pacing", {}),
            "structure": (director_analysis or {}).get("structure", {}),
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

        speaker_profiles = self.speaker_identifier.identify(speakers, segments)

        audio_files = []
        for index, segment in enumerate(segments):
            speaker = segment.get("speaker", "Narrator")
            text = segment.get("text", "")
            if not text:
                continue

            voice = self.speaker_identifier.assign_voice(speaker, speaker_profiles)
            audio_path = self.tts_tool.generate_speech(text, voice)
            audio_files.append({
                "index": index,
                "speaker": speaker,
                "text": text,
                "audio_path": audio_path,
                "voice": voice,
            })

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
        }
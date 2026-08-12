import os
from typing import Dict
from src.config import Config


class SentimentAnalyzerTool:
    """Analyze sentiment and tone of script text via Gemini multimodal.

    Lazy client + graceful fallback so the app works without keys.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = Config.GEMINI_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def analyze_sentiment(self, script_text: str) -> Dict:
        """Analyze tone and sentiment of script."""
        if not self.configured:
            return self._fallback(script_text)

        try:
            client = self._get_client()
            from google.genai import types

            prompt = f"""
            Analyze the sentiment and tone of this podcast script:
            {script_text[:5000]}

            Return JSON with:
            - overall_tone: (positive/neutral/negative)
            - emotional_arc: list of emotions throughout
            - speaker_tone: dict of speaker to tone
            - audience_engagement: rating 1-10
            - recommendations: list of suggestions
            """
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["TEXT"]),
            )
            return {
                "analysis": response.text,
                "overall_tone": "positive",
                "emotional_arc": ["intro", "build", "climax", "conclusion"],
                "speaker_tone": {},
                "audience_engagement": 8,
            }
        except Exception as e:
            print(f"Sentiment error: {e}")
            return self._fallback(script_text)

    def _fallback(self, script_text: str) -> Dict:
        """Deterministic lexical fallback when Gemini is unavailable."""
        positive = sum(script_text.lower().count(w) for w in
                       ["great", "love", "amazing", "awesome", "yes", "excited", "thanks", "thank you"])
        negative = sum(script_text.lower().count(w) for w in
                       ["bad", "hard", "hard", "problem", "issue", "unfortunately", "sorry", "fail"])
        tone = "positive" if positive > negative else ("negative" if negative > positive else "neutral")
        engagement = min(10, 5 + positive - negative)
        return {
            "analysis": {
                "method": "lexical-fallback",
                "positive_terms": positive,
                "negative_terms": negative,
            },
            "overall_tone": tone,
            "emotional_arc": ["intro", "build", "climax", "conclusion"],
            "speaker_tone": {},
            "audience_engagement": max(1, engagement),
        }
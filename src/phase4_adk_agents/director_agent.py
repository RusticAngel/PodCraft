from typing import Any, Dict
from .base_agent import BaseAgent

DIRECTOR_SYSTEM_INSTRUCTION = """
You are a Podcast Director AI. Your role is to analyze podcast scripts and prepare them for production.

TASKS:
1. Analyze script structure (intro, segments, outro)
2. Identify speaker roles and their speaking patterns
3. Determine overall tone and mood
4. Suggest pacing and emphasis for different sections
5. Identify production cues (music, sound effects, pauses)

OUTPUT FORMAT:
Return a JSON with:
- structure: dict with sections
- speakers: list with speaking style notes
- tone: string describing overall mood
- pacing: recommendations for each section
- production_notes: list of cues
"""


class DirectorAgent(BaseAgent):
    """Analyzes script structure, tone, and production requirements."""

    def create_agent(self) -> Any:
        config = {
            "name": "director_agent",
            "model": self.model_name,
            "system_instruction": DIRECTOR_SYSTEM_INSTRUCTION,
            "tools": [self._analyze_structure],
        }
        return self._coerce_config(config)

    def run(self, script_data: Dict) -> Any:
        """Run director analysis on script data."""
        input_payload = {
            "script_text": script_data.get("full_text", ""),
            "speakers": script_data.get("speakers", []),
            "dialogue_segments": script_data.get("dialogue_segments", []),
            "mood": script_data.get("mood", "neutral"),
            "estimated_duration": script_data.get("estimated_duration", 30),
        }

        # Fallback when Agent Engine / API keys are unavailable: run the
        # local heuristic tool so the pipeline still produces output.
        if not self.uses_agent_engine:
            return self._fallback(input_payload)

        agent = self.create_agent()
        try:
            return agent.run(input_payload)
        except Exception as e:
            print(f"Director agent error: {e}")
            return self._fallback(input_payload)

    def _fallback(self, payload: Dict) -> Dict:
        structure = self._analyze_structure(payload)
        return {
            "structure": structure,
            "speakers": [
                {"speaker": s, "style": "natural, conversational"} for s in payload.get("speakers", [])
            ],
            "tone": payload.get("mood", "neutral"),
            "pacing": {
                "overall": f"{payload.get('estimated_duration', 30)} minute episode",
                "recommendation": "Maintain steady conversational pacing; pause before key ideas.",
            },
            "production_notes": ["Intro bed", "Segment transitions", "Outro CTA"],
        }

    def _analyze_structure(self, script_data: Dict) -> Dict:
        """Tool function for analyzing script structure."""
        segments = script_data.get("dialogue_segments", [])
        total_words = len(script_data.get("script_text", "").split())

        return {
            "segments": len(segments),
            "speakers": list(dict.fromkeys(
                s.get("speaker") for s in segments if s.get("speaker")
            )),
            "total_words": total_words,
            "estimated_podcast_duration_minutes": total_words / 150,
        }
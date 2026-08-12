from typing import Dict, List
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .director_agent import DirectorAgent
from .researcher_agent import ResearcherAgent
from .audio_producer_agent import AudioProducerAgent
from src.phase2_document_processing.pdf_parser import PDFScriptParser
from src.phase2_document_processing.speaker_identifier import SpeakerIdentifier
from src.phase3_partner_integration.parallel_search import ParallelResearchTool
import os


class PodcastOrchestrator:
    """Orchestrates the complete multi-agent workflow."""

    def __init__(self):
        self.director = DirectorAgent()
        self.researcher = ResearcherAgent()
        self.producer = AudioProducerAgent()
        self.parser = PDFScriptParser()
        self.speaker_identifier = SpeakerIdentifier()
        self.parallel_tool = ParallelResearchTool()

    def process_script(self, pdf_path: str, genre: str = "general") -> Dict:
        """
        Complete multi-agent pipeline:
        1. Parse PDF -> structured data
        2. Director analyzes structure and tone
        3. Researcher finds market intelligence
        4. Producer generates audio assets
        """
        os.makedirs("./uploads", exist_ok=True)
        os.makedirs("./outputs", exist_ok=True)

        print("\U0001f4c4 Step 1: Parsing PDF script...")
        script_data = self.parser.parse(pdf_path)
        script_data["genre"] = genre

        print("\U0001f3ac Step 2: Director analyzing script...")
        director_analysis = self.director.run(script_data)

        print("\U0001f50d Step 3: Researcher gathering market data...")
        research = self.researcher.run(script_data, director_analysis)

        print("\U0001f3b5 Step 4: Producer generating audio...")
        audio_output = self.producer.run(script_data, director_analysis)

        print("\u2705 Orchestration complete!")

        speaker_profiles = self.speaker_identifier.identify(
            script_data.get("speakers", []),
            script_data.get("dialogue_segments", []),
        )

        return {
            "script_analysis": script_data,
            "speaker_profiles": speaker_profiles,
            "director_notes": director_analysis,
            "market_research": research,
            "audio_production": audio_output,
            "recommendations": self._generate_recommendations(
                script_data, director_analysis, research
            ),
            "status": "success",
        }

    def _generate_recommendations(self, script_data: Dict, analysis: Dict, research: Dict) -> List[str]:
        """Generate production recommendations."""
        recommendations = []

        # Based on script analysis
        if len(script_data.get("speakers", [])) > 3:
            recommendations.append(
                "Consider assigning unique voices to each speaker for better listener engagement."
            )

        # Based on market research
        comparable = research.get("comparable_podcasts", []) if isinstance(research, dict) else []
        comparable = [c for c in comparable if isinstance(c, dict) and c.get("title")]
        if comparable:
            recommendations.append(
                f"Format similar to {comparable[0].get('title', 'popular podcasts')} - consider adopting their pacing."
            )

        # Based on estimated duration
        duration = script_data.get("estimated_duration", 30)
        if duration > 60:
            recommendations.append(
                "Consider breaking this episode into 2 parts for better listener retention."
            )
        elif duration < 15:
            recommendations.append(
                "Episode is very short; consider adding an intro recap for completeness."
            )

        recommendations.append(
            "Use the mood-matched background music bed under the intro and outro for a polished finish."
        )

        return recommendations
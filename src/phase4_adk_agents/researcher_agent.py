from typing import Any, Dict
from .base_agent import BaseAgent
from src.phase3_partner_integration.parallel_search import ParallelResearchTool

RESEARCHER_SYSTEM_INSTRUCTION = """
You are a Podcast Research AI. Your role is to provide market intelligence for podcast production.

TASKS:
1. Research successful podcasts in similar genres
2. Identify audience preferences and trends
3. Find comparable podcast formats and structures
4. Gather data on episode lengths, release schedules, and engagement
5. Provide recommendations based on market data

OUTPUT FORMAT:
Return a JSON with:
- market_data: dict with findings
- comparable_podcasts: list with details
- audience_insights: dict with demographics and preferences
- recommendations: list of actionable suggestions
"""


class ResearcherAgent(BaseAgent):
    """Researches podcast market using Parallel Search API."""

    def __init__(self, model_name: str = None):
        super().__init__(model_name)
        self.parallel_tool = ParallelResearchTool()

    def create_agent(self) -> Any:
        config = {
            "name": "researcher_agent",
            "model": self.model_name,
            "system_instruction": RESEARCHER_SYSTEM_INSTRUCTION,
            "tools": [self._search_podcast_market],
        }
        return self._coerce_config(config)

    def run(self, script_data: Dict, director_analysis: Dict) -> Any:
        """Run research based on script content and director analysis."""
        input_payload = {
            "topics": script_data.get("topics", []) or director_analysis.get("topics", []),
            "genre": script_data.get("genre", "general"),
            "mood": script_data.get("mood", "neutral"),
            "estimated_duration": script_data.get("estimated_duration", 30),
        }

        if not self.uses_agent_engine:
            return self._fallback(input_payload)

        agent = self.create_agent()
        try:
            return agent.run(input_payload)
        except Exception as e:
            print(f"Researcher agent error: {e}")
            return self._fallback(input_payload)

    def _fallback(self, payload: Dict) -> Dict:
        market = self._search_podcast_market(payload)
        return {
            "market_data": market,
            "comparable_podcasts": market.get("comparable_podcasts", []),
            "audience_insights": {
                "interest_alignment": f"Topics align with active {payload.get('genre', 'general')} listeners",
                "preferred_length": "20-40 minute episodes dominate in this niche",
            },
            "recommendations": [
                "Use a tight 30-minute format for higher completion rates",
                "Publish on a fixed weekly cadence",
            ],
        }

    def _search_podcast_market(self, research_params: Dict) -> Dict:
        """Tool function for searching podcast market data."""
        topics = research_params.get("topics", [])
        genre = research_params.get("genre", "general")

        results = []
        comparable = []
        for topic in topics[:3]:
            search_results = self.parallel_tool.search_podcast_data(topic, genre)
            for item in search_results:
                if not isinstance(item, dict) or "error" in item or not item.get("title"):
                    continue
                results.append(item)
                if len(comparable) < 5:
                    comparable.append({
                        "title": item["title"],
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                    })

        return {
            "market_research": results[:10],
            "similar_podcasts_count": len(results),
            "comparable_podcasts": comparable[:5],
            "trending_topics": topics[:5],
            "search_configured": self.parallel_tool.configured,
        }
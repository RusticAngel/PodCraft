from abc import ABC, abstractmethod
from typing import Any, Dict
import os


class BaseAgent(ABC):
    """Abstract base class for all ADK agents.

    Vertex AI / Agent Engine (ADK) is initialized lazily so that the
    FastAPI app boots even when no credentials or project are configured.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = "us-central1"
        self._vertex_initialized = False

    def _init_vertex(self):
        """Lazily initialize Vertex AI. Safe to call repeatedly."""
        if self._vertex_initialized:
            return True
        if not self.project_id:
            return False
        try:
            from google.cloud import aiplatform

            aiplatform.init(project=self.project_id, location=self.location)
            self._vertex_initialized = True
            return True
        except Exception as e:
            print(f"Vertex AI init skipped: {e}")
            return False

    @property
    def uses_agent_engine(self) -> bool:
        """Whether Agent Engine (ADK) can be used for this run."""
        return self._init_vertex()

    @abstractmethod
    def create_agent(self) -> Any:
        """Create and return the ADK agent instance."""
        raise NotImplementedError

    @abstractmethod
    def run(self, input_data: Dict) -> Any:
        """Run the agent with given input."""
        raise NotImplementedError

    @staticmethod
    def _coerce_config(config: Dict) -> Any:
        """Build a ReasoningEngine/FastAgent config when ADK is available."""
        try:
            from vertexai.preview import reasoning_engines

            return reasoning_engines.ReasoningEngine.from_config(config)
        except Exception:
            try:
                from google.adk.agents import Agent as AdkAgent
                from google.genai import types

                return AdkAgent(
                    name=config.get("name", "agent"),
                    model=config.get("model"),
                    system_instruction=config.get("system_instruction"),
                    tools=config.get("tools", []),
                )
            except Exception as e:
                return {"error": f"ADK agent creation unavailable: {e}"}
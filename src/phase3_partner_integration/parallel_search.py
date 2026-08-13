from typing import Dict, List, Optional
import os

try:
    from parallel_web import ParallelSearch as _ParallelSearchClient
    _HAS_PARALLEL_WEB = True
except Exception:  # pragma: no cover - package may not be installed
    _HAS_PARALLEL_WEB = False

try:
    # parallel-web 1.2.0+ exposes the client as `parallel.Parallel`
    from parallel import Parallel as _ParallelSearchClient  # type: ignore
    _HAS_PARALLEL_WEB = True
except Exception:  # pragma: no cover
    pass

try:
    import requests
    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    _HAS_REQUESTS = False


class ParallelResearchTool:
    """Ground agents in real-time web data using Parallel Search.

    Uses the `parallel-web` SDK when installed, otherwise falls back to a
    direct HTTP client. Free tier intended for OpenCode agents.
    """

    HTTP_API_URL = "https://api.parallel.ai/v1/search"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PARALLEL_API_KEY")
        self._client = None
        if self.api_key and _HAS_PARALLEL_WEB:
            try:
                self._client = _ParallelSearchClient(api_key=self.api_key)
            except Exception:
                self._client = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search_podcast_data(self, topic: str, genre: str = None) -> List[Dict]:
        """Search for podcast industry data."""
        genre_part = f"{genre} " if genre else ""
        query = f"best {genre_part}podcasts about {topic} audience engagement trends"
        return self._search(query)

    def search_competitor_analysis(self, podcast_title: str) -> List[Dict]:
        """Research similar podcasts."""
        query = f"{podcast_title} podcast review ratings audience size"
        return self._search(query)

    def _search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Execute search and return structured results.

        Parallel Search is free via MCP without a key; when a key IS
        configured we call the Search API directly.
        """
        if not self.configured:
            return [{"error": "Parallel API key not configured (free MCP at https://search.parallel.ai/mcp is also available)"}]

        try:
            if self._client is not None:
                return self._search_sdk(query, max_results)
            if _HAS_REQUESTS:
                return self._search_http(query, max_results)
            return [{"error": "No HTTP client available for Parallel Search"}]
        except Exception as e:
            return [{"error": str(e)}]

    def _search_sdk(self, query: str, max_results: int) -> List[Dict]:
        response = self._client.search(
            objective=query,
            search_queries=[query],
            mode="turbo",
        )
        raw = response.get("results") if isinstance(response, dict) else getattr(response, "results", None)
        if isinstance(raw, list):
            return self._normalize(raw)[:max_results]
        return self._normalize([])[:max_results]

    def _search_http(self, query: str, max_results: int) -> List[Dict]:
        response = requests.post(
            self.HTTP_API_URL,
            json={
                "objective": query,
                "search_queries": [query],
                "mode": "turbo",
            },
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        return self._normalize(results)[:max_results]

    @staticmethod
    def _normalize(raw_results) -> List[Dict]:
        if not raw_results:
            return []
        normalized = []
        for r in raw_results:
            if not isinstance(r, dict):
                model_dump = getattr(r, "model_dump", None)
                r = model_dump() if callable(model_dump) else None
            if not isinstance(r, dict):
                continue
            excerpts = r.get("excerpts") or []
            snippet = " ".join(excerpts)[:500] if isinstance(excerpts, list) else (excerpts or "")
            normalized.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": snippet or r.get("snippet", "") or r.get("description", ""),
                "published_date": r.get("publish_date", "") or r.get("published_date", "") or r.get("date", ""),
            })
        return normalized
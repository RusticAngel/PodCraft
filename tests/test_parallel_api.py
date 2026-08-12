import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.phase3_partner_integration.parallel_search import ParallelResearchTool


def test_not_configured_returns_clear_error(monkeypatch):
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    tool = ParallelResearchTool(api_key=None)
    assert tool.configured is False
    result = tool._search("best podcasts")
    assert result[0]["error"].startswith("Parallel API key not configured")


def test_search_podcast_data_builds_query(monkeypatch):
    calls = {}

    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    tool = ParallelResearchTool(api_key="test-key")

    def fake_search(query, max_results=10):
        calls["query"] = query
        return [{"title": "Podcast A", "url": "https://a", "snippet": "snippet"}]

    monkeypatch.setattr(tool, "_search", fake_search)
    tool.search_podcast_data("AI", "technology")
    assert "AI" in calls["query"]
    assert "technology" in calls["query"]


def test_normalize_results():
    raw = [{"title": "T", "url": "U", "snippet": "S", "extra": "x"}, "not-a-dict"]
    out = ParallelResearchTool._normalize(raw)
    assert len(out) == 1
    assert out[0]["title"] == "T"
    assert "extra" not in out[0]


def test_search_podcast_data_without_configured(monkeypatch):
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    tool = ParallelResearchTool(api_key=None)
    result = tool.search_podcast_data("AI")
    assert result[0]["error"]  # graceful message, no crash
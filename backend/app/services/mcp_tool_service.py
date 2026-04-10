from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.services.web_search_service import WebSearchService


class MCPToolService:
    """
    Minimal MCP-like external tool bridge.
    In production this class can be replaced by real MCP server connectors.
    """

    def __init__(self, web_service: WebSearchService | None = None) -> None:
        self._enabled = bool(getattr(settings, "mcp_tools_enabled", True))
        self._timeout = max(2.0, float(getattr(settings, "mcp_timeout_seconds", 6.0)))
        self._nasa_api_key = str(getattr(settings, "mcp_nasa_api_key", "DEMO_KEY") or "DEMO_KEY")
        self._web_service = web_service or WebSearchService()
        self._headers = {"User-Agent": "AstroGraph-MCP/1.0"}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def query_latest_astronomy(self, query: str) -> dict[str, Any] | None:
        if not self._enabled:
            return None

        q = str(query or "").strip()
        if not q:
            return None

        apod = self._tool_nasa_apod()
        wiki = self._tool_wiki_search(q)
        now_iso = datetime.now(timezone.utc).isoformat()

        if apod is None and wiki is None:
            return None

        snippets: list[str] = []
        citations: list[str] = []
        tool_calls: list[dict[str, str]] = []

        if apod is not None:
            snippets.append(
                f"[NASA APOD {apod.get('date', '')}] {apod.get('title', '')}: {apod.get('summary', '')}"
            )
            if apod.get("url"):
                citations.append(f"mcp:nasa_apod:{apod['url']}")
            tool_calls.append({"tool": "nasa_apod", "status": "ok"})

        if wiki is not None:
            snippets.append(f"[{wiki.get('title', 'Wikipedia')}] {wiki.get('summary', '')}")
            if wiki.get("url"):
                citations.append(f"mcp:wikipedia:{wiki['url']}")
            tool_calls.append({"tool": "wiki_search", "status": "ok"})

        return {
            "provider": "mcp_tool_service",
            "query": q,
            "fetched_at": now_iso,
            "summary": "\n".join([s for s in snippets if s]).strip(),
            "citations": citations,
            "tool_calls": tool_calls,
        }

    def _tool_nasa_apod(self) -> dict[str, Any] | None:
        url = "https://api.nasa.gov/planetary/apod"
        try:
            with httpx.Client(timeout=self._timeout, headers=self._headers) as client:
                resp = client.get(url, params={"api_key": self._nasa_api_key})
                resp.raise_for_status()
                payload = resp.json()
            title = str(payload.get("title") or "").strip()
            explanation = str(payload.get("explanation") or "").strip()
            page = str(payload.get("hdurl") or payload.get("url") or "").strip()
            date = str(payload.get("date") or "").strip()
            if not (title or explanation):
                return None
            summary = explanation[:600]
            return {"title": title, "summary": summary, "url": page, "date": date}
        except Exception:
            return None

    def _tool_wiki_search(self, query: str) -> dict[str, Any] | None:
        if not self._web_service.enabled:
            return None
        result = self._web_service.search(query)
        if not result:
            return None
        return {
            "title": str(result.get("title") or "").strip(),
            "summary": str(result.get("summary") or "").strip()[:700],
            "url": str(result.get("url") or "").strip(),
        }


from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings


class WebSearchService:
    """
    Lightweight real-time web search fallback.
    Uses Wikipedia OpenSearch + page summary API, no API key required.
    """

    def __init__(self) -> None:
        self._enabled = bool(getattr(settings, "web_search_enabled", True))
        self._timeout = max(2.0, float(getattr(settings, "web_search_timeout_seconds", 6.0)))
        self._headers = {
            "User-Agent": "AstroGraph/1.0 (educational-research; +https://example.com/contact)"
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    def search(self, query: str) -> dict[str, Any] | None:
        if not self._enabled:
            return None
        q = str(query or "").strip()
        if not q:
            return None

        candidates = [q]
        simplified = self._simplify_query(q)
        if simplified and simplified.lower() != q.lower():
            candidates.append(simplified)

        for cand in candidates:
            for lang in ("zh", "en"):
                result = self._search_lang(cand, lang)
                if result is not None:
                    return result
        return None

    @staticmethod
    def _simplify_query(query: str) -> str:
        q = str(query or "").strip()
        if not q:
            return q
        low = q.lower()
        remove_en = [
            "what is the latest update about",
            "latest update about",
            "what is",
            "tell me about",
            "who is",
        ]
        for t in remove_en:
            if low.startswith(t):
                q = q[len(t) :].strip(" ?,.")
                break
        # Chinese lightweight cleanup
        q = re.sub(r"^(请问|我想知道|最新的|最近的)", "", q).strip(" ，。？?！!")
        return q.strip()

    def _search_lang(self, query: str, lang: str) -> dict[str, Any] | None:
        base = f"https://{lang}.wikipedia.org"
        opensearch_url = f"{base}/w/api.php"
        params = {
            "action": "opensearch",
            "search": query,
            "limit": 1,
            "namespace": 0,
            "format": "json",
        }
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True, headers=self._headers) as client:
                resp = client.get(opensearch_url, params=params)
                resp.raise_for_status()
                payload = resp.json()
            if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
                return None
            title = str(payload[1][0]).strip()
            if not title:
                return None
            summary_url = f"{base}/api/rest_v1/page/summary/{quote(title)}"
            with httpx.Client(timeout=self._timeout, follow_redirects=True, headers=self._headers) as client:
                summary_resp = client.get(summary_url)
                summary_resp.raise_for_status()
                summary_payload = summary_resp.json()
            extract = str(summary_payload.get("extract") or "").strip()
            page_url = (
                str(summary_payload.get("content_urls", {}).get("desktop", {}).get("page") or "").strip()
                or f"{base}/wiki/{quote(title)}"
            )
            if not extract:
                return None
            return {
                "title": title,
                "summary": extract,
                "url": page_url,
                "provider": f"wikipedia_{lang}",
            }
        except Exception:
            return None

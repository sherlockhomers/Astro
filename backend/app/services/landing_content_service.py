from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from functools import wraps
from typing import Any

import requests

from app.config import settings


def _with_retry(func):
    """Simple retry wrapper for instance methods using exponential backoff."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        max_attempts, base_delay = 3, 0.8
        for attempt in range(max_attempts):
            try:
                return func(self, *args, **kwargs)
            except (TimeoutError, ConnectionError, OSError, requests.RequestException):
                if attempt == max_attempts - 1:
                    raise
                import time as _time
                _time.sleep(base_delay * (2 ** attempt))
    return wrapper


class LandingContentService:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "AstroLanding/1.0 (+https://127.0.0.1)",
                "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
            }
        )
        self._lock = threading.Lock()
        self._news_cache: list[dict[str, Any]] = []
        self._news_cache_at = 0.0
        self._frontier_cache: dict[str, Any] = {"topics": []}
        self._frontier_cache_at = 0.0
        self._cards_cache: list[dict[str, Any]] = self._build_science_cards()

    @_with_retry
    def get_apod(self) -> dict[str, Any]:
        """NASA APOD JSON；失败时返回本地可展示的降级数据（供前端 img 使用，避免 iframe 被拒）。"""
        key = str(getattr(settings, "mcp_nasa_api_key", "") or "").strip()
        if not key or key.upper() in {"NASA-KEY-REQUIRED", ""}:
            key = "DEMO_KEY"
        try:
            resp = self._session.get(
                "https://api.nasa.gov/planetary/apod",
                params={"api_key": key, "thumbs": True},
                timeout=14,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                media_type = str(data.get("media_type", "")).strip().lower()
                if media_type == "image":
                    return data
                thumb = str(data.get("thumbnail_url", "")).strip()
                if thumb:
                    patched = dict(data)
                    patched["media_type"] = "image"
                    patched["url"] = thumb
                    patched["hdurl"] = thumb
                    return patched
        except Exception:
            pass
        return self._fallback_apod()

    def _fallback_apod(self) -> dict[str, Any]:
        return {
            "title": "大麦哲伦星云中的恒星形成区",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "explanation": (
                "大麦哲伦星云（LMC）边缘一个极其活跃的恒星形成区，充满星际气体与尘埃，"
                "是研究恒星诞生的天然实验室。"
            ),
            "media_type": "image",
            "url": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2574&auto=format&fit=crop",
            "hdurl": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2574&auto=format&fit=crop",
        }

    @_with_retry
    def get_news(self, limit: int = 6) -> list[dict[str, Any]]:
        limit = max(3, min(int(limit), 12))
        now = time.time()
        with self._lock:
            if self._news_cache and now - self._news_cache_at < 240:
                return self._news_cache[:limit]

        items: list[dict[str, Any]] = []
        try:
            url = "https://api.spaceflightnewsapi.net/v4/articles/?limit=30&ordering=-published_at"
            resp = self._session.get(url, timeout=12)
            resp.raise_for_status()
            payload = resp.json()
            for article in payload.get("results", []):
                title = str(article.get("title", "")).strip()
                link = str(article.get("url", "")).strip()
                image = str(article.get("image_url", "")).strip()
                source = str(article.get("news_site", "")).strip() or "Space News"
                summary = str(article.get("summary", "")).strip()
                published = str(article.get("published_at", "")).strip()
                if not title or not link or not image:
                    continue
                items.append(
                    {
                        "title": title,
                        "url": link,
                        "image_url": image,
                        "source": source,
                        "summary": self._trim_text(summary, 180),
                        "date": self._normalize_date(published),
                    }
                )
                if len(items) >= max(limit, 8):
                    break
        except Exception:
            items = []

        if len(items) < limit:
            items = self._fallback_news(limit=max(limit, 6))

        dedup: list[dict[str, Any]] = []
        seen = set()
        for x in items:
            key = str(x.get("url", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(x)
            if len(dedup) >= limit:
                break

        with self._lock:
            self._news_cache = dedup
            self._news_cache_at = time.time()
        return dedup

    def get_science_cards(self, limit: int = 8) -> list[dict[str, Any]]:
        limit = max(4, min(int(limit), 16))
        return self._cards_cache[:limit]

    def get_frontier(self, per_topic: int = 30) -> dict[str, Any]:
        # 前端要分页，一栏给 30~60 条都不算过分
        per_topic = max(9, min(int(per_topic), 60))
        now = time.time()
        with self._lock:
            cached_max = max((len(t.get("items", [])) for t in self._frontier_cache.get("topics", [])), default=0)
            # 缓存足够新、且条数不比这次要的少，就直接返
            if self._frontier_cache.get("topics") and cached_max >= per_topic and now - self._frontier_cache_at < 300:
                return self._frontier_cache

        topics_config = [
            ("exoplanet", "系外行星与行星科学", "cat:astro-ph.EP"),
            ("cosmology", "宇宙学与大尺度结构", "cat:astro-ph.CO"),
            ("stellar", "恒星演化与高能天体", "cat:astro-ph.SR"),
        ]
        topics: list[dict[str, Any]] = []
        for key, label, query in topics_config:
            items = self._fetch_arxiv(query=query, max_results=per_topic)
            topics.append({"key": key, "label": label, "items": items})

        if not any(t["items"] for t in topics):
            topics = self._fallback_frontier()

        payload = {
            "updated_at": datetime.utcnow().isoformat(),
            "topics": topics,
            "source": "arXiv",
        }
        with self._lock:
            self._frontier_cache = payload
            self._frontier_cache_at = time.time()
        return payload

    @_with_retry
    def _fetch_arxiv(self, query: str, max_results: int) -> list[dict[str, Any]]:
        try:
            resp = self._session.get(
                "https://export.arxiv.org/api/query",
                params={
                    "search_query": query,
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                timeout=14,
            )
            resp.raise_for_status()
        except Exception:
            return []

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        papers: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", ns):
            title = self._norm_ws(entry.findtext("atom:title", "", ns))
            link = self._norm_ws(entry.findtext("atom:id", "", ns))
            published = self._norm_ws(entry.findtext("atom:published", "", ns))
            summary = self._norm_ws(entry.findtext("atom:summary", "", ns))
            journal_ref = self._norm_ws(entry.findtext("arxiv:journal_ref", "", ns))
            primary = entry.find("arxiv:primary_category", ns)
            category = primary.attrib.get("term", "") if primary is not None else ""

            author_nodes = entry.findall("atom:author/atom:name", ns)
            authors = [self._norm_ws(a.text or "") for a in author_nodes if self._norm_ws(a.text or "")]

            if not title or not link:
                continue
            papers.append(
                {
                    "title": title,
                    "url": link,
                    "date": self._normalize_date(published),
                    "summary": self._trim_text(summary, 170),
                    "journal_ref": journal_ref,
                    "category": category,
                    "authors": authors[:4],
                    "source": "arXiv",
                }
            )
        return papers

    def _build_science_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "太阳",
                "type": "恒星",
                "image_url": "https://www.solarsystemscope.com/textures/download/2k_sun.jpg",
                "desc": "太阳是太阳系中心恒星，驱动地球气候与生命活动。",
                "facts": {"直径": "1,392,700 km", "表面温度": "约5500°C", "年龄": "约46亿年", "轨道位置": "银河系猎户臂"},
                "url": "https://science.nasa.gov/sun/",
            },
            {
                "name": "水星",
                "type": "行星",
                "image_url": "https://www.solarsystemscope.com/textures/download/2k_mercury.jpg",
                "desc": "太阳系最小行星，昼夜温差极大。",
                "facts": {"直径": "4,879 km", "公转周期": "88 天", "卫星数": "0", "平均温度": "-180°C 到 430°C"},
                "url": "https://science.nasa.gov/mercury/",
            },
            {
                "name": "金星",
                "type": "行星",
                "image_url": "https://www.solarsystemscope.com/textures/download/2k_venus_surface.jpg",
                "desc": "金星拥有浓厚二氧化碳大气，温室效应极强。",
                "facts": {"直径": "12,104 km", "公转周期": "225 天", "卫星数": "0", "地表温度": "约462°C"},
                "url": "https://science.nasa.gov/venus/",
            },
            {
                "name": "地球",
                "type": "行星",
                "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/The_Earth_seen_from_Apollo_17.jpg/1280px-The_Earth_seen_from_Apollo_17.jpg",
                "desc": "目前唯一已知存在生命的行星，拥有稳定液态水。",
                "facts": {"直径": "12,742 km", "公转周期": "365.25 天", "卫星数": "1", "平均温度": "约15°C"},
                "url": "https://science.nasa.gov/earth/",
            },
            {
                "name": "火星",
                "type": "行星",
                "image_url": "https://www.solarsystemscope.com/textures/download/2k_mars.jpg",
                "desc": "火星是最受关注的类地行星之一，存在古水活动证据。",
                "facts": {"直径": "6,779 km", "公转周期": "687 天", "卫星数": "2", "平均温度": "-63°C"},
                "url": "https://science.nasa.gov/mars/",
            },
            {
                "name": "木星",
                "type": "行星",
                "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/be/Solarsystemscope_texture_2k_jupiter.jpg/1920px-Solarsystemscope_texture_2k_jupiter.jpg",
                "desc": "太阳系最大行星，具有巨型风暴和强磁场。",
                "facts": {"直径": "139,820 km", "公转周期": "4333 天", "卫星数": "95+", "平均温度": "-145°C"},
                "url": "https://science.nasa.gov/jupiter/",
            },
            {
                "name": "土星",
                "type": "行星",
                "image_url": "https://www.solarsystemscope.com/textures/download/2k_saturn.jpg",
                "desc": "以壮观环系统著称，环由冰与岩屑构成。",
                "facts": {"直径": "116,460 km", "公转周期": "10759 天", "卫星数": "146+", "平均温度": "-178°C"},
                "url": "https://science.nasa.gov/saturn/",
            },
            {
                "name": "黑洞",
                "type": "高能天体",
                "image_url": "https://www.nasa.gov/wp-content/uploads/2023/03/2890_blackhole.jpg",
                "desc": "黑洞是时空极端弯曲区域，事件视界内连光也无法逃逸。",
                "facts": {"关键区域": "事件视界", "相关现象": "吸积盘与喷流", "探测方式": "X射线/引力波", "代表目标": "M87* / Sgr A*"},
                "url": "https://science.nasa.gov/universe/black-holes/",
            },
        ]

    def _fallback_news(self, limit: int) -> list[dict[str, Any]]:
        data = [
            {
                "title": "NASA finalizes science plans for Artemis 2 lunar flyby",
                "url": "https://spacenews.com/nasa-finalizes-science-plans-for-artemis-2-lunar-flyby/",
                "image_url": "https://spacenews.com/wp-content/uploads/2026/04/artemis2.jpg",
                "source": "SpaceNews",
                "summary": "NASA confirms detailed science timeline for Artemis II mission around the Moon.",
                "date": "2026-04-04",
            },
            {
                "title": "Orion Spacecraft Races Toward Historic Lunar Flyby in Artemis II Mission",
                "url": "https://www.nasaspaceflight.com/2026/04/orion-lunar-flyby-artemis-ii/",
                "image_url": "https://www.nasaspaceflight.com/wp-content/uploads/2026/04/orion-artemis2.jpg",
                "source": "NASASpaceflight",
                "summary": "Orion approaches key mission milestones during Artemis II deep-space phase.",
                "date": "2026-04-04",
            },
            {
                "title": "ESA publishes new Euclid deep field map",
                "url": "https://www.esa.int/Science_Exploration/Space_Science/Euclid",
                "image_url": "https://www.esa.int/var/esa/storage/images/esa_multimedia/images/2026/04/euclid_deep_field/26000000-1-eng-GB/Euclid_deep_field_pillars.jpg",
                "source": "ESA",
                "summary": "New Euclid data release improves dark matter and large-scale structure measurements.",
                "date": "2026-04-03",
            },
        ]
        return data[:limit]

    def _fallback_frontier(self) -> list[dict[str, Any]]:
        def build_items(prefix: str) -> list[dict[str, Any]]:
            rows = []
            for i in range(1, 16):
                rows.append(
                    {
                        "title": f"{prefix} Frontier Study {i}",
                        "url": "https://arxiv.org/list/astro-ph/new",
                        "date": "2026-04-01",
                        "summary": "Latest astronomy preprint from arXiv.",
                        "journal_ref": "",
                        "category": "astro-ph",
                        "authors": [],
                        "source": "arXiv",
                    }
                )
            return rows

        return [
            {"key": "exoplanet", "label": "系外行星与行星科学", "items": build_items("Exoplanet")},
            {"key": "cosmology", "label": "宇宙学与大尺度结构", "items": build_items("Cosmology")},
            {"key": "stellar", "label": "恒星演化与高能天体", "items": build_items("Stellar")},
        ]

    def _normalize_date(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return datetime.utcnow().strftime("%Y-%m-%d")
        for token in ("Z", "z"):
            if raw.endswith(token):
                raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        # RFC2822-like fallback
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return raw[:10]

    def _trim_text(self, text: str, max_len: int) -> str:
        t = self._norm_ws(text)
        if len(t) <= max_len:
            return t
        return t[: max_len - 1].rstrip() + "…"

    def _norm_ws(self, text: str) -> str:
        return " ".join(str(text or "").split())

from __future__ import annotations

import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.services.data_service import DataService
from app.services.vector_search_service import VectorSearchService


QUERY_EXPANSION_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("黑洞", "black hole", "事件视界", "event horizon"), ("黑洞", "事件视界", "奇点", "引力透镜效应")),
    (("中子星", "neutron star", "脉冲星", "pulsar"), ("中子星", "脉冲星", "简并态物质", "磁场极强")),
    (("系外行星", "exoplanet", "宜居", "habitable"), ("系外行星", "宜居带", "凌日", "径向速度")),
    (("银河系", "milky way", "星系"), ("银河系", "旋臂", "银河系中心", "暗物质")),
    (("仙女座", "andromeda"), ("仙女座星系", "本星系群", "星系碰撞")),
    (("木星", "jupiter", "木星大红斑"), ("木星", "木星大红斑", "伽利略卫星", "气态巨行星")),
    (("土星", "saturn", "土星环", "环"), ("土星", "土星环", "卡西尼号", "土卫六")),
    (("火星", "mars", "红色", "火星车"), ("火星", "火星车", "水冰", "火星探测")),
    (("太阳", "sun", "日冕", "太阳风"), ("太阳", "日冕", "核聚变", "太阳黑子")),
    (("月球", "moon", "月球"), ("月球", "潮汐", "月球环形山", "阿波罗")),
    (("最新", "最近", "实时", "today", "latest", "recent"), ("最新", "发现", "观测", "进展")),
]


class RetrievalService:
    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service
        self._vector_service = VectorSearchService(data_service)
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    def search(self, query: str, top_k: int) -> tuple[list[dict], str]:
        top_k = max(1, min(int(top_k), 20))
        cache_key = self._cache_key("search", query, None, top_k)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached["items"], cached["note"]

        expanded_query, expanded_terms = self._expand_query(query)
        if self._data_service.loaded:
            items = self._vector_service.search_text(expanded_query, top_k)
            note = "已使用向量语义检索 + BM25关键词匹配"
            if expanded_terms:
                note += f" （自动扩展关键词：{'、'.join(expanded_terms[:4])}）"
            self._put_cache(cache_key, items, note)
            return deepcopy(items), note

        items = [
            {
                "id": f"doc-{i + 1}",
                "title": f"关于{query}的模拟结果 {i + 1}",
                "score": round(0.92 - i * 0.07, 3),
                "source": "mock",
                "snippet": "数据源尚未加载，当前为模拟结果。",
                "image_url": f"/api/v1/image/placeholder?text={quote(f'{query}-{i + 1}')}"
            }
            for i in range(top_k)
        ]
        note = "数据源尚未加载，返回的是模拟占位结果。"
        self._put_cache(cache_key, items, note)
        return deepcopy(items), note

    def hybrid_search(self, query: str, image_hint: str | None, top_k: int) -> tuple[list[dict], str]:
        top_k = max(1, min(int(top_k), 20))
        normalized_hint = str(image_hint or "").strip() or None
        cache_key = self._cache_key("hybrid", query, normalized_hint, top_k)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached["items"], cached["note"]

        expanded_query, expanded_terms = self._expand_query(query)
        if self._data_service.loaded:
            merged = self._vector_service.hybrid_search(expanded_query, normalized_hint, top_k)
            if normalized_hint:
                note = (
                    f"已使用语义向量检索 + 图片线索「{normalized_hint}」多模态融合，"
                    "结合文本与视觉特征进行综合排序。"
                )
            else:
                note = "已使用语义向量检索与关键词混合排序返回结果。"
            if expanded_terms:
                note += f" （自动扩展关键词：{'、'.join(expanded_terms[:4])}）"
            self._put_cache(cache_key, merged, note)
            return deepcopy(merged), note

        items, note = self.search(query, top_k)
        self._put_cache(cache_key, items, note)
        return deepcopy(items), note

    def vector_schema(self) -> dict:
        return self._vector_service.get_schema()

    def get_cache_stats(self) -> dict[str, Any]:
        self._prune_cache()
        return {
            "enabled": self._cache_enabled(),
            "ttl_seconds": max(0, int(getattr(settings, "retrieval_cache_ttl_seconds", 0) or 0)),
            "max_entries": max(0, int(getattr(settings, "retrieval_cache_max_entries", 0) or 0)),
            "size": len(self._cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "evictions": self._cache_evictions,
        }

    def _expand_query(self, query: str) -> tuple[str, list[str]]:
        raw = str(query or "").strip()
        if not raw:
            return "", []

        query_lower = raw.lower()
        additions: list[str] = []
        for triggers, expansions in QUERY_EXPANSION_RULES:
            if any(trigger.lower() in query_lower for trigger in triggers):
                for item in expansions:
                    if item.lower() not in query_lower and item not in additions:
                        additions.append(item)

        if not additions:
            return raw, []
        expanded = f"{raw} {' '.join(additions[:6])}".strip()
        return expanded, additions

    def _cache_enabled(self) -> bool:
        return int(getattr(settings, "retrieval_cache_max_entries", 0) or 0) > 0 and int(
            getattr(settings, "retrieval_cache_ttl_seconds", 0) or 0
        ) > 0

    def _cache_key(self, mode: str, query: str, image_hint: str | None, top_k: int) -> str:
        revision = int(getattr(self._data_service, "revision", 0) or 0)
        return f"{revision}|{mode}|{str(query or '').strip().lower()}|{str(image_hint or '').strip().lower()}|{int(top_k)}"

    def _get_cache(self, cache_key: str) -> dict[str, Any] | None:
        if not self._cache_enabled():
            return None
        self._prune_cache()
        payload = self._cache.get(cache_key)
        if payload is None:
            self._cache_misses += 1
            return None
        self._cache.move_to_end(cache_key)
        self._cache_hits += 1
        return {"items": deepcopy(payload.get("items", [])), "note": str(payload.get("note", ""))}

    def _put_cache(self, cache_key: str, items: list[dict], note: str) -> None:
        if not self._cache_enabled():
            return
        self._cache[cache_key] = {
            "items": deepcopy(list(items)),
            "note": str(note or ""),
            "created_at": time.time(),
        }
        self._cache.move_to_end(cache_key)
        self._prune_cache()

    def _prune_cache(self) -> None:
        ttl_seconds = max(0, int(getattr(settings, "retrieval_cache_ttl_seconds", 0) or 0))
        max_entries = max(0, int(getattr(settings, "retrieval_cache_max_entries", 0) or 0))
        if ttl_seconds <= 0 or max_entries <= 0:
            if self._cache:
                self._cache_evictions += len(self._cache)
                self._cache.clear()
            return

        now_ts = time.time()
        expired = [
            key
            for key, payload in self._cache.items()
            if now_ts - float(payload.get("created_at", now_ts)) >= ttl_seconds
        ]
        for key in expired:
            self._cache.pop(key, None)
            self._cache_evictions += 1

        while len(self._cache) > max_entries:
            self._cache.popitem(last=False)
            self._cache_evictions += 1

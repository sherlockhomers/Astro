from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any

from app.config import settings
from app.services.data_service import DataService
from app.services.image_label_utils import astronomy_label_family, is_catalog_like_title, normalize_astronomy_label
from app.services.model_service import ModelService
from app.services.vector_search_service import VectorSearchService


class ImageService:
    _ZH_EN_HINTS: dict[str, str] = {
        "月球": "moon",
        "卫星": "moon",
        "太阳": "sun",
        "木星": "jupiter",
        "土星": "saturn",
        "火星": "mars",
        "金星": "venus",
        "水星": "mercury",
        "天王星": "uranus",
        "海王星": "neptune",
        "冥王星": "pluto",
        "黑洞": "black hole",
        "星云": "nebula",
        "星系": "galaxy",
        "旋涡星系": "spiral galaxy",
        "椭圆星系": "elliptical galaxy",
        "彗星": "comet",
        "小行星": "asteroid",
        "空间站": "space station",
        "国际空间站": "international space station",
        "星座": "constellation",
    }

    _ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
        "太阳": ("太阳", "sun", "sol"),
        "月球": ("月球", "月亮", "moon", "luna"),
        "水星": ("水星", "mercury"),
        "金星": ("金星", "venus"),
        "地球": ("地球", "earth", "terra"),
        "火星": ("火星", "mars"),
        "木星": ("木星", "jupiter"),
        "土星": ("土星", "saturn"),
        "天王星": ("天王星", "uranus"),
        "海王星": ("海王星", "neptune"),
        "冥王星": ("冥王星", "pluto"),
        "黑洞": ("黑洞", "black hole", "black holes"),
        "星云": ("星云", "nebula", "nebulae"),
        "旋涡星系": ("旋涡星系", "spiral galaxy", "spiral galaxies"),
        "椭圆星系": ("椭圆星系", "elliptical galaxy", "elliptical galaxies"),
        "星系": ("星系", "galaxy", "galaxies"),
        "彗星": ("彗星", "comet", "comets"),
        "小行星": ("小行星", "asteroid", "asteroids"),
        "国际空间站": ("国际空间站", "international space station", "iss"),
        "空间站": ("空间站", "space station"),
        "星座": ("星座", "constellation", "constellations"),
    }

    _ZERO_SHOT_LABELS: list[tuple[str, str]] = [
        ("\u6708\u7403", "moon"),
        ("\u592a\u9633", "sun"),
        ("\u6728\u661f", "jupiter"),
        ("\u571f\u661f", "saturn"),
        ("\u706b\u661f", "mars"),
        ("\u91d1\u661f", "venus"),
        ("\u6c34\u661f", "mercury"),
        ("\u6d77\u738b\u661f", "neptune"),
        ("\u5929\u738b\u661f", "uranus"),
        ("\u51a5\u738b\u661f", "pluto"),
        ("\u9ed1\u6d1e", "black hole"),
        ("\u661f\u4e91", "nebula"),
        ("\u65cb\u6da1\u661f\u7cfb", "spiral galaxy"),
        ("\u692d\u5706\u661f\u7cfb", "elliptical galaxy"),
        ("\u661f\u7cfb", "galaxy"),
        ("\u5f57\u661f", "comet"),
        ("\u5c0f\u884c\u661f", "asteroid"),
        ("\u56fd\u9645\u7a7a\u95f4\u7ad9", "international space station"),
        ("\u7a7a\u95f4\u7ad9", "space station"),
        ("\u661f\u5ea7", "constellation"),
    ]

    def __init__(self, data_service: DataService, model_service: ModelService) -> None:
        self._data_service = data_service
        self._model_service = model_service
        self._vector_service = VectorSearchService(data_service)
        self._label_vec_cache: dict[str, list[float]] = {}
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    def predict(self, filename: str, image_bytes: bytes) -> dict:
        cache_key = self._cache_key("predict", image_bytes, filename, 0, 0)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        hint = self.infer_image_hint(image_bytes)
        if hint.get("ok"):
            payload = dict(hint)
            payload.setdefault("filename", filename)
            payload["name"] = self._normalize_entity_name(str(payload.get("name", "") or "")) or str(payload.get("name", "") or "")
            self._put_cache(cache_key, payload)
            return payload

        if self._model_service.ready:
            ok, result = self._model_service.predict_image(image_bytes=image_bytes, filename=filename)
            if ok and isinstance(result, dict):
                payload = dict(result)
                payload.setdefault("ok", True)
                payload.setdefault("filename", filename)
                payload.setdefault("mode", "model")
                payload["name"] = self._normalize_entity_name(str(payload.get("name", "") or payload.get("label", "") or "")) or str(payload.get("name", "") or payload.get("label", "") or "")
                self._put_cache(cache_key, payload)
                return payload

        payload = {
            "ok": False,
            "message": "\u5f53\u524d\u6ca1\u6709\u62ff\u5230\u7a33\u5b9a\u7684\u8bc6\u56fe\u7ed3\u679c\uff0c\u8bf7\u6362\u4e00\u5f20\u4e3b\u4f53\u66f4\u6e05\u6670\u7684\u56fe\u7247\u518d\u8bd5\u3002",
            "filename": filename,
            "label": "unknown",
            "mode": "fallback",
        }
        self._put_cache(cache_key, payload)
        return payload

    def infer_image_hint(self, image_bytes: bytes) -> dict[str, Any]:
        if settings.milvus_enabled:
            from app.services.milvus_clip_service import milvus_clip_service

            mcs = milvus_clip_service
            if mcs._ensure_milvus() and mcs.count_entities() > 0:
                vec = mcs.encode_image_bytes(image_bytes)
                if vec:
                    label_guess = self._classify_image_label(vec, mcs)
                    hits = mcs.search(vec, top_k=3, offset=0)
                    items = self._hits_to_items(hits)
                    retrieval_guess = self._vote_retrieval_label(items)
                    if items:
                        top = items[0]
                        cleaned = self._normalize_entity_name(str(top.get("title", "")))
                        top_score = float(top.get("score", 0.0) or 0.0)
                        if label_guess is not None and cleaned and top_score >= 0.95:
                            label_name, label_score = label_guess
                            label_family = astronomy_label_family(label_name)
                            retrieval_family = astronomy_label_family(cleaned)
                            if not (
                                label_family == "solar_system"
                                and retrieval_family == "small_body"
                                and label_score >= 0.62
                                and top_score < 0.985
                            ):
                                return {
                                    "ok": True,
                                    "name": cleaned,
                                    "label": "retrieved-image",
                                    "confidence": round(top_score, 4),
                                    "mode": "clip_milvus",
                                    "source_image_id": top.get("id"),
                                }
                        if label_guess is not None and retrieval_guess is not None:
                            label_name, label_score = label_guess
                            retrieval_name, retrieval_vote, retrieval_count, retrieval_top_score = retrieval_guess
                            if retrieval_name == label_name:
                                return {
                                    "ok": True,
                                    "name": retrieval_name,
                                    "label": "retrieved-image",
                                    "confidence": round(max(retrieval_top_score, label_score), 4),
                                    "mode": "clip_consensus",
                                    "source_image_id": top.get("id"),
                                }
                            label_family = astronomy_label_family(label_name)
                            retrieval_family = astronomy_label_family(retrieval_name)
                            if (
                                retrieval_name
                                and retrieval_top_score >= 0.92
                                and retrieval_count >= 2
                                and retrieval_vote >= (label_score + 0.22)
                            ):
                                return {
                                    "ok": True,
                                    "name": retrieval_name,
                                    "label": "retrieved-image",
                                    "confidence": round(retrieval_top_score, 4),
                                    "mode": "clip_milvus",
                                    "source_image_id": top.get("id"),
                                }
                            if (
                                label_family == "solar_system"
                                and retrieval_family == "small_body"
                                and label_score >= 0.62
                                and retrieval_top_score < 0.985
                            ):
                                return {
                                    "ok": True,
                                    "name": label_name,
                                    "label": "clip-zeroshot",
                                    "confidence": round(label_score, 4),
                                    "mode": "clip_zeroshot",
                                }
                            if cleaned and label_name != cleaned and label_score >= 0.68 and top_score < 0.90:
                                return {
                                    "ok": True,
                                    "name": label_name,
                                    "label": "clip-zeroshot",
                                    "confidence": round(label_score, 4),
                                    "mode": "clip_zeroshot",
                                }
                        if cleaned and top_score >= 0.66:
                            return {
                                "ok": True,
                                "name": cleaned or top.get("title") or "unknown",
                                "label": "retrieved-image",
                                "confidence": top_score,
                                "mode": "clip_milvus",
                                "source_image_id": top.get("id"),
                            }
                    if label_guess is not None:
                        label_name, score = label_guess
                        return {
                            "ok": True,
                            "name": label_name,
                            "label": "clip-zeroshot",
                            "confidence": round(score, 4),
                            "mode": "clip_zeroshot",
                        }
                    if items:
                        top = items[0]
                        cleaned = self._normalize_entity_name(str(top.get("title", "")))
                        return {
                            "ok": True,
                            "name": cleaned or top.get("title") or "unknown",
                            "label": "retrieved-image",
                            "confidence": float(top.get("score", 0.0)),
                            "mode": "clip_milvus",
                            "source_image_id": top.get("id"),
                        }
        return {"ok": False, "name": "unknown", "label": "unknown", "mode": "unavailable"}

    def search_by_text(self, query: str, page: int = 1, page_size: int = 12) -> dict[str, Any]:
        query = query.strip()
        expanded_query = self._expand_text_query(query)
        page = max(1, page)
        page_size = max(1, min(page_size, 48))
        offset = (page - 1) * page_size
        cache_key = self._text_cache_key("text_search", expanded_query, page, page_size)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if settings.milvus_enabled:
            from app.services.milvus_clip_service import milvus_clip_service

            mcs = milvus_clip_service
            if mcs._ensure_milvus() and mcs.count_entities() > 0:
                vec = mcs.encode_text(expanded_query)
                if vec:
                    hits = mcs.search(vec, top_k=page_size + 1, offset=offset)
                    vector_items = self._hits_to_items(hits[:page_size])
                    lexical_items = self._lexical_search_items(query, limit=max(page_size * 3, 24))
                    payload = {
                        "items": self._merge_text_search_items(query, vector_items, lexical_items, page_size),
                        "page": page,
                        "page_size": page_size,
                        "has_next": len(hits) > page_size or len(lexical_items) > page_size,
                        "mode": "clip_milvus_hybrid",
                        "note": "\u5df2\u6309\u5b9e\u4f53\u8bcd\u5339\u914d\u548c\u5411\u91cf\u76f8\u4f3c\u5ea6\u8054\u5408\u6392\u5e8f\u3002",
                    }
                    self._put_cache(cache_key, payload)
                    return deepcopy(payload)

        payload = self._fallback_text_page(expanded_query, page, page_size)
        self._put_cache(cache_key, payload)
        return deepcopy(payload)

    def search_by_image_bytes(self, data: bytes, page: int = 1, page_size: int = 12) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, 48))
        offset = (page - 1) * page_size
        cache_key = self._cache_key("image_search", data, "", page, page_size)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if settings.milvus_enabled:
            from app.services.milvus_clip_service import milvus_clip_service

            mcs = milvus_clip_service
            if mcs._ensure_milvus() and mcs.count_entities() > 0:
                vec = mcs.encode_image_bytes(data)
                if vec:
                    hits = mcs.search(vec, top_k=page_size + 1, offset=offset)
                    has_next = len(hits) > page_size
                    hits = hits[:page_size]
                    payload = {
                        "items": self._hits_to_items(hits),
                        "page": page,
                        "page_size": page_size,
                        "has_next": has_next,
                        "mode": "clip_milvus",
                        "note": "\u5df2\u6309\u5b9e\u4f53\u8bcd\u5339\u914d\u548c\u5411\u91cf\u76f8\u4f3c\u5ea6\u8054\u5408\u6392\u5e8f\u3002",
                    }
                    self._put_cache(cache_key, payload)
                    return deepcopy(payload)

        payload = {
            "items": [],
            "page": page,
            "page_size": page_size,
            "has_next": False,
            "mode": "unavailable",
            "note": "图像向量库尚未就绪，请先确认 Milvus 已启动并完成索引。",
        }
        self._put_cache(cache_key, payload)
        return deepcopy(payload)

    def get_cache_stats(self) -> dict[str, Any]:
        self._prune_cache()
        return {
            "enabled": self._cache_enabled(),
            "ttl_seconds": max(0, int(getattr(settings, "image_cache_ttl_seconds", 0) or 0)),
            "max_entries": max(0, int(getattr(settings, "image_cache_max_entries", 0) or 0)),
            "size": len(self._cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "evictions": self._cache_evictions,
        }

    def _hits_to_items(self, hits: list[tuple[str, float]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for image_id, raw_score in hits:
            meta = self._data_service.get_image_meta(image_id)
            if not meta:
                continue
            score_disp = max(0.0, min(1.0, (float(raw_score) + 1.0) / 2.0))
            raw_title = str(meta.get("title", ""))
            normalized_title = self._normalize_entity_name(raw_title)
            display_title = normalized_title if normalized_title and (is_catalog_like_title(raw_title) or normalized_title != raw_title) else raw_title
            items.append(
                {
                    "id": image_id,
                    "title": display_title,
                    "source": str(meta.get("source", "")),
                    "score": round(score_disp, 4),
                    "snippet": str(meta.get("ref", ""))[-120:] or "",
                    "image_url": meta.get("url"),
                }
            )
        return items

    def _fallback_text_page(self, query: str, page: int, page_size: int) -> dict[str, Any]:
        if not self._data_service.loaded:
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "has_next": False,
                "mode": "local-hash-fallback",
                "note": "本地图像索引尚未加载完成。",
            }
        expanded = self._expand_text_query(query)
        all_items = self._vector_service.search_text(expanded, top_k=min(500, max(50, page * page_size + page_size)))
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_items[start:end]
        has_next = end < len(all_items)
        return {
            "items": page_items,
            "page": page,
            "page_size": page_size,
            "has_next": has_next,
            "mode": "local-hash-fallback",
            "note": "Milvus 不可用，已回退到本地索引结果。",
        }

    def _lexical_search_items(self, query: str, limit: int = 36) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 120))
        terms = self._collect_query_terms(query)
        if not terms:
            return []

        items_by_id: dict[str, dict[str, Any]] = {}
        for term in terms:
            rows = self._data_service.list_images(term, page=1, page_size=min(limit, 100)).get("items", [])
            for row in rows:
                image_id = str(row.get("image_id", "") or row.get("id", "")).strip()
                if not image_id:
                    continue
                score = self._score_lexical_item(row, terms)
                if score <= 0.0:
                    continue
                payload = {
                    "id": image_id,
                    "title": self._normalize_entity_name(str(row.get("title", "")).strip()) or str(row.get("title", "")).strip(),
                    "source": str(row.get("source", "")).strip(),
                    "score": round(score, 4),
                    "snippet": str(row.get("ref", "") or "")[-120:],
                    "image_url": row.get("url"),
                }
                current = items_by_id.get(image_id)
                if current is None or float(payload["score"]) > float(current.get("score", 0.0) or 0.0):
                    items_by_id[image_id] = payload
        ranked = sorted(items_by_id.values(), key=lambda item: (-float(item.get("score", 0.0)), str(item.get("title", ""))))
        return ranked[:limit]

    def _collect_query_terms(self, query: str) -> list[str]:
        raw = str(query or "").strip()
        if not raw:
            return []
        lowered = raw.lower()
        terms: list[str] = [raw]
        seen = {raw}
        for canonical, aliases in self._ENTITY_ALIASES.items():
            if any(alias.lower() in lowered for alias in aliases):
                for term in (canonical, *aliases):
                    candidate = str(term).strip()
                    if candidate and candidate not in seen:
                        seen.add(candidate)
                        terms.append(candidate)
        for zh, en in self._ZH_EN_HINTS.items():
            if zh in raw and en not in seen:
                seen.add(en)
                terms.append(en)
        return terms

    def _score_lexical_item(self, row: dict[str, Any], terms: list[str]) -> float:
        title = str(row.get("title", "")).strip().lower()
        source = str(row.get("source", "")).strip().lower()
        ref = str(row.get("ref", "")).strip().lower()
        score = 0.0
        for term in terms:
            needle = str(term).strip().lower()
            if not needle:
                continue
            if title == needle or title.startswith(f"{needle} "):
                score = max(score, 0.995)
            elif needle in title:
                score = max(score, 0.975)
            elif needle in ref:
                score = max(score, 0.935)
            elif needle in source:
                score = max(score, 0.91)
        return score

    def _merge_text_search_items(
        self,
        query: str,
        vector_items: list[dict[str, Any]],
        lexical_items: list[dict[str, Any]],
        page_size: int,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in vector_items:
            merged[str(item.get("id", ""))] = dict(item)
        for item in lexical_items:
            item_id = str(item.get("id", ""))
            if item_id in merged:
                merged[item_id]["score"] = round(max(float(merged[item_id].get("score", 0.0) or 0.0), float(item.get("score", 0.0) or 0.0)), 4)
                if item.get("title"):
                    merged[item_id]["title"] = item["title"]
                continue
            merged[item_id] = dict(item)

        query_terms = self._collect_query_terms(query)
        items = list(merged.values())
        items.sort(
            key=lambda item: (
                -self._score_lexical_item(
                    {"title": item.get("title", ""), "source": item.get("source", ""), "ref": item.get("snippet", "")},
                    query_terms,
                ),
                -float(item.get("score", 0.0) or 0.0),
                str(item.get("title", "")),
            )
        )
        return items[:page_size]

    def _expand_text_query(self, query: str) -> str:
        q = query.strip()
        if not q:
            return q
        lowered = q.lower()
        extras: list[str] = []
        for zh, en in self._ZH_EN_HINTS.items():
            if zh in q and en not in lowered:
                extras.append(en)
        if not extras:
            return q
        return f"{q} {' '.join(extras)}"

    def _normalize_entity_name(self, title: str) -> str:
        raw = str(title or "").strip().replace("_", " ")
        if not raw:
            return ""
        normalized = normalize_astronomy_label(raw)
        if normalized:
            return normalized
        known_entities = [label for label, _ in self._ZERO_SHOT_LABELS]
        for name in known_entities:
            if name in raw:
                return name
        t = re.sub(r"\s+\d+$", "", raw)
        t = re.sub(r"\s{2,}", " ", t)
        return t.strip()

    def _classify_image_label(self, image_vec: list[float], mcs: Any) -> tuple[str, float] | None:
        best_name = ""
        best_score = -1.0
        for zh, en in self._ZERO_SHOT_LABELS:
            vec = self._label_vec_cache.get(en)
            if vec is None:
                vec = mcs.encode_text(en)
                if not vec:
                    continue
                self._label_vec_cache[en] = vec
            score = float(sum(a * b for a, b in zip(image_vec, vec)))
            if score > best_score:
                best_score = score
                best_name = zh
        if best_name and best_score >= 0.2:
            return best_name, (best_score + 1.0) / 2.0
        return None

    def _vote_retrieval_label(self, items: list[dict[str, Any]]) -> tuple[str, float, int, float] | None:
        votes: dict[str, float] = {}
        counts: dict[str, int] = {}
        top_scores: dict[str, float] = {}
        for idx, item in enumerate(items[:3]):
            title = str(item.get("title", "")).strip()
            name = self._normalize_entity_name(title)
            if not name:
                continue
            weight = 1.35 if idx == 0 else 0.55 if idx == 1 else 0.35
            score = float(item.get("score", 0.0) or 0.0)
            votes[name] = votes.get(name, 0.0) + score * weight
            counts[name] = counts.get(name, 0) + 1
            top_scores[name] = max(score, top_scores.get(name, 0.0))
        if not votes:
            return None
        best_name = max(votes, key=lambda key: (votes[key], counts.get(key, 0), top_scores.get(key, 0.0)))
        return best_name, votes[best_name], counts.get(best_name, 0), top_scores.get(best_name, 0.0)

    def _cache_enabled(self) -> bool:
        return int(getattr(settings, "image_cache_max_entries", 0) or 0) > 0 and int(
            getattr(settings, "image_cache_ttl_seconds", 0) or 0
        ) > 0

    def _cache_key(self, mode: str, image_bytes: bytes, filename: str, page: int, page_size: int) -> str:
        digest = hashlib.sha1(image_bytes).hexdigest()
        revision = int(getattr(self._data_service, "revision", 0) or 0)
        return f"{revision}|{mode}|{digest}|{filename}|{page}|{page_size}"

    def _text_cache_key(self, mode: str, query: str, page: int, page_size: int) -> str:
        revision = int(getattr(self._data_service, "revision", 0) or 0)
        return f"{revision}|{mode}|{query.lower()}|{page}|{page_size}"

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
        return deepcopy(payload.get("value", {}))

    def _put_cache(self, cache_key: str, value: dict[str, Any]) -> None:
        if not self._cache_enabled():
            return
        self._cache[cache_key] = {"value": deepcopy(value), "created_at": time.time()}
        self._cache.move_to_end(cache_key)
        self._prune_cache()

    def _prune_cache(self) -> None:
        ttl_seconds = max(0, int(getattr(settings, "image_cache_ttl_seconds", 0) or 0))
        max_entries = max(0, int(getattr(settings, "image_cache_max_entries", 0) or 0))
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

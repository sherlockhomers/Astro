from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from typing import Any

from app.services.data_service import DataService

try:
    import numpy as np
except Exception:  # noqa: BLE001
    np = None


TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "what",
    "how",
    "why",
    "是",
    "的",
    "了",
    "和",
    "在",
    "以及",
    "请问",
    "一个",
}


class VectorSearchService:
    """
    ?????????
    - ????????????????????
    - ????BM25 ??????????????
    - ??????????????????????????
    """


    def __init__(self, data_service: DataService, dim: int = 256) -> None:
        self._data_service = data_service
        self._dim = dim
        self._text_rows: list[dict[str, Any]] = []
        self._image_rows: list[dict[str, Any]] = []
        self._text_matrix: Any | None = None
        self._image_matrix: Any | None = None
        self._doc_lengths: list[int] = []
        self._avg_doc_len = 0.0
        self._idf: dict[str, float] = {}
        self._inverted: dict[str, list[tuple[int, int]]] = {}
        self._index_revision = -1
        # 缓存上限 512 条，防止内存无限增长；超出时删除最老条目（近似 LRU）
        self._cache: dict[tuple[str, str, int, int], list[dict[str, Any]]] = {}
        self._cache_order: list[tuple[str, str, int, int]] = []
        self._MAX_CACHE_SIZE = 512

    def _set_cache(self, key: tuple[str, str, int, int], items: list[dict[str, Any]]) -> None:
        """写入缓存并实施近似 LRU 上限淘汰。"""
        if key in self._cache:
            # 已有，移到队尾（最近使用）
            self._cache_order = [k for k in self._cache_order if k != key]
            self._cache_order.append(key)
        else:
            # 新条目，超限则淘汰最老的
            while len(self._cache) >= self._MAX_CACHE_SIZE:
                oldest = self._cache_order.pop(0)
                self._cache.pop(oldest, None)
            self._cache_order.append(key)
        self._cache[key] = items

    def search_text(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        self._ensure_index()
        top_k = max(1, min(int(top_k), 50))
        key = ("text", self._norm_query(query), top_k, self._index_revision)
        hit = self._cache.get(key)
        if hit is not None:
            # LRU：移到队尾
            self._cache_order = [k for k in self._cache_order if k != key]
            self._cache_order.append(key)
            return [dict(x) for x in hit]
        items = self._search_core(
            rows=self._text_rows,
            matrix=self._text_matrix,
            query=query,
            top_k=top_k,
            use_lexical=True,
        )
        self._set_cache(key, [dict(x) for x in items])
        return items

    def search_image_hint(self, image_hint: str, top_k: int = 10) -> list[dict[str, Any]]:
        self._ensure_index()
        top_k = max(1, min(int(top_k), 50))
        key = ("image", self._norm_query(image_hint), top_k, self._index_revision)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache_order = [k for k in self._cache_order if k != key]
            self._cache_order.append(key)
            return [dict(x) for x in hit]
        items = self._search_core(
            rows=self._image_rows,
            matrix=self._image_matrix,
            query=image_hint,
            top_k=top_k,
            use_lexical=False,
        )
        self._set_cache(key, [dict(x) for x in items])
        return items

    def hybrid_search(self, query: str, image_hint: str | None, top_k: int = 10) -> list[dict[str, Any]]:
        top_k = max(1, min(int(top_k), 50))
        text_items = self.search_text(query, top_k=top_k * 2)
        if not image_hint:
            return text_items[:top_k]
        image_items = self.search_image_hint(image_hint, top_k=top_k * 2)
        return self._rrf_merge(text_items, image_items, top_k=top_k)

    def get_schema(self) -> dict[str, Any]:
        return {
            "provider": "local-hash-vector+bm25",
            "milvus_ready": False,
            "cache_size": len(self._cache),
            "collections": {
                "astro_text_vectors": {"dim": self._dim, "metric": "COSINE", "index": "HASH+BM25"},
                "astro_image_vectors": {"dim": self._dim, "metric": "COSINE", "index": "HASH"},
            },
        }

    def _ensure_index(self) -> None:
        if self._index_revision == self._data_service.revision:
            return
        self._build_index(self._data_service.export_entities())

    def _build_index(self, entities: list[dict[str, Any]]) -> None:
        text_rows: list[dict[str, Any]] = []
        image_rows: list[dict[str, Any]] = []
        text_vectors: list[list[float]] = []
        image_vectors: list[list[float]] = []
        doc_tfs: list[Counter[str]] = []
        doc_lengths: list[int] = []

        for entity in entities:
            source_file = str(entity.get("source_file", ""))
            is_image_catalog = source_file.lower() == "images_catalog.csv"
            payload = {
                "id": str(entity.get("id", "")),
                "title": str(entity.get("name", "")),
                "title_lc": str(entity.get("name", "")).strip().lower(),
                "source": source_file,
                "snippet": str(entity.get("description", "")).strip()[:220] or "无描述信息",
                "image_url": None,
            }
            if not is_image_catalog:
                raw_text = self._raw_to_text(entity.get("raw", {}))
                text = f"{entity.get('name', '')} {entity.get('category', '')} {entity.get('description', '')} {raw_text}"
                tokens = self._tokenize(text)
                tf = Counter(tokens)
                vec = self._embed(text)
                row = {**payload, "vector": vec}
                text_rows.append(row)
                text_vectors.append(vec)
                doc_tfs.append(tf)
                doc_lengths.append(sum(tf.values()))

            if entity.get("image_id"):
                ivec = self._embed(f"{entity.get('name', '')} {entity.get('raw', '')}")
                image_rows.append(
                    {
                        **payload,
                        "image_url": f"/api/v1/image/file/{entity['image_id']}",
                        "vector": ivec,
                    }
                )
                image_vectors.append(ivec)

        self._text_rows = text_rows
        self._image_rows = image_rows if image_rows else text_rows
        if np is not None and text_vectors:
            self._text_matrix = np.asarray(text_vectors, dtype="float32")
        else:
            self._text_matrix = None
        if np is not None and image_vectors:
            self._image_matrix = np.asarray(image_vectors, dtype="float32")
        elif np is not None and text_vectors:
            self._image_matrix = np.asarray(text_vectors, dtype="float32")
        else:
            self._image_matrix = None

        self._doc_lengths = doc_lengths
        self._avg_doc_len = (sum(doc_lengths) / max(len(doc_lengths), 1)) if doc_lengths else 0.0
        self._build_lexical_index(doc_tfs)
        self._index_revision = self._data_service.revision
        self._cache.clear()
        self._cache_order.clear()

    def _build_lexical_index(self, doc_tfs: list[Counter[str]]) -> None:
        if not doc_tfs:
            self._idf = {}
            self._inverted = {}
            return
        doc_freq: Counter[str] = Counter()
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for idx, tf in enumerate(doc_tfs):
            for token, freq in tf.items():
                if freq <= 0:
                    continue
                postings[token].append((idx, int(freq)))
                doc_freq[token] += 1
        n_docs = len(doc_tfs)
        idf: dict[str, float] = {}
        for token, df in doc_freq.items():
            idf[token] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        self._idf = idf
        self._inverted = dict(postings)

    def _search_core(
        self,
        rows: list[dict[str, Any]],
        matrix: Any | None,
        query: str,
        top_k: int,
        use_lexical: bool,
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        qvec = self._embed(query)
        qnorm = self._norm_query(query)
        query_tokens = self._tokenize(query)
        exact_query = qnorm if len(qnorm) >= 2 else ""

        if np is not None and matrix is not None and len(rows) == int(matrix.shape[0]):
            qarr = np.asarray(qvec, dtype="float32")
            vec_raw = matrix @ qarr
            combined = ((vec_raw + 1.0) / 2.0).astype("float32")
            if use_lexical:
                combined *= 0.65
                lex_scores = self._bm25_scores(query_tokens)
                if lex_scores:
                    max_lex = max(lex_scores.values())
                    if max_lex > 0:
                        for doc_idx, score in lex_scores.items():
                            combined[doc_idx] += 0.35 * float(score / max_lex)
            if exact_query:
                for idx, row in enumerate(rows):
                    if exact_query in str(row.get("title_lc", "")):
                        combined[idx] += 0.08
            keep_n = min(max(1, top_k * 4), len(rows))
            pick = np.argpartition(combined, -keep_n)[-keep_n:]
            pick = pick[np.argsort(combined[pick])[::-1]]
            items = [self._to_item(rows[int(i)], float(combined[int(i)])) for i in pick[:top_k]]
            return items

        vec_scores: list[float] = [self._cosine(qvec, row["vector"]) for row in rows]
        base_scores = [max(0.0, min(1.0, (x + 1.0) / 2.0)) for x in vec_scores]
        if use_lexical:
            base_scores = [x * 0.65 for x in base_scores]
            lex_scores = self._bm25_scores(query_tokens)
            if lex_scores:
                max_lex = max(lex_scores.values())
                if max_lex > 0:
                    for doc_idx, score in lex_scores.items():
                        base_scores[doc_idx] += 0.35 * float(score / max_lex)
        if exact_query:
            for idx, row in enumerate(rows):
                if exact_query in str(row.get("title_lc", "")):
                    base_scores[idx] += 0.08

        ranked = sorted(enumerate(base_scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [self._to_item(rows[idx], score) for idx, score in ranked]

    def _bm25_scores(self, query_tokens: list[str]) -> dict[int, float]:
        if not query_tokens or not self._inverted:
            return {}
        k1 = 1.5
        b = 0.75
        scores: dict[int, float] = defaultdict(float)
        qtf = Counter(query_tokens)
        for token, qfreq in qtf.items():
            postings = self._inverted.get(token)
            if not postings:
                continue
            idf = self._idf.get(token, 0.0)
            if idf <= 0:
                continue
            q_weight = 1.0 + 0.15 * max(0, qfreq - 1)
            for doc_idx, tf in postings:
                dl = self._doc_lengths[doc_idx] if doc_idx < len(self._doc_lengths) else 1
                denom = tf + k1 * (1.0 - b + b * (dl / max(self._avg_doc_len, 1.0)))
                if denom <= 0:
                    continue
                scores[doc_idx] += idf * (tf * (k1 + 1.0) / denom) * q_weight
        return dict(scores)

    def _embed(self, text: str) -> list[float]:
        tokens = self._tokenize(text)
        if not tokens:
            tokens = [str(text).lower()]
        vec = [0.0] * self._dim
        tf = Counter(tokens)
        for token, freq in tf.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            weight = 1.0 + math.log1p(freq)
            for i in range(0, len(digest), 2):
                pos = digest[i] % self._dim
                vec[pos] += (((digest[i + 1] / 255.0) - 0.5) * weight)
        return self._normalize(vec)

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for m in TOKEN_RE.finditer(str(text)):
            token = m.group(0).strip().lower()
            if len(token) <= 1 or token in STOPWORDS:
                continue
            tokens.append(token)
            if self._contains_cjk(token) and len(token) > 2:
                tokens.extend(token[i : i + 2] for i in range(len(token) - 1))
        return tokens

    def _normalize(self, vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in vec))
        if norm <= 0:
            return vec
        return [v / norm for v in vec]

    def _cosine(self, a: list[float], b: list[float]) -> float:
        return float(sum(x * y for x, y in zip(a, b)))

    def _raw_to_text(self, raw: Any) -> str:
        if not isinstance(raw, dict):
            return str(raw)
        parts: list[str] = []
        for key, value in raw.items():
            if value in (None, "", "nan", "None"):
                continue
            parts.append(f"{key} {value}")
        return " ".join(parts)

    def _norm_query(self, query: str) -> str:
        return " ".join(str(query).strip().lower().split())

    def _contains_cjk(self, token: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in token)

    def _to_item(self, row: dict[str, Any], score: float) -> dict[str, Any]:
        clipped = max(0.0, min(1.0, float(score)))
        return {
            "id": row["id"],
            "title": row["title"],
            "score": round(clipped, 4),
            "source": row["source"],
            "snippet": row["snippet"],
            "image_url": row.get("image_url"),
        }

    def _rrf_merge(self, left: list[dict[str, Any]], right: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        k = 60
        rank_map: dict[str, dict[str, Any]] = {}
        for idx, item in enumerate(left, start=1):
            rank_map[item["id"]] = {**item, "_rrf": 1.0 / (k + idx)}
        for idx, item in enumerate(right, start=1):
            if item["id"] in rank_map:
                rank_map[item["id"]]["_rrf"] += 1.0 / (k + idx)
                rank_map[item["id"]]["score"] = round(
                    max(float(rank_map[item["id"]]["score"]), float(item["score"])),
                    4,
                )
            else:
                rank_map[item["id"]] = {**item, "_rrf": 1.0 / (k + idx)}
        merged = sorted(rank_map.values(), key=lambda x: x["_rrf"], reverse=True)[: max(1, top_k)]
        for item in merged:
            item.pop("_rrf", None)
        return merged

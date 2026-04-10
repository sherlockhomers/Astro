from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger("astrograph")

_DIM = 512
_COLLECTION = "astro_image_clip"


class MilvusClipService:
    """
    CLIP (OpenCLIP ViT-B-32) + Milvus image retrieval.
    - Lazy-load CLIP model.
    - Fast-fail Milvus connect when unavailable (avoid API hanging).
    """

    def __init__(self) -> None:
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device: str | None = None
        self._connected = False
        self._collection = None
        self._last_error: str | None = None
        self._last_connect_attempt_ts: float = 0.0

    @property
    def ready(self) -> bool:
        return bool(self._connected and self._collection is not None and self._model is not None)

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def clip_model_loaded(self) -> bool:
        return self._model is not None

    def prewarm(self) -> dict[str, Any]:
        model_ok = self._ensure_model()
        milvus_ok = False
        entities = 0
        if settings.milvus_enabled:
            milvus_ok = self._ensure_milvus()
            if milvus_ok:
                entities = self.count_entities()
        return {
            "clip_model_loaded": model_ok,
            "milvus_connected": milvus_ok,
            "indexed_vectors": entities,
            "last_error": self._last_error,
        }

    def reset_collection(self) -> dict[str, Any]:
        from pymilvus import connections, utility

        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=str(settings.milvus_port),
            timeout=self._connect_timeout(),
        )
        coll_name = settings.milvus_collection or _COLLECTION
        if utility.has_collection(coll_name):
            utility.drop_collection(coll_name)
        self._connected = False
        self._collection = None
        self._last_error = None
        self._last_connect_attempt_ts = 0.0
        return self.ensure_schema()

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import open_clip
            import torch
        except ImportError as exc:
            self._last_error = f"CLIP dependency missing: {exc}"
            logger.warning(self._last_error)
            return False

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        name = settings.clip_model_name
        pretrained = settings.clip_pretrained
        try:
            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                name, pretrained=pretrained, device=self._device
            )
            self._tokenizer = open_clip.get_tokenizer(name)
            self._model.eval()
            self._last_error = None
            logger.info("CLIP loaded: %s / %s on %s", name, pretrained, self._device)
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"CLIP load failed: {exc}"
            logger.exception(self._last_error)
            return False

    def _connect_timeout(self) -> float:
        return max(0.5, float(getattr(settings, "milvus_connect_timeout_seconds", 1.8)))

    def _fail_cooldown(self) -> float:
        return max(1.0, float(getattr(settings, "milvus_fail_cooldown_seconds", 15.0)))

    def _ensure_milvus(self) -> bool:
        if self._connected and self._collection is not None:
            return True
        if not settings.milvus_enabled:
            self._last_error = "Milvus disabled (MILVUS_ENABLED=false)"
            return False

        now = time.time()
        if self._last_error and (now - self._last_connect_attempt_ts) < self._fail_cooldown():
            return False

        try:
            from pymilvus import Collection, connections, utility
        except ImportError as exc:
            self._last_error = f"pymilvus not installed: {exc}"
            logger.warning(self._last_error)
            return False

        self._last_connect_attempt_ts = now
        try:
            connections.connect(
                alias="default",
                host=settings.milvus_host,
                port=str(settings.milvus_port),
                timeout=self._connect_timeout(),
            )
            self._connected = True
            coll_name = settings.milvus_collection or _COLLECTION
            if not utility.has_collection(coll_name):
                self._last_error = f"Milvus collection not found: {coll_name}"
                logger.warning(self._last_error)
                self._collection = None
                return False
            self._collection = Collection(coll_name)
            self._collection.load()
            self._last_error = None
            logger.info("Milvus connected, collection=%s entities=%s", coll_name, self._collection.num_entities)
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"Milvus connect failed: {exc}"
            logger.warning(self._last_error)
            self._connected = False
            self._collection = None
            return False

    def ensure_schema(self) -> dict[str, Any]:
        """Create collection and index if missing."""
        from pymilvus import (
            Collection,
            CollectionSchema,
            DataType,
            FieldSchema,
            connections,
            utility,
        )

        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=str(settings.milvus_port),
            timeout=self._connect_timeout(),
        )
        # Reset transient connect errors so next _ensure_milvus can retry immediately.
        self._last_error = None
        self._last_connect_attempt_ts = 0.0
        coll_name = settings.milvus_collection or _COLLECTION
        if utility.has_collection(coll_name):
            return {"ok": True, "message": f"collection exists: {coll_name}", "collection": coll_name}

        fields = [
            FieldSchema(name="image_id", dtype=DataType.VARCHAR, is_primary=True, auto_id=False, max_length=64),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=_DIM),
        ]
        schema = CollectionSchema(fields, description="AstroGraph CLIP image vectors")
        col = Collection(name=coll_name, schema=schema)
        col.create_index(
            field_name="vector",
            index_params={
                "metric_type": "IP",
                "index_type": "HNSW",
                "params": {"M": 16, "efConstruction": 200},
            },
        )
        return {"ok": True, "message": f"created collection: {coll_name}", "collection": coll_name}

    def encode_text(self, text: str) -> list[float] | None:
        if not self._ensure_model():
            return None
        import torch

        with torch.no_grad():
            tokens = self._tokenizer([text])
            tokens = tokens.to(self._device)
            feats = self._model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            vec = feats.cpu().numpy().astype("float32")[0].tolist()
        return vec

    def encode_image_bytes(self, data: bytes) -> list[float] | None:
        if not self._ensure_model():
            return None
        from PIL import Image
        import torch

        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"image decode failed: {exc}"
            return None
        tensor = self._preprocess(img).unsqueeze(0).to(self._device)
        with torch.no_grad():
            feats = self._model.encode_image(tensor)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            vec = feats.cpu().numpy().astype("float32")[0].tolist()
        return vec

    def encode_image_path(self, path: str) -> list[float] | None:
        p = Path(path)
        if not p.is_file():
            return None
        return self.encode_image_bytes(p.read_bytes())

    def encode_image_paths_batch(
        self,
        rows: list[tuple[str, str]],
        batch_size: int = 32,
    ) -> tuple[list[tuple[str, list[float]]], int]:
        """
        Batch encode local image paths.
        Returns ([(image_id, vector), ...], skipped_count)
        """
        if not rows:
            return [], 0
        if not self._ensure_model():
            return [], len(rows)
        from PIL import Image
        import torch

        batch_size = max(1, int(batch_size))
        encoded: list[tuple[str, list[float]]] = []
        skipped = 0
        idx = 0
        while idx < len(rows):
            chunk = rows[idx : idx + batch_size]
            idx += batch_size
            image_ids: list[str] = []
            tensors = []
            for image_id, path in chunk:
                p = Path(path)
                if not p.exists() or not p.is_file():
                    skipped += 1
                    continue
                try:
                    with Image.open(p) as img:
                        rgb = img.convert("RGB")
                        tensor = self._preprocess(rgb)
                    tensors.append(tensor)
                    image_ids.append(str(image_id))
                except Exception:  # noqa: BLE001
                    skipped += 1
            if not tensors:
                continue
            input_tensor = torch.stack(tensors).to(self._device)
            with torch.no_grad():
                feats = self._model.encode_image(input_tensor)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                arr = feats.cpu().numpy().astype("float32")
            for i, iid in enumerate(image_ids):
                encoded.append((iid, arr[i].tolist()))
        return encoded, skipped

    def insert_vectors(self, rows: list[tuple[str, list[float]]], flush: bool = True) -> int:
        """Batch insert (image_id, vector)."""
        if not rows:
            return 0
        from pymilvus import Collection, connections

        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=str(settings.milvus_port),
            timeout=self._connect_timeout(),
        )
        coll_name = settings.milvus_collection or _COLLECTION
        col = Collection(coll_name)
        ids = [r[0] for r in rows]
        vecs = [r[1] for r in rows]
        col.insert([ids, vecs])
        if flush:
            col.flush()
            try:
                col.load()
            except Exception:  # noqa: BLE001
                pass
        return len(rows)

    def flush_collection(self, timeout: float | None = None) -> None:
        from pymilvus import Collection, connections

        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=str(settings.milvus_port),
            timeout=self._connect_timeout(),
        )
        coll_name = settings.milvus_collection or _COLLECTION
        col = Collection(coll_name)
        if timeout is None:
            col.flush()
        else:
            col.flush(timeout=timeout)
        try:
            col.load()
        except Exception:  # noqa: BLE001
            pass

    def fetch_existing_ids(self, image_ids: list[str], chunk_size: int = 500) -> set[str]:
        """
        Return IDs that already exist in Milvus collection.
        """
        if not image_ids:
            return set()
        if not self._ensure_milvus() or self._collection is None:
            return set()

        out: set[str] = set()
        chunk_size = max(1, min(int(chunk_size), 1000))
        for i in range(0, len(image_ids), chunk_size):
            chunk = [x for x in image_ids[i : i + chunk_size] if x]
            if not chunk:
                continue
            serialized: list[str] = []
            for raw in chunk:
                escaped = str(raw).replace("\\", "\\\\").replace('"', '\\"')
                serialized.append(f'"{escaped}"')
            expr_values = ",".join(serialized)
            expr = f"image_id in [{expr_values}]"
            try:
                rows = self._collection.query(expr=expr, output_fields=["image_id"])
            except Exception:  # noqa: BLE001
                continue
            for row in rows or []:
                iid = row.get("image_id") if isinstance(row, dict) else None
                if iid:
                    out.add(str(iid))
        return out

    def search(
        self,
        vector: list[float],
        top_k: int = 24,
        offset: int = 0,
    ) -> list[tuple[str, float]]:
        if not self._ensure_milvus() or self._collection is None:
            return []
        if self._collection.num_entities == 0:
            return []
        top_k = max(1, min(top_k, 256))
        offset = max(0, offset)
        need = min(offset + top_k, 2048)
        search_params = {"metric_type": "IP", "params": {"ef": 128}}
        try:
            res = self._collection.search(
                data=[vector],
                anns_field="vector",
                param=search_params,
                limit=need,
                output_fields=["image_id"],
            )
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"Milvus search failed: {exc}"
            logger.warning(self._last_error)
            try:
                self._collection.load()
            except Exception:  # noqa: BLE001
                pass
            return []
        if not res or not res[0]:
            return []
        hits = res[0]
        sliced = hits[offset : offset + top_k]
        out: list[tuple[str, float]] = []
        for hit in sliced:
            entity = getattr(hit, "entity", None)
            iid = entity.get("image_id") if entity is not None else None
            if not iid:
                iid = getattr(hit, "id", "")
            out.append((str(iid), float(hit.distance)))
        return out

    def count_entities(self) -> int:
        if not self._ensure_milvus() or self._collection is None:
            return 0
        return int(self._collection.num_entities)


milvus_clip_service = MilvusClipService()

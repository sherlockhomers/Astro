from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.data_service import DataService
from app.services.image_dedup_service import ImageDedupService


class MilvusIndexService:
    """
    Startup/background Milvus index bootstrap.
    - Never blocks API startup.
    - Can be triggered manually.
    - Keeps progress/status for frontend.
    """

    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service
        self._dedup = ImageDedupService()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._status: dict[str, Any] = {
            "state": "idle",
            "message": "not started",
            "started_at": None,
            "finished_at": None,
            "processed": 0,
            "total": 0,
            "inserted": 0,
            "skipped": 0,
            "existing_vectors": 0,
            "dedup": {},
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            payload = dict(self._status)
        running = bool(self._worker and self._worker.is_alive())
        payload["running"] = running
        payload["enabled"] = bool(settings.milvus_enabled)
        return payload

    def start(self, force: bool = False, csv_root: str | None = None) -> tuple[bool, str]:
        if not settings.milvus_enabled:
            with self._lock:
                self._status.update(
                    {
                        "state": "disabled",
                        "message": "milvus disabled",
                        "started_at": None,
                        "finished_at": datetime.utcnow().isoformat(),
                    }
                )
            return False, "milvus disabled"

        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return False, "index task already running"
            self._status = {
                "state": "running",
                "message": "index task started",
                "started_at": datetime.utcnow().isoformat(),
                "finished_at": None,
                "processed": 0,
                "total": 0,
                "inserted": 0,
                "skipped": 0,
                "existing_vectors": 0,
                "dedup": {},
            }
            self._worker = threading.Thread(
                target=self._run_task,
                args=(force, csv_root),
                daemon=True,
                name="milvus-index-bootstrap",
            )
            self._worker.start()
        return True, "started"

    def _set_status(self, **kwargs: Any) -> None:
        with self._lock:
            self._status.update(kwargs)

    def _run_task(self, force: bool, csv_root: str | None) -> None:
        from app.services.milvus_clip_service import milvus_clip_service

        try:
            if not self._data_service.loaded:
                src = (csv_root or settings.csv_root or "").strip()
                if not src:
                    self._set_status(
                        state="failed",
                        message="CSV_ROOT not configured",
                        finished_at=datetime.utcnow().isoformat(),
                    )
                    return
                self._data_service.load_data_source(src, [])

            rows = self._collect_image_rows()
            source_total = len(rows)
            dedup_summary: dict[str, Any] = {}
            if rows:
                self._set_status(
                    total=source_total,
                    message=f"deduplicating {source_total} images before indexing",
                )
                rows, dedup_summary = self._dedup.deduplicate_rows(rows)
            max_images = int(getattr(settings, "milvus_auto_index_max_images", 0) or 0)
            if max_images > 0:
                rows = rows[:max_images]
            total = len(rows)
            self._set_status(
                total=total,
                dedup=dedup_summary,
                message=f"collected {source_total} images, kept {total} after dedup",
            )
            if total == 0:
                self._set_status(
                    state="completed",
                    message="no image rows found",
                    finished_at=datetime.utcnow().isoformat(),
                )
                return

            if force:
                milvus_clip_service.reset_collection()
            else:
                milvus_clip_service.ensure_schema()
            if not milvus_clip_service._ensure_milvus():
                self._set_status(
                    state="failed",
                    message=milvus_clip_service.last_error or "milvus not ready",
                    finished_at=datetime.utcnow().isoformat(),
                )
                return

            existing_vectors = milvus_clip_service.count_entities()
            self._set_status(existing_vectors=existing_vectors)

            pending_rows = rows
            if existing_vectors > 0 and not force:
                all_ids = [iid for iid, _ in rows]
                existing_ids = milvus_clip_service.fetch_existing_ids(all_ids)
                pending_rows = [row for row in rows if row[0] not in existing_ids]
                self._set_status(skipped=(total - len(pending_rows)))

            if not pending_rows:
                self._set_status(
                    state="completed",
                    message=f"already indexed ({existing_vectors} vectors)",
                    finished_at=datetime.utcnow().isoformat(),
                    processed=total,
                )
                return

            batch_size = max(8, int(getattr(settings, "milvus_auto_index_batch_size", 64)))
            clip_batch_size = max(4, int(getattr(settings, "milvus_auto_index_clip_batch_size", 24)))

            inserted = 0
            processed = 0
            skipped = int(self.status().get("skipped", 0))
            started_ts = time.perf_counter()
            flush_every = 2000
            last_flushed_inserted = 0

            for i in range(0, len(pending_rows), batch_size):
                chunk = pending_rows[i : i + batch_size]
                encoded_rows, skipped_count = milvus_clip_service.encode_image_paths_batch(
                    chunk,
                    batch_size=clip_batch_size,
                )
                if encoded_rows:
                    inserted += milvus_clip_service.insert_vectors(encoded_rows, flush=False)
                processed += len(chunk)
                skipped += int(skipped_count)

                if inserted - last_flushed_inserted >= flush_every:
                    try:
                        milvus_clip_service.flush_collection(timeout=60.0)
                        last_flushed_inserted = inserted
                    except Exception:
                        pass

                elapsed = max(0.001, time.perf_counter() - started_ts)
                speed = processed / elapsed
                self._set_status(
                    processed=processed + (total - len(pending_rows)),
                    inserted=inserted,
                    skipped=skipped,
                    existing_vectors=milvus_clip_service.count_entities(),
                    dedup=dedup_summary,
                    message=f"indexing... {processed}/{len(pending_rows)} pending, {speed:.2f} img/s",
                )

            try:
                milvus_clip_service.flush_collection(timeout=180.0)
            except Exception:
                # Non-fatal: vectors are inserted even if flush/load times out.
                pass

            self._set_status(
                state="completed",
                message=f"index completed, inserted={inserted}, skipped={skipped}",
                inserted=inserted,
                skipped=skipped,
                processed=total,
                finished_at=datetime.utcnow().isoformat(),
                existing_vectors=milvus_clip_service.count_entities(),
                dedup=dedup_summary,
            )
        except Exception as exc:  # noqa: BLE001
            self._set_status(
                state="failed",
                message=f"{type(exc).__name__}: {exc}",
                finished_at=datetime.utcnow().isoformat(),
            )

    def _collect_image_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        seen: set[str] = set()
        for entity in self._data_service.export_entities():
            image_id = str(entity.get("image_id", "")).strip()
            if not image_id or image_id in seen:
                continue
            seen.add(image_id)
            meta = self._data_service.get_image_meta(image_id)
            if not meta:
                continue
            ref = str(meta.get("ref", "")).strip()
            if not ref or ref.lower().startswith(("http://", "https://")):
                continue
            path = Path(ref)
            if not path.is_file():
                continue
            rows.append((image_id, str(path)))
        return rows

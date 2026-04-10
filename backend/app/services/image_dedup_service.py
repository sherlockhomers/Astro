from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass
class ImageFingerprint:
    sha1: str
    dhash: str
    width: int
    height: int
    size: int
    mtime_ns: int


class ImageDedupService:
    def __init__(self) -> None:
        self._manifest_path = Path(str(getattr(settings, "milvus_dedup_manifest_path", "") or "")).resolve()
        self._manifest: dict[str, Any] | None = None

    def deduplicate_rows(self, rows: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], dict[str, Any]]:
        manifest = self._load_manifest()
        cached_rows = manifest.get("rows", {}) if isinstance(manifest, dict) else {}

        original_total = len(rows)
        scanned: list[dict[str, Any]] = []
        skipped_missing = 0

        for image_id, raw_path in rows:
            path = Path(raw_path)
            if not path.exists() or not path.is_file():
                skipped_missing += 1
                continue
            fp = self._get_fingerprint(path, cached_rows)
            if fp is None:
                skipped_missing += 1
                continue
            scanned.append(
                {
                    "image_id": str(image_id),
                    "path": str(path),
                    "path_obj": path,
                    "fingerprint": fp,
                    "score": self._row_quality_score(fp),
                    "stem_key": self._stem_key(path),
                    "parent_key": path.parent.name.lower(),
                }
            )

        exact_groups: dict[str, list[dict[str, Any]]] = {}
        for row in scanned:
            sha1 = row["fingerprint"].sha1
            exact_groups.setdefault(sha1, []).append(row)

        exact_kept: list[dict[str, Any]] = []
        exact_duplicate_count = 0
        exact_duplicate_ids: list[str] = []
        for group in exact_groups.values():
            group_sorted = sorted(group, key=lambda item: item["score"], reverse=True)
            exact_kept.append(group_sorted[0])
            if len(group_sorted) > 1:
                exact_duplicate_count += len(group_sorted) - 1
                exact_duplicate_ids.extend([str(item["image_id"]) for item in group_sorted[1:]])

        perceptual_kept: list[dict[str, Any]] = []
        perceptual_duplicate_count = 0
        perceptual_duplicate_ids: list[str] = []
        enable_perceptual = bool(getattr(settings, "milvus_dedup_enable_perceptual", True))
        hamming_threshold = max(0, int(getattr(settings, "milvus_dedup_hamming_threshold", 2) or 2))
        buckets: dict[str, list[dict[str, Any]]] = {}

        for row in sorted(exact_kept, key=lambda item: item["score"], reverse=True):
            fp = row["fingerprint"]
            bucket_key = fp.dhash[:6]
            bucket = buckets.setdefault(bucket_key, [])
            duplicate_found = False
            if enable_perceptual:
                for existing in bucket:
                    if row["stem_key"] != existing["stem_key"] and row["parent_key"] != existing["parent_key"]:
                        continue
                    distance = self._hamming_distance(fp.dhash, existing["fingerprint"].dhash)
                    if distance <= hamming_threshold:
                        duplicate_found = True
                        perceptual_duplicate_count += 1
                        perceptual_duplicate_ids.append(str(row["image_id"]))
                        break
            if duplicate_found:
                continue
            bucket.append(row)
            perceptual_kept.append(row)

        deduped_rows = [(str(row["image_id"]), str(row["path"])) for row in perceptual_kept]
        summary = {
            "original_total": original_total,
            "scanned_total": len(scanned),
            "kept_total": len(deduped_rows),
            "skipped_missing": skipped_missing,
            "exact_duplicates": exact_duplicate_count,
            "perceptual_duplicates": perceptual_duplicate_count,
            "duplicate_ids_sample": (exact_duplicate_ids + perceptual_duplicate_ids)[:20],
        }

        self._save_manifest(
            rows=scanned,
            summary=summary,
        )
        return deduped_rows, summary

    def _row_quality_score(self, fp: ImageFingerprint) -> tuple[int, int, int]:
        area = int(fp.width) * int(fp.height)
        return area, int(fp.size), max(int(fp.width), int(fp.height))

    def _stem_key(self, path: Path) -> str:
        raw = path.stem.lower()
        return "".join(ch for ch in raw if ch.isalpha())

    def _hamming_distance(self, left: str, right: str) -> int:
        if len(left) != len(right):
            return max(len(left), len(right))
        distance = 0
        for l_char, r_char in zip(left, right):
            xor_value = int(l_char, 16) ^ int(r_char, 16)
            distance += xor_value.bit_count()
        return distance

    def _get_fingerprint(self, path: Path, cached_rows: dict[str, Any]) -> ImageFingerprint | None:
        cache_key = str(path.resolve())
        stat = path.stat()
        size = int(stat.st_size)
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
        cached = cached_rows.get(cache_key)
        if (
            isinstance(cached, dict)
            and int(cached.get("size", -1)) == size
            and int(cached.get("mtime_ns", -1)) == mtime_ns
        ):
            try:
                return ImageFingerprint(
                    sha1=str(cached["sha1"]),
                    dhash=str(cached["dhash"]),
                    width=int(cached["width"]),
                    height=int(cached["height"]),
                    size=size,
                    mtime_ns=mtime_ns,
                )
            except Exception:
                pass

        try:
            from PIL import Image
        except Exception:
            return None

        try:
            data = path.read_bytes()
            sha1 = hashlib.sha1(data).hexdigest()
            with Image.open(path) as img:
                rgb = img.convert("L")
                width, height = img.size
                resized = rgb.resize((9, 8))
                pixels = list(resized.getdata())
            bits = []
            for row in range(8):
                offset = row * 9
                for col in range(8):
                    bits.append("1" if pixels[offset + col] > pixels[offset + col + 1] else "0")
            dhash = hex(int("".join(bits), 2))[2:].rjust(16, "0")
            return ImageFingerprint(
                sha1=sha1,
                dhash=dhash,
                width=int(width),
                height=int(height),
                size=size,
                mtime_ns=mtime_ns,
            )
        except Exception:
            return None

    def _load_manifest(self) -> dict[str, Any]:
        if self._manifest is not None:
            return self._manifest
        if not self._manifest_path.exists():
            self._manifest = {"version": 1, "rows": {}, "summary": {}}
            return self._manifest
        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("manifest must be a JSON object")
            payload.setdefault("rows", {})
            payload.setdefault("summary", {})
            self._manifest = payload
        except Exception:
            self._manifest = {"version": 1, "rows": {}, "summary": {}}
        return self._manifest

    def _save_manifest(self, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
        manifest_rows: dict[str, Any] = {}
        for row in rows:
            fp = row.get("fingerprint")
            path = str(row.get("path", ""))
            if not path or not isinstance(fp, ImageFingerprint):
                continue
            manifest_rows[path] = {
                "sha1": fp.sha1,
                "dhash": fp.dhash,
                "width": fp.width,
                "height": fp.height,
                "size": fp.size,
                "mtime_ns": fp.mtime_ns,
                "image_id": str(row.get("image_id", "")),
            }

        payload = {
            "version": 1,
            "summary": summary,
            "rows": manifest_rows,
        }
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._manifest = payload

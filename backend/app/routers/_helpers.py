"""Shared helpers for routers."""

from __future__ import annotations

from datetime import datetime
from html import escape
from urllib.parse import quote


def ensure_gallery_images(items: list[dict], query_text: str) -> list[dict]:
    normalized: list[dict] = []
    for idx, item in enumerate(items, start=1):
        payload = dict(item)
        if not payload.get("image_url"):
            title = payload.get("title") or query_text or "astro"
            payload["image_url"] = f"/api/v1/image/placeholder?text={quote(f'{title}-{idx}')}"
        normalized.append(payload)
    return normalized


def normalize_milvus_status(index_status: dict, milvus_connected: bool, indexed_vectors: int) -> dict:
    payload = dict(index_status or {})
    state = str(payload.get("state", "")).strip().lower()
    if milvus_connected and indexed_vectors > 0 and state in {"failed", "idle", "disabled"}:
        payload["state"] = "completed"
        payload["message"] = f"ready ({indexed_vectors} vectors)"
        payload["processed"] = max(int(payload.get("processed", 0) or 0), int(indexed_vectors))
        payload["existing_vectors"] = max(int(payload.get("existing_vectors", 0) or 0), int(indexed_vectors))
        if not payload.get("finished_at"):
            payload["finished_at"] = datetime.utcnow().isoformat()
    return payload


def image_placeholder_svg(text: str = "Astro") -> str:
    safe_text = escape(text)[:48]
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>"
        "<defs><linearGradient id='g' x1='0' x2='1' y1='0' y2='1'>"
        "<stop offset='0%' stop-color='#0d1628'/><stop offset='100%' stop-color='#1f365d'/>"
        "</linearGradient></defs>"
        "<rect width='640' height='360' fill='url(#g)'/>"
        "<circle cx='520' cy='70' r='28' fill='#d0a96c' opacity='0.35'/>"
        "<text x='32' y='200' fill='#e6edf7' font-size='34' font-family='Segoe UI, Arial, sans-serif'>"
        f"{safe_text}</text>"
        "<text x='32' y='238' fill='#9fb0c9' font-size='18' font-family='Segoe UI, Arial, sans-serif'>"
        "Astro Image Result</text>"
        "</svg>"
    )

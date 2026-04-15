from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.config import settings
from app.deps import ServiceContainer, get_services
from app.routers._helpers import ensure_gallery_images, normalize_milvus_status, image_placeholder_svg

router = APIRouter(prefix="/api/v1/image", tags=["image"])

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@router.post("/predict")
async def image_predict(file: UploadFile = File(...), svc: ServiceContainer = Depends(get_services)) -> dict:
    image_bytes = await file.read()
    return svc.image.predict(file.filename, image_bytes)


@router.post("/search-by-image")
async def image_search_by_image(
    file: UploadFile = File(...), page: int = 1, page_size: int = 12, top_k: int | None = None,
    svc: ServiceContainer = Depends(get_services),
) -> dict:
    image_bytes = await file.read()
    if top_k is not None and top_k > 0:
        page_size = min(int(top_k), 48)
        page = 1
    payload = svc.image.search_by_image_bytes(image_bytes, page=page, page_size=page_size)
    payload["items"] = ensure_gallery_images(payload.get("items", []), file.filename or "upload")
    return payload


@router.get("/search-by-text")
def image_search_by_text(
    query: str, page: int = 1, page_size: int = 12, top_k: int | None = None,
    svc: ServiceContainer = Depends(get_services),
) -> dict:
    if top_k is not None and top_k > 0:
        page_size = min(int(top_k), 48)
        page = 1
    payload = svc.image.search_by_text(query, page=page, page_size=page_size)
    payload["items"] = ensure_gallery_images(payload.get("items", []), query)
    return payload


@router.get("/vector-status")
def image_vector_status(svc: ServiceContainer = Depends(get_services)) -> dict:
    from app.services.milvus_clip_service import milvus_clip_service

    mcs = milvus_clip_service
    enabled = settings.milvus_enabled
    n, ok = 0, False
    if enabled:
        ok = mcs._ensure_milvus()
        n = mcs.count_entities() if ok else 0
    index_status = normalize_milvus_status(svc.milvus_index.status(), ok, n)
    return {
        "milvus_enabled": enabled, "milvus_connected": ok, "indexed_vectors": n,
        "collection": settings.milvus_collection, "last_error": mcs.last_error,
        "clip_ready": mcs.clip_model_loaded, "index_status": index_status,
    }


@router.get("/index-status")
def image_index_status(svc: ServiceContainer = Depends(get_services)) -> dict:
    status = svc.milvus_index.status()
    from app.services.milvus_clip_service import milvus_clip_service

    mcs = milvus_clip_service
    quick_connected, quick_vectors = False, 0
    if settings.milvus_enabled:
        quick_connected = mcs._ensure_milvus()
        quick_vectors = mcs.count_entities() if quick_connected else 0
    status["milvus_connected"] = quick_connected
    status["indexed_vectors"] = quick_vectors
    status["last_error"] = mcs.last_error
    return normalize_milvus_status(status, quick_connected, quick_vectors)


@router.post("/index-trigger")
def image_index_trigger(force: bool = False, svc: ServiceContainer = Depends(get_services)) -> dict:
    accepted, message = svc.milvus_index.start(force=force, csv_root=settings.csv_root)
    return {"accepted": accepted, "message": message, "status": svc.milvus_index.status()}


@router.get("/list")
def image_list(query: str = "", page: int = 1, page_size: int = 30, svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.data.list_images(query=query, page=page, page_size=page_size)


@router.get("/detail/{image_id}")
def image_detail(image_id: str, svc: ServiceContainer = Depends(get_services)) -> dict:
    item = svc.data.get_image_meta(image_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return item


@router.get("/file/{image_id}")
def image_file(image_id: str, svc: ServiceContainer = Depends(get_services)):
    item = svc.data.get_image_meta(image_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Image not found")
    image_ref = str(item.get("ref", "")).strip()
    if not image_ref:
        raise HTTPException(status_code=404, detail="Image reference is empty")
    if image_ref.lower().startswith(("http://", "https://")):
        return RedirectResponse(url=image_ref)
    file_path = Path(image_ref).resolve()
    allowed_roots = [Path(d).resolve() for d in settings.image_base_dirs.split(",") if d.strip()] if settings.image_base_dirs else []
    if allowed_roots and not any(str(file_path).startswith(str(root)) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Access to this path is not allowed")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    if file_path.suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    return FileResponse(file_path)


@router.get("/placeholder")
def image_placeholder(text: str = "Astro") -> Response:
    return Response(content=image_placeholder_svg(text), media_type="image/svg+xml")

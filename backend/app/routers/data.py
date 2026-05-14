from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import ServiceContainer, get_services, require_internal
from app.schemas import (
    DataLoadRequest, DataLoadResponse, DataScanRequest, DataScanResponse,
    SearchRequest, SearchResponse, TextIngestClearResponse, TextIngestRequest, TextIngestResponse,
    ExploreQueryRequest, ExploreBundleResponse,
)
from app.routers._helpers import ensure_gallery_images

router = APIRouter(prefix="/api/v1", tags=["data"])


# 数据源扫描/加载/语料导入这类接口允许用户提交任意服务器路径，
# 一旦裸奔就是任意路径读取 + 任意目录扫描，必须强制内部令牌。
@router.post("/data/scan", response_model=DataScanResponse, dependencies=[Depends(require_internal)])
def data_scan(payload: DataScanRequest, svc: ServiceContainer = Depends(get_services)) -> DataScanResponse:
    try:
        files = svc.data.scan_data_source(payload.csv_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DataScanResponse(files=files, total_files=len(files))


@router.post("/data/load", response_model=DataLoadResponse, dependencies=[Depends(require_internal)])
def data_load(payload: DataLoadRequest, svc: ServiceContainer = Depends(get_services)) -> DataLoadResponse:
    try:
        result = svc.data.load_data_source(payload.csv_root, payload.categories)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DataLoadResponse(**result)


@router.post("/data/ingest-text", response_model=TextIngestResponse, dependencies=[Depends(require_internal)])
def data_ingest_text(payload: TextIngestRequest, svc: ServiceContainer = Depends(get_services)) -> TextIngestResponse:
    try:
        result = svc.data.ingest_text_corpus(
            text_root=payload.text_root,
            category_prefix=payload.category_prefix,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TextIngestResponse(**result)


@router.post("/data/ingest-text/clear", response_model=TextIngestClearResponse, dependencies=[Depends(require_internal)])
def data_ingest_text_clear(svc: ServiceContainer = Depends(get_services)) -> TextIngestClearResponse:
    return TextIngestClearResponse(**svc.data.clear_text_corpus())


@router.get("/data/status")
def data_status(svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.data.get_status()


@router.post("/retrieval/search", response_model=SearchResponse)
def search(payload: SearchRequest, svc: ServiceContainer = Depends(get_services)) -> SearchResponse:
    items, note = svc.retrieval.hybrid_search(payload.query, payload.image_hint, payload.top_k)
    items = ensure_gallery_images(items, payload.query)
    return SearchResponse(items=items, note=note)


@router.get("/retrieval/vector-schema")
def retrieval_vector_schema(svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.retrieval.vector_schema()


@router.post("/explore/query", response_model=ExploreBundleResponse)
def explore_query(payload: ExploreQueryRequest, svc: ServiceContainer = Depends(get_services)) -> ExploreBundleResponse:
    bundle = svc.explore.query(payload.query, payload.image_hint)
    if bundle.get("related_images"):
        bundle["related_images"] = ensure_gallery_images(bundle["related_images"], payload.query)
    return ExploreBundleResponse(**bundle)

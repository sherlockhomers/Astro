from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from app.config import settings
from app.deps import ServiceContainer, get_services, require_internal

# 整组管理路由统一要求 X-Internal-Token，避免单个端点忘加导致裸奔
router = APIRouter(
    prefix="/api/v1",
    tags=["admin"],
    dependencies=[Depends(require_internal)],
)


@router.get("/metrics")
def metrics(
    svc: ServiceContainer = Depends(get_services),
) -> dict:
    return {"message": "metrics available via /metrics endpoint"}


@router.delete("/admin/cache/text")
def admin_clear_text_cache(svc: ServiceContainer = Depends(get_services)) -> dict:
    if hasattr(svc.retrieval, "_vector_service"):
        svc.retrieval._vector_service._index_revision = -1
    return {"ok": True, "message": "文本检索缓存已清除"}


@router.delete("/admin/cache/qa")
def admin_clear_qa_cache(svc: ServiceContainer = Depends(get_services)) -> dict:
    count = 0
    if hasattr(svc.qa, "_cache"):
        count = len(svc.qa._cache)
        svc.qa._cache.clear()
    return {"ok": True, "message": f"QA 缓存已清除，共清除 {count} 条"}


@router.delete("/admin/sessions/{session_id}")
def admin_delete_session(session_id: str, svc: ServiceContainer = Depends(get_services)) -> dict:
    success = svc.qa.delete_session(session_id)
    return {"ok": success, "message": "会话已删除" if success else "会话不存在"}


@router.post("/admin/sessions/{session_id}/reset")
def admin_reset_session(session_id: str, svc: ServiceContainer = Depends(get_services)) -> dict:
    ok = svc.qa.delete_session(session_id)
    if ok:
        svc.qa.create_session(session_id)
        return {"ok": True, "message": f"会话 {session_id} 已重置"}
    return {"ok": False, "message": "会话不存在"}


@router.get("/admin/stats")
def admin_stats(svc: ServiceContainer = Depends(get_services)) -> dict:
    data_status = svc.data.get_status()
    graph_status = svc.graph.status()
    vs_schema = svc.retrieval.vector_schema()
    qa_cache_size = len(svc.qa._cache) if hasattr(svc.qa, "_cache") else 0
    return {
        "app": settings.app_name, "env": settings.app_env,
        "data": {"entity_count": data_status.get("entity_count", 0), "image_count": data_status.get("image_count", 0), "loaded": data_status.get("loaded", False)},
        "graph": {"nodes": graph_status.get("nodes_count", 0), "relations": graph_status.get("relations_count", 0), "ready": graph_status.get("graph_ready", False)},
        "cache": {"qa_entries": qa_cache_size, "vector_cache_entries": vs_schema.get("cache_size", 0)},
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/admin/graph/rebuild")
def admin_rebuild_graph(svc: ServiceContainer = Depends(get_services)) -> dict:
    if not settings.csv_root:
        return {"ok": False, "message": "未配置 csv_root，请先设置数据源路径"}
    ok, message, task_id = svc.graph.build_graph(settings.csv_root, [], write_neo4j=False)
    return {"ok": ok, "message": message, "task_id": task_id}


@router.post("/admin/rules/reload")
def admin_reload_rules(svc: ServiceContainer = Depends(get_services)) -> dict:
    # 事实护栏规则和查询扩展规则都从文件读，运营改完文件调这里就生效，不用重启
    orchestrator = getattr(svc.qa, "_orchestrator", None)
    fact_info = orchestrator.reload_fact_rules() if orchestrator else {"count": 0, "sources": []}
    expansion_count = svc.retrieval.reload_expansion_rules() if hasattr(svc.retrieval, "reload_expansion_rules") else 0
    # 顺便把 QA 缓存清一下，不然老问题还会返老答案
    if hasattr(svc.qa, "_cache"):
        svc.qa._cache.clear()
    return {
        "ok": True,
        "fact_rules": fact_info,
        "query_expansions": expansion_count,
        "qa_cache_cleared": True,
    }

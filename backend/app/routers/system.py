from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.config import settings
from app.deps import ServiceContainer, get_services, require_internal
from app.routers._helpers import normalize_milvus_status
from app.schemas import (
    HealthResponse, ModelLoadRequest, ModelLoadResponse, ModelStatusResponse,
    SystemCapabilityReportResponse, SystemStatusResponse,
)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, env=settings.app_env)


@router.get("/health/ready")
def health_ready(svc: ServiceContainer = Depends(get_services)) -> dict:
    from app.services.sqlite_service import get_sqlite_connection

    checks: dict[str, Any] = {}
    all_healthy = True
    try:
        conn = get_sqlite_connection(settings.sqlite_path)
        conn.execute("SELECT 1").fetchone()
        checks["sqlite"] = {"status": "ok"}
    except Exception as exc:
        checks["sqlite"] = {"status": "error", "detail": str(exc)}
        all_healthy = False
    data_status = svc.data.get_status()
    checks["data"] = {"status": "ok" if data_status.get("loaded") else "not_loaded", "entity_count": data_status.get("entity_count", 0)}
    graph_status = svc.graph.status()
    checks["graph"] = {"status": "ok" if graph_status.get("graph_ready") else "not_ready", "nodes": graph_status.get("nodes_count", 0)}
    model_status = svc.model.get_status()
    checks["model"] = {"status": "ok" if model_status.get("loaded") else "not_loaded"}
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={"ready": all_healthy, "timestamp": datetime.utcnow().isoformat(), "app": settings.app_name, "env": settings.app_env, "checks": checks},
    )


@router.get("/health/live")
def health_live() -> dict:
    return {"alive": True, "timestamp": datetime.utcnow().isoformat()}


@router.get("/api/v1/model/status", response_model=ModelStatusResponse)
def model_status(svc: ServiceContainer = Depends(get_services)) -> ModelStatusResponse:
    return ModelStatusResponse(**svc.model.get_status())


@router.post("/api/v1/model/load", response_model=ModelLoadResponse)
def model_load(payload: ModelLoadRequest, svc: ServiceContainer = Depends(get_services)) -> ModelLoadResponse:
    ok, message = svc.model.load(payload.adapter_path, payload.class_name)
    status = ModelStatusResponse(**svc.model.get_status())
    return ModelLoadResponse(ok=ok, message=message, status=status)


@router.get("/api/v1/system/status", response_model=SystemStatusResponse)
def system_status(svc: ServiceContainer = Depends(get_services)) -> SystemStatusResponse:
    graph_status = svc.graph.status()
    data_status = svc.data.get_status()
    model_status_payload = svc.model.get_status()
    return SystemStatusResponse(
        model_ready=bool(model_status_payload["loaded"]),
        csv_ready=settings.csv_ready or data_status["loaded"],
        graph_ready=graph_status["graph_ready"],
        message=f"系统运行正常。 当前实体 {data_status['entity_count']} 个，关系 {graph_status['relations_count']} 条。",
    )


@router.get("/api/v1/system/capability-report", response_model=SystemCapabilityReportResponse)
def system_capability_report(
    _: None = Depends(require_internal),
    svc: ServiceContainer = Depends(get_services),
) -> SystemCapabilityReportResponse:
    return SystemCapabilityReportResponse(**_build_capability_report(svc))


def _build_capability_report(svc: ServiceContainer) -> dict:
    data_status = svc.data.get_status()
    graph_status = svc.graph.status()
    graph_schema = svc.graph.graph_schema_summary()
    model_status_payload = svc.model.get_status()
    milvus_raw = svc.milvus_index.status()
    indexed_vectors = int(milvus_raw.get("existing_vectors", 0) or 0)
    milvus_status = normalize_milvus_status(milvus_raw, bool(settings.milvus_enabled), indexed_vectors)
    qa_cache = svc.qa.get_cache_stats()

    entity_total = int(data_status.get("entity_count", 0) or 0)
    relation_total = int(graph_schema.get("relation_total", 0) or 0)
    category_total = int(data_status.get("category_count", 0) or 0)

    feature_flags = {
        "adaptive_rag_agent": True,
        "knowledge_graph": bool(graph_status.get("graph_ready")),
        "graph_rag": True,
        "dynamic_data": bool(settings.dynamic_enabled),
        "web_search": bool(settings.web_search_enabled),
        "mcp_tools": bool(settings.mcp_tools_enabled),
        "multimodal_model": bool(model_status_payload.get("supports_image_predict") or model_status_payload.get("supports_image_qa")),
        "image_vector_retrieval": bool(settings.milvus_enabled),
        "reflection_memory": bool(settings.agent_enable_reflection),
        "qa_cache": bool(qa_cache.get("enabled")),
    }

    strengths: list[str] = []
    risks: list[str] = []
    recommendations: list[str] = []

    if bool(model_status_payload.get("loaded")) and bool(model_status_payload.get("text_ready")):
        strengths.append("本地问答模型已就绪，主问答链路可离线运行。")
    else:
        risks.append("本地问答模型未完全就绪，核心体验会退化为检索或回退回答。")
        recommendations.append("优先确保主模型 text_ready=true，并做冷启动预热。")

    if entity_total >= 5000:
        strengths.append(f"本地知识库实体量达到 {entity_total}，基础科普覆盖面具备比赛展示价值。")
    else:
        risks.append(f"本地知识库实体量仅 {entity_total}，覆盖范围仍偏窄。")
        recommendations.append("继续扩充高质量天文语料，并对科普问答高频主题做专题聚合。")

    if not recommendations:
        recommendations.append("当前后端结构已具备比赛级原型基础，下一步重点应放在评测集与演示脚本固化。")

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "app": settings.app_name, "env": settings.app_env, "qa_mode": "adaptive_rag_agent",
            "entity_total": entity_total, "relation_total": relation_total,
            "category_total": category_total,
            "image_total": int(data_status.get("image_count", 0) or 0),
            "indexed_vectors": indexed_vectors,
        },
        "feature_flags": feature_flags,
        "components": {
            "model": model_status_payload, "data": data_status,
            "graph": graph_status, "graph_schema": graph_schema,
            "milvus": milvus_status, "qa_cache": qa_cache,
            "retrieval_schema": svc.retrieval.vector_schema(),
        },
        "strengths": strengths, "risks": risks, "recommendations": recommendations,
    }

from __future__ import annotations

from typing import Any

import json
import logging
import re
import signal
import time
import uuid
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from urllib.parse import quote

from fastapi import Cookie, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from app.config import settings
from app.metrics import register_metrics
from app.schemas import (
    AskRequest,
    AskResponse,
    AuthResponse,
    BuildGraphRequest,
    BuildGraphResponse,
    CypherQueryRequest,
    CypherQueryResponse,
    DataLoadRequest,
    DataLoadResponse,
    DataScanRequest,
    DataScanResponse,
    EvaluationReportResponse,
    EvaluationRunRequest,
    ExploreBundleResponse,
    ExploreQueryRequest,
    GraphExportCypherRequest,
    GraphExportCypherResponse,
    GraphMultiPathQueryResponse,
    GraphPathQueryResponse,
    GraphPathResponse,
    GraphRAGQueryRequest,
    GraphRAGQueryResponse,
    HealthResponse,
    LoginRequest,
    ModelLoadRequest,
    ModelLoadResponse,
    ModelStatusResponse,
    MutationStatusResponse,
    QADiagnosticsResponse,
    QAHistoryResponse,
    RegisterRequest,
    SearchRequest,
    SearchResponse,
    SystemCapabilityReportResponse,
    SystemStatusResponse,
    TextIngestClearResponse,
    TextIngestRequest,
    TextIngestResponse,
    UserFavoriteCreateRequest,
    UserOverviewResponse,
    UpdateProfileRequest,
    UserProfileResponse,
)
from app.services.data_service import DataService
from app.services.dynamic_data_service import DynamicDataService
from app.services.evaluation_service import EvaluationService
from app.services.explore_service import ExploreService
from app.services.graph_service import GraphService
from app.services.graphrag_service import GraphRAGService
from app.services.image_service import ImageService
from app.services.landing_content_service import LandingContentService
from app.services.mcp_tool_service import MCPToolService
from app.services.milvus_index_service import MilvusIndexService
from app.services.model3d_service import Model3DService
from app.services.model_service import ModelService
from app.services.qa_service import QAService
from app.services.retrieval_service import RetrievalService
from app.services.user_service import UserService
from app.services.web_search_service import WebSearchService

app = FastAPI(title=settings.app_name, version="0.1.0")
logger = logging.getLogger("astrograph")
# Prometheus /metrics endpoint + request latency histogram
register_metrics(app)
METRICS = {
    "requests_total": 0,
    "requests_by_path": defaultdict(int),
    "status_by_code": defaultdict(int),
    "latency_ms_sum_by_path": defaultdict(float),
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
RATE_LIMIT_RULES = {
    "/api/v1/qa/ask": (settings.qa_rate_limit_per_minute, 60.0),
    "/api/v1/qa/stream": (settings.qa_rate_limit_per_minute, 60.0),
    "/api/v1/qa/ask-with-image": (max(6, settings.qa_rate_limit_per_minute // 2), 60.0),
    "/api/v1/qa/stream-with-image": (max(6, settings.qa_rate_limit_per_minute // 2), 60.0),
    "/api/v1/auth/login": (10, 60.0),
    "/api/v1/auth/register": (6, 60.0),
    "/api/v1/auth/refresh": (20, 60.0),
}
RATE_LIMIT_STATE: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_LOCK = Lock()
# 每 N 次请求清理一次无用 key，防止 RATE_LIMIT_STATE 无限增长
_RATE_LIMIT_CLEANUP_INTERVAL = 100
_rate_limit_req_counter = 0

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

data_service = DataService()
retrieval_service = RetrievalService(data_service)
graph_service = GraphService(data_service)
model_service = ModelService()
image_service = ImageService(data_service, model_service)
landing_content_service = LandingContentService()
milvus_index_service = MilvusIndexService(data_service)
dynamic_data_service = DynamicDataService()
web_search_service = WebSearchService()
mcp_tool_service = MCPToolService(web_search_service)
qa_service = QAService(
    data_service,
    retrieval_service,
    graph_service,
    model_service,
    image_service=image_service,
    dynamic_service=dynamic_data_service,
    web_service=web_search_service,
    mcp_service=mcp_tool_service,
)
user_service = UserService()
graphrag_service = GraphRAGService(data_service, retrieval_service, graph_service)
model3d_service = Model3DService(data_service)
explore_service = ExploreService(
    data_service=data_service,
    retrieval_service=retrieval_service,
    graph_service=graph_service,
    model3d_service=model3d_service,
)
evaluation_service = EvaluationService(qa_service)


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    limited = _apply_rate_limit(request)
    if limited is not None:
        return limited
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    path = request.url.path
    METRICS["requests_total"] += 1
    METRICS["requests_by_path"][path] += 1
    METRICS["status_by_code"][str(response.status_code)] += 1
    METRICS["latency_ms_sum_by_path"][path] += elapsed_ms
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    response.headers["X-Request-ID"] = request_id
    return response


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _apply_rate_limit(request: Request) -> JSONResponse | None:
    rule = RATE_LIMIT_RULES.get(request.url.path)
    if rule is None:
        return None
    limit, window_seconds = rule
    now = time.time()
    key = f"{_client_ip(request)}|{request.url.path}"
    with RATE_LIMIT_LOCK:
        global _rate_limit_req_counter
        _rate_limit_req_counter += 1

        # 每隔 N 次请求，清理已过期的 key（避免无限增长）
        if _rate_limit_req_counter % _RATE_LIMIT_CLEANUP_INTERVAL == 0:
            expired_keys = [k for k, ts_list in RATE_LIMIT_STATE.items() if not ts_list or now - ts_list[-1] >= window_seconds]
            for k in expired_keys:
                RATE_LIMIT_STATE.pop(k, None)

        bucket = RATE_LIMIT_STATE[key]
        bucket[:] = [ts for ts in bucket if now - ts < window_seconds]
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试。"},
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
    return None


def _start_clip_warmup_background(delay_seconds: float = 0.0) -> None:
    def _worker() -> None:
        if delay_seconds > 0:
            time.sleep(max(0.0, float(delay_seconds)))
        try:
            from app.services.milvus_clip_service import milvus_clip_service

            result = milvus_clip_service.prewarm()
            logger.info("startup clip prewarm finished: %s", result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("startup clip prewarm failed: %s", exc)

    Thread(target=_worker, daemon=True, name="clip-prewarm").start()


@app.on_event("startup")
def _startup() -> None:
    logger.info("AstroGraph starting up — app=%s env=%s", settings.app_name, settings.app_env)

    # Register graceful shutdown
    def _shutdown_handler(signum, frame):
        logger.info("Received signal %d — initiating graceful shutdown", signum)
        # WAL checkpoint + close thread connections
        try:
            from app.services.sqlite_service import close_thread_connections
            close_thread_connections()
            logger.info("SQLite WAL connections closed successfully")
        except Exception as exc:
            logger.warning("Error during SQLite shutdown: %s", exc)
        import sys
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    # Best effort model load. Do not block startup on failure.
    model_service.load()
    if bool(getattr(settings, "astro_vision_warmup_on_startup", False)):
        try:
            accepted, message = model_service.warmup_vision_background(
                float(getattr(settings, "astro_vision_warmup_delay_seconds", 0.0) or 0.0)
            )
            logger.info("startup vision warmup: accepted=%s message=%s", accepted, message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("startup vision warmup trigger failed: %s", exc)

    # Best effort initial data loading/build.
    if settings.csv_root:
        try:
            if settings.auto_build_graph_on_startup:
                graph_service.build_graph(settings.csv_root, [], write_neo4j=False)
                logger.info("startup auto build graph success: %s", settings.csv_root)
            else:
                data_service.load_data_source(settings.csv_root, [])
                logger.info("startup auto load data source success: %s", settings.csv_root)
            if settings.text_corpus_auto_ingest_on_startup and settings.text_corpus_root:
                text_root = Path(settings.text_corpus_root)
                if text_root.exists():
                    ingest_result = data_service.ingest_text_corpus(str(text_root))
                    logger.info(
                        "startup text corpus ingest success: root=%s files=%s chunks=%s",
                        text_root,
                        ingest_result.get("files"),
                        ingest_result.get("chunks"),
                    )
                else:
                    logger.warning("startup text corpus ingest skipped: path not found %s", text_root)
            retrieval_service.hybrid_search("??", None, top_k=1)
            logger.info("startup retrieval index warmup success")
        except Exception as exc:  # noqa: BLE001
            logger.warning("startup auto load/build failed: %s", exc)

    if bool(getattr(settings, "clip_warmup_on_startup", False)):
        _start_clip_warmup_background(delay_seconds=2.0)

    # Milvus auto-index in background (non-blocking startup).
    if settings.milvus_enabled and bool(getattr(settings, "milvus_auto_index_on_startup", True)):
        try:
            accepted, msg = milvus_index_service.start(force=False, csv_root=settings.csv_root)
            logger.info("startup milvus auto-index: accepted=%s message=%s", accepted, msg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("startup milvus auto-index trigger failed: %s", exc)


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "bearer "
    lower = authorization.lower()
    if not lower.startswith(prefix):
        return None
    return authorization[len(prefix) :].strip()


def _require_user(authorization: str | None) -> dict:
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    user = user_service.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="??????????????")
    return user


def _client_context(request: Request) -> tuple[str, str]:
    user_agent = str(request.headers.get("user-agent", "") or "")
    ip_address = _client_ip(request)
    return user_agent, ip_address


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite=settings.auth_cookie_samesite,
        max_age=int(settings.auth_refresh_token_days) * 24 * 60 * 60,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        samesite=settings.auth_cookie_samesite,
    )


def _ensure_gallery_images(items: list[dict], query_text: str) -> list[dict]:
    normalized: list[dict] = []
    for idx, item in enumerate(items, start=1):
        payload = dict(item)
        if not payload.get("image_url"):
            title = payload.get("title") or query_text or "astro"
            payload["image_url"] = f"/api/v1/image/placeholder?text={quote(f'{title}-{idx}')}"
        normalized.append(payload)
    return normalized


def _normalize_milvus_status(index_status: dict, milvus_connected: bool, indexed_vectors: int) -> dict:
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


def _require_internal_access(internal_token: str | None) -> None:
    expected = str(getattr(settings, "auth_secret", "") or "").strip()
    if not expected or internal_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _answer_chunks(answer: str) -> list[str]:
    text = str(answer or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*|\n+", text) if part.strip()]
    if not parts:
        return [text]
    return [part if part.endswith(("。", "！", "？", ".", "!", "?", "；", ";")) else f"{part} " for part in parts]


def _public_citations(citations: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in citations:
        raw = str(item or "").strip()
        if not raw:
            continue
        if raw.startswith(("http://", "https://", "image:/")):
            candidate = raw
        elif "http://" in raw or "https://" in raw:
            idx_http = raw.find("http://")
            idx_https = raw.find("https://")
            candidates = [x for x in [idx_http, idx_https] if x >= 0]
            candidate = raw[min(candidates):] if candidates else ""
        else:
            continue
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def _derive_confidence(result: dict) -> str:
    reflection = result.get("trace", {}).get("reflection", {}) if isinstance(result, dict) else {}
    issues = reflection.get("issues", []) if isinstance(reflection, dict) else []
    count = len(issues) if isinstance(issues, list) else 0
    if count <= 1:
        return "high"
    if count <= 3:
        return "medium"
    return "low"


def _derive_image_confidence(result: dict) -> str:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    prediction = trace.get("prediction", {}) if isinstance(trace, dict) else {}
    focus_name = str(trace.get("focus_name", "") or "").strip().lower()
    image_result_count = int(trace.get("image_result_count", 0) or 0)
    score = prediction.get("confidence")
    try:
        confidence_score = float(score)
    except Exception:
        confidence_score = 0.0

    ambiguous_labels = {"unknown", "", "星座", "constellation", "galaxy", "星系"}
    if focus_name in ambiguous_labels:
        return "low" if image_result_count <= 0 else "medium"
    if confidence_score >= 0.72 and image_result_count >= 1:
        return "high"
    if confidence_score >= 0.58 or image_result_count >= 1:
        return "medium"
    return "low"


def _build_capability_report() -> dict:
    data_status = data_service.get_status()
    graph_status = graph_service.status()
    graph_schema = graph_service.graph_schema_summary()
    model_status_payload = model_service.get_status()
    milvus_raw = milvus_index_service.status()
    indexed_vectors = int(milvus_raw.get("existing_vectors", 0) or 0)
    milvus_status = _normalize_milvus_status(
        milvus_raw,
        bool(settings.milvus_enabled),
        indexed_vectors,
    )
    qa_cache = qa_service.get_cache_stats()

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

    entity_total = int(data_status.get("entity_count", 0) or 0)
    relation_total = int(graph_schema.get("relation_total", 0) or 0)
    category_total = int(data_status.get("category_count", 0) or 0)

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

    if relation_total >= 10000:
        strengths.append(f"知识图谱关系量达到 {relation_total}，关系探索模块已具备规模优势。")
    else:
        risks.append(f"知识图谱关系量为 {relation_total}，图谱规模和关系密度还有提升空间。")
        recommendations.append("优先补充可验证的实体关系三元组，并做关系类型归一化。")

    if bool(settings.milvus_enabled) and indexed_vectors >= 1000:
        strengths.append(f"图像向量检索已启用，当前可用向量 {indexed_vectors}，具备多模态检索亮点。")
    elif bool(settings.milvus_enabled):
        risks.append("Milvus 已启用，但当前已索引图像向量不足，图像检索优势还不稳定。")
        recommendations.append("完成全量图片向量化，并做启动时自动健康检查。")
    else:
        risks.append("图像向量检索未启用，多模态能力在答辩中会减分。")
        recommendations.append("为比赛演示环境固定开启 Milvus，并预建索引。")

    if bool(qa_cache.get("enabled")):
        strengths.append("问答结果缓存已启用，可降低重复问题时延并提升演示稳定性。")
    else:
        risks.append("问答没有缓存层，重复提问时延和 GPU 占用会更高。")

    if not bool(settings.agent_enable_llm_planner):
        risks.append("LLM 规划器当前关闭，策略路由主要依赖启发式规则。")
        recommendations.append("在模型稳定后，可逐步打开 LLM Planner 做 A/B 对比。")

    if not recommendations:
        recommendations.append("当前后端结构已具备比赛级原型基础，下一步重点应放在评测集与演示脚本固化。")

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "app": settings.app_name,
            "env": settings.app_env,
            "qa_mode": "adaptive_rag_agent",
            "entity_total": entity_total,
            "relation_total": relation_total,
            "category_total": category_total,
            "image_total": int(data_status.get("image_count", 0) or 0),
            "indexed_vectors": indexed_vectors,
        },
        "feature_flags": feature_flags,
        "components": {
            "model": model_status_payload,
            "data": data_status,
            "graph": graph_status,
            "graph_schema": graph_schema,
            "milvus": milvus_status,
            "qa_cache": qa_cache,
            "retrieval_schema": retrieval_service.vector_schema(),
        },
        "strengths": strengths,
        "risks": risks,
        "recommendations": recommendations,
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, env=settings.app_env)


@app.get("/health/ready")
def health_ready() -> dict:
    """
    Readiness probe for Kubernetes / load balancer.
    Checks all critical components and returns their status.
    """
    from app.services.sqlite_service import get_sqlite_connection

    checks: dict[str, Any] = {}
    all_healthy = True

    # 1. SQLite 可用性
    try:
        conn = get_sqlite_connection(settings.sqlite_path)
        conn.execute("SELECT 1").fetchone()
        checks["sqlite"] = {"status": "ok"}
    except Exception as exc:
        checks["sqlite"] = {"status": "error", "detail": str(exc)}
        all_healthy = False

    # 2. 数据加载状态
    data_status = data_service.get_status()
    checks["data"] = {
        "status": "ok" if data_status.get("loaded") else "not_loaded",
        "entity_count": data_status.get("entity_count", 0),
    }

    # 3. 图谱状态
    graph_status = graph_service.status()
    checks["graph"] = {
        "status": "ok" if graph_status.get("graph_ready") else "not_ready",
        "nodes": graph_status.get("nodes_count", 0),
    }

    # 4. 模型状态
    model_status = model_service.get_status()
    checks["model"] = {
        "status": "ok" if model_status.get("loaded") else "not_loaded",
    }

    status_code = 200 if all_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "ready": all_healthy,
            "timestamp": datetime.utcnow().isoformat(),
            "app": settings.app_name,
            "env": settings.app_env,
            "checks": checks,
        },
    )


@app.get("/health/live")
def health_live() -> JSONResponse:
    """
    Liveness probe — always returns 200 if the process is alive.
    Used by Kubernetes to know if the pod should be restarted.
    """
    return JSONResponse(content={"alive": True, "timestamp": datetime.utcnow().isoformat()})


@app.get("/api/v1/landing/apod")
def landing_apod() -> dict:
    """NASA 每日一图（经后端代理 JSON，前端用 img 展示，避免 iframe 被源站拒绝）。"""
    return landing_content_service.get_apod()


@app.get("/api/v1/landing/news")
def landing_news(limit: int = 6) -> dict:
    return {
        "items": landing_content_service.get_news(limit=limit),
        "updated_at": datetime.utcnow().isoformat(),
    }


@app.get("/api/v1/landing/science-cards")
def landing_science_cards(limit: int = 8) -> dict:
    return {"items": landing_content_service.get_science_cards(limit=limit)}


@app.get("/api/v1/landing/frontier")
def landing_frontier(per_topic: int = 15) -> dict:
    return landing_content_service.get_frontier(per_topic=per_topic)


@app.get("/api/v1/metrics")
def metrics(x_internal_token: str | None = Header(default=None)) -> dict:
    _require_internal_access(x_internal_token)
    avg_latency = {}
    for path, total_ms in METRICS["latency_ms_sum_by_path"].items():
        req = METRICS["requests_by_path"].get(path, 1)
        avg_latency[path] = round(float(total_ms) / max(int(req), 1), 2)
    return {
        "requests_total": METRICS["requests_total"],
        "requests_by_path": dict(METRICS["requests_by_path"]),
        "status_by_code": dict(METRICS["status_by_code"]),
        "avg_latency_ms_by_path": avg_latency,
    }


@app.get("/api/v1/model/status", response_model=ModelStatusResponse)
def model_status() -> ModelStatusResponse:
    return ModelStatusResponse(**model_service.get_status())


@app.post("/api/v1/model/load", response_model=ModelLoadResponse)
def model_load(payload: ModelLoadRequest) -> ModelLoadResponse:
    ok, message = model_service.load(payload.adapter_path, payload.class_name)
    status = ModelStatusResponse(**model_service.get_status())
    return ModelLoadResponse(ok=ok, message=message, status=status)


@app.post("/api/v1/auth/register", response_model=AuthResponse)
def auth_register(payload: RegisterRequest) -> AuthResponse:
    try:
        ok, message = user_service.register(payload.username, payload.password)
        return AuthResponse(ok=ok, message=message)
    except Exception as exc:  # noqa: BLE001
        logger.error("Register failed: %s", exc)
        return AuthResponse(ok=False, message="???????????")


@app.post("/api/v1/auth/login", response_model=AuthResponse)
def auth_login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
    try:
        user_agent, ip_address = _client_context(request)
        ok, message, user_id, username, access_token, refresh_token, expires_in = user_service.login(
            payload.username,
            payload.password,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        if ok and refresh_token:
            _set_refresh_cookie(response, refresh_token)
        return AuthResponse(
            ok=ok,
            message=message,
            token=access_token,
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
            user_id=user_id,
            username=username,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Login failed: %s", exc)
        _clear_refresh_cookie(response)
        return AuthResponse(ok=False, message="???????????")


@app.post("/api/v1/auth/refresh", response_model=AuthResponse)
def auth_refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> AuthResponse:
    try:
        user_agent, ip_address = _client_context(request)
        ok, message, payload = user_service.refresh_session(
            refresh_token or "",
            user_agent=user_agent,
            ip_address=ip_address,
        )
        if not ok or payload is None:
            _clear_refresh_cookie(response)
            return AuthResponse(ok=False, message=message)
        _set_refresh_cookie(response, payload["refresh_token"])
        return AuthResponse(
            ok=True,
            message=message,
            token=payload["access_token"],
            access_token=payload["access_token"],
            token_type="Bearer",
            expires_in=payload["expires_in"],
            user_id=payload["user_id"],
            username=payload["username"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Refresh failed: %s", exc)
        _clear_refresh_cookie(response)
        return AuthResponse(ok=False, message="?????????????")


@app.post("/api/v1/auth/logout")
def auth_logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> dict:
    try:
        if refresh_token:
            user_service.revoke_refresh_token(refresh_token)
    finally:
        _clear_refresh_cookie(response)
    return {"ok": True, "message": "????????"}


@app.get("/api/v1/auth/me", response_model=UserProfileResponse)
def auth_me(authorization: str | None = Header(default=None)) -> UserProfileResponse:
    user = _require_user(authorization)
    profile = user_service.get_profile(user["user_id"])
    return UserProfileResponse(
        ok=True,
        user_id=user["user_id"],
        username=user["username"],
        created_at=profile["created_at"] if profile else None,
    )


@app.patch("/api/v1/auth/profile", response_model=UserProfileResponse)
def auth_update_profile(
    payload: UpdateProfileRequest,
    authorization: str | None = Header(default=None),
) -> UserProfileResponse:
    user = _require_user(authorization)
    ok, message = user_service.update_username(user["user_id"], payload.username)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    profile = user_service.get_profile(user["user_id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfileResponse(
        ok=True,
        user_id=profile["user_id"],
        username=profile["username"],
        created_at=profile["created_at"],
    )


@app.get("/api/v1/system/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    graph_status = graph_service.status()
    data_status = data_service.get_status()
    model_status_payload = model_service.get_status()
    return SystemStatusResponse(
        model_ready=bool(model_status_payload["loaded"]),
        csv_ready=settings.csv_ready or data_status["loaded"],
        graph_ready=graph_status["graph_ready"],
        message=(
            "系统运行正常。"
            f" 当前实体 {data_status['entity_count']} 个，关系 {graph_status['relations_count']} 条。"
        ),
    )


@app.get("/api/v1/system/capability-report", response_model=SystemCapabilityReportResponse)
def system_capability_report(x_internal_token: str | None = Header(default=None)) -> SystemCapabilityReportResponse:
    _require_internal_access(x_internal_token)
    return SystemCapabilityReportResponse(**_build_capability_report())


@app.post("/api/v1/data/scan", response_model=DataScanResponse)
def data_scan(payload: DataScanRequest) -> DataScanResponse:
    try:
        files = data_service.scan_data_source(payload.csv_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DataScanResponse(files=files, total_files=len(files))


@app.post("/api/v1/data/load", response_model=DataLoadResponse)
def data_load(payload: DataLoadRequest) -> DataLoadResponse:
    try:
        result = data_service.load_data_source(payload.csv_root, payload.categories)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DataLoadResponse(**result)


@app.post("/api/v1/data/ingest-text", response_model=TextIngestResponse)
def data_ingest_text(payload: TextIngestRequest) -> TextIngestResponse:
    try:
        result = data_service.ingest_text_corpus(
            text_root=payload.text_root,
            category_prefix=payload.category_prefix,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TextIngestResponse(**result)


@app.post("/api/v1/data/ingest-text/clear", response_model=TextIngestClearResponse)
def data_ingest_text_clear() -> TextIngestClearResponse:
    result = data_service.clear_text_corpus()
    return TextIngestClearResponse(**result)


@app.get("/api/v1/data/status")
def data_status() -> dict:
    return data_service.get_status()


@app.post("/api/v1/qa/ask", response_model=AskResponse)
def ask_question(payload: AskRequest, authorization: str | None = Header(default=None)) -> AskResponse:
    sid = payload.session_id or uuid.uuid4().hex[:12]
    result = qa_service.ask_detailed(payload.question, sid)
    answer = str(result.get("answer", "")).strip()
    citations = [str(x) for x in result.get("citations", []) if str(x).strip()]
    graph_path = list(result.get("graph_path", []))
    mode = str(result.get("mode", "adaptive_rag_agent"))
    confidence = _derive_confidence(result)
    sid = str(result.get("session_id", sid))

    token = _extract_token(authorization)
    if token:
        user = user_service.get_user_by_token(token)
        if user:
            user_service.save_history(
                user_id=user["user_id"],
                session_id=sid,
                question=payload.question,
                answer=answer,
                citations_json=json.dumps(citations, ensure_ascii=False),
            )
    return AskResponse(
        answer=answer,
        citations=_public_citations(citations),
        graph_path=graph_path,
        mode=mode,
        confidence=confidence,
        session_id=sid,
    )


@app.post("/api/v1/qa/stream")
def ask_question_stream(payload: AskRequest, authorization: str | None = Header(default=None)):
    sid = payload.session_id or uuid.uuid4().hex[:12]
    token = _extract_token(authorization)
    user = user_service.get_user_by_token(token) if token else None

    def event_stream():
        stream_queue: Queue[dict | None] = Queue()
        result_box: dict[str, object] = {}

        def emit(stage: str, event_payload: dict | None = None) -> None:
            data = {"stage": stage}
            if isinstance(event_payload, dict):
                data.update(event_payload)
            stream_queue.put(data)

        def worker() -> None:
            try:
                result_box["result"] = qa_service.ask_detailed_with_timeout(
                    payload.question,
                    sid,
                    emit_stage=emit,
                    max_total_seconds=settings.qa_stream_total_timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                result_box["error"] = exc
            finally:
                stream_queue.put(None)

        thread = Thread(target=worker, daemon=True)
        thread.start()
        yield _sse_event("status", {"stage": "start", "message": "\u6b63\u5728\u5efa\u7acb\u56de\u7b54\u94fe\u8def\u3002"})
        sent_preview = ""

        while True:
            try:
                item = stream_queue.get(timeout=0.35)
            except Empty:
                if thread.is_alive():
                    yield ": ping\n\n"
                    continue
                item = None

            if item is None:
                break
            delta_text = str(item.get("delta", "") or "") if isinstance(item, dict) else ""
            if delta_text:
                sent_preview += delta_text
                yield _sse_event("delta", {"text": delta_text, "preview": True})
                item = {k: v for k, v in item.items() if k != "delta"}
            if item:
                yield _sse_event("status", item)

        thread.join()

        error = result_box.get("error")
        if error is not None:
            yield _sse_event(
                "error",
                {"message": "\u95ee\u7b54\u94fe\u8def\u6682\u65f6\u8d85\u65f6\uff0c\u7cfb\u7edf\u5df2\u56de\u9000\u5230\u5b89\u5168\u63d0\u793a\u3002", "detail": str(error)},
            )
            return

        result = dict(result_box.get("result") or {})
        answer = str(result.get("answer", "")).strip()
        citations = _public_citations([str(x) for x in result.get("citations", []) if str(x).strip()])
        graph_path = list(result.get("graph_path", []))
        mode = str(result.get("mode", "adaptive_rag_agent"))
        confidence = _derive_confidence(result)

        remaining_answer = answer
        if sent_preview and answer.startswith(sent_preview):
            remaining_answer = answer[len(sent_preview):].lstrip()

        for chunk in _answer_chunks(remaining_answer):
            yield _sse_event("delta", {"text": chunk})

        if user:
            user_service.save_history(
                user_id=user["user_id"],
                session_id=sid,
                question=payload.question,
                answer=answer,
                citations_json=json.dumps(citations, ensure_ascii=False),
            )

        yield _sse_event(
            "done",
            {
                "answer": answer,
                "citations": citations,
                "graph_path": graph_path,
                "mode": mode,
                "confidence": confidence,
                "session_id": sid,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/v1/qa/stream-with-image")
async def ask_question_stream_with_image(
    question: str = Form(...),
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
):
    image_bytes = await file.read()
    filename = file.filename or "upload.png"
    sid = session_id or uuid.uuid4().hex[:12]
    token = _extract_token(authorization)
    user = user_service.get_user_by_token(token) if token else None

    def event_stream():
        stream_queue: Queue[dict | None] = Queue()
        result_box: dict[str, object] = {}

        def worker() -> None:
            try:
                result_box["result"] = qa_service.ask_with_image_detailed_with_timeout(
                    question=question,
                    image_bytes=image_bytes,
                    filename=filename,
                    session_id=sid,
                    max_total_seconds=settings.qa_image_timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                result_box["error"] = exc
            finally:
                stream_queue.put(None)

        preview = None
        try:
            preview = qa_service.build_image_preview(question, image_bytes, filename)
        except Exception:
            preview = None

        thread = Thread(target=worker, daemon=True)
        thread.start()

        sent_preview = ""
        yield _sse_event("status", {"stage": "image_received", "message": "已接收图片，正在提取视觉特征。"})

        if preview:
            focus_name = str(preview.get("focus_name", "")).strip()
            if focus_name:
                yield _sse_event("status", {"stage": "vision_preview", "message": f"已完成初步识别，主体更接近{focus_name}。"})
            preview_text = str(preview.get("answer", "")).strip()
            if preview_text:
                sent_preview = preview_text
                yield _sse_event("delta", {"text": preview_text, "preview": True})
            yield _sse_event("status", {"stage": "retrieval", "message": "正在检索相似图像和知识片段。"})

        heartbeat = 0
        while True:
            try:
                item = stream_queue.get(timeout=0.45)
            except Empty:
                heartbeat += 1
                if thread.is_alive():
                    if heartbeat == 2:
                        yield _sse_event("status", {"stage": "reasoning", "message": "正在整合图片识别结果并生成科普说明。"})
                    yield ": ping\n\n"
                    continue
                item = None

            if item is None:
                break

        thread.join()
        error = result_box.get("error")
        if error is not None:
            yield _sse_event(
                "error",
                {"message": "图片问答暂时没有稳定完成。我先不输出不可靠结论。建议换一张主体更清晰的图片再试。", "detail": str(error)},
            )
            return

        result = dict(result_box.get("result") or {})
        answer = str(result.get("answer", "")).strip()
        citations = _public_citations([str(x) for x in result.get("citations", []) if str(x).strip()])
        graph_path = list(result.get("graph_path", []))
        mode = str(result.get("mode", "image_grounded_agent"))
        confidence = _derive_image_confidence(result)

        remaining_answer = answer
        if sent_preview and answer.startswith(sent_preview):
            remaining_answer = answer[len(sent_preview):].lstrip()
        for chunk in _answer_chunks(remaining_answer):
            yield _sse_event("delta", {"text": chunk})

        if user:
            user_service.save_history(
                user_id=user["user_id"],
                session_id=sid,
                question=question,
                answer=answer,
                citations_json=json.dumps(citations, ensure_ascii=False),
            )

        yield _sse_event(
            "done",
            {
                "answer": answer,
                "citations": citations,
                "graph_path": graph_path,
                "mode": mode,
                "confidence": confidence,
                "session_id": sid,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/v1/qa/diagnostics", response_model=QADiagnosticsResponse)
def ask_question_diagnostics(
    payload: AskRequest,
    x_internal_token: str | None = Header(default=None),
) -> QADiagnosticsResponse:
    _require_internal_access(x_internal_token)
    sid = payload.session_id or uuid.uuid4().hex[:12]
    result = qa_service.ask_detailed(payload.question, sid)
    result["confidence"] = _derive_confidence(result)
    return QADiagnosticsResponse(**result)


@app.get("/api/v1/eval/report", response_model=EvaluationReportResponse)
def eval_report(x_internal_token: str | None = Header(default=None)) -> EvaluationReportResponse:
    _require_internal_access(x_internal_token)
    return EvaluationReportResponse(**evaluation_service.latest_report())


@app.post("/api/v1/eval/run", response_model=EvaluationReportResponse)
def eval_run(
    payload: EvaluationRunRequest,
    x_internal_token: str | None = Header(default=None),
) -> EvaluationReportResponse:
    _require_internal_access(x_internal_token)
    report = evaluation_service.run(sample_size=payload.sample_size, use_cache=payload.use_cache)
    return EvaluationReportResponse(**report)


@app.post("/api/v1/qa/ask-with-image", response_model=AskResponse)
async def ask_with_image(
    question: str = Form(...),
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
) -> AskResponse:
    image_bytes = await file.read()
    filename = file.filename or "upload.png"
    sid = session_id or uuid.uuid4().hex[:12]

    try:
        result = qa_service.ask_with_image_detailed_with_timeout(
            question=question,
            image_bytes=image_bytes,
            filename=filename,
            session_id=sid,
            max_total_seconds=settings.qa_image_timeout_seconds,
        )
        answer = str(result.get("answer", "")).strip()
        citations = [str(x) for x in result.get("citations", []) if str(x).strip()]
        graph_path = list(result.get("graph_path", []))
        mode = str(result.get("mode", "image_grounded_agent"))
        confidence = _derive_image_confidence(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("image qa failed: %s", exc)
        answer = "这张图片的识别流程暂时没有稳定完成。我先不输出不可靠结论。建议换一张主体更清晰、对比度更高的图片再试。"
        citations = []
        graph_path = []
        mode = "image_grounded_agent"
        confidence = "low"

    token = _extract_token(authorization)
    if token:
        user = user_service.get_user_by_token(token)
        if user:
            user_service.save_history(
                user_id=user["user_id"],
                session_id=sid,
                question=question,
                answer=answer,
                citations_json=json.dumps(citations, ensure_ascii=False),
            )
    return AskResponse(
        answer=answer,
        citations=_public_citations(citations),
        graph_path=graph_path,
        mode=mode,
        confidence=confidence,
        session_id=sid,
    )

@app.post("/api/v1/graphrag/query", response_model=GraphRAGQueryResponse)
def graphrag_query(payload: GraphRAGQueryRequest) -> GraphRAGQueryResponse:
    result = graphrag_service.query(payload.question)
    return GraphRAGQueryResponse(**result)


@app.post("/api/v1/retrieval/search", response_model=SearchResponse)
def search(payload: SearchRequest) -> SearchResponse:
    items, note = retrieval_service.hybrid_search(payload.query, payload.image_hint, payload.top_k)
    items = _ensure_gallery_images(items, payload.query)
    return SearchResponse(items=items, note=note)


@app.post("/api/v1/explore/query", response_model=ExploreBundleResponse)
def explore_query(payload: ExploreQueryRequest) -> ExploreBundleResponse:
    bundle = explore_service.query(payload.query, payload.image_hint)
    if bundle.get("related_images"):
        bundle["related_images"] = _ensure_gallery_images(bundle["related_images"], payload.query)
    return ExploreBundleResponse(**bundle)


@app.get("/api/v1/retrieval/vector-schema")
def retrieval_vector_schema() -> dict:
    return retrieval_service.vector_schema()


@app.post("/api/v1/graph/build", response_model=BuildGraphResponse)
def build_graph(payload: BuildGraphRequest) -> BuildGraphResponse:
    try:
        accepted, message, task_id = graph_service.build_graph(
            payload.csv_root, payload.categories, payload.write_neo4j
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BuildGraphResponse(accepted=accepted, message=message, task_id=task_id)


@app.post("/api/v1/graph/export-cypher", response_model=GraphExportCypherResponse)
def graph_export_cypher(payload: GraphExportCypherRequest) -> GraphExportCypherResponse:
    ok, node_count, relation_count, message = graph_service.export_cypher(payload.output_path)
    return GraphExportCypherResponse(
        ok=ok,
        output_path=payload.output_path,
        node_count=node_count,
        relation_count=relation_count,
        message=message,
    )


@app.get("/api/v1/graph/status")
def graph_status() -> dict:
    return graph_service.status()


@app.get("/api/v1/graph/schema-summary")
def graph_schema_summary() -> dict:
    return graph_service.graph_schema_summary()


@app.get("/api/v1/graph/paths", response_model=GraphPathResponse)
def graph_paths(top_k: int = 20) -> GraphPathResponse:
    return GraphPathResponse(items=graph_service.preview_paths(top_k=top_k))


@app.get("/api/v1/graph/path", response_model=GraphPathQueryResponse)
def graph_path_between(source: str, target: str, max_hops: int = 4) -> GraphPathQueryResponse:
    path = graph_service.find_path(source, target, max_hops=max_hops)
    if not path:
        return GraphPathQueryResponse(found=False, path=[], message="Path not found")
    return GraphPathQueryResponse(found=True, path=path, message="ok")


@app.get("/api/v1/graph/multi-path", response_model=GraphMultiPathQueryResponse)
def graph_multi_path_between(
    source: str,
    target: str,
    max_hops: int = 4,
    max_paths: int = 6,
) -> GraphMultiPathQueryResponse:
    paths = graph_service.find_paths(source, target, max_hops=max_hops, max_paths=max_paths)
    if not paths:
        return GraphMultiPathQueryResponse(found=False, paths=[], message="Path not found")
    return GraphMultiPathQueryResponse(found=True, paths=paths, message="ok")


@app.post("/api/v1/graph/cypher", response_model=CypherQueryResponse)
def graph_cypher(payload: CypherQueryRequest) -> CypherQueryResponse:
    ok, records, message = graph_service.run_cypher(payload.query, payload.params)
    return CypherQueryResponse(ok=ok, records=records, message=message)


@app.get("/api/v1/visualization/graph")
def visualization_graph(max_nodes: int = 220, max_links: int = 900) -> dict:
    return graph_service.visualization_graph(max_nodes=max_nodes, max_links=max_links)


@app.get("/api/v1/visualization/subgraph")
def visualization_subgraph(
    query: str,
    max_nodes: int = 600,
    max_links: int = 4000,
    max_hops: int = 1,
    include_related: bool = False,
) -> dict:
    return graph_service.visualization_subgraph(
        query=query,
        max_nodes=max_nodes,
        max_links=max_links,
        max_hops=max_hops,
        include_related=include_related,
    )


@app.get("/api/v1/visualization/compare")
def visualization_compare(name_a: str, name_b: str) -> dict:
    return graph_service.compare_entities(name_a, name_b)


@app.get("/api/v1/visualization/timeline")
def visualization_timeline(limit: int = 200) -> dict:
    return {"items": graph_service.timeline(limit=limit)}


@app.get("/api/v1/visualization/starfield")
def visualization_starfield(limit: int = 800) -> dict:
    return {"items": graph_service.starfield_points(limit=limit)}


@app.get("/api/v1/visualization/model3d")
def visualization_model3d(query: str) -> dict:
    return model3d_service.search(query)


@app.get("/api/v1/user/history", response_model=QAHistoryResponse)
def user_history(
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(default=None),
) -> QAHistoryResponse:
    user = _require_user(authorization)
    history = user_service.list_history(user["user_id"], limit=limit, offset=offset)
    items = []
    for row in history["items"]:
        citations = []
        try:
            citations = json.loads(row.get("citations_json", "[]"))
        except json.JSONDecodeError:
            citations = []
        items.append(
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "question": row["question"],
                "answer": row["answer"],
                "citations": citations,
                "created_at": row["created_at"],
            }
        )
    return QAHistoryResponse(
        items=items,
        limit=int(history["limit"]),
        offset=int(history["offset"]),
        total=int(history["total"]),
        has_more=bool(history["has_more"]),
    )


@app.get("/api/v1/user/overview", response_model=UserOverviewResponse)
def user_overview(authorization: str | None = Header(default=None)) -> UserOverviewResponse:
    user = _require_user(authorization)
    overview = user_service.build_overview(user["user_id"])
    return UserOverviewResponse(**overview)


@app.post("/api/v1/user/favorites", response_model=MutationStatusResponse)
def user_favorite_create(
    payload: UserFavoriteCreateRequest,
    authorization: str | None = Header(default=None),
) -> MutationStatusResponse:
    user = _require_user(authorization)
    ok, message, row_id = user_service.save_favorite(
        user_id=user["user_id"],
        title=payload.title,
        category=payload.category,
        image_url=payload.image_url,
        source_query=payload.source_query,
    )
    return MutationStatusResponse(ok=ok, message=message, id=row_id)


@app.delete("/api/v1/user/favorites/{favorite_id}", response_model=MutationStatusResponse)
def user_favorite_delete(
    favorite_id: int,
    authorization: str | None = Header(default=None),
) -> MutationStatusResponse:
    user = _require_user(authorization)
    ok, message = user_service.delete_favorite(user["user_id"], favorite_id)
    return MutationStatusResponse(ok=ok, message=message, id=favorite_id if ok else None)


@app.delete("/api/v1/user/history/{history_id}", response_model=MutationStatusResponse)
def user_history_delete(
    history_id: int,
    authorization: str | None = Header(default=None),
) -> MutationStatusResponse:
    user = _require_user(authorization)
    ok, message = user_service.delete_history(user["user_id"], history_id)
    return MutationStatusResponse(ok=ok, message=message, id=history_id if ok else None)


@app.post("/api/v1/image/predict")
async def image_predict(file: UploadFile = File(...)) -> dict:
    image_bytes = await file.read()
    return image_service.predict(file.filename, image_bytes)


@app.post("/api/v1/image/search-by-image")
async def image_search_by_image(
    file: UploadFile = File(...),
    page: int = 1,
    page_size: int = 12,
    top_k: int | None = None,
) -> dict:
    image_bytes = await file.read()
    if top_k is not None and top_k > 0:
        page_size = min(int(top_k), 48)
        page = 1
    payload = image_service.search_by_image_bytes(image_bytes, page=page, page_size=page_size)
    payload["items"] = _ensure_gallery_images(payload.get("items", []), file.filename or "upload")
    return payload


@app.get("/api/v1/image/search-by-text")
def image_search_by_text(
    query: str,
    page: int = 1,
    page_size: int = 12,
    top_k: int | None = None,
) -> dict:
    if top_k is not None and top_k > 0:
        page_size = min(int(top_k), 48)
        page = 1
    payload = image_service.search_by_text(query, page=page, page_size=page_size)
    payload["items"] = _ensure_gallery_images(payload.get("items", []), query)
    return payload


@app.get("/api/v1/image/vector-status")
def image_vector_status() -> dict:
    from app.services.milvus_clip_service import milvus_clip_service

    mcs = milvus_clip_service
    enabled = settings.milvus_enabled
    n = 0
    ok = False
    if enabled:
        ok = mcs._ensure_milvus()
        n = mcs.count_entities() if ok else 0
    index_status = milvus_index_service.status()
    index_status = _normalize_milvus_status(index_status, ok, n)
    return {
        "milvus_enabled": enabled,
        "milvus_connected": ok,
        "indexed_vectors": n,
        "collection": settings.milvus_collection,
        "last_error": mcs.last_error,
        "clip_ready": mcs.clip_model_loaded,
        "index_status": index_status,
    }


@app.get("/api/v1/image/index-status")
def image_index_status() -> dict:
    status = milvus_index_service.status()
    from app.services.milvus_clip_service import milvus_clip_service

    mcs = milvus_clip_service
    quick_connected = False
    quick_vectors = 0
    if settings.milvus_enabled:
        quick_connected = mcs._ensure_milvus()
        quick_vectors = mcs.count_entities() if quick_connected else 0
    status["milvus_connected"] = quick_connected
    status["indexed_vectors"] = quick_vectors
    status["last_error"] = mcs.last_error
    return _normalize_milvus_status(status, quick_connected, quick_vectors)


@app.post("/api/v1/image/index-trigger")
def image_index_trigger(force: bool = False) -> dict:
    accepted, message = milvus_index_service.start(force=force, csv_root=settings.csv_root)
    return {
        "accepted": accepted,
        "message": message,
        "status": milvus_index_service.status(),
    }


@app.get("/api/v1/image/list")
def image_list(query: str = "", page: int = 1, page_size: int = 30) -> dict:
    return data_service.list_images(query=query, page=page, page_size=page_size)


@app.get("/api/v1/image/detail/{image_id}")
def image_detail(image_id: str) -> dict:
    item = data_service.get_image_meta(image_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return item


@app.get("/api/v1/image/file/{image_id}")
def image_file(image_id: str):
    item = data_service.get_image_meta(image_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Image not found")
    image_ref = str(item.get("ref", "")).strip()
    if not image_ref:
        raise HTTPException(status_code=404, detail="Image reference is empty")
    if image_ref.lower().startswith(("http://", "https://")):
        return RedirectResponse(url=image_ref)
    file_path = Path(image_ref)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    if file_path.suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    return FileResponse(file_path)


@app.get("/api/v1/image/placeholder")
def image_placeholder(text: str = "Astro") -> Response:
    safe_text = escape(text)[:48]
    svg = (
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
    return Response(content=svg, media_type="image/svg+xml")


# ─── Admin Management APIs ─────────────────────────────────────────────────────


@app.delete("/api/v1/admin/cache/text")
def admin_clear_text_cache() -> dict:
    """
    清除文本检索缓存，强制重新构建索引。
    """
    if hasattr(retrieval_service, "_vector_service"):
        retrieval_service._vector_service._index_revision = -1
    return {"ok": True, "message": "文本检索缓存已清除"}


@app.delete("/api/v1/admin/cache/qa")
def admin_clear_qa_cache() -> dict:
    """
    清除 QA 问答缓存。
    """
    count = 0
    if hasattr(qa_service, "_cache"):
        count = len(qa_service._cache)
        qa_service._cache.clear()
    return {"ok": True, "message": f"QA 缓存已清除，共清除 {count} 条"}


@app.delete("/api/v1/admin/sessions/{session_id}")
def admin_delete_session(session_id: str) -> dict:
    """
    删除指定 QA 会话及其历史记录。
    """
    success = qa_service.delete_session(session_id)
    return {"ok": success, "message": "会话已删除" if success else "会话不存在"}


@app.post("/api/v1/admin/sessions/{session_id}/reset")
def admin_reset_session(session_id: str) -> dict:
    """
    重置指定会话，清空所有历史记录。
    """
    ok = qa_service.delete_session(session_id)
    if ok:
        qa_service.create_session(session_id)
        return {"ok": True, "message": f"会话 {session_id} 已重置"}
    return {"ok": False, "message": "会话不存在"}


@app.get("/api/v1/admin/stats")
def admin_stats() -> dict:
    """
    返回系统运行统计信息：实体数、图谱节点数、缓存大小等。
    """
    data_status = data_service.get_status()
    graph_status = graph_service.status()
    vs_schema = retrieval_service.vector_schema()

    qa_cache_size = 0
    if hasattr(qa_service, "_cache"):
        qa_cache_size = len(qa_service._cache)

    return {
        "app": settings.app_name,
        "env": settings.app_env,
        "data": {
            "entity_count": data_status.get("entity_count", 0),
            "image_count": data_status.get("image_count", 0),
            "loaded": data_status.get("loaded", False),
        },
        "graph": {
            "nodes": graph_status.get("nodes_count", 0),
            "relations": graph_status.get("relations_count", 0),
            "ready": graph_status.get("graph_ready", False),
        },
        "cache": {
            "qa_entries": qa_cache_size,
            "vector_cache_entries": vs_schema.get("cache_size", 0),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/v1/admin/graph/rebuild")
def admin_rebuild_graph() -> dict:
    """
    手动触发图谱重建。
    """
    if not settings.csv_root:
        return {"ok": False, "message": "未配置 csv_root，请先设置数据源路径"}
    ok, message, task_id = graph_service.build_graph(settings.csv_root, [], write_neo4j=False)
    return {"ok": ok, "message": message, "task_id": task_id}

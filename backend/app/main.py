"""AstroGraph API — main application entry point.

All routes are organized in app.routers.* modules.
Service initialization is managed via app.deps.lifespan.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.deps import lifespan
from app.metrics import register_metrics

from app.routers import (
    admin,
    astro_tools,
    auth,
    data,
    graph,
    image,
    landing,
    qa,
    system,
    user,
    visualization,
)

app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
logger = logging.getLogger("astrograph")

register_metrics(app)

# ─── Rate Limiting ──────────────────────────────────────────────────────────────

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
_RATE_LIMIT_CLEANUP_INTERVAL = 100
_rate_limit_req_counter = 0

# ─── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Middleware ──────────────────────────────────────────────────────────────────

METRICS = {
    "requests_total": 0,
    "requests_by_path": defaultdict(int),
    "status_by_code": defaultdict(int),
    "latency_ms_sum_by_path": defaultdict(float),
}


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


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
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


# ─── Register Routers ───────────────────────────────────────────────────────────

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(qa.router)
app.include_router(data.router)
app.include_router(graph.router)
app.include_router(visualization.router)
app.include_router(image.router)
app.include_router(user.router)
app.include_router(landing.router)
app.include_router(admin.router)
app.include_router(astro_tools.router)

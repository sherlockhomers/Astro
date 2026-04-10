"""Prometheus metrics middleware and instrumentation for AstroGraph backend."""
from __future__ import annotations

import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

if _PROMETHEUS_AVAILABLE:
    # ── Request counters ──────────────────────────────────────────────────────
    http_requests_total = Counter(
        "astrograph_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code"],
    )

    http_request_duration_seconds = Histogram(
        "astrograph_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    # ── Business metrics ───────────────────────────────────────────────────────
    qa_answers_total = Counter(
        "astrograph_qa_answers_total",
        "Total Q&A answers generated",
        ["answer_source"],
    )

    qa_answers_with_graph_path = Counter(
        "astrograph_qa_graph_path_total",
        "Q&A answers that included a graph path",
    )

    retrieval_items_retrieved = Counter(
        "astrograph_retrieval_items_total",
        "Total retrieval items fetched",
        ["source"],
    )

    cache_hits_total = Counter(
        "astrograph_cache_hits_total",
        "Total cache hits",
        ["cache_name"],
    )

    cache_misses_total = Counter(
        "astrograph_cache_misses_total",
        "Total cache misses",
        ["cache_name"],
    )

    # ── Gauge metrics ─────────────────────────────────────────────────────────
    entities_loaded_gauge = Gauge(
        "astrograph_entities_loaded",
        "Number of entities currently loaded in memory",
    )

    graph_nodes_gauge = Gauge(
        "astrograph_graph_nodes",
        "Number of graph nodes",
    )

    graph_relations_gauge = Gauge(
        "astrograph_graph_relations",
        "Number of graph relations",
    )

    _AVAILABLE = True
else:
    # No-op stubs when prometheus_client is not installed
    _AVAILABLE = False
    http_requests_total = http_request_duration_seconds = None  # type: ignore[assignment]
    qa_answers_total = qa_answers_with_graph_path = None
    retrieval_items_retrieved = None
    cache_hits_total = cache_misses_total = None
    entities_loaded_gauge = graph_nodes_gauge = graph_relations_gauge = None


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record request latency + count per method/endpoint/status for Prometheus scraping."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _AVAILABLE:
            return await call_next(request)

        # Skip the /metrics endpoint itself to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = _normalize_path(request)
        start = time.perf_counter()

        response = await call_next(request)
        duration = time.perf_counter() - start

        status_code = str(response.status_code)
        http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

        return response


def _normalize_path(request: Request) -> str:
    """Collapse path parameters so /graph/path/earth/mars → /graph/path/{src}/{tgt}."""
    route = request.scope.get("route")
    if route is not None:
        # Use the route's path pattern (e.g. "/graph/path/{source}/{target}")
        return getattr(route, "path", request.url.path)
    # Fallback: redact numeric path segments
    import re
    return re.sub(r"/[a-f0-9]{8,}", "/{id}", request.url.path)


def register_metrics(app: FastAPI) -> None:
    """Add Prometheus middleware and /metrics endpoint to a FastAPI app."""
    if not _AVAILABLE:
        return

    app.add_middleware(PrometheusMiddleware)

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_qa_answer(source: str, has_graph_path: bool) -> None:
    if not _AVAILABLE:
        return
    qa_answers_total.labels(answer_source=source).inc()
    if has_graph_path:
        qa_answers_with_graph_path.inc()


def record_retrieval_items(source: str, count: int) -> None:
    if not _AVAILABLE:
        return
    retrieval_items_retrieved.labels(source=source).inc(count)


def record_cache_hit(cache_name: str) -> None:
    if not _AVAILABLE:
        return
    cache_hits_total.labels(cache_name=cache_name).inc()


def record_cache_miss(cache_name: str) -> None:
    if not _AVAILABLE:
        return
    cache_misses_total.labels(cache_name=cache_name).inc()


def update_gauges(entity_count: int, graph_nodes: int, graph_relations: int) -> None:
    if not _AVAILABLE:
        return
    entities_loaded_gauge.set(entity_count)
    graph_nodes_gauge.set(graph_nodes)
    graph_relations_gauge.set(graph_relations)

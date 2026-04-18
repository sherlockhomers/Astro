"""Dependency injection & service container for AstroGraph.

All service singletons live here. They are initialized once during app lifespan
and injected into route handlers via FastAPI's Depends().
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from app.config import settings

logger = logging.getLogger("astrograph")


class ServiceContainer:
    """Holds all service singletons. Created once during startup."""

    def __init__(self) -> None:
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
        from app.services.space_events_service import SpaceEventsService
        from app.services.user_service import UserService
        from app.services.web_search_service import WebSearchService

        from app.services.cloud_llm_service import CloudLLMService

        self.cloud_llm = CloudLLMService()
        self.data = DataService()
        self.space_events = SpaceEventsService()
        self.retrieval = RetrievalService(self.data)
        self.graph = GraphService(self.data)
        self.model = ModelService()
        self.image = ImageService(self.data, self.model)
        self.landing = LandingContentService()
        self.milvus_index = MilvusIndexService(self.data)
        self.dynamic = DynamicDataService()
        self.web_search = WebSearchService()
        self.mcp_tool = MCPToolService(self.web_search)
        self.qa = QAService(
            self.data,
            self.retrieval,
            self.graph,
            self.model,
            image_service=self.image,
            dynamic_service=self.dynamic,
            web_service=self.web_search,
            mcp_service=self.mcp_tool,
        )
        self.user = UserService()
        self.graphrag = GraphRAGService(self.data, self.retrieval, self.graph)
        self.model3d = Model3DService(self.data)
        self.explore = ExploreService(
            data_service=self.data,
            retrieval_service=self.retrieval,
            graph_service=self.graph,
            model3d_service=self.model3d,
        )
        self.evaluation = EvaluationService(self.qa)


_container: ServiceContainer | None = None


def _start_clip_warmup_background(delay_seconds: float = 0.0) -> None:
    def _worker() -> None:
        if delay_seconds > 0:
            time.sleep(max(0.0, float(delay_seconds)))
        try:
            from app.services.milvus_clip_service import milvus_clip_service

            result = milvus_clip_service.prewarm()
            logger.info("startup clip prewarm finished: %s", result)
        except Exception as exc:
            logger.warning("startup clip prewarm failed: %s", exc)

    Thread(target=_worker, daemon=True, name="clip-prewarm").start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize services on startup, cleanup on shutdown."""
    global _container
    logger.info("AstroGraph starting up — app=%s env=%s", settings.app_name, settings.app_env)

    _container = ServiceContainer()
    app.state.services = _container

    _container.model.load()
    if bool(getattr(settings, "astro_vision_warmup_on_startup", False)):
        try:
            accepted, message = _container.model.warmup_vision_background(
                float(getattr(settings, "astro_vision_warmup_delay_seconds", 0.0) or 0.0)
            )
            logger.info("startup vision warmup: accepted=%s message=%s", accepted, message)
        except Exception as exc:
            logger.warning("startup vision warmup trigger failed: %s", exc)

    if settings.csv_root:
        try:
            if settings.auto_build_graph_on_startup:
                _container.graph.build_graph(settings.csv_root, [], write_neo4j=False)
                logger.info("startup auto build graph success: %s", settings.csv_root)
            else:
                _container.data.load_data_source(settings.csv_root, [])
                logger.info("startup auto load data source success: %s", settings.csv_root)
            if settings.text_corpus_auto_ingest_on_startup and settings.text_corpus_root:
                text_root = Path(settings.text_corpus_root)
                if text_root.exists():
                    ingest_result = _container.data.ingest_text_corpus(str(text_root))
                    logger.info(
                        "startup text corpus ingest success: root=%s files=%s chunks=%s",
                        text_root,
                        ingest_result.get("files"),
                        ingest_result.get("chunks"),
                    )
                else:
                    logger.warning("startup text corpus ingest skipped: path not found %s", text_root)
            _container.retrieval.hybrid_search("??", None, top_k=1)
            logger.info("startup retrieval index warmup success")
        except Exception as exc:
            logger.warning("startup auto load/build failed: %s", exc)

    if bool(getattr(settings, "clip_warmup_on_startup", False)):
        _start_clip_warmup_background(delay_seconds=2.0)

    if settings.milvus_enabled and bool(getattr(settings, "milvus_auto_index_on_startup", True)):
        try:
            accepted, msg = _container.milvus_index.start(force=False, csv_root=settings.csv_root)
            logger.info("startup milvus auto-index: accepted=%s message=%s", accepted, msg)
        except Exception as exc:
            logger.warning("startup milvus auto-index trigger failed: %s", exc)

    yield

    logger.info("AstroGraph shutting down")
    try:
        from app.services.sqlite_service import close_thread_connections
        close_thread_connections()
        logger.info("SQLite WAL connections closed successfully")
    except Exception as exc:
        logger.warning("Error during SQLite shutdown: %s", exc)


def get_services(request: Request) -> ServiceContainer:
    return request.app.state.services


def extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "bearer "
    lower = authorization.lower()
    if not lower.startswith(prefix):
        return None
    return authorization[len(prefix):].strip()


def require_user(
    authorization: str | None = Header(default=None),
    svc: ServiceContainer = Depends(get_services),
) -> dict:
    token = extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    user = svc.user.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Token 已失效，请重新登录")
    return user


def optional_user(
    authorization: str | None = Header(default=None),
    svc: ServiceContainer = Depends(get_services),
) -> dict | None:
    token = extract_token(authorization)
    if not token:
        return None
    return svc.user.get_user_by_token(token)


def require_internal(x_internal_token: str | None = Header(default=None)) -> None:
    admin_tok = str(getattr(settings, "admin_token", "") or "").strip()
    expected = admin_tok or str(getattr(settings, "auth_secret", "") or "").strip()
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def client_context(request: Request) -> tuple[str, str]:
    user_agent = str(request.headers.get("user-agent", "") or "")
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    ip_address = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return user_agent, ip_address

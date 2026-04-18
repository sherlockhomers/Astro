"""Pytest configuration and shared fixtures for AstroGraph backend."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# ─── Disable real network/HTTP calls in tests by default ──────────────────────
os.environ.setdefault("NEO4J_ENABLED", "false")
os.environ.setdefault("MILVUS_ENABLED", "false")
os.environ.setdefault("STARWHISPER_ENABLED", "false")
os.environ.setdefault("MINIO_ENABLED", "false")
os.environ.setdefault("WEB_SEARCH_ENABLED", "false")
os.environ.setdefault("MCP_TOOLS_ENABLED", "false")


@pytest.fixture(scope="session")
def tmp_db_path() -> Generator[str, None, None]:
    """Provide a temporary SQLite database path that is cleaned up after the session."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture(scope="session")
def tmp_csv_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Provide a session-scoped temporary directory simulating a CSV data root."""
    csv_root = tmp_path_factory.mktemp("astro_csv_root") / "csv"
    csv_root.mkdir()
    return csv_root


@pytest.fixture
def sample_csv_file(tmp_csv_root: Path) -> Path:
    """Write a minimal CSV and return its path."""
    content = (
        "id,name,category,description,host_star,distance_ly,orbital_period_days\n"
        "1,Kepler-186f,Exoplanet,Kepler-186f is an Earth-size exoplanet,Kepler-186,500,130\n"
        "2,Proxima Centauri b,Exoplanet,A planet in the habitable zone of Proxima Centauri,Proxima Centauri,4.2,11.2\n"
        "3,TRAPPIST-1e,Exoplanet,One of the seven Earth-size planets in TRAPPIST-1,TRAPPIST-1,39.5,6.1\n"
    )
    path = tmp_csv_root / "test_entities.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def data_service_factory(tmp_db_path: str, tmp_csv_root: Path):
    """Factory that creates a fresh DataService instance for each call."""
    from app.services.data_service import DataService

    created: list[DataService] = []

    def _make() -> DataService:
        svc = DataService.__new__(DataService)
        # Re-initialise only the parts that touch the filesystem
        import sqlite3
        from app.services import sqlite_service as sqlite_svc
        svc._db_path = tmp_db_path
        svc._csv_root = str(tmp_csv_root)
        svc._entities: list[dict] = []
        svc._images: dict = {}
        svc._extra_entities: list[dict] = []
        svc._loaded = False
        svc._revision = 0

        # Minimal connect that uses the test DB
        def _connect():
            conn = sqlite3.connect(tmp_db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        svc._connect = _connect
        created.append(svc)
        return svc

    yield _make
    for svc in created:
        try:
            svc._loaded = False
        except Exception:
            pass


@pytest.fixture
def retrieval_service_factory(data_service_factory):
    """Factory that creates a fresh RetrievalService."""
    from app.services.retrieval_service import RetrievalService

    def _make() -> RetrievalService:
        ds = data_service_factory()
        return RetrievalService(ds)

    yield _make


@pytest.fixture
def qa_service_factory(data_service_factory):
    """Factory that creates a fresh QAService with minimal dependencies."""
    from app.services.retrieval_service import RetrievalService
    from app.services.graph_service import GraphService
    from app.services.model_service import ModelService
    from app.services.qa_service import QAService

    def _make() -> QAService:
        ds = data_service_factory()
        rs = RetrievalService(ds)
        gs = GraphService(ds)
        ms = ModelService()
        return QAService(ds, rs, gs, ms)

    yield _make


@pytest.fixture
def agent_service_factory(data_service_factory):
    """Factory that creates a fresh AgentService with a data service."""
    from app.services.agent_service import AgentService
    from app.services.retrieval_service import RetrievalService
    from app.services.graph_service import GraphService

    created: list[AgentService] = []

    def _make() -> AgentService:
        ds = data_service_factory()
        rs = RetrievalService(ds)
        gs = GraphService(ds)
        svc = AgentService(ds, rs, gs)
        created.append(svc)
        return svc

    yield _make

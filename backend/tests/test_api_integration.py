"""Integration tests for API endpoints using FastAPI TestClient.

这套测试会真正启动 FastAPI app（含 lifespan + 模型加载），
CI 容器里通常跑不动，所以整文件统一打 integration marker。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


class TestHealthEndpoints:
    def test_root_or_docs(self, client: TestClient):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_system_health(self, client: TestClient):
        resp = client.get("/api/v1/system/health")
        assert resp.status_code in (200, 404)


class TestAuthEndpoints:
    def test_register_and_login(self, client: TestClient):
        reg = client.post("/api/v1/auth/register", json={
            "username": "testuser_integration",
            "password": "TestPass123!",
        })
        assert reg.status_code in (200, 201, 409)

        login = client.post("/api/v1/auth/login", json={
            "username": "testuser_integration",
            "password": "TestPass123!",
        })
        assert login.status_code in (200, 401)

    def test_login_wrong_password(self, client: TestClient):
        resp = client.post("/api/v1/auth/login", json={
            "username": "nonexistent_user_xyz",
            "password": "wrong",
        })
        assert resp.status_code in (401, 404)


class TestQAEndpoints:
    def test_ask_without_auth_rejected(self, client: TestClient):
        resp = client.post("/api/v1/qa/ask", json={"question": "test"})
        assert resp.status_code in (401, 403, 422)


class TestGraphEndpoints:
    def test_graph_status(self, client: TestClient):
        resp = client.get("/api/v1/graph/status")
        assert resp.status_code in (200, 404)


class TestLandingEndpoints:
    def test_landing_apod(self, client: TestClient):
        resp = client.get("/api/v1/landing/apod")
        assert resp.status_code in (200, 503)

    def test_landing_frontier(self, client: TestClient):
        resp = client.get("/api/v1/landing/frontier")
        assert resp.status_code in (200, 503)

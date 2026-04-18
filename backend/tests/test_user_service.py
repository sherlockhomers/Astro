"""Tests for UserService — registration, login, JWT, session refresh, history, favorites."""
from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-only-32chars!!")

from app.services.user_service import UserService


@pytest.fixture
def user_service(tmp_path):
    db_path = str(tmp_path / "test_user.db")
    svc = UserService.__new__(UserService)
    svc._db_path = db_path
    svc._password_iterations = 10_000
    svc._access_minutes = 30
    svc._refresh_days = 14
    svc._init_db()
    return svc


class TestRegistration:
    def test_register_success(self, user_service):
        ok, msg = user_service.register("astro_user", "Password123")
        assert ok is True
        assert "成功" in msg

    def test_register_duplicate_username(self, user_service):
        user_service.register("duplicate_user", "Password123")
        ok, msg = user_service.register("duplicate_user", "Password456")
        assert ok is False
        assert "已存在" in msg

    def test_register_short_username(self, user_service):
        ok, msg = user_service.register("ab", "Password123")
        assert ok is False

    def test_register_short_password(self, user_service):
        ok, msg = user_service.register("valid_user", "Pass1")
        assert ok is False

    def test_register_password_no_letter(self, user_service):
        ok, msg = user_service.register("valid_user", "12345678")
        assert ok is False

    def test_register_password_no_digit(self, user_service):
        ok, msg = user_service.register("valid_user", "NoDigitsHere")
        assert ok is False


class TestLogin:
    def test_login_success(self, user_service):
        user_service.register("login_user", "Password123")
        ok, msg, user_id, username, access, refresh, expires = user_service.login("login_user", "Password123")
        assert ok is True
        assert user_id is not None
        assert username == "login_user"
        assert access is not None
        assert refresh is not None
        assert expires > 0

    def test_login_wrong_password(self, user_service):
        user_service.register("login_user2", "Password123")
        ok, msg, *_ = user_service.login("login_user2", "WrongPassword1")
        assert ok is False
        # 用户存在 vs 密码错，文案应该统一，别给暴力破解留信息
        assert "用户名或密码错误" in msg

    def test_login_nonexistent_user(self, user_service):
        ok, msg, *_ = user_service.login("ghost_user", "Password123")
        assert ok is False
        assert "用户名或密码错误" in msg

    def test_login_lockout_after_repeated_failures(self, user_service):
        user_service.register("lockout_user", "Password123")
        for _ in range(5):
            ok, _msg, *_ = user_service.login("lockout_user", "WrongPass1")
            assert ok is False
        # 已经错够 5 次了，再试即便密码对也得被拒
        ok, msg, *_ = user_service.login("lockout_user", "Password123")
        assert ok is False
        assert "锁定" in msg

    def test_lockout_cleared_after_successful_login(self, user_service):
        user_service.register("clear_user", "Password123")
        for _ in range(3):
            user_service.login("clear_user", "wrong")
        ok, msg, user_id, *_ = user_service.login("clear_user", "Password123")
        assert ok is True
        # 成功登录那一下会把计数清空，后面再错几次也没到阈值
        for _ in range(4):
            user_service.login("clear_user", "wrong")
        ok2, _, *_ = user_service.login("clear_user", "Password123")
        assert ok2 is True


class TestJWT:
    def test_access_token_validates(self, user_service):
        user_service.register("jwt_user", "Password123")
        _, _, _, _, access, _, _ = user_service.login("jwt_user", "Password123")
        user = user_service.get_user_by_token(access)
        assert user is not None
        assert user["username"] == "jwt_user"

    def test_invalid_token_returns_none(self, user_service):
        assert user_service.get_user_by_token("invalid.token.here") is None
        assert user_service.get_user_by_token("") is None

    def test_refresh_token_flow(self, user_service):
        user_service.register("refresh_user", "Password123")
        _, _, _, _, _, refresh, _ = user_service.login("refresh_user", "Password123")
        ok, msg, payload = user_service.refresh_session(refresh)
        assert ok is True
        assert payload is not None
        assert payload["username"] == "refresh_user"
        assert payload["access_token"] is not None
        assert payload["refresh_token"] is not None

    def test_revoked_refresh_token_rejected(self, user_service):
        user_service.register("revoke_user", "Password123")
        _, _, _, _, _, refresh, _ = user_service.login("revoke_user", "Password123")
        user_service.revoke_refresh_token(refresh)
        ok, msg, payload = user_service.refresh_session(refresh)
        assert ok is False


class TestProfile:
    def test_get_profile(self, user_service):
        user_service.register("profile_user", "Password123")
        _, _, user_id, _, _, _, _ = user_service.login("profile_user", "Password123")
        profile = user_service.get_profile(user_id)
        assert profile is not None
        assert profile["username"] == "profile_user"

    def test_update_username(self, user_service):
        user_service.register("old_name", "Password123")
        _, _, user_id, _, _, _, _ = user_service.login("old_name", "Password123")
        ok, msg = user_service.update_username(user_id, "new_name")
        assert ok is True
        profile = user_service.get_profile(user_id)
        assert profile["username"] == "new_name"


class TestHistory:
    def test_save_and_list_history(self, user_service):
        user_service.register("hist_user", "Password123")
        _, _, user_id, _, _, _, _ = user_service.login("hist_user", "Password123")
        user_service.save_history(user_id, "s1", "火星多大?", "火星半径约3389km", "[]")
        result = user_service.list_history(user_id)
        assert result["total"] >= 1
        assert result["items"][0]["question"] == "火星多大?"

    def test_delete_history(self, user_service):
        user_service.register("hist_del_user", "Password123")
        _, _, user_id, _, _, _, _ = user_service.login("hist_del_user", "Password123")
        user_service.save_history(user_id, "s1", "test q", "test a", "[]")
        history = user_service.list_history(user_id)
        item_id = history["items"][0]["id"]
        ok, _ = user_service.delete_history(user_id, item_id)
        assert ok is True


class TestFavorites:
    def test_save_and_list_favorites(self, user_service):
        user_service.register("fav_user", "Password123")
        _, _, user_id, _, _, _, _ = user_service.login("fav_user", "Password123")
        ok, msg, fav_id = user_service.save_favorite(user_id, "木星")
        assert ok is True
        assert fav_id is not None
        favorites = user_service.list_favorites(user_id)
        assert len(favorites) >= 1

    def test_duplicate_favorite_rejected(self, user_service):
        user_service.register("fav_dup_user", "Password123")
        _, _, user_id, _, _, _, _ = user_service.login("fav_dup_user", "Password123")
        user_service.save_favorite(user_id, "土星")
        ok, msg, _ = user_service.save_favorite(user_id, "土星")
        assert ok is False
        assert "已经收藏" in msg

    def test_delete_favorite(self, user_service):
        user_service.register("fav_del_user", "Password123")
        _, _, user_id, _, _, _, _ = user_service.login("fav_del_user", "Password123")
        _, _, fav_id = user_service.save_favorite(user_id, "海王星")
        ok, _ = user_service.delete_favorite(user_id, fav_id)
        assert ok is True

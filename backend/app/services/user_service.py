from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.services.sqlite_service import get_sqlite_connection


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserService:
    def __init__(self) -> None:
        self._db_path = settings.sqlite_path
        self._password_iterations = 200_000
        self._access_minutes = int(settings.auth_access_token_minutes)
        self._refresh_days = int(settings.auth_refresh_token_days)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return get_sqlite_connection(self._db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_algo TEXT NOT NULL DEFAULT 'pbkdf2_sha256',
                password_iterations INTEGER NOT NULL DEFAULT 200000,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                citations_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                jwt_id TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                revoked_at TEXT,
                replaced_by_hash TEXT,
                user_agent TEXT,
                ip_address TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT,
                image_url TEXT,
                source_query TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, title),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_history_user_id ON qa_history(user_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_refresh_sessions_user_id ON refresh_sessions(user_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_refresh_sessions_expires_at ON refresh_sessions(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_favorites_user_id ON user_favorites(user_id, id DESC)")
        self._ensure_legacy_columns(conn)
        self._cleanup_expired_sessions(conn)
        conn.commit()

    def _ensure_legacy_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            str(row["name"]): row
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "password_algo" not in existing:
            conn.execute("ALTER TABLE users ADD COLUMN password_algo TEXT NOT NULL DEFAULT 'pbkdf2_sha256'")
        if "password_iterations" not in existing:
            conn.execute("ALTER TABLE users ADD COLUMN password_iterations INTEGER NOT NULL DEFAULT 200000")

    def _cleanup_expired_sessions(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM refresh_sessions
            WHERE expires_at <= ?
               OR revoked_at IS NOT NULL
            """,
            (_utcnow().isoformat(),),
        )

    def register(self, username: str, password: str) -> tuple[bool, str]:
        username = str(username or "").strip()
        password = str(password or "")
        valid, reason = self._validate_credentials(username, password)
        if not valid:
            return False, reason

        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt, self._password_iterations)
        now = _utcnow().isoformat()

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, password_algo, password_iterations, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    password_hash,
                    salt.hex(),
                    "pbkdf2_sha256",
                    self._password_iterations,
                    now,
                ),
            )
            conn.commit()
            return True, "注册成功。"
        except sqlite3.IntegrityError:
            return False, "用户名已存在。"

    def login(
        self,
        username: str,
        password: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> tuple[bool, str, int | None, str | None, str | None, str | None, int | None]:
        row = self._get_user_row(username)
        if row is None:
            return False, "用户不存在。", None, None, None, None, None

        if not self._verify_password(row, password):
            return False, "密码错误。", None, None, None, None, None

        user_id = int(row["id"])
        canonical_username = str(row["username"])
        access_token, refresh_token, expires_in = self._issue_session(
            user_id=user_id,
            username=canonical_username,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return True, "登录成功。", user_id, canonical_username, access_token, refresh_token, expires_in

    def refresh_session(
        self,
        refresh_token: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> tuple[bool, str, dict[str, Any] | None]:
        token = str(refresh_token or "").strip()
        if not token:
            return False, "缺少刷新令牌。", None

        payload = self._decode_jwt(token, expected_type="refresh")
        if payload is None:
            return False, "刷新令牌无效或已过期。", None

        token_hash = self._hash_refresh_token(token)
        conn = self._connect()
        row = conn.execute(
            """
            SELECT id, user_id, username, expires_at, revoked_at
            FROM refresh_sessions
            WHERE token_hash = ? AND jwt_id = ?
            """,
            (token_hash, str(payload["jti"])),
        ).fetchone()
        if row is None:
            return False, "刷新令牌不存在或已失效。", None

        if row["revoked_at"] is not None:
            return False, "刷新令牌已失效。", None

        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        if expires_at <= _utcnow():
            conn.execute("DELETE FROM refresh_sessions WHERE id = ?", (int(row["id"]),))
            conn.commit()
            return False, "刷新令牌已过期，请重新登录。", None

        username = str(row["username"])
        user_id = int(row["user_id"])
        access_token, new_refresh_token, expires_in = self._issue_session(
            user_id=user_id,
            username=username,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        new_hash = self._hash_refresh_token(new_refresh_token)
        conn.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = ?, replaced_by_hash = ?
            WHERE id = ?
            """,
            (_utcnow().isoformat(), new_hash, int(row["id"])),
        )
        conn.commit()
        return True, "刷新成功。", {
            "user_id": user_id,
            "username": username,
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "expires_in": expires_in,
        }

    def revoke_refresh_token(self, refresh_token: str) -> None:
        token = str(refresh_token or "").strip()
        if not token:
            return
        token_hash = self._hash_refresh_token(token)
        conn = self._connect()
        conn.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = COALESCE(revoked_at, ?)
            WHERE token_hash = ?
            """,
            (_utcnow().isoformat(), token_hash),
        )
        conn.commit()

    def get_user_by_token(self, token: str) -> dict[str, Any] | None:
        payload = self._decode_jwt(str(token or "").strip(), expected_type="access")
        if payload is None:
            return None
        return {
            "user_id": int(payload["sub"]),
            "username": str(payload["username"]),
        }

    def get_profile(self, user_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "user_id": int(row["id"]),
            "username": str(row["username"]),
            "created_at": str(row["created_at"]),
        }

    def update_username(self, user_id: int, new_username: str) -> tuple[bool, str]:
        username = str(new_username or "").strip()
        if len(username) < 3:
            return False, "用户名至少需要 3 个字符。"
        conn = self._connect()
        try:
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
            conn.execute("UPDATE refresh_sessions SET username = ? WHERE user_id = ?", (username, user_id))
            conn.commit()
        except sqlite3.IntegrityError:
            return False, "用户名已存在。"
        return True, "用户名已更新。"

    def save_history(
        self,
        user_id: int,
        session_id: str,
        question: str,
        answer: str,
        citations_json: str,
    ) -> None:
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO qa_history (user_id, session_id, question, answer, citations_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, session_id, question, answer, citations_json, _utcnow().isoformat()),
        )
        conn.commit()

    def list_history(self, user_id: int, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        conn = self._connect()
        total = int(
            conn.execute("SELECT COUNT(*) FROM qa_history WHERE user_id = ?", (user_id,)).fetchone()[0]
        )
        rows = conn.execute(
            """
            SELECT id, session_id, question, answer, citations_json, created_at
            FROM qa_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, safe_limit, safe_offset),
        ).fetchall()
        items = [dict(row) for row in rows]
        return {
            "items": items,
            "limit": safe_limit,
            "offset": safe_offset,
            "total": total,
            "has_more": safe_offset + len(items) < total,
        }

    def delete_history(self, user_id: int, history_id: int) -> tuple[bool, str]:
        conn = self._connect()
        row = conn.execute(
            "SELECT id FROM qa_history WHERE id = ? AND user_id = ?",
            (int(history_id), int(user_id)),
        ).fetchone()
        if row is None:
            return False, "记录不存在。"
        conn.execute("DELETE FROM qa_history WHERE id = ? AND user_id = ?", (int(history_id), int(user_id)))
        conn.commit()
        return True, "历史记录已删除。"

    def save_favorite(
        self,
        user_id: int,
        title: str,
        category: str | None = None,
        image_url: str | None = None,
        source_query: str | None = None,
    ) -> tuple[bool, str, int | None]:
        clean_title = str(title or "").strip()
        if not clean_title:
            return False, "收藏标题不能为空。", None
        conn = self._connect()
        now = _utcnow().isoformat()
        try:
            cur = conn.execute(
                """
                INSERT INTO user_favorites (user_id, title, category, image_url, source_query, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(user_id), clean_title, str(category or "").strip() or None, str(image_url or "").strip() or None, str(source_query or "").strip() or None, now),
            )
            conn.commit()
            return True, "已加入收藏。", int(cur.lastrowid or 0)
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM user_favorites WHERE user_id = ? AND title = ?",
                (int(user_id), clean_title),
            ).fetchone()
            return False, "该天体已经收藏过了。", int(row["id"]) if row else None

    def list_favorites(self, user_id: int, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT id, title, category, image_url, source_query, created_at
            FROM user_favorites
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(user_id), safe_limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_favorite(self, user_id: int, favorite_id: int) -> tuple[bool, str]:
        conn = self._connect()
        row = conn.execute(
            "SELECT id FROM user_favorites WHERE id = ? AND user_id = ?",
            (int(favorite_id), int(user_id)),
        ).fetchone()
        if row is None:
            return False, "收藏项不存在。"
        conn.execute("DELETE FROM user_favorites WHERE id = ? AND user_id = ?", (int(favorite_id), int(user_id)))
        conn.commit()
        return True, "收藏项已删除。"

    def build_overview(self, user_id: int) -> dict[str, Any]:
        profile = self.get_profile(user_id)
        history = self.list_history(user_id, limit=80, offset=0)
        favorites = self.list_favorites(user_id, limit=24)
        recent = self._build_recent_explorations(history.get("items", []))
        recommended = self._build_recommendations(recent, favorites)
        history_preview = []
        for row in history.get("items", [])[:8]:
            citations = []
            try:
                citations = json.loads(str(row.get("citations_json", "[]")))
            except json.JSONDecodeError:
                citations = []
            history_preview.append(
                {
                    "id": int(row["id"]),
                    "session_id": str(row["session_id"]),
                    "question": str(row["question"]),
                    "answer": str(row["answer"]),
                    "citations": citations,
                    "created_at": str(row["created_at"]),
                }
            )
        return {
            "ok": True,
            "user_id": int(profile["user_id"]) if profile else int(user_id),
            "username": str(profile["username"]) if profile else "",
            "created_at": profile["created_at"] if profile else None,
            "stats": {
                "history_count": int(history.get("total", 0)),
                "favorites_count": len(favorites),
                "recent_count": len(recent),
            },
            "recent_explorations": recent,
            "favorites": favorites,
            "history_preview": history_preview,
            "recommended_continue": recommended,
        }

    def _build_recent_explorations(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            question = str(row.get("question", "")).strip()
            topic = self._extract_topic(question)
            if not topic:
                continue
            key = topic.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "id": int(row["id"]),
                    "session_id": str(row.get("session_id", "")),
                    "question": question,
                    "topic": topic,
                    "created_at": str(row.get("created_at", "")),
                }
            )
            if len(items) >= 8:
                break
        return items

    def _build_recommendations(self, recent: list[dict[str, Any]], favorites: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seeds: list[str] = []
        for item in recent[:4]:
            topic = str(item.get("topic", "")).strip()
            if topic and topic not in seeds:
                seeds.append(topic)
        for item in favorites[:4]:
            title = str(item.get("title", "")).strip()
            if title and title not in seeds:
                seeds.append(title)

        recommendations: list[dict[str, Any]] = []
        templates = [
            ("为什么{topic}这么特别？", "继续补充核心机制", "/app/qa"),
            ("{topic}和其他相近天体有什么区别？", "从对比视角继续探索", "/app/knowledge"),
            ("帮我查看{topic}的3D模型", "切到三维视角继续观察", "/app/starfield"),
        ]
        seen_queries: set[str] = set()
        for topic in seeds[:4]:
            for template, reason, path in templates:
                query = template.format(topic=topic)
                if query in seen_queries:
                    continue
                seen_queries.add(query)
                recommendations.append(
                    {
                        "title": query,
                        "query": query,
                        "reason": reason,
                        "path": path,
                    }
                )
                if len(recommendations) >= 8:
                    return recommendations
        if not recommendations:
            recommendations.extend(
                [
                    {"title": "木星为什么会有这么多卫星？", "query": "木星为什么会有这么多卫星？", "reason": "从行星系统入门", "path": "/app/qa"},
                    {"title": "黑洞为什么连光都逃不出来？", "query": "黑洞为什么连光都逃不出来？", "reason": "从极端引力现象入门", "path": "/app/qa"},
                    {"title": "查看土星的3D模型", "query": "土星", "reason": "进入三维观察模式", "path": "/app/starfield"},
                ]
            )
        return recommendations[:8]

    @staticmethod
    def _extract_topic(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        known = [
            "黑洞", "银河系", "仙女座星系", "木星", "土星", "火星", "地球", "月球", "太阳",
            "海王星", "天王星", "金星", "水星", "彗星", "星云", "恒星", "白矮星", "中子星",
            "引力波", "行星状星云", "旋涡星系",
        ]
        for item in known:
            if item in raw:
                return item
        match = re.search(r"[\u4e00-\u9fffA-Za-z0-9]{2,16}(黑洞|星系|星云|行星|卫星|彗星|太阳|月球|地球|火星|木星|土星|海王星|天王星|金星|水星)", raw)
        if match:
            return match.group(0)
        return raw[:18]

    def _validate_credentials(self, username: str, password: str) -> tuple[bool, str]:
        if len(username) < 3:
            return False, "用户名至少需要 3 个字符。"
        if len(password) < 8:
            return False, "密码至少需要 8 个字符。"
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            return False, "密码需要同时包含字母和数字。"
        return True, ""

    def _get_user_row(self, username: str) -> sqlite3.Row | None:
        conn = self._connect()
        return conn.execute(
            """
            SELECT id, username, password_hash, salt, password_algo, password_iterations
            FROM users WHERE username = ?
            """,
            (str(username or "").strip(),),
        ).fetchone()

    def _verify_password(self, row: sqlite3.Row, password: str) -> bool:
        algo = str(row["password_algo"] or "legacy")
        if algo == "pbkdf2_sha256":
            salt_bytes = bytes.fromhex(str(row["salt"]))
            actual = self._hash_password(password, salt_bytes, int(row["password_iterations"] or self._password_iterations))
            return hmac.compare_digest(actual, str(row["password_hash"]))

        legacy_hash = self._legacy_hash_password(password, str(row["salt"]))
        if not hmac.compare_digest(legacy_hash, str(row["password_hash"])):
            return False

        self._rehash_password_after_legacy_login(int(row["id"]), password)
        return True

    def _rehash_password_after_legacy_login(self, user_id: int, password: str) -> None:
        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt, self._password_iterations)
        conn = self._connect()
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, salt = ?, password_algo = 'pbkdf2_sha256', password_iterations = ?
            WHERE id = ?
            """,
            (password_hash, salt.hex(), self._password_iterations, user_id),
        )
        conn.commit()

    def _hash_password(self, password: str, salt: bytes, iterations: int) -> str:
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return derived.hex()

    def _legacy_hash_password(self, password: str, salt: str) -> str:
        payload = f"{settings.auth_secret}:{salt}:{password}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _issue_session(
        self,
        user_id: int,
        username: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> tuple[str, str, int]:
        access_expires_at = _utcnow() + timedelta(minutes=self._access_minutes)
        refresh_expires_at = _utcnow() + timedelta(days=self._refresh_days)
        jwt_id = secrets.token_urlsafe(16)

        access_token = self._encode_jwt(
            {
                "sub": str(user_id),
                "username": username,
                "type": "access",
                "exp": int(access_expires_at.timestamp()),
                "iat": int(_utcnow().timestamp()),
            }
        )
        refresh_token = self._encode_jwt(
            {
                "sub": str(user_id),
                "username": username,
                "type": "refresh",
                "jti": jwt_id,
                "exp": int(refresh_expires_at.timestamp()),
                "iat": int(_utcnow().timestamp()),
            }
        )
        token_hash = self._hash_refresh_token(refresh_token)
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO refresh_sessions (
                user_id, username, token_hash, jwt_id, expires_at, issued_at, revoked_at, replaced_by_hash, user_agent, ip_address
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                user_id,
                username,
                token_hash,
                jwt_id,
                refresh_expires_at.isoformat(),
                _utcnow().isoformat(),
                user_agent[:255],
                ip_address[:64],
            ),
        )
        conn.commit()
        return access_token, refresh_token, self._access_minutes * 60

    def _hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(f"{settings.auth_secret}:{token}".encode("utf-8")).hexdigest()

    def _encode_jwt(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        header_segment = self._b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_segment = self._b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
        signature = hmac.new(settings.auth_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        signature_segment = self._b64url_encode(signature)
        return f"{header_segment}.{payload_segment}.{signature_segment}"

    def _decode_jwt(self, token: str, expected_type: str | None = None) -> dict[str, Any] | None:
        try:
            header_segment, payload_segment, signature_segment = token.split(".")
        except ValueError:
            return None

        signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
        expected_signature = hmac.new(
            settings.auth_secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        actual_signature = self._b64url_decode(signature_segment)
        if not hmac.compare_digest(expected_signature, actual_signature):
            return None

        try:
            payload = json.loads(self._b64url_decode(payload_segment).decode("utf-8"))
        except Exception:
            return None

        expires_at = int(payload.get("exp", 0) or 0)
        if expires_at <= int(_utcnow().timestamp()):
            return None
        if expected_type and payload.get("type") != expected_type:
            return None
        if "sub" not in payload or "username" not in payload:
            return None
        return payload

    def _b64url_encode(self, raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def _b64url_decode(self, encoded: str) -> bytes:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))

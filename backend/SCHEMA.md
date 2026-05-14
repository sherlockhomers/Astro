# AstroGraph 后端数据库 Schema

> 项目当前不使用 Alembic 也不使用 SQLAlchemy ORM。所有持久化都走 raw `sqlite3`，
> 表结构由各 service 启动时 `CREATE TABLE IF NOT EXISTS` 自愈式维护。
> 之前曾经有 `backend/alembic/` 和 `backend/app/models.py`，但建的表（`auth_tokens` 等）
> 与运行时实际使用的表（`refresh_sessions` 等）严重漂移，已在审计后删除避免误导。

如果将来想引入正式的迁移工具（推荐 Alembic），需要：

1. 用当前运行时实际表为基线重新生成 baseline migration（不要复用之前那份）
2. 切换 service 的 `_init_db` 改为只跑迁移
3. 在 lifespan 启动阶段调用 `alembic upgrade head`

## 当前运行时表清单

| 表 | 维护者 | 主要字段 |
|---|---|---|
| `users` | `app/services/user_service.py::_init_db` | id, username UNIQUE, password_hash, salt, password_algo, password_iterations, created_at |
| `qa_history` | `user_service` | id, user_id FK, session_id, question, answer, citations_json, created_at |
| `refresh_sessions` | `user_service` | id, user_id, username, token_hash UNIQUE, jwt_id UNIQUE, expires_at, issued_at, revoked_at, replaced_by_hash, user_agent, ip_address |
| `user_favorites` | `user_service` | id, user_id, title, category, image_url, source_query, created_at, UNIQUE(user_id, title) |
| `login_failures` | `user_service` | id, username, ip_address, failed_at |
| `image_assets` | `app/services/data_service.py` | image_id PK, title, source, ref, kind, url, object_keys_json, bucket |
| `knowledge_chunks` | `data_service` | entity_id PK, title, description, category, source_file, raw_json |
| `qa_sessions` | `app/services/qa_service.py` | （消息上下文持久化） |
| `qa_agent_memory` | `app/services/adaptive_agent_orchestrator.py` | Agent 反思记忆 |
| `qa_reflection_logs` | `adaptive_agent_orchestrator` | Agent 反思日志 |
| `dynamic_facts` | `app/services/dynamic_data_service.py` | 动态事实缓存 |

## 索引清单

`user_service._init_db` 显式建了 5 个 idx：

- `idx_users_username`
- `idx_login_failures_lookup`（username, failed_at DESC）
- `idx_qa_history_user_id`
- `idx_refresh_sessions_user_id`
- `idx_refresh_sessions_expires_at`
- `idx_user_favorites_user_id`

其余表的索引参见各自 service 的 `CREATE INDEX` 语句。

## 已知 schema 兼容路径

`user_service._init_db._ensure_legacy_columns` 用 `PRAGMA table_info` 检测，缺列时 `ALTER TABLE` 加。当前迁移点：

- `users.password_algo`（默认 `pbkdf2_sha256`）
- `users.password_iterations`（默认 200000）

新增列时按这个模式追加。

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app.config import settings

_LOCAL = threading.local()
_INIT_LOCK = threading.Lock()


class SQLiteConnectionProxy:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        # Services still call close() in finally blocks. Keep the real connection
        # hot in thread-local storage so repeated requests reuse WAL-backed handles.
        return None


def _storage() -> dict[str, sqlite3.Connection]:
    conns = getattr(_LOCAL, "connections", None)
    if conns is None:
        conns = {}
        _LOCAL.connections = conns
    return conns


def _db_key(db_path: str) -> str:
    return str(Path(db_path).expanduser().resolve())


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={max(1000, int(settings.sqlite_busy_timeout_ms))}")
    conn.execute("PRAGMA temp_store=MEMORY")


def get_sqlite_connection(db_path: str) -> SQLiteConnectionProxy:
    key = _db_key(db_path)
    store = _storage()
    conn = store.get(key)
    if conn is None:
        with _INIT_LOCK:
            conn = store.get(key)
            if conn is None:
                Path(key).parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(key, timeout=30, check_same_thread=False)
                _configure_connection(conn)
                store[key] = conn
    return SQLiteConnectionProxy(conn)


def close_thread_connections() -> None:
    store = _storage()
    for conn in list(store.values()):
        try:
            conn.close()
        except Exception:
            pass
    store.clear()

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def resolve_db_path(db_path: str | None = None) -> str:
    """返回持久化数据库路径，支持环境变量和 sqlite:// 形式。"""
    candidate = db_path
    if candidate is None:
        for key in ("CHAT_DB_PATH", "DATABASE_URL", "DB_PATH", "SQLITE_DB_PATH"):
            value = os.getenv(key)
            if value:
                candidate = value
                break
        if candidate is None:
            candidate = "chat.db"

    if candidate.startswith("sqlite:///"):
        candidate = candidate[len("sqlite:///") :]
    elif candidate.startswith("sqlite://"):
        candidate = candidate[len("sqlite://") :]

    if candidate in {":memory:", "file::memory:?cache=shared"}:
        return candidate

    path = Path(candidate)
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path)


class ChatStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = resolve_db_path(db_path)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        path = Path(self.db_path)
        if path.name not in {":memory:", ""}:
            path.parent.mkdir(parents=True, exist_ok=True)

        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
        conn.close()

    def create_session(self, title: str | None = None) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        now = self._now()
        title = title or "新会话"
        conn = self._connect()
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
        conn.commit()
        session = self.get_session(session_id)
        conn.close()
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at ASC, id ASC"
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        if self.get_session(session_id) is None:
            return []

        conn = self._connect()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        conn.close()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def add_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        if self.get_session(session_id) is None:
            raise ValueError(f"session {session_id!r} does not exist")

        conn = self._connect()
        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, self._now()),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (self._now(), session_id),
        )
        conn.commit()
        message = {
            "id": cursor.lastrowid,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": self._now(),
        }
        conn.close()
        return message

    def clear_session(self, session_id: str) -> None:
        if self.get_session(session_id) is None:
            return
        conn = self._connect()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (self._now(), session_id),
        )
        conn.commit()
        conn.close()

    def delete_session(self, session_id: str) -> bool:
        conn = self._connect()
        cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    @staticmethod
    def _now() -> str:
        import datetime

        return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_chat_store = ChatStore()


def get_store(db_path: str | None = None) -> ChatStore:
    if db_path is not None:
        return ChatStore(db_path)
    return ChatStore(resolve_db_path())

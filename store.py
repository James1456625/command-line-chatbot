import datetime
import os
import uuid
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, select, ForeignKey, String, Text, Integer, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from sqlalchemy.pool import StaticPool


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


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MessageModel.id",
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    session: Mapped[SessionModel] = relationship(back_populates="messages")


class ChatStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = resolve_db_path(db_path)
        self.engine = self._create_engine()

        @event.listens_for(self.engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _create_engine(self):
        if self.db_path in {":memory:", "file::memory:?cache=shared"}:
            url = "sqlite:///:memory:" if self.db_path == ":memory:" else f"sqlite:///{self.db_path}"
            return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)

        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path.as_posix()}"
        return create_engine(url, connect_args={"check_same_thread": False})

    @staticmethod
    def _now() -> str:
        return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def create_session(self, title: str | None = None) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        now = self._now()
        orm_session = SessionModel(
            id=session_id,
            title=title or "新会话",
            created_at=now,
            updated_at=now,
        )
        with self.Session() as db:
            db.add(orm_session)
            db.commit()
        return self._session_dict(orm_session)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.Session() as db:
            rows = db.execute(
                select(SessionModel).order_by(SessionModel.created_at.asc(), SessionModel.id.asc())
            ).scalars().all()
            return [self._session_dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.Session() as db:
            row = db.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            ).scalar_one_or_none()
            return self._session_dict(row) if row else None

    def get_messages(self, session_id: str, keyword: str | None = None) -> list[dict[str, Any]]:
        if self.get_session(session_id) is None:
            return []

        with self.Session() as db:
            statement = (
                select(MessageModel)
                .where(MessageModel.session_id == session_id)
                .order_by(MessageModel.id.asc())
            )
            if keyword is not None:
                keyword = keyword.strip()
                if keyword:
                    # 对应 SQL: WHERE session_id = ? AND content LIKE '%keyword%'
                    statement = statement.where(MessageModel.content.contains(keyword))

            rows = db.execute(statement).scalars().all()
            return [{"role": row.role, "content": row.content} for row in rows]

    def add_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        return self.add_messages(session_id, [(role, content)])[0]

    def add_messages(self, session_id: str, messages: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
        """在一个事务中写入一组消息；任一步失败则整组回滚。"""
        items = list(messages)
        if not items:
            return []

        with self.Session() as db:
            try:
                session_row = db.execute(
                    select(SessionModel).where(SessionModel.id == session_id)
                ).scalar_one_or_none()
                if session_row is None:
                    raise ValueError(f"session {session_id!r} does not exist")

                created: list[MessageModel] = []
                now = self._now()
                for role, content in items:
                    message = MessageModel(
                        session_id=session_id,
                        role=role,
                        content=content,
                        created_at=now,
                    )
                    db.add(message)
                    created.append(message)
                    db.flush()

                session_row.updated_at = now
                db.flush()
                db.commit()
                return [self._message_dict(message) for message in created]
            except Exception:
                db.rollback()
                raise

    def add_turn(self, session_id: str, user_message: str, assistant_reply: str) -> list[dict[str, Any]]:
        """原子写入一轮对话中的用户消息和机器人回复。"""
        return self.add_messages(session_id, [("user", user_message), ("assistant", assistant_reply)])

    def clear_session(self, session_id: str) -> None:
        with self.Session() as db:
            session_row = db.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            ).scalar_one_or_none()
            if session_row is None:
                return
            for message in list(session_row.messages):
                db.delete(message)
            session_row.updated_at = self._now()
            db.commit()

    def delete_session(self, session_id: str) -> bool:
        with self.Session() as db:
            session_row = db.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            ).scalar_one_or_none()
            if session_row is None:
                return False
            db.delete(session_row)
            db.commit()
            return True

    @staticmethod
    def _session_dict(row: SessionModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _message_dict(row: MessageModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "session_id": row.session_id,
            "role": row.role,
            "content": row.content,
            "created_at": row.created_at,
        }


_chat_store = ChatStore()


def get_store(db_path: str | None = None) -> ChatStore:
    if db_path is not None:
        return ChatStore(db_path)
    return ChatStore(resolve_db_path())

import json
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from llm import call_llm
from store import ChatStore, get_store


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, description="新会话标题")


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, description="会话 ID")
    message: str | None = Field(default=None, description="用户消息")
    content: str | None = Field(default=None, description="用户消息别名")
    user_input: str | None = Field(default=None, description="用户消息别名")


app = FastAPI(title="Chatbot App", version="1.0.0")
store: ChatStore = get_store()


def generate_reply(messages: list[dict[str, str]], stream: bool = False) -> Any:
    return call_llm(messages, stream=stream)


def _extract_message(payload: ChatRequest | None = None, message: str | None = None) -> str:
    text = message or (payload.message if payload else None) or (payload.content if payload else None) or (payload.user_input if payload else None)
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="message is required")
    return text.strip()


@app.get("/")
def read_index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/sessions")
def list_sessions() -> list[dict[str, Any]]:
    return store.list_sessions()


@app.post("/sessions")
def create_session(payload: SessionCreateRequest) -> dict[str, Any]:
    session = store.create_session(payload.title)
    return session


@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: str) -> list[dict[str, Any]]:
    return store.get_messages(session_id)


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    deleted = store.delete_session(session_id)
    return {"deleted": deleted, "session_id": session_id}


@app.post("/sessions/{session_id}/clear")
def clear_session(session_id: str) -> dict[str, Any]:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    store.clear_session(session_id)
    return {"session_id": session_id, "cleared": True}


@app.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    message = _extract_message(payload)
    session_id = payload.session_id

    if not session_id or store.get_session(session_id) is None:
        session = store.create_session(title="新会话")
        session_id = session["id"]

    store.add_message(session_id, "user", message)
    history = store.get_messages(session_id)
    context = [{"role": item["role"], "content": item["content"]} for item in history]

    reply = generate_reply(context, stream=False)
    store.add_message(session_id, "assistant", reply)

    return {
        "session_id": session_id,
        "reply": reply,
        "messages": store.get_messages(session_id),
    }


@app.get("/chat/stream")
async def chat_stream(session_id: str | None = Query(default=None), message: str | None = Query(default=None)) -> StreamingResponse:
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    if not session_id or store.get_session(session_id) is None:
        session = store.create_session(title="新会话")
        session_id = session["id"]

    text = message.strip()
    store.add_message(session_id, "user", text)
    history = store.get_messages(session_id)
    context = [{"role": item["role"], "content": item["content"]} for item in history]

    async def _generate() -> Iterable[str]:
        chunks: list[str] = []
        for token in generate_reply(context, stream=True):
            chunks.append(str(token))
            payload = json.dumps({"type": "token", "text": str(token)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        reply = "".join(chunks)
        store.add_message(session_id, "assistant", reply)
        yield f"data: {json.dumps({'type': 'done', 'reply': reply}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

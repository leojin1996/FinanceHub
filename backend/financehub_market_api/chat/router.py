from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..auth.dependencies import AuthenticatedUser, get_current_user
from .agent import ChatAgent, ChatStreamEvent, build_chat_agent
from .models import (
    ChatMessage,
    ChatMessageListResponse,
    ChatSession,
    ChatSessionListResponse,
    SendMessageRequest,
)
from .recall_service import (
    ChatHistoryRecallService,
    build_chat_history_recall_service_from_env,
)
from .store import (
    ChatSessionStore,
    ChatStoreError,
    InMemoryChatSessionStore,
    build_chat_session_store,
)

LOGGER = logging.getLogger(__name__)

chat_router = APIRouter(prefix="/api/chat", tags=["chat"])

ChatSessionStoreLike = ChatSessionStore | InMemoryChatSessionStore
CHAT_HISTORY_RECALL_LIMIT = 5
CHAT_HISTORY_UNKNOWN_RISK_PROFILE = "unknown"
CHAT_HISTORY_SYSTEM_CONTEXT_PREFIX = (
    "Historical user memory recalled from previous chats. "
    "Use these notes only when they are relevant to the current request. "
    "Do not mention the retrieval process or present them as certain facts.\n"
)


@lru_cache(maxsize=1)
def get_chat_session_store() -> ChatSessionStoreLike:
    """Redis-backed store when available; otherwise in-memory (see build_chat_session_store)."""
    return build_chat_session_store()


@lru_cache(maxsize=1)
def get_chat_history_recall_service() -> ChatHistoryRecallService | None:
    return build_chat_history_recall_service_from_env()


@lru_cache(maxsize=1)
def get_chat_agent() -> ChatAgent:
    from ..main import get_market_data_service

    return build_chat_agent(get_market_data_service())


def _messages_to_openai_format(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Map stored messages to OpenAI chat format (user and assistant only)."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role in ("user", "assistant"):
            out.append({"role": msg.role, "content": msg.content})
    return out


def _recall_chat_history_snippets(
    recall_service: ChatHistoryRecallService | None,
    *,
    user_id: str,
    session_id: str,
    history: list[ChatMessage],
    latest_user_message: str,
) -> list[str]:
    if recall_service is None or not latest_user_message.strip():
        return []
    recent_user_messages = tuple(
        message.content
        for message in history
        if message.role == "user" and message.content.strip()
    )[-3:]
    try:
        return recall_service.recall(
            user_id=user_id,
            risk_profile=CHAT_HISTORY_UNKNOWN_RISK_PROFILE,
            user_intent_text=latest_user_message,
            latest_user_message=latest_user_message,
            limit=CHAT_HISTORY_RECALL_LIMIT,
            recent_user_messages=recent_user_messages,
            active_session_id=session_id,
        )
    except Exception:
        LOGGER.exception(
            "Failed to recall historical chat snippets for chat assistant",
            extra={"user_id": user_id},
        )
        return []


def _build_recalled_history_context_message(
    *,
    history: list[ChatMessage],
    recalled_snippets: list[str],
) -> dict[str, str] | None:
    session_user_messages = {
        message.content.strip()
        for message in history
        if message.role == "user" and message.content.strip()
    }
    filtered_snippets: list[str] = []
    seen: set[str] = set()
    for snippet in recalled_snippets:
        normalized = snippet.strip()
        if (
            not normalized
            or normalized in seen
            or normalized in session_user_messages
        ):
            continue
        seen.add(normalized)
        filtered_snippets.append(normalized)
    if not filtered_snippets:
        return None
    return {
        "role": "system",
        "content": CHAT_HISTORY_SYSTEM_CONTEXT_PREFIX
        + json.dumps(filtered_snippets, ensure_ascii=False),
    }


def _chat_sse_stream(
    *,
    agent_stream: Generator[ChatStreamEvent, None, None],
    store: ChatSessionStoreLike,
    session_id: str,
    user_id: str,
) -> Generator[str, None, None]:
    """Format ChatAgent stream as SSE, accumulate assistant text, persist when done."""
    content_parts: list[str] = []
    try:
        for event in agent_stream:
            yield f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"
            if event.event == "delta":
                piece = event.data.get("content")
                if isinstance(piece, str) and piece:
                    content_parts.append(piece)
    finally:
        full_text = "".join(content_parts)
        if not full_text:
            return
        assistant = ChatMessage(
            id=uuid.uuid4().hex,
            role="assistant",
            content=full_text,
            created_at=datetime.now(UTC).isoformat(),
        )
        try:
            store.add_message(session_id, assistant, user_id)
        except ChatStoreError:
            LOGGER.exception(
                "Failed to persist assistant message after stream for session %s",
                session_id,
            )


def _streaming_chat_response(
    *,
    agent_stream: Generator[ChatStreamEvent, None, None],
    store: ChatSessionStoreLike,
    session_id: str,
    user_id: str,
) -> StreamingResponse:
    return StreamingResponse(
        _chat_sse_stream(
            agent_stream=agent_stream,
            store=store,
            session_id=session_id,
            user_id=user_id,
        ),
        media_type="text/event-stream",
    )


@chat_router.post("/sessions", response_model=ChatSession)
def create_chat_session(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[ChatSessionStoreLike, Depends(get_chat_session_store)],
) -> ChatSession:
    try:
        return store.create_session(user.user_id)
    except ChatStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@chat_router.get("/sessions", response_model=ChatSessionListResponse)
def list_chat_sessions(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[ChatSessionStoreLike, Depends(get_chat_session_store)],
    limit: int = Query(default=50, ge=0, le=500),
) -> ChatSessionListResponse:
    try:
        sessions = store.list_sessions(user.user_id, limit)
    except ChatStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatSessionListResponse(sessions=sessions)


@chat_router.get(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageListResponse,
)
def get_chat_messages(
    session_id: str,
    _user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[ChatSessionStoreLike, Depends(get_chat_session_store)],
) -> ChatMessageListResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    try:
        messages = store.get_messages(session_id)
    except ChatStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatMessageListResponse(messages=messages)


def _index_user_chat_message(
    recall_service: ChatHistoryRecallService | None,
    *,
    user_id: str,
    session_id: str,
    message: ChatMessage,
) -> None:
    if recall_service is None or message.role != "user":
        return
    try:
        recall_service.index_user_message(
            user_id=user_id,
            session_id=session_id,
            message_id=message.id,
            content=message.content,
            created_at=message.created_at,
        )
    except Exception:
        LOGGER.exception(
            "Failed to index user chat message for recall",
            extra={"session_id": session_id, "user_id": user_id},
        )


@chat_router.post("/sessions/{session_id}/messages")
def send_chat_message(
    session_id: str,
    body: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[ChatSessionStoreLike, Depends(get_chat_session_store)],
    agent: Annotated[ChatAgent, Depends(get_chat_agent)],
    recall_service: Annotated[
        ChatHistoryRecallService | None, Depends(get_chat_history_recall_service)
    ],
) -> StreamingResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="chat session not found")

    user_message = ChatMessage(
        id=uuid.uuid4().hex,
        role="user",
        content=body.content,
        created_at=datetime.now(UTC).isoformat(),
    )
    try:
        store.add_message(session_id, user_message, user.user_id)
    except ChatStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="chat session not found") from exc

    background_tasks.add_task(
        _index_user_chat_message,
        recall_service,
        user_id=user.user_id,
        session_id=session_id,
        message=user_message,
    )

    history = store.get_messages(session_id)
    openai_messages = _messages_to_openai_format(history)
    recalled_context_message = _build_recalled_history_context_message(
        history=history,
        recalled_snippets=_recall_chat_history_snippets(
            recall_service,
            user_id=user.user_id,
            session_id=session_id,
            history=history,
            latest_user_message=user_message.content,
        ),
    )
    if recalled_context_message is not None:
        openai_messages = [recalled_context_message, *openai_messages]
    stream = agent.stream(openai_messages)
    return _streaming_chat_response(
        agent_stream=stream,
        store=store,
        session_id=session_id,
        user_id=user.user_id,
    )


@chat_router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[ChatSessionStoreLike, Depends(get_chat_session_store)],
) -> dict[str, bool]:
    try:
        deleted = store.delete_session(session_id, user.user_id)
    except ChatStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="chat session not found")
    return {"deleted": True}

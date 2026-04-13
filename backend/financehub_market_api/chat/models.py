from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ChatRole = Literal["user", "assistant", "system", "tool"]


class ChatSession(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ChatMessage(BaseModel):
    id: str
    role: ChatRole
    content: str
    created_at: str
    tool_calls: list[dict[str, Any]] | None = None


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSession]


class ChatMessageListResponse(BaseModel):
    messages: list[ChatMessage]


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)

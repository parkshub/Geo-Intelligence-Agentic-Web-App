from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Conversation ordered oldest to newest.",
    )
    trace_id: str | None = None


class ChatResponse(BaseModel):
    output: str
    tool_calls: list[dict] = Field(default_factory=list)
    debug: dict | None = None

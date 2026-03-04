from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings
from app.models import ChatRequest, ChatResponse
from app.services.agent import AgentService
from app.utils.logging import get_logger

settings = get_settings()
agent_service = AgentService()
logger = get_logger(__name__)

app = FastAPI(title="Geo-Intel Agent Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    logger.info(
        "http.request.start",
        method=request.method,
        path=request.url.path,
        query=str(request.url.query),
    )
    try:
        response: Response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "http.request.error",
            method=request.method,
            path=request.url.path,
            elapsed_ms=elapsed_ms,
        )
        raise
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "http.request.end",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "environment": settings.environment}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    logger.info(
        "chat.request",
        message_count=len(payload.messages),
        last_role=(payload.messages[-1].role if payload.messages else None),
        last_message_preview=(payload.messages[-1].content[:160] if payload.messages else ""),
    )
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages required")
    try:
        result = await agent_service.run(payload.messages, trace_id=payload.trace_id)
    except Exception:
        logger.exception("chat.error", message_count=len(payload.messages))
        raise
    response = ChatResponse(
        output=result.get("output", ""),
        tool_calls=[step for step in result.get("intermediate_steps", [])],
        debug={"log": result.get("logs")},
    )
    logger.info(
        "chat.response",
        output_length=len(response.output),
        tool_call_count=len(response.tool_calls),
        output_preview=response.output[:200],
    )
    return response

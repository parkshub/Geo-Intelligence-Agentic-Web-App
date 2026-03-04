from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings
from app.routers import places
from app.utils.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(
    title="Geo-Intelligence MCP Server",
    version="0.1.0",
    description="Wrapper around Geoapify/Overpass APIs with MCP-compatible endpoints.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places.router)


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
async def healthcheck():
    return {"status": "ok", "environment": settings.environment}

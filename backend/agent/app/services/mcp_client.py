from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.utils.logging import get_logger


class MCPClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = httpx.AsyncClient(base_url=settings.mcp.base_url, timeout=30.0)
        self._logger = get_logger(__name__)

    async def geocode(self, query: str) -> dict[str, Any]:
        self._logger.info("mcp_client.geocode", query=query)
        return await self._post_json("/places/geocode", {"query": query}, "geocode")

    async def search_places(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self._logger.info("mcp_client.search", payload=payload)
        return await self._post_json("/places/search", payload, "search")

    async def profile_area(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._logger.info("mcp_client.profile", payload=payload)
        return await self._post_json("/places/profile", payload, "profile")

    async def compare_areas(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._logger.info("mcp_client.compare", payload=payload)
        return await self._post_json("/places/compare", payload, "compare")

    async def demographics_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._logger.info("mcp_client.demographics", payload=payload)
        return await self._post_json("/places/demographics", payload, "demographics")

    async def demographics_compare(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._logger.info("mcp_client.demographics_compare", payload=payload)
        return await self._post_json("/places/demographics/compare", payload, "demographics_compare")

    async def industry_research(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._logger.info("mcp_client.industry_research", payload=payload)
        return await self._post_json("/places/industries", payload, "industry_research")

    async def _post_json(self, path: str, payload: dict[str, Any], operation: str):
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
            self._logger.info(
                "mcp_client.response",
                operation=operation,
                path=path,
                status_code=response.status_code,
                response_summary=_summarize_payload(data),
            )
            return data
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc.response)
            self._logger.exception(
                "mcp_client.error",
                operation=operation,
                path=path,
                payload_summary=_summarize_payload(payload),
                detail=detail,
            )
            raise ValueError(detail) from exc
        except Exception:
            self._logger.exception(
                "mcp_client.error",
                operation=operation,
                path=path,
                payload_summary=_summarize_payload(payload),
            )
            raise


def _summarize_payload(value: Any) -> Any:
    if isinstance(value, list):
        return {"type": "list", "len": len(value)}
    if isinstance(value, dict):
        keys = list(value.keys())
        return {"type": "dict", "keys": keys[:10], "truncated": len(keys) > 10}
    return {"type": type(value).__name__, "value": str(value)[:200]}


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
    except Exception:
        pass
    body = response.text.strip()
    if body:
        return body[:240]
    return f"Request failed with status {response.status_code}"

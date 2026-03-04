from __future__ import annotations

import itertools
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import OverpassConfig
from app.utils.logging import get_logger

logger = get_logger(__name__)


class OverpassError(RuntimeError):
    pass


class OverpassClient:
    """Minimal Overpass API helper with retry + endpoint rotation."""

    def __init__(self, config: OverpassConfig) -> None:
        self._endpoint_list = list(config.endpoints)
        if not self._endpoint_list:
            raise ValueError("At least one Overpass endpoint is required")
        self._endpoints = itertools.cycle(self._endpoint_list)
        self._timeout = config.timeout_seconds

    async def run_query(self, query: str) -> dict[str, Any]:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(len(self._endpoint_list)),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((httpx.HTTPError, OverpassError)),
        ):
            with attempt:
                endpoint = next(self._endpoints)
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(endpoint, data={"data": query})
                    if resp.status_code >= 500:
                        raise OverpassError(f"Server error {resp.status_code}")
                    resp.raise_for_status()
                    return resp.json()
        raise OverpassError("All Overpass endpoints failed")


def build_place_query(
    *,
    lat: float,
    lon: float,
    radius_m: int,
    amenity: str = "cafe",
    brand: str | None = None,
    timeout: int = 60,
) -> str:
    """Builds a bounded Overpass QL query."""
    filters = [f'["amenity"="{amenity}"]']
    if brand:
        filters.append(f'["brand"="{brand}"]')
    filters_str = "".join(filters)
    query = f"""
[out:json][timeout:{timeout}];
node{filters_str}(around:{radius_m},{lat},{lon});
out body;
"""
    return query

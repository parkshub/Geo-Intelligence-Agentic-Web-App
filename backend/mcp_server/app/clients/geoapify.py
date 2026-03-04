from __future__ import annotations

from typing import Any

import httpx

from app.config import GeoapifyConfig
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GeoapifyClient:
    """Thin wrapper around Geoapify Places + Geocoding APIs."""

    def __init__(self, config: GeoapifyConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(base_url=config.base_url, timeout=30.0)

    async def geocode(self, query: str) -> dict[str, Any]:
        params = {
            "text": query,
            "apiKey": self._config.api_key,
            "limit": 1,
            "filter": f"countrycode:{self._config.geocode_country_code.lower()}",
        }
        response = await self._client.get("/v1/geocode/search", params=params)
        response.raise_for_status()
        data = response.json()
        if not data.get("features"):
            raise ValueError(f"No results found for '{query}'")
        feature = data["features"][0]
        coords = feature["geometry"]["coordinates"]
        return {
            "label": feature["properties"].get("formatted"),
            "lat": feature["properties"].get("lat", coords[1]),
            "lon": feature["properties"].get("lon", coords[0]),
            "postcode": feature["properties"].get("postcode"),
        }

    async def search_places(
        self,
        *,
        lat: float,
        lon: float,
        radius_m: int,
        categories: list[str] | None = None,
        name: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params = {
            "lat": lat,
            "lon": lon,
            "radius": radius_m,
            "apiKey": self._config.api_key,
            "limit": limit or self._config.default_limit,
        }
        if categories:
            params["categories"] = ",".join(categories)
        if name:
            params["name"] = name
        response = await self._client.get("/v2/places", params=params)
        response.raise_for_status()
        payload = response.json()
        return payload.get("features", [])

    async def get_place_details(self, place_id: str) -> dict[str, Any]:
        params = {"id": place_id, "apiKey": self._config.api_key}
        response = await self._client.get("/v2/place-details", params=params)
        response.raise_for_status()
        data = response.json()
        features = data.get("features") or []
        if not features:
            raise ValueError(f"No place found for id={place_id}")
        return features[0]

    async def close(self) -> None:
        await self._client.aclose()

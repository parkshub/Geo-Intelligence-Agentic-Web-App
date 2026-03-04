from __future__ import annotations

from typing import Any

import httpx

from app.config import CensusConfig


class CensusClient:
    def __init__(self, config: CensusConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(base_url=config.base_url, timeout=30.0)

    @staticmethod
    def _variables() -> list[str]:
        return [
            "NAME",
            "B01003_001E",  # total population
            "B19013_001E",  # median household income
            "B01002_001E",  # median age
            "B11001_001E",  # households
            "B15003_001E",  # education total (25+)
            "B15003_022E",  # bachelor's
            "B15003_023E",  # master's
            "B15003_024E",  # professional
            "B15003_025E",  # doctorate
            "B17001_001E",  # poverty universe
            "B17001_002E",  # below poverty
            "B02001_001E",  # race total
            "B02001_002E",  # white
            "B02001_003E",  # black
            "B02001_005E",  # asian
            "B03003_001E",  # hispanic origin total
            "B03003_003E",  # hispanic or latino
        ]

    async def _fetch(self, for_value: str, not_found_message: str) -> dict[str, Any]:
        variables = self._variables()
        params: dict[str, str] = {
            "get": ",".join(variables),
            "for": for_value,
        }
        if self._config.api_key:
            params["key"] = self._config.api_key
        path = f"/{self._config.acs_year}/acs/acs5"
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        rows = response.json()
        if not rows or len(rows) < 2:
            raise ValueError(not_found_message)
        headers = rows[0]
        values = rows[1]
        return dict(zip(headers, values))

    async def get_zip_demographics(self, zip_code: str) -> dict[str, Any]:
        return await self._fetch(
            for_value=f"zip code tabulation area:{zip_code}",
            not_found_message=f"No Census demographics found for ZIP {zip_code}",
        )

    async def get_us_demographics(self) -> dict[str, Any]:
        return await self._fetch(
            for_value="us:1",
            not_found_message="No Census demographics found for the United States",
        )

    async def close(self) -> None:
        await self._client.aclose()

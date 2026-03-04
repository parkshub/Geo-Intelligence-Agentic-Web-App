"""
Placeholder for optional Foursquare Places integration.

Foursquare's premium fields incur paid usage immediately, so this client is intentionally
left unimplemented. To enable richer venue metadata during the interview demo, provide an
API key via MCP_FOURSQUARE__API_KEY and implement the minimal GET calls inside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FoursquareConfig:
    api_key: str


class FoursquareClient:
    def __init__(self, config: FoursquareConfig) -> None:
        self._config = config

    async def search(self, **_: Any) -> list[dict[str, Any]]:  # pragma: no cover - stub
        raise NotImplementedError(
            "Enable Foursquare integration by implementing search() with the curated endpoints."
        )

from __future__ import annotations

from typing import Any

from langchain_core.pydantic_v1 import BaseModel, Field, root_validator
from langchain_core.tools import StructuredTool

from app.services.mcp_client import MCPClient


class GeocodeInput(BaseModel):
    query: str = Field(description="Human friendly location like ZIP code, neighborhood, or address")


class SearchPlacesInput(BaseModel):
    location: str = Field(description="ZIP code or city to center the search on")
    lat: float | None = Field(default=None, description="Optional latitude override")
    lon: float | None = Field(default=None, description="Optional longitude override")
    radius_m: int = Field(default=2000, description="Radius in meters for the search")
    categories: str = Field(
        default="",
        description="Optional comma-separated Geoapify category filters",
    )
    brand: str | None = Field(default=None, description="Brand filter such as Starbucks")


class ProfileAreaInput(BaseModel):
    location: str
    radius_m: int = 2000
    categories: str = Field(
        default="",
        description="Optional comma-separated category intent such as restaurant, cafe, bakery, supermarket",
    )
    brand: str | None = Field(default=None)


class CompareAreasInput(BaseModel):
    area_a: str
    area_b: str
    radius_m: int = 2000
    categories: str = Field(
        default="",
        description="Optional comma-separated category intent for both areas",
    )
    brand: str | None = Field(default=None)


class DemographicsInput(BaseModel):
    zip_code: str | None = Field(default=None, description="5-digit US ZIP code")
    location: str | None = Field(
        default=None,
        description="Optional fallback location string when zip_code is not provided",
    )

    @root_validator
    def validate_zip_or_location(cls, values):
        if not values.get("zip_code") and not values.get("location"):
            raise ValueError("Either zip_code or location must be provided")
        return values

    class Config:
        @staticmethod
        def schema_extra(schema: dict[str, Any], model) -> None:
            # langchain_google_genai expects "required" to exist.
            schema.setdefault("required", [])


class DemographicsCompareInput(BaseModel):
    queries: str = Field(
        description="Comma-separated ZIP codes or location strings to compare demographics",
    )


class IndustryResearchInput(BaseModel):
    location: str = Field(description="ZIP code, city, or address to analyze industries around")
    radius_m: int = Field(default=3000, description="Search radius in meters")
    top_n: int = Field(default=8, description="Number of top industries to return")


def build_tools(client: MCPClient) -> list[StructuredTool]:
    def _parse_categories(value: Any) -> list[str]:
        if isinstance(value, str):
            return [c.strip() for c in value.split(",") if c.strip()]
        return []

    async def _geocode(query: str):
        return await client.geocode(query)

    async def _search(**kwargs: Any):
        payload = dict(kwargs)
        categories = payload.get("categories")
        if isinstance(categories, str):
            payload["categories"] = [c.strip() for c in categories.split(",") if c.strip()]
        return await client.search_places(payload)

    async def _profile(**kwargs: Any):
        payload = {
            "location": kwargs["location"],
            "radius_m": kwargs.get("radius_m", 2000),
            "categories": _parse_categories(kwargs.get("categories")),
            "brand": kwargs.get("brand"),
        }
        return await client.profile_area(payload)

    async def _compare(**kwargs: Any):
        payload = {
            "area_a": kwargs["area_a"],
            "area_b": kwargs["area_b"],
            "radius_m": kwargs.get("radius_m", 2000),
            "categories": _parse_categories(kwargs.get("categories")),
            "focus_brand": kwargs.get("brand"),
        }
        return await client.compare_areas(payload)

    async def _demographics(**kwargs: Any):
        payload = {
            "zip_code": kwargs.get("zip_code"),
            "location": kwargs.get("location"),
        }
        return await client.demographics_profile(payload)

    async def _demographics_compare(**kwargs: Any):
        queries = kwargs.get("queries", "")
        if isinstance(queries, str):
            parsed = [q.strip() for q in queries.split(",") if q.strip()]
        else:
            parsed = []
        return await client.demographics_compare({"queries": parsed})

    async def _industry_research(**kwargs: Any):
        payload = {
            "location": kwargs.get("location"),
            "radius_m": kwargs.get("radius_m", 3000),
            "top_n": kwargs.get("top_n", 8),
        }
        return await client.industry_research(payload)

    return [
        StructuredTool.from_function(
            coroutine=_geocode,
            name="geocode_location",
            description="Resolve a free-form location string into latitude and longitude",
            args_schema=GeocodeInput,
        ),
        StructuredTool.from_function(
            coroutine=_search,
            name="search_places",
            description=(
                "Search for raw place listings within a radius when the user explicitly asks "
                "for a list. Requires a clear location in the input."
            ),
            args_schema=SearchPlacesInput,
        ),
        StructuredTool.from_function(
            coroutine=_profile,
            name="summarize_area",
            description=(
                "Compute area competition metrics and return top competitors with coordinates. "
                "Preferred for map-like requests for a single location."
            ),
            args_schema=ProfileAreaInput,
        ),
        StructuredTool.from_function(
            coroutine=_compare,
            name="compare_areas",
            description=(
                "Compare two locations for campaign focus and return map-ready profiles for both areas."
            ),
            args_schema=CompareAreasInput,
        ),
        StructuredTool.from_function(
            coroutine=_demographics,
            name="get_demographics",
            description=(
                "Fetch Census demographics by ZIP or location. "
                "Use this when the user asks for demographics data or a demographics graph for one place."
            ),
            args_schema=DemographicsInput,
        ),
        StructuredTool.from_function(
            coroutine=_demographics_compare,
            name="compare_demographics",
            description=(
                "Compare demographics across multiple ZIP codes or locations. "
                "Use this when the user requests demographics graphs/charts for two or more places."
            ),
            args_schema=DemographicsCompareInput,
        ),
        StructuredTool.from_function(
            coroutine=_industry_research,
            name="analyze_industries",
            description="Rank top industries in an area using Geoapify place categories",
            args_schema=IndustryResearchInput,
        ),
    ]

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GeoapifyConfig(BaseModel):
    api_key: str = Field(default="", description="Geoapify API key")
    base_url: str = Field(default="https://api.geoapify.com", description="Geoapify API base URL")
    geocode_country_code: str = Field(
        default="us",
        description="Restrict geocoding results to this country code",
    )
    default_limit: int = Field(default=50, description="Default number of POIs to fetch")
    min_remaining_credits: int = Field(
        default=100,
        description="Minimum estimated credits to keep as buffer before throttling",
    )


class OverpassConfig(BaseModel):
    endpoints: list[str] = Field(
        default_factory=lambda: [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.openstreetmap.fr/api/interpreter",
        ]
    )
    timeout_seconds: int = 60
    radius_limit_m: int = 5000


class CensusConfig(BaseModel):
    api_key: str | None = Field(default=None, description="Census API key (optional but recommended)")
    base_url: str = Field(default="https://api.census.gov/data", description="Census API base URL")
    acs_year: int = Field(default=2023, description="ACS 5-year dataset year")


LLMProvider = Literal["openai", "openrouter", "anthropic", "google", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", env_prefix="MCP_")

    environment: Literal["local", "staging", "production"] = "local"
    geoapify: GeoapifyConfig = Field(default_factory=GeoapifyConfig)
    overpass: OverpassConfig = Field(default_factory=OverpassConfig)
    census: CensusConfig = Field(default_factory=CensusConfig)
    redis_url: str | None = Field(default=None)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

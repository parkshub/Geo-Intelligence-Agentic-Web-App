from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["openai", "openrouter", "anthropic", "google", "ollama"]


class MCPConfig(BaseModel):
    base_url: str = Field(default="http://localhost:8001", description="Base URL for MCP server")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENT_", env_nested_delimiter="__")

    environment: Literal["local", "staging", "production"] = "local"
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    llm_provider: LLMProvider = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

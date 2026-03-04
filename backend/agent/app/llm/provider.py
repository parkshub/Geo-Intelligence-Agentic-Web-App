from __future__ import annotations

import os
from typing import Mapping

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import LLMProvider, get_settings


def _build_openai(model: str, api_key: str | None, base_url: str | None) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url,
        temperature=0.1,
    )


def _build_anthropic(model: str, api_key: str | None) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=model, api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"), temperature=0.1)


def _build_google(model: str, api_key: str | None) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key or os.environ.get("GOOGLE_API_KEY"),
        temperature=0.1,
        convert_system_message_to_human=True,
    )


def _build_ollama(model: str, base_url: str | None) -> BaseChatModel:
    from langchain_community.chat_models import ChatOllama

    return ChatOllama(model=model, base_url=base_url or "http://localhost:11434", temperature=0.1)


def build_chat_model(overrides: Mapping[str, str | None] | None = None) -> BaseChatModel:
    settings = get_settings()
    provider: LLMProvider = overrides.get("provider") if overrides else settings.llm_provider
    model_name = overrides.get("model") if overrides else settings.llm_model
    api_key = overrides.get("api_key") if overrides else settings.llm_api_key
    base_url = overrides.get("base_url") if overrides else settings.llm_base_url

    if provider in {"openai", "openrouter"}:
        # OpenRouter is OpenAI-compatible; base_url expected via overrides
        return _build_openai(model_name, api_key, base_url)
    if provider == "anthropic":
        return _build_anthropic(model_name, api_key)
    if provider == "google":
        return _build_google(model_name, api_key)
    if provider == "ollama":
        return _build_ollama(model_name, base_url)
    raise ValueError(f"Unsupported provider {provider}")

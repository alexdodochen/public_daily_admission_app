from __future__ import annotations

from .. import config as appconfig
from .base import LLMClient, extract_json


def get_llm() -> LLMClient:
    """Build an LLM client from the user's saved config. Raises if not ready."""
    cfg = appconfig.load()
    if not cfg.llm_provider or not cfg.llm_api_key:
        raise RuntimeError("尚未設定 LLM provider — 請先到「設定」頁填入 API key")

    p = cfg.llm_provider.lower()
    if p == "anthropic":
        from .anthropic_provider import AnthropicClient
        return AnthropicClient(cfg.llm_api_key, cfg.llm_model)
    if p == "openai":
        from .openai_provider import OpenAIClient
        return OpenAIClient(cfg.llm_api_key, cfg.llm_model)
    if p == "gemini":
        from .gemini_provider import GeminiClient
        return GeminiClient(cfg.llm_api_key, cfg.llm_model)
    raise RuntimeError(f"未知的 LLM provider: {cfg.llm_provider}")


PROVIDERS = [
    {"id": "anthropic", "label": "Claude (Anthropic)",
     "help": "https://console.anthropic.com/ → API Keys",
     "default_model": "claude-sonnet-4-6"},
    {"id": "openai",    "label": "ChatGPT (OpenAI)",
     "help": "https://platform.openai.com/api-keys",
     "default_model": "gpt-4o"},
    {"id": "gemini",    "label": "Gemini (Google)",
     "help": "https://aistudio.google.com/app/apikey",
     "default_model": "gemini-2.0-flash"},
]

__all__ = ["get_llm", "LLMClient", "extract_json", "PROVIDERS"]

from app.llm.provider import LLMProvider
from app.llm.universal_provider import UniversalProvider
from app.llm.fake import FakeLLMProvider
from app.config import settings

# Backwards-compatibility alias — existing code that imports LiteLLMProvider still works
LiteLLMProvider = UniversalProvider


def build_llm_provider() -> UniversalProvider:
    """Factory: build the production LLM provider from settings."""
    return UniversalProvider(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_retries=settings.llm_max_retries,
    )


__all__ = ["LLMProvider", "UniversalProvider", "LiteLLMProvider", "FakeLLMProvider", "build_llm_provider"]

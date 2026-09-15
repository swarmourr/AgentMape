from app.llm.provider import LLMProvider
from app.llm.litellm_provider import LiteLLMProvider
from app.llm.fake import FakeLLMProvider
from app.config import settings


def build_llm_provider() -> LiteLLMProvider:
    """Factory: build the production LLM provider from settings."""
    return LiteLLMProvider(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_retries=settings.llm_max_retries,
    )


__all__ = ["LLMProvider", "LiteLLMProvider", "FakeLLMProvider", "build_llm_provider"]

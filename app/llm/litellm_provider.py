from __future__ import annotations

from typing import Any

import instructor
import litellm
from pydantic import BaseModel

# Suppress litellm's verbose default logging
litellm.suppress_debug_info = True

# Ollama model prefixes recognised for auto-mode detection
_OLLAMA_PREFIXES = ("ollama/", "ollama_chat/")


def _pick_instructor_mode(model: str, base_url: str | None) -> instructor.Mode:
    """
    Choose the instructor structured-output mode for a given model/endpoint.

    Ollama models use JSON mode — they accept a json_schema response_format
    but not OpenAI-style function/tool definitions.  All cloud providers
    (OpenAI, Anthropic, Azure, Bedrock, …) use TOOLS mode which gives the
    best reliability with instructor's retry logic.
    """
    is_ollama = model.startswith(_OLLAMA_PREFIXES) or (
        base_url is not None and ":11434" in base_url
    )
    return instructor.Mode.JSON if is_ollama else instructor.Mode.TOOLS


class LiteLLMProvider:
    """
    Production LLM provider backed by LiteLLM + instructor.

    LiteLLM normalises every provider (OpenAI, Anthropic, Azure OpenAI,
    AWS Bedrock, Vertex AI, Ollama, vLLM, …) behind a single call
    signature.  instructor patches the client to guarantee that the
    response is parsed into the requested Pydantic model.

    Configuration (environment variables):
        LLM_MODEL      — provider-prefixed model name
                          Cloud :  "gpt-4o"  |  "anthropic/claude-opus-4-6"
                                   "azure/gpt-4o"  |  "bedrock/..."
                          Local :  "ollama/llama3.3:70b"
                                   "ollama/qwen2.5:72b"
        LLM_API_KEY    — API key (not needed for Ollama)
        LLM_BASE_URL   — endpoint override
                          Ollama default: http://localhost:11434

    Provider keys are also read automatically from the environment by
    LiteLLM (OPENAI_API_KEY, ANTHROPIC_API_KEY, AZURE_API_KEY, …).

    Instructor mode is chosen automatically:
        Ollama  → instructor.Mode.JSON  (JSON schema in response_format)
        Others  → instructor.Mode.TOOLS (function/tool definitions)
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._max_retries = max_retries
        mode = _pick_instructor_mode(model, base_url)
        self._client = instructor.from_litellm(litellm.acompletion, mode=mode)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> BaseModel:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "response_model": response_model,
            "temperature": temperature,
            "max_retries": self._max_retries,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url

        return await self._client.create(**kwargs)

    @property
    def model(self) -> str:
        return self._model

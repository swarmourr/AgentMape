"""
Ollama LLM backend for local inference
"""
import requests
import logging
from typing import Dict, Any
from .base import LLMBackend

logger = logging.getLogger(__name__)


class OllamaBackend(LLMBackend):
    """Ollama backend for local LLM inference"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama backend

        Args:
            config: Configuration with keys: host, model, temperature, timeout, max_tokens
        """
        super().__init__(config)
        self.host = config.get('host', 'http://localhost:11434')
        self.model = config.get('model', 'llama3.3:latest')
        self.temperature = config.get('temperature', 0.1)
        self.timeout = config.get('timeout', 60)
        self.max_tokens = config.get('max_tokens', 4000)

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text using Ollama API

        Args:
            prompt: Input prompt
            **kwargs: Override default parameters (temperature, max_tokens, etc.)

        Returns:
            Generated text
        """
        # Build request
        url = f"{self.host}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get('temperature', self.temperature),
                "num_predict": kwargs.get('max_tokens', self.max_tokens)
            }
        }

        try:
            logger.debug(f"Sending request to Ollama: {self.host}")
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            generated_text = result.get('response', '')

            logger.debug(f"Received response from Ollama ({len(generated_text)} chars)")
            return generated_text

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise RuntimeError(f"Failed to generate from Ollama: {e}")

    def is_available(self) -> bool:
        """
        Check if Ollama is running and model is available

        Returns:
            True if Ollama is accessible
        """
        try:
            # Check if Ollama is running
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            response.raise_for_status()

            # Check if our model is available
            models = response.json().get('models', [])
            model_names = [m.get('name', '') for m in models]

            if self.model in model_names:
                logger.info(f"Ollama is available with model {self.model}")
                return True
            else:
                logger.warning(f"Ollama is running but model {self.model} not found")
                logger.info(f"Available models: {model_names}")
                return False

        except requests.exceptions.RequestException as e:
            logger.warning(f"Ollama not available: {e}")
            return False

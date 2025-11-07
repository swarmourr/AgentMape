"""
Base class for LLM backends
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class LLMBackend(ABC):
    """Abstract base class for LLM backends"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM backend

        Args:
            config: Configuration dictionary for the backend
        """
        self.config = config

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text from prompt

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the LLM backend is available

        Returns:
            True if backend is accessible, False otherwise
        """
        pass

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate JSON response from prompt

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters

        Returns:
            Parsed JSON response as dictionary
        """
        import json
        response = self.generate(prompt, **kwargs)

        # Try to extract JSON from response
        try:
            # Try direct parsing
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON in markdown code blocks
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))

            # Try to find JSON object
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))

            raise ValueError(f"Could not extract valid JSON from response: {response[:200]}")

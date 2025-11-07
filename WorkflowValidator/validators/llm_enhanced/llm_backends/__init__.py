"""
LLM backend implementations - Ollama only
"""
from .base import LLMBackend
from .ollama_backend import OllamaBackend

__all__ = ['LLMBackend', 'OllamaBackend']

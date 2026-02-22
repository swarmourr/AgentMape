#!/usr/bin/env python3
"""
Integration helper for Analyzer Agent
Wraps LLM calls to automatically log interactions
"""

import time
import logging
from typing import Dict, Any, Optional
from interaction_logger import get_interaction_logger

logger = logging.getLogger(__name__)


class AnalyzerLoggerMixin:
    """
    Mixin class to add interaction logging to Analyzer Agent
    Add this to your EnhancedAnalyzerAgent class
    """

    def __init_interaction_logger__(self):
        """Initialize the interaction logger - call this in __init__"""
        self.interaction_logger = get_interaction_logger()
        logger.info("Analyzer interaction logging enabled")

    def _log_llm_analysis_request(
        self,
        workflow_id: str,
        analysis_type: str,
        prompt: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Log LLM analysis request

        Args:
            workflow_id: Workflow ID being analyzed
            analysis_type: Type of analysis (held, failed, etc.)
            prompt: The prompt being sent to LLM
            metadata: Additional metadata

        Returns:
            interaction_id: ID to use when logging response
        """
        meta = metadata or {}
        meta.update({
            "analysis_type": analysis_type,
            "ollama_model": self.ollama_manager.ollama_model,
            "ollama_url": self.ollama_manager.ollama_api_base
        })

        return self.interaction_logger.log_llm_request(
            agent="Analyzer",
            interaction_type=f"workflow_analysis_{analysis_type}",
            prompt=prompt,
            workflow_id=workflow_id,
            metadata=meta
        )

    def _log_llm_analysis_response(
        self,
        interaction_id: str,
        response: str,
        success: bool,
        latency_ms: float,
        error: str = None,
        parsed_result: Dict[str, Any] = None
    ):
        """
        Log LLM analysis response

        Args:
            interaction_id: ID from _log_llm_analysis_request
            response: LLM response text
            success: Whether the request succeeded
            latency_ms: Request latency
            error: Error message if failed
            parsed_result: Parsed analysis result
        """
        self.interaction_logger.log_llm_response(
            interaction_id=interaction_id,
            response=response,
            success=success,
            error=error,
            latency_ms=latency_ms,
            parsed_data=parsed_result
        )

    def _log_analyzer_action(
        self,
        action_type: str,
        description: str,
        workflow_id: str = None,
        metadata: Dict[str, Any] = None
    ):
        """
        Log a non-LLM analyzer action

        Args:
            action_type: Type of action
            description: Action description
            workflow_id: Associated workflow ID
            metadata: Additional metadata
        """
        self.interaction_logger.log_agent_action(
            agent="Analyzer",
            action_type=action_type,
            description=description,
            workflow_id=workflow_id,
            metadata=metadata
        )


def wrap_llm_call_with_logging(original_method):
    """
    Decorator to wrap LLM calls with automatic logging

    Usage:
        @wrap_llm_call_with_logging
        def call_llm_for_analysis(self, prompt, workflow_id, analysis_type):
            # Your existing code
            response = requests.post(...)
            return response
    """
    def wrapper(self, prompt: str, workflow_id: str, analysis_type: str = "general", **kwargs):
        # Log request
        start_time = time.time()

        interaction_id = self.interaction_logger.log_llm_request(
            agent="Analyzer",
            interaction_type=f"workflow_analysis_{analysis_type}",
            prompt=prompt,
            workflow_id=workflow_id,
            metadata={
                "method": original_method.__name__,
                **kwargs
            }
        )

        try:
            # Call original method
            response = original_method(self, prompt, workflow_id, analysis_type, **kwargs)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Log successful response
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=str(response),
                success=True,
                latency_ms=latency_ms
            )

            return response

        except Exception as e:
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Log failed response
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=None,
                success=False,
                error=str(e),
                latency_ms=latency_ms
            )

            raise

    return wrapper


# === USAGE EXAMPLE ===
"""
To integrate into your Analyzer agent:

1. Add the mixin to your class:

class EnhancedAnalyzerAgent(AnalyzerLoggerMixin):
    def __init__(self, ...):
        # Your existing init code
        ...

        # Add this line
        self.__init_interaction_logger__()

2. In your LLM calling code (around line 1250-1324 in analyzer_rest.py):

    # BEFORE sending to LLM:
    interaction_id = self._log_llm_analysis_request(
        workflow_id=workflow_id,
        analysis_type="held",  # or "failed"
        prompt=prompt,
        metadata={"attempt": attempt + 1, "max_retries": max_retries}
    )

    start_time = time.time()

    # Your existing LLM call
    response = requests.post(
        self.ollama_manager.ollama_url,
        json=payload,
        timeout=generation_timeout
    )

    latency_ms = (time.time() - start_time) * 1000

    # AFTER receiving response:
    if response.status_code == 200:
        ollama_response = response.json()
        response_text = ollama_response.get('response', '').strip()

        # Parse the response
        parsed_result = self.extract_workflow_info_enhanced(ollama_response)

        # Log success
        self._log_llm_analysis_response(
            interaction_id=interaction_id,
            response=response_text,
            success=True,
            latency_ms=latency_ms,
            parsed_result=parsed_result
        )
    else:
        # Log failure
        self._log_llm_analysis_response(
            interaction_id=interaction_id,
            response=None,
            success=False,
            latency_ms=latency_ms,
            error=f"HTTP {response.status_code}"
        )

3. For non-LLM actions (optional):

    self._log_analyzer_action(
        action_type="file_analysis",
        description="Analyzing stderr output files",
        workflow_id=workflow_id,
        metadata={"file_count": len(stderr_files)}
    )
"""

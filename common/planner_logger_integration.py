#!/usr/bin/env python3
"""
Integration helper for Planner Agent
Wraps LLM calls to automatically log interactions
"""

import time
import logging
from typing import Dict, Any, Optional
from interaction_logger import get_interaction_logger

logger = logging.getLogger(__name__)


class PlannerLoggerMixin:
    """
    Mixin class to add interaction logging to Planner Agent
    Add this to your PlannerAgent class
    """

    def __init_interaction_logger__(self):
        """Initialize the interaction logger - call this in __init__"""
        self.interaction_logger = get_interaction_logger()
        logger.info("Planner interaction logging enabled")

    def _log_llm_plan_request(
        self,
        workflow_id: str,
        stage: str,
        prompt: str,
        parent_interaction_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Log LLM plan generation request

        Args:
            workflow_id: Workflow ID being planned for
            stage: Planning stage (single_stage, stage1, stage2, stage3)
            prompt: The prompt being sent to LLM
            parent_interaction_id: Parent interaction for multi-stage
            metadata: Additional metadata

        Returns:
            interaction_id: ID to use when logging response
        """
        meta = metadata or {}
        meta.update({
            "stage": stage,
            "ollama_model": getattr(self.ollama_manager, 'ollama_model', 'unknown'),
            "ollama_url": getattr(self.ollama_manager, 'ollama_api_base', 'unknown')
        })

        return self.interaction_logger.log_llm_request(
            agent="Planner",
            interaction_type=f"plan_generation_{stage}",
            prompt=prompt,
            workflow_id=workflow_id,
            parent_interaction_id=parent_interaction_id,
            metadata=meta
        )

    def _log_llm_plan_response(
        self,
        interaction_id: str,
        response: str,
        success: bool,
        latency_ms: float,
        error: str = None,
        parsed_plan: Dict[str, Any] = None
    ):
        """
        Log LLM plan generation response

        Args:
            interaction_id: ID from _log_llm_plan_request
            response: LLM response text
            success: Whether the request succeeded
            latency_ms: Request latency
            error: Error message if failed
            parsed_plan: Parsed plan result
        """
        self.interaction_logger.log_llm_response(
            interaction_id=interaction_id,
            response=response,
            success=success,
            error=error,
            latency_ms=latency_ms,
            parsed_data=parsed_plan
        )

    def _log_planner_action(
        self,
        action_type: str,
        description: str,
        workflow_id: str = None,
        parent_interaction_id: str = None,
        metadata: Dict[str, Any] = None
    ):
        """
        Log a non-LLM planner action

        Args:
            action_type: Type of action (file_fetch, validation, etc.)
            description: Action description
            workflow_id: Associated workflow ID
            parent_interaction_id: Parent interaction ID
            metadata: Additional metadata
        """
        self.interaction_logger.log_agent_action(
            agent="Planner",
            action_type=action_type,
            description=description,
            workflow_id=workflow_id,
            parent_interaction_id=parent_interaction_id,
            metadata=metadata
        )


# === USAGE EXAMPLE ===
"""
To integrate into your Planner agent:

1. Add the mixin to your class:

class PlannerAgent(PlannerLoggerMixin):
    def __init__(self, ...):
        # Your existing init code
        ...

        # Add this line
        self.__init_interaction_logger__()

2. For single-stage planning (around line 1265 in planner_rest.py):

    async def generate_plan_with_llm(self, ...):
        workflow_id = workflow_context.get('workflow_id')

        # Build prompt
        prompt = self.prompt_builder.build_planner_prompt(...)

        # LOG REQUEST
        interaction_id = self._log_llm_plan_request(
            workflow_id=workflow_id,
            stage="single_stage",
            prompt=prompt,
            metadata={
                "additional_files_count": len(additional_files) if additional_files else 0,
                "catalogs_provided": list(catalogs.keys())
            }
        )

        # Call LLM
        start_time = time.time()
        llm_response = self.ollama_manager.call_llm(prompt, self.prompt_builder.SYSTEM_PROMPT)
        latency_ms = (time.time() - start_time) * 1000

        if llm_response:
            try:
                # Parse LLM output
                plan = self.parse_llm_response(llm_response)

                # LOG SUCCESS
                self._log_llm_plan_response(
                    interaction_id=interaction_id,
                    response=str(llm_response),
                    success=True,
                    latency_ms=latency_ms,
                    parsed_plan=plan
                )

                return plan

            except Exception as e:
                # LOG FAILURE
                self._log_llm_plan_response(
                    interaction_id=interaction_id,
                    response=str(llm_response),
                    success=False,
                    latency_ms=latency_ms,
                    error=str(e)
                )
                raise
        else:
            # LOG FAILURE
            self._log_llm_plan_response(
                interaction_id=interaction_id,
                response=None,
                success=False,
                latency_ms=latency_ms,
                error="LLM not available"
            )


3. For multi-stage planning (around line 1302-1341 in planner_rest.py):

    async def generate_plan_multi_stage(self, ...):
        workflow_id = workflow_context.get('workflow_id')

        # ===== STAGE 1: Identify Required Files =====
        stage1_prompt = self._build_file_identification_prompt(...)

        # LOG STAGE 1 REQUEST
        parent_id = None  # First stage has no parent
        stage1_id = self._log_llm_plan_request(
            workflow_id=workflow_id,
            stage="stage1_file_identification",
            prompt=stage1_prompt,
            parent_interaction_id=parent_id
        )

        start_time = time.time()
        stage1_response = self.ollama_manager.call_llm(stage1_prompt, ...)
        latency_ms = (time.time() - start_time) * 1000

        # Parse files needed
        files_needed = self._parse_files_needed(stage1_response)

        # LOG STAGE 1 RESPONSE
        self._log_llm_plan_response(
            interaction_id=stage1_id,
            response=stage1_response,
            success=True,
            latency_ms=latency_ms,
            parsed_plan={"files_needed": files_needed}
        )

        # LOG FILE FETCHING ACTION
        self._log_planner_action(
            action_type="file_fetch",
            description=f"Fetching {len(files_needed)} files identified by LLM",
            workflow_id=workflow_id,
            parent_interaction_id=stage1_id,
            metadata={"files": files_needed}
        )

        # Fetch files...
        fetched_files = await self._fetch_files(files_needed, workflow_id)

        # ===== STAGE 2/3: Generate Plan with Files =====
        stage2_prompt = self._build_plan_with_files_prompt(...)

        # LOG STAGE 2 REQUEST (parent is stage1)
        stage2_id = self._log_llm_plan_request(
            workflow_id=workflow_id,
            stage="stage2_plan_generation",
            prompt=stage2_prompt,
            parent_interaction_id=stage1_id,  # Link to stage 1
            metadata={"fetched_files_count": len(fetched_files)}
        )

        start_time = time.time()
        stage2_response = self.ollama_manager.call_llm(stage2_prompt, ...)
        latency_ms = (time.time() - start_time) * 1000

        # Parse plan
        plan = self.parse_llm_response(stage2_response)

        # LOG STAGE 2 RESPONSE
        self._log_llm_plan_response(
            interaction_id=stage2_id,
            response=stage2_response,
            success=True,
            latency_ms=latency_ms,
            parsed_plan=plan
        )

        return plan


4. For plan validation actions:

    self._log_planner_action(
        action_type="plan_validation",
        description=f"Validating generated plan with {len(plan.get('actions', []))} actions",
        workflow_id=workflow_id,
        metadata={
            "validation_passed": validation_result.get('valid', False),
            "validation_errors": validation_result.get('errors', [])
        }
    )
"""

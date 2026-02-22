#!/usr/bin/env python3
"""
Planner Agent - LLM Interaction Logger
Integrated with existing planner_db.json
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PlannerInteractionLogger:
    """
    Logger for Planner's LLM interactions
    Uses existing TinyDB instance and database
    """

    def __init__(self, db_instance):
        """
        Initialize with existing TinyDB instance

        Args:
            db_instance: The TinyDB instance from PlannerAgent
        """
        self.db = db_instance
        self.llm_interactions = self.db.table('llm_interactions')
        logger.info("Planner interaction logging initialized")

    def log_llm_request(
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
            workflow_id: Workflow being planned for
            stage: Planning stage (single_stage, stage1, stage2, etc.)
            prompt: Prompt sent to LLM
            parent_interaction_id: Parent interaction for multi-stage
            metadata: Additional metadata

        Returns:
            interaction_id: Unique ID for this interaction
        """
        interaction_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        record = {
            "interaction_id": interaction_id,
            "parent_interaction_id": parent_interaction_id,
            "timestamp": timestamp,
            "agent": "Planner",
            "workflow_id": workflow_id,
            "stage": stage,
            "direction": "request",
            "prompt": prompt,
            "prompt_length": len(prompt),
            "metadata": metadata or {},
            "response": None,
            "response_length": None,
            "latency_ms": None,
            "success": None,
            "error": None,
            "completed_at": None,
            "parsed_plan": None
        }

        self.llm_interactions.insert(record)
        logger.debug(f"Logged LLM request: {interaction_id} for workflow {workflow_id} (stage: {stage})")

        return interaction_id

    def log_llm_response(
        self,
        interaction_id: str,
        response: str,
        success: bool,
        latency_ms: float,
        error: str = None,
        parsed_plan: Dict[str, Any] = None
    ):
        """
        Update interaction with LLM response

        Args:
            interaction_id: ID from log_llm_request
            response: LLM response text
            success: Whether successful
            latency_ms: Request latency
            error: Error message if failed
            parsed_plan: Parsed plan result
        """
        from tinydb import Query
        Query_ = Query()

        completed_at = datetime.now().isoformat()

        update_data = {
            "response": response,
            "response_length": len(response) if response else 0,
            "success": success,
            "error": error,
            "latency_ms": latency_ms,
            "completed_at": completed_at,
            "parsed_plan": parsed_plan
        }

        self.llm_interactions.update(update_data, Query_.interaction_id == interaction_id)
        logger.debug(f"Logged LLM response: {interaction_id} (success={success})")

    def log_action(
        self,
        action_type: str,
        description: str,
        workflow_id: str = None,
        parent_interaction_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Log a non-LLM planner action (e.g., file fetching, validation)

        Args:
            action_type: Type of action
            description: Action description
            workflow_id: Associated workflow ID
            parent_interaction_id: Parent interaction ID
            metadata: Additional metadata

        Returns:
            interaction_id: Unique ID for this action
        """
        interaction_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        record = {
            "interaction_id": interaction_id,
            "parent_interaction_id": parent_interaction_id,
            "timestamp": timestamp,
            "agent": "Planner",
            "workflow_id": workflow_id,
            "action_type": action_type,
            "direction": "action",
            "description": description,
            "metadata": metadata or {},
            "success": True,
            "completed_at": timestamp
        }

        self.llm_interactions.insert(record)
        logger.debug(f"Logged action: {interaction_id} - {action_type}")

        return interaction_id

    def get_workflow_interactions(self, workflow_id: str) -> list:
        """
        Get all interactions for a workflow

        Args:
            workflow_id: Workflow ID

        Returns:
            List of interactions sorted by timestamp
        """
        from tinydb import Query
        Query_ = Query()

        interactions = self.llm_interactions.search(Query_.workflow_id == workflow_id)
        interactions.sort(key=lambda x: x.get('timestamp', ''))

        return interactions

    def get_latest_interaction(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest interaction for a workflow
        Important: When same workflow_id appears multiple times, return most recent

        Args:
            workflow_id: Workflow ID

        Returns:
            Latest interaction or None
        """
        interactions = self.get_workflow_interactions(workflow_id)
        return interactions[-1] if interactions else None

    def get_all_interactions(self, limit: int = 100) -> list:
        """
        Get all interactions sorted by timestamp (most recent first)

        Args:
            limit: Maximum number to return

        Returns:
            List of interactions
        """
        all_interactions = self.llm_interactions.all()
        all_interactions.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return all_interactions[:limit]

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about logged interactions

        Returns:
            Statistics dictionary
        """
        all_interactions = self.llm_interactions.all()

        # Filter out actions for success rate
        llm_only = [i for i in all_interactions if i.get('direction') != 'action']

        total_count = len(llm_only)
        successful = len([i for i in llm_only if i.get('success') is True])
        failed = len([i for i in llm_only if i.get('success') is False])

        # Latency stats
        latencies = [i.get('latency_ms') for i in llm_only if i.get('latency_ms')]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Stage breakdown
        stages = {}
        for interaction in llm_only:
            stage = interaction.get('stage', 'unknown')
            stages[stage] = stages.get(stage, 0) + 1

        return {
            "agent": "Planner",
            "total_interactions": total_count,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total_count * 100) if total_count > 0 else 0,
            "average_latency_ms": round(avg_latency, 2),
            "by_stage": stages,
            "unique_workflows": len(set([i.get('workflow_id') for i in all_interactions if i.get('workflow_id')]))
        }

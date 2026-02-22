#!/usr/bin/env python3
"""
Analyzer Agent - LLM Interaction Logger
Integrated with existing analyzer_agent_db.json
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AnalyzerInteractionLogger:
    """
    Logger for Analyzer's LLM interactions
    Uses existing TinyDB instance and database
    """

    def __init__(self, db_instance):
        """
        Initialize with existing TinyDB instance

        Args:
            db_instance: The TinyDB instance from EnhancedAnalyzerAgent
        """
        self.db = db_instance
        self.llm_interactions = self.db.table('llm_interactions')
        logger.info("Analyzer interaction logging initialized")

    def log_llm_request(
        self,
        workflow_id: str,
        analysis_type: str,
        prompt: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Log LLM analysis request

        Args:
            workflow_id: Workflow being analyzed
            analysis_type: Type (held, failed, etc.)
            prompt: Prompt sent to LLM
            metadata: Additional metadata

        Returns:
            interaction_id: Unique ID for this interaction
        """
        interaction_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        record = {
            "interaction_id": interaction_id,
            "timestamp": timestamp,
            "agent": "Analyzer",
            "workflow_id": workflow_id,
            "analysis_type": analysis_type,
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
            "parsed_result": None
        }

        self.llm_interactions.insert(record)
        logger.debug(f"Logged LLM request: {interaction_id} for workflow {workflow_id}")

        return interaction_id

    def log_llm_response(
        self,
        interaction_id: str,
        response: str,
        success: bool,
        latency_ms: float,
        error: str = None,
        parsed_result: Dict[str, Any] = None
    ):
        """
        Update interaction with LLM response

        Args:
            interaction_id: ID from log_llm_request
            response: LLM response text
            success: Whether successful
            latency_ms: Request latency
            error: Error message if failed
            parsed_result: Parsed analysis result
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
            "parsed_result": parsed_result
        }

        self.llm_interactions.update(update_data, Query_.interaction_id == interaction_id)
        logger.debug(f"Logged LLM response: {interaction_id} (success={success})")

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

        total_count = len(all_interactions)
        successful = len([i for i in all_interactions if i.get('success') is True])
        failed = len([i for i in all_interactions if i.get('success') is False])

        # Latency stats
        latencies = [i.get('latency_ms') for i in all_interactions if i.get('latency_ms')]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Analysis type breakdown
        types = {}
        for interaction in all_interactions:
            atype = interaction.get('analysis_type', 'unknown')
            types[atype] = types.get(atype, 0) + 1

        return {
            "agent": "Analyzer",
            "total_interactions": total_count,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total_count * 100) if total_count > 0 else 0,
            "average_latency_ms": round(avg_latency, 2),
            "by_type": types,
            "unique_workflows": len(set([i.get('workflow_id') for i in all_interactions if i.get('workflow_id')]))
        }

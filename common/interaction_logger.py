#!/usr/bin/env python3
"""
Centralized LLM Interaction Logger
Logs all interactions between agents and LLM with timestamps
Accessible via API for web dashboard chat interface
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from tinydb import TinyDB, Query
from pathlib import Path

logger = logging.getLogger(__name__)


class InteractionLogger:
    """
    Centralized logger for LLM and agent interactions
    Stores all interactions in TinyDB with timestamps
    Provides API-friendly methods for retrieval
    """

    def __init__(self, db_path: str = "logs/interaction_logs.json"):
        """
        Initialize the interaction logger

        Args:
            db_path: Path to TinyDB database file
        """
        # Create logs directory if it doesn't exist
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db = TinyDB(db_path)
        self.interactions_table = self.db.table('llm_interactions')
        self.conversations_table = self.db.table('conversations')

        logger.info(f"InteractionLogger initialized with database: {db_path}")

    def log_llm_request(
        self,
        agent: str,
        interaction_type: str,
        prompt: str,
        workflow_id: str = None,
        parent_interaction_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Log an LLM request (before sending to LLM)

        Args:
            agent: Name of the agent (Analyzer, Planner, etc.)
            interaction_type: Type of interaction (workflow_analysis, plan_generation, etc.)
            prompt: The prompt sent to LLM
            workflow_id: Associated workflow ID
            parent_interaction_id: Parent interaction for multi-stage interactions
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
            "agent": agent,
            "workflow_id": workflow_id,
            "interaction_type": interaction_type,
            "direction": "request",
            "prompt": prompt,
            "prompt_length": len(prompt),
            "metadata": metadata or {},
            "response": None,
            "response_length": None,
            "latency_ms": None,
            "success": None,
            "error": None,
            "completed_at": None
        }

        self.interactions_table.insert(record)
        logger.debug(f"Logged LLM request: {interaction_id} ({agent} - {interaction_type})")

        return interaction_id

    def log_llm_response(
        self,
        interaction_id: str,
        response: str,
        success: bool = True,
        error: str = None,
        latency_ms: float = None,
        parsed_data: Dict[str, Any] = None
    ):
        """
        Update the interaction record with LLM response

        Args:
            interaction_id: ID from log_llm_request
            response: The response from LLM
            success: Whether the request was successful
            error: Error message if failed
            latency_ms: Request latency in milliseconds
            parsed_data: Parsed/structured data from response
        """
        Query_ = Query()
        completed_at = datetime.now().isoformat()

        update_data = {
            "response": response,
            "response_length": len(response) if response else 0,
            "success": success,
            "error": error,
            "latency_ms": latency_ms,
            "completed_at": completed_at
        }

        if parsed_data:
            update_data["parsed_data"] = parsed_data

        self.interactions_table.update(update_data, Query_.interaction_id == interaction_id)
        logger.debug(f"Logged LLM response: {interaction_id} (success={success})")

    def log_agent_action(
        self,
        agent: str,
        action_type: str,
        description: str,
        workflow_id: str = None,
        parent_interaction_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Log a non-LLM agent action (e.g., file fetching, plan validation)

        Args:
            agent: Name of the agent
            action_type: Type of action (file_fetch, validation, etc.)
            description: Description of the action
            workflow_id: Associated workflow ID
            parent_interaction_id: Parent interaction ID
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
            "agent": agent,
            "workflow_id": workflow_id,
            "interaction_type": action_type,
            "direction": "action",
            "description": description,
            "metadata": metadata or {},
            "success": True,
            "completed_at": timestamp
        }

        self.interactions_table.insert(record)
        logger.debug(f"Logged agent action: {interaction_id} ({agent} - {action_type})")

        return interaction_id

    def get_workflow_conversation(
        self,
        workflow_id: str,
        include_actions: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all interactions for a workflow in chronological order (chat format)

        Args:
            workflow_id: Workflow ID to filter by
            include_actions: Whether to include non-LLM actions

        Returns:
            List of interactions formatted for chat display
        """
        Query_ = Query()

        # Get all interactions for this workflow
        interactions = self.interactions_table.search(Query_.workflow_id == workflow_id)

        # Filter out actions if requested
        if not include_actions:
            interactions = [i for i in interactions if i.get('direction') != 'action']

        # Sort by timestamp
        interactions.sort(key=lambda x: x.get('timestamp', ''))

        # Format for chat display
        chat_messages = []
        for interaction in interactions:
            message = self._format_as_chat_message(interaction)
            chat_messages.append(message)

        return chat_messages

    def get_all_conversations(
        self,
        limit: int = 100,
        offset: int = 0,
        agent: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations grouped by workflow

        Args:
            limit: Maximum number of workflows to return
            offset: Offset for pagination
            agent: Filter by specific agent

        Returns:
            List of workflow conversations
        """
        Query_ = Query()

        # Get unique workflow IDs
        if agent:
            all_interactions = self.interactions_table.search(Query_.agent == agent)
        else:
            all_interactions = self.interactions_table.all()

        workflow_ids = list(set([i.get('workflow_id') for i in all_interactions if i.get('workflow_id')]))
        workflow_ids.sort(reverse=True)  # Most recent first

        # Apply pagination
        workflow_ids = workflow_ids[offset:offset + limit]

        # Get conversations for each workflow
        conversations = []
        for wf_id in workflow_ids:
            messages = self.get_workflow_conversation(wf_id)
            if messages:
                conversations.append({
                    "workflow_id": wf_id,
                    "message_count": len(messages),
                    "first_timestamp": messages[0].get('timestamp'),
                    "last_timestamp": messages[-1].get('timestamp'),
                    "agents": list(set([m.get('agent') for m in messages])),
                    "messages": messages
                })

        return conversations

    def get_latest_interactions(
        self,
        limit: int = 50,
        agent: str = None,
        interaction_type: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get latest interactions across all workflows

        Args:
            limit: Maximum number to return
            agent: Filter by agent
            interaction_type: Filter by type

        Returns:
            List of interactions
        """
        Query_ = Query()

        # Build query
        if agent and interaction_type:
            interactions = self.interactions_table.search(
                (Query_.agent == agent) & (Query_.interaction_type == interaction_type)
            )
        elif agent:
            interactions = self.interactions_table.search(Query_.agent == agent)
        elif interaction_type:
            interactions = self.interactions_table.search(Query_.interaction_type == interaction_type)
        else:
            interactions = self.interactions_table.all()

        # Sort by timestamp (most recent first)
        interactions.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Return limited results
        return interactions[:limit]

    def get_interaction_by_id(self, interaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific interaction by ID

        Args:
            interaction_id: Interaction ID

        Returns:
            Interaction record or None
        """
        Query_ = Query()
        results = self.interactions_table.search(Query_.interaction_id == interaction_id)
        return results[0] if results else None

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about logged interactions

        Returns:
            Statistics dictionary
        """
        all_interactions = self.interactions_table.all()

        total_count = len(all_interactions)
        successful_count = len([i for i in all_interactions if i.get('success') is True])
        failed_count = len([i for i in all_interactions if i.get('success') is False])

        # Agent breakdown
        agents = {}
        for interaction in all_interactions:
            agent = interaction.get('agent', 'Unknown')
            agents[agent] = agents.get(agent, 0) + 1

        # Type breakdown
        types = {}
        for interaction in all_interactions:
            itype = interaction.get('interaction_type', 'Unknown')
            types[itype] = types.get(itype, 0) + 1

        # Average latency
        latencies = [i.get('latency_ms') for i in all_interactions if i.get('latency_ms')]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        return {
            "total_interactions": total_count,
            "successful": successful_count,
            "failed": failed_count,
            "success_rate": (successful_count / total_count * 100) if total_count > 0 else 0,
            "by_agent": agents,
            "by_type": types,
            "average_latency_ms": round(avg_latency, 2),
            "unique_workflows": len(set([i.get('workflow_id') for i in all_interactions if i.get('workflow_id')]))
        }

    def clear_old_interactions(self, days: int = 30):
        """
        Clear interactions older than specified days

        Args:
            days: Number of days to keep
        """
        from datetime import timedelta

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        Query_ = Query()

        removed = self.interactions_table.remove(Query_.timestamp < cutoff_date)
        logger.info(f"Cleared {len(removed)} interactions older than {days} days")

        return len(removed)

    def _format_as_chat_message(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format an interaction record as a chat message

        Args:
            interaction: Raw interaction record

        Returns:
            Formatted chat message
        """
        direction = interaction.get('direction', 'request')

        if direction == 'request':
            # This is a message TO the LLM (user message in chat)
            return {
                "id": interaction.get('interaction_id'),
                "timestamp": interaction.get('timestamp'),
                "role": "user",
                "agent": interaction.get('agent'),
                "type": interaction.get('interaction_type'),
                "content": interaction.get('prompt', ''),
                "metadata": interaction.get('metadata', {}),
                "workflow_id": interaction.get('workflow_id'),
                "has_response": interaction.get('response') is not None,
                "success": interaction.get('success'),
                "latency_ms": interaction.get('latency_ms')
            }
        elif direction == 'action':
            # This is an agent action (system message in chat)
            return {
                "id": interaction.get('interaction_id'),
                "timestamp": interaction.get('timestamp'),
                "role": "system",
                "agent": interaction.get('agent'),
                "type": interaction.get('interaction_type'),
                "content": interaction.get('description', ''),
                "metadata": interaction.get('metadata', {}),
                "workflow_id": interaction.get('workflow_id')
            }
        else:
            # This is a response FROM the LLM (assistant message in chat)
            return {
                "id": interaction.get('interaction_id'),
                "timestamp": interaction.get('completed_at') or interaction.get('timestamp'),
                "role": "assistant",
                "agent": "LLM",
                "type": interaction.get('interaction_type'),
                "content": interaction.get('response', ''),
                "metadata": {
                    **interaction.get('metadata', {}),
                    "latency_ms": interaction.get('latency_ms'),
                    "success": interaction.get('success'),
                    "error": interaction.get('error')
                },
                "workflow_id": interaction.get('workflow_id'),
                "parsed_data": interaction.get('parsed_data')
            }

    def close(self):
        """Close the database connection"""
        self.db.close()
        logger.info("InteractionLogger closed")


# Global singleton instance
_global_logger = None

def get_interaction_logger(db_path: str = "logs/interaction_logs.json") -> InteractionLogger:
    """
    Get or create the global interaction logger instance

    Args:
        db_path: Path to database file

    Returns:
        InteractionLogger instance
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = InteractionLogger(db_path)
    return _global_logger

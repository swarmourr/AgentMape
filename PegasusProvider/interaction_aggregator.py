#!/usr/bin/env python3
"""
PegasusProvider - LLM Interaction Aggregator
Collects interactions from Analyzer and Planner and provides unified view
Handles duplicate workflow IDs by returning latest interaction
"""

import logging
import aiohttp
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class InteractionAggregator:
    """
    Aggregates LLM interactions from Analyzer and Planner
    Provides unified API for web dashboard
    """

    def __init__(self, analyzer_url: str = "http://localhost:8081", planner_url: str = "http://localhost:8082"):
        """
        Initialize aggregator

        Args:
            analyzer_url: URL of Analyzer agent
            planner_url: URL of Planner agent
        """
        self.analyzer_url = analyzer_url
        self.planner_url = planner_url
        logger.info(f"InteractionAggregator initialized (Analyzer: {analyzer_url}, Planner: {planner_url})")

    async def get_workflow_conversation(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get complete conversation for a workflow from both agents
        If same workflow_id appears multiple times, groups all interactions chronologically

        Args:
            workflow_id: Workflow ID

        Returns:
            Complete conversation with messages from both agents
        """
        analyzer_interactions = []
        planner_interactions = []

        # Fetch from Analyzer
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.analyzer_url}/api/analyzer/interactions/workflow/{workflow_id}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            analyzer_interactions = data.get('interactions', [])
                            logger.info(f"Fetched {len(analyzer_interactions)} interactions from Analyzer")
                    else:
                        logger.warning(f"Analyzer returned status {resp.status}")
        except Exception as e:
            logger.error(f"Failed to fetch from Analyzer: {e}")

        # Fetch from Planner
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.planner_url}/api/planner/interactions/workflow/{workflow_id}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            planner_interactions = data.get('interactions', [])
                            logger.info(f"Fetched {len(planner_interactions)} interactions from Planner")
                    else:
                        logger.warning(f"Planner returned status {resp.status}")
        except Exception as e:
            logger.error(f"Failed to fetch from Planner: {e}")

        # Combine and sort by timestamp
        all_interactions = analyzer_interactions + planner_interactions
        all_interactions.sort(key=lambda x: x.get('timestamp', ''))

        # Format as chat messages
        messages = [self._format_as_chat_message(i) for i in all_interactions]

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message_count": len(messages),
            "analyzer_count": len(analyzer_interactions),
            "planner_count": len(planner_interactions),
            "messages": messages,
            "timeline": {
                "first_timestamp": messages[0].get('timestamp') if messages else None,
                "last_timestamp": messages[-1].get('timestamp') if messages else None
            }
        }

    async def get_latest_interaction_per_workflow(self, limit: int = 50) -> Dict[str, Any]:
        """
        Get latest interaction for each unique workflow
        Important: If same workflow_id appears multiple times, return ONLY the latest

        Args:
            limit: Maximum number of unique workflows to return

        Returns:
            Latest interaction per workflow
        """
        # Fetch latest from both agents
        analyzer_latest = await self._fetch_latest_from_analyzer(limit * 2)  # Get more to ensure we have enough
        planner_latest = await self._fetch_latest_from_planner(limit * 2)

        # Combine all interactions
        all_interactions = analyzer_latest + planner_latest

        # Group by workflow_id and keep only the latest for each
        workflow_map = {}
        for interaction in all_interactions:
            wf_id = interaction.get('workflow_id')
            if not wf_id:
                continue

            timestamp = interaction.get('timestamp', '')

            # If this workflow not seen yet, or this interaction is newer
            if wf_id not in workflow_map or timestamp > workflow_map[wf_id].get('timestamp', ''):
                workflow_map[wf_id] = interaction

        # Convert to list and sort by timestamp (most recent first)
        latest_per_workflow = list(workflow_map.values())
        latest_per_workflow.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Limit results
        latest_per_workflow = latest_per_workflow[:limit]

        return {
            "success": True,
            "count": len(latest_per_workflow),
            "unique_workflows": len(workflow_map),
            "latest_interactions": latest_per_workflow
        }

    async def get_aggregated_statistics(self) -> Dict[str, Any]:
        """
        Get combined statistics from both agents

        Returns:
            Aggregated statistics
        """
        analyzer_stats = {}
        planner_stats = {}

        # Fetch from Analyzer
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.analyzer_url}/api/analyzer/interactions/statistics",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            analyzer_stats = data.get('statistics', {})
        except Exception as e:
            logger.error(f"Failed to fetch stats from Analyzer: {e}")

        # Fetch from Planner
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.planner_url}/api/planner/interactions/statistics",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            planner_stats = data.get('statistics', {})
        except Exception as e:
            logger.error(f"Failed to fetch stats from Planner: {e}")

        # Aggregate
        total_interactions = analyzer_stats.get('total_interactions', 0) + planner_stats.get('total_interactions', 0)
        total_successful = analyzer_stats.get('successful', 0) + planner_stats.get('successful', 0)
        total_failed = analyzer_stats.get('failed', 0) + planner_stats.get('failed', 0)

        # Calculate weighted average latency
        analyzer_latency = analyzer_stats.get('average_latency_ms', 0)
        planner_latency = planner_stats.get('average_latency_ms', 0)
        analyzer_count = analyzer_stats.get('total_interactions', 0)
        planner_count = planner_stats.get('total_interactions', 0)

        if total_interactions > 0:
            avg_latency = (
                (analyzer_latency * analyzer_count + planner_latency * planner_count) /
                total_interactions
            )
        else:
            avg_latency = 0

        return {
            "success": True,
            "statistics": {
                "total_interactions": total_interactions,
                "successful": total_successful,
                "failed": total_failed,
                "success_rate": (total_successful / total_interactions * 100) if total_interactions > 0 else 0,
                "average_latency_ms": round(avg_latency, 2),
                "by_agent": {
                    "Analyzer": analyzer_stats.get('total_interactions', 0),
                    "Planner": planner_stats.get('total_interactions', 0)
                },
                "unique_workflows": max(
                    analyzer_stats.get('unique_workflows', 0),
                    planner_stats.get('unique_workflows', 0)
                ),
                "analyzer_details": analyzer_stats,
                "planner_details": planner_stats
            }
        }

    async def _fetch_latest_from_analyzer(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch latest interactions from Analyzer"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.analyzer_url}/api/analyzer/interactions/latest?limit={limit}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            return data.get('interactions', [])
        except Exception as e:
            logger.error(f"Failed to fetch latest from Analyzer: {e}")

        return []

    async def _fetch_latest_from_planner(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch latest interactions from Planner"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.planner_url}/api/planner/interactions/latest?limit={limit}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            return data.get('interactions', [])
        except Exception as e:
            logger.error(f"Failed to fetch latest from Planner: {e}")

        return []

    def _format_as_chat_message(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format interaction as chat message

        Args:
            interaction: Raw interaction record

        Returns:
            Formatted chat message
        """
        agent = interaction.get('agent', 'Unknown')
        direction = interaction.get('direction', 'request')

        if direction == 'request':
            # User message (to LLM)
            return {
                "id": interaction.get('interaction_id'),
                "timestamp": interaction.get('timestamp'),
                "role": "user",
                "agent": agent,
                "type": interaction.get('analysis_type') or interaction.get('stage', 'unknown'),
                "content": interaction.get('prompt', ''),
                "workflow_id": interaction.get('workflow_id'),
                "has_response": interaction.get('response') is not None,
                "success": interaction.get('success'),
                "latency_ms": interaction.get('latency_ms'),
                "metadata": interaction.get('metadata', {})
            }
        elif direction == 'action':
            # System message (agent action)
            return {
                "id": interaction.get('interaction_id'),
                "timestamp": interaction.get('timestamp'),
                "role": "system",
                "agent": agent,
                "type": interaction.get('action_type', 'action'),
                "content": interaction.get('description', ''),
                "workflow_id": interaction.get('workflow_id'),
                "metadata": interaction.get('metadata', {})
            }
        else:
            # Assistant message (from LLM) - this is the response part
            return {
                "id": interaction.get('interaction_id'),
                "timestamp": interaction.get('completed_at') or interaction.get('timestamp'),
                "role": "assistant",
                "agent": "LLM",
                "type": interaction.get('analysis_type') or interaction.get('stage', 'unknown'),
                "content": interaction.get('response', ''),
                "workflow_id": interaction.get('workflow_id'),
                "success": interaction.get('success'),
                "latency_ms": interaction.get('latency_ms'),
                "metadata": interaction.get('metadata', {}),
                "parsed_data": interaction.get('parsed_result') or interaction.get('parsed_plan')
            }

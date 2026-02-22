#!/usr/bin/env python3
"""
API Endpoints for LLM Interaction Logs
Provides REST API for accessing interaction logs for web dashboard
"""

import logging
from aiohttp import web
from typing import Dict, Any
from interaction_logger import get_interaction_logger

logger = logging.getLogger(__name__)


class InteractionAPI:
    """
    REST API for accessing LLM interaction logs
    Designed for web dashboard chat interface
    """

    def __init__(self, app: web.Application = None):
        """
        Initialize the API

        Args:
            app: aiohttp Application to add routes to
        """
        self.logger = get_interaction_logger()

        if app:
            self.setup_routes(app)

    def setup_routes(self, app: web.Application):
        """
        Setup API routes

        Args:
            app: aiohttp Application
        """
        app.router.add_get('/api/interactions/workflow/{workflow_id}', self.get_workflow_conversation)
        app.router.add_get('/api/interactions/latest', self.get_latest_interactions)
        app.router.add_get('/api/interactions/conversations', self.get_all_conversations)
        app.router.add_get('/api/interactions/statistics', self.get_statistics)
        app.router.add_get('/api/interactions/{interaction_id}', self.get_interaction_by_id)
        app.router.add_post('/api/interactions/clear-old', self.clear_old_interactions)

        logger.info("Interaction API routes registered")

    async def get_workflow_conversation(self, request: web.Request) -> web.Response:
        """
        GET /api/interactions/workflow/{workflow_id}
        Get all interactions for a specific workflow (chat format)

        Query params:
            - include_actions: Include non-LLM actions (default: true)

        Returns:
            JSON array of chat messages
        """
        try:
            workflow_id = request.match_info['workflow_id']
            include_actions = request.query.get('include_actions', 'true').lower() == 'true'

            conversation = self.logger.get_workflow_conversation(workflow_id, include_actions)

            return web.json_response({
                "success": True,
                "workflow_id": workflow_id,
                "message_count": len(conversation),
                "messages": conversation
            })

        except Exception as e:
            logger.error(f"Error getting workflow conversation: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_latest_interactions(self, request: web.Request) -> web.Response:
        """
        GET /api/interactions/latest
        Get latest interactions across all workflows

        Query params:
            - limit: Max number to return (default: 50)
            - agent: Filter by agent name
            - type: Filter by interaction type

        Returns:
            JSON array of interactions
        """
        try:
            limit = int(request.query.get('limit', 50))
            agent = request.query.get('agent')
            interaction_type = request.query.get('type')

            interactions = self.logger.get_latest_interactions(
                limit=limit,
                agent=agent,
                interaction_type=interaction_type
            )

            return web.json_response({
                "success": True,
                "count": len(interactions),
                "interactions": interactions
            })

        except Exception as e:
            logger.error(f"Error getting latest interactions: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_all_conversations(self, request: web.Request) -> web.Response:
        """
        GET /api/interactions/conversations
        Get all conversations grouped by workflow

        Query params:
            - limit: Max number of workflows (default: 100)
            - offset: Pagination offset (default: 0)
            - agent: Filter by agent name

        Returns:
            JSON array of conversations
        """
        try:
            limit = int(request.query.get('limit', 100))
            offset = int(request.query.get('offset', 0))
            agent = request.query.get('agent')

            conversations = self.logger.get_all_conversations(
                limit=limit,
                offset=offset,
                agent=agent
            )

            return web.json_response({
                "success": True,
                "count": len(conversations),
                "limit": limit,
                "offset": offset,
                "conversations": conversations
            })

        except Exception as e:
            logger.error(f"Error getting conversations: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_statistics(self, request: web.Request) -> web.Response:
        """
        GET /api/interactions/statistics
        Get statistics about logged interactions

        Returns:
            JSON with statistics
        """
        try:
            stats = self.logger.get_statistics()

            return web.json_response({
                "success": True,
                "statistics": stats
            })

        except Exception as e:
            logger.error(f"Error getting statistics: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_interaction_by_id(self, request: web.Request) -> web.Response:
        """
        GET /api/interactions/{interaction_id}
        Get a specific interaction by ID

        Returns:
            JSON interaction record
        """
        try:
            interaction_id = request.match_info['interaction_id']

            interaction = self.logger.get_interaction_by_id(interaction_id)

            if interaction:
                return web.json_response({
                    "success": True,
                    "interaction": interaction
                })
            else:
                return web.json_response({
                    "success": False,
                    "error": "Interaction not found"
                }, status=404)

        except Exception as e:
            logger.error(f"Error getting interaction: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def clear_old_interactions(self, request: web.Request) -> web.Response:
        """
        POST /api/interactions/clear-old
        Clear old interactions

        Body:
            - days: Number of days to keep (default: 30)

        Returns:
            JSON with number of cleared interactions
        """
        try:
            data = await request.json()
            days = data.get('days', 30)

            count = self.logger.clear_old_interactions(days)

            return web.json_response({
                "success": True,
                "cleared_count": count,
                "days": days
            })

        except Exception as e:
            logger.error(f"Error clearing old interactions: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)


def setup_interaction_api(app: web.Application):
    """
    Helper function to setup interaction API on an existing aiohttp app

    Args:
        app: aiohttp Application

    Usage:
        from common.interaction_api import setup_interaction_api
        app = web.Application()
        setup_interaction_api(app)
    """
    api = InteractionAPI(app)
    logger.info("Interaction API setup complete")
    return api

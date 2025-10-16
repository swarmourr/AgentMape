#!/usr/bin/env python3
"""
Pegasus Data Provider Service
Dedicated service for executing and caching Pegasus WMS commands
Provides real-time workflow data from Pegasus tools

Port: 8084
API Endpoints:
  GET /health
  GET /api/workflows/{workflow_id}/status
  GET /api/workflows/{workflow_id}/analyzer
  GET /api/workflows/{workflow_id}/statistics
  GET /api/workflows/{workflow_id}/full
  POST /api/workflows/batch
  DELETE /cache
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime
from aiohttp import web
import aiohttp_cors

# Add parent directory to path to import pegasus_commands
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Monitoring'))
from pegasus_commands import PegasusCommandExecutor

# Configuration
HTTP_PORT = int(os.getenv("PEGASUS_PROVIDER_PORT", "8084"))
MONITOR_URL = os.getenv("MONITOR_URL", "http://localhost:8080")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PegasusProviderService:
    """Standalone service for Pegasus WMS data access"""

    def __init__(self):
        self.executor = PegasusCommandExecutor(timeout=30)
        self.app = web.Application()
        self.setup_routes()
        self.service_info = {
            "name": "Pegasus Data Provider",
            "version": "1.0.0",
            "port": HTTP_PORT,
            "started_at": datetime.now().isoformat(),
            "capabilities": [
                "pegasus-status",
                "pegasus-analyzer",
                "pegasus-statistics",
                "batch_queries",
                "caching"
            ]
        }



    def setup_routes(self):
        """Setup HTTP routes with proper CORS for ngrok/pinggy"""

        # FIXED CORS Configuration for ngrok/pinggy
        # When allow_credentials is True, cannot use wildcard origin
        # So we allow credentials=False with wildcard origin for public tunnel access
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=False,  # Changed to False to allow wildcard origin
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
            )
        })

        # Define all routes
        routes = [
            ('GET', '/health', self.handle_health),
            ('GET', '/api/info', self.handle_service_info),
            ('GET', '/api/workflows/{workflow_id}/status', self.handle_status),
            ('GET', '/api/workflows/{workflow_id}/analyzer', self.handle_analyzer),
            ('GET', '/api/workflows/{workflow_id}/statistics', self.handle_statistics),
            ('GET', '/api/workflows/{workflow_id}/full', self.handle_full_analysis),
            ('GET', '/api/workflows/{workflow_id}/jobs', self.handle_jobs),
            ('POST', '/api/workflows/batch', self.handle_batch_query),
            ('DELETE', '/api/cache', self.handle_clear_cache),
            ('GET', '/api/cache/stats', self.handle_cache_stats)
        ]

        # Add routes with CORS
        for method, path, handler in routes:
            route = self.app.router.add_route(method, path, handler)
            cors.add(route)

    async def handle_health(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "service": "pegasus_data_provider",
            "timestamp": datetime.now().isoformat()
        })

    async def handle_service_info(self, request):
        """Return service information"""
        return web.json_response(self.service_info)

    async def get_workflow_submit_dir(self, workflow_id: str) -> Optional[str]:
        """
        Query Monitor to get workflow submit directory
        This keeps separation - we don't store workflow data, Monitor does
        """
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{MONITOR_URL}/api/workflows/{workflow_id}/status",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('iwd') or data.get('workflow_dir')
                    else:
                        logger.warning(f"Monitor returned {resp.status} for workflow {workflow_id}")
                        return None
        except Exception as e:
            logger.error(f"Error querying Monitor for workflow {workflow_id}: {e}")
            return None

    async def handle_status(self, request):
        """Execute pegasus-status command"""
        try:
            workflow_id = request.match_info['workflow_id']
            logger.info(f"Status request for workflow: {workflow_id}")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            # Execute pegasus-status
            result = await asyncio.to_thread(
                self.executor.get_workflow_status, submit_dir
            )

            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error in handle_status: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_analyzer(self, request):
        """Execute pegasus-analyzer command (ROOT CAUSE ANALYSIS)"""
        try:
            workflow_id = request.match_info['workflow_id']
            verbose = request.query.get('verbose', 'true').lower() == 'true'
            logger.info(f"Analyzer request for workflow: {workflow_id} (verbose={verbose})")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            # Execute pegasus-analyzer
            result = await asyncio.to_thread(
                self.executor.get_workflow_analyzer_output, submit_dir, verbose
            )

            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error in handle_analyzer: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_statistics(self, request):
        """Execute pegasus-statistics command"""
        try:
            workflow_id = request.match_info['workflow_id']
            stat_type = request.query.get('type', 'summary')
            logger.info(f"Statistics request for workflow: {workflow_id} (type={stat_type})")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            # Execute pegasus-statistics
            result = await asyncio.to_thread(
                self.executor.get_workflow_statistics, submit_dir, stat_type
            )

            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error in handle_statistics: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_jobs(self, request):
        """Get workflow jobs and DAG structure"""
        try:
            workflow_id = request.match_info['workflow_id']
            logger.info(f"Jobs request for workflow: {workflow_id}")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            # Execute pegasus-status --long to get jobs
            result = await asyncio.to_thread(
                self.executor.get_workflow_jobs, submit_dir
            )

            return web.json_response(result)

        except Exception as e:
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_full_analysis(self, request):
        """Execute all Pegasus commands and combine results"""
        try:
            workflow_id = request.match_info['workflow_id']
            logger.info(f"Full analysis request for workflow: {workflow_id}")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            # Execute all commands in parallel
            status_task = asyncio.create_task(asyncio.to_thread(
                self.executor.get_workflow_status, submit_dir
            ))
            analyzer_task = asyncio.create_task(asyncio.to_thread(
                self.executor.get_workflow_analyzer_output, submit_dir, True
            ))
            stats_task = asyncio.create_task(asyncio.to_thread(
                self.executor.get_workflow_statistics, submit_dir, "summary"
            ))

            # Wait for all
            status_result, analyzer_result, stats_result = await asyncio.gather(
                status_task, analyzer_task, stats_task, return_exceptions=True
            )

            # Compile results
            full_analysis = {
                "workflow_id": workflow_id,
                "submit_dir": submit_dir,
                "timestamp": datetime.now().isoformat(),
                "status": status_result if not isinstance(status_result, Exception) else {"error": str(status_result)},
                "analyzer": analyzer_result if not isinstance(analyzer_result, Exception) else {"error": str(analyzer_result)},
                "statistics": stats_result if not isinstance(stats_result, Exception) else {"error": str(stats_result)},
            }

            # Extract key insights from analyzer
            if analyzer_result and analyzer_result.get('success'):
                analysis = analyzer_result.get('analysis', {})
                full_analysis['root_causes'] = analysis.get('root_causes', [])
                full_analysis['has_failures'] = analysis.get('has_failures', False)
                full_analysis['failed_jobs_count'] = len(analysis.get('failed_jobs', []))
                full_analysis['held_jobs_count'] = len(analysis.get('held_jobs', []))

            return web.json_response(full_analysis)

        except Exception as e:
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_batch_query(self, request):
        """
        Query multiple workflows in parallel
        POST body: {"workflow_ids": ["id1", "id2", ...], "query_type": "analyzer"}
        """
        try:
            data = await request.json()
            workflow_ids = data.get('workflow_ids', [])
            query_type = data.get('query_type', 'analyzer')  # analyzer, status, statistics, full

            logger.info(f"Batch query: {len(workflow_ids)} workflows, type={query_type}")

            if not workflow_ids:
                return web.json_response({
                    "success": False,
                    "error": "No workflow_ids provided"
                }, status=400)

            # Query all workflows in parallel
            tasks = []
            for wf_id in workflow_ids:
                if query_type == 'analyzer':
                    tasks.append(self._query_analyzer(wf_id))
                elif query_type == 'status':
                    tasks.append(self._query_status(wf_id))
                elif query_type == 'full':
                    tasks.append(self._query_full(wf_id))
                else:
                    tasks.append(self._query_analyzer(wf_id))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Compile results
            batch_results = {}
            for wf_id, result in zip(workflow_ids, results):
                if isinstance(result, Exception):
                    batch_results[wf_id] = {"success": False, "error": str(result)}
                else:
                    batch_results[wf_id] = result

            return web.json_response({
                "success": True,
                "query_type": query_type,
                "count": len(workflow_ids),
                "results": batch_results,
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Error in handle_batch_query: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def _query_analyzer(self, workflow_id: str):
        """Helper for batch query"""
        submit_dir = await self.get_workflow_submit_dir(workflow_id)
        if not submit_dir:
            return {"success": False, "error": "Workflow not found"}
        return await asyncio.to_thread(
            self.executor.get_workflow_analyzer_output, submit_dir, False
        )

    async def _query_status(self, workflow_id: str):
        """Helper for batch query"""
        submit_dir = await self.get_workflow_submit_dir(workflow_id)
        if not submit_dir:
            return {"success": False, "error": "Workflow not found"}
        return await asyncio.to_thread(
            self.executor.get_workflow_status, submit_dir
        )

    async def _query_full(self, workflow_id: str):
        """Helper for batch query"""
        submit_dir = await self.get_workflow_submit_dir(workflow_id)
        if not submit_dir:
            return {"success": False, "error": "Workflow not found"}

        # Simplified full query (without parallel execution for batch)
        analyzer = await asyncio.to_thread(
            self.executor.get_workflow_analyzer_output, submit_dir, False
        )
        return analyzer

    async def handle_clear_cache(self, request):
        """Clear command result cache"""
        try:
            self.executor.clear_cache()
            logger.info("Cache cleared")
            return web.json_response({
                "success": True,
                "message": "Cache cleared",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_cache_stats(self, request):
        """Get cache statistics"""
        try:
            cache_size = len(self.executor._command_cache)
            return web.json_response({
                "success": True,
                "cache_size": cache_size,
                "cache_ttl_seconds": self.executor._cache_ttl,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def start(self):
        """Start the HTTP server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', HTTP_PORT)
        await site.start()

        logger.info("=" * 80)
        logger.info(f"🚀 Pegasus Data Provider Service Started")
        logger.info("=" * 80)
        logger.info(f"Service: {self.service_info['name']}")
        logger.info(f"Version: {self.service_info['version']}")
        logger.info(f"Port: {HTTP_PORT}")
        logger.info(f"Monitor URL: {MONITOR_URL}")
        logger.info("")
        logger.info("API Endpoints:")
        logger.info(f"  GET  /health")
        logger.info(f"  GET  /api/info")
        logger.info(f"  GET  /api/workflows/{{id}}/status")
        logger.info(f"  GET  /api/workflows/{{id}}/analyzer")
        logger.info(f"  GET  /api/workflows/{{id}}/statistics")
        logger.info(f"  GET  /api/workflows/{{id}}/full")
        logger.info(f"  POST /api/workflows/batch")
        logger.info(f"  DELETE /api/cache")
        logger.info("=" * 80)

        # Keep running
        while True:
            await asyncio.sleep(3600)


async def main():
    """Main entry point"""
    service = PegasusProviderService()
    await service.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n🛑 Pegasus Data Provider Service stopped")

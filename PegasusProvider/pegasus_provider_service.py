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
  GET /api/workflows/{workflow_id}/jobs
  POST /api/workflows/{workflow_id}/rerun
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
        self.app = web.Application(middlewares=[self.cors_middleware])
        self.setup_routes()
        self.service_info = {
            "name": "Pegasus Data Provider",
            "version": "1.1.0",
            "port": HTTP_PORT,
            "started_at": datetime.now().isoformat(),
            "capabilities": [
                "pegasus-status",
                "pegasus-analyzer",
                "pegasus-statistics",
                "pegasus-run",
                "workflow-rerun",
                "batch_queries",
                "caching"
            ]
        }

    @web.middleware
    async def cors_middleware(self, request, handler):
        """Middleware to add CORS headers to all responses (for Pinggy/Ngrok tunnels)"""
        # Handle preflight OPTIONS request
        if request.method == 'OPTIONS':
            response = web.Response()
        else:
            try:
                response = await handler(request)
            except Exception as e:
                # Create error response
                response = web.json_response({"error": str(e)}, status=500)

        # Add CORS headers to response
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Access-Control-Expose-Headers'] = '*'
        response.headers['Access-Control-Max-Age'] = '3600'

        return response

    def setup_routes(self):
        """Setup HTTP routes - CORS handled by middleware"""

        # Define all routes (CORS is now handled by middleware, not aiohttp_cors)
        routes = [
            ('GET', '/health', self.handle_health),
            ('GET', '/api/info', self.handle_service_info),
            ('GET', '/api/workflows/{workflow_id}/status', self.handle_status),
            ('GET', '/api/workflows/{workflow_id}/analyzer', self.handle_analyzer),
            ('GET', '/api/workflows/{workflow_id}/statistics', self.handle_statistics),
            ('GET', '/api/workflows/{workflow_id}/full', self.handle_full_analysis),
            ('GET', '/api/workflows/{workflow_id}/jobs', self.handle_jobs),
            ('GET', '/api/workflows/{workflow_id}/dag', self.handle_dag),
            ('POST', '/api/workflows/{workflow_id}/rerun', self.handle_rerun_workflow),
            ('POST', '/api/workflows/batch', self.handle_batch_query),
            ('DELETE', '/api/cache', self.handle_clear_cache),
            ('GET', '/api/cache/stats', self.handle_cache_stats)
        ]

        # Add routes (no CORS library needed - middleware handles it)
        for method, path, handler in routes:
            self.app.router.add_route(method, path, handler)

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
            logger.info(f"🔍 Querying Monitor for workflow: {workflow_id}")
            logger.info(f"   Monitor URL: {MONITOR_URL}/api/workflows/{workflow_id}/status")

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{MONITOR_URL}/api/workflows/{workflow_id}/status",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    logger.info(f"   Monitor response status: {resp.status}")

                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"   Monitor data keys: {list(data.keys())}")

                        submit_dir = data.get('iwd') or data.get('workflow_dir')

                        if submit_dir:
                            logger.info(f"✅ Found submit directory: {submit_dir}")
                        else:
                            logger.warning(f"⚠️  No submit directory in Monitor response")
                            logger.warning(f"   Available data: {data}")

                        return submit_dir
                    else:
                        error_text = await resp.text()
                        logger.warning(f"❌ Monitor returned {resp.status} for workflow {workflow_id}")
                        logger.warning(f"   Error response: {error_text[:200]}")
                        return None
        except Exception as e:
            logger.error(f"❌ Error querying Monitor for workflow {workflow_id}: {e}")
            logger.exception("Full error traceback:")
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
            logger.info(f"📋 Jobs request for workflow: {workflow_id}")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                logger.error(f"❌ No submit directory found for jobs request")
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            # Execute pegasus-status --long to get jobs
            logger.info(f"⚙️  Executing pegasus-status --long for: {submit_dir}")
            result = await asyncio.to_thread(
                self.executor.get_workflow_jobs, submit_dir
            )

            if result.get('success'):
                job_count = len(result.get('jobs', []))
                logger.info(f"✅ Found {job_count} jobs in workflow")
            else:
                logger.error(f"❌ Failed to get jobs: {result.get('error')}")

            return web.json_response(result)

        except Exception as e:
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_dag(self, request):
        """Get workflow DAG structure using pegasus-graphviz, fallback to synthetic jobs"""
        try:
            workflow_id = request.match_info['workflow_id']
            logger.info(f"🔀 DAG request for workflow: {workflow_id}")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                logger.error(f"❌ No submit directory found for DAG request")
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            # Try pegasus-graphviz first (with retry)
            max_retries = 2
            result = None

            for attempt in range(max_retries):
                try:
                    logger.info(f"⚙️  Trying pegasus-graphviz for: {submit_dir} (attempt {attempt + 1}/{max_retries})")
                    result = await asyncio.to_thread(
                        self.executor.get_workflow_dag, submit_dir
                    )

                    if result and isinstance(result, dict) and result.get('success'):
                        node_count = len(result.get('nodes', []))
                        edge_count = len(result.get('edges', []))

                        # Check if we actually got nodes (not just edges)
                        if node_count > 0:
                            logger.info(f"✅ Generated DAG with {node_count} nodes and {edge_count} edges")
                            return web.json_response(result)
                        else:
                            logger.warning(f"⚠️  pegasus-graphviz returned 0 nodes (retry {attempt + 1}/{max_retries})")
                            await asyncio.sleep(0.5)  # Brief delay before retry
                            continue
                    else:
                        logger.warning(f"⚠️  pegasus-graphviz failed (attempt {attempt + 1}/{max_retries})")
                        logger.warning(f"   Error was: {result.get('error', 'unknown') if result else 'no result'}")
                        await asyncio.sleep(0.5)
                        continue

                except Exception as e:
                    logger.error(f"❌ Exception in pegasus-graphviz (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        break

            # Fallback to synthetic jobs from pegasus-status
            logger.warning(f"⚠️  pegasus-graphviz failed after {max_retries} attempts, falling back to synthetic jobs")

            try:
                jobs_result = await asyncio.to_thread(
                    self.executor.get_workflow_jobs, submit_dir
                )

                if jobs_result and isinstance(jobs_result, dict) and jobs_result.get('success'):
                    logger.info(f"✅ Using {len(jobs_result.get('jobs', []))} synthetic jobs as fallback")
                    return web.json_response({
                        "success": True,
                        "nodes": [],  # Empty - triggers fallback in frontend
                        "edges": [],
                        "jobs": jobs_result.get('jobs', []),
                        "fallback": True,
                        "timestamp": jobs_result.get('timestamp')
                    })
                else:
                    logger.error(f"❌ Fallback jobs also failed")
                    return web.json_response(jobs_result if jobs_result else {
                        "success": False,
                        "error": "Both pegasus-graphviz and pegasus-status failed"
                    })
            except Exception as e:
                logger.error(f"❌ Exception getting fallback jobs: {e}")
                return web.json_response({
                    "success": False,
                    "error": f"Failed to get workflow structure: {str(e)}"
                })

        except Exception as e:
            logger.error(f"❌ Error in handle_dag: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def handle_full_analysis(self, request):
        """Execute all Pegasus commands and combine results"""
        try:
            workflow_id = request.match_info['workflow_id']
            logger.info(f"📊 Full analysis request for workflow: {workflow_id}")

            # Get submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)
            if not submit_dir:
                logger.error(f"❌ No submit directory found for workflow {workflow_id}")
                return web.json_response({
                    "success": False,
                    "error": "Workflow not found or submit directory unknown"
                }, status=404)

            logger.info(f"⚙️  Executing Pegasus commands for: {submit_dir}")

            # Execute all commands in parallel
            logger.info("   Running pegasus-status...")
            status_task = asyncio.create_task(asyncio.to_thread(
                self.executor.get_workflow_status, submit_dir
            ))

            logger.info("   Running pegasus-analyzer...")
            analyzer_task = asyncio.create_task(asyncio.to_thread(
                self.executor.get_workflow_analyzer_output, submit_dir, True
            ))

            logger.info("   Running pegasus-statistics...")
            stats_task = asyncio.create_task(asyncio.to_thread(
                self.executor.get_workflow_statistics, submit_dir, "summary"
            ))

            # Wait for all
            logger.info("⏳ Waiting for all commands to complete...")
            status_result, analyzer_result, stats_result = await asyncio.gather(
                status_task, analyzer_task, stats_task, return_exceptions=True
            )

            # Log results
            logger.info("📋 Command results:")
            logger.info(f"   Status success: {isinstance(status_result, dict) and status_result.get('success')}")
            logger.info(f"   Analyzer success: {isinstance(analyzer_result, dict) and analyzer_result.get('success')}")
            logger.info(f"   Statistics success: {isinstance(stats_result, dict) and stats_result.get('success')}")

            if isinstance(status_result, Exception):
                logger.error(f"   ❌ Status error: {status_result}")
            if isinstance(analyzer_result, Exception):
                logger.error(f"   ❌ Analyzer error: {analyzer_result}")
            if isinstance(stats_result, Exception):
                logger.error(f"   ❌ Statistics error: {stats_result}")

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
                logger.info(f"✅ Extracted {len(full_analysis['root_causes'])} root causes")

            logger.info(f"✅ Returning full analysis with {len(full_analysis)} fields")
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

    async def handle_rerun_workflow(self, request):
        """Rerun a workflow using pegasus-run"""
        workflow_id = request.match_info.get('workflow_id')

        try:
            logger.info(f"🔄 Rerun requested for workflow: {workflow_id}")

            # Get workflow submit directory from Monitor
            submit_dir = await self.get_workflow_submit_dir(workflow_id)

            if not submit_dir:
                logger.error(f"❌ No submit directory found for workflow {workflow_id}")
                return web.json_response({
                    "success": False,
                    "error": "Workflow submit directory not found"
                }, status=404)

            logger.info(f"📂 Submit directory: {submit_dir}")

            # Execute pegasus-run command
            import subprocess
            result = subprocess.run(
                ['pegasus-run', submit_dir],
                capture_output=True,
                text=True,
                timeout=60
            )

            success = result.returncode == 0

            if success:
                logger.info(f"✅ Workflow rerun started successfully")
            else:
                logger.error(f"❌ Workflow rerun failed: {result.stderr}")

            return web.json_response({
                "success": success,
                "workflow_id": workflow_id,
                "submit_dir": submit_dir,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timestamp": datetime.now().isoformat()
            })

        except subprocess.TimeoutExpired:
            logger.error(f"❌ Rerun timeout for workflow {workflow_id}")
            return web.json_response({
                "success": False,
                "error": "Rerun command timed out"
            }, status=500)
        except Exception as e:
            logger.error(f"❌ Error rerunning workflow: {e}")
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
        logger.info(f"  GET  /api/workflows/{{id}}/jobs")
        logger.info(f"  POST /api/workflows/{{id}}/rerun")
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

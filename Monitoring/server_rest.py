#!/usr/bin/env python3
"""
FIXED Enhanced Pegasus Workflow Monitoring Agent - Hybrid MCP + HTTP Architecture
Resolves thread/async issues with analysis requests
Save as: fixed_enhanced_monitor_agent.py
Run with: python fixed_enhanced_monitor_agent.py
"""

import asyncio
import json
import logging
import websockets
import os
import subprocess
import time
import glob
import fnmatch
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from tinydb import TinyDB, Query
from threading import Thread
from enum import Enum
import concurrent.futures
import aiohttp
from aiohttp import web, ClientSession
import uuid

# Configuration
WS_HOST = os.getenv("WS_HOST", "localhost")
WS_PORT = int(os.getenv("WS_PORT", "8765"))
HTTP_HOST = os.getenv("HTTP_HOST", "localhost")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize TinyDB
db = TinyDB("workflows.json")
workflows_table = db.table("workflows")
held_jobs_table = db.table("held_jobs")
agents_table = db.table("agents")

class TerminalColor(Enum):
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'
    MAGENTA = '\033[35m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_MAGENTA = '\033[95m'

    def apply(self, text):
        return f"{self.value}{text}{TerminalColor.RESET.value}"

class AgentRegistry:
    """Manages registry of known agents"""
    
    def __init__(self):
        self.agents = {}
        self.load_agents_from_db()

    def load_agents_from_db(self):
        """Load agents from database"""
        try:
            agents = agents_table.all()
            for agent in agents:
                self.agents[agent['agent_id']] = agent
        except Exception as e:
            logger.error(f"Error loading agents from DB: {e}")

    def register_agent(self, agent_id: str, agent_type: str, mcp_url: str, http_url: str, capabilities: List[str]) -> bool:
        """Register a new agent"""
        try:
            agent_info = {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "mcp_url": mcp_url,
                "http_url": http_url,
                "capabilities": capabilities,
                "registered_at": datetime.now().isoformat(),
                "last_health_check": None,
                "status": "unknown"
            }
            
            self.agents[agent_id] = agent_info
            agents_table.upsert(agent_info, Query().agent_id == agent_id)
            logger.info(f"Registered agent {agent_id} ({agent_type})")
            return True
        except Exception as e:
            logger.error(f"Error registering agent {agent_id}: {e}")
            return False

    def get_agents_by_type(self, agent_type: str) -> List[Dict[str, Any]]:
        """Get all agents of specific type"""
        return [agent for agent in self.agents.values() if agent.get('agent_type') == agent_type]

    async def health_check_agent(self, agent_id: str) -> bool:
        """Perform health check on specific agent"""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{agent['http_url']}/health") as resp:
                    if resp.status == 200:
                        health_data = await resp.json()
                        agent['status'] = 'healthy'
                        agent['last_health_check'] = datetime.now().isoformat()
                        agents_table.update(agent, Query().agent_id == agent_id)
                        return True
        except Exception as e:
            logger.debug(f"Health check failed for {agent_id}: {e}")
        
        agent['status'] = 'unhealthy'
        agent['last_health_check'] = datetime.now().isoformat()
        agents_table.update(agent, Query().agent_id == agent_id)
        return False

class PegasusWorkflowManager:
    def __init__(self, agent_registry: AgentRegistry, config: dict = None):
        self.registered_workflows = {}
        self.watchers = {}
        self.monitoring_active = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        self.agent_registry = agent_registry
        self.config = config or {}  # ENHANCED: Store config for auto-analysis
        self.create_logs_directory()

        # Enhanced notification system
        self.push_enabled = True
        self.analyzer_connections = set()
        self.known_failed_workflows = set()
        self.known_held_workflows = set()
        self.notification_queue = []
        self.analysis_requests = {}  # Track pending analysis requests

        # FIXED: Thread-safe analysis request queue
        self.pending_analysis_queue = []

    def create_logs_directory(self):
        """Create logs directory if it doesn't exist"""
        if not os.path.exists("logs"):
            os.makedirs("logs")

    def setup_logger(self, workflow_id=None):
        """Setup a logger for each workflow"""
        if workflow_id is None:
            workflow_logger = logging.getLogger("main_monitor")
            workflow_logger.setLevel(logging.DEBUG)
            handler = logging.FileHandler("logs/main_monitor.log")
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            if not workflow_logger.handlers:
                workflow_logger.addHandler(handler)
            return workflow_logger

        workflow_log_dir = f"logs/{workflow_id}"
        if not os.path.exists(workflow_log_dir):
            os.makedirs(workflow_log_dir)

        workflow_logger = logging.getLogger(workflow_id)
        workflow_logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(f"{workflow_log_dir}/{workflow_id}_monitor.log")
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        if not workflow_logger.handlers:
            workflow_logger.addHandler(handler)
        return workflow_logger

    # FIXED: Thread-safe method to queue analysis requests
    def schedule_analysis_request(self, workflow_id: str, workflow_dir: str, analysis_type: str):
        """Thread-safe method to schedule analysis request"""
        try:
            analysis_request = {
                "workflow_id": workflow_id,
                "workflow_dir": workflow_dir,
                "analysis_type": analysis_type,
                "timestamp": datetime.now().isoformat(),
                "request_id": str(uuid.uuid4())
            }
            
            self.pending_analysis_queue.append(analysis_request)
            logger.info(f"Queued analysis request for workflow {workflow_id} (type: {analysis_type})")
            
        except Exception as e:
            logger.error(f"Error queuing analysis request: {e}")

    async def request_workflow_analysis(self, workflow_id: str, workflow_dir: str, analysis_type: str = "failed") -> Dict[str, Any]:
        """Request analysis from analyzer agent via HTTP - ENHANCED with catalog context"""

        # STEP 1: Find available analyzer
        print(f"\n{'='*80}")
        print(f"{TerminalColor.BRIGHT_CYAN.apply('🔍 STEP 1: REQUESTING WORKFLOW ANALYSIS')}")
        print(f"{'='*80}")
        print(f"{TerminalColor.YELLOW.apply('Workflow ID:')} {workflow_id}")
        print(f"{TerminalColor.YELLOW.apply('Workflow Dir:')} {workflow_dir}")
        print(f"{TerminalColor.YELLOW.apply('Analysis Type:')} {analysis_type}")
        print(f"{'='*80}\n")

        print(f"  {TerminalColor.CYAN.apply('→ Step 1.1:')} Finding available Analyzer agent...")

        analyzers = self.agent_registry.get_agents_by_type("analyzer")

        if not analyzers:
            print(f"    {TerminalColor.RED.apply('✗')} No analyzer agents registered")
            print(f"{'='*80}\n")
            return {"error": "No analyzer agents available"}

        # Find a healthy analyzer
        healthy_analyzer = None
        for analyzer in analyzers:
            if await self.agent_registry.health_check_agent(analyzer['agent_id']):
                healthy_analyzer = analyzer
                print(f"    {TerminalColor.GREEN.apply('✓')} Found healthy analyzer: {analyzer['agent_id']}")
                print(f"    {TerminalColor.GREEN.apply('✓')} Analyzer URL: {analyzer['http_url']}")
                break

        if not healthy_analyzer:
            print(f"    {TerminalColor.RED.apply('✗')} No healthy analyzer agents available")
            print(f"{'='*80}\n")
            return {"error": "No healthy analyzer agents available"}

        # Generate analysis request ID
        request_id = str(uuid.uuid4())
        print(f"    {TerminalColor.GREEN.apply('✓')} Request ID: {request_id}")

        # STEP 2: Discover catalogs
        print(f"\n  {TerminalColor.CYAN.apply('→ Step 1.2:')} Discovering workflow catalogs...")
        catalogs = self.discover_catalogs(workflow_dir)

        # Count actual catalog discoveries (not metadata fields)
        catalog_types = ['replica_catalog', 'transformation_catalog', 'site_catalog']
        catalog_count = sum(1 for k in catalog_types if catalogs.get(k) is not None)

        if catalog_count > 0:
            print(f"    {TerminalColor.GREEN.apply('✓')} Found {catalog_count} catalog(s)")
            for cat_type in catalog_types:
                cat_info = catalogs.get(cat_type)
                if cat_info and isinstance(cat_info, dict):
                    print(f"      • {cat_type}: {cat_info.get('path', 'N/A')}")
        else:
            print(f"    {TerminalColor.YELLOW.apply('⚠')} No catalogs discovered")

        # STEP 2.5: Read workflow descriptor and generator files
        print(f"\n  {TerminalColor.CYAN.apply('→ Step 1.2.5:')} Reading workflow files...")
        workflow_files = self.read_workflow_files(workflow_dir)

        # Ensure workflow_files is always a dict
        if not isinstance(workflow_files, dict):
            workflow_files = {}

        if workflow_files.get('workflow_yaml'):
            wf_yaml = workflow_files['workflow_yaml']
            print(f"    {TerminalColor.GREEN.apply('✓')} Workflow descriptor: {wf_yaml['filename']}")
            print(f"      - Size: {wf_yaml['size']} bytes")

            # Show parsed structure summary
            parsed = wf_yaml.get('parsed_structure', {})
            if parsed:
                print(f"      - Parsed structure:")
                if parsed.get('jobs'):
                    print(f"        • Jobs: {len(parsed['jobs'])}")
                if parsed.get('transformations'):
                    print(f"        • Transformations: {len(parsed['transformations'])} (embedded)")
                if parsed.get('replicas'):
                    print(f"        • Replicas: {len(parsed['replicas'])} (embedded)")
                if parsed.get('sites'):
                    print(f"        • Sites: {len(parsed['sites'])} (embedded)")

        if workflow_files.get('generator_script'):
            print(f"    {TerminalColor.GREEN.apply('✓')} Generator script: {workflow_files['generator_script']['filename']}")
            print(f"      - Size: {workflow_files['generator_script']['size']} bytes")

        if workflow_files.get('braindump_metadata'):
            metadata = workflow_files['braindump_metadata']
            print(f"    {TerminalColor.GREEN.apply('✓')} Braindump metadata extracted:")
            if metadata.get('submit_dir'):
                print(f"      - Submit dir: {metadata['submit_dir']}")
            if metadata.get('dax'):
                print(f"      - DAX file: {metadata['dax']}")

        if not workflow_files.get('workflow_yaml') and not workflow_files.get('generator_script'):
            print(f"    {TerminalColor.YELLOW.apply('⚠')} No workflow files found")

        # STEP 2.6: Run pegasus-analyzer
        print(f"\n  {TerminalColor.CYAN.apply('→ Step 1.2.6:')} Running pegasus-analyzer...")
        pegasus_analyzer_output = self.run_pegasus_analyzer(workflow_dir)

        if pegasus_analyzer_output.get('ran'):
            print(f"    {TerminalColor.GREEN.apply('✓')} pegasus-analyzer completed (exit code: {pegasus_analyzer_output['exit_code']})")
            if pegasus_analyzer_output.get('parsed_issues'):
                print(f"      - Found {len(pegasus_analyzer_output['parsed_issues'])} issues")
                for issue in pegasus_analyzer_output['parsed_issues'][:3]:  # Show first 3
                    print(f"        • {issue}")
                if len(pegasus_analyzer_output['parsed_issues']) > 3:
                    print(f"        • ... and {len(pegasus_analyzer_output['parsed_issues']) - 3} more")
        else:
            print(f"    {TerminalColor.YELLOW.apply('⚠')} pegasus-analyzer not available or failed")
            if pegasus_analyzer_output.get('error'):
                print(f"      - Error: {pegasus_analyzer_output['error']}")

        # Send analysis request via HTTP
        print(f"\n  {TerminalColor.CYAN.apply('→ Step 1.3:')} Sending analysis request to Analyzer...")

        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                request_data = {
                    "workflow_id": workflow_id,
                    "workflow_dir": workflow_dir,
                    "analysis_type": analysis_type,
                    "request_id": request_id,
                    "requester": "monitor_agent",
                    "catalogs": catalogs,  # ENHANCED: Include catalog information
                    "workflow_files": workflow_files,  # ENHANCED: Include workflow descriptor and generator
                    "pegasus_analyzer": pegasus_analyzer_output  # ENHANCED: Include pegasus-analyzer output
                }

                # Print request payload
                print(f"\n  {TerminalColor.BRIGHT_BLUE.apply('📤 REQUEST PAYLOAD TO ANALYZER:')}")
                print(f"  {TerminalColor.BRIGHT_BLUE.apply('='*78)}")

                # Create a summary version for display (full data still sent in request)
                import json

                # Build workflow_files summary safely
                wf_summary = {}
                if workflow_files and isinstance(workflow_files, dict):
                    if workflow_files.get("workflow_yaml"):
                        wf = workflow_files["workflow_yaml"]
                        wf_summary["workflow_yaml"] = {
                            "filename": wf.get("filename"),
                            "size": wf.get("size"),
                            "content_included": "YES" if wf.get("content") else "NO",  # Show content is included
                            "content_preview": wf.get("content", "")[:200] + "..." if wf.get("content") else None,  # First 200 chars
                            "parsed_structure_summary": {
                                "jobs_count": len(wf.get("parsed_structure", {}).get("jobs", [])),
                                "transformations_count": len(wf.get("parsed_structure", {}).get("transformations", [])),
                                "replicas_count": len(wf.get("parsed_structure", {}).get("replicas", [])),
                                "sites_count": len(wf.get("parsed_structure", {}).get("sites", []))
                            }
                        }
                    if workflow_files.get("generator_script"):
                        gs = workflow_files["generator_script"]
                        wf_summary["generator_script"] = {
                            "filename": gs.get("filename"),
                            "size": gs.get("size"),
                            "content_included": "YES" if gs.get("content") else "NO"
                        }

                summary_data = {
                    "workflow_id": request_data["workflow_id"],
                    "workflow_dir": request_data["workflow_dir"],
                    "analysis_type": request_data["analysis_type"],
                    "request_id": request_data["request_id"],
                    "requester": request_data["requester"],
                    "catalogs": {
                        k: {"path": v.get("path"), "format": v.get("format"), "embedded": v.get("embedded")}
                        for k, v in catalogs.items() if v and isinstance(v, dict)  # FIX: Only include dict values
                    },
                    "workflow_files": wf_summary if wf_summary else {},
                    "pegasus_analyzer": {
                        "ran": pegasus_analyzer_output.get("ran", False),
                        "exit_code": pegasus_analyzer_output.get("exit_code"),
                        "output_included": "YES" if pegasus_analyzer_output.get("output") else "NO",  # Show output is included
                        "output_preview": pegasus_analyzer_output.get("output", "")[:300] + "..." if pegasus_analyzer_output.get("output") else None,  # First 300 chars
                        "issues_found": len(pegasus_analyzer_output.get("parsed_issues", [])),
                        "error": pegasus_analyzer_output.get("error")
                    }
                }

                print(f"  {json.dumps(summary_data, indent=2)}")
                print(f"  {TerminalColor.BRIGHT_BLUE.apply('='*78)}\n")

                url = f"{healthy_analyzer['http_url']}/api/analyze"
                async with session.post(url, json=request_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()

                        # Track pending request
                        self.analysis_requests[request_id] = {
                            "workflow_id": workflow_id,
                            "analyzer_id": healthy_analyzer['agent_id'],
                            "requested_at": datetime.now().isoformat(),
                            "status": "pending",
                            "catalogs_included": True
                        }

                        logger.info(f"Analysis requested for workflow {workflow_id} with catalog context (request_id: {request_id})")

                        print(f"    {TerminalColor.BRIGHT_GREEN.apply('✓')} Analysis request sent successfully")
                        print(f"    {TerminalColor.GREEN.apply('✓')} Response: HTTP {resp.status}")
                        print(f"    {TerminalColor.GREEN.apply('✓')} Status: {result.get('status', 'queued')}")
                        print(f"\n{'='*80}")
                        print(f"{TerminalColor.BRIGHT_GREEN.apply('✅ ANALYSIS REQUEST COMPLETED')}")
                        print(f"{'='*80}\n")

                        return {
                            "success": True,
                            "request_id": request_id,
                            "analyzer_id": healthy_analyzer['agent_id'],
                            "message": "Analysis request sent successfully with catalog context",
                            "catalogs_discovered": bool(catalogs.get('replica_catalog') or catalogs.get('transformation_catalog') or catalogs.get('site_catalog'))
                        }
                    else:
                        print(f"    {TerminalColor.RED.apply('✗')} Analysis request failed: HTTP {resp.status}")
                        print(f"{'='*80}\n")
                        return {"error": f"Analysis request failed: HTTP {resp.status}"}

        except Exception as e:
            logger.error(f"Error requesting analysis for {workflow_id}: {e}")
            print(f"    {TerminalColor.RED.apply('✗')} Error: {str(e)}")
            print(f"{'='*80}\n")
            return {"error": f"Failed to request analysis: {str(e)}"}

    async def handle_analysis_complete(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle analysis completion webhook"""
        try:
            request_id = analysis_data.get("request_id")
            workflow_id = analysis_data.get("workflow_id")

            # STEP 1: Received analysis completion
            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_GREEN.apply('📥 RECEIVED ANALYSIS COMPLETION FROM ANALYZER')}")
            print(f"{'='*80}")
            print(f"{TerminalColor.YELLOW.apply('Workflow ID:')} {workflow_id}")
            print(f"{TerminalColor.YELLOW.apply('Request ID:')} {request_id}")
            print(f"{TerminalColor.YELLOW.apply('Analysis Type:')} {analysis_data.get('analysis_type', 'N/A')}")
            print(f"{'='*80}\n")

            if request_id in self.analysis_requests:
                self.analysis_requests[request_id]["status"] = "completed"
                self.analysis_requests[request_id]["completed_at"] = datetime.now().isoformat()

                logger.info(f"Analysis completed for workflow {workflow_id} (request_id: {request_id})")

                # STEP 2: Print analysis result summary
                print(f"  {TerminalColor.CYAN.apply('→ Analysis Result Summary:')}")
                result = analysis_data.get('result', {})
                analysis = result.get('analysis', {})
                problems = analysis.get('problems_and_solutions', [])

                if problems:
                    print(f"    {TerminalColor.YELLOW.apply(f'Problems identified: {len(problems)}')}")
                    for idx, problem in enumerate(problems[:3], 1):  # Show first 3
                        print(f"      {idx}. {problem.get('problem', 'N/A')[:80]}")
                    if len(problems) > 3:
                        print(f"      ... and {len(problems) - 3} more")
                else:
                    print(f"    {TerminalColor.GREEN.apply('✓')} No critical problems identified")

                llm_used = result.get('llm_used', False)
                print(f"    {TerminalColor.CYAN.apply('LLM Analysis:')} {'✓ Used' if llm_used else '✗ Not used (fallback)'}")
                print(f"    {TerminalColor.CYAN.apply('Completed at:')} {analysis_data.get('completed_at', 'N/A')}")

                # STEP 3: Update workflow record
                print(f"\n  {TerminalColor.CYAN.apply('→ Updating workflow record...')}")
                workflows_table.update({
                    "analysis_status": "completed",
                    "analysis_completed_at": datetime.now().isoformat(),
                    "analysis_summary": analysis_data.get("summary", {})
                }, Query().workflow_id == workflow_id)
                print(f"    {TerminalColor.GREEN.apply('✓')} Workflow record updated")

                print(f"\n{'='*80}")
                print(f"{TerminalColor.BRIGHT_GREEN.apply('✅ ANALYSIS COMPLETION HANDLED SUCCESSFULLY')}")
                print(f"{'='*80}\n")

                return {"acknowledged": True, "workflow_id": workflow_id}
            else:
                logger.warning(f"Received analysis completion for unknown request_id: {request_id}")
                print(f"  {TerminalColor.RED.apply('✗')} Unknown request_id: {request_id}")
                print(f"{'='*80}\n")
                return {"acknowledged": False, "error": "Unknown request_id"}

        except Exception as e:
            logger.error(f"Error handling analysis completion: {e}")
            print(f"\n{'='*80}")
            print(f"{TerminalColor.RED.apply('❌ ERROR HANDLING ANALYSIS COMPLETION')}")
            print(f"{TerminalColor.RED.apply('Error:')} {str(e)}")
            print(f"{'='*80}\n")
            return {"acknowledged": False, "error": str(e)}

    # FIXED: Enhanced notification methods - removed async calls from sync context
    def notify_workflow_held_sync(self, workflow_id: str, workflow_dir: str, hold_data: Dict[str, Any]):
        """Synchronous notification for held workflow with analysis request"""
        workflow_key = f"{workflow_id}_{hold_data.get('job_id', 'unknown')}"
        
        if workflow_key in self.known_held_workflows:
            return  # Already notified

        self.known_held_workflows.add(workflow_key)
        
        notification_data = {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "status": "held",
            "hold_details": hold_data
        }

        self.queue_notification("workflow_held", notification_data)
        
        # FIXED: Use thread-safe scheduling instead of asyncio.create_task
        self.schedule_analysis_request(workflow_id, workflow_dir, "held")

    def notify_workflow_failed_sync(self, workflow_id: str, workflow_dir: str, failure_context: Dict[str, Any] = None):
        """Synchronous notification for failed workflow with analysis request"""
        if workflow_id in self.known_failed_workflows:
            return  # Already notified

        self.known_failed_workflows.add(workflow_id)
        
        notification_data = {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "status": "failed",
            "failure_context": failure_context or {}
        }

        self.queue_notification("workflow_failed", notification_data)
        
        # FIXED: Use thread-safe scheduling instead of asyncio.create_task
        self.schedule_analysis_request(workflow_id, workflow_dir, "failed")

    def queue_notification(self, notification_type: str, data: Dict[str, Any]):
        """Queue notification for later processing (thread-safe)"""
        notification = {
            "type": notification_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self.notification_queue.append(notification)
        logger.info(f"Queued {notification_type} notification for workflow {data.get('workflow_id')}")

    # MCP Tools for Inter-Agent Communication
    async def get_workflow_details_for_analysis(self, workflow_id: str) -> Dict[str, Any]:
        """MCP tool: Get detailed workflow information for analysis - ENHANCED with catalog discovery"""
        try:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if not workflow_record:
                return {"error": f"Workflow {workflow_id} not found"}

            workflow_dir = workflow_record['iwd']

            # Get current status
            status_data = await self.get_workflow_status(workflow_id)

            # Get log files
            log_files = self.find_workflow_log_files(workflow_dir, workflow_id)

            # Get recent error logs
            recent_errors = self.get_recent_error_logs(workflow_dir, hours=24)

            # ENHANCED: Discover catalog files
            catalogs = self.discover_catalogs(workflow_dir)

            # Print catalog discovery results to console
            print(f"\n{TerminalColor.CYAN.apply('📂 Catalog Discovery Results for')} {workflow_id}:")
            if catalogs.get('replica_catalog'):
                rc = catalogs['replica_catalog']
                print(f"  {TerminalColor.GREEN.apply('✓ Replica Catalog:')} {rc['path']} ({rc['format']}, {'embedded' if rc['embedded'] else 'separate file'})")
            else:
                print(f"  {TerminalColor.YELLOW.apply('⚠ Replica Catalog:')} Not found")

            if catalogs.get('transformation_catalog'):
                tc = catalogs['transformation_catalog']
                print(f"  {TerminalColor.GREEN.apply('✓ Transformation Catalog:')} {tc['path']} ({tc['format']}, {'embedded' if tc['embedded'] else 'separate file'})")
            else:
                print(f"  {TerminalColor.YELLOW.apply('⚠ Transformation Catalog:')} Not found")

            if catalogs.get('site_catalog'):
                sc = catalogs['site_catalog']
                print(f"  {TerminalColor.GREEN.apply('✓ Site Catalog:')} {sc['path']} ({sc['format']}, {'embedded' if sc['embedded'] else 'separate file'})")
            else:
                print(f"  {TerminalColor.YELLOW.apply('⚠ Site Catalog:')} Not found")

            if catalogs.get('embedded_in_workflow'):
                print(f"  {TerminalColor.BLUE.apply('ℹ Embedded catalogs detected in:')} {catalogs.get('workflow_file')}")
            print()

            return {
                "workflow_id": workflow_id,
                "workflow_dir": workflow_dir,
                "status": status_data,
                "log_files": log_files,
                "recent_errors": recent_errors,
                "catalogs": catalogs,  # ENHANCED: Include catalog information
                "database_record": workflow_record
            }
        except Exception as e:
            return {"error": f"Error getting workflow details: {str(e)}"}

    async def get_workflow_logs_content(self, workflow_id: str, log_type: str = "error", max_size: int = 10000) -> Dict[str, Any]:
        """MCP tool: Get actual log file content for analysis"""
        try:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if not workflow_record:
                return {"error": f"Workflow {workflow_id} not found"}
            
            workflow_dir = workflow_record['iwd']
            log_contents = []
            
            if log_type == "error":
                recent_errors = self.get_recent_error_logs(workflow_dir, hours=48)
                for error_log in recent_errors[:5]:  # Limit to 5 most recent
                    try:
                        with open(error_log['path'], 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(max_size)  # Limit content size
                            log_contents.append({
                                "file_path": error_log['path'],
                                "file_name": error_log['name'],
                                "content": content,
                                "size": error_log['size'],
                                "modified": error_log['modified']
                            })
                    except Exception as e:
                        log_contents.append({
                            "file_path": error_log['path'],
                            "error": f"Could not read file: {str(e)}"
                        })
            
            return {
                "workflow_id": workflow_id,
                "log_type": log_type,
                "log_contents": log_contents,
                "total_logs": len(log_contents)
            }
        except Exception as e:
            return {"error": f"Error getting log contents: {str(e)}"}

    async def acknowledge_analysis_completion(self, workflow_id: str, analysis_summary: Dict[str, Any]) -> Dict[str, Any]:
        """MCP tool: Acknowledge analysis completion from analyzer"""
        try:
            # Update workflow record
            workflows_table.update({
                "analysis_acknowledged": True,
                "analysis_acknowledged_at": datetime.now().isoformat(),
                "final_analysis_summary": analysis_summary
            }, Query().workflow_id == workflow_id)
            
            logger.info(f"Acknowledged analysis completion for workflow {workflow_id}")
            
            return {
                "acknowledged": True,
                "workflow_id": workflow_id,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": f"Error acknowledging analysis: {str(e)}"}

    # Catalog Discovery Methods
    def parse_workflow_yaml_structure(self, yaml_content: str) -> Dict[str, Any]:
        """Parse workflow YAML to extract structured information"""
        import yaml

        parsed_structure = {
            "jobs": [],
            "transformations": [],
            "replicas": [],
            "sites": [],
            "profiles": {},
            "catalog_locations": {}
        }

        try:
            workflow_data = yaml.safe_load(yaml_content)

            if not workflow_data:
                return parsed_structure

            # Extract jobs
            if 'jobs' in workflow_data:
                for job in workflow_data['jobs']:
                    parsed_structure['jobs'].append({
                        "id": job.get('id', job.get('name', 'unknown')),
                        "namespace": job.get('namespace', ''),
                        "name": job.get('name', ''),
                        "arguments": job.get('arguments', []),
                        "uses": job.get('uses', [])
                    })

            # Extract transformation catalog (if embedded)
            if 'transformationCatalog' in workflow_data or 'pegasus' in workflow_data:
                pegasus_section = workflow_data.get('pegasus', {})
                if 'transformations' in pegasus_section:
                    parsed_structure['catalog_locations']['transformation'] = 'embedded'
                    for trans in pegasus_section['transformations']:
                        parsed_structure['transformations'].append({
                            "namespace": trans.get('namespace', ''),
                            "name": trans.get('name', ''),
                            "version": trans.get('version', ''),
                            "site": trans.get('site', ''),
                            "pfn": trans.get('pfn', ''),
                            "type": trans.get('type', 'STAGEABLE')
                        })

            # Extract replica catalog (if embedded)
            if 'replicaCatalog' in workflow_data or ('pegasus' in workflow_data and 'replicas' in workflow_data['pegasus']):
                pegasus_section = workflow_data.get('pegasus', {})
                if 'replicas' in pegasus_section:
                    parsed_structure['catalog_locations']['replica'] = 'embedded'
                    for replica in pegasus_section['replicas']:
                        parsed_structure['replicas'].append({
                            "lfn": replica.get('lfn', ''),
                            "pfn": replica.get('pfn', ''),
                            "site": replica.get('site', 'local')
                        })

            # Extract site catalog (if embedded)
            if 'siteCatalog' in workflow_data or ('pegasus' in workflow_data and 'sites' in workflow_data['pegasus']):
                pegasus_section = workflow_data.get('pegasus', {})
                if 'sites' in pegasus_section:
                    parsed_structure['catalog_locations']['site'] = 'embedded'
                    for site in pegasus_section['sites']:
                        parsed_structure['sites'].append({
                            "name": site.get('name', ''),
                            "arch": site.get('arch', ''),
                            "os": site.get('os', ''),
                            "profiles": site.get('profiles', {})
                        })

            # Extract profiles
            if 'profiles' in workflow_data:
                parsed_structure['profiles'] = workflow_data['profiles']

        except Exception as e:
            logger.error(f"Error parsing workflow YAML structure: {e}")

        return parsed_structure

    def extract_braindump_metadata(self, workflow_dir: str) -> Dict[str, Any]:
        """Extract useful metadata from braindump.yml"""
        import yaml

        braindump_path = os.path.join(workflow_dir, "braindump.yml")
        metadata = {}

        if os.path.exists(braindump_path):
            try:
                with open(braindump_path, 'r') as f:
                    braindump = yaml.safe_load(f)
                    if braindump:
                        metadata = {
                            "submit_dir": braindump.get("submit_dir"),
                            "planner": braindump.get("planner"),
                            "planner_version": braindump.get("planner_version"),
                            "dax": braindump.get("dax"),
                            "dag": braindump.get("dag"),
                            "user": braindump.get("user"),
                            "root_wf_uuid": braindump.get("root_wf_uuid"),
                            "wf_uuid": braindump.get("wf_uuid")
                        }
                        logger.info(f"Extracted braindump metadata: submit_dir={metadata.get('submit_dir')}, dax={metadata.get('dax')}")
            except Exception as e:
                logger.error(f"Error reading braindump.yml: {e}")

        return metadata

    def read_workflow_files(self, workflow_dir: str) -> Dict[str, Any]:
        """Read workflow descriptor and generator files with parsed structure"""
        import glob

        workflow_files = {}

        if not workflow_dir or not os.path.exists(workflow_dir):
            logger.warning(f"Workflow directory does not exist: {workflow_dir}")
            return workflow_files

        # STEP 1: Extract braindump metadata
        braindump_metadata = self.extract_braindump_metadata(workflow_dir)
        if braindump_metadata:
            workflow_files['braindump_metadata'] = braindump_metadata

        # STEP 2: Find actual workflow descriptor (workflow.yml, dax.yml, or from braindump 'dax' field)
        yaml_files = glob.glob(os.path.join(workflow_dir, "*.yml")) + glob.glob(os.path.join(workflow_dir, "*.yaml"))
        logger.debug(f"Found {len(yaml_files)} YAML files in {workflow_dir}: {yaml_files}")

        # Priority 1: Look for workflow.yml or dax.yml
        workflow_yamls = [f for f in yaml_files if os.path.basename(f).lower() in ['workflow.yml', 'workflow.yaml', 'dax.yml', 'dax.yaml']]

        # Priority 2: Use 'dax' field from braindump if available
        if not workflow_yamls and braindump_metadata.get('dax'):
            dax_path = braindump_metadata['dax']
            if os.path.exists(dax_path):
                workflow_yamls = [dax_path]
                logger.info(f"Using workflow descriptor from braindump 'dax' field: {dax_path}")

        # Priority 3: Look for submit directory planned workflow
        if not workflow_yamls and braindump_metadata.get('submit_dir'):
            submit_dir = braindump_metadata['submit_dir']
            if os.path.exists(submit_dir):
                submit_yamls = glob.glob(os.path.join(submit_dir, "*.yml")) + glob.glob(os.path.join(submit_dir, "*.yaml"))
                workflow_yamls = [f for f in submit_yamls if 'workflow' in os.path.basename(f).lower() or 'dax' in os.path.basename(f).lower()]
                if workflow_yamls:
                    logger.info(f"Found workflow descriptor in submit dir: {workflow_yamls[0]}")

        # Priority 4: Exclude braindump.yml and take any remaining YAML
        if not workflow_yamls:
            workflow_yamls = [f for f in yaml_files if 'braindump' not in os.path.basename(f).lower()]
            if workflow_yamls:
                logger.info(f"Using first non-braindump YAML: {workflow_yamls[0]}")

        if workflow_yamls:
            try:
                with open(workflow_yamls[0], 'r') as f:
                    content = f.read()
                    original_size = len(content)

                    # Parse YAML structure BEFORE truncating
                    parsed_structure = self.parse_workflow_yaml_structure(content)

                    # Limit size to avoid excessive data transfer (max 5KB)
                    if len(content) > 5000:
                        content = content[:5000] + "\n... (truncated - file too large)"

                    workflow_files['workflow_yaml'] = {
                        "filename": os.path.basename(workflow_yamls[0]),
                        "path": workflow_yamls[0],
                        "content": content,
                        "size": len(content),
                        "original_size": original_size,
                        "type": "yaml",
                        "parsed_structure": parsed_structure  # ENHANCED: Include parsed structure
                    }
            except Exception as e:
                logger.error(f"Error reading workflow YAML: {e}")

        # Look for workflow generator Python script
        py_files = glob.glob(os.path.join(workflow_dir, "*.py"))
        logger.debug(f"Found {len(py_files)} Python files in {workflow_dir}: {py_files}")

        generator_scripts = [f for f in py_files if any(keyword in os.path.basename(f).lower()
                            for keyword in ['workflow', 'generate', 'dax', 'plan'])]

        # If no generator script found by keywords, take the first .py file
        if not generator_scripts and py_files:
            generator_scripts = [py_files[0]]
            logger.info(f"No generator script found by keywords, using first Python file: {generator_scripts[0]}")

        if generator_scripts:
            try:
                with open(generator_scripts[0], 'r') as f:
                    content = f.read()
                    # Limit size to avoid excessive data transfer (max 10KB)
                    if len(content) > 10000:
                        content = content[:10000] + "\n... (truncated - file too large)"

                    workflow_files['generator_script'] = {
                        "filename": os.path.basename(generator_scripts[0]),
                        "path": generator_scripts[0],
                        "content": content,
                        "size": len(content),
                        "type": "python"
                    }
            except Exception as e:
                logger.error(f"Error reading generator script: {e}")

        return workflow_files

    def run_pegasus_analyzer(self, workflow_dir: str) -> Dict[str, Any]:
        """Run pegasus-analyzer on the workflow and capture output"""
        import subprocess

        result = {
            "ran": False,
            "exit_code": None,
            "output": None,
            "error": None,
            "parsed_issues": []
        }

        # Check if pegasus-analyzer is available
        try:
            subprocess.run(["which", "pegasus-analyzer"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.warning("pegasus-analyzer command not found in PATH")
            result["error"] = "pegasus-analyzer not installed or not in PATH"
            return result

        # Run pegasus-analyzer on the workflow directory
        try:
            logger.info(f"Running pegasus-analyzer on {workflow_dir}")
            proc = subprocess.run(
                ["pegasus-analyzer", workflow_dir],
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )

            result["ran"] = True
            result["exit_code"] = proc.returncode
            result["output"] = proc.stdout
            result["error"] = proc.stderr

            # Parse common issues from output
            if proc.stdout:
                issues = []
                for line in proc.stdout.split('\n'):
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in ['error', 'failed', 'missing', 'not found', 'permission denied']):
                        issues.append(line.strip())
                result["parsed_issues"] = issues

            logger.info(f"pegasus-analyzer completed with exit code {proc.returncode}, found {len(result['parsed_issues'])} issues")

        except subprocess.TimeoutExpired:
            logger.error("pegasus-analyzer timed out after 30 seconds")
            result["error"] = "Timeout after 30 seconds"
        except Exception as e:
            logger.error(f"Error running pegasus-analyzer: {e}")
            result["error"] = str(e)

        return result

    def discover_catalogs(self, workflow_dir: str) -> Dict[str, Any]:
        """Discover all catalog files and their formats"""
        catalogs = {
            "replica_catalog": None,
            "transformation_catalog": None,
            "site_catalog": None,
            "catalog_format": {},
            "embedded_in_workflow": False
        }

        # 1. Check for braindump.txt (contains Pegasus config)
        braindump_path = os.path.join(workflow_dir, "braindump.txt")
        if os.path.exists(braindump_path):
            braindump_info = self.parse_braindump(braindump_path)
            catalogs.update(braindump_info)

        # 2. Search for common catalog file patterns
        catalog_patterns = {
            "replica_catalog": ["rc.txt", "rc.yml", "replicas.txt", "replicas.yml", "*replica*.txt"],
            "transformation_catalog": ["tc.txt", "tc.yml", "transformations.txt", "transformations.yml", "*trans*.txt"],
            "site_catalog": ["sites.xml", "sites.yml", "sites.yaml", "sc.txt", "site*.yml"]
        }

        for catalog_type, patterns in catalog_patterns.items():
            if not catalogs.get(catalog_type):  # Only search if not found in braindump
                found = self.find_catalog_file(workflow_dir, patterns)
                if found:
                    catalogs[catalog_type] = {
                        "path": found,
                        "format": self.detect_catalog_format(found),
                        "exists": True,
                        "writable": os.access(found, os.W_OK),
                        "source": "file",
                        "embedded": False
                    }

        # 3. Check if catalogs are embedded in workflow file
        workflow_file = self.find_main_workflow_file(workflow_dir)
        if workflow_file:
            embedded = self.check_embedded_catalogs(workflow_file)
            if any(embedded.values()):
                catalogs["embedded_in_workflow"] = True
                catalogs["workflow_file"] = workflow_file
                catalogs["embedded_catalogs"] = embedded

                # Add embedded catalog info
                if embedded.get("has_replica_catalog") and not catalogs.get("replica_catalog"):
                    catalogs["replica_catalog"] = {
                        "path": embedded.get("replica_catalog_path", "embedded.replicaCatalog"),
                        "format": "yaml",
                        "exists": True,
                        "writable": os.access(workflow_file, os.W_OK),
                        "source": "workflow_yaml",
                        "embedded": True,
                        "parent_file": workflow_file
                    }

                if embedded.get("has_transformation_catalog") and not catalogs.get("transformation_catalog"):
                    catalogs["transformation_catalog"] = {
                        "path": embedded.get("transformation_catalog_path", "embedded.transformationCatalog"),
                        "format": "yaml",
                        "exists": True,
                        "writable": os.access(workflow_file, os.W_OK),
                        "source": "workflow_yaml",
                        "embedded": True,
                        "parent_file": workflow_file
                    }

                if embedded.get("has_site_catalog") and not catalogs.get("site_catalog"):
                    catalogs["site_catalog"] = {
                        "path": embedded.get("site_catalog_path", "embedded.sites"),
                        "format": "yaml",
                        "exists": True,
                        "writable": os.access(workflow_file, os.W_OK),
                        "source": "workflow_yaml",
                        "embedded": True,
                        "parent_file": workflow_file
                    }

        return catalogs

    def parse_braindump(self, braindump_path: str) -> Dict[str, Any]:
        """Parse braindump.txt to find catalog locations"""
        braindump_data = {}

        try:
            with open(braindump_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    if 'replica' in line.lower() and '=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            catalog_path = parts[1].strip().strip('"\'')
                            if os.path.exists(catalog_path):
                                braindump_data['replica_catalog'] = {
                                    "path": catalog_path,
                                    "format": self.detect_catalog_format(catalog_path),
                                    "source": "braindump",
                                    "exists": True,
                                    "writable": os.access(catalog_path, os.W_OK),
                                    "embedded": False
                                }

                    elif ('transformation' in line.lower() or 'tc' in line.lower()) and '=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            catalog_path = parts[1].strip().strip('"\'')
                            if os.path.exists(catalog_path):
                                braindump_data['transformation_catalog'] = {
                                    "path": catalog_path,
                                    "format": self.detect_catalog_format(catalog_path),
                                    "source": "braindump",
                                    "exists": True,
                                    "writable": os.access(catalog_path, os.W_OK),
                                    "embedded": False
                                }

                    elif ('site' in line.lower() or 'sc' in line.lower()) and '=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            catalog_path = parts[1].strip().strip('"\'')
                            if os.path.exists(catalog_path):
                                braindump_data['site_catalog'] = {
                                    "path": catalog_path,
                                    "format": self.detect_catalog_format(catalog_path),
                                    "source": "braindump",
                                    "exists": True,
                                    "writable": os.access(catalog_path, os.W_OK),
                                    "embedded": False
                                }

        except Exception as e:
            logger.error(f"Error parsing braindump: {e}")

        return braindump_data

    def find_catalog_file(self, workflow_dir: str, patterns: List[str]) -> Optional[str]:
        """Find catalog file matching patterns"""
        # Search in workflow directory and parent
        search_dirs = [
            workflow_dir,
            os.path.dirname(workflow_dir),  # Parent directory
            os.path.join(workflow_dir, "submit"),  # Submit directory
        ]

        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue

            for pattern in patterns:
                matches = glob.glob(os.path.join(search_dir, pattern))
                if matches:
                    return matches[0]  # Return first match

        return None

    def detect_catalog_format(self, file_path: str) -> str:
        """Detect catalog file format"""
        if not os.path.exists(file_path):
            return "unknown"

        ext = os.path.splitext(file_path)[1].lower()

        if ext in ['.yml', '.yaml']:
            return "yaml"
        elif ext in ['.xml']:
            return "xml"
        elif ext in ['.txt']:
            try:
                with open(file_path, 'r') as f:
                    first_line = f.readline()
                    if first_line.startswith('#!') and 'python' in first_line:
                        return "python"
                    else:
                        return "text"
            except:
                return "text"
        else:
            return "text"

    def find_main_workflow_file(self, workflow_dir: str) -> Optional[str]:
        """Find the main workflow YAML/DAX file"""
        workflow_patterns = [
            "*.yml",
            "*.yaml",
            "*.dax",
            "workflow.yml",
            "pipeline.yml"
        ]

        for pattern in workflow_patterns:
            matches = glob.glob(os.path.join(workflow_dir, pattern))
            # Filter out pegasus-generated files
            matches = [m for m in matches if 'pegasus' not in os.path.basename(m).lower() and 'braindump' not in m]
            if matches:
                # Return the first non-pegasus file
                return matches[0]

        return None

    def check_embedded_catalogs(self, workflow_file: str) -> Dict[str, Any]:
        """Check if workflow YAML has embedded catalogs"""
        embedded = {
            "has_replica_catalog": False,
            "has_transformation_catalog": False,
            "has_site_catalog": False
        }

        try:
            import yaml

            with open(workflow_file, 'r') as f:
                workflow_data = yaml.safe_load(f)

            if not workflow_data:
                return embedded

            # Check for replica catalog section (various naming conventions)
            if 'replicaCatalog' in workflow_data or 'replicas' in workflow_data or 'x-pegasus' in workflow_data:
                if 'replicaCatalog' in workflow_data:
                    embedded["has_replica_catalog"] = True
                    embedded["replica_catalog_path"] = "replicaCatalog"
                elif 'replicas' in workflow_data:
                    embedded["has_replica_catalog"] = True
                    embedded["replica_catalog_path"] = "replicas"
                elif 'x-pegasus' in workflow_data and 'replicas' in workflow_data['x-pegasus']:
                    embedded["has_replica_catalog"] = True
                    embedded["replica_catalog_path"] = "x-pegasus.replicas"

            # Check for transformation catalog section
            if 'transformationCatalog' in workflow_data or 'transformations' in workflow_data:
                if 'transformationCatalog' in workflow_data:
                    embedded["has_transformation_catalog"] = True
                    embedded["transformation_catalog_path"] = "transformationCatalog"
                elif 'transformations' in workflow_data:
                    embedded["has_transformation_catalog"] = True
                    embedded["transformation_catalog_path"] = "transformations"

            # Check for site catalog section
            if 'siteCatalog' in workflow_data or 'sites' in workflow_data:
                if 'siteCatalog' in workflow_data:
                    embedded["has_site_catalog"] = True
                    embedded["site_catalog_path"] = "siteCatalog.sites"
                elif 'sites' in workflow_data:
                    embedded["has_site_catalog"] = True
                    embedded["site_catalog_path"] = "sites"

        except Exception as e:
            logger.error(f"Error checking embedded catalogs: {e}")

        return embedded

    # Keep all existing helper methods (no changes needed)
    def find_workflow_log_files(self, workflow_dir: str, workflow_id: str = None) -> Dict[str, Any]:
        """Find and categorize log files for a workflow"""
        if not os.path.exists(workflow_dir):
            return {"error": f"Workflow directory {workflow_dir} does not exist"}

        log_files = {
            "workflow_dir": workflow_dir,
            "workflow_id": workflow_id,
            "pegasus_logs": [],
            "condor_logs": [],
            "job_logs": [],
            "error_logs": [],
            "other_logs": [],
            "summary": {
                "total_files": 0,
                "total_size": 0,
                "categories": {}
            }
        }

        try:
            log_patterns = {
                "pegasus_logs": [
                    "pegasus*.log", "braindump.txt", "pegasus*.dag.log", 
                    "pegasus*.dag.dagman.out", "pegasus*.dag.dagman.log",
                    "pegasus*.dag.rescue*", "pegasus*.dag.sub.out"
                ],
                "condor_logs": [
                    "*.sub.log", "*.sub.out", "*.sub.err", 
                    "condor*.log", "*.condor.log"
                ],
                "error_logs": [
                    "*.err", "*.error", "*stderr*", "*failure*", 
                    "*.rescue*", "*held*", "*failed*"
                ],
                "job_logs": [
                    "*.out", "*.log", "*stdout*", "*output*",
                    "*job*.log", "*task*.log"
                ]
            }

            for root, dirs, files in os.walk(workflow_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, workflow_dir)

                    try:
                        stat_info = os.stat(file_path)
                        file_info = {
                            "name": file,
                            "path": file_path,
                            "relative_path": relative_path,
                            "size": stat_info.st_size,
                            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat_info.st_mtime)),
                            "category": "other"
                        }

                        categorized = False
                        for category, patterns in log_patterns.items():
                            if any(self._matches_pattern(file.lower(), pattern) for pattern in patterns):
                                log_files[category].append(file_info)
                                file_info["category"] = category
                                categorized = True
                                break

                        if not categorized:
                            if self._is_log_file(file):
                                log_files["other_logs"].append(file_info)
                                file_info["category"] = "other_logs"

                        log_files["summary"]["total_files"] += 1
                        log_files["summary"]["total_size"] += stat_info.st_size

                    except OSError:
                        continue

            for category in ["pegasus_logs", "condor_logs", "job_logs", "error_logs", "other_logs"]:
                log_files["summary"]["categories"][category] = len(log_files[category])

            return log_files

        except Exception as e:
            return {"error": f"Error scanning log files: {str(e)}"}

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Check if filename matches a glob pattern"""
        return fnmatch.fnmatch(filename, pattern.lower())

    def _is_log_file(self, filename: str) -> bool:
        """Determine if a file is likely a log file"""
        log_extensions = ['.log', '.out', '.err', '.txt', '.stdout', '.stderr']
        log_keywords = ['log', 'output', 'error', 'debug', 'trace', 'monitor']
        
        filename_lower = filename.lower()
        
        if any(filename_lower.endswith(ext) for ext in log_extensions):
            return True
        
        if any(keyword in filename_lower for keyword in log_keywords):
            return True
        
        return False

    def get_recent_error_logs(self, workflow_dir: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recently modified error/failure logs"""
        if not os.path.exists(workflow_dir):
            return []

        recent_errors = []
        cutoff_time = time.time() - (hours * 3600)

        error_patterns = ["*.err", "*.error", "*stderr*", "*failure*", "*.rescue*", "*held*", "*failed*"]
        
        for root, dirs, files in os.walk(workflow_dir):
            for file in files:
                file_path = os.path.join(root, file)
                
                if any(self._matches_pattern(file.lower(), pattern) for pattern in error_patterns):
                    try:
                        stat_info = os.stat(file_path)
                        if stat_info.st_mtime > cutoff_time:
                            recent_errors.append({
                                "path": file_path,
                                "name": file,
                                "relative_path": os.path.relpath(file_path, workflow_dir),
                                "size": stat_info.st_size,
                                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat_info.st_mtime)),
                                "preview": self._get_file_preview(file_path, max_lines=5)
                            })
                    except OSError:
                        continue

        recent_errors.sort(key=lambda x: x["modified"], reverse=True)
        return recent_errors

    def _get_file_preview(self, file_path: str, max_lines: int = 10) -> str:
        """Get a preview of file content"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... [showing first {max_lines} lines]")
                        break
                    lines.append(line.rstrip())
                return '\n'.join(lines)
        except Exception as e:
            return f"Error reading file: {str(e)}"

    # Keep all existing Pegasus methods unchanged
    async def get_workflow_status(self, workflow_id: str = None) -> Dict[str, Any]:
        """Get status of specific workflow or all workflows"""
        try:
            cmd = ["pegasus-status", "-j"]
            if workflow_id:
                workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
                if workflow_record:
                    cmd.append(workflow_record['iwd'])

            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: subprocess.run(cmd, capture_output=True, text=True, check=True)
            )
            data = json.loads(result.stdout)
            
            if workflow_id:
                workflow_data = data.get("condor_jobs", {}).get(workflow_id)
                if workflow_data:
                    return {"workflow_id": workflow_id, "data": workflow_data}
                return {"error": f"Workflow {workflow_id} not found"}
            
            return data
        except subprocess.CalledProcessError as e:
            return {"error": f"Pegasus status command failed: {e}"}
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse JSON output: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}

    async def get_workflow_details(self) -> List[tuple]:
        """Get list of active workflows"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: subprocess.run(["pegasus-status", "-j"], capture_output=True, text=True, check=True)
            )
            data = json.loads(result.stdout)
            workflows = []
            for wf_id, workflow_data in data.get("condor_jobs", {}).items():
                iwd = workflow_data.get("DAG_CONDOR_JOBS", [{}])[0].get("Iwd", "Unknown")
                workflows.append((wf_id, iwd))
            return workflows
        except Exception as e:
            logger.error(f"Error getting workflow details: {e}")
            return []

    async def start_monitoring_workflow(self, workflow_id: str, iwd: str):
        """Start monitoring a specific workflow"""
        if workflow_id not in self.registered_workflows:
            self.registered_workflows[workflow_id] = iwd
            watcher_thread = Thread(
                target=self.watch_workflow_sync, 
                args=(workflow_id, iwd), 
                daemon=True
            )
            self.watchers[workflow_id] = watcher_thread
            watcher_thread.start()
            return True
        return False

    def watch_workflow_sync(self, workflow_id: str, iwd: str):
        """FIXED: Enhanced workflow watcher - no more async calls from threads"""
        workflow_logger = self.setup_logger(workflow_id)
        retries = 0
        max_retries = 3

        while workflow_id in self.registered_workflows:
            try:
                result = subprocess.run(
                    ["pegasus-status", "-j", iwd],
                    capture_output=True,
                    text=True,
                    check=True
                )
                data = json.loads(result.stdout)

                totals = data.get("dags", {})
                percent_done = totals.get("root", {}).get("percent_done", 0.0)
                state = totals.get("root", {}).get("state", "unknown")

                workflows_table.upsert({
                    "workflow_id": workflow_id,
                    "iwd": iwd,
                    "state": state,
                    "percent_done": percent_done,
                    "last_checked": time.strftime("%Y-%m-%d %H:%M:%S")
                }, Query().workflow_id == workflow_id)

                # Check for held jobs
                held_jobs = [
                    job for job in data.get("condor_jobs", {}).values()
                    for job in job.get("DAG_CONDOR_JOBS", [])
                    if job.get("JobStatusName", "") == "Held"
                ]

                if held_jobs:
                    retries += 1
                    workflow_logger.warning(f"Workflow {workflow_id} has jobs in 'Held' state. Retry {retries}/{max_retries}.")
                    
                    recent_errors = self.get_recent_error_logs(iwd, hours=2)
                    
                    for job in held_jobs:
                        hold_data = {
                            "job_id": job.get("pegasus_wf_dag_job_id", "Unknown"),
                            "hold_reason": job.get("HoldReason", "No reason provided"),
                            "site": job.get("pegasus_site", "Unknown"),
                            "cmd": job.get("Cmd"),
                            "recent_error_logs": recent_errors[:3]
                        }
                        
                        # This is now thread-safe
                        self.notify_workflow_held_sync(workflow_id, iwd, hold_data)
                        
                        held_job_data = {
                            "workflow_id": workflow_id,
                            "job_id": job.get("pegasus_wf_dag_job_id", "Unknown"),
                            "status": job.get("JobStatusName", "Unknown"),
                            "hold_reason": job.get("HoldReason", "No reason provided"),
                            "site": job.get("pegasus_site", "Unknown"),
                            "cmd": job.get("Cmd"),
                            "workflow_dir": iwd,
                            "recent_error_logs": recent_errors[:5],
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        held_jobs_table.insert(held_job_data)

                    if recent_errors:
                        self.notify_new_error_logs_sync(workflow_id, iwd, recent_errors)

                    if retries >= max_retries:
                        workflow_logger.warning(f"Maximum retries reached for workflow {workflow_id}. Stopping workflow.")
                        subprocess.run(["pegasus-remove", iwd], check=True)
                        workflows_table.update({"state": "removed"}, Query().workflow_id == workflow_id)
                        self.remove_workflow(workflow_id)
                        break

            except Exception as e:
                workflow_logger.error(f"Error monitoring workflow {workflow_id}: {e}")
                break

            time.sleep(10)

    def notify_new_error_logs_sync(self, workflow_id: str, workflow_dir: str, error_logs: List[Dict[str, Any]]):
        """Synchronous notification for new error logs"""
        notification_data = {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "error_logs": error_logs,
            "count": len(error_logs)
        }

        self.queue_notification("new_error_logs", notification_data)

        # ENHANCED: Trigger analysis automatically if enabled
        if self.config.get("auto_analysis_enabled", False):
            # Check if workflow already in queue (deduplication)
            already_queued = any(req['workflow_id'] == workflow_id for req in self.pending_analysis_queue)

            if not already_queued:
                logger.info(f"Auto-analysis enabled: Queuing analysis request for workflow {workflow_id}")
                analysis_request = {
                    "workflow_id": workflow_id,
                    "workflow_dir": workflow_dir,
                    "analysis_type": "failure_analysis"
                }
                self.pending_analysis_queue.append(analysis_request)
                logger.info(f"Added workflow {workflow_id} to analysis queue (queue size: {len(self.pending_analysis_queue)})")
            else:
                logger.info(f"Workflow {workflow_id} already in analysis queue, skipping duplicate")

    def remove_workflow(self, workflow_id: str):
        """Remove workflow from monitoring"""
        if workflow_id in self.registered_workflows:
            del self.registered_workflows[workflow_id]
        if workflow_id in self.watchers:
            del self.watchers[workflow_id]

    async def stop_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Stop a specific workflow"""
        try:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if not workflow_record:
                return {"error": f"Workflow {workflow_id} not found in database"}

            iwd = workflow_record['iwd']
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: subprocess.run(["pegasus-remove", iwd], capture_output=True, text=True, check=True)
            )
            
            workflows_table.update({"state": "removed"}, Query().workflow_id == workflow_id)
            self.remove_workflow(workflow_id)
            return {"success": f"Workflow {workflow_id} stopped successfully"}
        except subprocess.CalledProcessError as e:
            return {"error": f"Failed to stop workflow: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error stopping workflow: {e}"}


class EnhancedPegasusMCPServer:
    """Enhanced MCP Server with HTTP + WebSocket hybrid architecture"""

    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"Config file {config_file} not found, using defaults")
                return {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def __init__(self, config_file: str = "monitor_config.json"):
        # Load configuration
        self.config = self.load_config(config_file)

        self.agent_registry = AgentRegistry()
        self.workflow_manager = PegasusWorkflowManager(self.agent_registry, self.config)
        self.auto_monitor_active = False
        self.auto_monitor_task = None
        self.monitor_interval = self.config.get("monitor_interval", 60)

        # Configuration settings
        self.http_port = self.config.get("http_port", 8080)
        self.mcp_port = self.config.get("mcp_port", 8765)
        
        # MCP tools for external clients and inter-agent communication
        self.tools = {
            # Original tools for external clients
            "get_workflow_status": {
                "name": "get_workflow_status",
                "description": "Get status of workflows",
                "inputSchema": {"type": "object", "properties": {"workflow_id": {"type": "string"}}}
            },
            "list_workflows": {
                "name": "list_workflows", 
                "description": "List all active workflows",
                "inputSchema": {"type": "object", "properties": {}}
            },
            "get_held_jobs": {
                "name": "get_held_jobs",
                "description": "Get held jobs information",
                "inputSchema": {"type": "object", "properties": {"workflow_id": {"type": "string"}}}
            },
            "get_monitor_status": {
                "name": "get_monitor_status",
                "description": "Get monitoring status",
                "inputSchema": {"type": "object", "properties": {}}
            },
            # New inter-agent tools
            "get_workflow_details_for_analysis": {
                "name": "get_workflow_details_for_analysis",
                "description": "Get detailed workflow information for analysis (inter-agent)",
                "inputSchema": {"type": "object", "properties": {"workflow_id": {"type": "string", "description": "Workflow ID to analyze"}}, "required": ["workflow_id"]}
            },
            "get_workflow_logs_content": {
                "name": "get_workflow_logs_content", 
                "description": "Get actual log file content for analysis (inter-agent)",
                "inputSchema": {
                    "type": "object", 
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID"},
                        "log_type": {"type": "string", "description": "Type of logs (error, all)", "default": "error"},
                        "max_size": {"type": "integer", "description": "Maximum content size per file", "default": 10000}
                    },
                    "required": ["workflow_id"]
                }
            },
            "acknowledge_analysis_completion": {
                "name": "acknowledge_analysis_completion",
                "description": "Acknowledge analysis completion from analyzer (inter-agent)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID"},
                        "analysis_summary": {"type": "object", "description": "Analysis summary"}
                    },
                    "required": ["workflow_id", "analysis_summary"]
                }
            }
        }
        
        self.connected_clients = set()
        
        # HTTP server components
        self.app = web.Application()
        self.setup_http_routes()
        
        # Register default analyzer (if known)
        self.register_default_agents()

    def register_default_agents(self):
        """Register default known agents"""
        # Register analyzer agent if known
        self.agent_registry.register_agent(
            "analyzer_001",
            "analyzer", 
            "ws://localhost:8766",
            "http://localhost:8081",
            ["failure_analysis", "hold_analysis", "log_analysis"]
        )

    def setup_http_routes(self):
        """Setup HTTP routes"""
        # Health endpoint
        self.app.router.add_get('/health', self.handle_health)
        
        # API endpoints
        self.app.router.add_get('/api/workflows', self.handle_get_workflows)
        self.app.router.add_get('/api/workflows/{workflow_id}/status', self.handle_get_workflow_status)
        self.app.router.add_post('/api/workflows/{workflow_id}/analyze', self.handle_request_analysis)
        
        # Webhook endpoints
        self.app.router.add_post('/webhooks/analysis-complete', self.handle_analysis_complete_webhook)
        
        # Agent registry endpoints
        self.app.router.add_get('/api/agents/registry', self.handle_get_agents)
        self.app.router.add_post('/api/agents/register', self.handle_register_agent)

    async def handle_health(self, request):
        """Health check endpoint"""
        try:
            return web.json_response({
                "status": "healthy",
                "agent_type": "monitor",
                "agent_id": "monitor_001",
                "uptime": time.time(),
                "mcp_server": {
                    "host": WS_HOST,
                    "port": WS_PORT,
                    "status": "running"
                },
                "monitoring": {
                    "active": self.auto_monitor_active,
                    "workflows_monitored": len(self.workflow_manager.registered_workflows),
                    "interval_seconds": self.monitor_interval
                },
                "agent_registry": {
                    "known_agents": len(self.agent_registry.agents),
                    "healthy_agents": len([a for a in self.agent_registry.agents.values() if a.get('status') == 'healthy'])
                },
                "capabilities": [
                    "workflow_monitoring",
                    "job_tracking", 
                    "log_analysis",
                    "failure_detection",
                    "analysis_coordination"
                ],
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    async def handle_get_workflows(self, request):
        """Get all workflows endpoint"""
        try:
            workflows = await self.workflow_manager.get_workflow_details()
            monitored = list(self.workflow_manager.registered_workflows.items())
            
            return web.json_response({
                "active_workflows": [{"workflow_id": wf_id, "iwd": iwd} for wf_id, iwd in workflows],
                "monitored_workflows": [{"workflow_id": wf_id, "iwd": iwd} for wf_id, iwd in monitored],
                "total_active": len(workflows),
                "total_monitored": len(monitored),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_get_workflow_status(self, request):
        """Get specific workflow status endpoint"""
        try:
            workflow_id = request.match_info['workflow_id']
            status = await self.workflow_manager.get_workflow_status(workflow_id)
            return web.json_response(status)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_request_analysis(self, request):
        """Request workflow analysis endpoint"""
        try:
            workflow_id = request.match_info['workflow_id']
            data = await request.json()
            analysis_type = data.get('analysis_type', 'failed')
            
            # Get workflow directory
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if not workflow_record:
                return web.json_response({"error": f"Workflow {workflow_id} not found"}, status=404)
            
            result = await self.workflow_manager.request_workflow_analysis(
                workflow_id, 
                workflow_record['iwd'], 
                analysis_type
            )
            
            if result.get('success'):
                return web.json_response(result)
            else:
                return web.json_response(result, status=400)
                
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_analysis_complete_webhook(self, request):
        """Handle analysis completion webhook"""
        try:
            data = await request.json()
            result = await self.workflow_manager.handle_analysis_complete(data)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_get_agents(self, request):
        """Get agent registry endpoint"""
        try:
            return web.json_response({
                "agents": list(self.agent_registry.agents.values()),
                "total_agents": len(self.agent_registry.agents),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_register_agent(self, request):
        """Register new agent endpoint"""
        try:
            data = await request.json()
            success = self.agent_registry.register_agent(
                data['agent_id'],
                data['agent_type'],
                data['mcp_url'],
                data['http_url'],
                data.get('capabilities', [])
            )
            
            if success:
                return web.json_response({"success": True, "message": f"Agent {data['agent_id']} registered"})
            else:
                return web.json_response({"success": False, "message": "Failed to register agent"}, status=400)
                
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # FIXED: Add the missing analysis queue processor
    async def process_analysis_queue(self):
        """Process queued analysis requests from threads"""
        while self.auto_monitor_active:
            try:
                if self.workflow_manager.pending_analysis_queue:
                    request = self.workflow_manager.pending_analysis_queue.pop(0)
                    logger.info(f"Processing queued analysis request for {request['workflow_id']}")
                    
                    result = await self.workflow_manager.request_workflow_analysis(
                        request["workflow_id"],
                        request["workflow_dir"], 
                        request["analysis_type"]
                    )
                    
                    if result.get("success"):
                        logger.info(f"Successfully processed analysis request for {request['workflow_id']}")
                    else:
                        logger.warning(f"Analysis request failed for {request['workflow_id']}: {result}")
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error processing analysis queue: {e}")
                await asyncio.sleep(10)

    # WebSocket MCP Server methods
    async def start_auto_monitoring(self):
        """Start automatic workflow discovery and monitoring"""
        if self.auto_monitor_active:
            return False
        
        self.auto_monitor_active = True
        self.auto_monitor_task = asyncio.create_task(self.auto_monitor_loop())
        logger.info(f"Started automatic monitoring with {self.monitor_interval}s interval")
        return True

    async def auto_monitor_loop(self):
        """Enhanced auto monitoring loop with health checks"""
        monitor_logger = self.workflow_manager.setup_logger()
        
        while self.auto_monitor_active:
            try:
                monitor_logger.info("Checking for new workflows...")
                workflows = await self.workflow_manager.get_workflow_details()
                
                for wf_id, iwd in workflows:
                    if wf_id not in self.workflow_manager.registered_workflows:
                        logger.info(f"Auto-discovered new workflow: {wf_id}")
                        monitor_logger.info(f"Auto-discovered new workflow: {wf_id} in {iwd}")
                        await self.workflow_manager.start_monitoring_workflow(wf_id, iwd)
                
                # Perform health checks on known agents
                for agent_id in list(self.agent_registry.agents.keys()):
                    await self.agent_registry.health_check_agent(agent_id)
                
                monitored_count = len(self.workflow_manager.registered_workflows)
                healthy_agents = len([a for a in self.agent_registry.agents.values() if a.get('status') == 'healthy'])
                
                logger.info(f"Currently monitoring {monitored_count} workflows")
                logger.info(f"Healthy agents: {healthy_agents}/{len(self.agent_registry.agents)}")
                
                await asyncio.sleep(self.monitor_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-monitor loop: {e}")
                await asyncio.sleep(10)

    async def handle_client(self, websocket):
        """Handle WebSocket MCP client connections"""
        self.connected_clients.add(websocket)
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"MCP Client connected: {client_id}")
        
        try:
            async for message in websocket:
                await self.process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"MCP Client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"Error handling MCP client {client_id}: {e}")
        finally:
            self.connected_clients.discard(websocket)

    async def process_message(self, websocket, message: str):
        """Process incoming MCP messages"""
        try:
            request = json.loads(message)
            tool_name = request.get("tool")
            args = request.get("args", {})

            # Handle different tool calls
            if tool_name == "ping":
                result = {
                    "message": "pong", 
                    "agent": "monitor",
                    "status": "active",
                    "monitored_workflows": len(self.workflow_manager.registered_workflows),
                    "timestamp": datetime.now().isoformat()
                }
            elif tool_name == "get_workflow_status":
                result = await self.workflow_manager.get_workflow_status(args.get("workflow_id"))
            elif tool_name == "list_workflows":
                workflows = await self.workflow_manager.get_workflow_details()
                monitored = list(self.workflow_manager.registered_workflows.items())
                result = {
                    "active_workflows": [{"workflow_id": wf_id, "iwd": iwd} for wf_id, iwd in workflows],
                    "monitored_workflows": [{"workflow_id": wf_id, "iwd": iwd} for wf_id, iwd in monitored],
                    "total_active": len(workflows),
                    "total_monitored": len(monitored)
                }
            elif tool_name == "get_held_jobs":
                result = await self.get_held_jobs_data(args.get("workflow_id"))
            elif tool_name == "get_monitor_status":
                result = {
                    "auto_monitoring_active": self.auto_monitor_active,
                    "monitor_interval": self.monitor_interval,
                    "monitored_workflows": len(self.workflow_manager.registered_workflows),
                    "notification_queue_size": len(self.workflow_manager.notification_queue),
                    "connected_clients": len(self.connected_clients)
                }
            # Inter-agent tools
            elif tool_name == "get_workflow_details_for_analysis":
                result = await self.workflow_manager.get_workflow_details_for_analysis(args.get("workflow_id"))
            elif tool_name == "get_workflow_logs_content":
                result = await self.workflow_manager.get_workflow_logs_content(
                    args.get("workflow_id"),
                    args.get("log_type", "error"),
                    args.get("max_size", 10000)
                )
            elif tool_name == "acknowledge_analysis_completion":
                result = await self.workflow_manager.acknowledge_analysis_completion(
                    args.get("workflow_id"),
                    args.get("analysis_summary", {})
                )
            else:
                result = {
                    "error": f"Unknown tool: {tool_name}",
                    "available_tools": list(self.tools.keys()) + ["ping"]
                }

            response = {
                "status": "success",
                "tool": tool_name,
                "result": result
            }
            await websocket.send(json.dumps(response))

        except json.JSONDecodeError as e:
            error_response = {"status": "error", "message": f"Invalid JSON: {str(e)}"}
            await websocket.send(json.dumps(error_response))
        except Exception as e:
            error_response = {"status": "error", "message": f"Error processing message: {str(e)}"}
            await websocket.send(json.dumps(error_response))

    async def get_held_jobs_data(self, workflow_id: str = None):
        """Get held jobs data"""
        try:
            query = Query()
            if workflow_id:
                held_jobs = held_jobs_table.search(query.workflow_id == workflow_id)
            else:
                held_jobs = held_jobs_table.all()[-100:]  # Last 100 entries
            
            return {
                "held_jobs": held_jobs,
                "total_count": len(held_jobs),
                "workflow_filter": workflow_id
            }
        except Exception as e:
            return {"error": f"Failed to get held jobs: {str(e)}"}

    async def verify_agent_connections(self):
        """Verify connections to other agents (non-blocking)"""
        print(f"\n{TerminalColor.BRIGHT_CYAN.apply('🔗 CHECKING AGENT CONNECTIONS')}")
        print(f"{'='*80}")
        print(f"{TerminalColor.YELLOW.apply('ℹ')} Agents may not be started yet - will retry periodically")

        # Check Analyzer connection
        analyzer_url = self.config.get("analyzer_url", "http://localhost:8081")
        print(f"\n{TerminalColor.CYAN.apply('→ Analyzer Agent:')} {analyzer_url}")
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get(f"{analyzer_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"  {TerminalColor.GREEN.apply('✓')} Status: Connected")
                    else:
                        print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not ready (HTTP {resp.status})")
        except Exception as e:
            print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not started yet")

        # Check Planner connection
        planner_url = self.config.get("planner_url", "http://localhost:8082")
        print(f"\n{TerminalColor.CYAN.apply('→ Planner Agent:')} {planner_url}")
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get(f"{planner_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"  {TerminalColor.GREEN.apply('✓')} Status: Connected")
                    else:
                        print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not ready (HTTP {resp.status})")
        except Exception as e:
            print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not started yet")

        # Check Executor connection (future)
        executor_url = self.config.get("executor_url", "http://localhost:8083")
        print(f"\n{TerminalColor.CYAN.apply('→ Executor Agent:')} {executor_url}")
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get(f"{executor_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"  {TerminalColor.GREEN.apply('✓')} Status: Connected")
                    else:
                        print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not ready (HTTP {resp.status})")
        except Exception as e:
            print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not started yet")

        print(f"\n{'='*80}")

    async def periodic_agent_health_checks(self):
        """Periodically check connections to other agents"""
        await asyncio.sleep(10)  # Wait 10 seconds before first check

        while True:
            try:
                await asyncio.sleep(self.config.get("health_check_interval", 60))

                # Silent health checks - only log changes
                agents_status = {}

                # Check Analyzer
                analyzer_url = self.config.get("analyzer_url", "http://localhost:8081")
                try:
                    async with ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                        async with session.get(f"{analyzer_url}/health") as resp:
                            agents_status['analyzer'] = (resp.status == 200)
                except:
                    agents_status['analyzer'] = False

                # Check Planner
                planner_url = self.config.get("planner_url", "http://localhost:8082")
                try:
                    async with ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                        async with session.get(f"{planner_url}/health") as resp:
                            agents_status['planner'] = (resp.status == 200)
                except:
                    agents_status['planner'] = False

                # Check Executor
                executor_url = self.config.get("executor_url", "http://localhost:8083")
                try:
                    async with ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                        async with session.get(f"{executor_url}/health") as resp:
                            agents_status['executor'] = (resp.status == 200)
                except:
                    agents_status['executor'] = False

                # Log status summary
                connected = sum(1 for status in agents_status.values() if status)
                logger.info(f"Agent health check: {connected}/{len(agents_status)} agents available")

                # Log individual agent status changes
                for agent, status in agents_status.items():
                    if hasattr(self, '_last_agent_status'):
                        if self._last_agent_status.get(agent) != status:
                            if status:
                                print(f"{TerminalColor.GREEN.apply('✓')} {agent.capitalize()} agent connected")
                            else:
                                print(f"{TerminalColor.YELLOW.apply('○')} {agent.capitalize()} agent disconnected")

                self._last_agent_status = agents_status

            except Exception as e:
                logger.error(f"Error in periodic agent health checks: {e}")

    async def start_servers(self):
        """Start both HTTP and WebSocket servers"""
        # Use config ports, fallback to env vars or defaults
        http_port = self.http_port
        mcp_port = self.mcp_port
        http_host = "localhost"
        ws_host = "localhost"

        logger.info(f"Starting FIXED Enhanced Pegasus Monitor Agent")
        logger.info(f"WebSocket MCP Server: ws://{ws_host}:{mcp_port}")
        logger.info(f"HTTP API Server: http://{http_host}:{http_port}")

        # Verify connections to other agents
        await self.verify_agent_connections()

        # Start auto monitoring
        await self.start_auto_monitoring()

        # FIXED: Start the analysis queue processor
        asyncio.create_task(self.process_analysis_queue())

        # Start periodic agent health checks
        asyncio.create_task(self.periodic_agent_health_checks())

        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, http_host, http_port)
        await site.start()
        logger.info(f"HTTP server started on http://{http_host}:{http_port}")

        # Start WebSocket MCP server
        websocket_server = await websockets.serve(
            self.handle_client,
            ws_host,
            mcp_port,
            ping_interval=20,
            ping_timeout=10
        )
        logger.info(f"WebSocket MCP server started on ws://{ws_host}:{mcp_port}")

        # Print startup summary
        print(f"\n{TerminalColor.BRIGHT_GREEN.apply('✓ Enhanced Monitor Agent Started')}")
        print(f"{'='*80}")
        print(f"{TerminalColor.CYAN.apply('🌐 HTTP API:')} http://{http_host}:{http_port}")
        print(f"{TerminalColor.CYAN.apply('🔌 MCP WebSocket:')} ws://{ws_host}:{mcp_port}")
        print(f"{TerminalColor.CYAN.apply('📊 Known agents:')} {len(self.agent_registry.agents)}")
        print(f"{TerminalColor.CYAN.apply('🔍 Auto-monitoring:')} {self.auto_monitor_active}")
        print(f"{TerminalColor.CYAN.apply('⏱️  Monitor interval:')} {self.monitor_interval}s")
        print(f"{TerminalColor.CYAN.apply('🔧 Analysis queue processor:')} Running")

        print(f"\n{TerminalColor.BRIGHT_CYAN.apply('📋 Available HTTP Endpoints:')}")
        print(f"   GET  /health - Agent health status")
        print(f"   GET  /api/workflows - List workflows")
        print(f"   POST /api/workflows/{{id}}/analyze - Request analysis")
        print(f"   POST /webhooks/analysis-complete - Analysis webhook")
        print(f"   GET  /api/agents/registry - Agent registry")

        print(f"\n{TerminalColor.BRIGHT_CYAN.apply('🔗 Connected Agents:')}")
        print(f"   Analyzer: {self.config.get('analyzer_url', 'http://localhost:8081')}")
        print(f"   Planner: {self.config.get('planner_url', 'http://localhost:8082')}")
        print(f"   Executor: {self.config.get('executor_url', 'http://localhost:8083')}")

        print(f"\n{TerminalColor.CYAN.apply('Press Ctrl+C to stop')}")
        print(f"{'='*80}\n")
        
        try:
            await websocket_server.wait_closed()
        except KeyboardInterrupt:
            logger.info("Shutting down servers...")
            self.auto_monitor_active = False
            websocket_server.close()
            await websocket_server.wait_closed()
            await runner.cleanup()


async def main():
    server = EnhancedPegasusMCPServer()
    await server.start_servers()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{TerminalColor.YELLOW.apply('👋')} FIXED Enhanced Monitor Agent shutting down...")
    except Exception as e:
        print(f"{TerminalColor.RED.apply('❌')} Error: {e}")
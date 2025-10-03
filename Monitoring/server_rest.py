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
    WHITE = '\033[97m'
    RESET = '\033[0m'

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
    def __init__(self, agent_registry: AgentRegistry):
        self.registered_workflows = {}
        self.watchers = {}
        self.monitoring_active = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        self.agent_registry = agent_registry
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
        """Request analysis from analyzer agent via HTTP"""
        analyzers = self.agent_registry.get_agents_by_type("analyzer")
        
        if not analyzers:
            return {"error": "No analyzer agents available"}
        
        # Find a healthy analyzer
        healthy_analyzer = None
        for analyzer in analyzers:
            if await self.agent_registry.health_check_agent(analyzer['agent_id']):
                healthy_analyzer = analyzer
                break
        
        if not healthy_analyzer:
            return {"error": "No healthy analyzer agents available"}
        
        # Generate analysis request ID
        request_id = str(uuid.uuid4())
        
        # Send analysis request via HTTP
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                request_data = {
                    "workflow_id": workflow_id,
                    "workflow_dir": workflow_dir,
                    "analysis_type": analysis_type,
                    "request_id": request_id,
                    "requester": "monitor_agent"
                }
                
                url = f"{healthy_analyzer['http_url']}/api/analyze"
                async with session.post(url, json=request_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        
                        # Track pending request
                        self.analysis_requests[request_id] = {
                            "workflow_id": workflow_id,
                            "analyzer_id": healthy_analyzer['agent_id'],
                            "requested_at": datetime.now().isoformat(),
                            "status": "pending"
                        }
                        
                        logger.info(f"Analysis requested for workflow {workflow_id} (request_id: {request_id})")
                        return {
                            "success": True,
                            "request_id": request_id,
                            "analyzer_id": healthy_analyzer['agent_id'],
                            "message": "Analysis request sent successfully"
                        }
                    else:
                        return {"error": f"Analysis request failed: HTTP {resp.status}"}
                        
        except Exception as e:
            logger.error(f"Error requesting analysis for {workflow_id}: {e}")
            return {"error": f"Failed to request analysis: {str(e)}"}

    async def handle_analysis_complete(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle analysis completion webhook"""
        try:
            request_id = analysis_data.get("request_id")
            workflow_id = analysis_data.get("workflow_id")
            
            if request_id in self.analysis_requests:
                self.analysis_requests[request_id]["status"] = "completed"
                self.analysis_requests[request_id]["completed_at"] = datetime.now().isoformat()
                
                logger.info(f"Analysis completed for workflow {workflow_id} (request_id: {request_id})")
                
                # Update workflow record with analysis results
                workflows_table.update({
                    "analysis_status": "completed",
                    "analysis_completed_at": datetime.now().isoformat(),
                    "analysis_summary": analysis_data.get("summary", {})
                }, Query().workflow_id == workflow_id)
                
                return {"acknowledged": True, "workflow_id": workflow_id}
            else:
                logger.warning(f"Received analysis completion for unknown request_id: {request_id}")
                return {"acknowledged": False, "error": "Unknown request_id"}
                
        except Exception as e:
            logger.error(f"Error handling analysis completion: {e}")
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
        """MCP tool: Get detailed workflow information for analysis"""
        try:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if not workflow_record:
                return {"error": f"Workflow {workflow_id} not found"}
            
            # Get current status
            status_data = await self.get_workflow_status(workflow_id)
            
            # Get log files
            log_files = self.find_workflow_log_files(workflow_record['iwd'], workflow_id)
            
            # Get recent error logs
            recent_errors = self.get_recent_error_logs(workflow_record['iwd'], hours=24)
            
            return {
                "workflow_id": workflow_id,
                "workflow_dir": workflow_record['iwd'],
                "status": status_data,
                "log_files": log_files,
                "recent_errors": recent_errors,
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
    
    def __init__(self):
        self.agent_registry = AgentRegistry()
        self.workflow_manager = PegasusWorkflowManager(self.agent_registry)
        self.auto_monitor_active = False
        self.auto_monitor_task = None
        self.monitor_interval = 60
        
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

    async def start_servers(self):
        """Start both HTTP and WebSocket servers"""
        logger.info(f"Starting FIXED Enhanced Pegasus Monitor Agent")
        logger.info(f"WebSocket MCP Server: ws://{WS_HOST}:{WS_PORT}")
        logger.info(f"HTTP API Server: http://{HTTP_HOST}:{HTTP_PORT}")
        
        # Start auto monitoring
        await self.start_auto_monitoring()
        
        # FIXED: Start the analysis queue processor
        asyncio.create_task(self.process_analysis_queue())
        
        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
        await site.start()
        logger.info(f"HTTP server started on http://{HTTP_HOST}:{HTTP_PORT}")
        
        # Start WebSocket MCP server
        websocket_server = await websockets.serve(
            self.handle_client,
            WS_HOST,
            WS_PORT,
            ping_interval=20,
            ping_timeout=10
        )
        logger.info(f"WebSocket MCP server started on ws://{WS_HOST}:{WS_PORT}")
        
        # Print startup summary
        print(f"\n{TerminalColor.GREEN.apply('✓')} FIXED Enhanced Monitor Agent Started")
        print(f"🌐 HTTP API: http://{HTTP_HOST}:{HTTP_PORT}")
        print(f"🔌 MCP WebSocket: ws://{WS_HOST}:{WS_PORT}")
        print(f"📊 Known agents: {len(self.agent_registry.agents)}")
        print(f"🔍 Auto-monitoring: {self.auto_monitor_active}")
        print(f"🔧 Analysis queue processor: Running")
        print(f"📋 Available HTTP endpoints:")
        print(f"   GET  /health - Agent health status")
        print(f"   GET  /api/workflows - List workflows")
        print(f"   POST /api/workflows/{{id}}/analyze - Request analysis")
        print(f"   POST /webhooks/analysis-complete - Analysis webhook")
        print(f"   GET  /api/agents/registry - Agent registry")
        print(f"\n{TerminalColor.CYAN.apply('Press Ctrl+C to stop')}")
        
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
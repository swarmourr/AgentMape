#!/usr/bin/env python3
"""
Fixed Pegasus Workflow Monitoring MCP Server - Resolves async threading issues
Save as: fixed_monitor_agent.py
Run with: python fixed_monitor_agent.py
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
from datetime import datetime
from tinydb import TinyDB, Query
from threading import Thread
from enum import Enum
import concurrent.futures

# Configuration
WS_HOST = os.getenv("WS_HOST", "localhost")
WS_PORT = int(os.getenv("WS_PORT", "8765"))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize TinyDB
db = TinyDB("workflows.json")
workflows_table = db.table("workflows")
held_jobs_table = db.table("held_jobs")

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

class PegasusWorkflowManager:
    def __init__(self):
        self.registered_workflows = {}
        self.watchers = {}
        self.monitoring_active = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        self.create_logs_directory()
        
        # Push notification system (simplified - no async issues)
        self.push_enabled = True
        self.analyzer_connections = set()
        self.known_failed_workflows = set()
        self.known_held_workflows = set()
        self.notification_queue = []  # Simple queue instead of async

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

    # FIXED: Simple notification methods (no async)
    def queue_notification(self, notification_type: str, data: Dict[str, Any]):
        """Queue notification for later processing (thread-safe)"""
        notification = {
            "type": notification_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self.notification_queue.append(notification)
        logger.info(f"Queued {notification_type} notification for workflow {data.get('workflow_id')}")

    def notify_workflow_held_sync(self, workflow_id: str, workflow_dir: str, hold_data: Dict[str, Any]):
        """Synchronous notification for held workflow"""
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

    def notify_workflow_failed_sync(self, workflow_id: str, workflow_dir: str, failure_context: Dict[str, Any] = None):
        """Synchronous notification for failed workflow"""
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

    def notify_new_error_logs_sync(self, workflow_id: str, workflow_dir: str, error_logs: List[Dict[str, Any]]):
        """Synchronous notification for new error logs"""
        notification_data = {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "error_logs": error_logs,
            "count": len(error_logs)
        }

        self.queue_notification("new_error_logs", notification_data)

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
        """FIXED: Enhanced workflow watcher without async issues"""
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
                    
                    # FIXED: Use synchronous notification methods
                    for job in held_jobs:
                        hold_data = {
                            "job_id": job.get("pegasus_wf_dag_job_id", "Unknown"),
                            "hold_reason": job.get("HoldReason", "No reason provided"),
                            "site": job.get("pegasus_site", "Unknown"),
                            "cmd": job.get("Cmd"),
                            "recent_error_logs": recent_errors[:3]
                        }
                        
                        # FIXED: No more async calls from threads
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

                    # FIXED: Synchronous error logs notification
                    if recent_errors:
                        self.notify_new_error_logs_sync(workflow_id, iwd, recent_errors)

                    if retries >= max_retries:
                        workflow_logger.warning(f"Maximum retries reached for workflow {workflow_id}. Stopping workflow.")
                        subprocess.run(["pegasus-remove", iwd], check=True)
                        workflows_table.update({"state": "removed"}, Query().workflow_id == workflow_id)
                        self.remove_workflow(workflow_id)
                        break
                else:
                    retries = 0

                # Check for workflow completion/failure
                if state in ["Success", "Failure"]:
                    workflow_logger.info(f"Workflow {workflow_id} completed with state {state}.")
                    workflows_table.update({"state": state}, Query().workflow_id == workflow_id)
                    
                    if state == "Failure":
                        final_logs = self.find_workflow_log_files(iwd, workflow_id)
                        workflows_table.update({
                            "state": state,
                            "final_log_summary": final_logs.get("summary", {})
                        }, Query().workflow_id == workflow_id)
                        
                        # FIXED: Synchronous failure notification
                        failure_context = {
                            "final_state": state,
                            "percent_completed": percent_done,
                            "log_summary": final_logs.get("summary", {}),
                            "error_logs": final_logs.get("error_logs", [])[:5]
                        }
                        
                        self.notify_workflow_failed_sync(workflow_id, iwd, failure_context)
                    
                    self.remove_workflow(workflow_id)
                    break

            except Exception as e:
                workflow_logger.error(f"Error monitoring workflow {workflow_id}: {e}")
                break

            time.sleep(10)

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

class FixedPegasusMCPServer:
    """Fixed MCP Server without async threading issues"""
    
    def __init__(self):
        self.workflow_manager = PegasusWorkflowManager()
        self.auto_monitor_active = False
        self.auto_monitor_task = None
        self.monitor_interval = 60
        
        self.tools = {
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
            }
        }
        
        self.connected_clients = set()

    async def start_auto_monitoring(self):
        """Start automatic workflow discovery and monitoring"""
        if self.auto_monitor_active:
            return False
        
        self.auto_monitor_active = True
        self.auto_monitor_task = asyncio.create_task(self.auto_monitor_loop())
        logger.info(f"Started automatic monitoring with {self.monitor_interval}s interval")
        return True

    async def auto_monitor_loop(self):
        """Enhanced auto monitoring loop"""
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
                
                monitored_count = len(self.workflow_manager.registered_workflows)
                logger.info(f"Currently monitoring {monitored_count} workflows")
                logger.info(f"Connected analyzers: {len(self.workflow_manager.analyzer_connections)}")
                
                await asyncio.sleep(self.monitor_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-monitor loop: {e}")
                await asyncio.sleep(10)

    async def handle_client(self, websocket):
        """Handle client connections"""
        self.connected_clients.add(websocket)
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"Client connected: {client_id}")
        
        try:
            async for message in websocket:
                await self.process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            self.connected_clients.discard(websocket)

    async def process_message(self, websocket, message: str):
        """Process incoming messages"""
        try:
            request = json.loads(message)
            tool_name = request.get("tool")
            args = request.get("args", {})

            # Handle ping from analyzer
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
            elif tool_name == "analysis_completed":
                # Handle notifications from analyzer
                result = {
                    "received": "analysis_completed_notification",
                    "workflow_id": args.get("workflow_id"),
                    "analysis_type": args.get("analysis_type"),
                    "timestamp": datetime.now().isoformat()
                }
                logger.info(f"Received analysis completion notification for workflow {args.get('workflow_id')}")
            else:
                result = {
                    "error": f"Unknown tool: {tool_name}",
                    "available_tools": list(self.tools.keys()) + ["ping", "analysis_completed"]
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

    async def start_server(self):
        """Start the fixed WebSocket server"""
        logger.info(f"Starting Fixed Pegasus Monitor on {WS_HOST}:{WS_PORT}")
        
        await self.start_auto_monitoring()
        
        server = await websockets.serve(
            self.handle_client,
            WS_HOST,
            WS_PORT,
            ping_interval=20,
            ping_timeout=10
        )
        
        logger.info(f"Server listening on ws://{WS_HOST}:{WS_PORT}")
        logger.info("Fixed version - no async threading issues")
        logger.info("Press Ctrl+C to stop")
        
        try:
            await server.wait_closed()
        except KeyboardInterrupt:
            logger.info("Shutting down server...")
            self.auto_monitor_active = False
            server.close()
            await server.wait_closed()

async def main():
    server = FixedPegasusMCPServer()
    await server.start_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
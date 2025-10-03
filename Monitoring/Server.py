#!/usr/bin/env python3
"""
Pegasus Workflow Monitoring MCP Server - Enhanced with Log File Discovery
Save as: pegasus_mcp_server_enhanced.py
Run with: python pegasus_mcp_server_enhanced.py
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
WS_PORT = int(os.getenv("WS_PORT", "8766"))

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
            # Define log file patterns and categories
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

            # Scan all files recursively
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

                        # Categorize the file
                        categorized = False
                        for category, patterns in log_patterns.items():
                            if any(self._matches_pattern(file.lower(), pattern) for pattern in patterns):
                                log_files[category].append(file_info)
                                file_info["category"] = category
                                categorized = True
                                break

                        if not categorized:
                            # Check if it's a log file by extension or content
                            if self._is_log_file(file):
                                log_files["other_logs"].append(file_info)
                                file_info["category"] = "other_logs"

                        log_files["summary"]["total_files"] += 1
                        log_files["summary"]["total_size"] += stat_info.st_size

                    except OSError:
                        continue

            # Update category counts
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
        
        # Check extensions
        if any(filename_lower.endswith(ext) for ext in log_extensions):
            return True
        
        # Check keywords in filename
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
                
                # Check if matches error pattern
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

        # Sort by modification time (most recent first)
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
                # Add specific workflow directory if available
                workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
                if workflow_record:
                    cmd.append(workflow_record['iwd'])

            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: subprocess.run(cmd, capture_output=True, text=True, check=True)
            )
            data = json.loads(result.stdout)
            
            if workflow_id:
                # Return specific workflow data
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
            # Start monitoring in thread
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
        """Synchronous workflow watcher (runs in thread) - Enhanced with log discovery"""
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

                # Extract workflow details
                totals = data.get("dags", {})
                percent_done = totals.get("root", {}).get("percent_done", 0.0)
                state = totals.get("root", {}).get("state", "unknown")

                # Update workflow in database
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
                    
                    # Find recent error logs when jobs are held
                    recent_errors = self.get_recent_error_logs(iwd, hours=2)
                    
                    # Save held job details with log file information
                    for job in held_jobs:
                        held_job_data = {
                            "workflow_id": workflow_id,
                            "job_id": job.get("pegasus_wf_dag_job_id", "Unknown"),
                            "status": job.get("JobStatusName", "Unknown"),
                            "hold_reason": job.get("HoldReason", "No reason provided"),
                            "site": job.get("pegasus_site", "Unknown"),
                            "cmd": job.get("Cmd"),
                            "workflow_dir": iwd,
                            "recent_error_logs": recent_errors[:5],  # Store up to 5 recent error logs
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        held_jobs_table.insert(held_job_data)

                    workflow_logger.warning(f"Found {len(recent_errors)} recent error logs for workflow {workflow_id}")
                    for error_log in recent_errors[:3]:  # Log first 3 error files
                        workflow_logger.warning(f"Error log: {error_log['relative_path']} (modified: {error_log['modified']})")

                    if retries >= max_retries:
                        workflow_logger.warning(f"Maximum retries reached for workflow {workflow_id}. Stopping workflow.")
                        subprocess.run(["pegasus-remove", iwd], check=True)
                        workflows_table.update({"state": "removed"}, Query().workflow_id == workflow_id)
                        self.remove_workflow(workflow_id)
                        break
                else:
                    retries = 0

                # Stop monitoring on completion
                if state in ["Success", "Failure"]:
                    workflow_logger.info(f"Workflow {workflow_id} completed with state {state}.")
                    workflows_table.update({"state": state}, Query().workflow_id == workflow_id)
                    
                    # For failed workflows, capture final log information
                    if state == "Failure":
                        final_logs = self.find_workflow_log_files(iwd, workflow_id)
                        workflows_table.update({
                            "state": state,
                            "final_log_summary": final_logs.get("summary", {})
                        }, Query().workflow_id == workflow_id)
                    
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

class PegasusMCPServer:
    def __init__(self):
        self.workflow_manager = PegasusWorkflowManager()
        self.auto_monitor_active = False
        self.auto_monitor_task = None
        self.monitor_interval = 60  # seconds
        self.tools = {
            "get_workflow_status": {
                "name": "get_workflow_status",
                "description": "Get status of workflows (all or specific workflow)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Optional: specific workflow ID"}
                    }
                }
            },
            "list_workflows": {
                "name": "list_workflows",
                "description": "List all active workflows",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "start_monitoring": {
                "name": "start_monitoring",
                "description": "Start monitoring a workflow",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID to monitor"},
                        "iwd": {"type": "string", "description": "Initial working directory path"}
                    },
                    "required": ["workflow_id", "iwd"]
                }
            },
            "stop_monitoring": {
                "name": "stop_monitoring",
                "description": "Stop monitoring a workflow",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID to stop monitoring"}
                    },
                    "required": ["workflow_id"]
                }
            },
            "stop_workflow": {
                "name": "stop_workflow",
                "description": "Stop/remove a workflow execution",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID to stop"}
                    },
                    "required": ["workflow_id"]
                }
            },
            "get_held_jobs": {
                "name": "get_held_jobs",
                "description": "Get information about held jobs with log file paths",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Optional: filter by workflow ID"}
                    }
                }
            },
            "get_workflow_stats": {
                "name": "get_workflow_stats",
                "description": "Get workflow statistics from database",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "start_auto_monitor": {
                "name": "start_auto_monitor",
                "description": "Start automatic workflow discovery and monitoring",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "interval": {"type": "integer", "description": "Monitor interval in seconds (default: 60)"}
                    }
                }
            },
            "stop_auto_monitor": {
                "name": "stop_auto_monitor",
                "description": "Stop automatic workflow monitoring",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "get_monitor_status": {
                "name": "get_monitor_status",
                "description": "Get automatic monitoring status",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "pegasus_analyzer": {
                "name": "pegasus_analyzer",
                "description": "Run pegasus-analyzer on a workflow",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_dir": {"type": "string", "description": "Workflow directory path"}
                    },
                    "required": ["workflow_dir"]
                }
            },
            "list_workflow_logs": {
                "name": "list_workflow_logs",
                "description": "List all log files for a workflow with categorization",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID"},
                        "workflow_dir": {"type": "string", "description": "Optional: workflow directory path"},
                        "include_content": {"type": "boolean", "description": "Include file content preview (default: false)"}
                    },
                    "required": ["workflow_id"]
                }
            },
            "get_error_logs": {
                "name": "get_error_logs",
                "description": "Get recent error logs for a workflow",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID"},
                        "workflow_dir": {"type": "string", "description": "Optional: workflow directory path"},
                        "hours": {"type": "integer", "description": "Hours back to search (default: 24)"}
                    },
                    "required": ["workflow_id"]
                }
            },
            "read_log_file": {
                "name": "read_log_file",
                "description": "Read content of a specific log file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Full path to log file"},
                        "lines": {"type": "integer", "description": "Number of lines to read (default: 50)"},
                        "from_end": {"type": "boolean", "description": "Read from end of file (default: true)"}
                    },
                    "required": ["file_path"]
                }
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

    async def stop_auto_monitoring(self):
        """Stop automatic workflow monitoring"""
        if not self.auto_monitor_active:
            return False
        
        self.auto_monitor_active = False
        if self.auto_monitor_task:
            self.auto_monitor_task.cancel()
            try:
                await self.auto_monitor_task
            except asyncio.CancelledError:
                pass
            self.auto_monitor_task = None
        
        logger.info("Stopped automatic monitoring")
        return True

    async def auto_monitor_loop(self):
        """Main automatic monitoring loop"""
        monitor_logger = self.workflow_manager.setup_logger()
        
        while self.auto_monitor_active:
            try:
                monitor_logger.info("Checking for new workflows...")
                workflows = await self.workflow_manager.get_workflow_details()
                
                # Start monitoring any new workflows
                for wf_id, iwd in workflows:
                    if wf_id not in self.workflow_manager.registered_workflows:
                        logger.info(f"Auto-discovered new workflow: {wf_id}")
                        monitor_logger.info(f"Auto-discovered new workflow: {wf_id} in {iwd}")
                        await self.workflow_manager.start_monitoring_workflow(wf_id, iwd)
                
                # Log current monitoring status
                monitored_count = len(self.workflow_manager.registered_workflows)
                logger.info(f"Currently monitoring {monitored_count} workflows")
                monitor_logger.info(f"Currently monitoring {monitored_count} workflows")
                
                if monitored_count > 0:
                    monitor_logger.info("Monitored workflows:")
                    for wf_id, iwd in self.workflow_manager.registered_workflows.items():
                        monitor_logger.info(f"  - {wf_id} in {iwd}")
                
                await asyncio.sleep(self.monitor_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-monitor loop: {e}")
                monitor_logger.error(f"Error in auto-monitor loop: {e}")
                await asyncio.sleep(10)  # Short delay before retrying

    async def handle_client(self, websocket):
        """Handle a new client connection"""
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
        """Process incoming JSON-RPC message"""
        try:
            request = json.loads(message)
            method = request.get("method")
            request_id = request.get("id")
            params = request.get("params", {})
            
            logger.info(f"Received: {method} (ID: {request_id})")
            
            if method == "initialize":
                await self.handle_initialize(websocket, request_id, params)
            elif method == "notifications/initialized":
                pass
            elif method == "tools/list":
                await self.handle_list_tools(websocket, request_id)
            elif method == "tools/call":
                await self.handle_call_tool(websocket, request_id, params)
            else:
                await self.send_error(websocket, request_id, f"Unknown method: {method}")
                
        except json.JSONDecodeError:
            await self.send_error(websocket, -1, "Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send_error(websocket, -1, f"Processing error: {str(e)}")

    async def handle_initialize(self, websocket, request_id: int, params: Dict[str, Any]):
        """Handle MCP initialization"""
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "logging": {}
                },
                "serverInfo": {
                    "name": "pegasus-workflow-mcp-server",
                    "version": "1.1.0"
                }
            }
        }
        await websocket.send(json.dumps(response))
        logger.info("Client initialized")

    async def handle_list_tools(self, websocket, request_id: int):
        """Handle tools/list request"""
        tools_list = list(self.tools.values())
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools_list
            }
        }
        await websocket.send(json.dumps(response))

    async def handle_call_tool(self, websocket, request_id: int, params: Dict[str, Any]):
        """Handle tools/call request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            result = ""
            
            if tool_name == "get_workflow_status":
                result = await self.tool_get_workflow_status(arguments)
            elif tool_name == "list_workflows":
                result = await self.tool_list_workflows(arguments)
            elif tool_name == "start_monitoring":
                result = await self.tool_start_monitoring(arguments)
            elif tool_name == "stop_monitoring":
                result = await self.tool_stop_monitoring(arguments)
            elif tool_name == "stop_workflow":
                result = await self.tool_stop_workflow(arguments)
            elif tool_name == "get_held_jobs":
                result = await self.tool_get_held_jobs(arguments)
            elif tool_name == "get_workflow_stats":
                result = await self.tool_get_workflow_stats(arguments)
            elif tool_name == "start_auto_monitor":
                result = await self.tool_start_auto_monitor(arguments)
            elif tool_name == "stop_auto_monitor":
                result = await self.tool_stop_auto_monitor(arguments)
            elif tool_name == "get_monitor_status":
                result = await self.tool_get_monitor_status(arguments)
            elif tool_name == "pegasus_analyzer":
                result = await self.tool_pegasus_analyzer(arguments)
            elif tool_name == "list_workflow_logs":
                result = await self.tool_list_workflow_logs(arguments)
            elif tool_name == "get_error_logs":
                result = await self.tool_get_error_logs(arguments)
            elif tool_name == "read_log_file":
                result = await self.tool_read_log_file(arguments)
            else:
                raise Exception(f"Unknown tool: {tool_name}")
            
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": result
                        }
                    ]
                }
            }
            await websocket.send(json.dumps(response))
            
        except Exception as e:
            logger.error(f"Tool error ({tool_name}): {e}")
            await self.send_error(websocket, request_id, f"Tool execution failed: {str(e)}")

    async def tool_get_workflow_status(self, args: Dict[str, Any]) -> str:
        """Get workflow status tool implementation"""
        workflow_id = args.get("workflow_id")
        status = await self.workflow_manager.get_workflow_status(workflow_id)
        return json.dumps(status, indent=2)

    async def tool_list_workflows(self, args: Dict[str, Any]) -> str:
        """List workflows tool implementation"""
        workflows = await self.workflow_manager.get_workflow_details()
        monitored = list(self.workflow_manager.registered_workflows.items())
        
        result = {
            "active_workflows": [{"workflow_id": wf_id, "iwd": iwd} for wf_id, iwd in workflows],
            "monitored_workflows": [{"workflow_id": wf_id, "iwd": iwd} for wf_id, iwd in monitored],
            "total_active": len(workflows),
            "total_monitored": len(monitored)
        }
        return json.dumps(result, indent=2)

    async def tool_start_monitoring(self, args: Dict[str, Any]) -> str:
        """Start monitoring tool implementation"""
        workflow_id = args["workflow_id"]
        iwd = args["iwd"]
        
        success = await self.workflow_manager.start_monitoring_workflow(workflow_id, iwd)
        if success:
            return f"Started monitoring workflow {workflow_id} in directory {iwd}"
        else:
            return f"Workflow {workflow_id} is already being monitored"

    async def tool_stop_monitoring(self, args: Dict[str, Any]) -> str:
        """Stop monitoring tool implementation"""
        workflow_id = args["workflow_id"]
        self.workflow_manager.remove_workflow(workflow_id)
        return f"Stopped monitoring workflow {workflow_id}"

    async def tool_stop_workflow(self, args: Dict[str, Any]) -> str:
        """Stop workflow tool implementation"""
        workflow_id = args["workflow_id"]
        result = await self.workflow_manager.stop_workflow(workflow_id)
        return json.dumps(result, indent=2)

    async def tool_get_held_jobs(self, args: Dict[str, Any]) -> str:
        """Get held jobs tool implementation - enhanced with log file information"""
        workflow_id = args.get("workflow_id")
        
        try:
            query = Query()
            if workflow_id:
                held_jobs = held_jobs_table.search((query.workflow_id == workflow_id) & (query.status.exists()))
            else:
                all_jobs = held_jobs_table.search(query.status.exists())
                held_jobs = all_jobs[-1000:] if len(all_jobs) > 1000 else all_jobs
            
            # Organize by workflow and status
            organized_jobs = {}
            for job in held_jobs:
                wf_id = job.get("workflow_id", "Unknown")
                wf_dir = job.get("workflow_dir", job.get("iwd", "Unknown"))
                status = job.get("status", "Unknown")
                
                if wf_id not in organized_jobs:
                    organized_jobs[wf_id] = {
                        "workflow_id": wf_id,
                        "workflow_dir": wf_dir,
                        "job_counts": {"held": 0, "failed": 0, "total": 0},
                        "jobs": {"held": [], "failed": []},
                        "recent_error_logs": job.get("recent_error_logs", [])
                    }
                
                status_key = status.lower() if status.lower() in ["held", "failed"] else "other"
                if status_key in organized_jobs[wf_id]["job_counts"]:
                    organized_jobs[wf_id]["job_counts"][status_key] += 1
                else:
                    organized_jobs[wf_id]["job_counts"]["other"] = organized_jobs[wf_id]["job_counts"].get("other", 0) + 1
                    
                organized_jobs[wf_id]["job_counts"]["total"] += 1
                
                job_info = {
                    "job_id": job.get("job_id", "Unknown"),
                    "cluster_id": job.get("cluster_id", "Unknown"),
                    "status": status,
                    "reason": job.get("hold_reason", "No reason provided")[:100] + "..." if len(job.get("hold_reason", "")) > 100 else job.get("hold_reason", "No reason provided"),
                    "site": job.get("site", "Unknown"),
                    "timestamp": job.get("timestamp", "Unknown")
                }
                
                if status_key in organized_jobs[wf_id]["jobs"]:
                    if len(organized_jobs[wf_id]["jobs"][status_key]) < 50:
                        organized_jobs[wf_id]["jobs"][status_key].append(job_info)
                else:
                    organized_jobs[wf_id]["jobs"]["other"] = organized_jobs[wf_id]["jobs"].get("other", [])
                    if len(organized_jobs[wf_id]["jobs"]["other"]) < 10:
                        organized_jobs[wf_id]["jobs"]["other"].append(job_info)
            
            result = {
                "query_filter": {"workflow_id": workflow_id},
                "summary": {
                    "total_workflows_with_issues": len(organized_jobs),
                    "total_problematic_jobs": len(held_jobs),
                    "note": "Results limited to last 1000 entries if dataset is large"
                },
                "workflows": organized_jobs
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error in get_held_jobs: {e}")
            return json.dumps({
                "error": f"Failed to retrieve held jobs: {str(e)}",
                "query_filter": {"workflow_id": workflow_id}
            }, indent=2)

    async def tool_get_workflow_stats(self, args: Dict[str, Any]) -> str:
        """Get workflow statistics tool implementation"""
        all_workflows = workflows_table.all()
        stats = {
            "total_workflows": len(all_workflows),
            "states": {},
            "currently_monitored": len(self.workflow_manager.registered_workflows)
        }
        
        for workflow in all_workflows:
            state = workflow.get("state", "unknown")
            stats["states"][state] = stats["states"].get(state, 0) + 1
        
        return json.dumps(stats, indent=2)

    async def tool_start_auto_monitor(self, args: Dict[str, Any]) -> str:
        """Start auto monitoring tool implementation"""
        interval = args.get("interval", 60)
        if interval < 10:
            return "Error: Minimum interval is 10 seconds"
        
        self.monitor_interval = interval
        success = await self.start_auto_monitoring()
        
        if success:
            return f"Started automatic workflow monitoring with {interval}s interval"
        else:
            return "Automatic monitoring is already running"

    async def tool_stop_auto_monitor(self, args: Dict[str, Any]) -> str:
        """Stop auto monitoring tool implementation"""
        success = await self.stop_auto_monitoring()
        
        if success:
            return "Stopped automatic workflow monitoring"
        else:
            return "Automatic monitoring was not running"

    async def tool_get_monitor_status(self, args: Dict[str, Any]) -> str:
        """Get monitoring status tool implementation"""
        status = {
            "auto_monitoring_active": self.auto_monitor_active,
            "monitor_interval": self.monitor_interval,
            "monitored_workflows": len(self.workflow_manager.registered_workflows),
            "workflows": list(self.workflow_manager.registered_workflows.keys())
        }
        return json.dumps(status, indent=2)

    async def tool_pegasus_analyzer(self, args: Dict[str, Any]) -> str:
        """Run pegasus-analyzer tool implementation"""
        workflow_dir = args["workflow_dir"]
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                self.workflow_manager.executor,
                lambda: subprocess.run(
                    ["pegasus-analyzer", workflow_dir],
                    capture_output=True,
                    text=True,
                    check=True
                )
            )
            return f"Pegasus analyzer output:\n{result.stdout}"
        except subprocess.CalledProcessError as e:
            return f"Pegasus analyzer failed: {e}\nOutput: {e.stdout}\nError: {e.stderr}"
        except Exception as e:
            return f"Error running pegasus-analyzer: {e}"

    async def tool_list_workflow_logs(self, args: Dict[str, Any]) -> str:
        """List all log files for a workflow with categorization"""
        workflow_id = args["workflow_id"]
        workflow_dir = args.get("workflow_dir")
        include_content = args.get("include_content", False)
        
        # Get workflow directory if not provided
        if not workflow_dir:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if workflow_record:
                workflow_dir = workflow_record.get("iwd")
            else:
                return json.dumps({
                    "error": f"Workflow {workflow_id} not found and no directory provided"
                }, indent=2)
        
        # Find log files using workflow manager
        log_files = self.workflow_manager.find_workflow_log_files(workflow_dir, workflow_id)
        
        # Add content previews if requested
        if include_content and "error" not in log_files:
            for category in ["pegasus_logs", "condor_logs", "job_logs", "error_logs", "other_logs"]:
                for log_file in log_files[category]:
                    if log_file["size"] < 50000:  # Only preview files smaller than 50KB
                        log_file["content_preview"] = self.workflow_manager._get_file_preview(
                            log_file["path"], max_lines=10
                        )
                    else:
                        log_file["content_preview"] = f"File too large ({log_file['size']} bytes) - use read_log_file tool"
        
        return json.dumps(log_files, indent=2)

    async def tool_get_error_logs(self, args: Dict[str, Any]) -> str:
        """Get recent error logs for a workflow"""
        workflow_id = args["workflow_id"]
        workflow_dir = args.get("workflow_dir")
        hours = args.get("hours", 24)
        
        # Get workflow directory if not provided
        if not workflow_dir:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if workflow_record:
                workflow_dir = workflow_record.get("iwd")
            else:
                return json.dumps({
                    "error": f"Workflow {workflow_id} not found and no directory provided"
                }, indent=2)
        
        # Get recent error logs
        recent_errors = self.workflow_manager.get_recent_error_logs(workflow_dir, hours)
        
        result = {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "search_hours": hours,
            "total_error_files": len(recent_errors),
            "error_logs": recent_errors
        }
        
        return json.dumps(result, indent=2)

    async def tool_read_log_file(self, args: Dict[str, Any]) -> str:
        """Read content of a specific log file"""
        file_path = args["file_path"]
        lines = args.get("lines", 50)
        from_end = args.get("from_end", True)
        
        try:
            if not os.path.exists(file_path):
                return json.dumps({
                    "error": f"File {file_path} does not exist"
                }, indent=2)
            
            stat_info = os.stat(file_path)
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if from_end:
                    # Read from end of file
                    all_lines = f.readlines()
                    content_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                    content = ''.join(content_lines)
                    showing_lines = len(content_lines)
                else:
                    # Read from beginning of file
                    content_lines = []
                    for i, line in enumerate(f):
                        if i >= lines:
                            break
                        content_lines.append(line)
                    content = ''.join(content_lines)
                    showing_lines = len(content_lines)
            
            result = {
                "file_path": file_path,
                "file_size": stat_info.st_size,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat_info.st_mtime)),
                "requested_lines": lines,
                "showing_lines": showing_lines,
                "from_end": from_end,
                "content": content
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({
                "error": f"Error reading file {file_path}: {str(e)}"
            }, indent=2)

    async def tool_analyze_job_outputs(self, args: Dict[str, Any]) -> str:
        """Analyze job output files and extract stderr content"""
        workflow_id = args["workflow_id"]
        workflow_dir = args.get("workflow_dir")
        include_stderr = args.get("include_stderr", True)
        
        # Get workflow directory if not provided
        if not workflow_dir:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if workflow_record:
                workflow_dir = workflow_record.get("iwd")
            else:
                return json.dumps({
                    "error": f"Workflow {workflow_id} not found and no directory provided"
                }, indent=2)
        
        # Analyze job output files
        job_analysis = self.workflow_manager.find_job_output_files(workflow_dir)
        
        if "error" in job_analysis:
            return json.dumps(job_analysis, indent=2)
        
        # Add workflow ID to result
        job_analysis["workflow_id"] = workflow_id
        
        # Filter stderr extracts if not requested
        if not include_stderr:
            job_analysis.pop("stderr_extracts", None)
        
        return json.dumps(job_analysis, indent=2)

    async def tool_get_job_errors(self, args: Dict[str, Any]) -> str:
        """Get jobs with errors and their stderr content"""
        workflow_id = args["workflow_id"]
        workflow_dir = args.get("workflow_dir")
        error_types = args.get("error_types", [])
        
        # Get workflow directory if not provided
        if not workflow_dir:
            workflow_record = workflows_table.get(Query().workflow_id == workflow_id)
            if workflow_record:
                workflow_dir = workflow_record.get("iwd")
            else:
                return json.dumps({
                    "error": f"Workflow {workflow_id} not found and no directory provided"
                }, indent=2)
        
        # Get job analysis
        job_analysis = self.workflow_manager.find_job_output_files(workflow_dir)
        
        if "error" in job_analysis:
            return json.dumps(job_analysis, indent=2)
        
        # Filter jobs with errors
        jobs_with_errors = []
        error_summary = {
            "total_error_jobs": 0,
            "error_type_counts": {},
            "most_common_errors": []
        }
        
        for stderr_extract in job_analysis.get("stderr_extracts", []):
            error_indicators = stderr_extract.get("error_indicators", {})
            if error_indicators.get("has_errors", False):
                # Filter by error types if specified
                if error_types:
                    job_error_types = error_indicators.get("error_types", [])
                    if not any(et in job_error_types for et in error_types):
                        continue
                
                jobs_with_errors.append({
                    "job_dir": stderr_extract["job_dir"],
                    "stderr_file": stderr_extract["stderr_file"],
                    "error_types": error_indicators.get("error_types", []),
                    "syntax_errors": error_indicators.get("syntax_errors", []),
                    "runtime_errors": error_indicators.get("runtime_errors", []),
                    "critical_errors": error_indicators.get("critical_errors", []),
                    "stderr_preview": stderr_extract["stderr_content"][:500] + "..." if len(stderr_extract["stderr_content"]) > 500 else stderr_extract["stderr_content"]
                })
                
                error_summary["total_error_jobs"] += 1
                
                # Count error types
                for error_type in error_indicators.get("error_types", []):
                    error_summary["error_type_counts"][error_type] = error_summary["error_type_counts"].get(error_type, 0) + 1
        
        # Get most common error patterns
        all_errors = []
        for job in jobs_with_errors:
            all_errors.extend(job.get("syntax_errors", []))
            all_errors.extend(job.get("runtime_errors", []))
        
        from collections import Counter
        error_counter = Counter(all_errors)
        error_summary["most_common_errors"] = error_counter.most_common(5)
        
        result = {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "filter_error_types": error_types,
            "error_summary": error_summary,
            "jobs_with_errors": jobs_with_errors
        }
        
        return json.dumps(result, indent=2)

    async def send_error(self, websocket, request_id: int, error_message: str):
        """Send JSON-RPC error response"""
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,
                "message": error_message
            }
        }
        await websocket.send(json.dumps(error_response))

    async def start_server(self):
        """Start the WebSocket server"""
        logger.info(f"Starting Enhanced Pegasus Workflow MCP Server on {WS_HOST}:{WS_PORT}")
        
        # Start automatic monitoring by default
        await self.start_auto_monitoring()
        
        server = await websockets.serve(
            self.handle_client,
            WS_HOST,
            WS_PORT,
            ping_interval=20,
            ping_timeout=10
        )
        
        logger.info(f"Server listening on ws://{WS_HOST}:{WS_PORT}")
        logger.info(f"Automatic workflow monitoring started with {self.monitor_interval}s interval")
        logger.info("Enhanced features: Log file discovery and error tracking")
        logger.info("Press Ctrl+C to stop")
        
        try:
            await server.wait_closed()
        except KeyboardInterrupt:
            logger.info("Shutting down server...")
            await self.stop_auto_monitoring()
            server.close()
            await server.wait_closed()

async def main():
    server = PegasusMCPServer()
    await server.start_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
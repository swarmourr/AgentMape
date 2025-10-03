#!/usr/bin/env python3
"""
Enhanced Pegasus Workflow MCP Client with Job Analysis
Save as: pegasus_client_enhanced.py
"""

import asyncio
import json
import websockets
import sys
import os
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import signal
import time

@dataclass
class ClientConfig:
    """Client configuration management"""
    host: str = "localhost"
    port: int = 8766
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 2
    log_level: str = "INFO"
    log_file: Optional[str] = None
    auto_reconnect: bool = True
    heartbeat_interval: int = 30

    @classmethod
    def from_file(cls, config_path: str) -> 'ClientConfig':
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                data = json.load(f)
                return cls(**data)
        return cls()

    def save_to_file(self, config_path: str):
        with open(config_path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)

class PegasusLogger:
    """Enhanced logging system"""
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self.logger = logging.getLogger("PegasusClient")
        self.setup_logging()
    
    def setup_logging(self):
        self.logger.setLevel(getattr(logging, self.config.log_level.upper()))
        self.logger.handlers.clear()
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        if self.config.log_file:
            try:
                file_handler = logging.FileHandler(self.config.log_file)
                file_handler.setLevel(logging.DEBUG)
                file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                file_handler.setFormatter(file_format)
                self.logger.addHandler(file_handler)
            except Exception as e:
                self.logger.warning(f"Could not setup file logging: {e}")
    
    def info(self, msg: str): self.logger.info(msg)
    def debug(self, msg: str): self.logger.debug(msg)
    def warning(self, msg: str): self.logger.warning(msg)
    def error(self, msg: str): self.logger.error(msg)
    def critical(self, msg: str): self.logger.critical(msg)

class ConnectionManager:
    """Manages WebSocket connections with retry logic"""
    
    def __init__(self, config: ClientConfig, logger: PegasusLogger):
        self.config = config
        self.logger = logger
        self.websocket = None
        self.request_id = 1
        self.initialized = False
        self.tools_cache = []
        self.last_heartbeat = None
        self.connection_stats = {'connects': 0, 'reconnects': 0, 'errors': 0, 'last_error': None}
    
    @property
    def url(self) -> str:
        return f"ws://{self.config.host}:{self.config.port}"
    
    async def connect(self) -> bool:
        for attempt in range(self.config.max_retries):
            try:
                if self.websocket:
                    await self.close()
                
                self.logger.info(f"Connecting to {self.url} (attempt {attempt + 1})")
                
                self.websocket = await websockets.connect(
                    self.url,
                    ping_interval=self.config.heartbeat_interval,
                    ping_timeout=15,
                    close_timeout=10
                )
                
                self.connection_stats['connects'] += 1
                self.last_heartbeat = time.time()
                self.logger.info("Connected successfully")
                
                if await self.initialize():
                    return True
                else:
                    self.logger.error("Initialization failed")
                    continue
                    
            except Exception as e:
                self.connection_stats['errors'] += 1
                self.connection_stats['last_error'] = str(e)
                self.logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay ** (attempt + 1)
                    self.logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
        
        self.logger.critical("All connection attempts failed")
        return False
    
    async def initialize(self) -> bool:
        try:
            init_request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "pegasus-client", "version": "1.2.0"}
                }
            }
            
            response = await self.send_raw_request(init_request)
            
            if "error" in response:
                self.logger.error(f"Initialization failed: {response['error']}")
                return False
            
            await self.websocket.send(json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }))
            
            await self.refresh_tools_cache()
            
            self.initialized = True
            self.logger.info("Session initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Initialization error: {e}")
            return False
    
    async def send_raw_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        await self.websocket.send(json.dumps(request))
        response_text = await asyncio.wait_for(self.websocket.recv(), timeout=self.config.timeout)
        self.request_id += 1
        return json.loads(response_text)
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> str:
        if not await self.ensure_connected():
            raise Exception("Unable to establish connection")
        
        if arguments is None:
            arguments = {}
        
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        
        try:
            response = await self.send_raw_request(request)
            if "error" in response:
                raise Exception(f"Tool call failed: {response['error']}")
            return response["result"]["content"][0]["text"]
            
        except Exception as e:
            if "connection" in str(e).lower() and self.config.auto_reconnect:
                self.logger.warning("Connection lost, attempting reconnection...")
                if await self.reconnect():
                    response = await self.send_raw_request(request)
                    if "error" in response:
                        raise Exception(f"Tool call failed: {response['error']}")
                    return response["result"]["content"][0]["text"]
            raise
    
    async def ensure_connected(self) -> bool:
        if not self.websocket or not self.initialized:
            return await self.connect()
        try:
            _ = self.websocket.remote_address
            return True
        except:
            if self.config.auto_reconnect:
                return await self.reconnect()
            return False
    
    async def reconnect(self) -> bool:
        self.connection_stats['reconnects'] += 1
        self.logger.info("Reconnecting...")
        self.initialized = False
        return await self.connect()
    
    async def refresh_tools_cache(self):
        try:
            request = {"jsonrpc": "2.0", "id": self.request_id, "method": "tools/list"}
            response = await self.send_raw_request(request)
            if "error" not in response:
                self.tools_cache = response["result"]["tools"]
                self.logger.debug(f"Cached {len(self.tools_cache)} tools")
        except Exception as e:
            self.logger.warning(f"Could not refresh tools cache: {e}")
    
    def get_tools(self) -> List[Dict[str, Any]]:
        return self.tools_cache
    
    def get_connection_stats(self) -> Dict[str, Any]:
        return {
            **self.connection_stats,
            'uptime': time.time() - self.last_heartbeat if self.last_heartbeat else 0,
            'initialized': self.initialized
        }
    
    async def close(self):
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
            finally:
                self.websocket = None
                self.initialized = False

class CommandProcessor:
    """Processes and formats command output"""
    
    def __init__(self, connection: ConnectionManager, logger: PegasusLogger):
        self.connection = connection
        self.logger = logger
        self.command_history = []
    
    async def execute(self, command: str) -> bool:
        self.command_history.append({
            'command': command,
            'timestamp': datetime.now().isoformat(),
            'success': False
        })
        
        parts = command.strip().split()
        if not parts:
            return True
        
        cmd = parts[0].lower()
        args = parts[1:]
        
        try:
            if cmd in ["quit", "exit"]:
                return False
            elif cmd == "help":
                self.show_help()
            elif cmd == "status":
                await self.handle_status(args)
            elif cmd == "list":
                await self.handle_list()
            elif cmd == "held":
                await self.handle_held_jobs(args)
            elif cmd == "stats":
                await self.handle_stats()
            elif cmd == "tools":
                self.show_tools()
            elif cmd == "info":
                self.show_connection_info()
            elif cmd == "config":
                self.show_config()
            elif cmd == "reconnect":
                await self.handle_reconnect()
            elif cmd == "auto-start":
                await self.handle_auto_start(args)
            elif cmd == "auto-stop":
                await self.handle_auto_stop()
            elif cmd == "auto-status":
                await self.handle_auto_status()
            elif cmd == "monitor":
                await self.handle_monitor(args)
            elif cmd == "unmonitor":
                await self.handle_unmonitor(args)
            elif cmd == "stop":
                await self.handle_stop_workflow(args)
            elif cmd == "analyze":
                await self.handle_analyze(args)
            elif cmd == "logs":
                await self.handle_logs(args)
            elif cmd == "error-logs":
                await self.handle_error_logs(args)
            elif cmd == "read-log":
                await self.handle_read_log(args)
            elif cmd == "job-outputs":
                await self.handle_job_outputs(args)
            elif cmd == "job-errors":
                await self.handle_job_errors(args)
            else:
                print(f"Unknown command: {cmd}. Type 'help' for available commands.")
                return True
            
            self.command_history[-1]['success'] = True
            return True
            
        except Exception as e:
            self.logger.error(f"Command '{command}' failed: {e}")
            print(f"Error executing command: {e}")
            
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                print("Connection issue detected. Use 'reconnect' or 'info' to check status.")
            
            return True
    
    # Command handlers
    async def handle_status(self, args: List[str]):
        workflow_id = args[0] if args else None
        tool_args = {"workflow_id": workflow_id} if workflow_id else {}
        result = await self.connection.call_tool("get_workflow_status", tool_args)
        self.format_json_output(result, "Workflow Status")
    
    async def handle_list(self):
        result = await self.connection.call_tool("list_workflows")
        self.format_workflows_list(result)
    
    async def handle_held_jobs(self, args: List[str]):
        workflow_id = args[0] if args else None
        tool_args = {"workflow_id": workflow_id} if workflow_id else {}
        result = await self.connection.call_tool("get_held_jobs", tool_args)
        self.format_held_jobs(result)
    
    async def handle_stats(self):
        result = await self.connection.call_tool("get_workflow_stats")
        self.format_json_output(result, "Workflow Statistics")
    
    async def handle_reconnect(self):
        print("Reconnecting to server...")
        success = await self.connection.reconnect()
        print("Reconnection successful" if success else "Reconnection failed")
    
    async def handle_auto_start(self, args: List[str]):
        interval = int(args[0]) if args else None
        tool_args = {"interval": interval} if interval else {}
        result = await self.connection.call_tool("start_auto_monitor", tool_args)
        print(f"Auto-monitor: {result}")
    
    async def handle_auto_stop(self):
        result = await self.connection.call_tool("stop_auto_monitor")
        print(f"Auto-monitor: {result}")
    
    async def handle_auto_status(self):
        result = await self.connection.call_tool("get_monitor_status")
        self.format_monitor_status(result)
    
    async def handle_monitor(self, args: List[str]):
        if len(args) < 2:
            print("Usage: monitor <workflow_id> <iwd_path>")
            return
        result = await self.connection.call_tool("start_monitoring", {
            "workflow_id": args[0], "iwd": " ".join(args[1:])
        })
        print(f"Monitor: {result}")
    
    async def handle_unmonitor(self, args: List[str]):
        if not args:
            print("Usage: unmonitor <workflow_id>")
            return
        result = await self.connection.call_tool("stop_monitoring", {"workflow_id": args[0]})
        print(f"Unmonitor: {result}")
    
    async def handle_stop_workflow(self, args: List[str]):
        if not args:
            print("Usage: stop <workflow_id>")
            return
        workflow_id = args[0]
        confirm = input(f"Stop workflow {workflow_id}? (y/N): ").strip().lower()
        if confirm == 'y':
            result = await self.connection.call_tool("stop_workflow", {"workflow_id": workflow_id})
            self.format_json_output(result, "Stop Workflow Result")
        else:
            print("Operation cancelled")
    
    async def handle_analyze(self, args: List[str]):
        if not args:
            print("Usage: analyze <workflow_dir>")
            return
        print(f"Running pegasus-analyzer on {args[0]}...")
        result = await self.connection.call_tool("pegasus_analyzer", {"workflow_dir": args[0]})
        print("\nAnalyzer Output:")
        print(result)
    
    async def handle_logs(self, args: List[str]):
        if not args:
            print("Usage: logs <workflow_id> [--include-content] [--dir <path>]")
            return
        
        workflow_id = args[0]
        include_content = "--include-content" in args
        workflow_dir = None
        
        if "--dir" in args:
            dir_index = args.index("--dir")
            if dir_index + 1 < len(args):
                workflow_dir = args[dir_index + 1]
        
        tool_args = {"workflow_id": workflow_id}
        if workflow_dir:
            tool_args["workflow_dir"] = workflow_dir
        if include_content:
            tool_args["include_content"] = include_content
        
        result = await self.connection.call_tool("list_workflow_logs", tool_args)
        self.format_workflow_logs(result)
    
    async def handle_error_logs(self, args: List[str]):
        if not args:
            print("Usage: error-logs <workflow_id> [--hours <count>] [--dir <path>]")
            return
        
        workflow_id = args[0]
        hours = 24
        workflow_dir = None
        
        if "--hours" in args:
            hours_index = args.index("--hours")
            if hours_index + 1 < len(args):
                try:
                    hours = int(args[hours_index + 1])
                except ValueError:
                    print("Invalid hours count")
                    return
        
        if "--dir" in args:
            dir_index = args.index("--dir")
            if dir_index + 1 < len(args):
                workflow_dir = args[dir_index + 1]
        
        tool_args = {"workflow_id": workflow_id, "hours": hours}
        if workflow_dir:
            tool_args["workflow_dir"] = workflow_dir
        
        result = await self.connection.call_tool("get_error_logs", tool_args)
        self.format_error_logs(result)
    
    async def handle_read_log(self, args: List[str]):
        if not args:
            print("Usage: read-log <file_path> [--lines <count>] [--from-start]")
            return
        
        file_path = args[0]
        lines = 50
        from_end = True
        
        if "--lines" in args:
            lines_index = args.index("--lines")
            if lines_index + 1 < len(args):
                try:
                    lines = int(args[lines_index + 1])
                except ValueError:
                    print("Invalid lines count")
                    return
        
        if "--from-start" in args:
            from_end = False
        
        tool_args = {"file_path": file_path, "lines": lines, "from_end": from_end}
        result = await self.connection.call_tool("read_log_file", tool_args)
        self.format_log_content(result)

    async def handle_job_outputs(self, args: List[str]):
        """Handle job-outputs command - analyze job output files"""
        if not args:
            print("Usage: job-outputs <workflow_id> [--no-stderr] [--dir <path>]")
            return
        
        workflow_id = args[0]
        include_stderr = "--no-stderr" not in args
        workflow_dir = None
        
        if "--dir" in args:
            dir_index = args.index("--dir")
            if dir_index + 1 < len(args):
                workflow_dir = args[dir_index + 1]
        
        tool_args = {"workflow_id": workflow_id, "include_stderr": include_stderr}
        if workflow_dir:
            tool_args["workflow_dir"] = workflow_dir
        
        result = await self.connection.call_tool("analyze_job_outputs", tool_args)
        self.format_job_outputs(result)

    async def handle_job_errors(self, args: List[str]):
        """Handle job-errors command - get jobs with errors"""
        if not args:
            print("Usage: job-errors <workflow_id> [--types type1,type2] [--dir <path>]")
            return
        
        workflow_id = args[0]
        error_types = []
        workflow_dir = None
        
        if "--types" in args:
            types_index = args.index("--types")
            if types_index + 1 < len(args):
                error_types = args[types_index + 1].split(",")
        
        if "--dir" in args:
            dir_index = args.index("--dir")
            if dir_index + 1 < len(args):
                workflow_dir = args[dir_index + 1]
        
        tool_args = {"workflow_id": workflow_id}
        if error_types:
            tool_args["error_types"] = error_types
        if workflow_dir:
            tool_args["workflow_dir"] = workflow_dir
        
        result = await self.connection.call_tool("get_job_errors", tool_args)
        self.format_job_errors(result)
        
    # FORMATTING METHODS
    def format_json_output(self, result: str, title: str):
        try:
            data = json.loads(result)
            print(f"\n=== {title} ===")
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(f"\n=== {title} (Raw) ===")
            print(result)
    
    def format_workflows_list(self, result: str):
        try:
            data = json.loads(result)
            print("\n=== Workflows Summary ===")
            print(f"Active: {data.get('total_active', 0)}")
            print(f"Monitored: {data.get('total_monitored', 0)}")
            
            active = data.get('active_workflows', [])
            if active:
                print(f"\nActive Workflows ({len(active)}):")
                for wf in active:
                    wf_id = wf.get('workflow_id', 'Unknown')
                    iwd = wf.get('iwd', 'Unknown')
                    print(f"  {wf_id}")
                    print(f"    Directory: {iwd}")
            
            monitored = data.get('monitored_workflows', [])
            if monitored:
                print(f"\nMonitored Workflows ({len(monitored)}):")
                for wf in monitored:
                    print(f"  {wf.get('workflow_id', 'Unknown')} -> {wf.get('iwd', 'Unknown')}")
        except json.JSONDecodeError:
            print("\n=== Workflows (Raw) ===")
            print(result)
    
    def format_held_jobs(self, result: str):
        try:
            data = json.loads(result)
            if "error" in data:
                print(f"Error: {data['error']}")
                return
            
            summary = data.get('summary', {})
            print("\n=== Held Jobs Summary ===")
            print(f"Workflows with issues: {summary.get('total_workflows_with_issues', 0)}")
            print(f"Total problematic jobs: {summary.get('total_problematic_jobs', 0)}")
            
            workflows = data.get('workflows', {})
            if workflows:
                for wf_id, wf_data in workflows.items():
                    print(f"\nWorkflow: {wf_id}")
                    print(f"  Directory: {wf_data.get('workflow_dir', 'Unknown')}")
                    
                    job_counts = wf_data.get('job_counts', {})
                    print(f"  Held jobs: {job_counts.get('held', 0)}")
                    print(f"  Failed jobs: {job_counts.get('failed', 0)}")
                    print(f"  Total: {job_counts.get('total', 0)}")
                    
                    error_logs = wf_data.get('recent_error_logs', [])
                    if error_logs:
                        print(f"  Recent error logs ({len(error_logs)}):")
                        for log in error_logs[:3]:
                            print(f"    {log.get('relative_path', 'Unknown')} ({log.get('modified', 'Unknown')})")
                    
                    held_jobs = wf_data.get('jobs', {}).get('held', [])
                    if held_jobs:
                        print(f"  Recent held jobs:")
                        for job in held_jobs[:3]:
                            print(f"    {job.get('job_id', 'Unknown')}")
                            reason = job.get('reason', 'No reason')
                            if len(reason) > 80:
                                reason = reason[:77] + "..."
                            print(f"      Reason: {reason}")
                            print(f"      Time: {job.get('timestamp', 'Unknown')}")
            else:
                print("No held jobs found")
        except json.JSONDecodeError:
            print("\n=== Held Jobs (Raw) ===")
            print(result)
    
    def format_workflow_logs(self, result: str):
        try:
            data = json.loads(result)
            if "error" in data:
                print(f"Error: {data['error']}")
                return
            
            workflow_id = data.get("workflow_id", "Unknown")
            workflow_dir = data.get("workflow_dir", "Unknown")
            summary = data.get("summary", {})
            
            print(f"\n=== Logs for Workflow: {workflow_id} ===")
            print(f"Directory: {workflow_dir}")
            print(f"Total files: {summary.get('total_files', 0)}")
            print(f"Total size: {self.format_file_size(summary.get('total_size', 0))}")
            
            categories = {
                "pegasus_logs": "Pegasus Logs",
                "condor_logs": "Condor Logs", 
                "job_logs": "Job Logs",
                "error_logs": "Error Logs",
                "other_logs": "Other Logs"
            }
            
            for category, title in categories.items():
                files = data.get(category, [])
                if files:
                    print(f"\n{title} ({len(files)} files):")
                    for file_info in files[:10]:
                        size = self.format_file_size(file_info.get('size', 0))
                        modified = file_info.get('modified', 'Unknown')
                        print(f"  {file_info['name']} ({size}) - {modified}")
                        print(f"    Path: {file_info['path']}")
                        
                        if file_info.get('content_preview'):
                            preview = file_info['content_preview'][:200]
                            print(f"    Preview: {preview}...")
                    
                    if len(files) > 10:
                        print(f"    ... and {len(files) - 10} more files")
        except json.JSONDecodeError:
            print("\n=== Workflow Logs (Raw) ===")
            print(result)
    
    def format_error_logs(self, result: str):
        try:
            data = json.loads(result)
            if "error" in data:
                print(f"Error: {data['error']}")
                return
            
            workflow_id = data.get("workflow_id", "Unknown")
            workflow_dir = data.get("workflow_dir", "Unknown")
            search_hours = data.get("search_hours", 24)
            total_error_files = data.get("total_error_files", 0)
            
            print(f"\n=== Error Logs for Workflow: {workflow_id} ===")
            print(f"Directory: {workflow_dir}")
            print(f"Search period: Last {search_hours} hours")
            print(f"Error files found: {total_error_files}")
            
            error_logs = data.get("error_logs", [])
            if error_logs:
                print(f"\nRecent Error Files:")
                for error_log in error_logs:
                    size = self.format_file_size(error_log.get('size', 0))
                    modified = error_log.get('modified', 'Unknown')
                    print(f"  {error_log['name']} ({size}) - {modified}")
                    print(f"    Path: {error_log['path']}")
                    
                    if error_log.get('preview'):
                        preview = error_log['preview'][:200]
                        print(f"    Preview: {preview}...")
            else:
                print("No recent error logs found")
        except json.JSONDecodeError:
            print("\n=== Error Logs (Raw) ===")
            print(result)
    
    def format_log_content(self, result: str):
        try:
            data = json.loads(result)
            if "error" in data:
                print(f"Error: {data['error']}")
                return
            
            file_path = data.get("file_path", "Unknown")
            file_size = data.get("file_size", 0)
            modified = data.get("modified", "Unknown")
            showing_lines = data.get("showing_lines", 0)
            requested_lines = data.get("requested_lines", 0)
            from_end = data.get("from_end", True)
            
            print(f"\n=== Log File Content ===")
            print(f"File: {file_path}")
            print(f"Size: {self.format_file_size(file_size)}")
            print(f"Modified: {modified}")
            print(f"Showing: {showing_lines}/{requested_lines} lines ({'from end' if from_end else 'from start'})")
            print("=" * 60)
            
            content = data.get("content", "")
            print(content if content else "(Empty file)")
        except json.JSONDecodeError:
            print("\n=== Log Content (Raw) ===")
            print(result)

    def format_job_outputs(self, result: str):
        """Format job outputs analysis output"""
        try:
            data = json.loads(result)
            if "error" in data:
                print(f"Error: {data['error']}")
                return
            
            workflow_id = data.get("workflow_id", "Unknown")
            workflow_dir = data.get("workflow_dir", "Unknown")
            summary = data.get("summary", {})
            
            print(f"\n=== Job Outputs Analysis for Workflow: {workflow_id} ===")
            print(f"Directory: {workflow_dir}")
            print(f"Total jobs found: {summary.get('total_jobs', 0)}")
            print(f"Jobs with stderr: {summary.get('jobs_with_stderr', 0)}")
            print(f"Jobs with errors: {summary.get('jobs_with_errors', 0)}")
            
            job_outputs = data.get("job_outputs", [])
            if job_outputs:
                print(f"\nJob Output Files ({len(job_outputs)} jobs):")
                for i, job in enumerate(job_outputs[:10]):
                    print(f"\n  Job {i+1}: {job.get('relative_path', 'Unknown')}")
                    print(f"    Status: {job.get('job_status', 'unknown')}")
                    print(f"    Output files: {len(job.get('output_files', []))}")
                    
                    if job.get("stderr_file"):
                        print(f"    Stderr file: {job['stderr_file']}")
                    
                    if job.get("stderr_content"):
                        stderr_preview = job["stderr_content"][:150]
                        if len(job["stderr_content"]) > 150:
                            stderr_preview += "..."
                        print(f"    Stderr preview: {stderr_preview}")
                
                if len(job_outputs) > 10:
                    print(f"\n  ... and {len(job_outputs) - 10} more jobs")
            
            stderr_extracts = data.get("stderr_extracts", [])
            if stderr_extracts:
                print(f"\nStderr Extracts ({len(stderr_extracts)} jobs with stderr):")
                for extract in stderr_extracts[:5]:
                    job_dir = extract.get("job_dir", "Unknown")
                    error_indicators = extract.get("error_indicators", {})
                    print(f"  {job_dir}: {error_indicators.get('error_types', [])}")
                
                if len(stderr_extracts) > 5:
                    print(f"  ... and {len(stderr_extracts) - 5} more")
        except json.JSONDecodeError:
            print("\n=== Job Outputs (Raw) ===")
            print(result)

    def format_job_errors(self, result: str):
        """Format job errors output"""
        try:
            data = json.loads(result)
            if "error" in data:
                print(f"Error: {data['error']}")
                return
            
            workflow_id = data.get("workflow_id", "Unknown")
            workflow_dir = data.get("workflow_dir", "Unknown")
            filter_types = data.get("filter_error_types", [])
            error_summary = data.get("error_summary", {})
            
            print(f"\n=== Job Errors for Workflow: {workflow_id} ===")
            print(f"Directory: {workflow_dir}")
            if filter_types:
                print(f"Filtered by error types: {', '.join(filter_types)}")
            
            print(f"\nError Summary:")
            print(f"  Total jobs with errors: {error_summary.get('total_error_jobs', 0)}")
            
            error_type_counts = error_summary.get("error_type_counts", {})
            if error_type_counts:
                print(f"  Error type breakdown:")
                for error_type, count in error_type_counts.items():
                    print(f"    {error_type}: {count}")
            
            most_common = error_summary.get("most_common_errors", [])
            if most_common:
                print(f"  Most common errors:")
                for error, count in most_common[:3]:
                    print(f"    \"{error[:60]}{'...' if len(error) > 60 else ''}\": {count} times")
            
            jobs_with_errors = data.get("jobs_with_errors", [])
            if jobs_with_errors:
                print(f"\nJobs with Errors ({len(jobs_with_errors)}):")
                for i, job in enumerate(jobs_with_errors):
                    print(f"\n  Job {i+1}: {job.get('job_dir', 'Unknown')}")
                    print(f"    Error types: {', '.join(job.get('error_types', []))}")
                    
                    syntax_errors = job.get('syntax_errors', [])
                    if syntax_errors:
                        print(f"    Syntax errors:")
                        for error in syntax_errors[:2]:
                            print(f"      {error}")
                    
                    runtime_errors = job.get('runtime_errors', [])
                    if runtime_errors:
                        print(f"    Runtime errors:")
                        for error in runtime_errors[:2]:
                            print(f"      {error}")
                    
                    critical_errors = job.get('critical_errors', [])
                    if critical_errors:
                        print(f"    Critical errors: {', '.join(critical_errors)}")
                    
                    stderr_preview = job.get('stderr_preview', '')
                    if stderr_preview:
                        print(f"    Stderr preview:")
                        for line in stderr_preview.split('\n')[:3]:
                            if line.strip():
                                print(f"      {line}")
            else:
                print("No jobs with errors found")
        except json.JSONDecodeError:
            print("\n=== Job Errors (Raw) ===")
            print(result)
    
    def format_file_size(self, size_bytes: int) -> str:
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        return f"{size:.1f} {size_names[i]}"
    
    def format_monitor_status(self, result: str):
        try:
            data = json.loads(result)
            print("\n=== Auto-Monitor Status ===")
            print(f"Active: {'Yes' if data.get('auto_monitoring_active') else 'No'}")
            print(f"Interval: {data.get('monitor_interval', 'N/A')} seconds")
            print(f"Monitored workflows: {data.get('monitored_workflows', 0)}")
            
            workflows = data.get('workflows', [])
            if workflows:
                print("\nCurrently monitoring:")
                for wf_id in workflows[:10]:
                    print(f"  {wf_id}")
                if len(workflows) > 10:
                    print(f"  ... and {len(workflows) - 10} more")
        except json.JSONDecodeError:
            print("\n=== Monitor Status (Raw) ===")
            print(result)
    
    def show_help(self):
        print("""
=== Pegasus Workflow Monitor - Commands ===

Basic Commands:
  help                              - Show this help
  status [workflow_id]              - Get workflow status
  list                              - List workflows
  held [workflow_id]                - Show held/failed jobs
  stats                             - Workflow statistics
  tools                             - Show available tools

Monitoring Commands:
  monitor <workflow_id> <iwd>       - Start monitoring workflow
  unmonitor <workflow_id>           - Stop monitoring workflow
  auto-start [interval]             - Start auto-monitoring
  auto-stop                         - Stop auto-monitoring
  auto-status                       - Auto-monitor status

Log Analysis Commands:
  logs <workflow_id> [--include-content] [--dir <path>]
                                    - List log files for workflow
  error-logs <workflow_id> [--hours <count>] [--dir <path>]
                                    - Get recent error logs
  read-log <file_path> [--lines <count>] [--from-start]
                                    - Read content from log file

Job Output Analysis Commands:
  job-outputs <workflow_id> [--no-stderr] [--dir <path>]
                                    - Analyze job output files and extract stderr
  job-errors <workflow_id> [--types type1,type2] [--dir <path>]
                                    - Get jobs with errors and their details

Advanced Commands:
  stop <workflow_id>                - Stop workflow execution
  analyze <workflow_dir>            - Run pegasus-analyzer

System Commands:
  info                              - Connection information
  config                            - Show configuration
  reconnect                         - Reconnect to server
  quit / exit                       - Exit client

Examples:
  status                            # All workflow statuses
  logs workflow_123                 # List log files
  logs workflow_123 --include-content  # Include file previews
  error-logs workflow_123 --hours 6    # Recent error logs (6 hours)
  read-log /path/to/error.log --lines 100  # Read 100 lines from end
  job-outputs workflow_123          # Analyze job output files with stderr
  job-errors workflow_123           # Show jobs with errors and details
  job-errors workflow_123 --types syntax_error,runtime_error  # Filter by error type
  auto-start 60                     # Start monitoring every 60s
        """)
    
    def show_tools(self):
        tools = self.connection.get_tools()
        print(f"\n=== Available Tools ({len(tools)}) ===")
        for tool in tools:
            print(f"  {tool['name']}: {tool['description']}")
    
    def show_connection_info(self):
        stats = self.connection.get_connection_stats()
        print(f"\n=== Connection Information ===")
        print(f"URL: {self.connection.url}")
        print(f"Status: {'Connected' if stats['initialized'] else 'Disconnected'}")
        print(f"Connections: {stats['connects']}")
        print(f"Reconnections: {stats['reconnects']}")
        print(f"Errors: {stats['errors']}")
        print(f"Uptime: {stats['uptime']:.1f}s")
        
        if stats['last_error']:
            print(f"Last error: {stats['last_error']}")
        
        print(f"Cached tools: {len(self.connection.get_tools())}")
    
    def show_config(self):
        config = self.connection.config
        print(f"\n=== Configuration ===")
        print(f"Host: {config.host}")
        print(f"Port: {config.port}")
        print(f"Timeout: {config.timeout}s")
        print(f"Max retries: {config.max_retries}")
        print(f"Auto-reconnect: {config.auto_reconnect}")
        print(f"Log level: {config.log_level}")
        print(f"Log file: {config.log_file or 'Console only'}")

class PegasusClient:
    """Main client application"""
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self.logger = PegasusLogger(config)
        self.connection = ConnectionManager(config, self.logger)
        self.processor = CommandProcessor(self.connection, self.logger)
        self.running = True
    
    async def start(self):
        self.logger.info("Starting Enhanced Pegasus MCP Client v1.2")
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        if not await self.connection.connect():
            print("Failed to connect to server. Check configuration and server status.")
            return 1
        
        print(f"Connected to Pegasus MCP Server at {self.connection.url}")
        print("Type 'help' for available commands or 'quit' to exit.")
        print("New: job-outputs, job-errors for job-level error analysis")
        
        return await self.interactive_loop()
    
    async def interactive_loop(self) -> int:
        while self.running:
            try:
                command = input("\npegasus> ").strip()
                if not command:
                    continue
                
                if not await self.processor.execute(command):
                    break
                    
            except KeyboardInterrupt:
                print("\nUse 'quit' to exit gracefully.")
            except EOFError:
                print("\nExiting...")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                print(f"Unexpected error: {e}")
        
        await self.cleanup()
        return 0
    
    def signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False
    
    async def cleanup(self):
        self.logger.info("Shutting down client...")
        await self.connection.close()
        print("Client shutdown complete.")

async def run_command_line(config: ClientConfig, args: List[str]) -> int:
    logger = PegasusLogger(config)
    connection = ConnectionManager(config, logger)
    processor = CommandProcessor(connection, logger)
    
    if not await connection.connect():
        print("Failed to connect to server")
        return 1
    
    try:
        command = " ".join(args)
        await processor.execute(command)
        return 0
    except Exception as e:
        print(f"Command failed: {e}")
        return 1
    finally:
        await connection.close()

def create_default_config() -> str:
    config_path = os.path.expanduser("~/.pegasus_client_config.json")
    config = ClientConfig()
    config.save_to_file(config_path)
    return config_path

def main():
    parser = argparse.ArgumentParser(
        description="Enhanced Pegasus Workflow MCP Client with Job Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Interactive mode
  %(prog)s status                   # Quick status check
  %(prog)s list                     # List workflows
  %(prog)s job-outputs workflow_123 # Analyze job outputs with stderr
  %(prog)s job-errors workflow_123  # Show jobs with errors
  %(prog)s --host server.com        # Connect to remote server
  %(prog)s --create-config          # Create default config
        """
    )
    
    parser.add_argument("--config", "-c", help="Configuration file path")
    parser.add_argument("--host", help="Server hostname")
    parser.add_argument("--port", type=int, help="Server port")
    parser.add_argument("--timeout", type=int, help="Request timeout (seconds)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Log level")
    parser.add_argument("--log-file", help="Log file path")
    parser.add_argument("--no-auto-reconnect", action="store_true", help="Disable auto-reconnect")
    parser.add_argument("--create-config", action="store_true", help="Create default config file and exit")
    parser.add_argument("command", nargs="*", help="Command to execute (interactive mode if not provided)")
    
    args = parser.parse_args()
    
    if args.create_config:
        config_path = create_default_config()
        print(f"Default configuration created at: {config_path}")
        return 0
    
    config_path = args.config or os.path.expanduser("~/.pegasus_client_config.json")
    config = ClientConfig.from_file(config_path) if os.path.exists(config_path) else ClientConfig()
    
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.timeout:
        config.timeout = args.timeout
    if args.log_level:
        config.log_level = args.log_level
    if args.log_file:
        config.log_file = args.log_file
    if args.no_auto_reconnect:
        config.auto_reconnect = False
    
    try:
        if args.command:
            return asyncio.run(run_command_line(config, args.command))
        else:
            client = PegasusClient(config)
            return asyncio.run(client.start())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
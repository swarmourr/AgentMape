#!/usr/bin/env python3
"""
Complete Resilient Analyzer MCP Agent for MAPE-K Pegasus Workflow System
Continues operating even when dependencies are unavailable
Now includes monitor connection checking and configurable URLs
Save as: resilient_analyzer_agent.py
Run with: python resilient_analyzer_agent.py
"""

import asyncio
import json
import logging
import websockets
import os
import subprocess
import time
import yaml
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from tinydb import TinyDB, Query
from threading import Thread
import requests
from ruamel.yaml import YAML
from collections.abc import Mapping
from enum import Enum

class TerminalColor(Enum):
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    LIGHT_GRAY = '\033[37m'
    DARK_GRAY = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

    def apply(self, text):
        return f"{self.value}{text}{TerminalColor.RESET.value}"

class ResilientPegasusAnalyzerMCPAgent:
    def __init__(self, port: int = 8766, config_file: str = "analyzer_config.json"):
        """Initialize the Resilient Analyzer MCP Agent with configurable URLs"""
        self.port = port
        self.config_file = config_file

        # Setup logging FIRST (before loading config)
        logging.basicConfig(
            level=logging.INFO,  # Default level, will be updated after config loads
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Load configuration AFTER logger is initialized
        self.config = self.load_config()

        # Update logging level if specified in config
        if "log_level" in self.config:
            logging.getLogger().setLevel(getattr(logging, self.config["log_level"], "INFO"))
    
        # Database setup
        self.db = TinyDB('analyzer_agent_db.json')
        self.analysis_table = self.db.table('workflow_analysis')
        self.failed_workflows_table = self.db.table('failed_workflows')
        
        # Configurable URLs from config file
        self.ollama_url = self.config.get("ollama_url", "https://qsaje-2a04-cec0-121c-3de6-5fd-9c3c-c71f-82b6.a.free.pinggy.link/api/generate")
        self.ollama_api_base = self.config.get("ollama_api_base", "https://qsaje-2a04-cec0-121c-3de6-5fd-9c3c-c71f-82b6.a.free.pinggy.link")
        self.ollama_model = self.config.get("ollama_model", "qwen2.5:7b")
        self.ollama_available = False
        self.last_ollama_check = 0
        self.ollama_check_interval = self.config.get("ollama_check_interval", 30)
        
        # Monitor agent configuration
        self.monitor_url = self.config.get("monitor_url", "ws://localhost:8765")
        self.monitor_available = False
        self.last_monitor_check = 0
        self.monitor_check_interval = self.config.get("monitor_check_interval", 60)
        
        # Resilience settings
        self.push_notifications_enabled = self.config.get("push_notifications_enabled", True)
        self.auto_analysis_enabled = self.config.get("auto_analysis_enabled", True)
        self.fallback_mode = self.config.get("fallback_mode", True)  # Continue without Ollama
        
        # MCP Tools - including new monitor connection tools
        self.tools = {
            "analyze_failed_workflow": self.analyze_failed_workflow,
            "analyze_held_workflow": self.analyze_held_workflow,
            "get_analysis_results": self.get_analysis_results,
            "reanalyze_workflow": self.reanalyze_workflow,
            "get_analysis_history": self.get_analysis_history,
            "analyze_workflow_batch": self.analyze_workflow_batch,
            "get_error_patterns": self.get_error_patterns,
            "export_analysis_report": self.export_analysis_report,
            "clear_analysis_cache": self.clear_analysis_cache,
            "get_analyzer_status": self.get_analyzer_status,
            "check_ollama_status": self.check_ollama_status,
            "test_ollama_connection": self.test_ollama_connection,
            "check_monitor_connection": self.check_monitor_connection,
            "test_monitor_connection": self.test_monitor_connection,
            "get_connection_status": self.get_connection_status,
            "update_configuration": self.update_configuration,
            "get_configuration": self.get_configuration
        }
        
        self.logger.info(f"Resilient Analyzer MCP Agent initialized with {len(self.tools)} tools")
        self.logger.info(f"Ollama URL: {self.ollama_url}")
        self.logger.info(f"Monitor URL: {self.monitor_url}")

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        default_config = {
            "ollama_url": "https://plyxu-2a02-8428-f963-1801-84f6-2682-5795-cf1b.a.free.pinggy.link/api/generate",
            "ollama_api_base": "https://plyxu-2a02-8428-f963-1801-84f6-2682-5795-cf1b.a.free.pinggy.link",
            "ollama_model": "qwen2.5:7b",
            "ollama_check_interval": 30,
            "monitor_url": "ws://localhost:8765", 
            "monitor_check_interval": 60,
            "push_notifications_enabled": True,
            "auto_analysis_enabled": True,
            "fallback_mode": True,
            "log_level": "INFO",
            "enable_monitor_integration": True,
            "connection_timeout": 10,
            "retry_attempts": 3
        }

        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                # Merge with defaults
                default_config.update(loaded_config)
                if hasattr(self, 'logger'):
                    self.logger.info(f"Configuration loaded from {self.config_file}")
                else:
                    print(f"Configuration loaded from {self.config_file}")
            else:
                # Create default config file
                with open(self.config_file, 'w') as f:
                    json.dump(default_config, f, indent=4)
                if hasattr(self, 'logger'):
                    self.logger.info(f"Created default configuration file: {self.config_file}")
                else:
                    print(f"Created default configuration file: {self.config_file}")
        except Exception as e:
            error_msg = f"Error loading configuration: {e}. Using defaults."
            if hasattr(self, 'logger'):
                self.logger.error(error_msg)
            else:
                print(error_msg)

        return default_config

    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            self.logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")

    def check_ollama_availability(self) -> bool:
        """Check if Ollama is available (with caching to avoid frequent checks)"""
        current_time = time.time()
        
        # Only check every N seconds to avoid spamming
        if current_time - self.last_ollama_check < self.ollama_check_interval:
            return self.ollama_available
        
        self.last_ollama_check = current_time
        
        try:
            # Use the configurable API base URL for checking
            tags_url = f"{self.ollama_api_base}/api/tags"
            response = requests.get(tags_url, timeout=self.config.get("connection_timeout", 10))
            self.ollama_available = response.status_code == 200
            if self.ollama_available:
                self.logger.debug("Ollama connection verified")
            return self.ollama_available
        except Exception as e:
            self.ollama_available = False
            self.logger.debug(f"Ollama not available: {e}")
            return False
   
    async def check_monitor_availability(self) -> bool:
        """Check if Monitor agent is available - Always fresh check"""
        current_time = time.time()
        self.last_monitor_check = current_time

        if not self.config.get("enable_monitor_integration", True):
            return False

        try:
            async with websockets.connect(self.monitor_url, timeout=5) as websocket:
                ping_message = {
                    "tool": "ping",
                    "args": {},
                    "source": "analyzer_agent"
                }
                await websocket.send(json.dumps(ping_message))

                # Connection successful
                self.monitor_available = True
                self.logger.debug("Monitor agent connection verified")
                return True

        except Exception as e:
            self.monitor_available = False
            self.logger.debug(f"Monitor agent not available: {e}")
            return False

    # Connection status methods
    async def check_monitor_connection(self) -> Dict[str, Any]:
            """Check current monitor connection status"""
            try:
                is_available = await self.check_monitor_availability()

                return {
                    "status": "success",
                    "monitor_available": is_available,
                    "monitor_url": self.monitor_url,
                    "last_check": datetime.fromtimestamp(self.last_monitor_check).isoformat() if self.last_monitor_check else "Never",
                    "check_interval_seconds": self.monitor_check_interval,
                    "integration_enabled": self.config.get("enable_monitor_integration", True),
                    "connection_status": "connected" if is_available else "disconnected"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "monitor_url": self.monitor_url,
                    "connection_status": "error"
                }

    async def test_monitor_connection(self, force_check: bool = True) -> Dict[str, Any]:
        """Force test monitor agent connection"""
        try:
            if force_check:
                # Reset check time to force immediate check
                self.last_monitor_check = 0
            
            is_available = await self.check_monitor_availability()
            
            if is_available:
                # Try to get monitor status
                try:
                    async with websockets.connect(self.monitor_url, timeout=10) as websocket:
                        status_message = {
                            "tool": "get_monitor_status",
                            "args": {},
                            "source": "analyzer_agent"
                        }
                        await websocket.send(json.dumps(status_message))
                        
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        monitor_response = json.loads(response)
                        
                        return {
                            "status": "success",
                            "connection": "available",
                            "monitor_url": self.monitor_url,
                            "monitor_response": monitor_response,
                            "test_timestamp": datetime.now().isoformat()
                        }
                except Exception as e:
                    return {
                        "status": "success",
                        "connection": "basic_connection_ok",
                        "monitor_url": self.monitor_url,
                        "note": "Connected but could not get detailed status",
                        "error": str(e),
                        "test_timestamp": datetime.now().isoformat()
                    }
            else:
                return {
                    "status": "success",
                    "connection": "unavailable",
                    "monitor_url": self.monitor_url,
                    "error": "Could not establish WebSocket connection",
                    "test_timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            return {
                "status": "error",
                "connection": "error",
                "monitor_url": self.monitor_url,
                "error": str(e),
                "test_timestamp": datetime.now().isoformat()
            }

    async def get_connection_status(self) -> Dict[str, Any]:
        """Get comprehensive connection status for all services"""
        try:
            # Check Ollama
            ollama_status = self.check_ollama_availability()
            
            # Check Monitor
            monitor_status = await self.check_monitor_availability()
            
            # Overall health assessment
            if ollama_status and monitor_status:
                overall_health = "excellent"
            elif ollama_status or (self.fallback_mode and monitor_status):
                overall_health = "good"
            elif self.fallback_mode:
                overall_health = "degraded"
            else:
                overall_health = "poor"
            
            return {
                "status": "success",
                "overall_health": overall_health,
                "connections": {
                    "ollama": {
                        "available": ollama_status,
                        "url": self.ollama_url,
                        "api_base": self.ollama_api_base,
                        "model": self.ollama_model,
                        "last_check": datetime.fromtimestamp(self.last_ollama_check).isoformat() if self.last_ollama_check else "Never"
                    },
                    "monitor": {
                        "available": monitor_status,
                        "url": self.monitor_url,
                        "integration_enabled": self.config.get("enable_monitor_integration", True),
                        "last_check": datetime.fromtimestamp(self.last_monitor_check).isoformat() if self.last_monitor_check else "Never"
                    }
                },
                "system_status": {
                    "fallback_mode_enabled": self.fallback_mode,
                    "can_operate": ollama_status or self.fallback_mode,
                    "llm_analysis_available": ollama_status,
                    "monitor_integration_available": monitor_status
                },
                "check_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "check_timestamp": datetime.now().isoformat()
            }

    # Configuration management methods
    async def update_configuration(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Update analyzer configuration"""
        try:
            old_config = self.config.copy()
            
            # Update configuration
            self.config.update(new_config)
            
            # Update instance variables if URLs changed
            if "ollama_url" in new_config:
                self.ollama_url = new_config["ollama_url"]
                self.last_ollama_check = 0  # Force recheck
                
            if "ollama_api_base" in new_config:
                self.ollama_api_base = new_config["ollama_api_base"]
                self.last_ollama_check = 0  # Force recheck
                
            if "monitor_url" in new_config:
                self.monitor_url = new_config["monitor_url"]
                self.last_monitor_check = 0  # Force recheck
                
            if "ollama_model" in new_config:
                self.ollama_model = new_config["ollama_model"]
                
            # Save updated configuration
            self.save_config()
            
            # Log changes
            changes = []
            for key, new_value in new_config.items():
                if old_config.get(key) != new_value:
                    changes.append(f"{key}: {old_config.get(key)} -> {new_value}")
            
            self.logger.info(f"Configuration updated: {', '.join(changes)}")
            
            return {
                "status": "success",
                "message": "Configuration updated successfully",
                "changes": changes,
                "new_config": self.config,
                "restart_recommended": any(key in new_config for key in ["ollama_url", "monitor_url", "log_level"])
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to update configuration"
            }

    async def get_configuration(self) -> Dict[str, Any]:
        """Get current analyzer configuration"""
        try:
            return {
                "status": "success",
                "configuration": self.config.copy(),
                "active_urls": {
                    "ollama_url": self.ollama_url,
                    "ollama_api_base": self.ollama_api_base,
                    "monitor_url": self.monitor_url
                },
                "config_file": self.config_file
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to get configuration"
            }

    # Ollama status methods
    async def check_ollama_status(self) -> Dict[str, Any]:
        """Check current Ollama connection status"""
        is_available = self.check_ollama_availability()
        
        return {
            "status": "success",
            "ollama_available": is_available,
            "ollama_url": self.ollama_url,
            "ollama_api_base": self.ollama_api_base,
            "ollama_model": self.ollama_model,
            "last_check": datetime.fromtimestamp(self.last_ollama_check).isoformat() if self.last_ollama_check else "Never",
            "fallback_mode_enabled": self.fallback_mode,
            "check_interval_seconds": self.ollama_check_interval
        }

    async def test_ollama_connection(self) -> Dict[str, Any]:
        """Force test Ollama connection"""
        try:
            # Reset check time to force immediate check
            self.last_ollama_check = 0
            
            # Try the tags endpoint
            tags_url = f"{self.ollama_api_base}/api/tags"
            response = requests.get(tags_url, timeout=self.config.get("connection_timeout", 10))
            
            if response.status_code == 200:
                models = response.json().get("models", [])
                return {
                    "status": "success",
                    "connection": "available",
                    "api_base": self.ollama_api_base,
                    "models_count": len(models),
                    "models": [m.get("name", "unknown") for m in models[:5]],
                    "test_timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "status": "success",
                    "connection": "unavailable",
                    "api_base": self.ollama_api_base,
                    "error": f"HTTP {response.status_code}",
                    "test_timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            return {
                "status": "success",
                "connection": "unavailable",
                "api_base": self.ollama_api_base,
                "error": str(e),
                "test_timestamp": datetime.now().isoformat()
            }

    # Analysis result methods
    async def get_analysis_results(self, workflow_id: str) -> Dict[str, Any]:
        """Get analysis results for a specific workflow"""
        try:
            Query_obj = Query()
            results = self.analysis_table.search(Query_obj.workflow_id == workflow_id)
            
            if not results:
                return {"status": "not_found", "message": f"No analysis found for workflow {workflow_id}"}
            
            latest_analysis = max(results, key=lambda x: x['timestamp'])
            return {
                "status": "success",
                "workflow_id": workflow_id,
                "analysis": latest_analysis,
                "total_analyses": len(results)
            }
        except Exception as e:
            return {"status": "error", "message": f"Error retrieving analysis: {str(e)}"}

    async def reanalyze_workflow(self, workflow_id: str, workflow_dir: str, force: bool = False) -> Dict[str, Any]:
        """Reanalyze a workflow, optionally clearing previous results"""
        try:
            if force:
                Query_obj = Query()
                self.analysis_table.remove(Query_obj.workflow_id == workflow_id)
            return await self.analyze_failed_workflow(workflow_id, workflow_dir)
        except Exception as e:
            return {"status": "error", "message": f"Reanalysis failed: {str(e)}"}

    async def get_analysis_history(self, limit: int = 50) -> Dict[str, Any]:
        """Get analysis history with summary statistics"""
        try:
            all_analyses = self.analysis_table.all()
            sorted_analyses = sorted(all_analyses, key=lambda x: x['timestamp'], reverse=True)
            return {
                "status": "success",
                "total_analyses": len(all_analyses),
                "recent_analyses": sorted_analyses[:limit],
                "summary": {
                    "failed_workflows": len([a for a in all_analyses if a['analysis_type'] == 'failed']),
                    "held_workflows": len([a for a in all_analyses if a['analysis_type'] == 'held']),
                    "llm_analyses": len([a for a in all_analyses if a.get('llm_available', False)]),
                    "fallback_analyses": len([a for a in all_analyses if a.get('fallback_used', False)])
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Error getting history: {str(e)}"}

    async def analyze_workflow_batch(self, workflow_list: List[Dict[str, str]]) -> Dict[str, Any]:
        """Analyze multiple workflows in batch"""
        try:
            results = []
            for workflow in workflow_list:
                workflow_id = workflow.get('workflow_id')
                workflow_dir = workflow.get('workflow_dir')
                analysis_type = workflow.get('type', 'failed')
                
                if analysis_type == 'held':
                    result = await self.analyze_held_workflow(workflow_id, workflow_dir)
                else:
                    result = await self.analyze_failed_workflow(workflow_id, workflow_dir)
                
                results.append({"workflow_id": workflow_id, "result": result})
            
            return {
                "status": "success",
                "total_workflows": len(workflow_list),
                "results": results,
                "summary": {
                    "successful": len([r for r in results if r['result']['status'] in ['success', 'partial_success']]),
                    "failed": len([r for r in results if r['result']['status'] == 'error'])
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Batch analysis failed: {str(e)}"}

    async def get_error_patterns(self) -> Dict[str, Any]:
        """Get error patterns from analysis history"""
        try:
            all_analyses = self.analysis_table.all()
            error_patterns = {}
            
            for analysis in all_analyses:
                analysis_result = analysis.get('analysis_result', {})
                if 'error_indicators' in analysis_result:
                    for indicator in analysis_result['error_indicators']:
                        error_patterns[indicator] = error_patterns.get(indicator, 0) + 1
            
            return {
                "status": "success", 
                "total_analyses": len(all_analyses),
                "error_patterns": error_patterns,
                "most_common_errors": sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:10]
            }
        except Exception as e:
            return {"status": "error", "message": f"Error getting patterns: {str(e)}"}

    async def export_analysis_report(self, format_type: str = "json") -> Dict[str, Any]:
        """Export analysis report in specified format"""
        try:
            all_analyses = self.analysis_table.all()
            
            if format_type.lower() == "json":
                return {
                    "status": "success",
                    "format": "json",
                    "data": all_analyses,
                    "total_analyses": len(all_analyses),
                    "export_timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "status": "success", 
                    "message": f"Export format '{format_type}' not fully implemented",
                    "total_analyses": len(all_analyses)
                }
        except Exception as e:
            return {"status": "error", "message": f"Export failed: {str(e)}"}

    async def clear_analysis_cache(self, older_than_days: int = 7) -> Dict[str, Any]:
        """Clear analysis cache older than specified days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            cutoff_iso = cutoff_date.isoformat()
            
            Query_obj = Query()
            removed = self.analysis_table.remove(Query_obj.timestamp < cutoff_iso)
            
            return {
                "status": "success",
                "message": f"Cleared analyses older than {older_than_days} days",
                "removed_count": len(removed) if removed else 0
            }
        except Exception as e:
            return {"status": "error", "message": f"Cache clear failed: {str(e)}"}

    async def get_analyzer_status(self) -> Dict[str, Any]:
        """Get comprehensive analyzer status"""
        try:
            all_analyses = self.analysis_table.all()
            ollama_status = self.check_ollama_availability()
            monitor_status = await self.check_monitor_availability()
            
            return {
                "status": "active",
                "agent_type": "analyzer",
                "version": "2.0.0",
                "llm_backend": "ollama",
                "ollama_url": self.ollama_url,
                "ollama_api_base": self.ollama_api_base,
                "ollama_model": self.ollama_model,
                "ollama_available": ollama_status,
                "monitor_url": self.monitor_url,
                "monitor_available": monitor_status,
                "monitor_integration_enabled": self.config.get("enable_monitor_integration", True),
                "fallback_mode_enabled": self.fallback_mode,
                "total_analyses_performed": len(all_analyses),
                "database_size": len(self.db),
                "available_tools": list(self.tools.keys()),
                "last_analysis": max([a['timestamp'] for a in all_analyses]) if all_analyses else "None",
                "analysis_types": {
                    "failed": len([a for a in all_analyses if a['analysis_type'] == 'failed']),
                    "held": len([a for a in all_analyses if a['analysis_type'] == 'held'])
                },
                "llm_usage": {
                    "with_llm": len([a for a in all_analyses if a.get('llm_available', False)]),
                    "fallback_used": len([a for a in all_analyses if a.get('fallback_used', False)])
                },
                "configuration": {
                    "config_file": self.config_file,
                    "check_intervals": {
                        "ollama": self.ollama_check_interval,
                        "monitor": self.monitor_check_interval
                    }
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error getting status: {str(e)}",
                "agent_type": "analyzer",
                "fallback_mode_enabled": True
            }

    # Core analysis methods
    def generate_fallback_analysis(self, workflow_id: str, workflow_dir: str, logs: str, analysis_type: str = "failed") -> Dict[str, Any]:
        """Generate basic analysis without LLM when Ollama is unavailable"""
        self.logger.info(f"Generating fallback analysis for {workflow_id} (type: {analysis_type})")
        
        # Basic log analysis without LLM
        error_indicators = []
        if "error" in logs.lower():
            error_indicators.append("Error keywords found in logs")
        if "failed" in logs.lower():
            error_indicators.append("Failure indicators detected")
        if "permission denied" in logs.lower():
            error_indicators.append("Permission issues detected")
        if "no such file" in logs.lower():
            error_indicators.append("File not found errors detected")
        if "timeout" in logs.lower():
            error_indicators.append("Timeout issues detected")
        if "connection" in logs.lower():
            error_indicators.append("Connection issues detected")
        if "memory" in logs.lower():
            error_indicators.append("Memory-related issues detected")
        
        # Generate basic structured response
        if analysis_type == "held":
            analysis_result = {
                "hold_analysis": [
                    {
                        "reason": "Analysis performed without LLM - manual review recommended",
                        "solution": "Check logs for specific error messages and resolve dependencies",
                        "priority": "medium",
                        "category": "other"
                    }
                ],
                "recommended_actions": [
                    "Review workflow logs manually",
                    "Check resource availability",
                    "Verify input file paths",
                    "Check network connectivity",
                    "Verify service dependencies"
                ],
                "confidence_score": {
                    "score": 0.3,
                    "explanation": "Basic analysis without LLM - confidence low"
                },
                "fallback_mode": True,
                "error_indicators": error_indicators
            }
        else:
            analysis_result = {
                "problems_and_solutions": [
                    {
                        "problem": "Workflow failed - LLM analysis unavailable",
                        "solution": "Manual review required - check logs for specific errors",
                        "explanation": "Basic analysis performed without LLM due to service unavailability",
                        "error_level": "other",
                        "priority": "medium",
                        "level": "system",
                        "file_path": workflow_dir
                    }
                ],
                "confidence_score": {
                    "score": 0.3,
                    "explanation": "Basic analysis without LLM - manual review recommended"
                },
                "analysis_timestamp": datetime.now().isoformat(),
                "total_issues": 1,
                "fallback_mode": True,
                "error_indicators": error_indicators
            }
        
        return analysis_result

    def send_logs_and_workflow_to_llm(self, logs: str, workflow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send workflow logs and YAML to Ollama for analysis (with fallback)"""
        
        # Check Ollama availability first
        if not self.check_ollama_availability():
            self.logger.warning("Ollama not available - analysis will use fallback mode")
            return None
        
        prompt = (
            "Given the following Pegasus-WMS workflow failure logs and the original workflow YAML file, "
            "analyze the errors and provide a general description of the issues and their potential solutions. "
            "Automatically identify any problems related to replicas, transformations, or jobs, and provide high-level corrections. "
            "Additionally, categorize each issue with the appropriate error level (`site`, `replica`, `transformation`, `workflow`, or `other`) "
            "and specify whether the issue is user-level or system-level.\n\n"
            "Ensure your response includes a JSON object with the following structure:\n"
            "{\n"
            "  \"problems_and_solutions\": [\n"
            "    {\n"
            "      \"problem\": \"Description of the issue.\",\n"
            "      \"solution\": \"General description of how to address the issue.\",\n"
            "      \"explanation\": \"Why the issue occurred and general steps for resolution.\",\n"
            "      \"error_level\": \"site/replica/transformation/workflow/other\",\n"
            "      \"priority\": \"high/medium/low\",\n"
            "      \"level\": \"user/system\",\n"
            "      \"file_path\": \"path/to/file\"\n"
            "    }\n"
            "  ],\n"
            "  \"confidence_score\": {\n"
            "    \"score\": 0.85,\n"
            "    \"explanation\": \"This score is based on the model's assessment of the clarity and completeness of the logs and workflow provided.\"\n"
            "  }\n"
            "}\n"
            f"Logs:\n{logs}\n\nWorkflow:\n{json.dumps(workflow, indent=2)}"
        )

        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 2048
            }
        }

        try:
            response = requests.post(
                self.ollama_url, 
                json=payload, 
                timeout=self.config.get("connection_timeout", 120)
            )
            if response.status_code == 200:
                ollama_response = response.json()
                response_text = ollama_response.get('response', '')
                
                # Create compatible format for existing extraction method
                return {
                    "choices": [{
                        "message": {
                            "content": response_text
                        }
                    }]
                }
            else:
                self.logger.error(f"Ollama API Error: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request to Ollama failed: {e}")
            # Mark Ollama as unavailable for faster fallback
            self.ollama_available = False
            return None

    def clean_data(self, data):
        """Recursively clean ruamel.yaml objects to plain Python types."""
        if isinstance(data, Mapping):
            return {key: self.clean_data(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self.clean_data(item) for item in data]
        else:
            return data

    def load_workflow_yaml(self, file_path: str) -> Dict[str, Any]:
        """Load and clean workflow YAML file"""
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Workflow file not found: {file_path}")
            
            yaml = YAML()
            yaml.preserve_quotes = True
            with open(file_path, 'r') as yaml_file:
                raw_data = yaml.load(yaml_file)
            return self.clean_data(raw_data)
        except Exception as e:
            self.logger.error(f"Error loading workflow YAML: {e}")
            # Return minimal structure to prevent complete failure
            return {"error": f"Failed to load YAML: {str(e)}", "timestamp": datetime.now().isoformat()}

    def find_yaml_file(self, workflow_dir: str) -> str:
        """Find the workflow YAML file in the given directory"""
        try:
            if not os.path.exists(workflow_dir):
                return ""
            
            wf_name = workflow_dir.split("/")[-2] if "/" in workflow_dir else workflow_dir
            for file_name in os.listdir(workflow_dir):
                if (file_name.endswith(wf_name + '.yml') or file_name.endswith(wf_name + '.yaml')) and file_name != 'braindump.yml':
                    return os.path.join(workflow_dir, file_name)
            
            # Fallback: look for any YAML file
            for file_name in os.listdir(workflow_dir):
                if file_name.endswith(('.yml', '.yaml')) and file_name != 'braindump.yml':
                    return os.path.join(workflow_dir, file_name)
                    
            return ""
        except Exception as e:
            self.logger.error(f"Error finding YAML file: {e}")
            return ""

    def run_pegasus_analyzer(self, workflow_dir: str) -> str:
        """Run the Pegasus Analyzer to generate workflow logs"""
        try:
            if not os.path.exists(workflow_dir):
                return f"ERROR: Workflow directory {workflow_dir} does not exist"
            
            result = subprocess.run(
                ['pegasus-analyzer', workflow_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=60
            )
            return result.stdout + "\n" + result.stderr
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error running pegasus-analyzer: {e.stderr}")
            return f"ERROR: Pegasus analyzer failed: {e.stderr}"
        except subprocess.TimeoutExpired:
            self.logger.error("Pegasus analyzer timed out")
            return "ERROR: Pegasus analyzer timed out after 60 seconds"
        except FileNotFoundError:
            return "ERROR: pegasus-analyzer command not found - Pegasus WMS not installed or not in PATH"
        except Exception as e:
            self.logger.error(f"Unexpected error running pegasus-analyzer: {e}")
            return f"ERROR: Unexpected error: {str(e)}"

    def extract_workflow_info(self, json_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured workflow analysis from LLM response"""
        try:
            assistant_message = json_payload.get("choices", [])[0].get("message", {}).get("content", "")
            cleaned_json = assistant_message.strip()
            cleaned_json = cleaned_json.replace("```json\n", "").replace("```", "")
            cleaned_json = json.loads(cleaned_json)

            if isinstance(cleaned_json, dict):
                problems_and_solutions = cleaned_json.get("problems_and_solutions", [])
                confidence_score = cleaned_json.get("confidence_score", {"score": 0.0, "explanation": "No confidence data"})

                extracted_info = {
                    "problems_and_solutions": [],
                    "confidence_score": confidence_score,
                    "analysis_timestamp": datetime.now().isoformat(),
                    "total_issues": len(problems_and_solutions),
                    "llm_analysis": True
                }

                for problem_solution in problems_and_solutions:
                    problem_info = {
                        "problem": problem_solution.get("problem", ""),
                        "solution": problem_solution.get("solution", ""),
                        "explanation": problem_solution.get("explanation", ""),
                        "priority": problem_solution.get("priority", ""),
                        "error_level": problem_solution.get("error_level", ""),
                        "file_path": problem_solution.get("file_path", ""),
                        "level": problem_solution.get("level", "")
                    }
                    extracted_info["problems_and_solutions"].append(problem_info)

                return extracted_info
            else:
                return {"error": "Input data is not a valid dictionary"}
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error in workflow info extraction: {e}")
            return {"error": f"Failed to parse JSON response: {str(e)}"}
        except KeyError as e:
            self.logger.error(f"Key error in workflow info extraction: {e}")
            return {"error": f"Missing expected key in response: {str(e)}"}
        except Exception as e:
            self.logger.error(f"Error extracting workflow info: {e}")
            return {"error": f"Failed to extract workflow info: {str(e)}"}

    async def analyze_failed_workflow(self, workflow_id: str, workflow_dir: str) -> Dict[str, Any]:
        """Analyze a failed workflow using LLM-based analysis (with fallback)"""
        self.logger.info(f"Analyzing failed workflow: {workflow_id}")
        
        try:
            # Always attempt analysis, even if components are missing
            logs = self.run_pegasus_analyzer(workflow_dir)
            yaml_path = self.find_yaml_file(workflow_dir)
            
            # Load workflow data (with error handling)
            workflow_data = {}
            if yaml_path:
                workflow_data = self.load_workflow_yaml(yaml_path)
            
            # Attempt LLM analysis
            analysis_result = None
            llm_response = self.send_logs_and_workflow_to_llm(logs, workflow_data)
            
            if llm_response:
                analysis_result = self.extract_workflow_info(llm_response)
                if "error" not in analysis_result:
                    self.logger.info(f"LLM analysis successful for {workflow_id}")
                else:
                    llm_response = None
            
            # Use fallback if LLM failed
            if not llm_response or not analysis_result or "error" in analysis_result:
                self.logger.warning(f"Using fallback analysis for {workflow_id}")
                analysis_result = self.generate_fallback_analysis(workflow_id, workflow_dir, logs, "failed")
            
            # Store analysis in database
            analysis_record = {
                "workflow_id": workflow_id,
                "workflow_dir": workflow_dir,
                "analysis_type": "failed",
                "timestamp": datetime.now().isoformat(),
                "analysis_result": analysis_result,
                "logs": logs[:1000],  # Store first 1000 chars of logs
                "yaml_path": yaml_path,
                "llm_available": bool(llm_response),
                "fallback_used": "fallback_mode" in analysis_result
            }
            self.analysis_table.insert(analysis_record)
            
            # Notify monitor agent if available
            if self.monitor_available and self.config.get("enable_monitor_integration", True):
                await self.notify_monitor_of_analysis(workflow_id, analysis_result, "failed")
            
            return {
                "status": "success",
                "message": f"Analysis completed for workflow {workflow_id}",
                "analysis": analysis_result,
                "workflow_dir": workflow_dir,
                "yaml_path": yaml_path,
                "llm_used": bool(llm_response),
                "fallback_mode": "fallback_mode" in analysis_result,
                "monitor_notified": self.monitor_available
            }
            
        except Exception as e:
            error_msg = f"Error analyzing workflow {workflow_id}: {str(e)}"
            self.logger.error(error_msg)
            
            # Even on error, try to provide some useful information
            fallback_result = self.generate_fallback_analysis(workflow_id, workflow_dir, "", "failed")
            return {
                "status": "partial_success",
                "message": error_msg,
                "analysis": fallback_result,
                "workflow_dir": workflow_dir,
                "error": True,
                "fallback_mode": True
            }

    async def notify_monitor_of_analysis(self, workflow_id: str, analysis_result: Dict[str, Any], analysis_type: str):
        """Notify monitor agent of completed analysis"""
        try:
            if not self.monitor_available:
                return
            
            notification = {
                "tool": "analysis_completed",
                "args": {
                    "workflow_id": workflow_id,
                    "analysis_type": analysis_type,
                    "timestamp": datetime.now().isoformat(),
                    "summary": {
                        "total_issues": analysis_result.get("total_issues", 0),
                        "confidence": analysis_result.get("confidence_score", {}).get("score", 0),
                        "fallback_mode": analysis_result.get("fallback_mode", False)
                    }
                },
                "source": "analyzer_agent"
            }
            
            async with websockets.connect(self.monitor_url, timeout=10) as websocket:
                await websocket.send(json.dumps(notification))
                self.logger.debug(f"Notified monitor of analysis completion for {workflow_id}")
                
        except Exception as e:
            self.logger.warning(f"Failed to notify monitor agent: {e}")

    async def analyze_held_workflow(self, workflow_id: str, workflow_dir: str, hold_reason: str = "") -> Dict[str, Any]:
        """Analyze a held workflow (with fallback)"""
        self.logger.info(f"Analyzing held workflow: {workflow_id}")
        
        try:
            logs = self.run_pegasus_analyzer(workflow_dir)
            yaml_path = self.find_yaml_file(workflow_dir)
            workflow_data = {}
            if yaml_path:
                workflow_data = self.load_workflow_yaml(yaml_path)
            
            # Try LLM analysis first for held workflows
            analysis_result = None
            if self.check_ollama_availability():
                # Create held-specific prompt for Ollama
                prompt = (
                    f"This Pegasus workflow is HELD/STUCK (not failed). Hold reason: {hold_reason}\n"
                    "Analyze why this workflow might be held and provide solutions to release it. "
                    "Focus on resource constraints, dependencies, scheduling issues, or configuration problems.\n\n"
                    "Provide analysis in JSON format:\n"
                    "{\n"
                    "  \"hold_analysis\": [\n"
                    "    {\n"
                    "      \"reason\": \"Why workflow is held\",\n"
                    "      \"solution\": \"How to release it\",\n"
                    "      \"priority\": \"high/medium/low\",\n"
                    "      \"category\": \"resource/dependency/scheduling/config/other\"\n"
                    "    }\n"
                    "  ],\n"
                    "  \"recommended_actions\": [\"action1\", \"action2\"],\n"
                    "  \"confidence_score\": {\"score\": 0.85, \"explanation\": \"...\"}\n"
                    "}\n"
                    f"Logs:\n{logs}\n\nWorkflow:\n{json.dumps(workflow_data, indent=2)}"
                )

                payload = {
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 1024
                    }
                }
                
                try:
                    response = requests.post(self.ollama_url, json=payload, timeout=120)
                    if response.status_code == 200:
                        ollama_response = response.json()
                        response_text = ollama_response.get('response', '')
                        analysis_result = json.loads(response_text.strip())
                        self.logger.info(f"LLM hold analysis successful for {workflow_id}")
                except Exception as e:
                    self.logger.error(f"LLM hold analysis failed: {e}")
                    analysis_result = None
            
            # Use fallback if LLM failed or unavailable
            if not analysis_result:
                self.logger.warning(f"Using fallback hold analysis for {workflow_id}")
                analysis_result = self.generate_fallback_analysis(workflow_id, workflow_dir, logs, "held")
            
            # Store analysis
            analysis_record = {
                "workflow_id": workflow_id,
                "workflow_dir": workflow_dir,
                "analysis_type": "held",
                "hold_reason": hold_reason,
                "timestamp": datetime.now().isoformat(),
                "analysis_result": analysis_result,
                "logs": logs[:1000],
                "yaml_path": yaml_path,
                "llm_available": "hold_analysis" in analysis_result and not analysis_result.get("fallback_mode", False),
                "fallback_used": analysis_result.get("fallback_mode", False)
            }
            self.analysis_table.insert(analysis_record)
            
            # Notify monitor agent if available
            if self.monitor_available and self.config.get("enable_monitor_integration", True):
                await self.notify_monitor_of_analysis(workflow_id, analysis_result, "held")
            
            return {
                "status": "success",
                "message": f"Hold analysis completed for workflow {workflow_id}",
                "analysis": analysis_result,
                "hold_reason": hold_reason,
                "llm_used": analysis_record["llm_available"],
                "fallback_mode": analysis_result.get("fallback_mode", False),
                "monitor_notified": self.monitor_available
            }
            
        except Exception as e:
            error_msg = f"Error analyzing held workflow {workflow_id}: {str(e)}"
            self.logger.error(error_msg)
            
            # Even on error, provide fallback analysis
            fallback_result = self.generate_fallback_analysis(workflow_id, workflow_dir, "", "held")
            return {
                "status": "partial_success",
                "message": error_msg,
                "analysis": fallback_result,
                "hold_reason": hold_reason,
                "error": True,
                "fallback_mode": True
            }

    # Server and communication methods
    async def handle_client_message(self, websocket):
        """Handle incoming WebSocket messages from MCP clients"""
        self.logger.info(f"New client connected: {websocket.remote_address}")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    tool_name = data.get('tool')
                    args = data.get('args', {})
                    
                    if tool_name in self.tools:
                        self.logger.info(f"Executing tool: {tool_name}")
                        result = await self.tools[tool_name](**args)
                        
                        response = {
                            "status": "success",
                            "tool": tool_name,
                            "result": result,
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        response = {
                            "status": "error",
                            "message": f"Unknown tool: {tool_name}",
                            "available_tools": list(self.tools.keys())
                        }
                    
                    await websocket.send(json.dumps(response, indent=2))
                    
                except json.JSONDecodeError:
                    error_response = {"status": "error", "message": "Invalid JSON message"}
                    await websocket.send(json.dumps(error_response))
                except Exception as e:
                    error_response = {"status": "error", "message": f"Tool execution error: {str(e)}"}
                    await websocket.send(json.dumps(error_response))
                    
        except Exception as e:
            self.logger.error(f"Error handling client: {e}")

    async def start_server(self):
        """Start the resilient MCP server"""
        self.logger.info(f"Starting Resilient Analyzer MCP Agent on port {self.port}")
        print(f"✓ Resilient Analyzer MCP Agent starting...")
        print(f"🔍 Available analysis tools: {len(self.tools)}")
        print(f"📊 Database: {len(self.analysis_table.all())} analysis records")
        print(f"🌐 Server: ws://localhost:{self.port}")
        print(f"🦙 LLM Backend: Ollama ({self.ollama_model})")
        print(f"🔗 Ollama URL: {self.ollama_url}")

        # Check Ollama connection (non-blocking)
        ollama_available = self.check_ollama_availability()
        if ollama_available:
            print(f"✅ Ollama connection: OK")
        else:
            print(f"⚠ Ollama connection: Not available")
            print(f"🔄 Fallback mode: Enabled (basic analysis without LLM)")
            print(f"💡 Check Ollama service or update URL in config")

        # Check Monitor Agent connection
        print(f"🔗 Monitor Agent URL: {self.monitor_url}")
        monitor_available = await self.check_monitor_availability()
        if monitor_available:
            print(f"✅ Monitor Agent connection: OK")
        else:
            print(f"⚠ Monitor Agent connection: Not available")
            if self.config.get("enable_monitor_integration", True):
                print(f"💡 Check monitor agent or disable integration in config")
            else:
                print(f"💡 Monitor integration disabled in config")

        print(f"🚀 Agent will continue operating regardless of dependencies")
        print(f"⚙️  Configuration file: {self.config_file}")

        # Start background monitoring tasks
        asyncio.create_task(self.periodic_ollama_check())
        asyncio.create_task(self.periodic_monitor_check())

        async with websockets.serve(self.handle_client_message, "localhost", self.port):
            self.logger.info(f"Analyzer agent running on ws://localhost:{self.port}")
            await asyncio.Future()  # Run forever

    async def periodic_monitor_check(self):
        """Periodically check Monitor agent availability"""
        while True:
            try:
                await asyncio.sleep(self.monitor_check_interval)
                old_status = self.monitor_available
                new_status = await self.check_monitor_availability()
                
                if old_status != new_status:
                    if new_status:
                        self.logger.info("Monitor agent became available")
                    else:
                        self.logger.info("Monitor agent became unavailable")
                        
            except Exception as e:
                self.logger.error(f"Error in periodic monitor check: {e}")

    async def periodic_ollama_check(self):
        """Periodically check Ollama availability"""
        while True:
            try:
                await asyncio.sleep(self.ollama_check_interval)
                old_status = self.ollama_available
                new_status = self.check_ollama_availability()
                
                if old_status != new_status:
                    if new_status:
                        self.logger.info("Ollama became available - switching from fallback mode")
                    else:
                        self.logger.info("Ollama became unavailable - switching to fallback mode")
                        
            except Exception as e:
                self.logger.error(f"Error in periodic Ollama check: {e}")

def main():
    """Main function to run the Resilient Analyzer MCP Agent"""
    agent = ResilientPegasusAnalyzerMCPAgent(port=8766)
    
    try:
        asyncio.run(agent.start_server())
    except KeyboardInterrupt:
        print(f"\n{TerminalColor.YELLOW.apply('👋')} Resilient Analyzer MCP Agent shutting down...")
    except Exception as e:
        print(f"{TerminalColor.RED.apply('❌')} Error: {e}")

if __name__ == "__main__":
    main()
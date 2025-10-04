#!/usr/bin/env python3
"""
Enhanced Pegasus Analyzer Agent - Complete Version
Combines MCP tools for inter-agent communication with HTTP for health checks and events
Enhanced with robust Ollama integration and comprehensive diagnostics
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
import aiohttp
from aiohttp import web, ClientSession
import uuid

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

class PromptManager:
    """Dedicated class for managing LLM prompts for workflow analysis"""
    
    @staticmethod
    def get_workflow_analysis_prompt(logs: str, workflow: Dict[str, Any]) -> str:
        """Generate prompt for workflow failure analysis"""
        return (
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
    
    @staticmethod
    def get_held_workflow_analysis_prompt(logs: str, workflow: Dict[str, Any], hold_reason: str = "") -> str:
        """Generate prompt for held workflow analysis"""
        return (
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
            f"Logs:\n{logs}\n\nWorkflow:\n{json.dumps(workflow, indent=2)}"
        )
    
    @staticmethod
    def get_workflow_optimization_prompt(workflow: Dict[str, Any], performance_data: Dict[str, Any] = None) -> str:
        """Generate prompt for workflow optimization suggestions"""
        return (
            "Analyze the following Pegasus workflow and suggest optimizations for better performance, "
            "resource utilization, and reliability. Consider job parallelization, data locality, "
            "resource requirements, and fault tolerance.\n\n"
            "Provide suggestions in JSON format:\n"
            "{\n"
            "  \"optimizations\": [\n"
            "    {\n"
            "      \"area\": \"parallelization/resource/data/fault_tolerance/other\",\n"
            "      \"suggestion\": \"Specific optimization recommendation\",\n"
            "      \"impact\": \"Expected performance improvement\",\n"
            "      \"implementation\": \"How to implement this optimization\",\n"
            "      \"priority\": \"high/medium/low\"\n"
            "    }\n"
            "  ],\n"
            "  \"overall_assessment\": \"General workflow quality assessment\",\n"
            "  \"confidence_score\": {\"score\": 0.85, \"explanation\": \"...\"}\n"
            "}\n"
            f"Workflow:\n{json.dumps(workflow, indent=2)}\n"
            f"Performance Data:\n{json.dumps(performance_data or {}, indent=2) if performance_data else 'No performance data available'}"
        )
    
    @staticmethod
    def get_error_pattern_analysis_prompt(error_logs: List[str]) -> str:
        """Generate prompt for error pattern analysis across multiple workflows"""
        logs_text = "\n\n--- WORKFLOW SEPARATOR ---\n\n".join(error_logs)
        
        return (
            "Analyze the following collection of Pegasus workflow error logs to identify common patterns, "
            "recurring issues, and systemic problems. Look for trends in failures that might indicate "
            "infrastructure issues, configuration problems, or workflow design patterns that frequently fail.\n\n"
            "Provide analysis in JSON format:\n"
            "{\n"
            "  \"common_patterns\": [\n"
            "    {\n"
            "      \"pattern\": \"Description of the recurring issue\",\n"
            "      \"frequency\": \"How often this pattern appears\",\n"
            "      \"impact\": \"Severity of this pattern\",\n"
            "      \"root_cause\": \"Likely underlying cause\",\n"
            "      \"prevention\": \"How to prevent this pattern\"\n"
            "    }\n"
            "  ],\n"
            "  \"systemic_issues\": [\n"
            "    \"List of infrastructure or configuration issues\"\n"
            "  ],\n"
            "  \"recommendations\": [\n"
            "    \"Overall recommendations for improving workflow reliability\"\n"
            "  ],\n"
            "  \"confidence_score\": {\"score\": 0.85, \"explanation\": \"...\"}\n"
            "}\n"
            f"Error Logs:\n{logs_text}"
        )

class OllamaConnectionManager:
    """Enhanced Ollama connection management with detailed diagnostics"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ollama_api_base = config.get("ollama_api_base", "http://localhost:11434")
        self.ollama_url = config.get("ollama_url", f"{self.ollama_api_base}/api/generate")
        self.ollama_model = config.get("ollama_model", "qwen2.5:7b")
        self.connection_timeout = config.get("connection_timeout", 10)
        
        # Connection status tracking
        self.last_health_check = 0
        self.health_check_interval = config.get("ollama_check_interval", 30)
        self.is_healthy = False
        self.model_available = False
        self.last_error = None
        self.connection_history = []
        
        # Setup logging
        self.logger = logging.getLogger(f"{__name__}.OllamaManager")
    
    def log_connection_attempt(self, endpoint: str, success: bool, error: str = None):
        """Log connection attempt with timestamp"""
        self.connection_history.append({
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint,
            "success": success,
            "error": error
        })
        
        # Keep only last 20 attempts
        self.connection_history = self.connection_history[-20:]
    
    def test_base_connectivity(self) -> Tuple[bool, str]:
        """Test basic connectivity to Ollama server"""
        try:
            response = requests.get(
                self.ollama_api_base, 
                timeout=self.connection_timeout,
                headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
            )
            
            if response.status_code == 200:
                self.log_connection_attempt("base", True)
                return True, "Base connectivity OK"
            else:
                error_msg = f"Base endpoint returned HTTP {response.status_code}"
                self.log_connection_attempt("base", False, error_msg)
                return False, error_msg
                
        except requests.exceptions.ConnectTimeout:
            error_msg = "Connection timeout to Ollama server"
            self.log_connection_attempt("base", False, error_msg)
            return False, error_msg
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error: {str(e)}"
            self.log_connection_attempt("base", False, error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.log_connection_attempt("base", False, error_msg)
            return False, error_msg
    
    def test_tags_endpoint(self) -> Tuple[bool, str]:
        """Test /api/tags endpoint and model availability"""
        try:
            tags_url = f"{self.ollama_api_base}/api/tags"
            response = requests.get(
                tags_url, 
                timeout=self.connection_timeout,
                headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                if self.ollama_model in model_names:
                    self.model_available = True
                    success_msg = f"Model {self.ollama_model} available ({len(models)} total models)"
                    self.log_connection_attempt("tags", True)
                    return True, success_msg
                else:
                    self.model_available = False
                    error_msg = f"Model {self.ollama_model} not found. Available: {model_names[:3]}"
                    self.log_connection_attempt("tags", False, error_msg)
                    return False, error_msg
            else:
                error_msg = f"Tags endpoint returned HTTP {response.status_code}: {response.text[:200]}"
                self.log_connection_attempt("tags", False, error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Tags endpoint error: {str(e)}"
            self.log_connection_attempt("tags", False, error_msg)
            return False, error_msg
    
    def test_generation_endpoint(self) -> Tuple[bool, str]:
        """Test actual text generation capability"""
        if not self.model_available:
            return False, "Model not available - skipping generation test"
        
        test_payload = {
            "model": self.ollama_model,
            "prompt": "Respond with exactly: TEST_OK",
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 10
            }
        }
        
        try:
            response = requests.post(
                self.ollama_url,
                json=test_payload,
                timeout=30,  # Generation can take longer
                headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                generated_text = data.get('response', '').strip()
                
                if generated_text:
                    success_msg = f"Generation working. Response: '{generated_text[:50]}'"
                    self.log_connection_attempt("generate", True)
                    return True, success_msg
                else:
                    error_msg = "Generation returned empty response"
                    self.log_connection_attempt("generate", False, error_msg)
                    return False, error_msg
            else:
                error_msg = f"Generation endpoint returned HTTP {response.status_code}: {response.text[:200]}"
                self.log_connection_attempt("generate", False, error_msg)
                return False, error_msg
                
        except requests.exceptions.Timeout:
            error_msg = "Generation request timed out (>30s)"
            self.log_connection_attempt("generate", False, error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Generation endpoint error: {str(e)}"
            self.log_connection_attempt("generate", False, error_msg)
            return False, error_msg
    
    def test_json_generation(self) -> Tuple[bool, str]:
        """Test JSON format generation specifically"""
        if not self.model_available:
            return False, "Model not available - skipping JSON test"
        
        test_payload = {
            "model": self.ollama_model,
            "prompt": 'Respond with valid JSON: {"status": "ok", "test": true}',
            "stream": False,
            "format": "json",  # This might not be supported by older Ollama versions
            "options": {
                "temperature": 0.0,
                "num_predict": 50
            }
        }
        
        try:
            response = requests.post(
                self.ollama_url,
                json=test_payload,
                timeout=30,
                headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                generated_text = data.get('response', '').strip()
                
                try:
                    parsed_json = json.loads(generated_text)
                    success_msg = f"JSON generation working: {parsed_json}"
                    self.log_connection_attempt("json", True)
                    return True, success_msg
                except json.JSONDecodeError:
                    # Try without explicit JSON format
                    return self.test_json_generation_fallback()
            else:
                error_msg = f"JSON generation returned HTTP {response.status_code}: {response.text[:200]}"
                self.log_connection_attempt("json", False, error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"JSON generation error: {str(e)}"
            self.log_connection_attempt("json", False, error_msg)
            return False, error_msg
    
    def test_json_generation_fallback(self) -> Tuple[bool, str]:
        """Test JSON generation without explicit format parameter"""
        test_payload = {
            "model": self.ollama_model,
            "prompt": 'You must respond with valid JSON only: {"status": "ok", "message": "json working"}',
            "stream": False,
            # No format parameter
            "options": {
                "temperature": 0.0,
                "num_predict": 100
            }
        }
        
        try:
            response = requests.post(
                self.ollama_url,
                json=test_payload,
                timeout=30,
                headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                generated_text = data.get('response', '').strip()
                
                # Try to extract JSON from response
                try:
                    # Look for JSON in the response
                    start = generated_text.find('{')
                    end = generated_text.rfind('}') + 1
                    if start >= 0 and end > start:
                        json_text = generated_text[start:end]
                        parsed_json = json.loads(json_text)
                        success_msg = f"JSON fallback working: {parsed_json}"
                        self.log_connection_attempt("json_fallback", True)
                        return True, success_msg
                    else:
                        error_msg = f"No JSON found in response: {generated_text[:100]}"
                        self.log_connection_attempt("json_fallback", False, error_msg)
                        return False, error_msg
                except json.JSONDecodeError as e:
                    error_msg = f"JSON parsing failed: {e}. Text: {generated_text[:100]}"
                    self.log_connection_attempt("json_fallback", False, error_msg)
                    return False, error_msg
            else:
                error_msg = f"JSON fallback returned HTTP {response.status_code}"
                self.log_connection_attempt("json_fallback", False, error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"JSON fallback error: {str(e)}"
            self.log_connection_attempt("json_fallback", False, error_msg)
            return False, error_msg
    
    def comprehensive_health_check(self) -> Dict[str, Any]:
        """Run comprehensive health check with detailed results"""
        self.logger.info("Starting comprehensive Ollama health check...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "overall_healthy": False,
            "tests": {},
            "recommendations": []
        }
        
        # Test 1: Base connectivity
        base_ok, base_msg = self.test_base_connectivity()
        results["tests"]["base_connectivity"] = {"success": base_ok, "message": base_msg}
        
        if not base_ok:
            results["recommendations"].extend([
                "Check if Ollama server is running",
                "Verify network connectivity to Ollama server",
                f"Test manually: curl {self.ollama_api_base}"
            ])
            self.is_healthy = False
            self.last_error = base_msg
            return results
        
        # Test 2: Tags endpoint and model availability
        tags_ok, tags_msg = self.test_tags_endpoint()
        results["tests"]["model_availability"] = {"success": tags_ok, "message": tags_msg}
        
        if not tags_ok:
            results["recommendations"].extend([
                f"Pull the required model: ollama pull {self.ollama_model}",
                "Check available models: ollama list",
                "Verify model name spelling in configuration"
            ])
            self.is_healthy = False
            self.last_error = tags_msg
            return results
        
        # Test 3: Basic generation
        gen_ok, gen_msg = self.test_generation_endpoint()
        results["tests"]["text_generation"] = {"success": gen_ok, "message": gen_msg}
        
        if not gen_ok:
            results["recommendations"].extend([
                "Check Ollama server logs for errors",
                "Try restarting Ollama service",
                f"Test model manually: ollama run {self.ollama_model}"
            ])
            self.is_healthy = False
            self.last_error = gen_msg
            return results
        
        # Test 4: JSON generation (critical for analyzer)
        json_ok, json_msg = self.test_json_generation()
        results["tests"]["json_generation"] = {"success": json_ok, "message": json_msg}
        
        if not json_ok:
            results["recommendations"].extend([
                "JSON format may not be supported - will use text parsing",
                "Consider updating Ollama to latest version",
                "JSON analysis will use fallback parsing method"
            ])
            # JSON failure is not critical - we can parse manually
        
        # Overall health determination
        critical_tests = ["base_connectivity", "model_availability", "text_generation"]
        all_critical_passed = all(results["tests"][test]["success"] for test in critical_tests)
        
        if all_critical_passed:
            self.is_healthy = True
            self.last_error = None
            results["overall_healthy"] = True
            results["recommendations"] = ["All critical tests passed - Ollama ready for analysis"]
        else:
            self.is_healthy = False
            results["overall_healthy"] = False
        
        self.last_health_check = time.time()
        return results
    
    def quick_health_check(self) -> bool:
        """Quick health check using cached results when possible"""
        current_time = time.time()
        
        # Use cached result if recent
        if (current_time - self.last_health_check) < self.health_check_interval:
            return self.is_healthy
        
        # Quick connectivity test
        try:
            response = requests.get(
                f"{self.ollama_api_base}/api/tags",
                timeout=5,
                headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                self.is_healthy = self.ollama_model in model_names
                self.model_available = self.is_healthy
                
                if self.is_healthy:
                    self.last_error = None
                else:
                    self.last_error = f"Model {self.ollama_model} not available"
            else:
                self.is_healthy = False
                self.last_error = f"Ollama API returned {response.status_code}"
                
        except Exception as e:
            self.is_healthy = False
            self.last_error = str(e)
        
        self.last_health_check = current_time
        return self.is_healthy
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status"""
        return {
            "is_healthy": self.is_healthy,
            "model_available": self.model_available,
            "last_error": self.last_error,
            "last_health_check": datetime.fromtimestamp(self.last_health_check).isoformat() if self.last_health_check else None,
            "config": {
                "api_base": self.ollama_api_base,
                "generate_url": self.ollama_url,
                "model": self.ollama_model,
                "timeout": self.connection_timeout
            },
            "connection_history": self.connection_history[-5:],  # Last 5 attempts
            "next_health_check": datetime.fromtimestamp(
                self.last_health_check + self.health_check_interval
            ).isoformat() if self.last_health_check else "Now"
        }

class AgentRegistry:
    """Manages registry of known agents"""
    
    def __init__(self, db_path: str = "analyzer_agents.json"):
        self.db = TinyDB(db_path)
        self.agents_table = self.db.table("agents")
        self.agents = {}
        self.load_agents_from_db()

    def load_agents_from_db(self):
        """Load agents from database"""
        try:
            agents = self.agents_table.all()
            for agent in agents:
                self.agents[agent['agent_id']] = agent
        except Exception as e:
            logging.error(f"Error loading agents from DB: {e}")

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
            self.agents_table.upsert(agent_info, Query().agent_id == agent_id)
            logging.info(f"Registered agent {agent_id} ({agent_type})")
            return True
        except Exception as e:
            logging.error(f"Error registering agent {agent_id}: {e}")
            return False

    async def health_check_agent(self, agent_id: str) -> bool:
        """Perform health check on specific agent"""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{agent['http_url']}/health") as resp:
                    if resp.status == 200:
                        agent['status'] = 'healthy'
                        agent['last_health_check'] = datetime.now().isoformat()
                        self.agents_table.update(agent, Query().agent_id == agent_id)
                        return True
        except Exception as e:
            logging.debug(f"Health check failed for {agent_id}: {e}")
        
        agent['status'] = 'unhealthy'
        agent['last_health_check'] = datetime.now().isoformat()
        self.agents_table.update(agent, Query().agent_id == agent_id)
        return False

    def get_agents_by_type(self, agent_type: str) -> List[Dict[str, Any]]:
        """Get all agents of specific type"""
        return [agent for agent in self.agents.values() if agent.get('agent_type') == agent_type]

class EnhancedAnalyzerAgent:
    def __init__(self, mcp_port: int = 8766, http_port: int = 8081, config_file: str = "analyzer_config.json"):
        """Initialize the Enhanced Analyzer Agent with improved Ollama integration"""
        self.mcp_port = mcp_port
        self.http_port = http_port
        self.config_file = config_file

        # Setup logging with more detail
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('analyzer_agent.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

        # Load configuration
        self.config = self.load_config()
        if "log_level" in self.config:
            logging.getLogger().setLevel(getattr(logging, self.config["log_level"], "INFO"))
    
        # Database setup
        self.db = TinyDB('analyzer_agent_db.json')
        self.analysis_table = self.db.table('workflow_analysis')
        self.failed_workflows_table = self.db.table('failed_workflows')
        
        # Enhanced Ollama connection manager
        self.ollama_manager = OllamaConnectionManager(self.config)
        
        # Prompt manager for LLM interactions
        self.prompt_manager = PromptManager()
        
        # Agent registry
        self.agent_registry = AgentRegistry()
        
        # Resilience settings
        self.push_notifications_enabled = self.config.get("push_notifications_enabled", True)
        self.auto_analysis_enabled = self.config.get("auto_analysis_enabled", True)
        self.fallback_mode = self.config.get("fallback_mode", True)
        
        # Track analysis requests
        self.active_analyses = {}
        self.analysis_queue = []
        
        # MCP Tools - keeping all existing ones but enhancing Ollama integration
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
            "get_connection_status": self.get_connection_status,
            "update_configuration": self.update_configuration,
            "get_configuration": self.get_configuration,
            # New enhanced tools
            "run_ollama_diagnostics": self.run_ollama_diagnostics,
            "force_ollama_health_check": self.force_ollama_health_check,
            "analyze_error_patterns": self.analyze_error_patterns,
            "optimize_workflow": self.optimize_workflow
        }
        
        # HTTP server components
        self.app = web.Application()
        self.setup_http_routes()
        
        # Register default monitor agents
        self.register_default_agents()
        
        self.logger.info(f"Enhanced Analyzer Agent initialized with {len(self.tools)} MCP tools")
        self.logger.info(f"Ollama Manager: {self.ollama_manager.ollama_api_base}")

    def load_config(self) -> Dict[str, Any]:
        """Load configuration with better defaults"""
        default_config = {
            "ollama_api_base": "http://localhost:11434",
            "ollama_model": "qwen2.5:7b",
            "ollama_check_interval": 30,
            "connection_timeout": 15,
            "generation_timeout": 120,
            "push_notifications_enabled": True,
            "auto_analysis_enabled": True,
            "fallback_mode": True,
            "log_level": "INFO",
            "retry_attempts": 3,
            "use_json_format": True,  # Try JSON format first, fallback if unsupported
            "monitor_agents": [
                {
                    "agent_id": "monitor_001",
                    "mcp_url": "ws://localhost:8765",
                    "http_url": "http://localhost:8080"
                }
            ]
        }

        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                default_config.update(loaded_config)
                self.logger.info(f"Configuration loaded from {self.config_file}")
            else:
                with open(self.config_file, 'w') as f:
                    json.dump(default_config, f, indent=4)
                self.logger.info(f"Created default configuration file: {self.config_file}")
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}. Using defaults.")

        # Ensure ollama_url is derived from api_base if not explicitly set
        if "ollama_url" not in default_config:
            default_config["ollama_url"] = f"{default_config['ollama_api_base']}/api/generate"

        return default_config

    def register_default_agents(self):
        """Register default known agents from config"""
        monitor_agents = self.config.get("monitor_agents", [])
        for monitor in monitor_agents:
            self.agent_registry.register_agent(
                monitor["agent_id"],
                "monitor",
                monitor["mcp_url"],
                monitor["http_url"],
                ["workflow_monitoring", "job_tracking", "log_files"]
            )

    def setup_http_routes(self):
        """Setup HTTP routes"""
        # Health endpoint
        self.app.router.add_get('/health', self.handle_health)
        
        # Analysis endpoints
        self.app.router.add_post('/api/analyze', self.handle_analyze_request)
        self.app.router.add_get('/api/analyze/{request_id}/status', self.handle_get_analysis_status)
        self.app.router.add_get('/api/analysis/{workflow_id}/results', self.handle_get_analysis_results_http)
        
        # Configuration endpoints
        self.app.router.add_get('/api/config', self.handle_get_config)
        self.app.router.add_post('/api/config', self.handle_update_config)
        
        # Agent registry endpoints
        self.app.router.add_get('/api/agents/registry', self.handle_get_agents)
        self.app.router.add_post('/api/agents/register', self.handle_register_agent)
        
        # Ollama diagnostics endpoints
        self.app.router.add_get('/api/ollama/status', self.handle_ollama_status)
        self.app.router.add_post('/api/ollama/test', self.handle_test_ollama)

    def send_logs_and_workflow_to_llm_enhanced(self, logs: str, workflow: Dict[str, Any], analysis_type: str = "failed", hold_reason: str = "") -> Optional[Dict[str, Any]]:
        """Enhanced LLM communication with better error handling and fallback"""
        
        # First, check if Ollama is healthy
        if not self.ollama_manager.quick_health_check():
            self.logger.warning(f"Ollama not healthy: {self.ollama_manager.last_error}")
            if not self.fallback_mode:
                return None
            # Continue to try anyway in fallback mode
        
        # Generate appropriate prompt based on analysis type
        if analysis_type == "held":
            prompt = self.prompt_manager.get_held_workflow_analysis_prompt(logs, workflow, hold_reason)
        else:
            prompt = self.prompt_manager.get_workflow_analysis_prompt(logs, workflow)

        # Try with JSON format first (if supported)
        if self.config.get("use_json_format", True):
            result = self._try_llm_request(prompt, use_json_format=True)
            if result:
                return result
            
            self.logger.info("JSON format failed, trying without format parameter")
        
        # Fallback: try without JSON format
        result = self._try_llm_request(prompt, use_json_format=False)
        if result:
            return result
        
        self.logger.error("All LLM request attempts failed")
        return None

    def _try_llm_request(self, prompt: str, use_json_format: bool = True) -> Optional[Dict[str, Any]]:
        """Try a single LLM request with detailed error handling"""
        
        payload = {
            "model": self.ollama_manager.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 2048
            }
        }
        
        if use_json_format:
            payload["format"] = "json"
        
        max_retries = self.config.get("retry_attempts", 3)
        generation_timeout = self.config.get("generation_timeout", 120)
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"LLM request attempt {attempt + 1}/{max_retries} (JSON format: {use_json_format})")
                
                response = requests.post(
                    self.ollama_manager.ollama_url, 
                    json=payload, 
                    timeout=generation_timeout,
                    headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
                )
                
                if response.status_code == 200:
                    ollama_response = response.json()
                    response_text = ollama_response.get('response', '').strip()
                    
                    if not response_text:
                        self.logger.warning(f"Empty response from Ollama on attempt {attempt + 1}")
                        continue
                    
                    # Update connection status on success
                    self.ollama_manager.is_healthy = True
                    self.ollama_manager.last_error = None
                    self.ollama_manager.log_connection_attempt("generate", True)
                    
                    return {
                        "choices": [{
                            "message": {
                                "content": response_text
                            }
                        }]
                    }
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    self.logger.error(f"Ollama API Error on attempt {attempt + 1}: {error_msg}")
                    self.ollama_manager.log_connection_attempt("generate", False, error_msg)
                    
                    # Don't retry on client errors (4xx)
                    if 400 <= response.status_code < 500:
                        break
                        
            except requests.exceptions.Timeout:
                error_msg = f"Request timeout ({generation_timeout}s) on attempt {attempt + 1}"
                self.logger.error(error_msg)
                self.ollama_manager.log_connection_attempt("generate", False, error_msg)
                
            except requests.exceptions.ConnectionError as e:
                error_msg = f"Connection error on attempt {attempt + 1}: {str(e)}"
                self.logger.error(error_msg)
                self.ollama_manager.log_connection_attempt("generate", False, error_msg)
                
            except requests.exceptions.RequestException as e:
                error_msg = f"Request failed on attempt {attempt + 1}: {str(e)}"
                self.logger.error(error_msg)
                self.ollama_manager.log_connection_attempt("generate", False, error_msg)
                
            except Exception as e:
                error_msg = f"Unexpected error on attempt {attempt + 1}: {str(e)}"
                self.logger.error(error_msg)
                self.ollama_manager.log_connection_attempt("generate", False, error_msg)
            
            # Wait before retry (exponential backoff)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                self.logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        # Mark as unhealthy after all retries failed
        self.ollama_manager.is_healthy = False
        self.ollama_manager.last_error = "All generation attempts failed"
        
        return None

    def extract_workflow_info_enhanced(self, json_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced workflow info extraction with better JSON parsing"""
        try:
            assistant_message = json_payload.get("choices", [])[0].get("message", {}).get("content", "")
            cleaned_json = assistant_message.strip()
            
            # Remove markdown code blocks if present
            if "```json" in cleaned_json:
                start = cleaned_json.find("```json") + 7
                end = cleaned_json.rfind("```")
                if end > start:
                    cleaned_json = cleaned_json[start:end].strip()
            elif "```" in cleaned_json:
                cleaned_json = cleaned_json.replace("```", "").strip()
            
            # Try to find JSON object in the response
            start_brace = cleaned_json.find('{')
            end_brace = cleaned_json.rfind('}')
            
            if start_brace >= 0 and end_brace > start_brace:
                json_text = cleaned_json[start_brace:end_brace + 1]
                try:
                    parsed_json = json.loads(json_text)
                except json.JSONDecodeError:
                    # Try to fix common JSON issues
                    json_text = self._fix_common_json_issues(json_text)
                    parsed_json = json.loads(json_text)
            else:
                return {"error": "No JSON object found in response", "raw_response": cleaned_json[:500]}

            if isinstance(parsed_json, dict):
                problems_and_solutions = parsed_json.get("problems_and_solutions", [])
                confidence_score = parsed_json.get("confidence_score", {"score": 0.0, "explanation": "No confidence data"})

                extracted_info = {
                    "problems_and_solutions": [],
                    "confidence_score": confidence_score,
                    "analysis_timestamp": datetime.now().isoformat(),
                    "total_issues": len(problems_and_solutions),
                    "llm_analysis": True,
                    "raw_response_preview": cleaned_json[:200] + "..." if len(cleaned_json) > 200 else cleaned_json
                }

                for problem_solution in problems_and_solutions:
                    problem_info = {
                        "problem": problem_solution.get("problem", "Unknown problem"),
                        "solution": problem_solution.get("solution", "No solution provided"),
                        "explanation": problem_solution.get("explanation", "No explanation provided"),
                        "priority": problem_solution.get("priority", "medium"),
                        "error_level": problem_solution.get("error_level", "other"),
                        "file_path": problem_solution.get("file_path", ""),
                        "level": problem_solution.get("level", "system")
                    }
                    extracted_info["problems_and_solutions"].append(problem_info)

                return extracted_info
            else:
                return {"error": "Parsed JSON is not a dictionary", "parsed_data": parsed_json}
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error in workflow info extraction: {e}")
            return {
                "error": f"Failed to parse JSON response: {str(e)}", 
                "raw_response": cleaned_json[:500] if 'cleaned_json' in locals() else "No response"
            }
        except KeyError as e:
            self.logger.error(f"Key error in workflow info extraction: {e}")
            return {"error": f"Missing expected key in response: {str(e)}"}
        except Exception as e:
            self.logger.error(f"Error extracting workflow info: {e}")
            return {"error": f"Failed to extract workflow info: {str(e)}"}

    def _fix_common_json_issues(self, json_text: str) -> str:
        """Fix common JSON formatting issues"""
        # Remove trailing commas
        json_text = json_text.replace(',}', '}').replace(',]', ']')
        
        # Fix unescaped quotes in strings (basic attempt)
        lines = json_text.split('\n')
        fixed_lines = []
        for line in lines:
            if ':' in line and '"' in line:
                # Try to fix unescaped quotes in values
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key_part = parts[0]
                    value_part = parts[1].strip()
                    if value_part.startswith('"') and value_part.endswith('"') and value_part.count('"') > 2:
                        # Multiple quotes in value - escape internal ones
                        value_content = value_part[1:-1]
                        value_content = value_content.replace('"', '\\"')
                        value_part = f'"{value_content}"'
                        line = f"{key_part}: {value_part}"
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

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

    def generate_fallback_analysis(self, workflow_id: str, workflow_dir: str, logs: str, analysis_type: str = "failed") -> Dict[str, Any]:
        """Enhanced fallback analysis with better pattern detection"""
        self.logger.info(f"Generating fallback analysis for {workflow_id} (type: {analysis_type})")
        
        error_indicators = []
        specific_issues = []
        
        # Enhanced error pattern detection
        log_lower = logs.lower()
        
        # File system issues
        if "permission denied" in log_lower:
            error_indicators.append("Permission issues detected")
            specific_issues.append({
                "problem": "Permission denied errors found",
                "solution": "Check file and directory permissions",
                "priority": "high",
                "error_level": "site"
            })
        
        if "no such file" in log_lower or "file not found" in log_lower:
            error_indicators.append("File not found errors detected")
            specific_issues.append({
                "problem": "Missing input files or paths",
                "solution": "Verify all input file paths exist and are accessible",
                "priority": "high",
                "error_level": "workflow"
            })
        
        # Network/connectivity issues
        if "timeout" in log_lower:
            error_indicators.append("Timeout issues detected")
            specific_issues.append({
                "problem": "Timeout errors in workflow execution",
                "solution": "Increase timeout values or check network connectivity",
                "priority": "medium",
                "error_level": "site"
            })
        
        if "connection" in log_lower and ("refused" in log_lower or "failed" in log_lower):
            error_indicators.append("Connection issues detected")
            specific_issues.append({
                "problem": "Network connection failures",
                "solution": "Check network connectivity and service availability",
                "priority": "high",
                "error_level": "site"
            })
        
        # Resource issues
        if "memory" in log_lower or "out of memory" in log_lower:
            error_indicators.append("Memory-related issues detected")
            specific_issues.append({
                "problem": "Memory allocation issues",
                "solution": "Increase available memory or optimize workflow",
                "priority": "high",
                "error_level": "site"
            })
        
        # Pegasus-specific errors
        if "replica" in log_lower and "error" in log_lower:
            error_indicators.append("Replica management issues detected")
            specific_issues.append({
                "problem": "Data replica handling errors",
                "solution": "Check replica catalog and data locations",
                "priority": "medium",
                "error_level": "replica"
            })
        
        if "transformation" in log_lower and ("failed" in log_lower or "error" in log_lower):
            error_indicators.append("Transformation execution issues detected")
            specific_issues.append({
                "problem": "Job transformation failures",
                "solution": "Check transformation definitions and execution environment",
                "priority": "high",
                "error_level": "transformation"
            })
        
        # Default issue if no specific patterns found
        if not specific_issues:
            specific_issues.append({
                "problem": "Workflow failed - manual analysis required",
                "solution": "Review workflow logs and configuration for specific error details",
                "priority": "medium",
                "error_level": "other"
            })
        
        if analysis_type == "held":
            analysis_result = {
                "hold_analysis": [
                    {
                        "reason": "Automated analysis without LLM - manual review recommended",
                        "solution": issue["solution"],
                        "priority": issue["priority"],
                        "category": issue["error_level"]
                    } for issue in specific_issues
                ],
                "recommended_actions": [
                    "Review workflow logs manually for specific error messages",
                    "Check resource availability and quotas",
                    "Verify input file paths and accessibility",
                    "Check network connectivity to required services",
                    "Verify service dependencies are running"
                ],
                "confidence_score": {
                    "score": 0.4 if specific_issues else 0.2,
                    "explanation": "Pattern-based analysis without LLM - confidence limited"
                },
                "fallback_mode": True,
                "error_indicators": error_indicators,
                "detected_patterns": len(specific_issues)
            }
        else:
            analysis_result = {
                "problems_and_solutions": [
                    {
                        "problem": issue["problem"],
                        "solution": issue["solution"],
                        "explanation": "Detected through pattern matching in logs",
                        "error_level": issue["error_level"],
                        "priority": issue["priority"],
                        "level": "system",
                        "file_path": workflow_dir
                    } for issue in specific_issues
                ],
                "confidence_score": {
                    "score": 0.4 if specific_issues else 0.2,
                    "explanation": f"Pattern-based analysis detected {len(specific_issues)} potential issues"
                },
                "analysis_timestamp": datetime.now().isoformat(),
                "total_issues": len(specific_issues),
                "fallback_mode": True,
                "error_indicators": error_indicators,
                "llm_analysis": False
            }
        
        return analysis_result

    # Core Analysis Methods
    async def analyze_failed_workflow(self, workflow_id: str, workflow_dir: str) -> Dict[str, Any]:
        """Analyze a failed workflow using enhanced LLM integration"""
        self.logger.info(f"Analyzing failed workflow: {workflow_id}")
        
        try:
            logs = self.run_pegasus_analyzer(workflow_dir)
            yaml_path = self.find_yaml_file(workflow_dir)
            
            workflow_data = {}
            if yaml_path:
                workflow_data = self.load_workflow_yaml(yaml_path)
            
            analysis_result = None
            llm_response = self.send_logs_and_workflow_to_llm_enhanced(logs, workflow_data, "failed")
            
            if llm_response:
                analysis_result = self.extract_workflow_info_enhanced(llm_response)
                if "error" not in analysis_result:
                    self.logger.info(f"LLM analysis successful for {workflow_id}")
                else:
                    self.logger.warning(f"LLM analysis had errors: {analysis_result['error']}")
                    llm_response = None
            
            if not llm_response or not analysis_result or "error" in analysis_result:
                self.logger.warning(f"Using fallback analysis for {workflow_id}")
                analysis_result = self.generate_fallback_analysis(workflow_id, workflow_dir, logs, "failed")
            
            # Enhanced analysis record with more diagnostics
            analysis_record = {
                "workflow_id": workflow_id,
                "workflow_dir": workflow_dir,
                "analysis_type": "failed",
                "timestamp": datetime.now().isoformat(),
                "analysis_result": analysis_result,
                "logs": logs[:1000],  # Store first 1000 chars of logs
                "yaml_path": yaml_path,
                "llm_available": bool(llm_response),
                "fallback_used": "fallback_mode" in analysis_result,
                "ollama_status": self.ollama_manager.get_connection_status()
            }
            self.analysis_table.insert(analysis_record)

            # PRINT ANALYSIS OUTPUT TO CONSOLE
            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_GREEN.apply('🔍 WORKFLOW ANALYSIS COMPLETED')}")
            print(f"{'='*80}")
            print(f"{TerminalColor.CYAN.apply('Workflow ID:')} {workflow_id}")
            print(f"{TerminalColor.CYAN.apply('Workflow Dir:')} {workflow_dir}")
            print(f"{TerminalColor.CYAN.apply('Analysis Type:')} Failed Workflow")
            print(f"{TerminalColor.CYAN.apply('LLM Used:')} {bool(llm_response)}")
            print(f"{TerminalColor.CYAN.apply('Fallback Mode:')} {'fallback_mode' in analysis_result}")
            print(f"{TerminalColor.CYAN.apply('Ollama Healthy:')} {self.ollama_manager.is_healthy}")

            print(f"\n{TerminalColor.BRIGHT_YELLOW.apply('📋 Problems & Solutions:')}")
            problems = analysis_result.get("problems_and_solutions", [])
            if problems:
                for idx, problem in enumerate(problems, 1):
                    print(f"\n  {TerminalColor.WHITE.apply(f'Issue #{idx}:')}")
                    print(f"    {TerminalColor.RED.apply('Problem:')} {problem.get('problem', 'N/A')}")
                    print(f"    {TerminalColor.GREEN.apply('Solution:')} {problem.get('solution', 'N/A')}")
                    print(f"    {TerminalColor.YELLOW.apply('Priority:')} {problem.get('priority', 'N/A')}")
                    print(f"    {TerminalColor.BLUE.apply('Error Level:')} {problem.get('error_level', 'N/A')}")
                    if problem.get('file_path'):
                        print(f"    {TerminalColor.CYAN.apply('File:')} {problem.get('file_path')}")
            else:
                print(f"  {TerminalColor.YELLOW.apply('No specific problems identified')}")

            confidence = analysis_result.get("confidence_score", {})
            if confidence:
                print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('📊 Confidence Score:')} {confidence.get('score', 'N/A')}")
                print(f"  {confidence.get('explanation', 'N/A')}")
            print(f"{'='*80}\n")

            return {
                "status": "success",
                "message": f"Analysis completed for workflow {workflow_id}",
                "analysis": analysis_result,
                "workflow_dir": workflow_dir,
                "yaml_path": yaml_path,
                "llm_used": bool(llm_response),
                "fallback_mode": "fallback_mode" in analysis_result,
                "ollama_healthy": self.ollama_manager.is_healthy
            }
            
        except Exception as e:
            error_msg = f"Error analyzing workflow {workflow_id}: {str(e)}"
            self.logger.error(error_msg)
            
            fallback_result = self.generate_fallback_analysis(workflow_id, workflow_dir, "", "failed")
            return {
                "status": "partial_success",
                "message": error_msg,
                "analysis": fallback_result,
                "workflow_dir": workflow_dir,
                "error": True,
                "fallback_mode": True,
                "ollama_healthy": False
            }

    async def analyze_held_workflow(self, workflow_id: str, workflow_dir: str, hold_reason: str = "") -> Dict[str, Any]:
        """Analyze a held workflow with enhanced LLM integration"""
        self.logger.info(f"Analyzing held workflow: {workflow_id}")
        
        try:
            logs = self.run_pegasus_analyzer(workflow_dir)
            yaml_path = self.find_yaml_file(workflow_dir)
            workflow_data = {}
            if yaml_path:
                workflow_data = self.load_workflow_yaml(yaml_path)
            
            analysis_result = None
            llm_response = self.send_logs_and_workflow_to_llm_enhanced(logs, workflow_data, "held", hold_reason)
            
            if llm_response:
                # For held workflows, we need different extraction logic
                try:
                    assistant_message = llm_response.get("choices", [])[0].get("message", {}).get("content", "")
                    cleaned_json = assistant_message.strip()
                    
                    # Remove markdown if present
                    if "```json" in cleaned_json:
                        start = cleaned_json.find("```json") + 7
                        end = cleaned_json.rfind("```")
                        if end > start:
                            cleaned_json = cleaned_json[start:end].strip()
                    
                    # Extract JSON
                    start_brace = cleaned_json.find('{')
                    end_brace = cleaned_json.rfind('}')
                    if start_brace >= 0 and end_brace > start_brace:
                        json_text = cleaned_json[start_brace:end_brace + 1]
                        analysis_result = json.loads(json_text)
                        self.logger.info(f"LLM hold analysis successful for {workflow_id}")
                except Exception as e:
                    self.logger.error(f"LLM hold analysis parsing failed: {e}")
                    analysis_result = None
            
            if not analysis_result:
                self.logger.warning(f"Using fallback hold analysis for {workflow_id}")
                analysis_result = self.generate_fallback_analysis(workflow_id, workflow_dir, logs, "held")
            
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

            # PRINT HELD WORKFLOW ANALYSIS OUTPUT
            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_YELLOW.apply('⚠️  HELD WORKFLOW ANALYSIS COMPLETED')}")
            print(f"{'='*80}")
            print(f"{TerminalColor.CYAN.apply('Workflow ID:')} {workflow_id}")
            print(f"{TerminalColor.CYAN.apply('Workflow Dir:')} {workflow_dir}")
            print(f"{TerminalColor.CYAN.apply('Analysis Type:')} Held Workflow")
            print(f"{TerminalColor.CYAN.apply('Hold Reason:')} {hold_reason or 'Not specified'}")
            print(f"{TerminalColor.CYAN.apply('Fallback Mode:')} {analysis_result.get('fallback_mode', False)}")

            print(f"\n{TerminalColor.BRIGHT_YELLOW.apply('🔍 Hold Analysis:')}")
            hold_analyses = analysis_result.get("hold_analysis", [])
            if hold_analyses:
                for idx, hold_item in enumerate(hold_analyses, 1):
                    print(f"\n  {TerminalColor.WHITE.apply(f'Hold Issue #{idx}:')}")
                    print(f"    {TerminalColor.RED.apply('Reason:')} {hold_item.get('reason', 'N/A')}")
                    print(f"    {TerminalColor.GREEN.apply('Solution:')} {hold_item.get('solution', 'N/A')}")
                    print(f"    {TerminalColor.YELLOW.apply('Priority:')} {hold_item.get('priority', 'N/A')}")
                    print(f"    {TerminalColor.BLUE.apply('Category:')} {hold_item.get('category', 'N/A')}")
            else:
                print(f"  {TerminalColor.YELLOW.apply('No specific hold reasons identified')}")

            recommended_actions = analysis_result.get("recommended_actions", [])
            if recommended_actions:
                print(f"\n{TerminalColor.BRIGHT_CYAN.apply('💡 Recommended Actions:')}")
                for idx, action in enumerate(recommended_actions, 1):
                    print(f"  {idx}. {action}")

            confidence = analysis_result.get("confidence_score", {})
            if confidence:
                print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('📊 Confidence Score:')} {confidence.get('score', 'N/A')}")
                print(f"  {confidence.get('explanation', 'N/A')}")
            print(f"{'='*80}\n")

            return {
                "status": "success",
                "message": f"Hold analysis completed for workflow {workflow_id}",
                "analysis": analysis_result,
                "hold_reason": hold_reason,
                "llm_used": analysis_record["llm_available"],
                "fallback_mode": analysis_result.get("fallback_mode", False)
            }
            
        except Exception as e:
            error_msg = f"Error analyzing held workflow {workflow_id}: {str(e)}"
            self.logger.error(error_msg)
            
            fallback_result = self.generate_fallback_analysis(workflow_id, workflow_dir, "", "held")
            return {
                "status": "partial_success",
                "message": error_msg,
                "analysis": fallback_result,
                "hold_reason": hold_reason,
                "error": True,
                "fallback_mode": True
            }

    # New enhanced analysis methods
    async def analyze_error_patterns(self, workflow_ids: List[str] = None, limit: int = 50) -> Dict[str, Any]:
        """Analyze error patterns across multiple workflows using LLM"""
        try:
            if workflow_ids:
                # Analyze specific workflows
                Query_obj = Query()
                analyses = [self.analysis_table.search(Query_obj.workflow_id == wf_id) for wf_id in workflow_ids]
                analyses = [a for sublist in analyses for a in sublist if a]  # Flatten and filter
            else:
                # Analyze recent failed workflows
                all_analyses = self.analysis_table.all()
                failed_analyses = [a for a in all_analyses if a.get('analysis_type') == 'failed']
                analyses = sorted(failed_analyses, key=lambda x: x['timestamp'], reverse=True)[:limit]
            
            if not analyses:
                return {
                    "status": "error",
                    "message": "No workflow analyses found for pattern analysis"
                }
            
            # Extract error logs
            error_logs = []
            for analysis in analyses:
                logs = analysis.get('logs', '')
                if logs and 'ERROR' not in logs:  # Skip if no actual logs
                    continue
                workflow_id = analysis.get('workflow_id', 'unknown')
                error_logs.append(f"WORKFLOW_ID: {workflow_id}\n{logs}")
            
            if not error_logs:
                return {
                    "status": "error", 
                    "message": "No error logs found in the selected analyses"
                }
            
            # Use LLM to analyze patterns
            prompt = self.prompt_manager.get_error_pattern_analysis_prompt(error_logs[:20])  # Limit to prevent token overflow
            
            llm_response = self._try_llm_request(prompt, use_json_format=True)
            if not llm_response:
                llm_response = self._try_llm_request(prompt, use_json_format=False)
            
            pattern_analysis = None
            if llm_response:
                try:
                    assistant_message = llm_response.get("choices", [])[0].get("message", {}).get("content", "")
                    # Extract JSON from response
                    start_brace = assistant_message.find('{')
                    end_brace = assistant_message.rfind('}')
                    if start_brace >= 0 and end_brace > start_brace:
                        json_text = assistant_message[start_brace:end_brace + 1]
                        pattern_analysis = json.loads(json_text)
                except Exception as e:
                    self.logger.error(f"Error parsing pattern analysis: {e}")
                    pattern_analysis = None
            
            # Fallback pattern analysis if LLM fails
            if not pattern_analysis:
                # Basic pattern detection
                all_logs_text = "\n".join(error_logs)
                common_errors = {}
                
                error_patterns = [
                    "permission denied", "file not found", "connection refused", 
                    "timeout", "memory", "disk space", "authentication failed",
                    "replica", "transformation", "job failed"
                ]
                
                for pattern in error_patterns:
                    count = all_logs_text.lower().count(pattern)
                    if count > 0:
                        common_errors[pattern] = count
                
                pattern_analysis = {
                    "common_patterns": [
                        {
                            "pattern": pattern,
                            "frequency": f"Found {count} times",
                            "impact": "medium" if count < 5 else "high",
                            "root_cause": "Requires manual investigation",
                            "prevention": "Review logs and system configuration"
                        }
                        for pattern, count in sorted(common_errors.items(), key=lambda x: x[1], reverse=True)[:5]
                    ],
                    "systemic_issues": ["Pattern analysis performed without LLM - limited insights"],
                    "recommendations": ["Enable LLM for detailed pattern analysis", "Review most frequent error types"],
                    "confidence_score": {"score": 0.3, "explanation": "Basic pattern matching without LLM analysis"},
                    "fallback_mode": True
                }
            
            return {
                "status": "success",
                "message": f"Pattern analysis completed for {len(analyses)} workflows",
                "pattern_analysis": pattern_analysis,
                "analyzed_workflows": len(analyses),
                "total_error_logs": len(error_logs),
                "llm_used": llm_response is not None
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error in pattern analysis: {str(e)}"
            }

    async def optimize_workflow(self, workflow_id: str, workflow_dir: str, performance_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Analyze workflow for optimization opportunities"""
        try:
            yaml_path = self.find_yaml_file(workflow_dir)
            if not yaml_path:
                return {
                    "status": "error",
                    "message": f"No workflow YAML file found in {workflow_dir}"
                }
            
            workflow_data = self.load_workflow_yaml(yaml_path)
            if "error" in workflow_data:
                return {
                    "status": "error", 
                    "message": f"Error loading workflow: {workflow_data['error']}"
                }
            
            # Generate optimization prompt
            prompt = self.prompt_manager.get_workflow_optimization_prompt(workflow_data, performance_data)
            
            # Try LLM analysis
            llm_response = self._try_llm_request(prompt, use_json_format=True)
            if not llm_response:
                llm_response = self._try_llm_request(prompt, use_json_format=False)
            
            optimization_result = None
            if llm_response:
                try:
                    assistant_message = llm_response.get("choices", [])[0].get("message", {}).get("content", "")
                    start_brace = assistant_message.find('{')
                    end_brace = assistant_message.rfind('}')
                    if start_brace >= 0 and end_brace > start_brace:
                        json_text = assistant_message[start_brace:end_brace + 1]
                        optimization_result = json.loads(json_text)
                        self.logger.info(f"LLM optimization analysis successful for {workflow_id}")
                except Exception as e:
                    self.logger.error(f"Error parsing optimization analysis: {e}")
            
            # Fallback optimization analysis
            if not optimization_result:
                job_count = len(workflow_data.get("jobs", []))
                optimization_result = {
                    "optimizations": [
                        {
                            "area": "parallelization",
                            "suggestion": f"Workflow has {job_count} jobs - review dependencies for parallel execution opportunities",
                            "impact": "Potential 20-50% runtime reduction with proper parallelization",
                            "implementation": "Review job dependencies and cluster resources",
                            "priority": "medium"
                        },
                        {
                            "area": "resource",
                            "suggestion": "Review resource requirements for each job",
                            "impact": "Better resource utilization and reduced queuing time",
                            "implementation": "Analyze job requirements and adjust site configurations",
                            "priority": "medium"
                        }
                    ],
                    "overall_assessment": "Basic optimization analysis - enable LLM for detailed recommendations",
                    "confidence_score": {"score": 0.3, "explanation": "Limited analysis without LLM"},
                    "fallback_mode": True
                }
            
            return {
                "status": "success",
                "workflow_id": workflow_id,
                "optimization_analysis": optimization_result,
                "workflow_stats": {
                    "total_jobs": len(workflow_data.get("jobs", [])),
                    "total_files": len(workflow_data.get("files", [])),
                    "transformations": len(workflow_data.get("transformations", []))
                },
                "llm_used": llm_response is not None
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error in workflow optimization analysis: {str(e)}"
            }

    # All existing MCP tool methods with enhanced versions
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
            ollama_status = self.ollama_manager.quick_health_check()
            
            return {
                "status": "active",
                "agent_type": "analyzer",
                "version": "2.0.0",
                "llm_backend": "ollama",
                "ollama_url": self.ollama_manager.ollama_url,
                "ollama_api_base": self.ollama_manager.ollama_api_base,
                "ollama_model": self.ollama_manager.ollama_model,
                "ollama_available": ollama_status,
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
                        "ollama": self.ollama_manager.health_check_interval
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

    # Enhanced diagnostic tools
    async def run_ollama_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive Ollama diagnostics"""
        try:
            self.logger.info("Running comprehensive Ollama diagnostics...")
            diagnostics = self.ollama_manager.comprehensive_health_check()
            
            return {
                "status": "success",
                "message": "Ollama diagnostics completed",
                "diagnostics": diagnostics,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Diagnostics failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

    async def force_ollama_health_check(self) -> Dict[str, Any]:
        """Force a fresh health check of Ollama"""
        try:
            self.logger.info("Forcing fresh Ollama health check...")
            self.ollama_manager.last_health_check = 0  # Reset cache
            
            is_healthy = self.ollama_manager.quick_health_check()
            connection_status = self.ollama_manager.get_connection_status()
            
            return {
                "status": "success",
                "message": "Health check completed",
                "is_healthy": is_healthy,
                "connection_status": connection_status,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Health check failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

    # Configuration management
    async def update_configuration(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Update analyzer configuration"""
        try:
            old_config = self.config.copy()
            
            self.config.update(new_config)
            
            # Update Ollama manager if Ollama settings changed
            if any(key.startswith("ollama_") for key in new_config.keys()):
                self.ollama_manager = OllamaConnectionManager(self.config)
                
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            
            changes = []
            for key, new_value in new_config.items():
                if old_config.get(key) != new_value:
                    changes.append(f"{key}: {old_config.get(key)} -> {new_value}")
            
            self.logger.info(f"Configuration updated: {', '.join(changes)}")
            
            return {
                "status": "success",
                "message": "Configuration updated successfully",
                "changes": changes,
                "new_config": self.config
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
                    "ollama_url": self.ollama_manager.ollama_url,
                    "ollama_api_base": self.ollama_manager.ollama_api_base
                },
                "config_file": self.config_file
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to get configuration"
            }

    # Status checking methods  
    async def check_ollama_status(self) -> Dict[str, Any]:
        """Check current Ollama connection status"""
        is_available = self.ollama_manager.quick_health_check()
        
        return {
            "status": "success",
            "ollama_available": is_available,
            "ollama_url": self.ollama_manager.ollama_url,
            "ollama_api_base": self.ollama_manager.ollama_api_base,
            "ollama_model": self.ollama_manager.ollama_model,
            "last_check": datetime.fromtimestamp(self.ollama_manager.last_health_check).isoformat() if self.ollama_manager.last_health_check else "Never",
            "fallback_mode_enabled": self.fallback_mode,
            "check_interval_seconds": self.ollama_manager.health_check_interval
        }

    async def test_ollama_connection(self) -> Dict[str, Any]:
        """Force test Ollama connection"""
        try:
            self.ollama_manager.last_health_check = 0
            
            tags_url = f"{self.ollama_manager.ollama_api_base}/api/tags"
            response = requests.get(tags_url, timeout=self.config.get("connection_timeout", 10))
            
            if response.status_code == 200:
                models = response.json().get("models", [])
                return {
                    "status": "success",
                    "connection": "available",
                    "api_base": self.ollama_manager.ollama_api_base,
                    "models_count": len(models),
                    "models": [m.get("name", "unknown") for m in models[:5]],
                    "test_timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "status": "success",
                    "connection": "unavailable",
                    "api_base": self.ollama_manager.ollama_api_base,
                    "error": f"HTTP {response.status_code}",
                    "test_timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            return {
                "status": "success",
                "connection": "unavailable",
                "api_base": self.ollama_manager.ollama_api_base,
                "error": str(e),
                "test_timestamp": datetime.now().isoformat()
            }

    async def get_connection_status(self) -> Dict[str, Any]:
        """Get comprehensive connection status"""
        try:
            ollama_status = self.ollama_manager.quick_health_check()
            
            if ollama_status:
                overall_health = "excellent"
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
                        "url": self.ollama_manager.ollama_url,
                        "api_base": self.ollama_manager.ollama_api_base,
                        "model": self.ollama_manager.ollama_model,
                        "last_check": datetime.fromtimestamp(self.ollama_manager.last_health_check).isoformat() if self.ollama_manager.last_health_check else "Never"
                    }
                },
                "system_status": {
                    "fallback_mode_enabled": self.fallback_mode,
                    "can_operate": ollama_status or self.fallback_mode,
                    "llm_analysis_available": ollama_status
                },
                "check_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "check_timestamp": datetime.now().isoformat()
            }

    # HTTP Handler Methods
    async def handle_health(self, request):
        """Health check endpoint"""
        try:
            ollama_status = self.ollama_manager.quick_health_check()
            
            return web.json_response({
                "status": "healthy",
                "agent_type": "analyzer",
                "agent_id": "analyzer_001",
                "uptime": time.time(),
                "mcp_server": {
                    "port": self.mcp_port,
                    "status": "running"
                },
                "http_server": {
                    "port": self.http_port,
                    "status": "running"
                },
                "llm_backend": {
                    "provider": "ollama",
                    "model": self.ollama_manager.ollama_model,
                    "available": ollama_status,
                    "fallback_mode": self.fallback_mode
                },
                "analysis_stats": {
                    "total_analyses": len(self.analysis_table.all()),
                    "active_analyses": len(self.active_analyses),
                    "queue_size": len(self.analysis_queue)
                },
                "capabilities": [
                    "failure_analysis",
                    "hold_analysis", 
                    "log_analysis",
                    "error_pattern_detection",
                    "workflow_debugging",
                    "workflow_optimization"
                ],
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    async def handle_analyze_request(self, request):
        """Handle analysis request from monitor agent"""
        try:
            data = await request.json()
            workflow_id = data.get('workflow_id')
            workflow_dir = data.get('workflow_dir')
            analysis_type = data.get('analysis_type', 'failed')
            request_id = data.get('request_id', str(uuid.uuid4()))
            requester = data.get('requester', 'unknown')
            
            if not workflow_id or not workflow_dir:
                return web.json_response({
                    "error": "Missing required fields: workflow_id, workflow_dir"
                }, status=400)
            
            # Queue analysis request
            analysis_request = {
                "request_id": request_id,
                "workflow_id": workflow_id,
                "workflow_dir": workflow_dir,
                "analysis_type": analysis_type,
                "requester": requester,
                "status": "queued",
                "queued_at": datetime.now().isoformat()
            }
            
            self.analysis_queue.append(analysis_request)
            self.active_analyses[request_id] = analysis_request
            
            # Process analysis in background
            asyncio.create_task(self.process_analysis_request(analysis_request))
            
            return web.json_response({
                "success": True,
                "request_id": request_id,
                "workflow_id": workflow_id,
                "status": "queued",
                "message": "Analysis request queued successfully"
            })
            
        except Exception as e:
            self.logger.error(f"Error handling analysis request: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def process_analysis_request(self, analysis_request: Dict[str, Any]):
        """Process analysis request in background"""
        try:
            request_id = analysis_request["request_id"]
            workflow_id = analysis_request["workflow_id"]
            workflow_dir = analysis_request["workflow_dir"]
            analysis_type = analysis_request["analysis_type"]

            # Update status
            self.active_analyses[request_id]["status"] = "processing"
            self.active_analyses[request_id]["started_at"] = datetime.now().isoformat()

            self.logger.info(f"Starting analysis for workflow {workflow_id} (request: {request_id})")

            # STEP 1: Print analysis start
            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_CYAN.apply('🔄 STEP 1: STARTING WORKFLOW ANALYSIS')}")
            print(f"{'='*80}")
            print(f"{TerminalColor.YELLOW.apply('Request ID:')} {request_id}")
            print(f"{TerminalColor.YELLOW.apply('Workflow ID:')} {workflow_id}")
            print(f"{TerminalColor.YELLOW.apply('Workflow Dir:')} {workflow_dir}")
            print(f"{TerminalColor.YELLOW.apply('Analysis Type:')} {analysis_type}")
            print(f"{'='*80}\n")

            # Perform analysis
            if analysis_type == "held":
                result = await self.analyze_held_workflow(workflow_id, workflow_dir)
            else:
                result = await self.analyze_failed_workflow(workflow_id, workflow_dir)

            # Update status
            self.active_analyses[request_id]["status"] = "completed"
            self.active_analyses[request_id]["completed_at"] = datetime.now().isoformat()
            self.active_analyses[request_id]["result"] = result

            # STEP 2: Analysis completed (already printed in analyze_failed_workflow)

            # STEP 3: Notify requester via HTTP webhook
            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_MAGENTA.apply('🔄 STEP 2: NOTIFYING CONNECTED AGENTS')}")
            print(f"{'='*80}\n")

            await self.notify_analysis_complete(analysis_request, result)

            self.logger.info(f"Completed analysis for workflow {workflow_id} (request: {request_id})")

            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_GREEN.apply('✅ ANALYSIS WORKFLOW COMPLETED SUCCESSFULLY')}")
            print(f"{'='*80}\n")

        except Exception as e:
            self.logger.error(f"Error processing analysis request {request_id}: {e}")
            self.active_analyses[request_id]["status"] = "failed"
            self.active_analyses[request_id]["error"] = str(e)

            print(f"\n{'='*80}")
            print(f"{TerminalColor.RED.apply('❌ ANALYSIS WORKFLOW FAILED')}")
            print(f"{TerminalColor.RED.apply('Error:')} {str(e)}")
            print(f"{'='*80}\n")

    async def notify_analysis_complete(self, analysis_request: Dict[str, Any], result: Dict[str, Any]):
        """Notify requester that analysis is complete via HTTP webhook"""
        requester = analysis_request.get("requester")
        workflow_id = analysis_request["workflow_id"]
        workflow_dir = analysis_request["workflow_dir"]

        if requester == "monitor_agent":
            print(f"  {TerminalColor.CYAN.apply('→ Step 2.1:')} Notifying Monitor Agent")

            monitor_agents = self.agent_registry.get_agents_by_type("monitor")

            for monitor in monitor_agents:
                if monitor.get('status') == 'healthy':
                    try:
                        async with ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                            webhook_data = {
                                "request_id": analysis_request["request_id"],
                                "workflow_id": workflow_id,
                                "analysis_type": analysis_request["analysis_type"],
                                "status": "completed",
                                "result": result,
                                "completed_at": datetime.now().isoformat(),
                                "analyzer_id": "analyzer_001"
                            }

                            url = f"{monitor['http_url']}/webhooks/analysis-complete"
                            async with session.post(url, json=webhook_data) as resp:
                                if resp.status == 200:
                                    self.logger.info(f"Notified monitor of analysis completion for {workflow_id}")
                                    print(f"    {TerminalColor.GREEN.apply('✓')} Monitor webhook sent: {url}")
                                    print(f"    {TerminalColor.GREEN.apply('✓')} Response: HTTP {resp.status}")
                                else:
                                    self.logger.error(f"Failed to notify monitor: HTTP {resp.status}")
                                    print(f"    {TerminalColor.RED.apply('✗')} Monitor notification failed: HTTP {resp.status}")

                    except Exception as e:
                        self.logger.error(f"Error notifying monitor: {e}")
                        print(f"    {TerminalColor.RED.apply('✗')} Error: {e}")
                        continue

        # NOTIFY PLANNER: Send analysis to Planner for plan generation
        print(f"\n  {TerminalColor.CYAN.apply('→ Step 2.2:')} Notifying Planner Agent")
        await self.notify_planner_of_analysis(workflow_id, workflow_dir, result)

    async def notify_planner_of_analysis(self, workflow_id: str, workflow_dir: str, analysis_data: Dict[str, Any]):
        """Notify Planner agent with analysis results and catalog information"""
        try:
            planner_url = self.config.get("planner_url", "http://localhost:8082")
            webhook_url = f"{planner_url}/webhooks/analysis-complete"

            # CHECK CONNECTION: Verify Planner is reachable
            print(f"    {TerminalColor.YELLOW.apply('◆')} Checking connection to Planner...")
            try:
                async with ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    health_url = f"{planner_url}/health"
                    async with session.get(health_url) as resp:
                        if resp.status == 200:
                            health_data = await resp.json()
                            print(f"    {TerminalColor.GREEN.apply('✓')} Planner is reachable and healthy")
                            print(f"      - Status: {health_data.get('status', 'unknown')}")
                            print(f"      - Ollama: {'✓' if health_data.get('ollama_available') else '✗'}")
                        else:
                            print(f"    {TerminalColor.RED.apply('✗')} Planner health check failed: HTTP {resp.status}")
                            print(f"    {TerminalColor.YELLOW.apply('⚠')} Continuing anyway...")
            except Exception as health_error:
                print(f"    {TerminalColor.RED.apply('✗')} Cannot reach Planner at {planner_url}")
                print(f"    {TerminalColor.RED.apply('✗')} Error: {str(health_error)}")
                print(f"    {TerminalColor.YELLOW.apply('⚠')} Skipping Planner notification")
                return

            print(f"    {TerminalColor.YELLOW.apply('◆')} Discovering catalogs in workflow directory...")

            # Get catalog information from Monitor's discovery
            # The catalog info should be in the analysis_request or we need to discover it here
            from pathlib import Path
            catalogs = {}

            # Try to discover catalogs if not already in result
            if workflow_dir and Path(workflow_dir).exists():
                # Basic catalog discovery - looking for common files
                workflow_path = Path(workflow_dir)

                # Look for replica catalog
                rc_files = list(workflow_path.glob("*rc.txt")) + list(workflow_path.glob("*replicas*"))
                if rc_files:
                    catalogs["replica_catalog"] = {
                        "path": str(rc_files[0]),
                        "format": "text" if rc_files[0].suffix == ".txt" else "yaml",
                        "embedded": False
                    }
                    print(f"    {TerminalColor.GREEN.apply('✓')} Found replica catalog: {rc_files[0].name}")

                # Look for site catalog
                sc_files = list(workflow_path.glob("*sites.y*ml")) + list(workflow_path.glob("*sc.txt"))
                if sc_files:
                    catalogs["site_catalog"] = {
                        "path": str(sc_files[0]),
                        "format": "yaml" if ".y" in sc_files[0].suffix else "text",
                        "embedded": False
                    }
                    print(f"    {TerminalColor.GREEN.apply('✓')} Found site catalog: {sc_files[0].name}")

                # Look for transformation catalog
                tc_files = list(workflow_path.glob("*tc.txt")) + list(workflow_path.glob("*transformations*"))
                if tc_files:
                    catalogs["transformation_catalog"] = {
                        "path": str(tc_files[0]),
                        "format": "text" if tc_files[0].suffix == ".txt" else "yaml",
                        "embedded": False
                    }
                    print(f"    {TerminalColor.GREEN.apply('✓')} Found transformation catalog: {tc_files[0].name}")

            if not catalogs:
                print(f"    {TerminalColor.YELLOW.apply('⚠')} No catalogs found in workflow directory")

            print(f"    {TerminalColor.YELLOW.apply('◆')} Building webhook payload...")
            print(f"      - Workflow ID: {workflow_id}")
            print(f"      - Catalogs included: {len(catalogs)}")
            print(f"      - Analysis problems: {len(analysis_data.get('analysis', {}).get('problems_and_solutions', []))}")

            # Build webhook payload for Planner
            webhook_data = {
                "workflow_id": workflow_id,
                "workflow_dir": workflow_dir,
                "result": analysis_data,
                "catalogs": catalogs,
                "timestamp": datetime.now().isoformat()
            }

            print(f"    {TerminalColor.YELLOW.apply('◆')} Sending to Planner: {webhook_url}")

            # Send to Planner
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(webhook_url, json=webhook_data) as resp:
                    if resp.status == 200:
                        response_data = await resp.json()
                        self.logger.info(f"✅ Notified Planner of analysis completion for {workflow_id}")
                        print(f"    {TerminalColor.BRIGHT_GREEN.apply('✓')} Planner webhook sent successfully")
                        print(f"    {TerminalColor.GREEN.apply('✓')} Response: HTTP {resp.status}")
                        if response_data.get("plan_id"):
                            print(f"    {TerminalColor.GREEN.apply('✓')} Plan ID: {response_data.get('plan_id')}")
                            print(f"    {TerminalColor.GREEN.apply('✓')} Auto-execute: {response_data.get('auto_execute', False)}")
                    else:
                        error_text = await resp.text()
                        self.logger.error(f"Failed to notify Planner: HTTP {resp.status} - {error_text}")
                        print(f"    {TerminalColor.RED.apply('✗')} Planner notification failed: HTTP {resp.status}")
                        print(f"    {TerminalColor.RED.apply('✗')} Error: {error_text[:200]}")

        except Exception as e:
            self.logger.error(f"Error notifying Planner: {e}")
            print(f"    {TerminalColor.RED.apply('✗')} Error notifying Planner: {e}")

    async def handle_get_analysis_status(self, request):
        """Get analysis request status"""
        try:
            request_id = request.match_info['request_id']
            
            if request_id in self.active_analyses:
                return web.json_response(self.active_analyses[request_id])
            else:
                return web.json_response({"error": "Request ID not found"}, status=404)
                
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_get_analysis_results_http(self, request):
        """Get analysis results via HTTP"""
        try:
            workflow_id = request.match_info['workflow_id']
            result = await self.get_analysis_results(workflow_id)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_get_config(self, request):
        """Get current configuration"""
        try:
            result = await self.get_configuration()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_update_config(self, request):
        """Update configuration"""
        try:
            data = await request.json()
            result = await self.update_configuration(data)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_get_agents(self, request):
        """Get agent registry"""
        try:
            return web.json_response({
                "agents": list(self.agent_registry.agents.values()),
                "total_agents": len(self.agent_registry.agents),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_register_agent(self, request):
        """Register new agent"""
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

    async def handle_ollama_status(self, request):
        """Get Ollama status via HTTP"""
        try:
            result = await self.check_ollama_status()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_test_ollama(self, request):
        """Test Ollama connection via HTTP"""
        try:
            result = await self.test_ollama_connection()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # WebSocket MCP Server methods
    async def handle_client_message(self, websocket):
        """Handle incoming WebSocket messages from MCP clients"""
        self.logger.info(f"New MCP client connected: {websocket.remote_address}")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    tool_name = data.get('tool')
                    args = data.get('args', {})
                    
                    if tool_name in self.tools:
                        self.logger.info(f"Executing MCP tool: {tool_name}")
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
            self.logger.error(f"Error handling MCP client: {e}")

    async def start_servers(self):
        """Start both HTTP and WebSocket MCP servers"""
        self.logger.info(f"Starting Enhanced Analyzer Agent")
        self.logger.info(f"WebSocket MCP Server: ws://localhost:{self.mcp_port}")
        self.logger.info(f"HTTP API Server: http://localhost:{self.http_port}")

        # Check Ollama connection
        ollama_available = self.ollama_manager.quick_health_check()
        if ollama_available:
            print(f"✅ Ollama connection: OK")
        else:
            print(f"⚠ Ollama connection: Not available")
            print(f"🔄 Fallback mode: Enabled")

        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self.http_port)
        await site.start()
        self.logger.info(f"HTTP server started on http://localhost:{self.http_port}")

        # Start periodic health checks
        asyncio.create_task(self.periodic_health_checks())

        # Start WebSocket MCP server
        async with websockets.serve(self.handle_client_message, "localhost", self.mcp_port):
            self.logger.info(f"WebSocket MCP server started on ws://localhost:{self.mcp_port}")

            # Check connections to other agents
            await self.verify_agent_connections()

            # Print startup summary
            print(f"\n{TerminalColor.GREEN.apply('✓')} Enhanced Analyzer Agent Started")
            print(f"{'='*80}")
            print(f"🌐 HTTP API: http://localhost:{self.http_port}")
            print(f"🔌 MCP WebSocket: ws://localhost:{self.mcp_port}")
            print(f"📊 Known agents: {len(self.agent_registry.agents)}")
            print(f"🦙 LLM Backend: Ollama ({self.ollama_manager.ollama_model})")
            print(f"{'='*80}")
            print(f"📋 Available HTTP endpoints:")
            print(f"   GET  /health - Agent health status")
            print(f"   POST /api/analyze - Process analysis request")
            print(f"   GET  /api/analyze/{{id}}/status - Check analysis status")
            print(f"   GET  /api/config - Get configuration")
            print(f"   POST /api/config - Update configuration")
            print(f"   GET  /api/ollama/status - Ollama status")
            print(f"   POST /api/ollama/test - Test Ollama connection")
            print(f"\n📋 Available MCP tools ({len(self.tools)}):")
            for tool_name in sorted(self.tools.keys()):
                print(f"   • {tool_name}")
            print(f"\n{TerminalColor.CYAN.apply('Press Ctrl+C to stop')}")
            print(f"{'='*80}\n")

            await asyncio.Future()  # Run forever

    async def verify_agent_connections(self):
        """Verify connections to other agents at startup"""
        print(f"\n{TerminalColor.BRIGHT_CYAN.apply('🔗 VERIFYING AGENT CONNECTIONS')}")
        print(f"{'='*80}")

        # Check Planner connection
        planner_url = self.config.get("planner_url", "http://localhost:8082")
        print(f"\n{TerminalColor.CYAN.apply('→ Checking Planner Agent...')}")
        print(f"  URL: {planner_url}")
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{planner_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"  {TerminalColor.GREEN.apply('✓')} Planner: Connected")
                        print(f"  {TerminalColor.GREEN.apply('✓')} Status: {data.get('status', 'unknown')}")
                        print(f"  {TerminalColor.GREEN.apply('✓')} Ollama: {data.get('ollama_available', False)}")
                    else:
                        print(f"  {TerminalColor.RED.apply('✗')} Planner: HTTP {resp.status}")
        except Exception as e:
            print(f"  {TerminalColor.RED.apply('✗')} Planner: Not reachable")
            print(f"  {TerminalColor.YELLOW.apply('⚠')} Error: {str(e)[:60]}")
            print(f"  {TerminalColor.YELLOW.apply('⚠')} Planning features will be unavailable")

        # Check Monitor connection (if registered)
        monitor_url = self.config.get("monitor_url", "ws://localhost:8765")
        if monitor_url.startswith("ws://"):
            http_monitor_url = monitor_url.replace("ws://", "http://").replace(":8765", ":8080")
        else:
            http_monitor_url = monitor_url

        print(f"\n{TerminalColor.CYAN.apply('→ Checking Monitor Agent...')}")
        print(f"  URL: {http_monitor_url}")
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{http_monitor_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"  {TerminalColor.GREEN.apply('✓')} Monitor: Connected")
                        print(f"  {TerminalColor.GREEN.apply('✓')} Status: {data.get('status', 'unknown')}")
                        print(f"  {TerminalColor.GREEN.apply('✓')} Active workflows: {data.get('active_workflows', 0)}")
                    else:
                        print(f"  {TerminalColor.RED.apply('✗')} Monitor: HTTP {resp.status}")
        except Exception as e:
            print(f"  {TerminalColor.RED.apply('✗')} Monitor: Not reachable")
            print(f"  {TerminalColor.YELLOW.apply('⚠')} Error: {str(e)[:60]}")
            print(f"  {TerminalColor.YELLOW.apply('⚠')} Will wait for Monitor to connect")

        print(f"\n{'='*80}")

    async def periodic_health_checks(self):
        """Periodically check agent health"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Check Ollama availability
                old_status = self.ollama_manager.is_healthy
                new_status = self.ollama_manager.quick_health_check()
                
                if old_status != new_status:
                    if new_status:
                        self.logger.info("Ollama became available - switching from fallback mode")
                    else:
                        self.logger.info("Ollama became unavailable - switching to fallback mode")
                
                # Health check all known agents
                for agent_id in list(self.agent_registry.agents.keys()):
                    await self.agent_registry.health_check_agent(agent_id)
                        
            except Exception as e:
                self.logger.error(f"Error in periodic health checks: {e}")

    async def get_workflow_data_from_monitor(self, workflow_id: str) -> Dict[str, Any]:
        """Get workflow data from monitor agent via MCP"""
        monitor_agents = self.agent_registry.get_agents_by_type("monitor")
        
        if not monitor_agents:
            self.logger.warning("No monitor agents available for workflow data")
            return {}
        
        # Find a healthy monitor
        for monitor in monitor_agents:
            if await self.agent_registry.health_check_agent(monitor['agent_id']):
                try:
                    # Connect to monitor's MCP server and get workflow details
                    async with websockets.connect(monitor['mcp_url'], timeout=30) as websocket:
                        request = {
                            "tool": "get_workflow_details_for_analysis",
                            "args": {"workflow_id": workflow_id},
                            "source": "analyzer_agent"
                        }
                        
                        await websocket.send(json.dumps(request))
                        response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        data = json.loads(response)
                        
                        if data.get("status") == "success":
                            return data.get("result", {})
                        else:
                            self.logger.warning(f"Monitor returned error: {data}")
                            
                except Exception as e:
                    self.logger.error(f"Error getting workflow data from monitor: {e}")
                    continue
        
        return {}

def main():
    """Main function to run the Enhanced Analyzer Agent"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Pegasus Analyzer Agent")
    parser.add_argument("--mcp-port", type=int, default=8766, help="MCP WebSocket port")
    parser.add_argument("--http-port", type=int, default=8081, help="HTTP API port")
    parser.add_argument("--config", type=str, default="analyzer_config.json", help="Configuration file path")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    
    args = parser.parse_args()
    
    # Override log level if specified
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    agent = EnhancedAnalyzerAgent(
        mcp_port=args.mcp_port, 
        http_port=args.http_port,
        config_file=args.config
    )
    
    try:
        asyncio.run(agent.start_servers())
    except KeyboardInterrupt:
        print(f"\n{TerminalColor.YELLOW.apply('👋')} Enhanced Analyzer Agent shutting down...")
    except Exception as e:
        print(f"{TerminalColor.RED.apply('❌')} Error: {e}")

if __name__ == "__main__":
    main()
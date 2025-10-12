#!/usr/bin/env python3
"""
Simple Real-Time MAPE-K Dashboard
Monitors Monitor, Analyzer, Planner agents and displays status
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests
import json
from datetime import datetime
from typing import Dict, List, Any

app = Flask(__name__)
CORS(app)

# Configuration - Ports des agents
MONITOR_URL = "http://localhost:8080"
ANALYZER_URL = "http://localhost:8081"
PLANNER_URL = "http://localhost:8082"
DASHBOARD_PORT = 8085

class DashboardMonitor:
    """Collecte les données des agents MAPE-K"""

    def __init__(self):
        self.cache = {
            "last_update": None,
            "agents_status": {},
            "workflows": [],
            "recent_events": []
        }
        # Activity log storage (max 100 entries)
        self.activity_log = []
        self.max_activity_logs = 100

    def get_agent_status(self, agent_name: str, url: str) -> Dict[str, Any]:
        """Récupère le status d'un agent"""
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                return {
                    "name": agent_name,
                    "status": "healthy",
                    "url": url,
                    "response_time": response.elapsed.total_seconds(),
                    "last_check": datetime.now().isoformat()
                }
        except Exception as e:
            return {
                "name": agent_name,
                "status": "unhealthy",
                "url": url,
                "error": str(e),
                "last_check": datetime.now().isoformat()
            }

    def get_monitor_workflows(self) -> List[Dict]:
        """Récupère les workflows du Monitor"""
        try:
            response = requests.get(f"{MONITOR_URL}/api/workflows", timeout=2)
            if response.status_code == 200:
                data = response.json()
                # Combine active and monitored workflows
                active = data.get("active_workflows", [])
                monitored = data.get("monitored_workflows", [])

                # Format workflows with status
                workflows = []
                for wf in active:
                    workflows.append({
                        "workflow_id": wf.get("workflow_id", "Unknown"),
                        "status": "running",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })

                return workflows
        except Exception as e:
            print(f"Error getting workflows: {e}")
            return []

    def get_analyzer_stats(self) -> Dict:
        """Récupère les stats de l'Analyzer"""
        try:
            response = requests.get(f"{ANALYZER_URL}/api/stats", timeout=2)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error getting analyzer stats: {e}")
            return {"analyses_completed": 0, "active_analyses": 0}

    def get_planner_stats(self) -> Dict:
        """Récupère les stats du Planner"""
        try:
            # Get plans from /api/plans endpoint
            response = requests.get(f"{PLANNER_URL}/api/plans", timeout=2)
            if response.status_code == 200:
                data = response.json()
                plans = data.get("plans", [])
                return {
                    "plans_generated": len(plans),
                    "active_planning": 0
                }
        except:
            return {"plans_generated": 0, "active_planning": 0}

    def get_workflow_counts_from_analyzer(self) -> Dict:
        """Get workflow counts by type from Analyzer's analysis database"""
        try:
            # Try to get all analyses from Analyzer
            response = requests.get(f"{ANALYZER_URL}/api/analyses/all", timeout=2)
            if response.status_code == 200:
                data = response.json()
                analyses = data.get("analyses", [])

                # Count by analysis type
                failed_count = len([a for a in analyses if a.get("analysis_type") == "failed"])
                held_count = len([a for a in analyses if a.get("analysis_type") == "held"])

                return {
                    "failed": failed_count,
                    "held": held_count,
                    "success": 0  # Not tracked yet
                }
        except:
            pass

        # Fallback: return zeros
        return {"failed": 0, "held": 0, "success": 0}

    def add_activity_log(self, agent: str, action: str, workflow_id: str = None, status: str = "info", details: str = ""):
        """Add an activity log entry"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "action": action,
            "workflow_id": workflow_id,
            "status": status,  # info, success, warning, error
            "details": details
        }

        self.activity_log.insert(0, log_entry)  # Add at beginning

        # Keep only max_activity_logs entries
        if len(self.activity_log) > self.max_activity_logs:
            self.activity_log = self.activity_log[:self.max_activity_logs]

    def get_recent_activities(self, limit: int = 50) -> List[Dict]:
        """Get recent activity logs"""
        return self.activity_log[:limit]

    def poll_agent_activities(self):
        """Poll agents for recent activities and update activity log"""
        # This will be called periodically to fetch logs from agents

        # Check Monitor for new workflows
        try:
            response = requests.get(f"{MONITOR_URL}/api/workflows", timeout=1)
            if response.status_code == 200:
                data = response.json()
                active_workflows = data.get("active_workflows", [])

                # Log new workflows being monitored (simple check)
                for wf in active_workflows[:3]:  # Just the first 3
                    workflow_id = wf.get("workflow_id")
                    if workflow_id and not any(log.get("workflow_id") == workflow_id and log.get("action") == "Monitoring workflow" for log in self.activity_log[:10]):
                        self.add_activity_log(
                            agent="Monitor",
                            action="Monitoring workflow",
                            workflow_id=workflow_id,
                            status="info",
                            details=f"Started monitoring at {wf.get('monitoring_started', 'N/A')}"
                        )
        except:
            pass

        # Check Analyzer for recent analyses
        try:
            response = requests.get(f"{ANALYZER_URL}/api/analyses/all", timeout=1)
            if response.status_code == 200:
                data = response.json()
                analyses = data.get("analyses", [])

                # Log recent analyses (check if not already logged)
                for analysis in analyses[:5]:  # Just the first 5
                    workflow_id = analysis.get("workflow_id")
                    analysis_type = analysis.get("analysis_type")

                    if workflow_id and not any(log.get("workflow_id") == workflow_id and "Analysis" in log.get("action", "") for log in self.activity_log[:10]):
                        self.add_activity_log(
                            agent="Analyzer",
                            action=f"Analysis completed ({analysis_type})",
                            workflow_id=workflow_id,
                            status="warning" if analysis_type == "failed" else "info",
                            details=f"Analyzed workflow for {analysis_type} state"
                        )
        except:
            pass

        # Check Planner for plans
        try:
            response = requests.get(f"{PLANNER_URL}/api/plans", timeout=1)
            if response.status_code == 200:
                data = response.json()
                plans = data.get("plans", [])

                # Log recent plans
                for plan in plans[:3]:
                    workflow_id = plan.get("workflow_id")

                    if workflow_id and not any(log.get("workflow_id") == workflow_id and "Repair plan" in log.get("action", "") for log in self.activity_log[:10]):
                        self.add_activity_log(
                            agent="Planner",
                            action="Repair plan generated",
                            workflow_id=workflow_id,
                            status="success",
                            details=f"Generated repair plan: {plan.get('description', 'N/A')}"
                        )
        except:
            pass

    def collect_all_data(self) -> Dict[str, Any]:
        """Collecte toutes les données des agents"""

        # Poll for new activities
        self.poll_agent_activities()

        # Status des agents
        agents_status = {
            "monitor": self.get_agent_status("Monitor", MONITOR_URL),
            "analyzer": self.get_agent_status("Analyzer", ANALYZER_URL),
            "planner": self.get_agent_status("Planner", PLANNER_URL)
        }

        # Workflows actifs
        workflows = self.get_monitor_workflows()

        # Stats
        analyzer_stats = self.get_analyzer_stats()
        planner_stats = self.get_planner_stats()

        # Get detailed workflow counts from Analyzer database
        workflow_counts = self.get_workflow_counts_from_analyzer()
        workflow_counts["running"] = len(workflows)  # Add running count from Monitor

        return {
            "timestamp": datetime.now().isoformat(),
            "agents_status": agents_status,
            "workflows": workflows[:10],  # Derniers 10
            "workflow_counts": workflow_counts,
            "analyzer_stats": analyzer_stats,
            "planner_stats": planner_stats,
            "system_healthy": all(
                agent["status"] == "healthy"
                for agent in agents_status.values()
            )
        }

# Instance globale
dashboard = DashboardMonitor()

@app.route('/')
def index():
    """Page principale du dashboard"""
    return render_template('dashboard.html')

@app.route('/workflow/<workflow_id>')
def workflow_analysis(workflow_id):
    """Page d'analyse détaillée d'un workflow"""
    return render_template('workflow_details.html')

@app.route('/api/data')
def get_data():
    """API pour récupérer toutes les données"""
    data = dashboard.collect_all_data()
    return jsonify(data)

@app.route('/api/agents')
def get_agents():
    """API pour récupérer uniquement le status des agents"""
    data = dashboard.collect_all_data()
    return jsonify(data["agents_status"])

@app.route('/api/workflows')
def get_workflows():
    """API pour récupérer les workflows"""
    data = dashboard.collect_all_data()
    return jsonify({
        "workflows": data["workflows"],
        "counts": data["workflow_counts"]
    })

@app.route('/api/workflows/detailed')
def get_workflows_detailed():
    """API pour récupérer les workflows avec informations détaillées de monitoring"""
    try:
        # Check if we should include historical workflows
        include_historical = request.args.get('include_historical', 'true').lower() == 'true'

        # Get all workflows from Monitor (including historical)
        response = requests.get(f"{MONITOR_URL}/api/workflows/all", timeout=3)

        if response.status_code != 200:
            return jsonify({"error": "Could not fetch workflows from Monitor"}), 500

        monitor_data = response.json()
        all_workflows = monitor_data.get("workflows", [])

        # Filter out historical workflows if requested
        if not include_historical:
            all_workflows = [wf for wf in all_workflows if not wf.get('is_historical', False)]

        # Combine and enrich workflow data
        detailed_workflows = []

        for wf in all_workflows:
            workflow_id = wf.get("workflow_id", "Unknown")

            # Try to get detailed status
            workflow_info = {
                "workflow_id": workflow_id,
                "status": "completed" if wf.get("state") in ["Success", "Failure", "Failed"] else "monitoring",
                "iwd": wf.get("iwd", "N/A"),
                "first_seen": wf.get("first_seen"),
                "last_checked": wf.get("last_checked"),
                "state": wf.get("state", "unknown"),
                "percent_done": wf.get("percent_done", 0),
                "is_active": wf.get("is_active", False),
                "metadata_collected": wf.get("metadata_collected", False),
                "metadata": {},
                "pipeline_step": wf.get("pipeline_step", "monitoring"),
                "current_agent": wf.get("current_agent", {
                    "id": "monitor_001",
                    "name": "Monitor",
                    "type": "monitor"
                }),
                "step_history": wf.get("step_history", []),
                "is_historical": wf.get("is_historical", False),
                "run_number": wf.get("run_number", 1),
                "original_workflow_id": wf.get("original_workflow_id"),
                "superseded_at": wf.get("superseded_at"),
                "analysis_status": wf.get("analysis_status", "no_analysis"),
                "analysis_completed_at": wf.get("analysis_completed_at"),
                "analysis_summary": wf.get("analysis_summary", {})
            }

            # Try to get more details from Monitor
            try:
                detail_response = requests.get(
                    f"{MONITOR_URL}/api/workflows/{workflow_id}/status",
                    timeout=1
                )
                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    workflow_info.update({
                        "state": detail_data.get("state", "unknown"),
                        "metadata": detail_data.get("metadata", {})
                    })
            except:
                pass

            # Try to get analysis status from Analyzer
            try:
                analysis_response = requests.get(
                    f"{ANALYZER_URL}/api/analysis/{workflow_id}/results",
                    timeout=1
                )
                if analysis_response.status_code == 200:
                    analysis_data = analysis_response.json()
                    workflow_info["analysis_status"] = analysis_data.get("status", "no_analysis")
                    workflow_info["problems_count"] = len(
                        analysis_data.get("analysis", {}).get("problems_and_solutions", [])
                    )
                else:
                    workflow_info["analysis_status"] = "no_analysis"
                    workflow_info["problems_count"] = 0
            except:
                workflow_info["analysis_status"] = "no_analysis"
                workflow_info["problems_count"] = 0

            # Try to get plans from Planner
            try:
                plans_response = requests.get(f"{PLANNER_URL}/api/plans", timeout=1)
                if plans_response.status_code == 200:
                    plans_data = plans_response.json()
                    all_plans = plans_data.get("plans", [])
                    workflow_plans = [p for p in all_plans if p.get("workflow_id") == workflow_id]
                    workflow_info["plans_count"] = len(workflow_plans)
                else:
                    workflow_info["plans_count"] = 0
            except:
                workflow_info["plans_count"] = 0

            detailed_workflows.append(workflow_info)

        return jsonify({
            "workflows": detailed_workflows,
            "total": len(detailed_workflows),
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/activities')
def get_activities():
    """API pour récupérer les activités récentes du système MAPE-K"""
    try:
        limit = request.args.get('limit', 50, type=int)
        activities = dashboard.get_recent_activities(limit)

        return jsonify({
            "activities": activities,
            "total": len(activities),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/workflow/<workflow_id>/details')
def get_workflow_details(workflow_id):
    """API pour récupérer les détails d'un workflow spécifique (modal)"""
    try:
        details = {}

        # Get workflow status from Monitor
        try:
            response = requests.get(f"{MONITOR_URL}/api/workflows/{workflow_id}/status", timeout=2)
            if response.status_code == 200:
                details["monitor_data"] = response.json()
        except:
            details["monitor_data"] = {"error": "Could not fetch from Monitor"}

        # Get analysis results from Analyzer
        try:
            response = requests.get(f"{ANALYZER_URL}/api/analysis/{workflow_id}/results", timeout=2)
            if response.status_code == 200:
                details["analysis_data"] = response.json()
        except:
            details["analysis_data"] = {"error": "No analysis found"}

        # Get plans from Planner
        try:
            response = requests.get(f"{PLANNER_URL}/api/plans", timeout=2)
            if response.status_code == 200:
                all_plans = response.json().get("plans", [])
                # Filter plans for this workflow
                workflow_plans = [p for p in all_plans if p.get("workflow_id") == workflow_id]
                details["plans"] = workflow_plans
        except:
            details["plans"] = []

        details["workflow_id"] = workflow_id
        details["timestamp"] = datetime.now().isoformat()

        return jsonify(details)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/workflow/<workflow_id>/analysis')
def get_workflow_analysis(workflow_id):
    """API complète pour la page d'analyse d'un workflow"""
    try:
        result = {
            "workflow_id": workflow_id,
            "monitor": {},
            "analyzer": {},
            "planner": {},
            "timestamp": datetime.now().isoformat()
        }

        # Get Monitor data (metadata, status)
        try:
            # Try to get workflow metadata from Monitor
            response = requests.get(f"{MONITOR_URL}/api/workflows/{workflow_id}/status", timeout=2)
            if response.status_code == 200:
                monitor_data = response.json()
                result["monitor"] = {
                    "status": "success",
                    "metadata": monitor_data.get("metadata", {}),
                    "state": monitor_data.get("state", "unknown"),
                    "workflow_dir": monitor_data.get("workflow_dir", "N/A")
                }
            else:
                result["monitor"] = {"error": "Monitor data not available"}
        except Exception as e:
            result["monitor"] = {"error": f"Could not connect to Monitor: {str(e)}"}

        # Get Analyzer data (analysis results, problems)
        try:
            response = requests.get(f"{ANALYZER_URL}/api/analysis/{workflow_id}/results", timeout=2)
            if response.status_code == 200:
                analyzer_data = response.json()
                analysis = analyzer_data.get("analysis", {})
                result["analyzer"] = {
                    "status": "success",
                    "problems": analysis.get("problems_and_solutions", []),
                    "analysis_status": analyzer_data.get("status", "completed"),
                    "logs": analyzer_data.get("pegasus_analyzer_output", "")
                }
            else:
                result["analyzer"] = {"error": "Analysis not found"}
        except Exception as e:
            result["analyzer"] = {"error": f"Could not connect to Analyzer: {str(e)}"}

        # Get Planner data (repair plans)
        try:
            response = requests.get(f"{PLANNER_URL}/api/plans", timeout=2)
            if response.status_code == 200:
                planner_data = response.json()
                all_plans = planner_data.get("plans", [])

                # Filter plans for this workflow
                workflow_plans = [p for p in all_plans if p.get("workflow_id") == workflow_id]

                result["planner"] = {
                    "status": "success",
                    "plans": workflow_plans,
                    "total_plans": len(workflow_plans)
                }
            else:
                result["planner"] = {"error": "Plans not available"}
        except Exception as e:
            result["planner"] = {"error": f"Could not connect to Planner: {str(e)}"}

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/network/topology')
def get_network_topology():
    """API to get agent network topology for visualization"""
    try:
        nodes = []
        edges = []

        # Check each agent status
        monitor_status = dashboard.get_agent_status("Monitor", MONITOR_URL)
        analyzer_status = dashboard.get_agent_status("Analyzer", ANALYZER_URL)
        planner_status = dashboard.get_agent_status("Planner", PLANNER_URL)

        # Get workflow counts
        try:
            workflows_response = requests.get(f"{MONITOR_URL}/api/workflows/all", timeout=2)
            workflows_count = len(workflows_response.json().get("workflows", [])) if workflows_response.status_code == 200 else 0
            active_count = len([w for w in workflows_response.json().get("workflows", []) if w.get("is_active")]) if workflows_response.status_code == 200 else 0
        except:
            workflows_count = 0
            active_count = 0

        # Get analysis counts and check for recent activity
        analyses_count = 0
        recent_analyses = 0
        has_active_problems = False
        try:
            analyses_response = requests.get(f"{ANALYZER_URL}/api/analyses/all", timeout=2)
            if analyses_response.status_code == 200:
                analyses = analyses_response.json().get("analyses", [])
                analyses_count = len(analyses)

                # Check for recent analyses (last 5 minutes)
                from datetime import datetime, timedelta
                five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
                recent_analyses = len([a for a in analyses if a.get("timestamp", "") > five_min_ago])
                has_active_problems = recent_analyses > 0
        except:
            analyses_count = 0
            recent_analyses = 0

        # Get plan counts
        try:
            plans_response = requests.get(f"{PLANNER_URL}/api/plans", timeout=2)
            plans_count = len(plans_response.json().get("plans", [])) if plans_response.status_code == 200 else 0
        except:
            plans_count = 0

        # Check LLM connection (from Analyzer)
        llm_status = "unknown"
        llm_model = "N/A"
        try:
            # Try to get Analyzer config or health endpoint that includes LLM status
            analyzer_health = requests.get(f"{ANALYZER_URL}/health", timeout=2)
            if analyzer_health.status_code == 200:
                llm_status = "connected"
                llm_model = "llama3:latest"
        except:
            llm_status = "disconnected"

        # Create AGENT nodes with detailed info
        nodes.append({
            "id": "monitor",
            "label": "MONITOR",
            "group": "agent",
            "status": monitor_status.get("status", "unknown"),
            "type": "monitor",
            "level": 1,
            "value": 30,
            "icon": "fa-radar",
            "title": f"<b>Monitor Agent</b><br/><br/><i class='fas fa-circle' style='color: {'#10b981' if monitor_status.get('status') == 'healthy' else '#ef4444'}'></i> Status: {monitor_status.get('status', 'unknown')}<br/><i class='fas fa-clock'></i> Response: {monitor_status.get('response_time', 0):.3f}s<br/><i class='fas fa-network-wired'></i> Port: 8080<br/><br/><i class='fas fa-chart-line'></i> Tracking: {workflows_count} workflows<br/><i class='fas fa-running'></i> Active: {active_count} workflows",
            "metrics": {
                "workflows": workflows_count,
                "active": active_count,
                "response_time": monitor_status.get('response_time', 0)
            }
        })

        # Determine analyzer operational state
        analyzer_operational_state = "idle"
        if analyzer_status.get("status") != "healthy":
            analyzer_operational_state = "offline"
        elif has_active_problems:
            analyzer_operational_state = "analyzing"

        nodes.append({
            "id": "analyzer",
            "label": "ANALYZER",
            "group": "agent",
            "status": analyzer_status.get("status", "unknown"),
            "operational_state": analyzer_operational_state,
            "type": "analyzer",
            "level": 2,
            "value": 30,
            "icon": "fa-microscope",
            "title": f"<b>Analyzer Agent</b><br/><br/><i class='fas fa-circle' style='color: {'#10b981' if analyzer_status.get('status') == 'healthy' else '#ef4444'}'></i> Status: {analyzer_status.get('status', 'unknown')}<br/><i class='fas fa-clock'></i> Response: {analyzer_status.get('response_time', 0):.3f}s<br/><i class='fas fa-network-wired'></i> Port: 8081<br/><br/><i class='fas fa-info-circle'></i> State: <b>{analyzer_operational_state.upper()}</b><br/><i class='fas fa-tasks'></i> Total Analyses: {analyses_count}<br/><i class='fas fa-fire'></i> Recent (5m): {recent_analyses}<br/><i class='fas fa-robot'></i> LLM: {llm_status}<br/><i class='fas fa-brain'></i> Model: {llm_model}",
            "metrics": {
                "analyses": analyses_count,
                "recent_analyses": recent_analyses,
                "has_active_problems": has_active_problems,
                "response_time": analyzer_status.get('response_time', 0),
                "llm_connected": llm_status == "connected"
            }
        })

        nodes.append({
            "id": "planner",
            "label": "PLANNER",
            "group": "agent",
            "status": planner_status.get("status", "unknown"),
            "type": "planner",
            "level": 3,
            "value": 30,
            "icon": "fa-project-diagram",
            "title": f"<b>Planner Agent</b><br/><br/><i class='fas fa-circle' style='color: {'#10b981' if planner_status.get('status') == 'healthy' else '#ef4444'}'></i> Status: {planner_status.get('status', 'unknown')}<br/><i class='fas fa-clock'></i> Response: {planner_status.get('response_time', 0):.3f}s<br/><i class='fas fa-network-wired'></i> Port: 8082<br/><br/><i class='fas fa-clipboard-check'></i> Total Plans: {plans_count}",
            "metrics": {
                "plans": plans_count,
                "response_time": planner_status.get('response_time', 0)
            }
        })

        # SYSTEM nodes
        nodes.append({
            "id": "workflows",
            "label": "PEGASUS\nWORKFLOWS",
            "group": "system",
            "status": "active" if active_count > 0 else "idle",
            "type": "workflows",
            "level": 0,
            "value": 40,
            "icon": "fa-cogs",
            "title": f"<b>Pegasus Workflow System</b><br/><br/><i class='fas fa-tasks'></i> Total Workflows: {workflows_count}<br/><i class='fas fa-running'></i> Active: {active_count}<br/><i class='fas fa-check-circle'></i> Completed: {workflows_count - active_count}"
        })

        # DATABASE nodes
        nodes.append({
            "id": "monitor_db",
            "label": "MONITOR\nDATABASE",
            "group": "database",
            "status": "healthy" if monitor_status.get("status") == "healthy" else "unknown",
            "type": "database",
            "level": 1,
            "value": 20,
            "icon": "fa-database",
            "title": f"<b>Monitor Database</b><br/><br/><i class='fas fa-hdd'></i> Type: TinyDB (JSON)<br/><i class='fas fa-file-code'></i> File: workflows.json<br/><i class='fas fa-table'></i> Records: {workflows_count}"
        })

        nodes.append({
            "id": "analyzer_db",
            "label": "ANALYZER\nDATABASE",
            "group": "database",
            "status": "healthy" if analyzer_status.get("status") == "healthy" else "unknown",
            "type": "database",
            "level": 2,
            "value": 20,
            "icon": "fa-database",
            "title": f"<b>Analyzer Database</b><br/><br/><i class='fas fa-hdd'></i> Type: TinyDB (JSON)<br/><i class='fas fa-file-code'></i> File: analysis.json<br/><i class='fas fa-table'></i> Records: {analyses_count}"
        })

        nodes.append({
            "id": "planner_db",
            "label": "PLANNER\nDATABASE",
            "group": "database",
            "status": "healthy" if planner_status.get("status") == "healthy" else "unknown",
            "type": "database",
            "level": 3,
            "value": 20,
            "icon": "fa-database",
            "title": f"<b>Planner Database</b><br/><br/><i class='fas fa-hdd'></i> Type: TinyDB (JSON)<br/><i class='fas fa-file-code'></i> File: plans.json<br/><i class='fas fa-table'></i> Records: {plans_count}"
        })

        # LLM node
        nodes.append({
            "id": "llm",
            "label": "OLLAMA\nLLM",
            "group": "external",
            "status": llm_status,
            "type": "llm",
            "level": 2,
            "value": 35,
            "icon": "fa-brain",
            "title": f"<b>Large Language Model</b><br/><br/><i class='fas fa-server'></i> Service: Ollama<br/><i class='fas fa-brain'></i> Model: {llm_model}<br/><i class='fas fa-circle' style='color: {'#10b981' if llm_status == 'connected' else '#ef4444'}'></i> Status: {llm_status}<br/><br/><b>Capabilities:</b><br/>• Root cause analysis<br/>• Problem detection<br/>• Solution suggestions"
        })

        # DASHBOARD node
        nodes.append({
            "id": "dashboard",
            "label": "DASHBOARD",
            "group": "ui",
            "status": "healthy",
            "type": "dashboard",
            "level": 2,
            "value": 25,
            "icon": "fa-chart-line",
            "title": "<b>Dashboard Interface</b><br/><br/><i class='fas fa-network-wired'></i> Port: 8085<br/><i class='fas fa-th-large'></i> Views: Dashboard, Workflows, Agents, Analytics<br/><br/><b>Features:</b><br/>• Real-time monitoring<br/>• Network visualization<br/>• Analytics charts"
        })

        # Create edges with detailed metadata
        # Workflow System connections
        edges.append({
            "from": "workflows",
            "to": "monitor",
            "label": f"DETECT • {active_count} active",
            "arrows": "to",
            "width": 3,
            "color": {"color": "#10b981" if monitor_status.get("status") == "healthy" else "#ef4444"},
            "title": "<b>Workflow Detection</b><br/><br/><i class='fas fa-sync'></i> Monitor polls Pegasus workflows<br/><i class='fas fa-bell'></i> Detects state changes<br/><i class='fas fa-clock'></i> Interval: 30s"
        })

        # Monitor connections
        edges.append({
            "from": "monitor",
            "to": "monitor_db",
            "label": "STORE",
            "arrows": "to",
            "width": 2,
            "color": {"color": "#64748b"},
            "title": "<b>Data Persistence</b><br/><br/><i class='fas fa-save'></i> Stores workflow metadata<br/><i class='fas fa-database'></i> State information<br/><i class='fas fa-history'></i> Historical tracking"
        })

        # Monitor to Analyzer edge - show state
        trigger_label = f"TRIGGER • {analyses_count} total"
        trigger_color = "#6366f1"
        if has_active_problems:
            trigger_label = f"ANALYZING • {recent_analyses} active"
            trigger_color = "#f59e0b"
        elif analyses_count == 0:
            trigger_label = "MONITORING • No issues"
            trigger_color = "#10b981"

        edges.append({
            "from": "monitor",
            "to": "analyzer",
            "label": trigger_label,
            "arrows": "to",
            "width": 3 if has_active_problems else 2,
            "color": {"color": trigger_color},
            "title": f"<b>Analysis Request</b><br/><br/><i class='fas fa-info-circle'></i> State: {'ACTIVE ANALYSIS' if has_active_problems else 'IDLE MONITORING'}<br/><i class='fas fa-paper-plane'></i> Total requests: {analyses_count}<br/><i class='fas fa-fire'></i> Recent (5m): {recent_analyses}<br/><i class='fas fa-bolt'></i> Event-driven"
        })

        # Analyzer connections
        edges.append({
            "from": "analyzer",
            "to": "monitor",
            "label": "FILE REQUEST",
            "arrows": "to",
            "width": 2,
            "dashes": True,
            "color": {"color": "#94a3b8"},
            "title": "<b>File Retrieval</b><br/><br/><i class='fas fa-download'></i> Pull-based architecture<br/><i class='fas fa-file-alt'></i> Requests logs & configs<br/><i class='fas fa-shield-alt'></i> On-demand access"
        })

        edges.append({
            "from": "analyzer",
            "to": "llm",
            "label": "AI QUERY",
            "arrows": "to",
            "width": 3,
            "color": {"color": "#ec4899"},
            "title": "<b>LLM Integration</b><br/><br/><i class='fas fa-brain'></i> Sends logs for AI analysis<br/><i class='fas fa-search'></i> Gets root cause insights<br/><i class='fas fa-lightbulb'></i> Solution suggestions"
        })

        edges.append({
            "from": "analyzer",
            "to": "analyzer_db",
            "label": "PERSIST",
            "arrows": "to",
            "width": 2,
            "color": {"color": "#64748b"},
            "title": "<b>Analysis Storage</b><br/><br/><i class='fas fa-save'></i> Stores analysis results<br/><i class='fas fa-bug'></i> Detected problems<br/><i class='fas fa-chart-bar'></i> Metrics & logs"
        })

        # Analyzer to Planner edge - show if problems exist
        planner_label = f"REPORT • {analyses_count} issues" if analyses_count > 0 else "NO ISSUES"
        planner_color = "#f59e0b" if analyses_count > 0 else "#94a3b8"
        planner_width = 3 if has_active_problems else 1
        planner_dashes = analyses_count == 0

        edges.append({
            "from": "analyzer",
            "to": "planner",
            "label": planner_label,
            "arrows": "to",
            "width": planner_width,
            "dashes": planner_dashes,
            "color": {"color": planner_color},
            "title": f"<b>Problem Report</b><br/><br/><i class='fas fa-info-circle'></i> Status: {'PROBLEMS DETECTED' if analyses_count > 0 else 'NO PROBLEMS'}<br/><i class='fas fa-clipboard-list'></i> Total reports: {analyses_count}<br/><i class='fas fa-fire'></i> Recent: {recent_analyses}<br/><i class='fas fa-tools'></i> {'Solutions provided' if analyses_count > 0 else 'System healthy'}"
        })

        # Planner connections
        edges.append({
            "from": "planner",
            "to": "planner_db",
            "label": "STORE PLANS",
            "arrows": "to",
            "width": 2,
            "color": {"color": "#64748b"},
            "title": "<b>Plan Storage</b><br/><br/><i class='fas fa-save'></i> Stores repair plans<br/><i class='fas fa-history'></i> Execution history<br/><i class='fas fa-check'></i> Approval tracking"
        })

        edges.append({
            "from": "planner",
            "to": "workflows",
            "label": "EXECUTE",
            "arrows": "to",
            "width": 2,
            "dashes": True,
            "color": {"color": "#8b5cf6"},
            "title": "<b>Plan Execution</b><br/><br/><i class='fas fa-play-circle'></i> Executes repair plans<br/><i class='fas fa-wrench'></i> Auto-repair (future)<br/><i class='fas fa-redo'></i> Workflow remediation"
        })

        # Dashboard connections (queries)
        for agent_id in ["monitor", "analyzer", "planner"]:
            edges.append({
                "from": "dashboard",
                "to": agent_id,
                "label": "HTTP/REST",
                "arrows": "to",
                "width": 1,
                "dashes": True,
                "color": {"color": "#3b82f6"},
                "title": f"<b>Status Polling</b><br/><br/><i class='fas fa-sync-alt'></i> Polls {agent_id.upper()}<br/><i class='fas fa-clock'></i> Interval: 5s<br/><i class='fas fa-network-wired'></i> REST API"
            })

        return jsonify({
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_agents": 3,
                "healthy_agents": sum(1 for s in [monitor_status, analyzer_status, planner_status] if s.get("status") == "healthy"),
                "total_workflows": workflows_count,
                "active_workflows": active_count,
                "total_analyses": analyses_count,
                "recent_analyses": recent_analyses,
                "has_active_problems": has_active_problems,
                "analyzer_state": analyzer_operational_state,
                "total_plans": plans_count,
                "llm_status": llm_status
            },
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/charts/workflow-states')
def get_workflow_states_chart():
    """API to get workflow state distribution for pie chart"""
    try:
        # Get all workflows
        response = requests.get(f"{MONITOR_URL}/api/workflows/all", timeout=3)
        if response.status_code != 200:
            return jsonify({"error": "Could not fetch workflows"}), 500

        workflows = response.json().get("workflows", [])

        # Count by state
        state_counts = {}
        for wf in workflows:
            state = wf.get("state", "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1

        # Format for chart
        labels = list(state_counts.keys())
        data = list(state_counts.values())

        return jsonify({
            "labels": labels,
            "data": data,
            "total": len(workflows),
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/charts/problem-distribution')
def get_problem_distribution_chart():
    """API to get problem category distribution for bar chart"""
    try:
        # Get all analyses from Analyzer
        response = requests.get(f"{ANALYZER_URL}/api/analyses/all", timeout=3)
        if response.status_code != 200:
            return jsonify({"error": "Could not fetch analyses"}), 500

        analyses = response.json().get("analyses", [])

        # Count problem categories
        category_counts = {}
        for analysis in analyses:
            analysis_type = analysis.get("analysis_type", "unknown")
            category_counts[analysis_type] = category_counts.get(analysis_type, 0) + 1

        # Format for chart
        labels = list(category_counts.keys())
        data = list(category_counts.values())

        return jsonify({
            "labels": labels,
            "data": data,
            "total": len(analyses),
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/charts/agent-activity')
def get_agent_activity_chart():
    """API to get recent agent activity for timeline chart"""
    try:
        activities = dashboard.get_recent_activities(50)

        # Group by agent and count
        agent_counts = {"Monitor": 0, "Analyzer": 0, "Planner": 0}
        for activity in activities:
            agent = activity.get("agent", "Unknown")
            if agent in agent_counts:
                agent_counts[agent] += 1

        return jsonify({
            "labels": list(agent_counts.keys()),
            "data": list(agent_counts.values()),
            "total_activities": len(activities),
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     🎯 MAPE-K DASHBOARD SERVER                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Dashboard URL: http://localhost:{DASHBOARD_PORT}                                      ║
║  API Endpoint:  http://localhost:{DASHBOARD_PORT}/api/data                             ║
║                                                                              ║
║  Monitoring:                                                                 ║
║    • Monitor:  {MONITOR_URL}                                        ║
║    • Analyzer: {ANALYZER_URL}                                        ║
║    • Planner:  {PLANNER_URL}                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)

    app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=True)

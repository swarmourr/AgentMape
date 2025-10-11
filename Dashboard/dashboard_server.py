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
        # Get all workflows from Monitor (including historical)
        response = requests.get(f"{MONITOR_URL}/api/workflows/all", timeout=3)

        if response.status_code != 200:
            return jsonify({"error": "Could not fetch workflows from Monitor"}), 500

        monitor_data = response.json()
        all_workflows = monitor_data.get("workflows", [])

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
                "metadata": {}
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

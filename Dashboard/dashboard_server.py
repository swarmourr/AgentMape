#!/usr/bin/env python3
"""
Simple Real-Time MAPE-K Dashboard
Monitors Monitor, Analyzer, Planner agents and displays status
"""

from flask import Flask, render_template, jsonify
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
            # Try to get analysis status (doesn't have /api/stats endpoint)
            # Return default values for now
            return {"analyses_completed": "N/A", "active_analyses": 0}
        except:
            return {"analyses_completed": "N/A", "active_analyses": 0}

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

    def collect_all_data(self) -> Dict[str, Any]:
        """Collecte toutes les données des agents"""

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

        # Compter les workflows par statut
        # Note: Le Monitor ne retourne pas les statuts détaillés pour l'instant
        # On affiche juste le nombre de workflows actifs
        workflow_counts = {
            "running": len(workflows),
            "failed": 0,  # Ces données viendraient de l'Analyzer
            "held": 0,    # Ces données viendraient de l'Analyzer
            "success": 0  # À implémenter
        }

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

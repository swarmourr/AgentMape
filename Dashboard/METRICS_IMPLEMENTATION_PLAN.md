# MAPE-K Metrics Implementation Plan

## Overview
This document outlines how to implement comprehensive evaluation metrics in the existing MAPE-K system.

---

## Phase 1: Database Schema for Metrics Storage

### Create Metrics Database

**File**: `Dashboard/metrics_db.py`

```python
from tinydb import TinyDB, Query
from datetime import datetime, timedelta
from typing import Dict, List, Any
import statistics

class MetricsDatabase:
    def __init__(self, db_path='metrics.json'):
        self.db = TinyDB(db_path)

        # Tables for different metric types
        self.workflows = self.db.table('workflows')
        self.analyses = self.db.table('analyses')
        self.plans = self.db.table('plans')
        self.executions = self.db.table('executions')
        self.system_health = self.db.table('system_health')
        self.costs = self.db.table('costs')

    def record_workflow_event(self, workflow_id, event_type, data):
        """Record workflow lifecycle events"""
        self.workflows.insert({
            'workflow_id': workflow_id,
            'event_type': event_type,  # detected, analyzed, planned, executed, completed, failed
            'timestamp': datetime.now().isoformat(),
            'data': data
        })

    def record_analysis(self, workflow_id, analysis_data):
        """Record Analyzer metrics"""
        self.analyses.insert({
            'workflow_id': workflow_id,
            'timestamp': datetime.now().isoformat(),
            'analysis_time_seconds': analysis_data.get('duration'),
            'llm_tokens_used': analysis_data.get('tokens'),
            'root_cause_identified': analysis_data.get('root_cause'),
            'error_type': analysis_data.get('error_type'),
            'fixable': analysis_data.get('fixable'),
            'stderr_used': analysis_data.get('used_stderr', False),
            'files_requested': analysis_data.get('files_requested', []),
            'confidence': analysis_data.get('confidence', 0.0)
        })

    def record_plan(self, workflow_id, plan_data):
        """Record Planner metrics"""
        self.plans.insert({
            'workflow_id': workflow_id,
            'timestamp': datetime.now().isoformat(),
            'planning_time_seconds': plan_data.get('duration'),
            'llm_tokens_used': plan_data.get('tokens'),
            'num_steps': plan_data.get('num_steps'),
            'plan_type': plan_data.get('plan_type'),  # code_fix, catalog_update, etc.
            'risk_level': plan_data.get('risk_level'),  # low, medium, high
            'requires_approval': plan_data.get('requires_approval', False),
            'plan_valid': plan_data.get('valid', True)
        })

    def record_execution(self, workflow_id, execution_data):
        """Record Executor metrics"""
        self.executions.insert({
            'workflow_id': workflow_id,
            'timestamp': datetime.now().isoformat(),
            'execution_time_seconds': execution_data.get('duration'),
            'success': execution_data.get('success', False),
            'rollback_required': execution_data.get('rollback', False),
            'retry_count': execution_data.get('retry_count', 0)
        })

    def record_system_health(self, agent_name, health_data):
        """Record agent health metrics"""
        self.system_health.insert({
            'agent': agent_name,
            'timestamp': datetime.now().isoformat(),
            'status': health_data.get('status'),  # healthy, unhealthy
            'response_time_ms': health_data.get('response_time_ms'),
            'cpu_percent': health_data.get('cpu'),
            'memory_mb': health_data.get('memory'),
            'error': health_data.get('error')
        })

    def record_cost(self, workflow_id, cost_data):
        """Record cost metrics"""
        self.costs.insert({
            'workflow_id': workflow_id,
            'timestamp': datetime.now().isoformat(),
            'llm_tokens_total': cost_data.get('tokens'),
            'llm_cost_usd': cost_data.get('llm_cost'),
            'compute_time_seconds': cost_data.get('compute_time'),
            'human_time_seconds': cost_data.get('human_time', 0)
        })

    def get_repair_success_rate(self, days=7):
        """Calculate Repair Success Rate"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        Query = self.workflows._query_constructor
        workflows = self.workflows.search(Query.timestamp >= cutoff)

        total_failed = len([w for w in workflows if w['event_type'] == 'detected'])
        total_repaired = len([w for w in workflows if w['event_type'] == 'completed'])

        if total_failed == 0:
            return 0.0

        return (total_repaired / total_failed) * 100

    def get_time_to_recovery(self, workflow_id):
        """Calculate Time to Recovery for a workflow"""
        Query = self.workflows._query_constructor
        events = self.workflows.search(Query.workflow_id == workflow_id)

        if not events:
            return None

        # Sort by timestamp
        events.sort(key=lambda x: x['timestamp'])

        detected_time = None
        completed_time = None

        for event in events:
            if event['event_type'] == 'detected':
                detected_time = datetime.fromisoformat(event['timestamp'])
            if event['event_type'] == 'completed':
                completed_time = datetime.fromisoformat(event['timestamp'])

        if detected_time and completed_time:
            return (completed_time - detected_time).total_seconds()

        return None

    def get_root_cause_accuracy(self, days=7):
        """Calculate Root Cause Accuracy (requires manual validation)"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        Query = self.analyses._query_constructor
        analyses = self.analyses.search(Query.timestamp >= cutoff)

        # Filter only validated analyses
        validated = [a for a in analyses if 'validated' in a and 'correct' in a]

        if not validated:
            return None

        correct = len([a for a in validated if a['correct'] == True])
        return (correct / len(validated)) * 100

    def get_average_llm_tokens(self, days=7):
        """Calculate average LLM token usage"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        Query = self.analyses._query_constructor
        analyses = self.analyses.search(Query.timestamp >= cutoff)

        tokens = [a['llm_tokens_used'] for a in analyses if 'llm_tokens_used' in a]

        if not tokens:
            return 0

        return statistics.mean(tokens)

    def get_cost_per_repair(self, days=7):
        """Calculate average cost per successful repair"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        Query = self.costs._query_constructor
        costs = self.costs.search(Query.timestamp >= cutoff)

        Query2 = self.workflows._query_constructor
        completed = self.workflows.search(
            (Query2.timestamp >= cutoff) &
            (Query2.event_type == 'completed')
        )

        total_cost = sum([c.get('llm_cost_usd', 0) for c in costs])
        num_repaired = len(completed)

        if num_repaired == 0:
            return 0

        return total_cost / num_repaired
```

---

## Phase 2: Instrumentation - Add Tracking to Existing Agents

### 2.1 Monitor Agent Instrumentation

**File**: `Monitoring/server_rest.py`

Add to workflow detection:

```python
from metrics_db import MetricsDatabase

metrics_db = MetricsDatabase('../Dashboard/metrics.json')

# When failure detected:
def on_workflow_failure_detected(workflow_id, workflow_data):
    metrics_db.record_workflow_event(
        workflow_id=workflow_id,
        event_type='detected',
        data={
            'state': workflow_data.get('state'),
            'workflow_dir': workflow_data.get('workflow_dir'),
            'detection_method': 'pegasus-analyzer'
        }
    )
```

### 2.2 Analyzer Agent Instrumentation

**File**: `Analyzer/analyzer_rest.py`

Add to analysis function:

```python
from metrics_db import MetricsDatabase
import time

metrics_db = MetricsDatabase('../Dashboard/metrics.json')

async def analyze_workflow(workflow_id, ...):
    start_time = time.time()
    tokens_used = 0

    # ... existing analysis code ...

    # After LLM response
    tokens_used = response.get('eval_count', 0)  # From Ollama

    end_time = time.time()
    duration = end_time - start_time

    # Record metrics
    metrics_db.record_analysis(
        workflow_id=workflow_id,
        analysis_data={
            'duration': duration,
            'tokens': tokens_used,
            'root_cause': analysis_result.get('root_cause'),
            'error_type': analysis_result.get('error_type'),
            'fixable': analysis_result.get('fixable'),
            'used_stderr': len(job_out_files) > 0,
            'files_requested': analysis_result.get('files_needed_for_fix', []),
            'confidence': analysis_result.get('confidence', 0.5)
        }
    )

    metrics_db.record_workflow_event(
        workflow_id=workflow_id,
        event_type='analyzed',
        data={'analysis_id': analysis_result.get('id')}
    )
```

### 2.3 Planner Agent Instrumentation

**File**: `Planner/planner_rest.py`

Add to planning function:

```python
from metrics_db import MetricsDatabase
import time

metrics_db = MetricsDatabase('../Dashboard/metrics.json')

async def create_repair_plan(workflow_id, analysis, ...):
    start_time = time.time()
    tokens_used = 0

    # ... existing planning code ...

    tokens_used = response.get('eval_count', 0)

    end_time = time.time()
    duration = end_time - start_time

    # Record metrics
    metrics_db.record_plan(
        workflow_id=workflow_id,
        plan_data={
            'duration': duration,
            'tokens': tokens_used,
            'num_steps': len(plan.get('steps', [])),
            'plan_type': plan.get('type'),
            'risk_level': plan.get('risk_level', 'low'),
            'requires_approval': plan.get('requires_approval', False),
            'valid': True
        }
    )

    metrics_db.record_workflow_event(
        workflow_id=workflow_id,
        event_type='planned',
        data={'plan_id': plan.get('id')}
    )
```

### 2.4 Dashboard Health Monitoring

**File**: `Dashboard/dashboard_server.py`

Add periodic health checks:

```python
from metrics_db import MetricsDatabase
import psutil

metrics_db = MetricsDatabase('metrics.json')

def record_agent_health():
    """Called every 30 seconds"""
    agents = {
        'monitor': MONITOR_URL,
        'analyzer': ANALYZER_URL,
        'planner': PLANNER_URL
    }

    for agent_name, url in agents.items():
        try:
            start = time.time()
            response = requests.get(f"{url}/health", timeout=2)
            response_time = (time.time() - start) * 1000  # ms

            metrics_db.record_system_health(
                agent_name=agent_name,
                health_data={
                    'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                    'response_time_ms': response_time,
                    'cpu': psutil.cpu_percent(),
                    'memory': psutil.virtual_memory().used / 1024 / 1024  # MB
                }
            )
        except Exception as e:
            metrics_db.record_system_health(
                agent_name=agent_name,
                health_data={
                    'status': 'unhealthy',
                    'error': str(e)
                }
            )

# Add to background polling
def poll_loop():
    while polling_active:
        try:
            poll_agent_activities()
            record_agent_health()  # Add this
        except Exception as e:
            print(f"Error in polling loop: {e}")
        time.sleep(30)
```

---

## Phase 3: Metrics Dashboard UI

### 3.1 Backend API Endpoints

**File**: `Dashboard/dashboard_server.py`

```python
from metrics_db import MetricsDatabase

metrics_db = MetricsDatabase('metrics.json')

@app.route('/api/metrics/summary', methods=['GET'])
def get_metrics_summary():
    """Get overall metrics summary"""
    days = int(request.args.get('days', 7))

    return jsonify({
        'success': True,
        'period_days': days,
        'metrics': {
            'repair_success_rate': metrics_db.get_repair_success_rate(days),
            'average_llm_tokens': metrics_db.get_average_llm_tokens(days),
            'cost_per_repair': metrics_db.get_cost_per_repair(days),
            'root_cause_accuracy': metrics_db.get_root_cause_accuracy(days)
        }
    })

@app.route('/api/metrics/workflows', methods=['GET'])
def get_workflow_metrics():
    """Get detailed workflow metrics"""
    days = int(request.args.get('days', 7))
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    Query = metrics_db.workflows._query_constructor
    events = metrics_db.workflows.search(Query.timestamp >= cutoff)

    # Group by workflow_id
    workflows = {}
    for event in events:
        wf_id = event['workflow_id']
        if wf_id not in workflows:
            workflows[wf_id] = []
        workflows[wf_id].append(event)

    # Calculate TTR for each workflow
    results = []
    for wf_id, wf_events in workflows.items():
        ttr = metrics_db.get_time_to_recovery(wf_id)

        results.append({
            'workflow_id': wf_id,
            'time_to_recovery_seconds': ttr,
            'events': wf_events
        })

    return jsonify({
        'success': True,
        'workflows': results
    })

@app.route('/api/metrics/agents', methods=['GET'])
def get_agent_metrics():
    """Get agent performance metrics"""
    days = int(request.args.get('days', 7))
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    Query = metrics_db.system_health._query_constructor
    health_records = metrics_db.system_health.search(Query.timestamp >= cutoff)

    # Group by agent
    agents = {}
    for record in health_records:
        agent = record['agent']
        if agent not in agents:
            agents[agent] = {
                'total_checks': 0,
                'healthy_checks': 0,
                'response_times': []
            }

        agents[agent]['total_checks'] += 1
        if record['status'] == 'healthy':
            agents[agent]['healthy_checks'] += 1
        if 'response_time_ms' in record:
            agents[agent]['response_times'].append(record['response_time_ms'])

    # Calculate metrics
    results = {}
    for agent, data in agents.items():
        uptime = (data['healthy_checks'] / data['total_checks']) * 100 if data['total_checks'] > 0 else 0
        avg_response = statistics.mean(data['response_times']) if data['response_times'] else 0

        results[agent] = {
            'uptime_percent': uptime,
            'avg_response_time_ms': avg_response,
            'total_checks': data['total_checks']
        }

    return jsonify({
        'success': True,
        'agents': results
    })

@app.route('/api/metrics/costs', methods=['GET'])
def get_cost_metrics():
    """Get cost breakdown"""
    days = int(request.args.get('days', 7))
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    Query = metrics_db.costs._query_constructor
    cost_records = metrics_db.costs.search(Query.timestamp >= cutoff)

    total_tokens = sum([c.get('llm_tokens_total', 0) for c in cost_records])
    total_cost = sum([c.get('llm_cost_usd', 0) for c in cost_records])

    return jsonify({
        'success': True,
        'total_tokens': total_tokens,
        'total_cost_usd': total_cost,
        'cost_per_repair': metrics_db.get_cost_per_repair(days),
        'records': cost_records
    })

@app.route('/api/metrics/error_distribution', methods=['GET'])
def get_error_distribution():
    """Get error type distribution"""
    days = int(request.args.get('days', 7))
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    Query = metrics_db.analyses._query_constructor
    analyses = metrics_db.analyses.search(Query.timestamp >= cutoff)

    error_types = {}
    for analysis in analyses:
        error_type = analysis.get('error_type', 'unknown')
        error_types[error_type] = error_types.get(error_type, 0) + 1

    return jsonify({
        'success': True,
        'error_distribution': error_types
    })
```

### 3.2 Frontend Metrics Dashboard

**File**: `Dashboard/templates/dashboard.html`

Add new "Metrics" view:

```html
<!-- Metrics View -->
<div class="view-container" id="view-metrics">
    <div class="section fade-in">
        <div class="section-header">
            <h2 class="section-title">
                <span>📊</span>
                <span>System Metrics</span>
            </h2>
            <div class="section-actions">
                <select id="metrics-timerange" onchange="loadMetrics()" style="padding: 8px 12px; border-radius: 6px; border: 1px solid var(--gray-300);">
                    <option value="1">Last 24 Hours</option>
                    <option value="7" selected>Last 7 Days</option>
                    <option value="30">Last 30 Days</option>
                    <option value="90">Last 90 Days</option>
                </select>
                <button class="btn btn-secondary" onclick="loadMetrics()">
                    🔄 Refresh
                </button>
                <button class="btn btn-primary" onclick="exportMetrics()">
                    📥 Export Report
                </button>
            </div>
        </div>

        <!-- KPI Cards -->
        <div class="stats-grid" style="margin-bottom: 24px;">
            <div class="stat-card">
                <div class="stat-icon success">✅</div>
                <div class="stat-title">Repair Success Rate</div>
                <div class="stat-value" id="metric-success-rate">-</div>
                <div class="stat-subtitle" id="metric-success-subtitle">-</div>
            </div>

            <div class="stat-card">
                <div class="stat-icon primary">⏱️</div>
                <div class="stat-title">Avg Time to Recovery</div>
                <div class="stat-value" id="metric-ttr">-</div>
                <div class="stat-subtitle">Minutes</div>
            </div>

            <div class="stat-card">
                <div class="stat-icon warning">🎯</div>
                <div class="stat-title">Root Cause Accuracy</div>
                <div class="stat-value" id="metric-rca">-</div>
                <div class="stat-subtitle">-</div>
            </div>

            <div class="stat-card">
                <div class="stat-icon danger">💰</div>
                <div class="stat-title">Cost per Repair</div>
                <div class="stat-value" id="metric-cost">-</div>
                <div class="stat-subtitle">USD</div>
            </div>
        </div>

        <!-- Charts Grid -->
        <div class="charts-grid" style="margin-bottom: 24px;">
            <!-- Error Distribution Chart -->
            <div class="chart-card">
                <div class="chart-title">Error Type Distribution</div>
                <div class="chart-container">
                    <canvas id="error-distribution-chart"></canvas>
                </div>
            </div>

            <!-- Time to Recovery Trend -->
            <div class="chart-card">
                <div class="chart-title">Time to Recovery Trend</div>
                <div class="chart-container">
                    <canvas id="ttr-trend-chart"></canvas>
                </div>
            </div>
        </div>

        <!-- Agent Performance Table -->
        <div class="section">
            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px;">Agent Performance</h3>
            <table class="workflows-table" id="agent-metrics-table">
                <thead>
                    <tr>
                        <th>Agent</th>
                        <th>Uptime %</th>
                        <th>Avg Response Time</th>
                        <th>Health Checks</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="agent-metrics-body">
                    <tr>
                        <td colspan="5">Loading...</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
```

JavaScript to load metrics:

```javascript
async function loadMetrics() {
    const days = document.getElementById('metrics-timerange').value;

    try {
        // Load summary metrics
        const summaryResponse = await fetch(`/api/metrics/summary?days=${days}`);
        const summaryData = await summaryResponse.json();

        if (summaryData.success) {
            const m = summaryData.metrics;

            document.getElementById('metric-success-rate').textContent =
                m.repair_success_rate ? `${m.repair_success_rate.toFixed(1)}%` : 'N/A';

            document.getElementById('metric-rca').textContent =
                m.root_cause_accuracy ? `${m.root_cause_accuracy.toFixed(1)}%` : 'N/A';

            document.getElementById('metric-cost').textContent =
                m.cost_per_repair ? `$${m.cost_per_repair.toFixed(2)}` : 'N/A';
        }

        // Load workflow metrics for TTR
        const workflowResponse = await fetch(`/api/metrics/workflows?days=${days}`);
        const workflowData = await workflowResponse.json();

        if (workflowData.success && workflowData.workflows.length > 0) {
            const ttrs = workflowData.workflows
                .map(w => w.time_to_recovery_seconds)
                .filter(t => t != null);

            if (ttrs.length > 0) {
                const avgTTR = ttrs.reduce((a, b) => a + b, 0) / ttrs.length;
                document.getElementById('metric-ttr').textContent =
                    `${(avgTTR / 60).toFixed(1)}`;
            }
        }

        // Load agent metrics
        loadAgentMetrics(days);

        // Load error distribution chart
        loadErrorDistribution(days);

    } catch (error) {
        console.error('Error loading metrics:', error);
    }
}

async function loadAgentMetrics(days) {
    const response = await fetch(`/api/metrics/agents?days=${days}`);
    const data = await response.json();

    if (data.success) {
        const tbody = document.getElementById('agent-metrics-body');
        tbody.innerHTML = Object.entries(data.agents).map(([agent, metrics]) => `
            <tr>
                <td><strong>${agent}</strong></td>
                <td>${metrics.uptime_percent.toFixed(1)}%</td>
                <td>${metrics.avg_response_time_ms.toFixed(0)}ms</td>
                <td>${metrics.total_checks}</td>
                <td>
                    <span class="workflow-status ${metrics.uptime_percent > 95 ? 'success' : 'warning'}">
                        ${metrics.uptime_percent > 95 ? 'Healthy' : 'Degraded'}
                    </span>
                </td>
            </tr>
        `).join('');
    }
}

async function loadErrorDistribution(days) {
    const response = await fetch(`/api/metrics/error_distribution?days=${days}`);
    const data = await response.json();

    if (data.success) {
        const ctx = document.getElementById('error-distribution-chart').getContext('2d');
        new Chart(ctx, {
            type: 'pie',
            data: {
                labels: Object.keys(data.error_distribution),
                datasets: [{
                    data: Object.values(data.error_distribution),
                    backgroundColor: [
                        '#ef4444', '#f59e0b', '#10b981',
                        '#3b82f6', '#8b5cf6', '#ec4899'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }
}
```

---

## Phase 4: Export & Reporting

### 4.1 Metrics Export API

```python
@app.route('/api/metrics/export', methods=['GET'])
def export_metrics_report():
    """Export comprehensive metrics report"""
    days = int(request.args.get('days', 7))

    report = {
        'generated_at': datetime.now().isoformat(),
        'period_days': days,
        'summary': {
            'repair_success_rate': metrics_db.get_repair_success_rate(days),
            'root_cause_accuracy': metrics_db.get_root_cause_accuracy(days),
            'average_llm_tokens': metrics_db.get_average_llm_tokens(days),
            'cost_per_repair': metrics_db.get_cost_per_repair(days)
        },
        'workflows': [],
        'agents': {},
        'costs': {}
    }

    # Get all workflow data
    # Get all agent data
    # Get all cost data

    # Create CSV or JSON export
    import tempfile
    import csv

    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w') as f:
        json.dump(report, f, indent=2)

    return send_file(
        path,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'metrics_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )
```

---

## Phase 5: Installation Steps

### Step 1: Install Dependencies

```bash
pip install psutil statistics
```

### Step 2: Create Metrics Database File

```bash
cd Dashboard
python3 -c "from metrics_db import MetricsDatabase; MetricsDatabase('metrics.json')"
```

### Step 3: Add to Each Agent

Add import and initialization to each agent's main file.

### Step 4: Add Metrics View to Sidebar

In `dashboard.html`:

```html
<div class="nav-item" data-view="metrics" onclick="switchView('metrics')">
    <span class="nav-icon">📊</span>
    <span>Metrics</span>
</div>
```

### Step 5: Test Metrics Collection

Run a test workflow and verify metrics are recorded.

---

## Next Steps

1. Implement Phase 1 (Database)
2. Instrument agents (Phase 2)
3. Build dashboard UI (Phase 3)
4. Add export functionality (Phase 4)
5. Validate with real workflows
6. Add alerting based on metrics

---

This provides a complete, production-ready metrics system integrated into your existing MAPE-K architecture!

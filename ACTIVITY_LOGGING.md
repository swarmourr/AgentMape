# Activity Logging System

## Overview

The MAPE-K system now includes a comprehensive activity logging system that displays real-time system activities in the dashboard. This provides visibility into what each agent is doing at any moment.

## Features

✅ **Real-time Activity Feed** - Shows live system activities as they happen
✅ **Agent Actions** - Tracks Monitor, Analyzer, Planner, and Executor activities
✅ **Workflow Context** - Links activities to specific workflows
✅ **Log Levels** - Info, Success, Warning, Error with color coding
✅ **Auto-cleanup** - Keeps last 1000 activities automatically

## What You'll See

### Example Activities:

**Monitor:**
- ✅ **Monitor** started monitoring workflow
  - _Detected new workflow in /path/to/workflow_
  - Workflow: 7ab8bfc7...

**Analyzer:**
- ℹ️ **Analyzer** started analyzing workflow
  - _Analyzer analyzer_001 started root cause analysis_
  - Workflow: 7ab8bfc7...

**Planner:**
- ℹ️ **Planner** started creating repair plan
  - _Planning repairs for workflow issues_
  - Workflow: 7ab8bfc7...

**Executor:**
- ✅ **Executor** completed repairs
  - _Successfully executed 3 repair actions_
  - Workflow: 7ab8bfc7...

## Implementation

### Backend (Monitor Agent)

**Activity Log Storage:**
- Stored in TinyDB: `activity_log_table`
- Automatically limits to 1000 most recent entries
- Fields: timestamp, agent, action, workflow_id, details, level

**Logging Function:**
```python
log_activity(
    agent="Monitor",
    action="started_monitoring",
    workflow_id="7ab8bfc7-...",
    details="Detected new workflow in /path/to/workflow",
    level="success"  # info, success, warning, error
)
```

**API Endpoint:**
```
GET /api/activities?limit=50&workflow_id=XXX&agent=Monitor
```

**Parameters:**
- `limit` - Number of activities to return (default: 50)
- `workflow_id` - Filter by specific workflow (optional)
- `agent` - Filter by specific agent (optional)

**Response:**
```json
{
  "activities": [
    {
      "timestamp": "2025-10-13T10:30:45",
      "agent": "Monitor",
      "action": "started_monitoring",
      "workflow_id": "7ab8bfc7-8d03-4025-ad6b-69963cd9f9b4",
      "details": "Detected new workflow in /path/to/workflow",
      "level": "success"
    }
  ],
  "total": 1,
  "filtered": 1,
  "timestamp": "2025-10-13T10:31:00"
}
```

### Frontend (Dashboard)

**Location:** Dashboard main page under "Real-Time Activity Feed"

**Features:**
- Color-coded by log level (green=success, blue=info, yellow=warning, red=error)
- Agent icons for visual identification
- Relative timestamps ("2 minutes ago")
- Workflow ID preview
- Activity details in expandable format
- Auto-refresh every 15 seconds

**Display Format:**
```
🔬 Analyzer                                    2 minutes ago
ℹ️ started analyzing workflow
Workflow: 7ab8bfc7...
└─ Analyzer analyzer_001 started root cause analysis
```

## Adding Activity Logging to Your Code

### In Monitor Agent:
```python
# When starting to monitor a workflow
log_activity(
    agent="Monitor",
    action="started_monitoring",
    workflow_id=workflow_id,
    details=f"Detected new workflow in {iwd}",
    level="success"
)

# When requesting analysis
log_activity(
    agent="Analyzer",
    action="started_analyzing",
    workflow_id=workflow_id,
    details=f"Analyzer {analyzer_id} started root cause analysis",
    level="info"
)
```

### In Analyzer Agent:
```python
# When analysis completes
log_activity(
    agent="Analyzer",
    action="completed_analysis",
    workflow_id=workflow_id,
    details=f"Found {problem_count} issues",
    level="success" if problem_count > 0 else "info"
)

# When analysis fails
log_activity(
    agent="Analyzer",
    action="analysis_failed",
    workflow_id=workflow_id,
    details=str(error),
    level="error"
)
```

### In Planner Agent:
```python
# When planning starts
log_activity(
    agent="Planner",
    action="started_planning",
    workflow_id=workflow_id,
    details=f"Creating repair plan for {problem_count} problems",
    level="info"
)

# When plan is generated
log_activity(
    agent="Planner",
    action="completed_planning",
    workflow_id=workflow_id,
    details=f"Generated plan with {action_count} repair actions",
    level="success"
)
```

### In Executor Agent:
```python
# When execution starts
log_activity(
    agent="Executor",
    action="started_execution",
    workflow_id=workflow_id,
    details=f"Executing {action_count} repair actions",
    level="info"
)

# When execution completes
log_activity(
    agent="Executor",
    action="completed_execution",
    workflow_id=workflow_id,
    details=f"Successfully executed {success_count}/{total_count} actions",
    level="success" if success_count == total_count else "warning"
)
```

## Action Names

### Standard Actions:

**Monitor:**
- `started_monitoring` - Workflow detection
- `metadata_collected` - Metadata gathered
- `workflow_failed` - Workflow failure detected

**Analyzer:**
- `started_analyzing` - Analysis initiated
- `completed_analysis` - Analysis finished
- `analysis_failed` - Analysis error

**Planner:**
- `started_planning` - Planning initiated
- `completed_planning` - Plan generated
- `planning_failed` - Planning error

**Executor:**
- `started_execution` - Execution initiated
- `completed_execution` - Execution finished
- `execution_failed` - Execution error

## Log Levels

| Level | Icon | Color | Use Case |
|-------|------|-------|----------|
| `success` | ✅ | Green (#10b981) | Successful completion of actions |
| `info` | ℹ️ | Blue (#6366f1) | General information, process started |
| `warning` | ⚠️ | Yellow (#f59e0b) | Partial success, potential issues |
| `error` | ❌ | Red (#ef4444) | Failures, errors, critical issues |

## Testing

### View Activities in Dashboard:
1. Start the system: `./start_system.sh`
2. Open dashboard: `http://localhost:5000`
3. Look for "Real-Time Activity Feed" section
4. Activities will appear as workflows are processed

### Test API Directly:
```bash
# Get all recent activities
curl http://localhost:8080/api/activities?limit=20

# Get activities for specific workflow
curl "http://localhost:8080/api/activities?workflow_id=7ab8bfc7-8d03-4025-ad6b-69963cd9f9b4"

# Get activities from specific agent
curl "http://localhost:8080/api/activities?agent=Monitor&limit=10"
```

### Check Activity Log Database:
```python
from tinydb import TinyDB

db = TinyDB("Monitoring/workflows.json")
activities = db.table("activity_log").all()

print(f"Total activities: {len(activities)}")
for activity in activities[-5:]:  # Last 5
    print(f"{activity['agent']}: {activity['action']} - {activity.get('details', '')}")
```

## Benefits

1. **Transparency** - See exactly what the system is doing
2. **Debugging** - Track down issues by seeing agent activities
3. **Monitoring** - Real-time view of system health
4. **Audit Trail** - Historical record of system actions
5. **User Confidence** - Clear visibility builds trust

## Examples

### Successful Workflow Processing:
```
✅ Monitor started monitoring workflow (2 sec ago)
   └─ Detected new workflow in /home/user/workflows/run0001

ℹ️ Analyzer started analyzing workflow (5 sec ago)
   └─ Analyzer analyzer_001 started root cause analysis

ℹ️ Planner started creating repair plan (10 sec ago)
   └─ Creating repair plan for 3 problems

✅ Executor completed repairs (15 sec ago)
   └─ Successfully executed 3 repair actions
```

### Error Scenario:
```
✅ Monitor started monitoring workflow (1 min ago)
   └─ Detected new workflow in /home/user/workflows/run0042

ℹ️ Analyzer started analyzing workflow (1 min ago)
   └─ Analyzer analyzer_001 started root cause analysis

❌ Analyzer analysis failed (50 sec ago)
   └─ Could not parse workflow DAX file
```

## Future Enhancements

Possible additions:
- Filter activities by date range
- Export activity log to file
- Real-time notifications for specific events
- Activity search functionality
- Performance metrics (execution times)
- Activity grouping by workflow

---

**Activity logging is now live!** Check your dashboard to see system activities in real-time. 🎉

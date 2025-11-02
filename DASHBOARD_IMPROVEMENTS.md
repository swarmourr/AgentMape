# Dashboard Improvements & Vision

## Current Dashboard Status

**What Exists Now:**
- Basic workflow list view
- Workflow statistics (total, running, failed, completed)
- Simple status display
- vis-network library for workflow visualization

**Current Limitations:**
- Static view (manual refresh required)
- No real-time updates
- No MAPE-K loop visualization
- No agent activity visibility
- No error drill-down
- No historical trends
- No plan visualization

---

## Vision: Comprehensive MAPE-K Dashboard

A real-time, interactive dashboard that shows the complete autonomous workflow management lifecycle from failure detection to automatic recovery.

---

## Improvement 1: Real-Time Activity Stream

### What
Live feed showing what's happening across all agents right now

### Why
- Users want to know "what is the system doing?"
- Real-time updates instead of manual refresh
- Build trust through transparency

### Design

```
┌─────────────────────────────────────────────────────────┐
│  LIVE ACTIVITY FEED                      🔴 LIVE        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ⏰ 14:32:15  MONITOR    Detected failure               │
│              Workflow: falcon-7b (3bae3258...)          │
│              Job: FineTuneLLM_ID0000001 (exit code: 1)  │
│              → Extracting .out files...                  │
│                                                          │
│  ⏰ 14:32:16  MONITOR    ✓ Extracted 1 .out file        │
│              → Sending to Analyzer                       │
│                                                          │
│  ⏰ 14:32:17  ANALYZER   Analyzing workflow failure      │
│              → Extracted stderr (143 chars)              │
│              → Calling LLM for root cause analysis...    │
│                                                          │
│  ⏰ 14:32:25  ANALYZER   ✓ Root cause identified         │
│              Error: SyntaxError at line 105              │
│              Confidence: 95%                             │
│              → Sending to Planner                        │
│                                                          │
│  ⏰ 14:32:26  PLANNER    Generating corrective plan      │
│              → Stage 1: Identifying required files       │
│                                                          │
│  ⏰ 14:32:30  PLANNER    ✓ Plan generated                │
│              Actions: 1 (edit_file)                      │
│              Estimated time: 2 minutes                   │
│              → Awaiting execution                        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Features
- **Auto-scroll**: New events appear at top
- **Filtering**: Filter by agent, workflow, severity
- **Color coding**:
  - 🔵 Info (normal operations)
  - 🟡 Warning (potential issues)
  - 🔴 Error (failures)
  - 🟢 Success (completions)
- **Timestamps**: Show time elapsed since event
- **Expandable**: Click event to see full details
- **Websocket-based**: Real-time push from agents

### Technical Implementation
```javascript
// Frontend (React/Vue)
const socket = new WebSocket('ws://monitor:8084/events');

socket.onmessage = (event) => {
  const activity = JSON.parse(event.data);
  addToActivityFeed(activity);
};

// Backend (Monitor agent)
async def publish_activity(event_type, data):
    await websocket_manager.broadcast({
        "timestamp": datetime.now().isoformat(),
        "agent": "monitor",
        "event_type": event_type,
        "data": data
    });
```

---

## Improvement 2: MAPE-K Loop Visualization

### What
Visual diagram showing data flow through Monitor → Analyze → Plan → Execute

### Why
- Users need to understand the autonomous loop
- See where workflows are in the pipeline
- Identify bottlenecks

### Design

```
┌──────────────────────────────────────────────────────────────┐
│  MAPE-K LOOP STATUS                                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌────┐│
│   │ MONITOR │─────▶│ ANALYZE │─────▶│  PLAN   │─────▶│EXEC││
│   └─────────┘  2   └─────────┘  1   └─────────┘  3   └────┘│
│       │                                                      │
│       │            ┌───────────────┐                        │
│       └───────────▶│   KNOWLEDGE   │◀───────────────────────┤
│                    └───────────────┘                        │
│                                                              │
│  Active Workflows per Stage:                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  Monitor:   2 detecting failures                            │
│  Analyze:   1 diagnosing (falcon-7b)                        │
│  Plan:      3 generating fixes                              │
│  Execute:   0 (not implemented)                             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Interactive Features
- **Clickable nodes**: Click "Analyze" to see workflows being analyzed
- **Animated flow**: Show data moving between stages
- **Queue depth**: Show how many workflows waiting at each stage
- **Stage metrics**: Average time spent in each stage
- **Health indicators**:
  - 🟢 Green: Healthy (processing < 5 workflows)
  - 🟡 Yellow: Busy (5-10 workflows)
  - 🔴 Red: Overloaded (>10 workflows)

### Technical Implementation
```javascript
// D3.js or vis.js for visualization
const mapeLoop = {
  nodes: [
    { id: 'monitor', label: 'Monitor', count: 2, avgTime: 5 },
    { id: 'analyze', label: 'Analyze', count: 1, avgTime: 15 },
    { id: 'plan', label: 'Plan', count: 3, avgTime: 30 },
    { id: 'execute', label: 'Execute', count: 0, avgTime: 120 }
  ],
  edges: [
    { from: 'monitor', to: 'analyze', workflows: ['falcon-7b'] },
    { from: 'analyze', to: 'plan', workflows: ['montage-abc'] },
    { from: 'plan', to: 'execute', workflows: ['blast-123', 'clima-456'] }
  ]
};
```

---

## Improvement 3: Workflow Failure Drill-Down

### What
Detailed view of a failed workflow with complete diagnostic information

### Why
- Users need to understand WHY workflow failed
- See the complete error chain
- Verify autonomous diagnosis is correct

### Design

```
┌──────────────────────────────────────────────────────────────┐
│  Workflow: falcon-7b (3bae3258-f3f4-4b16-b579-58210af66dd7)  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  STATUS: Failed ❌                                           │
│  SUBMITTED: 2025-01-30 14:30:00                              │
│  FAILED: 2025-01-30 14:32:15 (2m 15s)                        │
│  RETRY ATTEMPTS: 3 / 3                                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 🔍 ROOT CAUSE ANALYSIS                                 │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Job: FineTuneLLM_ID0000001                            │ │
│  │  Transformation: FineTuneLLM                           │ │
│  │  Script: /home/hsafri/scripts/FineTuneLLM              │ │
│  │                                                        │ │
│  │  Error Type: SyntaxError                              │ │
│  │  Severity: High                                        │ │
│  │  Auto-fixable: Yes                                     │ │
│  │  Confidence: 95%                                       │ │
│  │                                                        │ │
│  │  Error Message:                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │ File "/srv/./FineTuneLLM", line 105              │ │ │
│  │  │     tokenizer=tokenizer                          │ │ │
│  │  │               ^^^^^^^^^                           │ │ │
│  │  │ SyntaxError: invalid syntax.                     │ │ │
│  │  │ Perhaps you forgot a comma?                      │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  [📄 View Full stderr] [📂 View Script] [🔧 View Fix] │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 📊 JOB EXECUTION DETAILS                               │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Exit Code: 1                                          │ │
│  │  Duration: 0.05s                                       │ │
│  │  Memory Used: 8.1 MB                                   │ │
│  │  Working Directory: /srv                               │ │
│  │                                                        │ │
│  │  Missing Files:                                        │ │
│  │  • /srv/falcon-7b.zip (ENOENT)                         │ │
│  │    ⚠️  This is a SYMPTOM, not root cause              │ │
│  │    Job crashed before creating this file               │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 🔧 CORRECTIVE PLAN                                     │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Plan ID: plan-abc123                                  │ │
│  │  Generated: 2025-01-30 14:32:30                        │ │
│  │  Status: ⏳ Awaiting Execution                         │ │
│  │                                                        │ │
│  │  Actions:                                              │ │
│  │  1. Edit File                                          │ │
│  │     Path: /home/hsafri/scripts/FineTuneLLM             │ │
│  │     Line: 105                                          │ │
│  │     Change: Add comma after 'tokenizer=tokenizer'      │ │
│  │                                                        │ │
│  │  Estimated Recovery Time: 2 minutes                    │ │
│  │                                                        │ │
│  │  [▶️ Execute Plan] [📄 View Full Plan] [❌ Reject]     │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 📈 DEPENDENCY GRAPH                                    │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │         ┌───────────┐                                  │ │
│  │         │  Stage-In │  ✓ Completed                     │ │
│  │         └─────┬─────┘                                  │ │
│  │               │                                        │ │
│  │         ┌─────▼─────┐                                  │ │
│  │         │FineTuneLLM│  ❌ FAILED ◀── ROOT CAUSE       │ │
│  │         └─────┬─────┘                                  │ │
│  │               │                                        │ │
│  │         ┌─────▼─────┐                                  │ │
│  │         │  Evaluate │  ⏸️ Waiting (cascade blocked)   │ │
│  │         └───────────┘                                  │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Features
- **Clear root cause highlighting**: Distinguish from cascade symptoms
- **Expandable sections**: Click to see more details
- **Color coding**:
  - 🔴 Failed jobs
  - 🟢 Completed jobs
  - 🟡 Waiting jobs
  - 🔵 Running jobs
- **Action buttons**: Execute plan, view files, reject fix
- **Dependency visualization**: See impact of failure on downstream jobs

---

## Improvement 4: Historical Trends & Analytics

### What
Charts showing workflow success rates, common errors, MTTF (Mean Time To Failure), MTTR (Mean Time To Recovery)

### Why
- Identify recurring problems
- Measure system improvement over time
- Make data-driven decisions

### Design

```
┌──────────────────────────────────────────────────────────────┐
│  ANALYTICS DASHBOARD                    Last 30 Days         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ SUCCESS RATE TREND                                     │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │  100% ┤                                      ╭─────    │ │
│  │   90% ┤                              ╭───────╯         │ │
│  │   80% ┤                      ╭───────╯                 │ │
│  │   70% ┤              ╭───────╯                         │ │
│  │   60% ┤      ╭───────╯                                 │ │
│  │   50% ┤──────╯                                         │ │
│  │       └┬─────┬─────┬─────┬─────┬─────┬─────┬─────     │ │
│  │       Week1 Week2 Week3 Week4 Week5 Week6 Week7        │ │
│  │                                                        │ │
│  │  📈 Improvement: +42% since MAPE-K deployment         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ TOP 5 ERROR TYPES                                      │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │  1. SyntaxError         ████████████████ 45%           │ │
│  │  2. ImportError         ██████████ 25%                 │ │
│  │  3. Out of Memory       ██████ 15%                     │ │
│  │  4. Missing Files       ████ 10%                       │ │
│  │  5. Permission Denied   ██ 5%                          │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ RECOVERY METRICS                                       │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Total Failures (30 days): 157                         │ │
│  │  Auto-Fixed: 112 (71%)                                 │ │
│  │  Manual Intervention: 45 (29%)                         │ │
│  │                                                        │ │
│  │  Average Time to Diagnosis: 12 seconds                 │ │
│  │  Average Time to Plan: 25 seconds                      │ │
│  │  Average Time to Recovery: 4m 35s                      │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ LLM ANALYSIS ACCURACY                                  │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Root Cause Identified: 89% ████████████████████       │ │
│  │  Fix Success Rate:      73% ███████████████            │ │
│  │  Confidence Score Avg:  0.87                           │ │
│  │                                                        │ │
│  │  False Positives: 8                                    │ │
│  │  False Negatives: 12                                   │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Chart Types
- **Line charts**: Success rate over time, MTTR trends
- **Bar charts**: Error type distribution, fix success by error type
- **Pie charts**: Auto-fixed vs manual intervention ratio
- **Heatmaps**: Failure patterns by time/day (find peak failure times)

### Exportable Reports
- CSV export of all metrics
- PDF summary reports
- Scheduled email reports (daily/weekly)

---

## Improvement 5: Agent Health Monitoring

### What
Show status and health of each MAPE-K agent

### Why
- Detect if agents are down or unhealthy
- Monitor resource usage
- Prevent service degradation

### Design

```
┌──────────────────────────────────────────────────────────────┐
│  AGENT HEALTH DASHBOARD                                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┬──────────┬──────────┬──────────┬─────────┐ │
│  │ Agent       │ Status   │ CPU      │ Memory   │ Queue   │ │
│  ├─────────────┼──────────┼──────────┼──────────┼─────────┤ │
│  │ Monitor     │ 🟢 Up    │ 12%      │ 256 MB   │ 0       │ │
│  │ Analyzer    │ 🟢 Up    │ 45%      │ 1.2 GB   │ 2       │ │
│  │ Planner     │ 🟡 Slow  │ 78%      │ 2.8 GB   │ 8       │ │
│  │ Executor    │ 🔴 Down  │ -        │ -        │ -       │ │
│  │ Knowledge   │ 🟢 Up    │ 5%       │ 128 MB   │ -       │ │
│  └─────────────┴──────────┴──────────┴──────────┴─────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ PLANNER DETAILS (Click to expand)                      │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Status: 🟡 Degraded Performance                       │ │
│  │  Issue: High queue depth (8 workflows waiting)         │ │
│  │  Recommendation: Scale horizontally or increase LLM    │ │
│  │                  timeout                               │ │
│  │                                                        │ │
│  │  Last Heartbeat: 2 seconds ago                         │ │
│  │  Uptime: 3 days, 14 hours                              │ │
│  │  Requests Processed: 1,247                             │ │
│  │  Avg Response Time: 28s (target: <20s)                 │ │
│  │                                                        │ │
│  │  Recent Errors:                                        │ │
│  │  • 14:25 - LLM timeout (retried successfully)          │ │
│  │  • 13:18 - Connection refused to Knowledge DB          │ │
│  │                                                        │ │
│  │  [🔄 Restart Agent] [📊 View Logs] [⚙️ Configure]     │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Health Indicators
- **🟢 Green**: Healthy (normal operation)
- **🟡 Yellow**: Degraded (slow response, high queue)
- **🔴 Red**: Down (not responding, crashed)
- **🔵 Blue**: Starting/Restarting

### Metrics Tracked
- **Heartbeat**: Last seen timestamp
- **CPU/Memory**: Resource usage
- **Queue depth**: Pending work
- **Response time**: Average latency
- **Error rate**: Failures per hour
- **Uptime**: How long agent has been running

---

## Improvement 6: Plan Visualization & Comparison

### What
Visual representation of corrective plans with before/after comparison

### Why
- Users want to understand what the Planner is proposing
- Review changes before execution
- Learn from past fixes

### Design

```
┌──────────────────────────────────────────────────────────────┐
│  PLAN VIEWER: plan-abc123                                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Generated: 2025-01-30 14:32:30                              │
│  Status: ⏳ Awaiting Approval                                │
│  Confidence: 95%                                             │
│  Estimated Time: 2 minutes                                   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ACTION 1: Edit File                                    │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  File: /home/hsafri/scripts/FineTuneLLM                │ │
│  │  Type: Python Script                                   │ │
│  │  Size: 6,815 bytes                                     │ │
│  │                                                        │ │
│  │  Changes:                                              │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │ Line 105:                                        │ │ │
│  │  │                                                  │ │ │
│  │  │ ❌ BEFORE:                                       │ │ │
│  │  │    model = AutoModelForCausalLM.from_pretrained( │ │ │
│  │  │        model_name                                │ │ │
│  │  │        tokenizer=tokenizer                       │ │ │
│  │  │        device_map="auto"                         │ │ │
│  │  │    )                                             │ │ │
│  │  │                                                  │ │ │
│  │  │ ✅ AFTER:                                        │ │ │
│  │  │    model = AutoModelForCausalLM.from_pretrained( │ │ │
│  │  │        model_name,                 ◄── Added     │ │ │
│  │  │        tokenizer=tokenizer,        ◄── Added     │ │ │
│  │  │        device_map="auto"                         │ │ │
│  │  │    )                                             │ │ │
│  │  │                                                  │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  Impact: Fixes SyntaxError, allows job to execute     │ │
│  │  Risk: Low (syntax fix only, no logic change)         │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ SAFETY CHECKS                                          │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  ✅ No dangerous commands                              │ │
│  │  ✅ File exists and is writable                        │ │
│  │  ✅ No system paths modified                           │ │
│  │  ✅ Backup created                                     │ │
│  │  ✅ Rollback available                                 │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  [✅ Approve & Execute] [✏️ Edit Plan] [❌ Reject]           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Features
- **Diff view**: Highlight changes (added/removed lines)
- **Syntax highlighting**: Language-aware code display
- **Impact assessment**: Show risk level and expected outcome
- **Safety validation**: Show all safety checks passed
- **Approval workflow**: Approve, edit, or reject plans
- **Version history**: Compare with previous plans for same error

---

## Improvement 7: Search & Filtering

### What
Powerful search across all workflows, errors, and plans

### Why
- Find specific failures quickly
- Track down recurring errors
- Analyze patterns

### Design

```
┌──────────────────────────────────────────────────────────────┐
│  🔍 Search Workflows & Errors                                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Search: [SyntaxError                              ] 🔍      │
│                                                              │
│  Filters:                                                    │
│  Status:     [❌ Failed] [ ] Running [ ] Completed           │
│  Date:       [Last 7 days ▼]                                 │
│  Agent:      [All ▼]                                         │
│  Error Type: [SyntaxError ▼]                                 │
│  Auto-fixed: [ ] Yes [✓] No                                  │
│                                                              │
│  ─────────────────────────────────────────────────────────── │
│                                                              │
│  Results: 23 workflows                                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ falcon-7b (3bae3258...)         2025-01-30 14:32:15    │ │
│  │ ❌ Failed - SyntaxError at line 105                    │ │
│  │ Job: FineTuneLLM_ID0000001                             │ │
│  │ [View Details]                                         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ llama-13b (7d3c892f...)         2025-01-28 10:15:42    │ │
│  │ ❌ Failed - SyntaxError at line 87                     │ │
│  │ Job: FineTuneLlama_ID0000002                           │ │
│  │ [View Details]                                         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ... 21 more results                                         │
│                                                              │
│  [Export Results to CSV]                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Search Capabilities
- **Full-text search**: Search in stderr, error messages, file names
- **Advanced filters**: Combine multiple criteria
- **Date ranges**: Last hour, day, week, month, custom
- **Saved searches**: Save common queries
- **Export**: CSV, JSON export of results

---

## Improvement 8: Configuration & Settings

### What
Central place to configure all system settings

### Why
- Different users need different configurations
- Enable/disable features
- Tune LLM parameters

### Design

```
┌──────────────────────────────────────────────────────────────┐
│  ⚙️ SYSTEM SETTINGS                                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ MONITORING SETTINGS                                    │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Polling Interval:       [5] seconds                   │ │
│  │  Extract .out files:     [✓] Enabled                   │ │
│  │  Auto-remove on hold:    [✓] After 1 minute            │ │
│  │  Max retries:            [3]                           │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ANALYZER SETTINGS                                      │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  LLM Model:              [llama3.3:latest ▼]           │ │
│  │  LLM Temperature:        [0.1]        ━━━●────         │ │
│  │  Max tokens:             [2048]                        │ │
│  │  Timeout:                [120] seconds                 │ │
│  │  Prioritize stderr:      [✓] Enabled                   │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ PLANNER SETTINGS                                       │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Multi-stage planning:   [✓] Enabled                   │ │
│  │  Request approval:       [✓] For high-risk plans       │ │
│  │  Auto-execute:           [ ] Disabled (Executor N/A)   │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ NOTIFICATIONS                                          │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │                                                        │ │
│  │  Email alerts:           [✓] On failure                │ │
│  │  Slack integration:      [ ] Disabled                  │ │
│  │  Webhook URL:            [https://...         ]        │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  [💾 Save Settings] [🔄 Reset to Defaults]                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Configurable Parameters
- **Monitor**: Polling interval, retry limits, .out extraction
- **Analyzer**: LLM model, temperature, timeout, stderr priority
- **Planner**: Multi-stage mode, approval workflows
- **Notifications**: Email, Slack, webhooks
- **Security**: API keys, authentication, rate limits

---

## Improvement 9: Notification System

### What
Alert users when important events occur

### Why
- Users can't watch dashboard 24/7
- Need to know immediately when workflows fail
- Acknowledge successful auto-recovery

### Notification Types

**1. Failure Detected**
```
🔴 Workflow Failed: falcon-7b

Job: FineTuneLLM_ID0000001
Error: SyntaxError at line 105
Status: Analyzing...

[View Details] [Dismiss]
```

**2. Analysis Complete**
```
🔵 Analysis Complete: falcon-7b

Root Cause: SyntaxError
Confidence: 95%
Auto-fixable: Yes
Status: Generating plan...

[View Analysis] [Dismiss]
```

**3. Plan Ready**
```
🟡 Corrective Plan Ready: falcon-7b

Actions: 1 (edit file)
Risk: Low
Awaiting approval

[Approve] [Review] [Reject]
```

**4. Auto-Recovery Success**
```
🟢 Workflow Recovered: falcon-7b

Auto-fixed in 4m 35s
Fix: Added comma at line 105
Status: Running

[View Details] [Dismiss]
```

### Notification Channels
- **In-app**: Toast notifications in dashboard
- **Email**: Configurable recipients
- **Slack**: Integration with workspace
- **Webhooks**: Custom integrations
- **SMS**: Critical failures only (via Twilio)

---

## Improvement 10: Mobile-Responsive Design

### What
Dashboard works on tablets and phones

### Why
- Users may need to check status on the go
- Mobile alerts with quick actions
- Approve plans from phone

### Mobile View

```
┌──────────────────────┐
│  MAPE-K Dashboard    │
├──────────────────────┤
│                      │
│  ⚡ 2 Active Issues   │
│                      │
│  ┌──────────────────┐│
│  │ falcon-7b        ││
│  │ ❌ Failed         ││
│  │ 2m ago           ││
│  │ [View] [Fix]     ││
│  └──────────────────┘│
│                      │
│  ┌──────────────────┐│
│  │ llama-13b        ││
│  │ 🔵 Analyzing     ││
│  │ 30s ago          ││
│  │ [View]           ││
│  └──────────────────┘│
│                      │
│  📊 Stats (30 days)  │
│  Success: 89%        │
│  Auto-fixed: 71%     │
│  Avg Recovery: 4m    │
│                      │
│  [All Workflows]     │
│  [Settings]          │
│                      │
└──────────────────────┘
```

---

## Implementation Priority

### Phase 1: Critical (First)
1. ✅ **Real-Time Activity Stream** - Show what's happening
2. ✅ **Workflow Failure Drill-Down** - Understand errors
3. ✅ **Agent Health Monitoring** - Detect issues early

### Phase 2: High Value
4. **MAPE-K Loop Visualization** - Show the flow
5. **Plan Visualization** - Review before execution
6. **Search & Filtering** - Find workflows quickly

### Phase 3: Analytics
7. **Historical Trends** - Learn from patterns
8. **Configuration UI** - Easy settings management

### Phase 4: Nice-to-Have
9. **Notification System** - Alerts and webhooks
10. **Mobile Support** - On-the-go monitoring

---

## Technical Stack Recommendations

### Frontend
- **Framework**: React or Vue.js
- **State Management**: Redux or Vuex
- **UI Components**: Material-UI or Ant Design
- **Charts**: Chart.js or D3.js
- **Real-time**: WebSocket for live updates
- **Code Editor**: Monaco Editor (for viewing/editing files)

### Backend
- **WebSocket Server**: aiohttp WebSocket or Socket.IO
- **API Gateway**: Nginx or Traefik
- **Caching**: Redis for metrics
- **Time-series DB**: InfluxDB for historical data

### Example WebSocket Integration
```python
# Backend (Monitor agent)
class DashboardWebSocket:
    def __init__(self):
        self.clients = set()

    async def broadcast_event(self, event):
        """Send event to all connected clients"""
        for client in self.clients:
            await client.send_json(event)

    async def on_workflow_failed(self, workflow_id, data):
        """Broadcast failure to dashboard"""
        await self.broadcast_event({
            "type": "workflow.failed",
            "workflow_id": workflow_id,
            "timestamp": datetime.now().isoformat(),
            "data": data
        })

# Frontend (React)
useEffect(() => {
  const socket = new WebSocket('ws://monitor:8084/dashboard');

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'workflow.failed') {
      // Update UI with failure
      addNotification(data);
      updateWorkflowList(data.workflow_id);
    }
  };

  return () => socket.close();
}, []);
```

---

## Success Metrics for Dashboard

**Usability:**
- Time to find a failed workflow: **<10 seconds**
- Time to understand root cause: **<30 seconds**
- Time to approve a plan: **<1 minute**

**Performance:**
- Dashboard load time: **<2 seconds**
- Real-time event latency: **<500ms**
- Chart rendering: **<1 second**

**Adoption:**
- Daily active users: **>80% of workflow users**
- Plan approval rate: **>60%**
- User satisfaction: **>4/5 stars**

---

## Summary

The improved dashboard transforms from a basic workflow list to a comprehensive **mission control center** for autonomous workflow management, providing:

1. **Visibility**: See everything happening in real-time
2. **Understanding**: Drill down to root causes instantly
3. **Control**: Review and approve plans before execution
4. **Intelligence**: Learn from trends and patterns
5. **Confidence**: Trust the system through transparency

The dashboard becomes the **window into autonomous operation**, making complex MAPE-K processes understandable and trustworthy for users.

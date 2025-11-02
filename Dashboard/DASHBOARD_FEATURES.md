# MAPE-K Dashboard - Complete Feature List

## Real-Time Monitoring Features

### 1. **WebSocket Live Updates** ✅
- Real-time activity stream via WebSocket (`ws://localhost:8085/ws/activities`)
- Auto-reconnection with exponential backoff
- Live connection indicator (Green "Live" / Red "Disconnected")
- Background polling thread (every 3 seconds)
- Broadcasts all agent activities instantly

### 2. **Toast Popup Notifications** ✅
- Slide-in notifications from top-right
- 4 color-coded types: Info (blue), Success (green), Warning (orange), Error (red)
- Auto-dismiss after 5 seconds with countdown bar
- Manual close button
- Shows agent icons, workflow IDs, and details

### 3. **Sound Notifications** ✅
- Web Audio API with different tones per notification type
- Error (F4), Warning (G4), Info (A4), Success (C5)
- Plays automatically for warnings and errors
- Can be toggled on/off

### 4. **Desktop Notifications** ✅
- Browser native notifications via Notification API
- Shows for critical events (errors, analyzer warnings)
- Click to focus dashboard window
- Auto-closes after 5 seconds

### 5. **Activity Feed** ✅
- Real-time feed of all MAPE-K activities
- Shows last 20 activities (auto-removes old ones)
- Smooth slide-in/fade-out animations
- Search and filter capabilities:
  - Text search across all fields
  - Filter by agent (Monitor, Analyzer, Planner)
  - Filter by status (Info, Success, Warning, Error)
  - Clear filters button

---

## Configuration Management ✅

### 6. **Ollama Configuration Panel** ✅
**Location**: Settings page (⚙️ icon in sidebar)

**Features**:
- Edit Ollama API Base URL
- Edit Model Name
- Select which agents to update (Analyzer, Planner, or both)
- Load current configuration button
- Save configuration button
- Shows current config from both agents
- Real-time status messages (Loading, Saved, Error)

**API Endpoints**:
- `GET /api/config/ollama` - Get current Ollama config
- `PUT /api/config/ollama` - Update Ollama config
- `GET /api/config/agents` - Get all agent configs
- `GET /api/config/agents/<agent_name>` - Get specific agent config
- `PUT /api/config/agents/<agent_name>` - Update agent config
- `POST /api/config/reload/<agent_name>` - Notify agent to reload

**How to Use**:
1. Go to Settings page
2. Click "Load Current Config"
3. Edit API Base URL and/or Model Name
4. Select agents to update
5. Click "Save Configuration"
6. See toast notification confirming save

---

## Workflow Management ✅

### 7. **Workflow Export** ✅
**Location**: Workflows page, each workflow row has "📥 Export" button

**Features**:
- Exports complete workflow data as JSON file
- Includes:
  - Analysis results from Analyzer
  - Repair plan from Planner
  - Workflow metadata from Monitor
  - Execution details
  - Timestamps

**API Endpoints**:
- `GET /api/workflow/<workflow_id>/export` - Get export data as JSON
- `GET /api/workflow/<workflow_id>/export/json` - Download as file
- `GET /api/export/all` - Export all system data

**File Format**:
```json
{
  "workflow_id": "example_wf_123",
  "exported_at": "2025-01-30T10:30:00Z",
  "analysis": { ... },
  "plan": { ... },
  "metadata": { ... }
}
```

### 8. **Workflow Retry** ✅
**Location**: Workflows page, "🔄 Retry" button (only for failed workflows)

**Features**:
- One-click workflow retry
- Executes `pegasus-run <workflow_dir>`
- Confirmation dialog before retry
- Real-time status updates via toast
- Activity log entry created
- Auto-refreshes workflow list after retry

**API Endpoints**:
- `POST /api/workflow/<workflow_id>/retry` - Retry failed workflow

### 9. **Workflow Plan Viewer** ✅
**API Endpoint**: `GET /api/workflow/<workflow_id>/plan`

**Features**:
- Fetch repair plan for any workflow
- Returns latest plan and all historical plans
- Can be accessed programmatically

### 10. **Workflow Analysis Viewer** ✅
**API Endpoint**: `GET /api/workflow/<workflow_id>/analysis`

**Features**:
- Fetch analysis results for any workflow
- Returns root cause, error type, fixability, etc.

---

## Dashboard Views

### 11. **Dashboard Overview** ✅
- Agent status cards (Monitor, Analyzer, Planner)
- Workflow statistics (Active, Success, Failed, Held)
- Real-time activity feed
- Recent workflows table
- System health indicator

### 12. **Workflows View** ✅
- All monitored workflows
- Filterable by status
- Color-coded status badges
- MAPE-K pipeline visualization
- Action buttons: View, Export, Retry, Details

### 13. **Agents View** ✅
- Detailed agent health cards
- Flip cards for more info (URL, port, latency)
- Network topology visualization (vis.js)
- Agent status legend
- Real-time connectivity status

### 14. **Analytics View** ✅
- Workflow state distribution chart
- Problem type distribution chart
- Agent activity chart
- Coming soon: More advanced analytics

### 15. **Settings View** ✅
- Ollama configuration panel
- Agent configuration (coming soon)
- System settings (coming soon)

---

## Additional Features

### 16. **Activity Filtering** ✅
- Real-time search across activities
- Filter by agent type
- Filter by status level
- Shows "No results" empty state when filtered

### 17. **Auto-Remove Old Activities** ✅
- Keeps only last 20 activities in view
- Old activities fade out with animation
- Prevents memory buildup

### 18. **Duplicate Detection** ✅
- Backend checks last 5 activities to prevent duplicates
- Allows re-logging if enough time has passed

### 19. **WebSocket Broadcasting** ✅
- All config changes broadcast to connected clients
- All workflow actions broadcast in real-time
- Multiple clients stay in sync

### 20. **Responsive Design** ✅
- Mobile-friendly layout
- Sidebar navigation
- Adaptive grid layouts
- Touch-friendly buttons

---

## Technical Stack

**Backend**:
- Flask + Flask-CORS
- Flask-Sock (WebSocket support)
- TinyDB for activity storage
- Requests for inter-agent communication
- Threading for background polling

**Frontend**:
- Vanilla JavaScript (no framework)
- Chart.js for charts
- vis-network for topology graphs
- Font Awesome icons
- CSS Grid and Flexbox
- Web Audio API for sounds
- Notification API for desktop alerts

---

## API Endpoints Summary

### Configuration
- `GET /api/config/agents` - All agent configs
- `GET /api/config/agents/<name>` - Specific agent config
- `PUT /api/config/agents/<name>` - Update agent config
- `GET /api/config/ollama` - Ollama config
- `PUT /api/config/ollama` - Update Ollama config
- `POST /api/config/reload/<name>` - Reload agent config

### Workflow Management
- `GET /api/workflow/<id>/export` - Export workflow data
- `GET /api/workflow/<id>/export/json` - Download as file
- `GET /api/workflow/<id>/plan` - Get repair plan
- `GET /api/workflow/<id>/analysis` - Get analysis
- `POST /api/workflow/<id>/retry` - Retry workflow
- `GET /api/export/all` - Export all data

### Dashboard Data
- `GET /api/data` - All dashboard data
- `GET /api/activities?limit=N` - Activity feed
- `GET /api/workflows` - Workflows list
- `GET /api/workflows/detailed` - Detailed workflows
- `GET /api/agents` - Agent status

### WebSocket
- `ws://localhost:8085/ws/activities` - Real-time activity stream

---

## Key Improvements Made

1. ✅ **Fixed `os` import error** - Added `import os` to dashboard_server.py
2. ✅ **Configuration Management** - Full UI for editing Ollama settings
3. ✅ **Workflow Export** - Download complete workflow data as JSON
4. ✅ **Workflow Retry** - One-click retry for failed workflows
5. ✅ **Real-time Updates** - WebSocket for instant notifications
6. ✅ **Toast Popups** - Visual notifications for all events
7. ✅ **Sound Alerts** - Audio feedback for critical events
8. ✅ **Desktop Notifications** - Native browser notifications
9. ✅ **Activity Filtering** - Search and filter activity feed
10. ✅ **Auto-cleanup** - Old activities automatically removed

---

## What's Next (Future Enhancements)

### Phase 1 - Configuration Expansion
- [ ] Full agent configuration UI (Monitor, Analyzer, Planner)
- [ ] LLM prompt editor with version control
- [ ] Safety rules configuration (allowed/forbidden operations)
- [ ] Alert rules configuration

### Phase 2 - Workflow Management
- [ ] Plan approval/rejection interface
- [ ] Plan preview with code diff viewer
- [ ] Batch workflow operations (retry multiple at once)
- [ ] Workflow priority queue management

### Phase 3 - Advanced Analytics
- [ ] Root cause analytics dashboard
- [ ] Success rate trends over time
- [ ] Agent performance metrics
- [ ] Cost tracking (LLM API usage)
- [ ] Workflow success funnel

### Phase 4 - Knowledge Base
- [ ] Error pattern library editor
- [ ] Successful repairs history viewer
- [ ] Manual error/fix entry interface
- [ ] Pattern matching rule builder

### Phase 5 - Security & Audit
- [ ] Audit log viewer (all system actions)
- [ ] User role management (Admin/Operator/Viewer)
- [ ] Approval workflows for critical actions
- [ ] Session management and authentication

### Phase 6 - Advanced Features
- [ ] Slack/Email notification integration
- [ ] Custom webhooks for events
- [ ] Multi-workflow orchestration
- [ ] Workflow templates and presets
- [ ] MAPE-K loop performance optimization suggestions

---

## How to Use the Dashboard

### Starting the Dashboard
```bash
cd Dashboard
python dashboard_server.py
```
Access at: `http://localhost:8085`

### Changing Ollama Configuration
1. Navigate to Settings (⚙️ icon)
2. Click "Load Current Config"
3. Edit API Base URL (e.g., `http://localhost:11434`)
4. Edit Model Name (e.g., `llama3.3:70b`)
5. Select agents to update (Analyzer, Planner, or both)
6. Click "Save Configuration"
7. Restart agents to apply changes

### Exporting Workflow Data
1. Go to Workflows view
2. Find the workflow you want to export
3. Click "📥 Export" button
4. JSON file will download automatically

### Retrying Failed Workflow
1. Go to Workflows view
2. Find a failed workflow
3. Click "🔄 Retry" button
4. Confirm in dialog
5. Wait for pegasus-run to execute
6. See status in activity feed and toast popup

---

## Troubleshooting

### WebSocket Not Connecting
- Check if dashboard_server.py is running
- Check browser console for errors
- Verify no firewall blocking WebSocket connections

### Ollama Config Not Saving
- Check file permissions on config files
- Verify paths in dashboard_server.py are correct:
  - `ANALYZER_CONFIG_PATH = "../Analyzer/analyzer_config.json"`
  - `PLANNER_CONFIG_PATH = "../Planner/planner_config.json"`

### Workflow Retry Failing
- Verify `pegasus-run` is in system PATH
- Check workflow directory exists
- Check permissions to execute pegasus-run
- See error message in toast popup

### No Activities Showing
- Check if agents are running (Monitor, Analyzer, Planner)
- Verify agents are reachable at configured URLs
- Check background polling is active (console logs)

---

**Dashboard Version**: 2.0
**Last Updated**: 2025-01-30
**Status**: Production Ready ✅

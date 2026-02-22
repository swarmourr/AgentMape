# LLM Interaction Logging System - Complete Guide

## ✅ Architecture Overview

This system logs all LLM interactions with timestamps in each component's **existing database** and provides a centralized API through PegasusProvider for aggregation.

### Key Design Decisions

1. **No Common Directory** - Each component has its own logger integrated with existing DB
2. **Use Existing Databases** - `analyzer_agent_db.json` and `planner_db.json`
3. **PegasusProvider Aggregation** - Centralized API that collects from all sources
4. **Latest Interaction Handling** - When same workflow_id appears multiple times, returns most recent
5. **Timestamps on Everything** - ISO 8601 format with millisecond precision

---

## 📁 Files Created

```
AgentMape/
├── Analyzer/
│   ├── interaction_logger.py                    # NEW - Logger for Analyzer
│   ├── INTERACTION_INTEGRATION.md               # NEW - Integration guide
│   └── analyzer_agent_db.json                   # EXISTING - adds 'llm_interactions' table
│
├── Planner/
│   ├── interaction_logger.py                    # NEW - Logger for Planner
│   ├── INTERACTION_INTEGRATION.md               # NEW - Integration guide
│   └── planner_db.json                          # EXISTING - adds 'llm_interactions' table
│
└── PegasusProvider/
    ├── interaction_aggregator.py                # NEW - Aggregates from all sources
    └── INTERACTION_INTEGRATION.md               # NEW - Integration guide
```

---

## 🏗️ Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│           WEB DASHBOARD (Your existing)             │
│                 Port: 8000+                         │
└────────────────────┬────────────────────────────────┘
                     │
                     │ HTTP GET
                     ▼
┌─────────────────────────────────────────────────────┐
│         PEGASUS PROVIDER (Aggregator)               │
│                 Port: 8084                          │
│  ┌────────────────────────────────────────────┐    │
│  │  InteractionAggregator                     │    │
│  │  - get_workflow_conversation()             │    │
│  │  - get_latest_interaction_per_workflow()   │    │
│  │  - get_aggregated_statistics()             │    │
│  └────────────────────────────────────────────┘    │
└────────┬───────────────────────────────┬────────────┘
         │                               │
         │ Fetch                         │ Fetch
         ▼                               ▼
┌──────────────────────┐       ┌──────────────────────┐
│  ANALYZER AGENT      │       │  PLANNER AGENT       │
│  Port: 8081          │       │  Port: 8082          │
│                      │       │                      │
│  ┌────────────────┐ │       │  ┌────────────────┐ │
│  │ Interaction    │ │       │  │ Interaction    │ │
│  │ Logger         │ │       │  │ Logger         │ │
│  └────────┬───────┘ │       │  └────────┬───────┘ │
│           │         │       │           │         │
│           ▼         │       │           ▼         │
│  ┌────────────────┐ │       │  ┌────────────────┐ │
│  │ TinyDB         │ │       │  │ TinyDB         │ │
│  │ analyzer_      │ │       │  │ planner_       │ │
│  │ agent_db.json  │ │       │  │ db.json        │ │
│  │                │ │       │  │                │ │
│  │ Tables:        │ │       │  │ Tables:        │ │
│  │ - workflow_    │ │       │  │ - plans        │ │
│  │   analysis     │ │       │  │ - execution_   │ │
│  │ - failed_      │ │       │  │   requests     │ │
│  │   workflows    │ │       │  │ - agents       │ │
│  │ - llm_         │ │       │  │ - llm_         │ │
│  │   interactions │ │       │  │   interactions │ │
│  │   ★ NEW        │ │       │  │   ★ NEW        │ │
│  └────────────────┘ │       │  └────────────────┘ │
└──────────────────────┘       └──────────────────────┘
```

---

## 🚀 Quick Integration Steps

### 1. Analyzer Integration

```bash
cd /Users/hamzasafri/Desktop/AgentMape/Analyzer

# Follow INTERACTION_INTEGRATION.md:
# 1. Import AnalyzerInteractionLogger
# 2. Initialize in __init__: self.interaction_logger = AnalyzerInteractionLogger(self.db)
# 3. Add logging around LLM calls (lines 1250-1324)
# 4. Add API endpoints
```

### 2. Planner Integration

```bash
cd /Users/hamzasafri/Desktop/AgentMape/Planner

# Follow INTERACTION_INTEGRATION.md:
# 1. Import PlannerInteractionLogger
# 2. Initialize: interaction_logger = PlannerInteractionLogger(db)
# 3. Add logging in generate_plan_with_llm and generate_plan_multi_stage
# 4. Add API endpoints
```

### 3. PegasusProvider Aggregation

```bash
cd /Users/hamzasafri/Desktop/AgentMape/PegasusProvider

# Follow INTERACTION_INTEGRATION.md:
# 1. Import InteractionAggregator
# 2. Initialize in __init__
# 3. Add routes and handlers
```

---

## 📊 API Endpoints

### Component-Level APIs

#### Analyzer (Port 8081)
- `GET /api/analyzer/interactions/workflow/{workflow_id}` - Get Analyzer's interactions for workflow
- `GET /api/analyzer/interactions/latest?limit=50` - Get latest Analyzer interactions
- `GET /api/analyzer/interactions/statistics` - Get Analyzer statistics

#### Planner (Port 8082)
- `GET /api/planner/interactions/workflow/{workflow_id}` - Get Planner's interactions for workflow
- `GET /api/planner/interactions/latest?limit=50` - Get latest Planner interactions
- `GET /api/planner/interactions/statistics` - Get Planner statistics

### Aggregated API (PegasusProvider)

#### **🌟 Use These in Your Web Dashboard:**

**1. Get Complete Workflow Conversation**
```bash
GET http://localhost:8084/api/interactions/workflow/{workflow_id}
```
Returns all interactions from both Analyzer and Planner, sorted chronologically.

**2. Get Latest Interaction Per Workflow**
```bash
GET http://localhost:8084/api/interactions/latest?limit=50
```
**Important:** Returns only the LATEST interaction for each unique workflow_id.
If same workflow appears 10 times, returns only the most recent one.

**3. Get Combined Statistics**
```bash
GET http://localhost:8084/api/interactions/statistics
```
Returns aggregated statistics from both agents.

---

## 💾 Database Schema

### Analyzer: `analyzer_agent_db.json`

```json
{
  "workflow_analysis": {
    "_default": {...}  // Existing
  },
  "failed_workflows": {
    "_default": {...}  // Existing
  },
  "llm_interactions": {
    "1": {
      "interaction_id": "uuid-123",
      "timestamp": "2025-02-21T21:30:00.123456",
      "agent": "Analyzer",
      "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
      "analysis_type": "held",
      "direction": "request",
      "prompt": "Given the following Pegasus workflow logs...",
      "prompt_length": 1500,
      "metadata": {
        "attempt": 1,
        "max_retries": 3,
        "ollama_model": "llama3.3:latest"
      },
      "response": "Based on the logs, the workflow is held because...",
      "response_length": 850,
      "latency_ms": 1234.5,
      "success": true,
      "error": null,
      "completed_at": "2025-02-21T21:30:01.357956",
      "parsed_result": {
        "problems_and_solutions": [...],
        "confidence_score": 0.85
      }
    }
  }
}
```

### Planner: `planner_db.json`

```json
{
  "plans": {
    "_default": {...}  // Existing
  },
  "execution_requests": {
    "_default": {...}  // Existing
  },
  "agents": {
    "_default": {...}  // Existing
  },
  "llm_interactions": {
    "1": {
      "interaction_id": "uuid-456",
      "parent_interaction_id": null,
      "timestamp": "2025-02-21T21:35:00.123456",
      "agent": "Planner",
      "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
      "stage": "single_stage",
      "direction": "request",
      "prompt": "Generate a repair plan for...",
      "prompt_length": 2000,
      "metadata": {
        "additional_files_count": 3,
        "catalogs_provided": ["replica", "transformation", "site"]
      },
      "response": "Here is the repair plan...",
      "response_length": 1200,
      "latency_ms": 2345.6,
      "success": true,
      "error": null,
      "completed_at": "2025-02-21T21:35:02.468912",
      "parsed_plan": {
        "plan_id": "plan-789",
        "actions_count": 5,
        "validation_passed": true
      }
    },
    "2": {
      "interaction_id": "uuid-789",
      "parent_interaction_id": "uuid-456",  // Links to parent (stage 1)
      "timestamp": "2025-02-21T21:36:00.000000",
      "agent": "Planner",
      "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
      "stage": "stage2_plan_generation",
      "direction": "request",
      ...
    }
  }
}
```

---

## 🔑 Key Features

### 1. Duplicate Workflow ID Handling

**Problem:** Same workflow might be analyzed multiple times (retry, re-run, etc.)

**Solution:**
- Component APIs return ALL interactions
- Aggregator API returns ONLY the latest per workflow when using `/latest` endpoint
- Full conversation endpoint returns ALL in chronological order

**Example:**
```javascript
// Get all interactions for workflow (including retries)
const all = await fetch('/api/interactions/workflow/workflow-123');
// Returns 10 interactions (e.g., 3 Analyzer attempts + 7 Planner stages)

// Get only latest interaction per workflow
const latest = await fetch('/api/interactions/latest?limit=50');
// Returns 1 interaction per unique workflow_id (the most recent)
```

### 2. Timestamps

All timestamps in ISO 8601 format with timezone:
- `timestamp`: When request was made
- `completed_at`: When response was received
- `latency_ms`: Time between request and response

### 3. Multi-Stage Tracking

Planner's multi-stage interactions are linked via `parent_interaction_id`:

```json
{
  "interaction_id": "stage1-id",
  "parent_interaction_id": null,
  "stage": "stage1_file_identification"
}
{
  "interaction_id": "stage2-id",
  "parent_interaction_id": "stage1-id",  // Links to stage 1
  "stage": "stage2_plan_generation"
}
```

### 4. Chat Message Format

API returns messages in chat-ready format:
- `role`: "user" (request to LLM), "assistant" (response from LLM), "system" (agent action)
- `agent`: "Analyzer", "Planner", or "LLM"
- `content`: The actual prompt or response text
- `metadata`: Additional context

---

## 🧪 Testing

### Test Each Component

```bash
# 1. Start all services
cd Analyzer && python3 analyzer_rest.py &
cd Planner && python3 planner_rest.py &
cd PegasusProvider && python3 pegasus_provider_service.py &

# 2. Process a real workflow (generates interactions)
# ... your normal workflow processing ...

# 3. Test Analyzer API
curl http://localhost:8081/api/analyzer/interactions/statistics
curl http://localhost:8081/api/analyzer/interactions/latest?limit=5

# 4. Test Planner API
curl http://localhost:8082/api/planner/interactions/statistics
curl http://localhost:8082/api/planner/interactions/latest?limit=5

# 5. Test PegasusProvider Aggregation
curl http://localhost:8084/api/interactions/statistics
curl http://localhost:8084/api/interactions/latest?limit=10
curl http://localhost:8084/api/interactions/workflow/YOUR_WORKFLOW_ID

# 6. Check databases
cat Analyzer/analyzer_agent_db.json | jq '.llm_interactions'
cat Planner/planner_db.json | jq '.llm_interactions'
```

---

## 🌐 Web Dashboard Integration

### Use PegasusProvider Endpoints

```javascript
// In your web dashboard JavaScript

const PROVIDER_URL = 'http://localhost:8084';

// 1. Get workflow conversation for chat display
async function loadWorkflowChat(workflowId) {
    const response = await fetch(`${PROVIDER_URL}/api/interactions/workflow/${workflowId}`);
    const data = await response.json();

    if (data.success) {
        // data.messages = [{role, agent, content, timestamp, ...}, ...]
        renderChatMessages(data.messages);
    }
}

// 2. Get latest interactions (one per workflow)
async function loadRecentWorkflows() {
    const response = await fetch(`${PROVIDER_URL}/api/interactions/latest?limit=20`);
    const data = await response.json();

    if (data.success) {
        // data.latest_interactions = one entry per unique workflow_id
        renderWorkflowList(data.latest_interactions);
    }
}

// 3. Get statistics
async function loadStats() {
    const response = await fetch(`${PROVIDER_URL}/api/interactions/statistics`);
    const data = await response.json();

    if (data.success) {
        displayStats(data.statistics);
    }
}
```

### Chat UI Example

```html
<div class="chat-messages">
    <!-- Rendered from data.messages -->
    <div class="message user">
        <div class="agent-badge">Analyzer</div>
        <div class="timestamp">2025-02-21 10:30:00</div>
        <div class="content">Given the following Pegasus workflow logs...</div>
    </div>

    <div class="message assistant">
        <div class="agent-badge">LLM</div>
        <div class="timestamp">2025-02-21 10:30:01</div>
        <div class="latency">⏱️ 1234ms</div>
        <div class="content">Based on the logs, the workflow is held because...</div>
    </div>

    <div class="message user">
        <div class="agent-badge">Planner</div>
        <div class="timestamp">2025-02-21 10:32:00</div>
        <div class="content">Generate a repair plan for...</div>
    </div>
</div>
```

---

## ✅ Benefits

1. **No Common Directory** - Each component manages its own logging
2. **Existing Databases** - No new database files, uses existing TinyDB instances
3. **Centralized Access** - PegasusProvider aggregates everything
4. **Latest Interaction** - Smart handling of duplicate workflow IDs
5. **Timestamps** - Complete timeline of all LLM interactions
6. **Multi-Stage Tracking** - Links related interactions
7. **API Ready** - REST endpoints for web dashboard
8. **Minimal Changes** - Small additions to existing code

---

## 📝 Summary

✅ **Analyzer** - Logs interactions to `analyzer_agent_db.json` (llm_interactions table)
✅ **Planner** - Logs interactions to `planner_db.json` (llm_interactions table)
✅ **PegasusProvider** - Aggregates from both, handles duplicates, provides unified API
✅ **Web Dashboard** - Uses PegasusProvider endpoints for chat UI

**Use this URL in your dashboard:**
```
http://localhost:8084/api/interactions/workflow/{workflow_id}
```

---

## 📚 Integration Guides

- **Analyzer:** See `Analyzer/INTERACTION_INTEGRATION.md`
- **Planner:** See `Planner/INTERACTION_INTEGRATION.md`
- **PegasusProvider:** See `PegasusProvider/INTERACTION_INTEGRATION.md`

**Start with one component, test it, then move to the next!**

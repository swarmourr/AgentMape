# PegasusProvider - LLM Interaction Aggregation

## Overview

The PegasusProvider acts as the central aggregation point for LLM interactions from both Analyzer and Planner. It provides a unified API for the web dashboard and handles duplicate workflow IDs by returning the latest interaction.

## Step 1: Import the Aggregator

**File:** `PegasusProvider/pegasus_provider_service.py`

**At the top (around line 30-31, after other imports):**
```python
from interaction_aggregator import InteractionAggregator
```

## Step 2: Initialize in the Class

**File:** `PegasusProvider/pegasus_provider_service.py`

**In `__init__` method (around line 48-66), add:**

```python
def __init__(self):
    self.executor = PegasusCommandExecutor(timeout=30)
    self.app = web.Application(middlewares=[self.cors_middleware])

    # ADD THIS:
    self.interaction_aggregator = InteractionAggregator(
        analyzer_url=os.getenv("ANALYZER_URL", "http://localhost:8081"),
        planner_url=os.getenv("PLANNER_URL", "http://localhost:8082")
    )

    self.setup_routes()
    self.service_info = {
        # ... existing code ...
    }
```

## Step 3: Add Routes

**File:** `PegasusProvider/pegasus_provider_service.py`

**In `setup_routes` method (around line 90-107), add:**

```python
def setup_routes(self):
    """Setup HTTP routes - CORS handled by middleware"""

    # Define all routes
    routes = [
        ('GET', '/health', self.handle_health),
        ('GET', '/api/info', self.handle_service_info),
        ('GET', '/api/workflows/{workflow_id}/status', self.handle_status),
        ('GET', '/api/workflows/{workflow_id}/analyzer', self.handle_analyzer),
        ('GET', '/api/workflows/{workflow_id}/statistics', self.handle_statistics),
        ('GET', '/api/workflows/{workflow_id}/full', self.handle_full_analysis),
        ('GET', '/api/workflows/{workflow_id}/jobs', self.handle_jobs),
        ('GET', '/api/workflows/{workflow_id}/dag', self.handle_dag),
        ('POST', '/api/workflows/{workflow_id}/rerun', self.handle_rerun_workflow),
        ('POST', '/api/workflows/batch', self.handle_batch_query),
        ('DELETE', '/api/cache', self.handle_clear_cache),
        ('GET', '/api/cache/stats', self.handle_cache_stats),

        # ADD THESE NEW ROUTES:
        ('GET', '/api/interactions/workflow/{workflow_id}', self.handle_workflow_conversation),
        ('GET', '/api/interactions/latest', self.handle_latest_interactions),
        ('GET', '/api/interactions/statistics', self.handle_interaction_statistics),
    ]

    # Add routes
    for method, path, handler in routes:
        self.app.router.add_route(method, path, handler)
```

## Step 4: Add Handler Methods

**File:** `PegasusProvider/pegasus_provider_service.py`

**Add these methods to the PegasusProviderService class:**

```python
async def handle_workflow_conversation(self, request):
    """
    GET /api/interactions/workflow/{workflow_id}
    Get complete conversation for a workflow from both Analyzer and Planner
    Handles duplicate workflow IDs by grouping all interactions chronologically
    """
    try:
        workflow_id = request.match_info['workflow_id']
        logger.info(f"Fetching conversation for workflow: {workflow_id}")

        result = await self.interaction_aggregator.get_workflow_conversation(workflow_id)

        return web.json_response(result)

    except Exception as e:
        logger.error(f"Error getting workflow conversation: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def handle_latest_interactions(self, request):
    """
    GET /api/interactions/latest?limit=50
    Get latest interaction per unique workflow
    Important: Returns only ONE interaction per workflow_id (the most recent)
    """
    try:
        limit = int(request.query.get('limit', 50))
        logger.info(f"Fetching latest interactions (limit: {limit})")

        result = await self.interaction_aggregator.get_latest_interaction_per_workflow(limit)

        return web.json_response(result)

    except Exception as e:
        logger.error(f"Error getting latest interactions: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def handle_interaction_statistics(self, request):
    """
    GET /api/interactions/statistics
    Get aggregated statistics from both Analyzer and Planner
    """
    try:
        logger.info("Fetching aggregated interaction statistics")

        result = await self.interaction_aggregator.get_aggregated_statistics()

        return web.json_response(result)

    except Exception as e:
        logger.error(f"Error getting interaction statistics: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)
```

## API Endpoints

Once integrated, PegasusProvider will expose these new endpoints:

### 1. Get Workflow Conversation

```bash
GET http://localhost:8084/api/interactions/workflow/{workflow_id}
```

**Response:**
```json
{
  "success": true,
  "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
  "message_count": 15,
  "analyzer_count": 8,
  "planner_count": 7,
  "timeline": {
    "first_timestamp": "2025-02-21T10:30:00.123456",
    "last_timestamp": "2025-02-21T10:35:45.789012"
  },
  "messages": [
    {
      "id": "uuid-1",
      "timestamp": "2025-02-21T10:30:00.123456",
      "role": "user",
      "agent": "Analyzer",
      "type": "held",
      "content": "Given the following Pegasus workflow logs...",
      "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
      "has_response": true,
      "success": true,
      "latency_ms": 1234.5
    },
    {
      "id": "uuid-1",
      "timestamp": "2025-02-21T10:30:01.357956",
      "role": "assistant",
      "agent": "LLM",
      "type": "held",
      "content": "Based on the logs, the workflow is held because...",
      "success": true,
      "latency_ms": 1234.5,
      "parsed_data": {...}
    },
    {
      "id": "uuid-2",
      "timestamp": "2025-02-21T10:32:00.000000",
      "role": "user",
      "agent": "Planner",
      "type": "single_stage",
      "content": "Generate a repair plan...",
      ...
    }
  ]
}
```

### 2. Get Latest Interactions Per Workflow

**Important:** Returns only the LATEST interaction for each unique workflow_id.

```bash
GET http://localhost:8084/api/interactions/latest?limit=50
```

**Response:**
```json
{
  "success": true,
  "count": 23,
  "unique_workflows": 23,
  "latest_interactions": [
    {
      "interaction_id": "uuid-latest",
      "timestamp": "2025-02-21T11:00:00.000000",
      "agent": "Planner",
      "workflow_id": "workflow-A",
      "stage": "stage2_plan_generation",
      "success": true,
      "latency_ms": 2345.6,
      ...
    },
    {
      "interaction_id": "uuid-latest-2",
      "timestamp": "2025-02-21T10:55:00.000000",
      "agent": "Analyzer",
      "workflow_id": "workflow-B",
      "analysis_type": "held",
      "success": true,
      "latency_ms": 1234.5,
      ...
    }
  ]
}
```

### 3. Get Aggregated Statistics

```bash
GET http://localhost:8084/api/interactions/statistics
```

**Response:**
```json
{
  "success": true,
  "statistics": {
    "total_interactions": 156,
    "successful": 142,
    "failed": 14,
    "success_rate": 91.03,
    "average_latency_ms": 1567.89,
    "by_agent": {
      "Analyzer": 78,
      "Planner": 78
    },
    "unique_workflows": 45,
    "analyzer_details": {
      "agent": "Analyzer",
      "total_interactions": 78,
      "successful": 71,
      "failed": 7,
      "success_rate": 91.03,
      "average_latency_ms": 1234.5,
      "by_type": {
        "held": 45,
        "failed": 33
      },
      "unique_workflows": 45
    },
    "planner_details": {
      "agent": "Planner",
      "total_interactions": 78,
      "successful": 71,
      "failed": 7,
      "success_rate": 91.03,
      "average_latency_ms": 1900.28,
      "by_stage": {
        "single_stage": 50,
        "stage1_file_identification": 14,
        "stage2_plan_generation": 14
      },
      "unique_workflows": 45
    }
  }
}
```

## Testing

```bash
# Start PegasusProvider
cd /Users/hamzasafri/Desktop/AgentMape/PegasusProvider
python3 pegasus_provider_service.py

# Test endpoints:

# Get aggregated statistics
curl http://localhost:8084/api/interactions/statistics

# Get latest interactions per workflow (only 1 per workflow_id)
curl http://localhost:8084/api/interactions/latest?limit=20

# Get full conversation for a specific workflow
curl http://localhost:8084/api/interactions/workflow/4ddc0377-0222-447e-a6d4-5e83c8474dea
```

## Key Features

✅ **Centralized Aggregation** - Single endpoint for all interactions
✅ **Duplicate Handling** - Returns latest interaction when same workflow_id appears multiple times
✅ **Cross-Agent Timeline** - Chronological view of Analyzer → Planner flow
✅ **Unified Statistics** - Combined metrics from both agents
✅ **Chat Format** - Pre-formatted for web dashboard display
✅ **CORS Support** - Works with web dashboards via existing middleware

## Environment Variables

Optionally set agent URLs (defaults shown):

```bash
export ANALYZER_URL="http://localhost:8081"
export PLANNER_URL="http://localhost:8082"
export PEGASUS_PROVIDER_PORT="8084"
```

## Architecture Flow

```
Web Dashboard
     |
     | GET /api/interactions/workflow/XYZ
     ▼
PegasusProvider:8084 (Aggregator)
     |
     ├──> Analyzer:8081/api/analyzer/interactions/workflow/XYZ
     |     └─> analyzer_agent_db.json (llm_interactions table)
     |
     └──> Planner:8082/api/planner/interactions/workflow/XYZ
           └─> planner_db.json (llm_interactions table)
     |
     ▼
Merged, sorted, formatted response
     |
     ▼
Web Dashboard (Chat UI)
```

## Integration with Existing Dashboard

In your web dashboard JavaScript, use the PegasusProvider endpoints:

```javascript
// Fetch conversation for workflow
const workflowId = '4ddc0377-0222-447e-a6d4-5e83c8474dea';

const response = await fetch(`http://localhost:8084/api/interactions/workflow/${workflowId}`);
const data = await response.json();

if (data.success) {
    // data.messages contains chronological chat messages from both agents
    renderChatMessages(data.messages);
}

// Fetch latest interactions (one per workflow)
const latest = await fetch('http://localhost:8084/api/interactions/latest?limit=50');
const latestData = await latest.json();

if (latestData.success) {
    // latestData.latest_interactions contains one entry per unique workflow_id
    renderWorkflowList(latestData.latest_interactions);
}

// Fetch statistics
const stats = await fetch('http://localhost:8084/api/interactions/statistics');
const statsData = await stats.json();

if (statsData.success) {
    displayStatistics(statsData.statistics);
}
```

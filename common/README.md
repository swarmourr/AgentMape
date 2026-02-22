# LLM Interaction Logging System

A centralized system for logging all LLM and agent interactions with timestamps, stored in TinyDB, and accessible via REST API for web dashboard chat interface.

## Components

### 1. `interaction_logger.py`
Core logging functionality using TinyDB. Logs all LLM requests, responses, and agent actions with timestamps.

### 2. `interaction_api.py`
REST API endpoints for accessing logged interactions. Designed for web dashboard integration.

### 3. `analyzer_logger_integration.py`
Integration helper for the Analyzer agent. Provides mixin class and usage examples.

### 4. `planner_logger_integration.py`
Integration helper for the Planner agent. Provides mixin class and usage examples.

## Quick Start

### Step 1: Add to Analyzer Agent

In `Analyzer/analyzer_rest.py`:

```python
# Add import at top
from common.analyzer_logger_integration import AnalyzerLoggerMixin

# Modify class declaration (line 698)
class EnhancedAnalyzerAgent(AnalyzerLoggerMixin):
    def __init__(self, mcp_port: int = 8766, http_port: int = 8081, config_file: str = "analyzer_config.json"):
        # ... existing init code ...

        # Add this line after other initializations (around line 783)
        self.__init_interaction_logger__()
```

In the LLM calling code (around line 1250-1324):

```python
import time

# Before LLM call
interaction_id = self._log_llm_analysis_request(
    workflow_id=workflow_id,
    analysis_type="held",  # or "failed"
    prompt=prompt,
    metadata={"attempt": attempt + 1}
)

start_time = time.time()

# Your existing LLM call
response = requests.post(...)

latency_ms = (time.time() - start_time) * 1000

# After successful response
if response.status_code == 200:
    ollama_response = response.json()
    response_text = ollama_response.get('response', '').strip()
    parsed_result = self.extract_workflow_info_enhanced(ollama_response)

    self._log_llm_analysis_response(
        interaction_id=interaction_id,
        response=response_text,
        success=True,
        latency_ms=latency_ms,
        parsed_result=parsed_result
    )
else:
    self._log_llm_analysis_response(
        interaction_id=interaction_id,
        response=None,
        success=False,
        latency_ms=latency_ms,
        error=f"HTTP {response.status_code}"
    )
```

### Step 2: Add to Planner Agent

In `Planner/planner_rest.py`:

```python
# Add import at top
from common.planner_logger_integration import PlannerLoggerMixin

# Find your PlannerAgent class and add the mixin
class PlannerAgent(PlannerLoggerMixin):
    def __init__(self, ...):
        # ... existing init code ...

        # Add this line
        self.__init_interaction_logger__()
```

In the plan generation code (around line 1265):

```python
import time

# Build prompt
prompt = self.prompt_builder.build_planner_prompt(analysis_result, catalogs, workflow_context)

# LOG REQUEST
interaction_id = self._log_llm_plan_request(
    workflow_id=workflow_id,
    stage="single_stage",
    prompt=prompt,
    metadata={"additional_files_count": len(additional_files) if additional_files else 0}
)

# Call LLM
start_time = time.time()
llm_response = self.ollama_manager.call_llm(prompt, self.prompt_builder.SYSTEM_PROMPT)
latency_ms = (time.time() - start_time) * 1000

if llm_response:
    try:
        plan = self.parse_llm_response(llm_response)

        # LOG SUCCESS
        self._log_llm_plan_response(
            interaction_id=interaction_id,
            response=str(llm_response),
            success=True,
            latency_ms=latency_ms,
            parsed_plan=plan
        )

        return plan
    except Exception as e:
        # LOG FAILURE
        self._log_llm_plan_response(
            interaction_id=interaction_id,
            response=str(llm_response),
            success=False,
            latency_ms=latency_ms,
            error=str(e)
        )
        raise
```

### Step 3: Add API Endpoints

You have two options:

**Option A: Add to existing Dashboard server** (`Dashboard/dashboard_server.py`):

```python
from common.interaction_api import setup_interaction_api

# In your app initialization
app = web.Application()
setup_interaction_api(app)  # Add this line
# ... rest of your routes ...
```

**Option B: Add to Analyzer server** (`Analyzer/analyzer_rest.py`):

```python
from common.interaction_api import setup_interaction_api

# In EnhancedAnalyzerAgent.setup_http_routes() method (around line 777)
def setup_http_routes(self):
    # ... existing routes ...

    # Add interaction API
    from common.interaction_api import setup_interaction_api
    setup_interaction_api(self.app)
```

**Option C: Add to Planner server** (`Planner/planner_rest.py`):

```python
from common.interaction_api import setup_interaction_api

# In the main() function or wherever you setup routes
app = web.Application()
setup_interaction_api(app)
# ... rest of your routes ...
```

## API Endpoints

Once integrated, you'll have these endpoints available:

### Get Workflow Conversation (Chat Format)
```bash
GET /api/interactions/workflow/{workflow_id}?include_actions=true
```

**Example:**
```bash
curl http://localhost:8081/api/interactions/workflow/4ddc0377-0222-447e-a6d4-5e83c8474dea
```

**Response:**
```json
{
  "success": true,
  "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
  "message_count": 8,
  "messages": [
    {
      "id": "uuid-1",
      "timestamp": "2025-02-21T10:30:00Z",
      "role": "user",
      "agent": "Analyzer",
      "type": "workflow_analysis_held",
      "content": "Given the following Pegasus workflow...",
      "metadata": {...},
      "has_response": true,
      "success": true,
      "latency_ms": 1200
    },
    {
      "id": "uuid-1",
      "timestamp": "2025-02-21T10:30:01.200Z",
      "role": "assistant",
      "agent": "LLM",
      "type": "workflow_analysis_held",
      "content": "Based on the logs, the workflow is held because...",
      "metadata": {...},
      "parsed_data": {...}
    },
    {
      "id": "uuid-2",
      "timestamp": "2025-02-21T10:30:05Z",
      "role": "user",
      "agent": "Planner",
      "type": "plan_generation_single_stage",
      "content": "Generate a repair plan for...",
      ...
    }
  ]
}
```

### Get Latest Interactions
```bash
GET /api/interactions/latest?limit=50&agent=Analyzer&type=workflow_analysis_held
```

### Get All Conversations
```bash
GET /api/interactions/conversations?limit=100&offset=0
```

### Get Statistics
```bash
GET /api/interactions/statistics
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
    "by_agent": {
      "Analyzer": 78,
      "Planner": 78
    },
    "by_type": {
      "workflow_analysis_held": 45,
      "plan_generation_single_stage": 33,
      ...
    },
    "average_latency_ms": 1234.56,
    "unique_workflows": 23
  }
}
```

### Get Specific Interaction
```bash
GET /api/interactions/{interaction_id}
```

### Clear Old Interactions
```bash
POST /api/interactions/clear-old
Content-Type: application/json

{"days": 30}
```

## Database Structure

All interactions are stored in `logs/interaction_logs.json`:

```json
{
  "llm_interactions": {
    "1": {
      "interaction_id": "uuid-123",
      "parent_interaction_id": null,
      "timestamp": "2025-02-21T10:30:00.123456Z",
      "agent": "Analyzer",
      "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
      "interaction_type": "workflow_analysis_held",
      "direction": "request",
      "prompt": "Given the following Pegasus workflow logs...",
      "prompt_length": 1500,
      "metadata": {
        "analysis_type": "held",
        "ollama_model": "llama3.3:latest",
        "attempt": 1
      },
      "response": "Based on the logs, the workflow is held because...",
      "response_length": 850,
      "latency_ms": 1200.5,
      "success": true,
      "error": null,
      "completed_at": "2025-02-21T10:30:01.323456Z",
      "parsed_data": {
        "problems_and_solutions": [...]
      }
    }
  }
}
```

## Web Dashboard Integration

### JavaScript Example

```javascript
// Fetch conversation for a workflow
async function loadWorkflowConversation(workflowId) {
    const response = await fetch(`/api/interactions/workflow/${workflowId}`);
    const data = await response.json();

    if (data.success) {
        renderChatMessages(data.messages);
    }
}

// Render as chat messages
function renderChatMessages(messages) {
    const chatContainer = document.getElementById('chat-container');
    chatContainer.innerHTML = '';

    messages.forEach(msg => {
        const div = document.createElement('div');
        div.className = `chat-message ${msg.role}`;

        const timestamp = new Date(msg.timestamp).toLocaleString();

        div.innerHTML = `
            <div class="message-header">
                <strong>${msg.agent}</strong>
                <span class="timestamp">${timestamp}</span>
            </div>
            <div class="message-content">${formatContent(msg.content)}</div>
            ${msg.latency_ms ? `<div class="latency">⏱️ ${msg.latency_ms}ms</div>` : ''}
        `;

        chatContainer.appendChild(div);
    });
}

function formatContent(content) {
    // Truncate long prompts/responses
    if (content.length > 500) {
        return `<div class="truncated">${content.substring(0, 500)}... <button onclick="showFull(this)">Show More</button></div>`;
    }
    return content;
}
```

### CSS Example

```css
.chat-message {
    margin: 10px 0;
    padding: 10px;
    border-radius: 8px;
}

.chat-message.user {
    background-color: #e3f2fd;
    margin-right: 20%;
}

.chat-message.assistant {
    background-color: #f5f5f5;
    margin-left: 20%;
}

.chat-message.system {
    background-color: #fff3e0;
    font-style: italic;
}

.message-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 5px;
    font-size: 0.9em;
}

.timestamp {
    color: #666;
}

.latency {
    font-size: 0.8em;
    color: #999;
    margin-top: 5px;
}
```

## Testing

```bash
# Test the logger directly
python3 -c "
from common.interaction_logger import get_interaction_logger

logger = get_interaction_logger()

# Log a test interaction
iid = logger.log_llm_request(
    agent='Analyzer',
    interaction_type='test',
    prompt='Test prompt',
    workflow_id='test-123'
)

logger.log_llm_response(
    interaction_id=iid,
    response='Test response',
    success=True,
    latency_ms=100.5
)

# Get statistics
stats = logger.get_statistics()
print(stats)
"
```

## File Locations

- **Logger**: `common/interaction_logger.py`
- **API**: `common/interaction_api.py`
- **Analyzer Integration**: `common/analyzer_logger_integration.py`
- **Planner Integration**: `common/planner_logger_integration.py`
- **Database**: `logs/interaction_logs.json` (auto-created)
- **Log Files**: `analyzer_agent.log`, etc. (existing)

## Benefits

✅ **Centralized logging** - All LLM interactions in one place
✅ **Automatic timestamps** - ISO format with millisecond precision
✅ **Chat-style format** - Ready for web dashboard display
✅ **API accessible** - REST endpoints for easy integration
✅ **TinyDB storage** - Lightweight, no database server needed
✅ **Multi-stage tracking** - Links related interactions via parent_id
✅ **Performance metrics** - Latency tracking for all LLM calls
✅ **Rich metadata** - Capture context, attempts, errors, etc.
✅ **Easy querying** - Filter by workflow, agent, type, time
✅ **Minimal code changes** - Mixin pattern for easy integration

## Next Steps

1. Integrate into Analyzer agent
2. Integrate into Planner agent
3. Add API endpoints to your web server
4. Update dashboard to display chat interface
5. Test with real workflows

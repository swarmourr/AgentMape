# Quick Integration Guide

## Complete Implementation with TinyDB + API Access

I've created a complete LLM interaction logging system for your AgentMape project. Here's what's been created:

### 📁 Files Created

```
AgentMape/
├── common/
│   ├── interaction_logger.py              # Core logging with TinyDB
│   ├── interaction_api.py                  # REST API endpoints
│   ├── analyzer_logger_integration.py      # Analyzer integration helper
│   ├── planner_logger_integration.py       # Planner integration helper
│   ├── chat_interface_example.html         # Web chat UI example
│   ├── README.md                           # Full documentation
│   └── INTEGRATION_GUIDE.md               # This file
└── logs/
    └── interaction_logs.json               # Auto-created TinyDB database
```

---

## 🚀 3-Step Integration

### Step 1: Integrate into Analyzer Agent

**File:** `Analyzer/analyzer_rest.py`

**At line 1 (imports):**
```python
from common.analyzer_logger_integration import AnalyzerLoggerMixin
import time  # If not already imported
```

**At line 698 (class declaration):**
```python
# BEFORE:
class EnhancedAnalyzerAgent:

# AFTER:
class EnhancedAnalyzerAgent(AnalyzerLoggerMixin):
```

**At line ~783 (in __init__ method, after all other initializations):**
```python
# Add this line
self.__init_interaction_logger__()
```

**At lines 1256-1284 (in the LLM calling code):**
```python
# FIND THIS SECTION (around line 1256):
for attempt in range(max_retries):
    try:
        self.logger.info(f"LLM request attempt {attempt + 1}/{max_retries}")

        # ADD THIS BEFORE THE REQUEST:
        interaction_id = self._log_llm_analysis_request(
            workflow_id=workflow_id,
            analysis_type=analysis_type,  # "held" or "failed"
            prompt=prompt,
            metadata={"attempt": attempt + 1, "max_retries": max_retries}
        )

        start_time = time.time()

        response = requests.post(
            self.ollama_manager.ollama_url,
            json=payload,
            timeout=generation_timeout,
            headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
        )

        latency_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            ollama_response = response.json()
            response_text = ollama_response.get('response', '').strip()

            # ... your existing parsing code ...
            parsed_result = self.extract_workflow_info_enhanced(ollama_response)

            # ADD THIS AFTER SUCCESSFUL PARSE:
            self._log_llm_analysis_response(
                interaction_id=interaction_id,
                response=response_text,
                success=True,
                latency_ms=latency_ms,
                parsed_result=parsed_result
            )

            # Update connection status on success
            self.ollama_manager.is_healthy = True
            # ... rest of your code ...
        else:
            # ADD THIS IN ERROR CASE:
            self._log_llm_analysis_response(
                interaction_id=interaction_id,
                response=None,
                success=False,
                latency_ms=latency_ms,
                error=f"HTTP {response.status_code}"
            )
```

### Step 2: Integrate into Planner Agent

**File:** `Planner/planner_rest.py`

**At line 1 (imports):**
```python
from common.planner_logger_integration import PlannerLoggerMixin
import time  # If not already imported
```

**Find your PlannerAgent class and add mixin:**
```python
class PlannerAgent(PlannerLoggerMixin):
    def __init__(self, ...):
        # Your existing init code
        ...
        # Add this line
        self.__init_interaction_logger__()
```

**At line ~1265 (in generate_plan_with_llm method):**
```python
# Build prompt
prompt = self.prompt_builder.build_planner_prompt(analysis_result, catalogs, workflow_context)

# ADD THIS:
interaction_id = self._log_llm_plan_request(
    workflow_id=workflow_id,
    stage="single_stage",
    prompt=prompt,
    metadata={
        "additional_files_count": len(additional_files) if additional_files else 0,
        "catalogs_provided": list(catalogs.keys())
    }
)

# Call LLM
start_time = time.time()
llm_response = self.ollama_manager.call_llm(prompt, self.prompt_builder.SYSTEM_PROMPT)
latency_ms = (time.time() - start_time) * 1000

if llm_response:
    try:
        # Parse LLM output
        plan = self.parse_llm_response(llm_response)

        # ADD THIS:
        self._log_llm_plan_response(
            interaction_id=interaction_id,
            response=str(llm_response),
            success=True,
            latency_ms=latency_ms,
            parsed_plan=plan
        )

        # ... rest of your code ...
        return plan

    except Exception as e:
        logger.error(f"Error parsing LLM response: {e}")

        # ADD THIS:
        self._log_llm_plan_response(
            interaction_id=interaction_id,
            response=str(llm_response),
            success=False,
            latency_ms=latency_ms,
            error=str(e)
        )

        return self.generate_fallback_plan(analysis_result, workflow_context)
else:
    # ADD THIS:
    self._log_llm_plan_response(
        interaction_id=interaction_id,
        response=None,
        success=False,
        latency_ms=latency_ms,
        error="LLM not available"
    )
```

### Step 3: Add API Endpoints

**Option A: Add to Dashboard Server** (Recommended)

**File:** `Dashboard/dashboard_server.py`

```python
# At the top, add import
from common.interaction_api import setup_interaction_api

# In your app initialization (find where you create web.Application())
app = web.Application()

# Add this line RIGHT AFTER creating the app
setup_interaction_api(app)

# ... rest of your routes ...
```

**Option B: Add to Analyzer Server**

**File:** `Analyzer/analyzer_rest.py`

In the `setup_http_routes` method (around line 777):
```python
def setup_http_routes(self):
    # ... existing routes ...

    # Add this
    from common.interaction_api import setup_interaction_api
    setup_interaction_api(self.app)
```

---

## 🧪 Testing

### Test 1: Verify Logger Works

```bash
cd /Users/hamzasafri/Desktop/AgentMape

python3 -c "
from common.interaction_logger import get_interaction_logger

logger = get_interaction_logger()

# Log a test interaction
iid = logger.log_llm_request(
    agent='Analyzer',
    interaction_type='test',
    prompt='Test prompt for workflow analysis',
    workflow_id='test-workflow-123',
    metadata={'test': True}
)

logger.log_llm_response(
    interaction_id=iid,
    response='Test response from LLM',
    success=True,
    latency_ms=100.5
)

# Get statistics
stats = logger.get_statistics()
print('Statistics:', stats)

# Get the conversation
conv = logger.get_workflow_conversation('test-workflow-123')
print('Messages:', len(conv))
"
```

### Test 2: Check Database Created

```bash
cat logs/interaction_logs.json
```

You should see JSON with your test interaction!

### Test 3: Test API Endpoints

Start your server (Analyzer or Dashboard), then:

```bash
# Get statistics
curl http://localhost:8081/api/interactions/statistics

# Get test workflow conversation
curl http://localhost:8081/api/interactions/workflow/test-workflow-123

# Get latest interactions
curl http://localhost:8081/api/interactions/latest?limit=10
```

### Test 4: View in Browser

1. Open the chat interface:
```bash
# If using Python's http.server
cd /Users/hamzasafri/Desktop/AgentMape/common
python3 -m http.server 9000

# Then open: http://localhost:9000/chat_interface_example.html
```

2. Update the `API_BASE` in the HTML file if your API is on a different port:
```javascript
// Line 241 in chat_interface_example.html
const API_BASE = 'http://localhost:8081'; // Change to your API port
```

---

## 📊 API Endpoints Reference

Once integrated, you'll have these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/interactions/workflow/{workflow_id}` | GET | Get all interactions for a workflow (chat format) |
| `/api/interactions/latest` | GET | Get latest interactions (supports filters) |
| `/api/interactions/conversations` | GET | Get all conversations grouped by workflow |
| `/api/interactions/statistics` | GET | Get statistics about interactions |
| `/api/interactions/{interaction_id}` | GET | Get specific interaction by ID |
| `/api/interactions/clear-old` | POST | Clear old interactions (cleanup) |

### Example API Calls from JavaScript

```javascript
// Get workflow conversation for chat display
fetch('/api/interactions/workflow/4ddc0377-0222-447e-a6d4-5e83c8474dea')
  .then(r => r.json())
  .then(data => {
    console.log('Messages:', data.messages);
    // Render in chat UI
  });

// Get latest 20 interactions from Analyzer
fetch('/api/interactions/latest?limit=20&agent=Analyzer')
  .then(r => r.json())
  .then(data => {
    console.log('Interactions:', data.interactions);
  });

// Get statistics
fetch('/api/interactions/statistics')
  .then(r => r.json())
  .then(data => {
    console.log('Stats:', data.statistics);
  });
```

---

## 🎨 Using the Chat Interface

The `chat_interface_example.html` provides a ready-to-use web UI:

**Features:**
- ✅ Load conversations by Workflow ID
- ✅ View latest interactions
- ✅ Filter by agent (Analyzer/Planner)
- ✅ Real-time statistics
- ✅ Chat-style message display
- ✅ Color-coded by role (user/assistant/system)
- ✅ Latency indicators
- ✅ Success/failure badges
- ✅ Expandable long messages
- ✅ Metadata display

**To integrate into your existing dashboard:**

Copy the CSS and JavaScript from `chat_interface_example.html` into your dashboard template.

---

## 📝 What Gets Logged

### For Each LLM Interaction:

```json
{
  "interaction_id": "unique-uuid",
  "timestamp": "2025-02-21T10:30:00.123456Z",
  "agent": "Analyzer",
  "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
  "interaction_type": "workflow_analysis_held",
  "direction": "request",
  "prompt": "Given the following Pegasus workflow logs...",
  "prompt_length": 1500,
  "response": "Based on the logs, the workflow is held because...",
  "response_length": 850,
  "latency_ms": 1200.5,
  "success": true,
  "error": null,
  "completed_at": "2025-02-21T10:30:01.323456Z",
  "metadata": {
    "analysis_type": "held",
    "ollama_model": "llama3.3:latest",
    "attempt": 1,
    "max_retries": 3
  },
  "parsed_data": {
    "problems_and_solutions": [...],
    "confidence_score": 0.85
  }
}
```

---

## 🔧 Advanced Usage

### Log Non-LLM Actions

```python
# In Analyzer
self._log_analyzer_action(
    action_type="stderr_analysis",
    description="Analyzing stderr output from 5 .out files",
    workflow_id=workflow_id,
    metadata={"file_count": 5}
)

# In Planner
self._log_planner_action(
    action_type="file_fetch",
    description="Fetching transformation catalog file",
    workflow_id=workflow_id,
    metadata={"file_path": "/path/to/tc.txt"}
)
```

### Link Multi-Stage Interactions

```python
# Stage 1
stage1_id = self._log_llm_plan_request(
    workflow_id=workflow_id,
    stage="stage1_file_identification",
    prompt=stage1_prompt,
    parent_interaction_id=None  # First stage
)

# Stage 2 (linked to stage 1)
stage2_id = self._log_llm_plan_request(
    workflow_id=workflow_id,
    stage="stage2_plan_generation",
    prompt=stage2_prompt,
    parent_interaction_id=stage1_id  # Link to parent
)
```

### Query Database Directly

```python
from common.interaction_logger import get_interaction_logger

logger = get_interaction_logger()

# Get all interactions for a workflow
messages = logger.get_workflow_conversation("workflow-id-123")

# Get statistics
stats = logger.get_statistics()

# Get latest 50 interactions from Analyzer
latest = logger.get_latest_interactions(limit=50, agent="Analyzer")

# Clean up old data (keep last 30 days)
removed = logger.clear_old_interactions(days=30)
```

---

## ✅ Verification Checklist

- [ ] `common/` directory created with all 7 files
- [ ] Analyzer agent has `AnalyzerLoggerMixin` added
- [ ] Analyzer `__init__` calls `self.__init_interaction_logger__()`
- [ ] Analyzer LLM calls wrapped with logging
- [ ] Planner agent has `PlannerLoggerMixin` added
- [ ] Planner `__init__` calls `self.__init_interaction_logger__()`
- [ ] Planner LLM calls wrapped with logging
- [ ] API endpoints added to one of the servers
- [ ] `logs/interaction_logs.json` created after first run
- [ ] API endpoints accessible at `/api/interactions/*`
- [ ] Chat interface can load conversations

---

## 🎯 Benefits

✅ **Automatic Logging** - All LLM interactions logged automatically
✅ **TinyDB Storage** - Lightweight, no database server needed
✅ **Timestamps** - ISO format with millisecond precision
✅ **API Access** - REST endpoints for web dashboard
✅ **Chat Format** - Pre-formatted for chat UI display
✅ **Performance Metrics** - Latency tracking for all calls
✅ **Multi-Stage Support** - Links related interactions
✅ **Rich Metadata** - Captures context, attempts, errors
✅ **Easy Querying** - Filter by workflow, agent, type
✅ **Minimal Changes** - Mixin pattern, no major refactoring

---

## 📞 Support

If you encounter any issues:

1. Check that `common/` directory exists
2. Verify imports are correct
3. Ensure `logs/` directory is writable
4. Check server logs for errors
5. Test API endpoints with curl
6. Verify TinyDB file is created: `ls -la logs/interaction_logs.json`

---

## 🚀 Next Steps

1. Complete the integration steps above
2. Restart your Analyzer and Planner agents
3. Process a real workflow
4. Check the database: `cat logs/interaction_logs.json`
5. Test the API endpoints
6. View in the chat interface
7. Integrate into your existing dashboard

**That's it! You now have complete LLM interaction logging with TinyDB and API access!**

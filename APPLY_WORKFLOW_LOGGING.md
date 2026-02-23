# Apply Workflow-Specific Logging to Analyzer & Planner

## Quick Integration Steps

### For Analyzer:

**1. Add Import** (Line ~27 in `analyzer_rest.py`):
```python
from workflow_interaction_logger import get_workflow_logger, close_workflow_logger
import time
```

**2. Modify Method Signature** (Line 1234):
```python
# FIND:
def _try_llm_request(self, prompt: str, use_json_format: bool = True) -> Optional[Dict[str, Any]]:

# CHANGE TO:
def _try_llm_request(self, prompt: str, workflow_id: str, analysis_type: str, use_json_format: bool = True) -> Optional[Dict[str, Any]]:
```

**3. Add Logging at Start of `_try_llm_request`** (Line ~1254):
```python
# ADD AT THE START OF THE METHOD (after line 1253):
wf_logger = get_workflow_logger(workflow_id)
```

**4. Log LLM Request** (Before line 1258 `response = requests.post`):
```python
# ADD BEFORE requests.post:
wf_logger.log_print(f"LLM request attempt {attempt + 1}/{max_retries}")
interaction_id = wf_logger.log_llm_request(
    prompt=prompt,
    metadata={
        "attempt": attempt + 1,
        "max_retries": max_retries,
        "ollama_model": self.ollama_manager.ollama_model,
        "analysis_type": analysis_type
    }
)

start_time = time.time()
```

**5. Log LLM Response** (After line 1265 `if response.status_code == 200:`):
```python
# FIND (around line 1277):
self.ollama_manager.log_connection_attempt("generate", True)

# ADD AFTER IT:
latency_ms = (time.time() - start_time) * 1000
wf_logger.log_llm_response(
    interaction_id=interaction_id,
    response=response_text,
    success=True,
    latency_ms=latency_ms
)
```

**6. Update Method Calls** (Line 1202):
```python
# FIND:
def send_logs_and_workflow_to_llm_enhanced(self, logs: str, workflow: Dict[str, Any], analysis_type: str = "failed", hold_reason: str = "", stderr_summary: str = "") -> Optional[Dict[str, Any]]:

# CHANGE TO:
def send_logs_and_workflow_to_llm_enhanced(self, logs: str, workflow: Dict[str, Any], workflow_id: str, analysis_type: str = "failed", hold_reason: str = "", stderr_summary: str = "") -> Optional[Dict[str, Any]]:
```

**7. Update `_try_llm_request` calls** (Lines 1220 and 1227):
```python
# FIND (line 1220):
result = self._try_llm_request(prompt, use_json_format=True)

# CHANGE TO:
result = self._try_llm_request(prompt, workflow_id, analysis_type, use_json_format=True)

# FIND (line 1227):
result = self._try_llm_request(prompt, use_json_format=False)

# CHANGE TO:
result = self._try_llm_request(prompt, workflow_id, analysis_type, use_json_format=False)
```

**8. Update analyze methods** (Line 1714):
```python
# FIND:
llm_response = self.send_logs_and_workflow_to_llm_enhanced(logs, workflow_data, "failed", stderr_summary=stderr_summary)

# CHANGE TO:
llm_response = self.send_logs_and_workflow_to_llm_enhanced(logs, workflow_data, workflow_id, "failed", stderr_summary=stderr_summary)
```

**9. Add logging to analyze_failed_workflow** (Line 1686):
```python
# ADD AT START OF METHOD (after line 1688):
wf_logger = get_workflow_logger(workflow_id)

try:
    wf_logger.log_event("analysis_start", {
        "workflow_id": workflow_id,
        "analysis_type": "failed"
    })

    # ... your existing code ...

finally:
    close_workflow_logger(workflow_id)
```

**10. Add API endpoints** (in `setup_http_routes` method):
```python
# ADD THESE ROUTES:
self.app.router.add_get('/api/analyzer/workflow-logs/{workflow_id}', self.get_workflow_logs)
self.app.router.add_get('/api/analyzer/workflow-logs', self.list_workflow_logs)
```

**11. Add API handler methods** (anywhere in the class):

See `analyzer_workflow_logger_patch.py` for the complete handler methods:
- `get_workflow_logs`
- `download_workflow_logs`
- `list_workflow_logs`

---

## Testing

After integration:

```bash
# 1. Start Analyzer
cd Analyzer
python3 analyzer_rest.py

# 2. Process a workflow (this creates the log automatically)

# 3. Check logs were created
ls -la workflow_logs/

# 4. View via API
curl http://localhost:8081/api/analyzer/workflow-logs

# 5. Get specific workflow logs
curl http://localhost:8081/api/analyzer/workflow-logs/{workflow_id}

# 6. View directly
cat workflow_logs/{workflow_id}/interactions.json | python3 -m json.tool
```

---

## API Endpoints Added

### List All Workflows with Logs
```bash
GET http://localhost:8081/api/analyzer/workflow-logs
```

Response:
```json
{
  "success": true,
  "workflows": [
    {
      "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
      "database_path": "workflow_logs/bd3f384f.../interactions.json",
      "counts": {
        "llm_interactions": 1,
        "outputs": 5,
        "events": 4
      }
    }
  ]
}
```

### Get Complete Logs for Workflow
```bash
GET http://localhost:8081/api/analyzer/workflow-logs/{workflow_id}
```

Response:
```json
{
  "success": true,
  "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
  "tables": {
    "llm_interactions": [...],
    "outputs": [...],
    "events": [...]
  }
}
```

---

## What Gets Logged

For each workflow, a separate database is created with:

1. **LLM Interactions** - Full prompts, responses, latency
2. **Outputs** - All print statements, JSON data
3. **Events** - Analysis start/end, errors, fallbacks

Example structure:
```
workflow_logs/
└── bd3f384f-eeeb-4468-b8e4-510053acf3a1/
    └── interactions.json
        ├── llm_interactions (table)
        ├── outputs (table)
        └── events (table)
```

---

## For Planner

Apply the same changes to `Planner/planner_rest.py` with these adjustments:

1. Import the logger
2. Add `workflow_id` parameter to LLM calling methods
3. Log requests/responses
4. Add API endpoints

The integration is identical, just adjust the method names to match your Planner code.

---

## See Also

- `analyzer_workflow_logger_patch.py` - Complete patch with all changes
- `WORKFLOW_SPECIFIC_LOGGING.md` - Full documentation
- `Analyzer/WORKFLOW_LOGGING_INTEGRATION.md` - Detailed guide

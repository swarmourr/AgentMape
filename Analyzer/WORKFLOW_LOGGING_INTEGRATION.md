# Workflow-Specific Interaction Logging - Integration Guide

## Overview

This creates a **separate database for each workflow ID** and logs **everything**:
- ✅ LLM prompts and responses
- ✅ All print statements
- ✅ All JSON data
- ✅ All events and outputs
- ✅ Timestamps on everything

## Database Structure

```
workflow_logs/
├── {workflow-id-1}/
│   └── interactions.json         # Complete log for this workflow
├── {workflow-id-2}/
│   └── interactions.json         # Complete log for this workflow
└── {workflow-id-3}/
    └── interactions.json         # Complete log for this workflow
```

Each `interactions.json` contains:
- `llm_interactions` table - All LLM conversations
- `outputs` table - All prints and JSON outputs
- `events` table - All events (session start/end, etc.)

---

## Integration Steps

### Step 1: Import the Logger

**File:** `Analyzer/analyzer_rest.py`

**At line ~27 (imports section):**
```python
from workflow_interaction_logger import get_workflow_logger, close_workflow_logger
import time
```

### Step 2: Create Logger at Start of Analysis

**Find your workflow analysis methods** (e.g., `analyze_failed_workflow`, `analyze_held_workflow`)

**At the START of the method:**

```python
async def analyze_failed_workflow(self, workflow_id: str, workflow_dir: str, job_out_files: List = None) -> Dict[str, Any]:
    """Analyze failed workflow with complete logging"""

    # CREATE WORKFLOW-SPECIFIC LOGGER
    wf_logger = get_workflow_logger(workflow_id)

    try:
        wf_logger.log_event("analysis_start", {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "analysis_type": "failed"
        })

        # Log any print statements
        wf_logger.log_print(f"Starting analysis for workflow: {workflow_id}")

        # ... your existing code ...
```

### Step 3: Log LLM Interactions

**Find where you call the LLM** (around line 1250-1324)

**BEFORE the LLM call:**

```python
# Build the prompt
prompt = self.prompt_manager.get_workflow_analysis_prompt(logs, workflow_yaml, stderr_summary)

# LOG THE REQUEST
interaction_id = wf_logger.log_llm_request(
    prompt=prompt,
    metadata={
        "attempt": attempt + 1,
        "max_retries": max_retries,
        "ollama_model": self.ollama_manager.ollama_model,
        "analysis_type": "failed",  # or "held"
        "prompt_type": "workflow_analysis"
    }
)

# LOG THE PROMPT AS JSON
wf_logger.log_json({
    "prompt": prompt,
    "prompt_length": len(prompt),
    "ollama_model": self.ollama_manager.ollama_model
}, label="llm_request")

start_time = time.time()

# Your existing LLM call
response = requests.post(
    self.ollama_manager.ollama_url,
    json=payload,
    timeout=generation_timeout,
    headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
)

latency_ms = (time.time() - start_time) * 1000
```

**AFTER the LLM response:**

```python
if response.status_code == 200:
    ollama_response = response.json()
    response_text = ollama_response.get('response', '').strip()

    # LOG THE RESPONSE AS JSON
    wf_logger.log_json(ollama_response, label="llm_response_raw")

    # Parse the response
    parsed_result = self.extract_workflow_info_enhanced(ollama_response)

    # LOG THE PARSED RESULT AS JSON
    wf_logger.log_json(parsed_result, label="llm_response_parsed")

    # LOG SUCCESS
    wf_logger.log_llm_response(
        interaction_id=interaction_id,
        response=response_text,
        success=True,
        latency_ms=latency_ms,
        parsed_result=parsed_result
    )

    wf_logger.log_print(f"LLM analysis completed successfully in {latency_ms:.2f}ms")

    # ... rest of your code ...

else:
    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"

    # LOG FAILURE
    wf_logger.log_llm_response(
        interaction_id=interaction_id,
        response=None,
        success=False,
        latency_ms=latency_ms,
        error=error_msg
    )

    wf_logger.log_print(f"LLM request failed: {error_msg}", level="error")
```

### Step 4: Log All Your Print Statements

**Replace your print statements:**

```python
# BEFORE:
print(f"Analyzing workflow {workflow_id}")

# AFTER:
wf_logger.log_print(f"Analyzing workflow {workflow_id}")
```

**Or capture all prints automatically:**

```python
# At the start of your analysis method:
with wf_logger.capture_output("workflow_analysis"):
    # All prints inside this block are automatically captured
    print("This will be logged automatically")
    print("So will this")
    # ... your existing code with prints ...
```

### Step 5: Log JSON Data

**Whenever you have important JSON data:**

```python
# Log workflow YAML
wf_logger.log_json(workflow_yaml, label="workflow_yaml")

# Log analysis result
wf_logger.log_json(analysis_result, label="final_analysis_result")

# Log any configuration
wf_logger.log_json(config_data, label="configuration")
```

### Step 6: Log Events

```python
# Log important events
wf_logger.log_event("llm_fallback_triggered", {
    "reason": "LLM not available",
    "using_fallback": True
})

wf_logger.log_event("analysis_complete", {
    "total_issues": len(problems_and_solutions),
    "confidence_score": confidence_score
})
```

### Step 7: Close Logger at End

**At the END of your analysis method:**

```python
async def analyze_failed_workflow(self, workflow_id: str, workflow_dir: str, job_out_files: List = None) -> Dict[str, Any]:
    wf_logger = get_workflow_logger(workflow_id)

    try:
        # ... all your analysis code ...

        # Log final result
        wf_logger.log_json(final_result, label="final_result")
        wf_logger.log_event("analysis_complete", {"success": True})

        return final_result

    except Exception as e:
        wf_logger.log_print(f"Error during analysis: {e}", level="error")
        wf_logger.log_event("analysis_error", {"error": str(e)})
        raise

    finally:
        # Close the logger
        close_workflow_logger(workflow_id)
```

---

## Complete Example

Here's a complete example of integrating into your analysis method:

```python
async def analyze_held_workflow(self, workflow_id: str, workflow_dir: str, hold_reason: str = "", job_out_files: List = None) -> Dict[str, Any]:
    """Analyze held workflow with complete logging"""

    # STEP 1: Create workflow-specific logger
    wf_logger = get_workflow_logger(workflow_id)

    try:
        # STEP 2: Log analysis start
        wf_logger.log_event("analysis_start", {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "analysis_type": "held",
            "hold_reason": hold_reason
        })

        wf_logger.log_print(f"Starting held workflow analysis for: {workflow_id}")

        # Get workflow data
        logs = self.get_pegasus_analyzer_logs(workflow_dir)
        workflow_yaml = self.load_workflow_yaml(workflow_dir)

        # STEP 3: Log input data
        wf_logger.log_json({"logs": logs, "logs_length": len(logs)}, label="input_logs")
        wf_logger.log_json(workflow_yaml, label="input_workflow_yaml")

        # Build prompt
        prompt = self.prompt_manager.get_workflow_analysis_prompt(logs, workflow_yaml)

        wf_logger.log_print(f"Generated prompt ({len(prompt)} chars)")

        # STEP 4: Log LLM request
        interaction_id = wf_logger.log_llm_request(
            prompt=prompt,
            metadata={
                "analysis_type": "held",
                "ollama_model": self.ollama_manager.ollama_model,
                "prompt_length": len(prompt)
            }
        )

        # Make LLM call
        wf_logger.log_print("Sending request to LLM...")
        start_time = time.time()

        response = requests.post(
            self.ollama_manager.ollama_url,
            json={"model": self.ollama_manager.ollama_model, "prompt": prompt},
            timeout=120
        )

        latency_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            ollama_response = response.json()
            response_text = ollama_response.get('response', '')

            wf_logger.log_print(f"Received LLM response ({len(response_text)} chars) in {latency_ms:.2f}ms")

            # STEP 5: Log response
            wf_logger.log_json(ollama_response, label="llm_response_raw")

            # Parse
            parsed_result = self.extract_workflow_info_enhanced(ollama_response)

            wf_logger.log_json(parsed_result, label="llm_response_parsed")

            # STEP 6: Log LLM interaction complete
            wf_logger.log_llm_response(
                interaction_id=interaction_id,
                response=response_text,
                success=True,
                latency_ms=latency_ms,
                parsed_result=parsed_result
            )

            # Build final result
            final_result = {
                "workflow_id": workflow_id,
                "analysis_type": "held",
                "timestamp": datetime.now().isoformat(),
                **parsed_result
            }

            # STEP 7: Log final result
            wf_logger.log_json(final_result, label="final_analysis_result")
            wf_logger.log_event("analysis_complete", {
                "success": True,
                "problems_found": len(parsed_result.get('problems_and_solutions', [])),
                "latency_ms": latency_ms
            })

            wf_logger.log_print("Analysis completed successfully!")

            return final_result

        else:
            error_msg = f"HTTP {response.status_code}"
            wf_logger.log_print(f"LLM request failed: {error_msg}", level="error")

            wf_logger.log_llm_response(
                interaction_id=interaction_id,
                response=None,
                success=False,
                latency_ms=latency_ms,
                error=error_msg
            )

            # Use fallback
            wf_logger.log_event("llm_fallback_triggered", {"reason": error_msg})
            return self.fallback_analysis(workflow_id, logs)

    except Exception as e:
        wf_logger.log_print(f"Error during analysis: {e}", level="error")
        wf_logger.log_event("analysis_error", {"error": str(e), "type": type(e).__name__})
        raise

    finally:
        # STEP 8: Close logger
        close_workflow_logger(workflow_id)
```

---

## Database Schema

Each workflow's `interactions.json` will contain:

### Table: `llm_interactions`

```json
{
  "1": {
    "interaction_id": "uuid-123",
    "session_id": "session-uuid",
    "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
    "timestamp": "2026-02-22T08:38:30.000000",
    "type": "llm_request",
    "agent": "Analyzer",
    "prompt": "[Full prompt text here...]",
    "prompt_length": 15234,
    "metadata": {
      "attempt": 1,
      "max_retries": 3,
      "analysis_type": "failed"
    },
    "response": "[Full response text here...]",
    "response_length": 2456,
    "latency_ms": 7591.419,
    "success": true,
    "error": null,
    "completed_at": "2026-02-22T08:38:37.591419",
    "parsed_result": {
      "problems_and_solutions": [...]
    }
  }
}
```

### Table: `outputs`

```json
{
  "1": {
    "output_id": "uuid-456",
    "session_id": "session-uuid",
    "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
    "timestamp": "2026-02-22T08:38:31.000000",
    "type": "print",
    "level": "info",
    "message": "Starting analysis for workflow: bd3f384f...",
    "context": {}
  },
  "2": {
    "output_id": "uuid-789",
    "session_id": "session-uuid",
    "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
    "timestamp": "2026-02-22T08:38:32.000000",
    "type": "json",
    "label": "workflow_yaml",
    "data": {
      "jobs": [...],
      "transformations": [...]
    },
    "context": {}
  }
}
```

### Table: `events`

```json
{
  "1": {
    "event_id": "uuid-abc",
    "session_id": "session-uuid",
    "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
    "timestamp": "2026-02-22T08:38:30.000000",
    "event_type": "analysis_start",
    "data": {
      "workflow_dir": "/path/to/workflow",
      "analysis_type": "failed"
    }
  },
  "2": {
    "event_id": "uuid-def",
    "session_id": "session-uuid",
    "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
    "timestamp": "2026-02-22T08:38:40.000000",
    "event_type": "analysis_complete",
    "data": {
      "success": true,
      "problems_found": 3,
      "latency_ms": 7591.419
    }
  }
}
```

---

## Querying the Logs

```python
from tinydb import TinyDB

# Open a specific workflow's log
db = TinyDB('workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json')

# Get all LLM interactions
llm_interactions = db.table('llm_interactions').all()

# Get all outputs
outputs = db.table('outputs').all()

# Get all events
events = db.table('events').all()

# Query specific data
from tinydb import Query
q = Query()

# Find successful LLM interactions
successful = db.table('llm_interactions').search(q.success == True)

# Find all prints
prints = db.table('outputs').search(q.type == 'print')

# Find JSON logs
json_logs = db.table('outputs').search(q.type == 'json')
```

---

## Benefits

✅ **Separate DB per workflow** - Easy to find logs for a specific workflow
✅ **Everything logged** - LLM prompts, responses, prints, JSON data, events
✅ **Timestamps on everything** - Complete timeline
✅ **JSON format** - Easy to query and analyze
✅ **Session tracking** - Group related operations
✅ **Context preserved** - Metadata and context for all logs

---

## Testing

```bash
# Run analyzer with this integration
python3 analyzer_rest.py

# After processing a workflow, check the logs:
ls -la workflow_logs/

# You'll see:
workflow_logs/
├── bd3f384f-eeeb-4468-b8e4-510053acf3a1/
│   └── interactions.json

# View the log:
cat workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json | jq .

# Or use Python:
python3 -c "
from tinydb import TinyDB
db = TinyDB('workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json')
print('LLM interactions:', len(db.table('llm_interactions').all()))
print('Outputs:', len(db.table('outputs').all()))
print('Events:', len(db.table('events').all()))
"
```

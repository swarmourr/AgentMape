# Workflow-Specific Interaction Logging System

## 🎯 Overview

This system creates a **separate database for each workflow ID** and logs **EVERYTHING**:

- ✅ LLM prompts and responses (full text)
- ✅ All print statements
- ✅ All JSON data
- ✅ All events (start, end, errors, etc.)
- ✅ Timestamps on everything
- ✅ Session tracking

## 📁 File Structure

```
AgentMape/
├── Analyzer/
│   ├── workflow_interaction_logger.py       # NEW - Logger for Analyzer
│   └── WORKFLOW_LOGGING_INTEGRATION.md      # NEW - Integration guide
│
├── Planner/
│   ├── workflow_interaction_logger.py       # NEW - Logger for Planner
│   └── (similar integration guide)
│
└── workflow_logs/                           # NEW - Auto-created
    ├── {workflow-id-1}/
    │   └── interactions.json                # Complete log for workflow 1
    ├── {workflow-id-2}/
    │   └── interactions.json                # Complete log for workflow 2
    └── {workflow-id-3}/
        └── interactions.json                # Complete log for workflow 3
```

## 🗄️ Database Structure

Each workflow gets its own `interactions.json` with 3 tables:

### 1. `llm_interactions` - LLM Conversations

Logs every LLM request and response:

```json
{
  "1": {
    "interaction_id": "uuid-123",
    "session_id": "session-uuid",
    "workflow_id": "bd3f384f-eeeb-4468-b8e4-510053acf3a1",
    "timestamp": "2026-02-22T08:38:30.000000",
    "completed_at": "2026-02-22T08:38:37.591419",
    "type": "llm_request",
    "agent": "Analyzer",

    "prompt": "[FULL 15KB PROMPT TEXT HERE]",
    "prompt_length": 15234,

    "response": "[FULL 2.5KB RESPONSE TEXT HERE]",
    "response_length": 2456,

    "latency_ms": 7591.419,
    "success": true,
    "error": null,

    "metadata": {
      "attempt": 1,
      "max_retries": 3,
      "analysis_type": "failed",
      "ollama_model": "llama3.3:latest"
    },

    "parsed_result": {
      "problems_and_solutions": [...],
      "confidence_score": 0.95
    }
  }
}
```

### 2. `outputs` - All Prints and JSON Data

Logs every print statement and JSON output:

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
      "transformations": [...],
      "full_yaml_content": "..."
    },
    "context": {}
  }
}
```

### 3. `events` - All Events

Logs all important events:

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
    "timestamp": "2026-02-22T08:38:40.000000",
    "event_type": "analysis_complete",
    "data": {
      "success": true,
      "problems_found": 3,
      "total_latency_ms": 10000
    }
  }
}
```

---

## 🚀 Quick Integration

### For Analyzer:

```python
from workflow_interaction_logger import get_workflow_logger, close_workflow_logger
import time

async def analyze_failed_workflow(self, workflow_id: str, workflow_dir: str) -> Dict[str, Any]:
    # 1. CREATE LOGGER
    wf_logger = get_workflow_logger(workflow_id)

    try:
        # 2. LOG EVENTS
        wf_logger.log_event("analysis_start", {"workflow_id": workflow_id})

        # 3. LOG PRINTS
        wf_logger.log_print(f"Starting analysis for {workflow_id}")

        # 4. LOG JSON DATA
        wf_logger.log_json(workflow_yaml, label="workflow_yaml")

        # 5. LOG LLM REQUEST
        interaction_id = wf_logger.log_llm_request(
            prompt=prompt,
            metadata={"analysis_type": "failed"}
        )

        # 6. CALL LLM
        start_time = time.time()
        response = requests.post(ollama_url, json=payload)
        latency_ms = (time.time() - start_time) * 1000

        # 7. LOG LLM RESPONSE
        if response.status_code == 200:
            parsed_result = self.parse_response(response.json())

            wf_logger.log_llm_response(
                interaction_id=interaction_id,
                response=response.text,
                success=True,
                latency_ms=latency_ms,
                parsed_result=parsed_result
            )

            # 8. LOG FINAL RESULT
            wf_logger.log_json(parsed_result, label="final_result")
            wf_logger.log_event("analysis_complete", {"success": True})

            return parsed_result

    finally:
        # 9. CLOSE LOGGER
        close_workflow_logger(workflow_id)
```

---

## 📊 What Gets Logged

### Example for Workflow: `bd3f384f-eeeb-4468-b8e4-510053acf3a1`

**File:** `workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json`

**Contents:**

1. **Session Start Event**
   - Timestamp: 2026-02-22T08:38:30
   - Type: session_start

2. **Analysis Start Event**
   - Timestamp: 2026-02-22T08:38:30
   - Type: analysis_start
   - Data: workflow_dir, analysis_type

3. **Print: "Starting analysis..."**
   - Timestamp: 2026-02-22T08:38:31
   - Type: print
   - Message: "Starting analysis for workflow: bd3f384f..."

4. **JSON: Workflow YAML**
   - Timestamp: 2026-02-22T08:38:32
   - Type: json
   - Label: workflow_yaml
   - Data: {full YAML content}

5. **LLM Request**
   - Timestamp: 2026-02-22T08:38:33
   - Prompt: "[Full 15KB prompt]"
   - Metadata: {attempt: 1, model: "llama3.3:latest"}

6. **Print: "Sending request to LLM..."**
   - Timestamp: 2026-02-22T08:38:34

7. **LLM Response**
   - Completed: 2026-02-22T08:38:37.591419
   - Response: "[Full 2.5KB response]"
   - Latency: 7591ms
   - Success: true
   - Parsed Result: {problems_and_solutions: [...]}

8. **JSON: Parsed Result**
   - Timestamp: 2026-02-22T08:38:38
   - Label: llm_response_parsed
   - Data: {parsed problems and solutions}

9. **JSON: Final Result**
   - Timestamp: 2026-02-22T08:38:39
   - Label: final_analysis_result
   - Data: {complete analysis result}

10. **Analysis Complete Event**
    - Timestamp: 2026-02-22T08:38:40
    - Type: analysis_complete
    - Data: {success: true, problems_found: 3}

11. **Session End Event**
    - Timestamp: 2026-02-22T08:38:40
    - Type: session_end
    - Summary: {llm_interactions: 1, outputs: 5, events: 4}

---

## 🔍 Querying the Logs

### Python:

```python
from tinydb import TinyDB, Query

# Open workflow log
workflow_id = "bd3f384f-eeeb-4468-b8e4-510053acf3a1"
db = TinyDB(f'workflow_logs/{workflow_id}/interactions.json')

# Get all LLM interactions
llm_interactions = db.table('llm_interactions').all()
print(f"Total LLM calls: {len(llm_interactions)}")

# Get all print statements
outputs = db.table('outputs').all()
prints = [o for o in outputs if o['type'] == 'print']
for p in prints:
    print(f"[{p['timestamp']}] {p['message']}")

# Get all JSON logs
json_logs = [o for o in outputs if o['type'] == 'json']
for j in json_logs:
    print(f"[{j['timestamp']}] {j['label']}: {len(str(j['data']))} bytes")

# Get timeline of events
events = db.table('events').all()
for e in sorted(events, key=lambda x: x['timestamp']):
    print(f"[{e['timestamp']}] {e['event_type']}")

# Query specific data
q = Query()
failed_llm = db.table('llm_interactions').search(q.success == False)
print(f"Failed LLM calls: {len(failed_llm)}")
```

### Command Line:

```bash
# List all workflow logs
ls -la workflow_logs/

# View a specific workflow's log
cat workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json | jq .

# Count LLM interactions
cat workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json | jq '.llm_interactions | length'

# View all events
cat workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json | jq '.events'

# Extract just the LLM prompt
cat workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json | jq '.llm_interactions."1".prompt'

# Extract parsed results
cat workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json | jq '.llm_interactions."1".parsed_result'
```

---

## 🎁 Benefits

### 1. **Separate DB Per Workflow**
- Easy to find logs for a specific workflow
- No mixing of data from different workflows
- Can delete old workflow logs individually

### 2. **Everything Logged**
- Full LLM prompts (not truncated)
- Full LLM responses (not truncated)
- All print statements with timestamps
- All JSON data (workflow YAML, configs, results)
- All events (start, end, errors, fallback triggers)

### 3. **Complete Timeline**
- Every item has a timestamp
- Can reconstruct exactly what happened when
- See request → response latency
- Track session duration

### 4. **Easy Debugging**
- See the exact prompt that was sent
- See the exact response that was received
- See all intermediate steps
- See what data was available at each step

### 5. **JSON Format**
- Easy to query with TinyDB
- Easy to process with jq
- Easy to import into other tools
- Easy to analyze programmatically

### 6. **Session Tracking**
- Each analysis session gets a unique ID
- Can see all operations in a session
- Session summary at the end

---

## 📝 Integration Guides

- **Analyzer:** See `Analyzer/WORKFLOW_LOGGING_INTEGRATION.md`
- **Planner:** Similar to Analyzer (use `Planner/workflow_interaction_logger.py`)

---

## 🧪 Testing

```bash
# 1. Integrate the logger into your Analyzer
# 2. Run analyzer on a workflow
python3 Analyzer/analyzer_rest.py

# 3. Process a workflow (this creates the log)
# ...

# 4. Check the logs
ls -la workflow_logs/

# You should see:
workflow_logs/
└── bd3f384f-eeeb-4468-b8e4-510053acf3a1/
    └── interactions.json

# 5. View the log
cat workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json | jq .

# 6. Check what's logged
python3 -c "
from tinydb import TinyDB
db = TinyDB('workflow_logs/bd3f384f-eeeb-4468-b8e4-510053acf3a1/interactions.json')
print('Tables:', db.tables())
print('LLM interactions:', len(db.table('llm_interactions').all()))
print('Outputs:', len(db.table('outputs').all()))
print('Events:', len(db.table('events').all()))
"
```

---

## 🎯 Summary

**Created:**
- ✅ `Analyzer/workflow_interaction_logger.py` - Logger for Analyzer
- ✅ `Analyzer/WORKFLOW_LOGGING_INTEGRATION.md` - Integration guide
- ✅ `Planner/workflow_interaction_logger.py` - Logger for Planner

**Usage:**
```python
# At start of workflow analysis:
wf_logger = get_workflow_logger(workflow_id)

# Log everything:
wf_logger.log_print("message")
wf_logger.log_json(data, label="description")
wf_logger.log_llm_request(prompt, metadata)
wf_logger.log_llm_response(id, response, success, latency)
wf_logger.log_event("event_name", data)

# At end:
close_workflow_logger(workflow_id)
```

**Result:**
- Separate database per workflow: `workflow_logs/{workflow_id}/interactions.json`
- Everything logged with timestamps
- Easy to query and analyze
- Complete audit trail of all operations

**Follow the integration guide to add ~20-30 lines of code to your Analyzer!**

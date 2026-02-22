# Analyzer - LLM Interaction Logging Integration

## Step 1: Import the Logger

**File:** `Analyzer/analyzer_rest.py`

**At line ~27 (after other imports):**
```python
from interaction_logger import AnalyzerInteractionLogger
import time  # If not already imported
```

## Step 2: Initialize Logger in __init__

**File:** `Analyzer/analyzer_rest.py`

**At line ~724 (right after database setup):**
```python
# Database setup
self.db = TinyDB('analyzer_agent_db.json')
self.analysis_table = self.db.table('workflow_analysis')
self.failed_workflows_table = self.db.table('failed_workflows')

# ADD THIS LINE:
self.interaction_logger = AnalyzerInteractionLogger(self.db)
```

## Step 3: Log LLM Interactions

**File:** `Analyzer/analyzer_rest.py`

**Find the LLM calling code (around line 1250-1324) and modify:**

### BEFORE (Original Code):
```python
for attempt in range(max_retries):
    try:
        self.logger.info(f"LLM request attempt {attempt + 1}/{max_retries}")

        response = requests.post(
            self.ollama_manager.ollama_url,
            json=payload,
            timeout=generation_timeout,
            headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
        )

        if response.status_code == 200:
            ollama_response = response.json()
            response_text = ollama_response.get('response', '').strip()

            # ... existing code ...
```

### AFTER (With Logging):
```python
# DETERMINE ANALYSIS TYPE
analysis_type = "held" if "held" in str(workflow_dir).lower() else "failed"

for attempt in range(max_retries):
    try:
        self.logger.info(f"LLM request attempt {attempt + 1}/{max_retries}")

        # LOG REQUEST
        interaction_id = self.interaction_logger.log_llm_request(
            workflow_id=workflow_id,
            analysis_type=analysis_type,
            prompt=prompt,
            metadata={
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "ollama_model": self.ollama_manager.ollama_model,
                "use_json_format": use_json_format
            }
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

            if not response_text:
                self.logger.warning(f"Empty response from Ollama on attempt {attempt + 1}")
                # LOG FAILURE
                self.interaction_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response="",
                    success=False,
                    latency_ms=latency_ms,
                    error="Empty response from LLM"
                )
                continue

            # Parse the response
            parsed_result = self.extract_workflow_info_enhanced(ollama_response)

            # Update connection status on success
            self.ollama_manager.is_healthy = True
            self.ollama_manager.last_error = None
            self.ollama_manager.log_connection_attempt("generate", True)

            # LOG SUCCESS
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=response_text,
                success=True,
                latency_ms=latency_ms,
                parsed_result=parsed_result
            )

            return {
                "choices": [{
                    "message": {
                        "content": response_text
                    }
                }]
            }
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            self.logger.error(f"Ollama API Error on attempt {attempt + 1}: {error_msg}")

            # LOG FAILURE
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=None,
                success=False,
                latency_ms=latency_ms,
                error=error_msg
            )

            self.ollama_manager.log_connection_attempt("generate", False, error_msg)

            # Don't retry on client errors (4xx)
            if 400 <= response.status_code < 500:
                break

    except requests.exceptions.Timeout:
        latency_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
        error_msg = f"Request timeout ({generation_timeout}s) on attempt {attempt + 1}"
        self.logger.error(error_msg)

        # LOG FAILURE
        if 'interaction_id' in locals():
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=None,
                success=False,
                latency_ms=latency_ms,
                error=error_msg
            )

        self.ollama_manager.log_connection_attempt("generate", False, error_msg)

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
        error_msg = f"Unexpected error on attempt {attempt + 1}: {str(e)}"
        self.logger.error(error_msg)

        # LOG FAILURE
        if 'interaction_id' in locals():
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=None,
                success=False,
                latency_ms=latency_ms,
                error=error_msg
            )

        self.ollama_manager.log_connection_attempt("generate", False, error_msg)

    # Wait before retry (exponential backoff)
    if attempt < max_retries - 1:
        wait_time = 2 ** attempt
        self.logger.info(f"Waiting {wait_time}s before retry...")
        time.sleep(wait_time)
```

## Step 4: Add API Endpoints

**File:** `Analyzer/analyzer_rest.py`

**In the `setup_http_routes` method (around line 777), add:**

```python
def setup_http_routes(self):
    """Setup HTTP routes"""
    # ... existing routes ...

    # ADD THESE NEW ROUTES:
    self.app.router.add_get('/api/analyzer/interactions/workflow/{workflow_id}',
                            self.get_workflow_interactions)
    self.app.router.add_get('/api/analyzer/interactions/latest',
                            self.get_latest_interactions)
    self.app.router.add_get('/api/analyzer/interactions/statistics',
                            self.get_interaction_statistics)
```

**Then add these handler methods (add anywhere in the class):**

```python
async def get_workflow_interactions(self, request: web.Request) -> web.Response:
    """Get all LLM interactions for a specific workflow"""
    try:
        workflow_id = request.match_info['workflow_id']

        interactions = self.interaction_logger.get_workflow_interactions(workflow_id)

        return web.json_response({
            "success": True,
            "workflow_id": workflow_id,
            "agent": "Analyzer",
            "count": len(interactions),
            "interactions": interactions
        })
    except Exception as e:
        self.logger.error(f"Error getting workflow interactions: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def get_latest_interactions(self, request: web.Request) -> web.Response:
    """Get latest LLM interactions"""
    try:
        limit = int(request.query.get('limit', 50))

        interactions = self.interaction_logger.get_all_interactions(limit=limit)

        return web.json_response({
            "success": True,
            "agent": "Analyzer",
            "count": len(interactions),
            "interactions": interactions
        })
    except Exception as e:
        self.logger.error(f"Error getting latest interactions: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def get_interaction_statistics(self, request: web.Request) -> web.Response:
    """Get statistics about LLM interactions"""
    try:
        stats = self.interaction_logger.get_statistics()

        return web.json_response({
            "success": True,
            "statistics": stats
        })
    except Exception as e:
        self.logger.error(f"Error getting interaction statistics: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)
```

## Testing

After integration, test with:

```bash
# Start Analyzer agent
cd /Users/hamzasafri/Desktop/AgentMape/Analyzer
python3 analyzer_rest.py

# In another terminal, test the endpoints:

# Get statistics
curl http://localhost:8081/api/analyzer/interactions/statistics

# Get latest interactions
curl http://localhost:8081/api/analyzer/interactions/latest?limit=10

# Get interactions for a specific workflow
curl http://localhost:8081/api/analyzer/interactions/workflow/YOUR_WORKFLOW_ID

# Check the database
cat analyzer_agent_db.json | jq '.llm_interactions'
```

## Database Structure

The interactions will be stored in `analyzer_agent_db.json` under the `llm_interactions` table:

```json
{
  "workflow_analysis": {...},
  "failed_workflows": {...},
  "llm_interactions": {
    "1": {
      "interaction_id": "uuid-123",
      "timestamp": "2025-02-21T21:30:00.123456",
      "agent": "Analyzer",
      "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
      "analysis_type": "held",
      "direction": "request",
      "prompt": "Given the following...",
      "response": "Based on the logs...",
      "latency_ms": 1234.5,
      "success": true,
      "parsed_result": {...}
    }
  }
}
```

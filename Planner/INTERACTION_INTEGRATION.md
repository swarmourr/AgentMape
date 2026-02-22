# Planner - LLM Interaction Logging Integration

## Step 1: Import the Logger

**File:** `Planner/planner_rest.py`

**At line ~24 (after other imports):**
```python
from interaction_logger import PlannerInteractionLogger
import time  # If not already imported
```

## Step 2: Initialize Logger

**File:** `Planner/planner_rest.py`

**Find where TinyDB is initialized (around line 36-39) and add:**

```python
# Database setup
db = TinyDB("planner_db.json")
plans_table = db.table("plans")
execution_requests_table = db.table("execution_requests")
agents_table = db.table("agents")

# ADD THIS LINE:
interaction_logger = PlannerInteractionLogger(db)
```

**Then in your PlannerAgent class __init__ (if you have one), add:**
```python
self.interaction_logger = interaction_logger
```

**OR if using global `db`, create a global logger:**
```python
interaction_logger = PlannerInteractionLogger(db)
```

## Step 3: Log LLM Interactions (Single-Stage Planning)

**File:** `Planner/planner_rest.py`

**Find `generate_plan_with_llm` method (around line 1192-1300):**

### ADD LOGGING:

```python
async def generate_plan_with_llm(
    self,
    analysis_result: Dict[str, Any],
    catalogs: Dict[str, Any],
    workflow_context: Dict[str, Any],
    additional_files: Dict[str, str] = None,
    use_multi_stage: bool = True
) -> Dict[str, Any]:
    """Generate repair plan using LLM with optional multi-stage approach"""

    workflow_id = workflow_context.get('workflow_id')
    logger.info(f"Generating plan for workflow {workflow_id}")

    # ... existing file fetching code ...

    # Build prompt
    prompt = self.prompt_builder.build_planner_prompt(analysis_result, catalogs, workflow_context)

    # LOG REQUEST
    interaction_id = self.interaction_logger.log_llm_request(
        workflow_id=workflow_id,
        stage="single_stage",
        prompt=prompt,
        metadata={
            "additional_files_count": len(additional_files) if additional_files else 0,
            "catalogs_provided": list(catalogs.keys()),
            "use_multi_stage": use_multi_stage
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

            # Check if LLM is requesting more files
            if plan.get('needs_more_information'):
                logger.info(f"LLM requesting additional files for {workflow_id}")
                # LOG THIS RESPONSE
                self.interaction_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response=str(llm_response),
                    success=True,
                    latency_ms=latency_ms,
                    parsed_plan={"status": "needs_more_files", "files_requested": plan.get('files_requested', [])}
                )
                return await self.handle_file_request(plan, analysis_result, catalogs, workflow_context)

            # Validate plan
            validation_result = self.validator.validate_plan(plan, workflow_context)

            # Add metadata
            plan["plan_id"] = str(uuid.uuid4())
            plan["workflow_id"] = workflow_id
            plan["created_at"] = datetime.now().isoformat()
            plan["validation_result"] = validation_result
            plan["llm_used"] = True

            # Store plan
            self.plans_table.insert(plan)

            # LOG SUCCESS
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=str(llm_response),
                success=True,
                latency_ms=latency_ms,
                parsed_plan={
                    "plan_id": plan["plan_id"],
                    "actions_count": len(plan.get("actions", [])),
                    "validation_passed": validation_result.get("valid", False)
                }
            )

            # Print plan summary
            self.print_plan_summary(plan)

            return plan

        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")

            # LOG FAILURE
            self.interaction_logger.log_llm_response(
                interaction_id=interaction_id,
                response=str(llm_response),
                success=False,
                latency_ms=latency_ms,
                error=str(e)
            )

            return self.generate_fallback_plan(analysis_result, workflow_context)
    else:
        logger.warning("LLM not available, using fallback planning")

        # LOG FAILURE
        self.interaction_logger.log_llm_response(
            interaction_id=interaction_id,
            response=None,
            success=False,
            latency_ms=latency_ms,
            error="LLM not available"
        )

        return self.generate_fallback_plan(analysis_result, workflow_context)
```

## Step 4: Log Multi-Stage Planning

**File:** `Planner/planner_rest.py`

**Find `generate_plan_multi_stage` method (around line 1302-1400):**

```python
async def generate_plan_multi_stage(
    self,
    analysis_result: Dict[str, Any],
    catalogs: Dict[str, Any],
    workflow_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Multi-stage LLM approach to handle large prompts"""
    workflow_id = workflow_context.get('workflow_id')

    # ===== STAGE 1: Identify Required Files =====
    stage1_prompt = self._build_file_identification_prompt(analysis_result, workflow_context)

    # LOG STAGE 1 REQUEST
    parent_id = None  # First stage has no parent
    stage1_id = self.interaction_logger.log_llm_request(
        workflow_id=workflow_id,
        stage="stage1_file_identification",
        prompt=stage1_prompt,
        parent_interaction_id=parent_id,
        metadata={"problems_count": len(analysis_result.get("problems_and_solutions", []))}
    )

    start_time = time.time()
    stage1_response = self.ollama_manager.call_llm(
        stage1_prompt,
        "You are a Pegasus workflow debugging assistant. Identify which files are needed to fix errors."
    )
    latency_ms = (time.time() - start_time) * 1000

    if not stage1_response:
        # LOG FAILURE
        self.interaction_logger.log_llm_response(
            interaction_id=stage1_id,
            response=None,
            success=False,
            latency_ms=latency_ms,
            error="LLM not available for stage 1"
        )
        return await self.generate_plan_with_llm(analysis_result, catalogs, workflow_context, use_multi_stage=False)

    # Parse files needed
    files_needed = self._parse_files_needed(stage1_response)

    # LOG STAGE 1 RESPONSE
    self.interaction_logger.log_llm_response(
        interaction_id=stage1_id,
        response=stage1_response,
        success=True,
        latency_ms=latency_ms,
        parsed_plan={"files_identified": files_needed}
    )

    # LOG FILE FETCHING ACTION
    self.interaction_logger.log_action(
        action_type="file_fetch",
        description=f"Fetching {len(files_needed)} files identified by LLM",
        workflow_id=workflow_id,
        parent_interaction_id=stage1_id,
        metadata={"files": files_needed}
    )

    # Fetch files...
    fetched_files = await self._fetch_files(files_needed, workflow_id)

    # ===== STAGE 2: Generate Plan with Files =====
    stage2_prompt = self._build_plan_with_files_prompt(analysis_result, catalogs, workflow_context, fetched_files)

    # LOG STAGE 2 REQUEST (linked to stage 1)
    stage2_id = self.interaction_logger.log_llm_request(
        workflow_id=workflow_id,
        stage="stage2_plan_generation",
        prompt=stage2_prompt,
        parent_interaction_id=stage1_id,  # Link to parent
        metadata={
            "fetched_files_count": len(fetched_files),
            "files_requested": len(files_needed)
        }
    )

    start_time = time.time()
    stage2_response = self.ollama_manager.call_llm(stage2_prompt, self.prompt_builder.SYSTEM_PROMPT)
    latency_ms = (time.time() - start_time) * 1000

    if not stage2_response:
        # LOG FAILURE
        self.interaction_logger.log_llm_response(
            interaction_id=stage2_id,
            response=None,
            success=False,
            latency_ms=latency_ms,
            error="LLM not available for stage 2"
        )
        return self.generate_fallback_plan(analysis_result, workflow_context)

    # Parse plan
    plan = self.parse_llm_response(stage2_response)

    # ... validation and storage code ...

    # LOG STAGE 2 SUCCESS
    self.interaction_logger.log_llm_response(
        interaction_id=stage2_id,
        response=stage2_response,
        success=True,
        latency_ms=latency_ms,
        parsed_plan={
            "plan_id": plan.get("plan_id"),
            "actions_count": len(plan.get("actions", []))
        }
    )

    return plan
```

## Step 5: Add API Endpoints

**Add these functions to `planner_rest.py`:**

```python
async def get_workflow_interactions(request: web.Request) -> web.Response:
    """Get all LLM interactions for a specific workflow"""
    try:
        workflow_id = request.match_info['workflow_id']

        interactions = interaction_logger.get_workflow_interactions(workflow_id)

        return web.json_response({
            "success": True,
            "workflow_id": workflow_id,
            "agent": "Planner",
            "count": len(interactions),
            "interactions": interactions
        })
    except Exception as e:
        logger.error(f"Error getting workflow interactions: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def get_latest_interactions(request: web.Request) -> web.Response:
    """Get latest LLM interactions"""
    try:
        limit = int(request.query.get('limit', 50))

        interactions = interaction_logger.get_all_interactions(limit=limit)

        return web.json_response({
            "success": True,
            "agent": "Planner",
            "count": len(interactions),
            "interactions": interactions
        })
    except Exception as e:
        logger.error(f"Error getting latest interactions: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def get_interaction_statistics(request: web.Request) -> web.Response:
    """Get statistics about LLM interactions"""
    try:
        stats = interaction_logger.get_statistics()

        return web.json_response({
            "success": True,
            "statistics": stats
        })
    except Exception as e:
        logger.error(f"Error getting interaction statistics: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)
```

**Add routes in your app setup:**

```python
# In main() or wherever routes are defined
app.router.add_get('/api/planner/interactions/workflow/{workflow_id}', get_workflow_interactions)
app.router.add_get('/api/planner/interactions/latest', get_latest_interactions)
app.router.add_get('/api/planner/interactions/statistics', get_interaction_statistics)
```

## Testing

```bash
# Start Planner agent
cd /Users/hamzasafri/Desktop/AgentMape/Planner
python3 planner_rest.py

# Test endpoints:

# Get statistics
curl http://localhost:8082/api/planner/interactions/statistics

# Get latest interactions
curl http://localhost:8082/api/planner/interactions/latest?limit=10

# Get interactions for a specific workflow
curl http://localhost:8082/api/planner/interactions/workflow/YOUR_WORKFLOW_ID

# Check the database
cat planner_db.json | jq '.llm_interactions'
```

## Database Structure

The interactions will be stored in `planner_db.json`:

```json
{
  "plans": {...},
  "execution_requests": {...},
  "agents": {...},
  "llm_interactions": {
    "1": {
      "interaction_id": "uuid-456",
      "parent_interaction_id": null,
      "timestamp": "2025-02-21T21:35:00.123456",
      "agent": "Planner",
      "workflow_id": "4ddc0377-0222-447e-a6d4-5e83c8474dea",
      "stage": "single_stage",
      "direction": "request",
      "prompt": "Generate a repair plan...",
      "response": "Here is the plan...",
      "latency_ms": 2345.6,
      "success": true,
      "parsed_plan": {
        "plan_id": "plan-123",
        "actions_count": 3
      }
    }
  }
}
```

# 📋 LLM-Powered Planner Agent

The Planner Agent is part of the MAPE-K architecture for autonomous Pegasus workflow management. It receives analysis from the Analyzer agent and generates **executable repair plans** using AI (Ollama LLM).

## 🎯 Purpose

Transforms workflow failure **analysis** (what's wrong) into **actionable plans** (how to fix it) with:
- ✅ Specific bash/Pegasus commands
- ✅ Catalog-aware repairs (knows if catalogs are embedded or separate files)
- ✅ Risk assessment and validation
- ✅ Rollback strategies
- ✅ Auto-execution for low-risk plans

## 🏗️ Architecture

```
Analyzer → completes analysis
     ↓ (webhook)
Planner → generates repair plan with LLM
     ↓ (if auto-approved)
Executor → executes the plan
```

## 📁 Files

- **`planner_rest.py`** - Main planner agent with LLM integration
- **`planner_config.json`** - Configuration (Ollama URL, ports, settings)
- **`planner_db.json`** - TinyDB database (auto-created)

## ⚙️ Configuration (`planner_config.json`)

```json
{
    "ollama_url": "https://...pinggy.link/api/generate",
    "ollama_model": "llama3:latest",
    "http_port": 8082,
    "auto_approve_low_risk": true,
    "auto_approve_confidence_threshold": 0.75
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `ollama_url` | - | Ollama API URL for LLM |
| `ollama_model` | `llama3:latest` | LLM model to use |
| `http_port` | `8082` | HTTP server port |
| `auto_approve_low_risk` | `true` | Auto-execute low-risk plans |
| `auto_approve_confidence_threshold` | `0.75` | Min confidence for auto-execution |

## 🚀 Usage

### Start the Planner

```bash
cd /Users/hamzasafri/Desktop/AgentMape/Planner
python planner_rest.py
```

**Expected output:**
```
✓ LLM-Powered Planner Agent Started
================================================================================
🌐 HTTP API: http://localhost:8082
🦙 Ollama Model: llama3:latest
🔗 Ollama URL: https://...pinggy.link/api/generate
✅ Ollama: Connected

📋 Available Endpoints:
   POST /webhooks/analysis-complete - Receive analysis from Analyzer
   POST /api/create-plan - Manually create plan
   GET  /api/plans - List all plans
   GET  /api/plans/{id} - Get specific plan
   POST /api/plans/{id}/approve - Approve plan for execution
   GET  /health - Health check
```

### Workflow (Automatic)

1. **Analyzer completes analysis**
   ```
   Analyzer detects workflow failure
   → Runs pegasus-analyzer
   → Sends logs to LLM
   → Gets structured analysis
   → Sends webhook to Planner
   ```

2. **Planner receives webhook**
   ```
   POST http://localhost:8082/webhooks/analysis-complete
   {
     "workflow_id": "wf_123",
     "result": { analysis data },
     "catalogs": { catalog information }
   }
   ```

3. **Planner generates plan with LLM**
   ```
   → Builds context-rich prompt with catalog info
   → Calls Ollama LLM
   → Parses JSON plan
   → Validates plan
   → Assesses risk
   ```

4. **Plan output**
   ```
   📋 REPAIR PLAN GENERATED
   ================================================================================
   Plan ID: plan-uuid-...
   Workflow ID: wf_123
   Summary: Add missing file to replica catalog and resubmit
   Strategy: automatic
   Risk Level: low
   Auto Execute: True

   🔧 Repair Steps:
     Step 1: Backup replica catalog
       $ cp /workflow/rc.txt /workflow/rc.txt.backup

     Step 2: Add data.csv entry to replica catalog
       $ echo 'data.csv file:///data/input.csv local' >> /workflow/rc.txt

     Step 3: Resubmit workflow
       $ pegasus-run /workflow/dir

   📊 Confidence: 0.92
   ================================================================================
   ```

5. **Auto-execution** (if risk is low)
   ```
   ✅ Plan approved for auto-execution
   → Sends execution request to Executor
   ```

## 📊 Example Plans

### Example 1: Missing Replica Entry (Text Catalog)

**Analysis Input:**
```json
{
  "problem": "Input file 'data.csv' not found",
  "error_level": "replica",
  "catalogs": {
    "replica_catalog": {
      "path": "/workflow/rc.txt",
      "format": "text",
      "embedded": false
    }
  }
}
```

**Generated Plan:**
```json
{
  "plan_summary": "Add data.csv to replica catalog and resubmit",
  "risk_level": "low",
  "repair_steps": [
    {
      "step_number": 1,
      "commands": ["cp /workflow/rc.txt /workflow/rc.txt.backup"],
      "validation_command": "test -f /workflow/rc.txt.backup"
    },
    {
      "step_number": 2,
      "commands": ["echo 'data.csv file:///data/input.csv local' >> /workflow/rc.txt"],
      "validation_command": "grep 'data.csv' /workflow/rc.txt"
    },
    {
      "step_number": 3,
      "commands": ["pegasus-run /workflow/dir"],
      "validation_command": "pegasus-status /workflow/dir | grep Running"
    }
  ],
  "confidence_score": {"score": 0.92},
  "requires_approval": false
}
```

### Example 2: Memory Issue (Embedded Site Catalog)

**Analysis Input:**
```json
{
  "problem": "Job held due to insufficient memory",
  "error_level": "site",
  "catalogs": {
    "site_catalog": {
      "path": "embedded.sites",
      "format": "yaml",
      "embedded": true,
      "parent_file": "/workflow/workflow.yml"
    }
  }
}
```

**Generated Plan:**
```json
{
  "plan_summary": "Increase memory allocation and release held jobs",
  "risk_level": "medium",
  "repair_steps": [
    {
      "step_number": 1,
      "commands": ["cp /workflow/workflow.yml /workflow/workflow.yml.backup"],
      "validation_command": "test -f /workflow/workflow.yml.backup"
    },
    {
      "step_number": 2,
      "commands": [
        "yq eval '.sites[0].profiles.condor.request_memory = \"8GB\"' -i /workflow/workflow.yml"
      ],
      "validation_command": "yq eval '.sites[0].profiles.condor.request_memory' /workflow/workflow.yml"
    },
    {
      "step_number": 3,
      "commands": ["condor_release -constraint 'DAGManJobId =?= <cluster_id>'"],
      "validation_command": "condor_q | grep -v Held"
    }
  ],
  "confidence_score": {"score": 0.78},
  "requires_approval": true
}
```

## 🔍 API Endpoints

### Health Check
```bash
curl http://localhost:8082/health
```

### Manual Plan Creation
```bash
curl -X POST http://localhost:8082/api/create-plan \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_result": {...},
    "catalogs": {...},
    "workflow_context": {
      "workflow_id": "wf_123",
      "workflow_dir": "/path/to/workflow"
    }
  }'
```

### List All Plans
```bash
curl http://localhost:8082/api/plans
```

### Get Specific Plan
```bash
curl http://localhost:8082/api/plans/{plan_id}
```

### Approve Plan
```bash
curl -X POST http://localhost:8082/api/plans/{plan_id}/approve
```

## 🧠 LLM Prompt Strategy

The Planner builds intelligent prompts that include:

1. **Workflow Context**
   - Workflow ID, directory, state

2. **Catalog Information** (catalog-aware!)
   - Location (embedded vs separate)
   - Format (text, YAML, XML)
   - Correct commands for each type

3. **Analysis Results**
   - Problems identified
   - Error levels
   - Priorities

4. **Command Examples**
   - Text catalog: `echo 'lfn pfn site' >> rc.txt`
   - YAML catalog: `yq eval '.replicaCatalog.replicas += [...]' -i workflow.yml`

## 🛡️ Risk Assessment

Plans are automatically categorized:

| Risk Level | Auto-Execute | Requires Approval | Examples |
|-----------|--------------|-------------------|----------|
| **Low** | ✅ Yes (if confidence > 0.75) | No | Add replica entry, resubmit workflow |
| **Medium** | ⚠️ With notification | Yes | Modify site resources, change TC |
| **High** | ❌ No | Yes | Dangerous commands, low confidence |

### Safety Checks:
- ✅ Dangerous command detection (`rm -rf`, `dd`, etc.)
- ✅ Confidence threshold validation
- ✅ Rollback strategy required
- ✅ Command syntax verification

## 🐛 Troubleshooting

### "Ollama not available"
```
⚠ Ollama: Not available (fallback mode)
```
**Fix:** Check Ollama URL in config, verify Ollama is running

### "Manual intervention required"
- LLM unavailable → Falls back to manual review
- Low confidence → Requires human approval
- High risk commands detected

### Plans not generating
1. Check Analyzer is sending webhooks
2. Check Planner is receiving on port 8082
3. Check `planner_db.json` for stored plans
4. Check logs: `tail -f analyzer_agent.log`

## 📈 Next Steps

After plan generation:
1. ✅ **Executor Agent** - Executes approved plans
2. ✅ **Knowledge Base** - Learns from successful repairs
3. ✅ **Feedback Loop** - Improves planning over time

## 🔗 Integration

### With Analyzer
Analyzer automatically sends webhook after analysis completion.

### With Executor (Coming Soon)
Planner will send execution requests to Executor agent.

### With Monitor
Monitor triggers the whole chain via held/failed workflow detection.

---

**Status:** ✅ Fully implemented with LLM-powered plan generation and catalog awareness!

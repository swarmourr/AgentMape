# MAPE-K Autonomous Workflow Management System
## Project Summary & Future Improvements

---

## What We Built

An autonomous system that automatically diagnoses and repairs failed scientific workflows using Large Language Models (LLMs) and the MAPE-K pattern (Monitor-Analyze-Plan-Execute-Knowledge).

### Current System

**Monitor Agent:**
- Detects workflow failures in real-time
- Extracts stderr from job .out files
- Maps temporary execution paths (/srv/) to real source file paths
- Collects workflow metadata (transformations, replicas, catalogs)
- Sends data to Analyzer via REST API

**Analyzer Agent:**
- Receives workflow failure data with real stderr output
- Uses LLM (Ollama + Llama 3.3) to diagnose root causes
- Distinguishes real errors from cascade symptoms
- Prioritizes stderr data over pegasus-analyzer logs
- Identifies whether errors are fixable automatically
- Sends analysis to Planner

**Planner Agent:**
- Receives analysis with root cause identification
- Uses LLM to generate corrective plans
- Multi-stage planning: identify files → fetch files → create plan
- Catalog-aware: uses workflow transformations and replicas
- Generates actionable fixes (file edits, catalog updates, resource changes)

**Current Status:**
- ✅ Monitor extracts real error data from .out files
- ✅ Monitor maps temporary paths to real PFNs
- ✅ Analyzer prioritizes stderr over cascade errors
- ✅ Planner generates catalog-aware plans
- ❌ No automatic execution (plans must be applied manually)
- ❌ Uses REST API (polling-based, not event-driven)

---

## Key Problems Solved

### 1. Real Error Data vs Log Messages

**Problem:**
- Pegasus-analyzer only shows cascade errors ("file transfer failed")
- Real root cause hidden in .out files ("SyntaxError at line 105")
- LLM was analyzing wrong information

**Solution:**
- Monitor extracts stderr from .out files automatically
- Sends real error data to Analyzer
- LLM sees actual Python errors, not Pegasus logs

**Impact:**
- Analyzer can identify exact line with error
- Distinguishes symptoms from root causes
- Much more accurate diagnosis

### 2. Temporary Path vs Real Source Path

**Problem:**
- Transformations show `/srv/FineTuneLLM` (temporary execution path)
- This path doesn't exist after job completes
- Planner can't request the actual source file

**Solution:**
- Monitor extracts transformation PFNs from workflow YAML
- Maps job name (FineTuneLLM_ID0000001) to transformation name (FineTuneLLM)
- Resolves real path (e.g., `/home/user/scripts/FineTuneLLM`)
- Sends real path in job_out_files data

**Impact:**
- Analyzer sees real source file location
- Planner can request actual files
- No more placeholder paths like `/absolute/path/to/...`

### 3. Planner Requesting Workflow YAML

**Problem:**
- Analyzer LLM requests `workflow.yml` or `braindump.yml` unnecessarily
- Planner already has workflow YAML from Monitor
- Wastes time fetching files that are already available

**Solution:**
- Enhanced Analyzer prompt with explicit instructions:
  - "Planner ALREADY HAS workflow YAML"
  - "DO NOT request workflow.yml or braindump.yml"
  - "Use empty array [] for most errors"
- Clear guidance on when to request files (only for SyntaxErrors)

**Impact:**
- Analyzer stops requesting redundant files
- Faster planning process
- Clearer separation of responsibilities

### 4. Cascade Errors vs Root Causes

**Problem:**
- Job fails with SyntaxError (root cause)
- pegasus-analyzer reports "missing file: model.zip" (cascade symptom)
- LLM focuses on missing file instead of syntax error

**Solution:**
- Analyzer prompt prioritizes stderr over pegasus-analyzer
- Clear instruction: "stderr shows root cause, pegasus-analyzer shows cascade"
- Example in prompt: "Fix the ImportError, NOT the missing file"

**Impact:**
- LLM correctly identifies root causes
- Generates fixes for real problems
- Stops chasing symptoms

---

## Current Limitations

### 1. No Automatic Execution
**Issue:** Planner generates fix plans but doesn't execute them
**Impact:** Requires manual intervention to apply fixes
**Status:** Plans sit idle in database

### 2. REST API Communication
**Issue:** Agents use HTTP polling instead of event-driven architecture
**Impact:** Slower response times, more overhead
**Status:** Works but not optimal

### 3. Limited Testing
**Issue:** Only tested on simple workflows with known errors
**Impact:** Unknown behavior on complex real-world workflows
**Status:** Need comprehensive test suite

### 4. Planner Uses braindump.yml
**Issue:** Planner fallback logic picks braindump.yml instead of workflow.yml
**Impact:** Can't find transformation catalog, requests workflow YAML
**Status:** Bug in Planner's YAML discovery logic

### 5. No Learning from History
**Issue:** System doesn't learn from past failures
**Impact:** Makes same mistakes repeatedly
**Status:** No persistent knowledge base

---

## How to Improve

### Improvement 1: Implement Executor Agent

**What:**
Add fourth agent that automatically executes Planner's corrective plans

**Why:**
- Close the MAPE-K loop (currently stops at Plan)
- Enable true autonomous recovery
- Reduce manual intervention to zero

**How:**
```
Executor receives plan from Planner
  ↓
Validate plan safety (no destructive actions)
  ↓
Create backup for rollback
  ↓
Execute actions (edit files, update catalogs)
  ↓
If error: rollback to backup
  ↓
Resubmit workflow using pegasus-run
  ↓
Report status to Monitor
```

**Key Features:**
- **Safety validation**: Prevent destructive commands (rm -rf, DROP TABLE)
- **Atomic operations**: All-or-nothing execution with rollback
- **Path restrictions**: Can't modify /etc, /usr, /bin
- **File existence checks**: Verify files exist before editing

**Benefits:**
- Workflow automatically recovers without human intervention
- Safe execution with rollback on failure
- Complete MAPE-K autonomic loop

### Improvement 2: Migrate to MCP Protocol

**What:**
Replace REST API with Model Context Protocol (MCP)

**Why:**
- Industry-standard protocol for LLM-agent communication
- Native context management
- Automatic tool discovery
- Less boilerplate code

**Current (REST):**
```python
# Manual HTTP requests
response = requests.post("http://analyzer:8082/analyze",
                        json={"workflow_id": id, "data": data})
```

**Future (MCP):**
```python
# Declarative tool calling
result = await client.call_tool("analyze_workflow",
                                workflow_id=id)
```

**Benefits:**
- Standardized communication protocol
- Better context awareness
- Easier to add new agents
- Reduced network overhead

### Improvement 3: Event-Driven Architecture (Pub/Sub)

**What:**
Replace HTTP polling with publish/subscribe event bus

**Why:**
- Real-time notifications instead of polling
- Agents don't need to know about each other
- Scale to many agents easily

**Current (Polling):**
```
Analyzer: "Hey Planner, do you have any work for me?"
Planner: "Not yet"
(wait 5 seconds)
Analyzer: "How about now?"
Planner: "Not yet"
(repeat...)
```

**Future (Pub/Sub):**
```
Monitor publishes: "workflow.failed" event
  ↓
Analyzer subscribed → receives notification immediately
  ↓
Analyzer publishes: "analysis.completed" event
  ↓
Planner subscribed → receives notification immediately
```

**Benefits:**
- Faster response times
- Less network traffic
- Better scalability
- Decoupled agents

### Improvement 4: Fix Planner YAML Discovery

**What:**
Stop Planner from using braindump.yml instead of workflow.yml

**Why:**
- braindump.yml has no transformation/replica catalogs
- Causes Planner to think it needs workflow YAML
- Wrong file leads to incorrect analysis

**How:**
1. Trust Monitor's metadata (workflow_yaml_path field)
2. Exclude braindump.* from YAML search
3. Validate file has transformations/jobs sections

**Code Change:**
```python
# BEFORE: Searches all .yml files, picks braindump.yml
yaml_files = glob.glob("*.yml")  # Finds braindump.yml

# AFTER: Exclude braindump, trust metadata
workflow_yaml_path = metadata.get('workflow_yaml_path')  # From Monitor
if not workflow_yaml_path:
    yaml_files = [f for f in glob.glob("*.yml")
                  if 'braindump' not in f]  # Exclude braindump
```

**Benefits:**
- Planner has correct workflow file
- Can find transformations and replicas
- Stops requesting workflow YAML unnecessarily

### Improvement 5: Comprehensive Testing

**What:**
Test system on many different workflows and failure types

**Why:**
- Current testing: 1-2 simple workflows with known errors
- Real workflows: complex dependencies, multiple failure modes
- Need to validate before production deployment

**Test Categories:**

**Simple Workflows (Baseline):**
- Single job with SyntaxError
- Single job with missing file
- Single job with out-of-memory error

**Parallel Workflows:**
- Multiple jobs fail simultaneously
- Fan-out pattern (1 job → 10 parallel jobs)
- Fan-in pattern (10 jobs → 1 merge job)

**Complex Workflows:**
- Multi-stage ML pipelines (preprocess → train → evaluate)
- Conditional execution (if/else branches)
- Dynamic job generation (parameterized jobs)

**Production Workflows:**
- Real scientific workflows (astronomy, bioinformatics, climate)
- 1000+ jobs
- Multiple failure points

**Failure Scenarios:**
- Code errors: SyntaxError, ImportError, RuntimeError, TypeError
- Resource errors: OOM, disk quota, CPU timeout, GPU unavailable
- Data errors: missing files, corrupted data, wrong format, permissions
- Config errors: wrong transformation PFN, missing catalog entries
- Cascade errors: upstream failure propagation, retry exhaustion

**Metrics to Measure:**
- **Root cause accuracy**: Did Analyzer identify correct root cause? (Target: >85%)
- **Fix success rate**: Did workflow complete after fix? (Target: >70%)
- **Time to recovery**: Detection → fix → completion (Target: <5 min)
- **False positives**: Incorrect error classifications (Target: <10%)
- **Unrecoverable failures**: Require human intervention (Target: <20%)

**Benefits:**
- Validate system reliability
- Find edge cases and bugs
- Build confidence for production
- Collect data for research paper

### Improvement 6: LLM Prompt Optimization

**What:**
Iteratively improve LLM prompts based on test results

**Why:**
- Current prompts work for simple cases
- May fail on complex/ambiguous errors
- Need to refine based on real failures

**Approach:**
1. Run test suite, collect failed cases
2. Analyze why LLM misdiagnosed
3. Update prompt with examples from failures
4. Re-run tests, measure improvement
5. Repeat until metrics meet targets

**Example Refinements:**
- Add more examples of cascade vs root cause
- Clarify when files are needed vs not needed
- Show examples of complex error patterns
- Guide LLM on ambiguous cases

**Benefits:**
- Higher accuracy over time
- Handle more complex errors
- Reduce false positives
- Better generalization

### Improvement 7: Add Learning/Knowledge Base

**What:**
Store past failures and fixes, use for future diagnoses

**Why:**
- Same errors occur repeatedly (e.g., common typos)
- Learn patterns over time
- Suggest fixes based on history

**Architecture:**
```
Knowledge Base (Database)
  ├── past_failures: workflow_id, error_type, root_cause, stderr
  ├── successful_fixes: workflow_id, fix_applied, fix_worked
  └── error_patterns: error_signature → common_root_causes
```

**Usage:**
```
New failure detected
  ↓
Search knowledge base for similar errors
  ↓
If found: suggest known fix
  ↓
If not found: use LLM analysis
  ↓
After fix: store in knowledge base
```

**Benefits:**
- Faster diagnosis for common errors
- Learn from experience
- Reduce LLM calls (cost savings)
- Build institutional knowledge

### Improvement 8: Multi-Agent Coordination

**What:**
Enable agents to negotiate and collaborate on complex problems

**Why:**
- Some failures need multiple perspectives
- Agents may disagree on diagnosis
- Coordination improves accuracy

**Example:**
```
Monitor: "Job failed, here's the data"
  ↓
Analyzer 1: "I think it's a SyntaxError" (confidence: 70%)
Analyzer 2: "I think it's a missing file" (confidence: 65%)
  ↓
Coordinator: "Let's get more data - request full script"
  ↓
With more context:
Analyzer 1: "Confirmed SyntaxError" (confidence: 95%)
Analyzer 2: "You're right, missing file was cascade" (confidence: 40%)
  ↓
Planner: Receives consensus diagnosis
```

**Coordination Protocols:**
- **Voting**: Multiple analyzers vote, highest confidence wins
- **Delegation**: Coordinator assigns specialist analyzer based on error type
- **Consensus**: Require agreement threshold before proceeding
- **Escalation**: If agents can't agree, request human input

**Benefits:**
- Higher accuracy through consensus
- Reduced false positives
- Handle ambiguous cases better
- Leverage multiple LLM models

### Improvement 9: Dashboard & Visualization

**What:**
Web dashboard showing MAPE-K loop in real-time

**Why:**
- Hard to understand system behavior from logs
- Users want to see what's happening
- Debugging requires visibility

**Features:**
- **Workflow Status**: All monitored workflows, color-coded by state
- **Agent Activity**: Real-time view of what each agent is doing
- **MAPE-K Loop Visualization**: Show data flow between agents
- **Failure Timeline**: Chronological view of failure → diagnosis → fix → recovery
- **Metrics Dashboard**: Success rates, response times, error distributions
- **Plan History**: All generated plans, which were executed, outcomes

**Benefits:**
- Better user experience
- Easier debugging
- Transparency in autonomous actions
- Trust building

### Improvement 10: Safety & Guardrails

**What:**
Add multiple safety layers to prevent harmful actions

**Why:**
- Autonomous execution can be dangerous
- LLMs can hallucinate destructive commands
- Need to protect user data and systems

**Safety Layers:**

**Layer 1: Static Analysis**
- Blacklist dangerous commands (rm -rf, DROP TABLE, chmod 777)
- Whitelist allowed paths (only workflow directories)
- Validate file paths exist before modification

**Layer 2: Dry-Run Mode**
- Simulate plan execution without making changes
- Show what would happen
- Require user approval for actual execution

**Layer 3: Rollback Capability**
- Backup all files before modification
- Atomic operations (all succeed or all rollback)
- Keep backups for 7 days

**Layer 4: Human-in-the-Loop**
- Flag high-risk plans for human review
- Require approval for certain action types
- Emergency stop button

**Layer 5: Audit Trail**
- Log all actions taken
- Record before/after states
- Enable forensic analysis

**Benefits:**
- Safe autonomous operation
- User confidence in system
- Compliance with policies
- Recovery from mistakes

---

## Prioritized Roadmap

### Phase 1: Critical Fixes (Now)
1. Fix Planner braindump.yml bug
2. Deploy Monitor + Analyzer with PFN mapping to server
3. Test on 5-10 simple workflows

### Phase 2: Close the Loop (1-2 months)
1. Implement Executor agent
2. Add safety validation
3. Test automatic recovery

### Phase 3: Scale & Test (2-3 months)
1. Comprehensive test suite (50+ workflows)
2. Iterate on prompts based on failures
3. Measure and optimize metrics

### Phase 4: Production Ready (3-6 months)
1. Migrate to MCP protocol
2. Add pub/sub event bus
3. Deploy dashboard
4. Production deployment

### Phase 5: Advanced Features (6-12 months)
1. Learning from history
2. Multi-agent coordination
3. Fine-tune LLM on workflow errors
4. Publish research paper

---

## Success Metrics

**Technical Metrics:**
- Root cause identification accuracy: **>85%**
- Automatic fix success rate: **>70%**
- Average time to recovery: **<5 minutes**
- False positive rate: **<10%**

**User Metrics:**
- Reduction in manual debugging time: **>80%**
- Increase in workflow success rate: **>30%**
- User satisfaction score: **>4/5**

**Research Metrics:**
- Paper published in top-tier venue (HPDC, SC, eScience)
- System adopted by other institutions
- Open source community engagement

---

## How to Use This Document

**For Development:**
- Use "How to Improve" section as implementation guide
- Follow "Prioritized Roadmap" for sequencing
- Check "Success Metrics" for validation

**For Proposals:**
- Use "What We Built" to show current achievements
- Use "Current Limitations" to justify future work
- Use "How to Improve" to outline proposed research

**For Papers:**
- "Key Problems Solved" → Contributions section
- "How to Improve" → Future Work section
- "Success Metrics" → Evaluation section

**For Users:**
- "What We Built" → System overview
- "Current Limitations" → Known issues
- "Prioritized Roadmap" → When features will be available

---

## Key Takeaways

**What Works Well:**
- ✅ Real error data extraction from .out files
- ✅ PFN mapping from temporary to real paths
- ✅ LLM-based root cause analysis
- ✅ Catalog-aware planning

**What Needs Improvement:**
- ❌ No automatic execution (manual intervention required)
- ❌ REST API instead of event-driven architecture
- ❌ Limited testing on real workflows
- ❌ Planner YAML discovery bug
- ❌ No learning from history

**Most Important Next Steps:**
1. **Fix braindump.yml bug** (affects Planner immediately)
2. **Implement Executor** (closes MAPE-K loop)
3. **Comprehensive testing** (validates before production)

**Biggest Impact Improvements:**
1. **Executor**: Enables true autonomous recovery
2. **Event-driven architecture**: 10x faster response times
3. **Learning from history**: Improves over time automatically

---

## Conclusion

We have built a functional MAPE-K system that can automatically diagnose workflow failures using LLMs. The system successfully extracts real error data, maps paths correctly, and generates corrective plans.

The next critical step is implementing the Executor to close the autonomic loop and enable true self-healing workflows. Following that, comprehensive testing and migration to event-driven architecture will make the system production-ready.

With these improvements, the system can reduce manual debugging time by 80% and enable autonomous operation of complex scientific workflows.

---

**Document Version:** 1.0
**Date:** January 30, 2025
**Status:** Living document - update as system evolves

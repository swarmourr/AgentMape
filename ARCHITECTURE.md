# PegasusAgent — Architecture Reference

> Auto-healing agent for Pegasus WMS / HTCondor workflows.
> Triggered by DAGMan as a POST script on every job exit.
> No API server required — runs entirely in-process.

---

## System Architecture

```mermaid
flowchart LR
    WF(["Scientist\nsubmits workflow"])

    subgraph PEG["  Pegasus WMS  "]
        PLAN["pegasus-plan\n.dag  .sub  files"]
    end

    subgraph HTC["  HTCondor / DAGMan  "]
        direction TB
        DAGMAN["DAGMan\norchestrates retries"]
        SLOT["Compute slot\nexecutes job"]
        DAGMAN -->|submit| SLOT
    end

    subgraph HEALER["  PegasusAgent Healer  "]
        direction TB

        POST["POST script\npegasus_post_script.py"]

        subgraph FAST_PATH["Fast paths  (no agent)"]
            direction LR
            FP1["healer tag\nstop / no-fix"]
            FP2["sibling marker\nalready patched"]
        end

        subgraph AGENT["Remediation agent  (LangGraph)"]
            direction LR
            DIAG["Diagnostic loop\nrule classifier  →  LLM ReAct"]
            ACT["Action loop\nfix catalog  →  policy gate  →  apply"]
            OUT["Outcome loop\nevaluate  →  write memory"]
            DIAG --> ACT --> OUT
        end

        POST --> FAST_PATH
        POST --> AGENT
    end

    subgraph STORAGE["  Persistent storage  "]
        direction TB
        SUB[".sub files\npatched resource requests"]
        MEM["memory.db\nepisodic fix history"]
        CHK["checkpoint.db\nLangGraph state"]
        LOGS[".healer.log\n.agent_report"]
    end

    LLM(["LLM provider\nLiteLLM / Anthropic\n(optional)"])

    WF --> PEG --> DAGMAN
    SLOT -->|"job exits\n(success or fail)"| POST

    FAST_PATH -->|"exit 1 — retry\nno agent run"| DAGMAN
    AGENT -->|"AUTO  exit 1\npatch .sub + retry"| DAGMAN
    AGENT -->|"ASK   exit ≠0\nproposal report"| DAGMAN
    AGENT -->|"STOP  exit ≠0\nescalate"| DAGMAN

    ACT -->|patches| SUB
    SUB -->|"DAGMan reads\non next submit"| SLOT
    OUT -->|stores episode| MEM
    AGENT <-->|resume / save| CHK
    POST -->|writes| LOGS

    DIAG -.->|"LLM fallback\nambiguous failures"| LLM
    ACT  -.->|"LLM fallback\nunknown fix"| LLM

    classDef ext     fill:#6c757d,color:#fff,stroke:none
    classDef healer  fill:#1d3557,color:#fff,stroke:none
    classDef fast    fill:#e9c46a,color:#222,stroke:none
    classDef loop    fill:#2d6a4f,color:#fff,stroke:none
    classDef store   fill:#457b9d,color:#fff,stroke:none
    classDef llmnode fill:#e63946,color:#fff,stroke:none

    class WF,SLOT,DAGMAN ext
    class POST healer
    class FP1,FP2 fast
    class DIAG,ACT,OUT loop
    class SUB,MEM,CHK,LOGS store
    class LLM llmnode
```

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [POST Script — Entry Point](#2-post-script--entry-point)
3. [Evidence Collection](#3-evidence-collection)
4. [The Two-Loop LangGraph](#4-the-two-loop-langgraph)
5. [Diagnostic Loop](#5-diagnostic-loop)
   - [Rule Classifier](#51-rule-classifier)
   - [LLM Diagnosis Agent (ReAct)](#52-llm-diagnosis-agent-react)
6. [Action Loop](#6-action-loop)
   - [Fix Catalog](#61-fix-catalog)
   - [LLM Fix Planner](#62-llm-fix-planner)
   - [Policy Engine](#63-policy-engine)
   - [Apply Fix + Sibling Broadcast](#64-apply-fix--sibling-broadcast)
7. [Thread & Checkpoint System](#7-thread--checkpoint-system)
8. [Memory System](#8-memory-system)
9. [Sub File Patching](#9-sub-file-patching)
10. [Exit Code Contract](#10-exit-code-contract)
11. [Demo Workflows](#11-demo-workflows)
12. [Known Limitations](#12-known-limitations)

---

## 1. System Overview

```
Pegasus WMS plans a DAG → HTCondor executes jobs → job fails
                                                          │
                                           DAGMan calls POST script
                                                          │
                                           pegasus_post_script.py
                                                          │
                                    ┌─────────────────────┴──────────────────────┐
                                    │         LangGraph remediation graph         │
                                    │  collect → classify → fix → apply → retry  │
                                    └─────────────────────┬──────────────────────┘
                                                          │
                          ┌───────────────────────────────┼───────────────────────┐
                          │                               │                       │
                    exit 1 (AUTO)                   exit 0 (ASK)           exit 0 (STOP)
                    DAGMan retries             proposal written           workflow ends
                    patched .sub              human applies fix
```

**Key design decisions:**

| Decision | Rationale |
|---|---|
| POST script, not daemon | No server to maintain; DAGMan manages lifecycle |
| In-process LangGraph | No IPC, no network; graph state in SQLite checkpoint |
| Rules-first, LLM-fallback | Fast + cheap for known failures; LLM only for ambiguous ones |
| Deterministic policy gate | LLM can never auto-apply forbidden actions regardless of output |
| Sibling broadcast | One agent run fixes the whole parallel family |

---

## 2. POST Script — Entry Point

**File:** `scripts/pegasus_post_script.py`

DAGMan calls this script after every job exits (success or failure).

### Invocation signature

```
python pegasus_post_script.py $RETURN $JOB $RETRY $MAX_RETRIES <submit_dir> <wf_uuid>
```

DAGMan substitutes `$RETURN` (exit code), `$JOB` (job name), `$RETRY` (retry count) at runtime.

### Execution flow

```mermaid
flowchart TD
    A[DAGMan calls POST script] --> B[call pegasus-exitcode\ncreates .meta for stage_out]
    B --> C[open .healer.log next to .out/.err]
    C --> D{healer tag\nin .sub?}
    D -- stop tag --> E[exit 0 — abort workflow]
    D -- no tag --> F{sibling marker\nfast path?}
    F -- marker exists\n+ .sub patched\n+ exit code matches --> G[exit 1 — retry immediately\nno agent run]
    F -- no fast path --> H[resolve thread_id\nfrom .healer_thread file]
    H --> I[collect evidence\nfrom submit dir]
    I --> J[run LangGraph\nremediation graph]
    J --> K{policy decision}
    K -- AUTO --> L[exit 1 — DAGMan retries]
    K -- ASK --> M{job failed?}
    M -- yes --> N[exit original code\nproposal in report]
    M -- no --> O[exit 0]
    K -- STOP / ESCALATE --> P{job failed?}
    P -- yes --> Q[exit original code]
    P -- no --> R[exit 0]
```

### Key functions

| Function | Responsibility |
|---|---|
| `_call_pegasus_exitcode()` | Runs `/usr/bin/pegasus-exitcode job.out` to create `.meta` checksum files that stage_out requires |
| `_find_job_subdir()` | Locates the `00/00/` subdirectory containing the job's `.sub` file |
| `_open_log()` | Opens `{job_id}.healer.log` next to `.out/.err` for persistent tracing |
| `_resolve_thread()` | Returns `(thread_id, is_resume)` — thread_id = `{wf_uuid}/{job_id}/{instance_id}` |
| `_marker_fast_path()` | Checks if sibling broadcast already fixed this job — skips agent entirely |
| `_run()` | Async: collects evidence, builds services, invokes graph, returns exit code |

### Files written next to `.out` / `.err`

```
00/00/
  compute_compute_A.out          ← HTCondor/kickstart output
  compute_compute_A.err          ← HTCondor stderr
  compute_compute_A.healer.log   ← healer trace (every invocation appended)
  compute_compute_A.healer_thread← thread_id for LangGraph checkpoint resume
  compute_compute_A.agent_report ← structured JSON report (diagnosis + fix)
  compute_compute_A.meta         ← created by pegasus-exitcode (output checksums)
```

---

## 3. Evidence Collection

**File:** `app/utils/collectors/submit_dir.py`

Called synchronously before the graph runs. Reads all diagnostic files from the submit directory and returns a `RawEvidence` model.

```mermaid
flowchart LR
    subgraph submit_dir[Submit Directory  00/00/]
        sub[job.sub]
        out[job.out\nkickstart YAML / XML]
        err[job.err\nstderr]
        lof[job.in.lof\ninput list]
        log[job.log\nHTCondor event log]
    end

    subgraph extra[Workflow-level]
        dag[dagman.out]
        monitord[monitord.log]
    end

    subgraph external[External]
        analyzer[pegasus-analyzer\nCLI subprocess]
        condor[condor_history\nclassads]
    end

    submit_dir --> E[collect_evidence]
    extra --> E
    external --> E
    E --> RawEvidence
```

**Available sources** (reported in healer log):
- `pegasus_analyzer` — structured failure summary from `pegasus-analyzer`
- `stderr` — raw stderr content (up to 200 KB)
- `stdout_kickstart` — kickstart `.out` file with timing and exit codes
- `submit_file` — HTCondor `.sub` file (resource requests, tags)
- `dagman_log` — DAGMan `.out` for retry history
- `transformation_script` — the actual executable script

In `collect_context` node, `RawEvidence` enriches `FailureContext` with:
- `job_tags` — from `+PegasusHealerTags` in `.sub`
- `stderr_excerpt` — last 3000 chars of stderr (for rule classifier pattern matching)
- `requested_resources` — from `.sub` (not condor_history, which has pre-patch values)
- `transformation` — parsed from executable path in `.sub`

### Kickstart output format

Pegasus 5.x writes the `.out` file in **YAML** format; Pegasus 4.x used XML `<invocation>` elements. The agent handles both automatically.

**YAML structure (Pegasus 5.x):**

```yaml
- invocation: True
  mainjob:
    usage:
      maxrss: 262144      # KB — peak RSS → peak_memory_mb
      utime: 1.23         # user CPU time
      stime: 0.45         # system CPU time
    status:
      regular_exitcode: 0          # normal exit
      # or: signal_number: 9       # SIGKILL → exit_signal + exit_code 137
    duration: 294.0                # wall time in seconds
  files:
    filename.gz:
      error: 2                     # non-zero → transfer failure
  stderr:
    data: |                        # ← full application stderr embedded here
      INFO: Reading URL pairs...
      ERROR: Transfer failed
      Killed
  stdout:
    size: 0
    data: |                        # ← full application stdout (if any)
      ...
```

The `stderr.data` block is the **primary diagnostic source** for transfer failures, application crashes, and OOM kills — more complete than the `.err` file, which often only contains HTCondor bookkeeping. `get_kickstart_data` extracts both `stderr_data` and `stdout_data`. `get_stderr` falls back to `stderr_data` from the YAML automatically when the `.err` file is empty.

---

## 4. The Two-Loop LangGraph

**File:** `app/graph/graph.py`

The graph has two loops connected through `evaluate_outcome`:

```mermaid
flowchart TD
    START --> entry{route_entry}
    entry -- fresh failure --> collect_context
    entry -- resume after retry --> evaluate_outcome

    collect_context --> run_rule_classifier

    run_rule_classifier -- rule matched\nconfidence ≥ 0.85 --> lookup_fix_catalog
    run_rule_classifier -- no match --> retrieve_memories
    run_rule_classifier -- no evidence --> handle_insufficient_evidence

    retrieve_memories --> run_diagnosis_agent
    run_diagnosis_agent --> lookup_fix_catalog

    lookup_fix_catalog -- known fix --> validate_policy
    lookup_fix_catalog -- unknown --> run_fix_planner
    run_fix_planner --> validate_policy

    validate_policy -- AUTO --> apply_fix
    validate_policy -- ASK --> generate_proposal_report
    validate_policy -- STOP/ESCALATE --> escalate

    apply_fix --> authorize_retry
    authorize_retry --> END_1[END\ngraph pauses]

    evaluate_outcome -- EFFECTIVE --> write_memory
    evaluate_outcome -- INEFFECTIVE --> collect_context
    evaluate_outcome -- limit reached --> escalate

    write_memory --> END_2[END]
    generate_proposal_report --> END_3[END]
    escalate --> END_4[END]
    handle_insufficient_evidence --> END_5[END]

    style run_rule_classifier fill:#2d6a4f,color:#fff
    style lookup_fix_catalog fill:#2d6a4f,color:#fff
    style validate_policy fill:#2d6a4f,color:#fff
    style apply_fix fill:#2d6a4f,color:#fff
    style authorize_retry fill:#2d6a4f,color:#fff
    style evaluate_outcome fill:#2d6a4f,color:#fff
    style write_memory fill:#2d6a4f,color:#fff
    style run_diagnosis_agent fill:#1d3557,color:#fff
    style run_fix_planner fill:#1d3557,color:#fff
    style retrieve_memories fill:#457b9d,color:#fff
```

**Green nodes** — deterministic, no LLM
**Blue nodes** — LLM-powered
**Teal nodes** — memory / retrieval

### State keys

| Key | Set by | Used by |
|---|---|---|
| `incident_id` | POST script | all nodes |
| `job_id`, `workflow_id` | POST script | collect_context |
| `exit_code` | POST script | rule classifier |
| `context` | collect_context | all diagnostic nodes |
| `raw_evidence` | collect_context | diagnosis agent, fix planner |
| `diagnosis` | rule_classifier / diagnosis_agent | lookup_fix_catalog, apply_fix |
| `proposed_fix` | fix_catalog / fix_planner | validate_policy, apply_fix |
| `policy_decision` | validate_policy | graph router, POST script |
| `overlay` | apply_fix | (logged) |
| `retry_job_instance_id` | authorize_retry | graph resume signal |
| `retry_outcome` | POST script (invocation 2+) | evaluate_outcome |
| `retrieved_memories` | retrieve_memories | run_diagnosis_agent |

---

## 5. Diagnostic Loop

### 5.1 Rule Classifier

**File:** `app/utils/rules/classifier.py`

Pure Python — no LLM, no I/O. Runs first, every time. Returns a `Diagnosis` or `None`.

```mermaid
flowchart TD
    ctx[FailureContext] --> oom{exit_code=137\nor signal=9\nor scheduler_reason∋OOM?}
    oom -- yes → 1+ signal --> OOM[OUT_OF_MEMORY\nconfidence 0.90–0.97]
    oom -- no --> disk{scheduler_reason∋disk\nor stderr∋'No space left'\nor disk_used ≥ 90%?}
    disk -- yes --> DISK[DISK_EXCEEDED\nconfidence 0.95]
    disk -- no --> wall{scheduler_reason∋walltime\nor runtime ≥ 95% of limit?}
    wall -- yes --> WALL[WALLTIME_EXCEEDED\nconfidence 0.93]
    wall -- no --> trans{scheduler_reason∋evict\npreempt, network?}
    trans -- yes --> TRANS[TRANSIENT_INFRASTRUCTURE\nconfidence 0.90]
    trans -- no --> admit{scheduler_reason∋QoS\nqueue, account?}
    admit -- yes --> ADMIT[SCHEDULER_ADMISSION\nconfidence 0.92]
    admit -- no --> inp{input_checks\nhave failures?}
    inp -- yes --> MISS[MISSING_INPUT\nconfidence 0.95]
    inp -- no --> NONE[None → LLM agent]
```

**Signal sets used:**

| Failure type | Signals checked |
|---|---|
| OUT_OF_MEMORY | exit 137, signal 9, scheduler hold reason, peak_memory ≥ 85% of request |
| DISK_EXCEEDED | scheduler hold reason, stderr patterns (`No space left`, `ENOSPC`, `disk full`), disk_used ≥ 90% |
| WALLTIME_EXCEEDED | scheduler hold reason, runtime ≥ 95% of request |
| TRANSIENT | scheduler reason (evict, preempt, node fail, network, disconnected) |
| SCHEDULER_ADMISSION | scheduler reason (QoS, invalid queue, account, over limit) |
| MISSING_INPUT | input_checks list (populated by ContextCollector) |

### 5.2 LLM Diagnosis Agent (ReAct)

**File:** `app/agents/diagnosis.py`

Only invoked when no rule matched. Implements a ReAct (Reason + Act) loop.

```mermaid
sequenceDiagram
    participant G as Graph
    participant A as DiagnosisAgent
    participant L as LLM
    participant T as Tools

    G->>A: run(ctx, raw_evidence, memories)
    A->>L: seed_message(ctx, memories, past_diagnoses)
    loop ReAct loop (max 7 steps)
        L-->>A: ThoughtAction {thought, action}
        alt action == "conclude"
            A-->>G: Diagnosis(failure_type, confidence, explanation)
        else action == tool_name
            A->>T: call tool(raw_evidence)
            T-->>A: observation
            A->>L: append observation → next step
        end
        Note over A: stop if confidence ≥ 0.85<br/>or same tool called twice
    end
```

**Available tools:**

| Tool | Returns |
|---|---|
| `parse_failure_summary` | pegasus-analyzer structured output |
| `get_stderr` | stderr content — from `.err` file, or falls back to `stderr_data` embedded in kickstart YAML when `.err` is empty |
| `get_kickstart_data` | timing, exit codes, resource usage from kickstart YAML or XML; critically includes `stderr_data` / `stdout_data` (full app output captured by kickstart) and `file_errors` (transfer error codes per file) |
| `get_stdout` | application stdout captured by kickstart (`stdout.data` in YAML, `<stdout>` in XML) |
| `get_resource_requests` | current `.sub` resource values |
| `get_condor_history` | HTCondor classads (memory, disk, runtime used) |
| `get_event_log` | HTCondor event log (evictions, holds, checkpoints) |
| `get_dagman_log` | DAGMan retry history |
| `get_transformation_script` | source of the executable |
| `get_input_validation` | checks which input files exist and are accessible |

**Seed message** contains:
- Job identity and exit code
- Available data sources
- Past diagnoses (same incident, prior attempts)
- Similar past incidents from memory (`retrieved_memories`)

**Stopping conditions:**
1. `action == "conclude"` — LLM decided it has enough evidence
2. `confidence ≥ 0.85` in thought — next step forced to conclude
3. Same tool called twice — force conclude to avoid loops
4. `MAX_STEPS = 7` reached — force conclude with lower confidence

---

## 6. Action Loop

### 6.1 Fix Catalog

**File:** `app/utils/fixes/catalog.py`

Deterministic lookup — no LLM. Maps `FailureType` → `FixProposal` using policy multipliers.

| Failure type | Action | Formula | Auto? |
|---|---|---|---|
| OUT_OF_MEMORY | INCREASE_MEMORY | `ceil(current × 1.5)`, max 512 GB | AUTO |
| DISK_EXCEEDED | INCREASE_DISK | `ceil(current × 2.0)`, max 1 TB | AUTO |
| WALLTIME_EXCEEDED | INCREASE_RUNTIME | `int(current × 1.5)`, max 48 h | ASK |
| TRANSIENT_INFRASTRUCTURE | NO_ACTION_TRANSIENT_RETRY | — | AUTO |
| MISSING_INPUT | CORRECT_DATA_BINDING | — | ASK |

Returns `None` for `APPLICATION_ERROR`, `LOGIC_VALIDATION`, `UNKNOWN` → routes to LLM Fix Planner.

### 6.2 LLM Fix Planner

**File:** `app/agents/fix_planning.py`

Called only when the catalog has no entry. Given the diagnosis and raw evidence, proposes a `FixProposal` with `script_patches` or configuration changes.

### 6.3 Policy Engine

**File:** `app/utils/policies/engine.py`
**Config:** `policies/remediation.yaml`

Deterministic safety gate. Runs after every fix proposal — catalog or LLM. **LLM output can never override policy.**

```mermaid
flowchart TD
    proposal[FixProposal] --> f1{forbidden action?\nMODIFY_EXECUTABLE\nMODIFY_ALGORITHM}
    f1 -- yes --> STOP1[STOP]
    f1 -- no --> f2{requires_human_review?}
    f2 -- yes --> STOP2[STOP]
    f2 -- no --> f3{confidence\n< threshold 0.80?}
    f3 -- yes --> ESCALATE[ESCALATE]
    f3 -- no --> f4{healer tag\nno-fix or stop?}
    f4 -- yes --> STOP3[STOP]
    f4 -- no --> f5{scope level\nsufficient?}
    f5 -- no --> f6{fallback_decision}
    f6 --> ASK_fallback[ASK]
    f5 -- yes --> f7{attempts ≤ max?}
    f7 -- no --> ESCALATE2[ESCALATE]
    f7 -- yes --> f8{proposal.requires_approval?}
    f8 -- yes --> ASK[ASK]
    f8 -- no --> AUTO[AUTO]
```

**Scope levels** (from `remediation.yaml`):

```
job      → submit dir only (.sub, .dag)         current default
script   → job + transformation scripts
catalog  → script + replica/transformation catalogs
workflow → catalog + DAX / pegasus.properties
```

**Healer tags** (set per-job in workflow YAML → appear in `.sub`):

| Tag | Effect |
|---|---|
| `no-fix` | Diagnose only — never apply or propose a fix |
| `stop` | Abort entire workflow on failure |
| `stop-jobs` | Stop all jobs of the same transformation family |

### 6.4 Apply Fix + Sibling Broadcast

**Files:** `app/graph/nodes.py` → `apply_fix`, `app/utils/pegasus/sibling_fixer.py`

```mermaid
sequenceDiagram
    participant N as apply_fix node
    participant RC as DAGManRetryController
    participant SF as sibling_fixer
    participant FS as filesystem

    N->>RC: apply_overlay(proposal)
    RC->>FS: patch failing job's .sub file\n(both request_* and pegasus_* attrs)
    RC-->>N: OverlayResult (hash_before, hash_after)

    N->>RC: broadcast_to_siblings(fix, transformation)
    RC->>SF: find_siblings(submit_dir, transformation,\nresource_key, original_value)
    SF->>FS: scan all *.sub files for same\ntransformation + same original value
    SF-->>RC: [{sub_path, job_id, cluster_id}]

    loop for each sibling
        RC->>FS: patch sibling .sub
        alt sibling is IDLE in HTCondor
            RC->>HTCondor: condor_qedit (live ClassAd update)
        end
    end

    RC->>SF: write_marker(submit_dir,\ntransformation, failure_type)
    SF->>FS: .healer_{transformation}_{failure_type}.applied\n(atomic O_CREAT|O_EXCL)
```

**Sibling states and actions:**

| HTCondor state | Action |
|---|---|
| IDLE (queued) | Patch `.sub` + `condor_qedit` — updates live ClassAd, job runs with new resources |
| RUNNING | Patch `.sub` only — if it fails, retry uses new values |
| NOT_SUBMITTED | Patch `.sub` only — DAGMan reads patched file on submission |
| FAILED / HELD | Skip — handled by their own POST script invocation |

**Marker fast path** — when a sibling already had its `.sub` patched but ran with old ClassAd:

```
marker file exists
  AND this job's .sub already has the patched value
  AND current exit code matches the failure type's known codes
  ──→ skip entire agent run ──→ exit 1 (retry with patched .sub)
```

---

## 7. Thread & Checkpoint System

**Invocation 1** (first failure, `$RETRY=0`):

```
thread_id = "{workflow_uuid}/{job_id}/{instance_id}"
.healer_thread file written → fresh thread
graph runs: collect → classify → fix → apply → authorize_retry → END
```

**Invocation 2+** (retried job exits, `$RETRY=1`):

```
thread_id read from .healer_thread → is_resume=True
graph resumes from checkpoint: input = {retry_outcome: EFFECTIVE|INEFFECTIVE}
route_entry → evaluate_outcome → write_memory → END
```

The **SQLite checkpointer** (`~/.pegasus_healer_checkpoint.db`) stores the full graph state between invocations. Override with `HEALER_CHECKPOINT` env var.

```mermaid
sequenceDiagram
    participant D as DAGMan
    participant P1 as POST script\n(invocation 1)
    participant G as LangGraph\n+ SQLite checkpoint
    participant P2 as POST script\n(invocation 2)

    D->>P1: $RETURN=137 $RETRY=0
    P1->>G: ainvoke({incident_id, exit_code=137, ...})
    G->>G: collect → classify → fix → apply → authorize_retry
    G-->>G: checkpoint saved to SQLite
    P1-->>D: exit 1 (retry)

    D->>D: retries job with patched .sub
    D->>P2: $RETURN=0 $RETRY=1
    P2->>G: ainvoke({retry_outcome: EFFECTIVE})
    G->>G: resume from checkpoint → evaluate_outcome → write_memory
    P2-->>D: exit 0 (success)
```

---

## 8. Memory System

**File:** `app/utils/memory/sqlite_repo.py`

```mermaid
flowchart LR
    subgraph write_path[Write path — EFFECTIVE outcome]
        WM[write_memory node]
        WM -->|store_episode| DB[(~/.pegasus_healer_memory.db\nSQLite)]
    end

    subgraph read_path[Read path — LLM agent only]
        RM[retrieve_memories node]
        RM -->|find_similar| DB
        DB -->|top-5 episodes| RM
        RM --> seed[seed_message\nSimilar past incidents:\n  - failure=OOM fix=INCREASE_MEMORY outcome=EFFECTIVE]
        seed --> LLM[DiagnosisAgent LLM]
    end
```

**Episode schema stored:**

```
failure_type       TEXT    e.g. OUT_OF_MEMORY
transformation     TEXT    e.g. compute
execution_site     TEXT    e.g. local
fix_action         TEXT    e.g. INCREASE_MEMORY
outcome            TEXT    EFFECTIVE
config_delta       JSON    {"memory_mb": 384}
confidence         REAL    0.97
occurrence_count   INT     1  (incremented on duplicates)
```

**When retrieve_memories is called:**
Only on the LLM-agent path — when `run_rule_classifier` returns no match. For `OUT_OF_MEMORY`, `DISK_EXCEEDED`, `WALLTIME_EXCEEDED` the rule classifier always fires first (confidence ≥ 0.90), so memory retrieval is **skipped** for these common cases.

**Current limitations:**

| Limitation | Impact |
|---|---|
| `project_id = workflow_id` (UUID) | Episodes from `run0001` never found in `run0002` — memory is write-only cross-run |
| Exact-match SQL (`WHERE project_id=?`) | No semantic similarity — structurally identical failures with different field values return 0 results |
| No embedding / vector search | Cannot find "similar" failures across transformations |

---

## 9. Sub File Patching

**File:** `app/utils/pegasus/sub_file.py`

Pegasus `.sub` files use two parallel attributes for resource requests. Patching only one breaks on retry because the template re-expands:

```
# HTCondor scheduling          # Pegasus metadata
request_memory = 256    ←──→  pegasus_memory_mb = 256
request_disk   = 512    ←──→  pegasus_diskspace_mb = 512
request_cpus   = 1      ←──→  pegasus_cores = 1
+MaxRuntime    = 3600   ←──→  pegasus_job_runtime = 3600
```

The patcher updates **both** columns atomically. If an attribute is absent, it is inserted before the final `queue` statement.

**Example — OOM fix on compute job (256 → 384 MB):**

```diff
- request_memory          = 256
- pegasus_memory_mb       = 256
+ request_memory          = 384
+ pegasus_memory_mb       = 384
```

---

## 10. Exit Code Contract

| Condition | POST script exits | DAGMan action |
|---|---|---|
| AUTO fix applied | 1 | Retry job with patched `.sub` |
| Sibling fast path | 1 | Retry job with already-patched `.sub` |
| ASK — job failed | original exit code (non-zero) | Mark node FAILED (prevents stage_out) |
| ASK — job succeeded | 0 | Continue workflow |
| STOP / ESCALATE — job failed | original exit code | Mark node FAILED |
| STOP / ESCALATE — job succeeded | 0 | Continue workflow |
| EFFECTIVE outcome on resume | 0 | Continue workflow |
| Healer tag `stop` | 0 | Workflow aborts |

**Why ASK exits with original code when job failed:**
Exiting 0 would make DAGMan mark the node DONE → `stage_out` runs → looks for `.meta` file → fails because job never produced output. Preserving the non-zero exit code keeps the node in FAILED state and prevents downstream jobs from running against non-existent outputs.

---

## 11. Demo Workflows

### hello-world-demo

Baseline end-to-end test.

```
hello (request_memory=256, exits 137 on attempt 0)
  → healer: OUT_OF_MEMORY → INCREASE_MEMORY → 256→384 MB → retry
  → hello succeeds → world runs → stage_out → SUCCESS
```

### disk-demo (`workflows/disk_demo.py`)

```
analyze (request_disk=512 MB, stderr: "No space left on device")
  → healer: DISK_EXCEEDED → INCREASE_DISK → 512→1024 MB → retry
  → analyze succeeds → report runs → SUCCESS
```

### sibling-demo (`workflows/sibling_demo.py`)

```mermaid
flowchart LR
    data.in --> A[compute_A\n256 MB]
    data.in --> B[compute_B\n256 MB]
    data.in --> C[compute_C\n256 MB]
    A --> merge
    B --> merge
    C --> merge
    merge --> merged.out
```

All three `compute` jobs fail with exit 137. Healer detects OOM on each, patches all three `.sub` files (sibling broadcast), writes marker. On next run sibling fast path fires for jobs whose marker was written before they failed.

---

## 12. Known Limitations

| Area | Limitation | Planned fix |
|---|---|---|
| Memory retrieval | `project_id = workflow_uuid` — cross-run lookup always returns empty | Use stable workflow name as project_id |
| Memory retrieval | Exact SQL match, no semantic similarity | Embedding column + cosine similarity |
| retrieve_memories | Skipped entirely when rules match (OOM/DISK/WALLTIME) | Intentional — fast path; memory matters for LLM path only |
| Sibling fast path | Race condition when all siblings fail simultaneously → all run full agent | Add DAGMan PRIORITY ordering to stagger starts |
| Sub file patching | Only patches `request_*` and `pegasus_*` — custom submit attributes untouched | Extend `_ATTR_MAP` as needed |
| Policy scope | Default `level: job` — script/catalog/workflow fixes always produce ASK | Raise scope level in `remediation.yaml` when trust is established |
| Embedding model | No embedding configured → retrieve_memories returns exact-match SQL only | Set `EMBED_MODEL` / `EMBED_API_KEY` env vars when adding semantic search |
| ASK decision | In automated POST script context ASK = STOP (no notification channel, no approval UI) | Replace ASK with human-approval webhook or remove from automated path |

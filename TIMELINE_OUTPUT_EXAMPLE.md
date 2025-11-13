# Multi-Prompt Timeline Output Example

## Command to Run

```bash
cd WorkflowValidator
python3.11 cli.py /path/to/workflow.yml -l full -v
```

## Expected Output with Timeline

```
================================================================================
⏱️  VALIDATION TIMELINE (Multi-Prompt Architecture)
================================================================================
🔍 [PROMPT 1] Running structure validator...
✓ Structure validation completed in 0.023s
--------------------------------------------------------------------------------
🔍 [PROMPT 2] Running path validator...
INFO:path_validator:Validating transformation: FineTuneLLM -> /home/hsafri/LLM-Fine-Tune/bin/finetune.py
INFO:path_validator:✓ Transformation executable OK: FineTuneLLM
INFO:path_validator:Validating replica path: pegasus_data -> /home/hsafri/LLM-Fine-Tune/data/data.json
INFO:path_validator:✓ Replica file OK: pegasus_data (12884901 bytes)
✓ Path validation completed in 0.156s
--------------------------------------------------------------------------------
🔍 [PROMPT 3] Running integrity validator...
INFO:integrity_validator:Checking integrity: pegasus_data -> /home/hsafri/LLM-Fine-Tune/data/data.json
INFO:integrity_validator:✓ Integrity OK: pegasus_data
✓ Integrity validation completed in 0.082s
--------------------------------------------------------------------------------
🔍 [PROMPT 4] Running job input validator...
INFO:job_input_validator:Validated job inputs: FineTuneLLM - 1 inputs, 0 outputs
✓ Job input validation completed in 0.005s
--------------------------------------------------------------------------------
🔍 [PROMPT 5] Running resource validator...
INFO:resource_validator:Validated resources: FineTuneLLM - 16.0GB RAM, 4 CPUs
✓ Resource validation completed in 0.003s
--------------------------------------------------------------------------------
🔍 [PROMPT 6] Running DAG validator...
INFO:dag_validator:DAG validated: 1 jobs, max depth: 0
✓ DAG validation completed in 0.002s
--------------------------------------------------------------------------------

================================================================================
🤖 LLM MULTI-PROMPT VALIDATION
================================================================================
🤖 [LLM PROMPT 1/7] Validating workflow structure...
✓ LLM structure validation: 1.234s
--------------------------------------------------------------------------------
🤖 [LLM PROMPT 2/7] Validating job dependencies...
✓ LLM dependency validation: 1.123s
--------------------------------------------------------------------------------
🤖 [LLM PROMPT 3/7] Validating file paths...
✓ LLM path validation: 1.056s
--------------------------------------------------------------------------------
🤖 [LLM PROMPT 4/7] Validating resource requirements...
✓ LLM resource validation: 0.987s
--------------------------------------------------------------------------------
🤖 [LLM PROMPT 5/7] Validating data integrity...
✓ LLM integrity validation: 1.145s
--------------------------------------------------------------------------------
🤖 [LLM PROMPT 6/7] Running security checks...
✓ LLM security validation: 1.234s
--------------------------------------------------------------------------------
🤖 [LLM PROMPT 7/7] Checking best practices...
✓ LLM best practices check: 1.089s
--------------------------------------------------------------------------------

================================================================================
⏱️  TOTAL VALIDATORS RUN: 13 prompts
================================================================================

================================================================================
🔍  PEGASUS WORKFLOW VALIDATION REPORT
================================================================================

Workflow: /home/hsafri/LLM-Fine-Tune/generated_workflows/falcon-7b.yml
Validated: 2025-01-15 10:30:45
Duration: 8.14s

Overall Status: ✅ PASSED

────────────────────────────────────────────────────────────────────────────────
📊 SUMMARY
────────────────────────────────────────────────────────────────────────────────
  Total Issues: 0
  ├─ Errors:    0
  └─ Warnings:  0

────────────────────────────────────────────────────────────────────────────────
🔧 VALIDATOR RESULTS
────────────────────────────────────────────────────────────────────────────────

✅ STRUCTURE (0.02s)
   Checks performed: 3
   Errors: 0, Warnings: 0

✅ PATHS (0.16s)
   Checks performed: 2
   Errors: 0, Warnings: 0
   Files validated: 2
      ✓ FineTuneLLM (2.5KB) - exists, readable, executable, valid_shebang
      ✓ pegasus_data (12.3MB) - exists, readable, non-empty

✅ INTEGRITY (0.08s)
   Checks performed: 1
   Errors: 0, Warnings: 0
   Files validated: 1
      ✓ pegasus_data (12.3MB) - readable

✅ JOB_INPUTS (0.01s)
   Checks performed: 1
   Errors: 0, Warnings: 0
   Jobs validated: 1
      ✓ FineTuneLLM (1 inputs, 0 outputs)

✅ RESOURCES (0.00s)
   Checks performed: 1
   Errors: 0, Warnings: 0
   Jobs validated: 1
      ✓ FineTuneLLM (16GB RAM, 4 CPUs)

✅ DAG (0.00s)
   Checks performed: 2
   Errors: 0, Warnings: 0

   📊 DAG Statistics:
      Total Jobs: 1
      Jobs with Dependencies: 0
      Max Depth: 0
      Cycles Detected: 0

✅ LLM_STRUCTURE (1.23s)
   Checks performed: 1
   Errors: 0, Warnings: 0

✅ LLM_DEPENDENCIES (1.12s)
   Checks performed: 1
   Errors: 0, Warnings: 0

✅ LLM_PATHS (1.06s)
   Checks performed: 1
   Errors: 0, Warnings: 0

✅ LLM_RESOURCES (0.99s)
   Checks performed: 1
   Errors: 0, Warnings: 0

✅ LLM_INTEGRITY (1.15s)
   Checks performed: 1
   Errors: 0, Warnings: 0

✅ LLM_SECURITY (1.23s)
   Checks performed: 1
   Errors: 0, Warnings: 0

✅ LLM_BEST_PRACTICES (1.09s)
   Checks performed: 1
   Errors: 0, Warnings: 0

================================================================================
✅ VALIDATION PASSED

Workflow is ready for submission!
================================================================================
```

## Summary

**Total Prompts: 13**
- 6 rule-based validators (fast: < 0.3s total)
- 7 LLM validators (comprehensive: ~7.8s total)

**Multi-Prompt Architecture:**
- Each validator is independent
- Clear timeline showing what's being checked
- LLM validates everything with 7 different prompts
- Rule-based for speed, LLM for intelligence

**Run it now:**
```bash
python3.11 cli.py /home/hsafri/LLM-Fine-Tune/generated_workflows/falcon-7b.yml -l full -v
```

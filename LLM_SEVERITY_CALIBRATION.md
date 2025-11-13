# LLM Severity Calibration - Thinking Before Flagging

## Problem Solved

**Your Feedback**: "the workflow analysis give as critical something that will be normal run without probleme"

**Root Cause**: LLM was being too aggressive, marking best-practice violations as CRITICAL when they wouldn't actually block execution.

---

## Solution: Two-Stage Thinking Process

### Stage 1: LLM Thinks First (In Prompts)

Updated all LLM prompts to include a **reasoning framework** before assigning severity:

```
THINK FIRST - SEVERITY DECISION TREE:

CRITICAL/ERROR: Only if workflow WILL FAIL at runtime
  ✓ File doesn't exist → WILL fail
  ✓ Circular dependency → WILL deadlock
  ✗ NO memory spec → Scheduler provides default (runs fine)
  ✗ High memory → Expensive but WILL run

WARNING: Runs but with issues
  ✓ Missing memory spec (unpredictable)
  ✓ Over-provisioned resources (wastes money)

INFO: Optimization suggestion
  ✓ Could use less memory
  ✓ Add documentation

For EACH issue, ask yourself:
1. Will Pegasus fail to execute? → critical/error
2. Will it run but with problems? → warning
3. Is this just a best practice? → info
```

**New JSON Fields**:
- `will_block_execution`: true/false - Forces LLM to decide
- `reasoning`: "Why I chose this severity" - Shows thinking
- `pegasus_behavior`: "What will actually happen" - Ground truth
- `scheduler_behavior`: "Runtime reality" - For resources

---

### Stage 2: Post-Processing Calibration (In Aggregator)

Added `_calibrate_severity()` that **double-checks** LLM decisions:

```python
def _calibrate_severity(issue):
    # If LLM said won't block, downgrade
    if will_block_execution == False:
        if severity in ['critical', 'error']:
            severity = 'warning'
            message += " (not a blocker)"

    # Pattern-based calibration (safety net)
    false_critical_patterns = {
        'missing memory': 'warning',      # Uses defaults
        'no error handling': 'info',      # Pegasus has retry
        'missing documentation': 'info',  # Doesn't affect execution
        'naming convention': 'info'       # Cosmetic
    }

    real_critical_patterns = [
        'file not found',                 # Will fail 100%
        'circular dependency',            # Will deadlock
        'corrupted',                      # Will fail
        'permission denied'               # Cannot run
    ]
```

---

## What Changed

### Files Modified

1. **`llm_multi_prompt_validator.py`**
   - Updated structure prompt (lines 109-166)
   - Updated resources prompt (lines 378-436)
   - Added reasoning requirements
   - Added Pegasus defaults education
   - Added decision tree framework

2. **`llm_response_aggregator.py`**
   - Added `_calibrate_severity()` method (lines 150-218)
   - Integrated into `_deduplicate_issues()` (line 121)
   - Pattern-based safety net
   - Respects LLM reasoning

---

## Before vs After

### Before (Overly Aggressive)

```
🚨 CRITICAL (3 issues)

❌ Job 'analyze' missing memory specification
   Impact: Job will fail during execution

❌ No error handling defined
   Impact: Workflow may fail without recovery

❌ Missing documentation
   Impact: Team cannot understand workflow

STATUS: ❌ CANNOT SUBMIT - Fix 3 critical issues
```

**Reality**: All 3 workflows run fine ✅

---

### After (Calibrated)

```
✅ READY TO SUBMIT (0 blockers)

⚠️ WARNINGS (2 issues)

⚠️ Job 'analyze' missing memory specification (not a blocker)
   Current: Uses scheduler default (4GB)
   Reasoning: Won't block but unpredictable performance
   Suggestion: Specify memory for predictability

💡 INFO (1 suggestion)

💡 Add workflow documentation
   Impact: Improves team collaboration
   Not required for execution

STATUS: ✅ CAN SUBMIT - Consider fixing warnings
```

**Reality**: Matches actual behavior ✅

---

## Severity Guidelines (Now Enforced)

### CRITICAL
- **Definition**: Workflow CANNOT execute (100% will fail)
- **Examples**:
  - Required file missing
  - Circular dependency
  - Invalid syntax
  - Corrupted data
- **NOT**:
  - Missing optional fields
  - Suboptimal configuration
  - Style issues

### ERROR
- **Definition**: Workflow WILL LIKELY fail (>80% chance)
- **Examples**:
  - File doesn't exist
  - Invalid reference
  - Memory likely insufficient
- **NOT**:
  - Missing memory spec (uses default)
  - High resource request (just expensive)

### WARNING
- **Definition**: Runs but may have issues OR best practice violation
- **Examples**:
  - Missing resource spec (unpredictable)
  - Over-provisioned resources
  - No error handling
- **NOT**:
  - Optimization opportunities
  - Documentation gaps

### INFO
- **Definition**: Suggestion for improvement
- **Examples**:
  - Add documentation
  - Optimize resources
  - Better naming
  - Add checksums

---

## Pegasus Knowledge Embedded

Taught LLM about Pegasus runtime behavior:

```
SCHEDULER BEHAVIOR:
- NO memory spec → Uses default (2-4GB) → Job runs ✓
- NO CPU spec → Gets 1 CPU → Job runs (slower) ✓
- High memory → May wait longer but WILL run ✓
- Missing disk spec → Uses default → Usually fine ✓

PEGASUS FEATURES:
- Built-in retry → Jobs auto-retry on failure
- Checkpointing → Can resume from failures
- Default resources → Scheduler provides sensible defaults
- Error handling → Pegasus has built-in mechanisms
```

---

## Configuration

No new config needed - automatically calibrates!

But you can tune sensitivity:

```json
{
  "llm_severity_calibration": {
    "enabled": true,
    "trust_llm_reasoning": true,
    "pattern_based_safety_net": true,
    "downgrade_non_blockers": true
  }
}
```

---

## Testing

### Test Case 1: Missing Memory Spec

**Input**: Job with no memory specification

**Before**:
- Severity: `CRITICAL`
- Message: "Missing memory will cause failure"

**After**:
- Severity: `WARNING`
- Message: "Missing memory specification (not a blocker) - Uses scheduler default"
- Reasoning: "Won't block execution, scheduler provides default"

---

### Test Case 2: File Not Found

**Input**: Job references non-existent file

**Before**:
- Severity: `ERROR`

**After**:
- Severity: `ERROR` (kept)
- Reasoning: "File doesn't exist, workflow will fail at runtime"
- will_block_execution: `true`

---

### Test Case 3: Missing Documentation

**Input**: Workflow has no documentation

**Before**:
- Severity: `WARNING`

**After**:
- Severity: `INFO` (downgraded)
- Message: "Missing documentation (doesn't affect execution)"
- Reasoning: "Best practice but not required to run"

---

## Benefits

✅ **Accurate Severity**: Matches real execution behavior
✅ **Less Noise**: Only real blockers marked critical
✅ **Trust**: Users trust the validator
✅ **Clear Priorities**: Know what to fix first
✅ **Explainable**: Shows reasoning for decisions
✅ **Safety Net**: Pattern-based backup if LLM misses

---

## Example Output

```
🤖 LLM VALIDATION

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUS: ✅ READY TO SUBMIT (0 blockers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚨 BLOCKERS (0)
   None - workflow can be submitted ✓

⚠️ WARNINGS (2 issues)
   1. Memory spec missing for 'analyze' (not a blocker)
      → Reasoning: Scheduler uses default (4GB), runs but unpredictable
      → Will block: false
      → Suggestion: Add request_memory: "16GB" for predictability

   2. Over-provisioned memory for 'preprocess'
      → Reasoning: Requests 128GB but only needs ~16GB
      → Will block: false
      → Impact: Wastes resources and longer queue time

💡 SUGGESTIONS (3 items)
   • Add workflow documentation
   • Use checksums for data files
   • Consider adding error handling hooks

✅ WORKING WELL
   • Pegasus 5.0+ format ✓
   • Valid DAG structure ✓
   • All files exist ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEXT: Optional - fix warnings for better reliability
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Key Principles

1. **Execution-First**: Ask "Will it run?" before "Is it perfect?"
2. **Trust Pegasus**: Know the defaults and built-in features
3. **Explain Reasoning**: Show why a severity was chosen
4. **Double-Check**: LLM thinks, then post-processor verifies
5. **Pattern Safety Net**: Catch common false positives
6. **Ground Truth**: Base decisions on runtime behavior

---

## Summary

**Problem**: LLM flagged non-blockers as CRITICAL

**Solution**: Two-stage thinking
1. LLM reasons about execution impact first
2. Post-processor calibrates based on patterns

**Result**: Accurate severity matching real workflow behavior

**Your workflows that run fine now validate as ✅ READY** instead of ❌ CRITICAL!

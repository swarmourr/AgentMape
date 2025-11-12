# Increased LLM Context Size

## Changes Made

### Previous Limits (Too Small)
- Runner script: **1500 chars** ❌
- Generator script: **1500 chars** ❌
- Total context: ~3000 chars
- Max response tokens: 100

### New Limits (Much Larger)
- Runner script: **4000 chars** ✅
- Generator script: **4000 chars** ✅
- Total context: ~8000 chars
- Max response tokens: **500** ✅

## Why This Matters

### Problem with Small Context
If your output path is defined after line 50-60 in the script, it gets cut off:

```python
# Line 1-50: Imports, config, setup...
# Line 60: OUTPUT_FILE = "workflows/pipeline.yml"  # ❌ CUT OFF!
```

The LLM never sees line 60, so it returns "NONE".

### Solution with Large Context
Now the LLM sees up to ~150-200 lines of code (4000 chars):

```python
# Line 1-50: Imports, config, setup...
# Line 60: OUTPUT_FILE = "workflows/pipeline.yml"  # ✅ INCLUDED!
# Line 70-150: More code...
```

## What You'll See

### When Running Tests
```
Building prompt...
  Using context size:
    Runner:    234 / 234 chars      ✓ Full script sent
    Generator: 4000 / 5678 chars    ⚠️ Truncated (but much more than before!)

================================================================================
REQUEST TO LLM
================================================================================
...
[Full 4000 chars of each script]
...
================================================================================
Prompt length: 8543 chars
Runner sent: 4000 chars (total: 234 chars)
Generator sent: 4000 chars (total: 5678 chars)
Temperature: 0.1
Max tokens: 500
================================================================================
```

### If Script is Large
If your generator is 5678 chars:
- **Before**: Only first 1500 chars sent (26%)
- **Now**: First 4000 chars sent (70%) ✅

## Context Size Breakdown

| Script Type | Old Limit | New Limit | Typical Lines |
|-------------|-----------|-----------|---------------|
| Runner (bash) | 1500 | 4000 | ~150 lines |
| Generator (Python) | 1500 | 4000 | ~120 lines |
| Combined prompt | ~3000 | ~8500 | ~270 lines total |

## Token Limits

### LLM Model Capacity
Most models support:
- **Input tokens**: 4K-128K (glm-4.6 likely supports 8K+)
- **Output tokens**: 2K-4K

Our usage:
- **Input**: ~8500 chars ≈ 2000-2500 tokens ✅ (well within limits)
- **Output**: 500 tokens ✅ (enough for path + explanation)

## Testing

### Test 1: Small Scripts (< 4000 chars)
```bash
python3 test_llm_direct.py

# Expected:
Runner sent: 234 chars (total: 234 chars)      # Full script
Generator sent: 1456 chars (total: 1456 chars) # Full script
```
✅ Both scripts sent completely

### Test 2: Large Scripts (> 4000 chars)
```bash
python3 test_llm_direct.py

# Expected:
Runner sent: 4000 chars (total: 456 chars)      # Truncated
Generator sent: 4000 chars (total: 6789 chars)  # Truncated
```
✅ Much more context than before (1500 → 4000)

## When 4000 Chars Isn't Enough

### Option 1: Increase Further
Edit `runner_analyzer.py` lines 153-154:

```python
# From:
runner_truncate = min(len(content), 4000)
generator_truncate = min(len(generator_content), 4000)

# To:
runner_truncate = min(len(content), 8000)  # Double it
generator_truncate = min(len(generator_content), 8000)
```

**Warning**: Check your LLM model's token limit first!

### Option 2: Move Output Logic to Top
Put your output configuration at the top of the file:

```python
#!/usr/bin/env python3
"""Workflow Generator"""

# OUTPUT CONFIGURATION - Put this at the top!
OUTPUT_DIR = "workflows"
OUTPUT_FILE = "pipeline.yml"
OUTPUT_PATH = f"{OUTPUT_DIR}/{OUTPUT_FILE}"

# Now rest of imports, functions, etc...
import yaml
import sys
...
```

### Option 3: Add Comments
Help the LLM find output paths:

```python
# WORKFLOW OUTPUT CONFIGURATION
OUTPUT_DIR = "workflows"  # Directory for generated workflows
OUTPUT_FILE = "pipeline.yml"  # Main workflow file
```

### Option 4: Use Explicit Flag
Skip auto-detection entirely:

```bash
python3 cli.py workflow.py --runner run.sh \
  --generated-workflows workflows/pipeline.yml
```

## Monitoring Context Usage

The output now shows exactly what's being sent:

```
================================================================================
Runner sent: 4000 chars (total: 234 chars)
Generator sent: 4000 chars (total: 5678 chars)
================================================================================
```

**Interpretation**:
- If `sent == total`: Full script sent ✅
- If `sent < total`: Script truncated ⚠️
  - Check if important info is in first 4000 chars
  - If not, move it up or increase limit

## Estimating Lines

Rough estimate of how many lines fit in 4000 chars:

### Bash Scripts (~25-30 chars/line)
```
4000 chars ÷ 27 chars/line ≈ 148 lines
```

### Python Scripts (~33-35 chars/line)
```
4000 chars ÷ 34 chars/line ≈ 117 lines
```

### Dense Code (~40-45 chars/line)
```
4000 chars ÷ 42 chars/line ≈ 95 lines
```

## Best Practices

1. **Put output config at top** (within first 50 lines)
2. **Use clear variable names** (OUTPUT_FILE, OUTPUT_DIR)
3. **Add comments** explaining output paths
4. **Check truncation** in test output
5. **Increase limits** if needed (but watch token limits)

## Files Modified

- **[runner_analyzer.py](runner_analyzer.py)**:
  - Line 153-154: Increased runner/generator to 4000
  - Line 195: Increased single script to 5000
  - Line 253: Increased max_tokens to 500

- **[test_llm_direct.py](test_llm_direct.py)**:
  - Line 96-97: Increased to 4000
  - Line 168: Increased max_tokens to 500

## Quick Reference

| Setting | Old Value | New Value |
|---------|-----------|-----------|
| Runner context | 1500 | 4000 |
| Generator context | 1500 | 4000 |
| Single script context | 2000 | 5000 |
| Max output tokens | 100 | 500 |
| Total prompt size | ~3000 | ~8500 |

## Verification

Run the test to see the new context:

```bash
python3 test_llm_direct.py

# Look for these lines:
Using context size:
  Runner:    4000 / 5678 chars    # 70% of script included
  Generator: 4000 / 6789 chars    # 59% of script included
```

Much better than the old 26%! ✅

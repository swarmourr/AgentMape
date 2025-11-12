# Testing LLM Request and Response

## Quick Test - See Request & Response

Run this on your test computer to see EXACTLY what's sent to LLM and what it responds:

```bash
cd /home/hsafri/MAPEAgents/WorkflowValidator
python3 test_llm_direct.py
```

## What You'll See

### 1. File Reading
```
Reading scripts...
  Runner:    /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
  Generator: /home/hsafri/LLM-Fine-Tune/workflow.py

✓ Runner read: 234 chars
✓ Generator read: 1456 chars
```

### 2. Config Loading
```
Loading LLM configuration...
✓ Config loaded
  Enabled: True
  Host:    https://taimg-90-101-5-186.a.free.pinggy.link
  Model:   glm-4.6:cloud
```

### 3. Backend Check
```
Initializing LLM backend...
✓ Backend initialized

Checking backend availability...
✓ Backend is AVAILABLE
```

### 4. THE REQUEST (Full Prompt)
```
================================================================================
REQUEST TO LLM
================================================================================
You are analyzing a workflow generation system with two scripts:

1. RUNNER SCRIPT (orchestrator that executes the generator):
```
#!/bin/bash
# Your actual runner script content here...
```

2. GENERATOR SCRIPT (creates the workflow YAML):
```
#!/usr/bin/env python3
# Your actual generator script content here...
```

TASK: Determine the EXACT path or pattern where the workflow YAML file(s) will be saved.

Look for:
- Output file paths in generator...
- Output directories in generator...
...

Response:
================================================================================
Prompt length: 2847 chars
Temperature: 0.1
Max tokens: 100
================================================================================

⏳ Sending request to LLM...
   Host: https://taimg-90-101-5-186.a.free.pinggy.link
   Model: glm-4.6:cloud
   Please wait...
```

### 5. THE RESPONSE (Raw from LLM)
```
================================================================================
RESPONSE FROM LLM
================================================================================
workflows/pipeline.yml
================================================================================
Response length: 22 chars
================================================================================

Cleaned response: 'workflows/pipeline.yml'

✅ SUCCESS! LLM detected path: workflows/pipeline.yml

💾 Response saved to: /tmp/llm_response_test.txt
```

## When Running the Actual Validator

When you run the validator with `-v`, you'll now see:

```bash
python3.11 cli.py workflow.py --runner run.sh -v
```

You'll see the same output:

```
================================================================================
LLM REQUEST
================================================================================
You are analyzing a workflow generation system with two scripts:
...
================================================================================
Prompt length: 2847 chars
Temperature: 0.1
Max tokens: 100
================================================================================

Sending to LLM...

================================================================================
LLM RESPONSE
================================================================================
workflows/pipeline.yml
================================================================================
Response length: 22 chars
================================================================================

✅ LLM detected path: workflows/pipeline.yml
```

## Files Created

After running the test:

1. **`/tmp/llm_prompt_test.txt`** - Full prompt sent to LLM
2. **`/tmp/llm_response_test.txt`** - Raw and cleaned response

You can check these files:
```bash
# See the full prompt
cat /tmp/llm_prompt_test.txt

# See the response
cat /tmp/llm_response_test.txt
```

## Possible Responses

### ✅ Success - Path Detected
```
workflows/pipeline.yml
```
**Meaning**: LLM found the output path!

### ❌ Failure - NONE
```
NONE
```
**Meaning**: LLM couldn't find output path in the scripts

**Why?**
- Output path is after line ~60 (only first 1500 chars sent)
- Output path is computed dynamically
- No explicit OUTPUT_FILE/OUTPUT_DIR variables

**Fix**: Add this to top of your generator:
```python
OUTPUT_FILE = "workflows/pipeline.yml"  # <-- Add this at line 5
```

### ❌ Error - Connection Failed
```
❌ LLM request FAILED
   Error: Connection timeout
```
**Why?**: Can't reach Ollama server

**Fix**: Test connection:
```bash
curl https://taimg-90-101-5-186.a.free.pinggy.link/api/version
```

## Debugging Tips

### 1. Check the Prompt
```bash
cat /tmp/llm_prompt_test.txt
```

Look for:
- Is your runner script included?
- Is your generator script included?
- Can you see output path information in the content?
- Is important info being cut off at 1500 chars?

### 2. Check Your Scripts
```bash
# See first 50 lines of generator
head -50 /home/hsafri/LLM-Fine-Tune/workflow.py

# Search for output-related code
grep -i "output\|yaml\|open\|write" /home/hsafri/LLM-Fine-Tune/workflow.py
```

### 3. Test with Simple Example
If your scripts don't work, test with examples:
```bash
# Uses example scripts that definitely work
python3 test_llm_direct.py
```

### 4. Increase Content Length
If your output path is far down in the file, edit `runner_analyzer.py`:
```python
# Line 159 and 164, change:
{content[:1500]}        # From 1500
{content[:3000]}        # To 3000

{generator_content[:1500]}  # From 1500
{generator_content[:3000]}  # To 3000
```

## Integration Test

After direct test works, test with actual validator:

```bash
cd /home/hsafri/MAPEAgents/WorkflowValidator

python3.11 cli.py ../../LLM-Fine-Tune/workflow.py \
  --runner /home/hsafri/LLM-Fine-Tune/run_workdlows.sh \
  --workflow-dir ../../LLM-Fine-Tune/ \
  -l full -m hybrid -v 2>&1 | tee validator_output.log
```

You should see:
1. The full LLM request printed
2. The full LLM response printed
3. The detected path
4. Validation proceeding

## Summary Commands

```bash
# Direct LLM test (shows request & response)
python3 test_llm_direct.py

# See saved prompt
cat /tmp/llm_prompt_test.txt

# See saved response
cat /tmp/llm_response_test.txt

# Run validator with LLM (shows request & response inline)
python3.11 cli.py workflow.py --runner run.sh -v

# Test Ollama connection
curl https://taimg-90-101-5-186.a.free.pinggy.link/api/version
```

## Expected Flow

When everything works:
```
1. Read scripts                    ✓
2. Load LLM config                 ✓
3. Initialize backend              ✓
4. Check availability              ✓
5. Build prompt with both scripts  ✓
6. Send to LLM                     ✓
7. Receive response                ✓
8. Extract path                    ✓
9. Use for validation              ✓
```

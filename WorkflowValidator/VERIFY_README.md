# Verification Script - How to Run

## Purpose
This script helps you verify if the LLM analysis is being called correctly and see exactly what's happening in the detection flow.

## On Your Test Computer

### Step 1: Copy Files
Copy the WorkflowValidator directory to your test computer at:
```bash
/home/hsafri/MAPEAgents/WorkflowValidator/
```

### Step 2: Run Verification Script
```bash
cd /home/hsafri/MAPEAgents/WorkflowValidator
python3 verify_llm_flow.py
```

## What the Script Does

### Step 1: Check File Paths
- Verifies that your runner and generator scripts exist
- Shows file paths being used

### Step 2: Read File Contents
- Reads both scripts
- Shows first 200 chars of each
- Confirms files are readable

### Step 3: Test Rule-Based Detection
- Tests all regex patterns against both scripts
- Shows which patterns match (if any)
- This is CRITICAL - if rule-based finds something, LLM is never called!

### Step 4: Determine if LLM Will Be Called
- If rule-based found something → LLM NOT called ❌
- If rule-based found nothing → LLM WILL be called ✓

### Step 5: Check LLM Configuration
- Reads validator_config.json
- Shows if LLM backend is enabled
- Shows host, model, etc.

### Step 6: Test LLM Backend Availability
- Tries to initialize OllamaBackend
- Tests if backend.is_available() returns True
- Shows connection status

### Step 7: Build and Show Prompt
- If LLM will be called, builds the exact prompt
- Shows prompt length and content preview
- **Saves full prompt to: `/tmp/llm_prompt_debug.txt`**

### Step 8: Send to LLM (if enabled)
- Actually calls the LLM with the prompt
- Shows raw response
- Shows cleaned response
- Shows if path was detected

## Expected Output

### Scenario 1: Rule-Based Detects Output
```
[STEP 3] Testing rule-based detection...
  Checking RUNNER patterns...
    ✗ No matches in runner
  Checking GENERATOR patterns...
    ✓ MATCHED [OUTPUT variable]: generated_workflows/pipeline.yml

[STEP 4] Determining if LLM will be called...
  ✗ Rule-based found in GENERATOR: generated_workflows/pipeline.yml
  → LLM will NOT be called (early return)

SUMMARY
Rule-based detected in generator: generated_workflows/pipeline.yml
LLM backend enabled:              True
Will LLM be called:               False

✓ Output detected by rule-based patterns
  Final result: generated_workflows/pipeline.yml
```

### Scenario 2: LLM Is Called
```
[STEP 3] Testing rule-based detection...
  Checking RUNNER patterns...
    ✗ No matches in runner
  Checking GENERATOR patterns...
    ✗ No matches in generator

[STEP 4] Determining if LLM will be called...
  ✓ Rule-based detection failed
  → LLM WILL be called

[STEP 5] Checking LLM backend configuration...
  Enabled:     True
  Host:        https://taimg-90-101-5-186.a.free.pinggy.link
  Model:       glm-4.6:cloud
  ✓ LLM backend is ENABLED

[STEP 6] Testing LLM backend availability...
  ✓ Backend initialized
  ✓ Backend is AVAILABLE

[STEP 7] Building prompt for LLM...
  Prompt length: 2847 chars
  ✓ Full prompt saved to: /tmp/llm_prompt_debug.txt

[STEP 8] Sending prompt to LLM...
  ✓ LLM response received (45 chars)

  RAW RESPONSE:
  workflows/pipeline.yml

  CLEANED RESPONSE:
  workflows/pipeline.yml

  ✅ LLM detected: workflows/pipeline.yml

SUMMARY
Rule-based detected in runner:    No
Rule-based detected in generator: No
LLM backend enabled:              True
LLM backend available:            True
Will LLM be called:               True

✓ LLM analysis was called (see above for result)
```

### Scenario 3: LLM Fails to Detect
```
[STEP 8] Sending prompt to LLM...
  ✓ LLM response received (4 chars)

  RAW RESPONSE:
  NONE

  CLEANED RESPONSE:
  NONE

  ❌ LLM could not determine output location

SUMMARY
Will LLM be called:               True

❌ Neither rule-based nor LLM will detect output
  User will be prompted interactively
```

## Debugging

### Issue: Rule-based detects when it shouldn't
If you see:
```
✓ MATCHED [something]: some/path
→ LLM will NOT be called (early return)
```

**Solution**: The rule-based pattern is matching something in your script. Check:
1. Is this the correct path?
2. If yes, great! No need for LLM
3. If no, the pattern is too broad and needs fixing

### Issue: LLM backend not available
If you see:
```
❌ Backend is NOT AVAILABLE
```

**Debug**:
```bash
# Test Ollama connectivity
curl https://taimg-90-101-5-186.a.free.pinggy.link/api/version

# Test model
curl -X POST https://taimg-90-101-5-186.a.free.pinggy.link/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-4.6:cloud",
    "prompt": "Hello",
    "stream": false
  }'
```

### Issue: LLM returns "NONE"
If LLM is called but returns "NONE":

1. Check the saved prompt:
```bash
cat /tmp/llm_prompt_debug.txt
```

2. Verify your scripts have output information in first 1500 chars
3. Add explicit OUTPUT variables:
```python
# Add this to top of generator
OUTPUT_FILE = "workflows/pipeline.yml"
```

## Files to Check

After running verification script:

1. **Prompt file**: `/tmp/llm_prompt_debug.txt`
   - Contains exact prompt sent to LLM
   - Check if your scripts are properly included

2. **Log file** (if using validator):
   - `/home/hsafri/MAPEAgents/WorkflowValidator/validator.log`
   - Shows detailed logging

## Next Steps

After verification:

### If LLM is being called correctly:
```bash
# Run actual validator
cd /home/hsafri/MAPEAgents/WorkflowValidator
python3.11 cli.py ../../LLM-Fine-Tune/workflow.py \
  --runner /home/hsafri/LLM-Fine-Tune/run_workdlows.sh \
  --workflow-dir ../../LLM-Fine-Tune/ \
  -l full -m hybrid -v
```

### If LLM is NOT being called:
- Check why rule-based is detecting (might be good!)
- Or check why LLM backend is unavailable
- Or use manual path: `--generated-workflows workflows/`

## Questions to Answer

After running this script, you should know:

1. ✓ Are my script files being read correctly?
2. ✓ Is rule-based detection finding something?
3. ✓ Is LLM backend enabled in config?
4. ✓ Is LLM backend available/reachable?
5. ✓ What exact prompt is being sent to LLM?
6. ✓ What response is LLM returning?
7. ✓ Why is/isn't LLM being called?

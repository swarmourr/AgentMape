# Debugging LLM Detection

## Problem
You want to see exactly what prompt is being sent to the LLM and what response it returns.

## Solution 1: Use the Test Script

Run the test script that shows the exact prompt:

```bash
cd /Users/hamzasafri/Desktop/AgentMape/WorkflowValidator
python3 test_llm_prompt.py
```

This will:
1. Read your actual runner and generator scripts
2. Build the exact prompt that would be sent
3. Show you the complete prompt
4. Test the LLM backend connection
5. Send the prompt to LLM
6. Show you the raw response
7. Show you the cleaned response

**Expected Output:**
```
================================================================================
TESTING LLM PROMPT GENERATION
================================================================================

📄 Runner script length: XXX chars
📄 Generator script length: XXX chars

================================================================================
EXACT PROMPT THAT WILL BE SENT TO LLM:
================================================================================
You are analyzing a workflow generation system with two scripts:

1. RUNNER SCRIPT (orchestrator that executes the generator):
```
[your runner script content]
```

2. GENERATOR SCRIPT (creates the workflow YAML):
```
[your generator script content]
```

TASK: Determine the EXACT path or pattern where the workflow YAML file(s) will be saved.
...

================================================================================

Total prompt length: XXXX chars
Runner content sent: XXX chars (truncated from XXX)
Generator content sent: XXX chars (truncated from XXX)

================================================================================
TESTING LLM BACKEND CONNECTION
================================================================================
✓ Config loaded
  Enabled: True
  Host: https://taimg-90-101-5-186.a.free.pinggy.link
  Model: glm-4.6:cloud
✓ Backend initialized
✓ Backend is available

================================================================================
SENDING PROMPT TO LLM...
================================================================================

================================================================================
LLM RESPONSE:
================================================================================
[actual LLM response]
================================================================================

Cleaned response: [cleaned response]
✅ LLM detected: [path]
```

## Solution 2: Enable Verbose Mode

Run the validator with verbose mode to see logging:

```bash
cd /home/hsafri/MAPEAgents/WorkflowValidator

# Set logging to DEBUG level
export PYTHONUNBUFFERED=1

python3.11 cli.py ../../LLM-Fine-Tune/workflow.py \
  --runner /home/hsafri/LLM-Fine-Tune/run_workdlows.sh \
  --workflow-dir ../../LLM-Fine-Tune/ \
  -l full -m hybrid -v 2>&1 | tee llm_debug.log
```

Look for these log lines:
```
INFO:__main__:Analyzing runner script: /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
INFO:__main__:Also reading generator script: ../../LLM-Fine-Tune/workflow.py
INFO:__main__:Using LLM to analyze BOTH runner and generator together...
INFO:__main__:Sending prompt to LLM (length: XXXX chars)
INFO:__main__:  Runner content: XXX chars
INFO:__main__:  Generator content: XXX chars
INFO:__main__:LLM response received (length: XX chars)
INFO:__main__:Cleaned LLM response: [path]
```

## Solution 3: Save Prompt to File

Add this code to save the prompt to a file for inspection:

```python
# In runner_analyzer.py, add before llm_backend.generate():
with open('/tmp/llm_prompt.txt', 'w') as f:
    f.write(prompt)
print("Prompt saved to /tmp/llm_prompt.txt")
```

## Common Issues

### Issue 1: LLM Returns "NONE"
**Reason**: LLM couldn't find output path in the scripts

**Debug**:
1. Check if your scripts actually contain output path information
2. Look at the truncated content (first 1500 chars) - is the output path in there?
3. If output path is after line 50+, increase truncation limit

**Fix**:
```python
# In runner_analyzer.py, increase truncation:
{content[:3000]}  # Instead of [:1500]
{generator_content[:3000]}  # Instead of [:1500]
```

### Issue 2: LLM Backend Not Available
**Reason**: Ollama service not reachable

**Debug**:
```bash
# Test Ollama connectivity
curl https://taimg-90-101-5-186.a.free.pinggy.link/api/version

# Check if model is available
curl -X POST https://taimg-90-101-5-186.a.free.pinggy.link/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "glm-4.6:cloud", "prompt": "test", "stream": false}'
```

### Issue 3: Prompt Too Long
**Reason**: Scripts are very large, prompt exceeds token limit

**Fix**:
- Reduce truncation limit
- Or use rule-based detection instead
- Or split analysis into multiple calls

### Issue 4: Wrong Model
**Reason**: Model doesn't understand the task

**Fix**:
```json
// In validator_config.json
{
  "llm_backend": {
    "model": "llama3.3:latest"  // Try different model
  }
}
```

## Analyzing the Prompt

When you see the prompt, check:

1. **Is the runner script content correct?**
   - Should show the actual bash/shell script
   - Look for `python3` commands, redirections, environment variables

2. **Is the generator script content correct?**
   - Should show the actual Python script
   - Look for `open()`, `Path()`, `OUTPUT_FILE`, etc.

3. **Is the content truncated at a bad spot?**
   - If output path is at line 60 but only 40 lines are sent, it will fail
   - Increase truncation limit if needed

4. **Is the prompt clear enough?**
   - Does it explain what to look for?
   - Are examples provided?

## Improving Detection

If LLM consistently fails, try:

1. **Add comments to your scripts**:
```python
# Output workflow to: workflows/pipeline.yml
OUTPUT_FILE = "workflows/pipeline.yml"
```

2. **Use clear variable names**:
```python
# Good
OUTPUT_FILE = "workflow.yml"

# Bad
out = "workflow.yml"
```

3. **Put output logic early in file**:
```python
# Put this at top (within first 1500 chars)
OUTPUT_DIR = "workflows"
OUTPUT_FILE = "pipeline.yml"

# Not at bottom
```

4. **Use explicit paths**:
```bash
# Good
python3 generator.py > workflows/pipeline.yml

# Bad (harder to detect)
python3 generator.py > $OUTPUT
```

## Manual Testing

Test the LLM directly:

```python
from validators.llm_enhanced.llm_backends import OllamaBackend
import json

config = {
    "host": "https://taimg-90-101-5-186.a.free.pinggy.link",
    "model": "glm-4.6:cloud",
    "temperature": 0.1,
    "max_tokens": 100
}

backend = OllamaBackend(config)

prompt = """
Analyze this Python script and find where it saves YAML files:

```python
OUTPUT_FILE = "workflows/pipeline.yml"
with open(OUTPUT_FILE, 'w') as f:
    yaml.dump(workflow, f)
```

Respond with ONLY the path. Example: "workflows/pipeline.yml"
"""

response = backend.generate(prompt)
print(response)
```

## Getting Help

If LLM detection still fails:

1. Run `test_llm_prompt.py` and save the output
2. Check if LLM response makes sense
3. Share the prompt and response for debugging
4. Use `--generated-workflows` to bypass auto-detection:

```bash
python3 cli.py workflow.py --runner run.sh --generated-workflows workflows/
```

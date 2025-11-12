# Summary: LLM Integration for Output Detection

## What Was Implemented

### 1. Combined LLM Analysis
- **File**: [runner_analyzer.py](runner_analyzer.py)
- **Function**: `_llm_based_detection(content, llm_backend, generator_content=None)`
- **What it does**: Sends BOTH runner and generator scripts to LLM together
- **Purpose**: LLM can merge information from both scripts to find output path

### 2. Detection Flow
```
1. Rule-based detection on runner   → If found, return ✓
2. Rule-based detection on generator → If found, return ✓
3. LLM analysis on BOTH scripts      → If found, return ✓
4. Interactive user prompt           → Ask user
5. Stdout capture fallback           → Last resort
```

### 3. LLM Backend Configuration
- **File**: [validator_config.json](validator_config.json)
- **Settings**:
  ```json
  {
    "llm_backend": {
      "enabled": true,
      "host": "https://taimg-90-101-5-186.a.free.pinggy.link",
      "model": "glm-4.6:cloud",
      "timeout": 60,
      "temperature": 0.1,
      "max_tokens": 4000
    }
  }
  ```

## How to Verify It's Working

### Method 1: Run Verification Script
```bash
cd /home/hsafri/MAPEAgents/WorkflowValidator
python3 verify_llm_flow.py
```

This will show you:
- ✓ If rule-based detects anything (if yes, LLM not needed)
- ✓ If LLM backend is enabled and available
- ✓ Exact prompt sent to LLM
- ✓ LLM response
- ✓ Why LLM is/isn't being called

### Method 2: Run Actual Validator with Verbose
```bash
cd /home/hsafri/MAPEAgents/WorkflowValidator
python3.11 cli.py ../../LLM-Fine-Tune/workflow.py \
  --runner /home/hsafri/LLM-Fine-Tune/run_workdlows.sh \
  --workflow-dir ../../LLM-Fine-Tune/ \
  -l full -m hybrid -v 2>&1 | tee validation.log
```

Look for these lines:
```
🔍 Analyzing runner to detect workflow output location...
   ✓ LLM backend available for intelligent analysis
   Using: Rule-based + LLM analysis
   LLM will analyze BOTH scripts together for better context

   📄 Runner:    /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
   📄 Generator: ../../LLM-Fine-Tune/workflow.py
   🔍 Analyzing both scripts to determine output location...
```

Then either:
```
   ✅ Auto-detected output: workflows/pipeline.yml
```

Or:
```
   ⚠️  Could not auto-detect output location

❓ Where does the runner save workflow YAML files?
   Examples:
   - output/workflow.yml  (single file)
   - output/             (directory)
   - output/*.yml        (glob pattern)
   - [press Enter to capture stdout instead]

   Output location: _
```

## Key Files

### Core Implementation
1. **[runner_analyzer.py](runner_analyzer.py)** - Detection logic
   - `analyze_runner_script()` - Main function
   - `_rule_based_detection()` - Regex patterns
   - `_llm_based_detection()` - LLM analysis with combined prompt
   - `find_generated_workflows()` - Search for generated files

2. **[cli.py](cli.py)** - CLI integration (lines 321-503)
   - Initializes LLM backend
   - Calls analyzer with both scripts
   - Handles user prompts
   - Falls back to stdout capture

3. **[validator_config.json](validator_config.json)** - Configuration
   - LLM backend settings
   - Model selection
   - Timeout and temperature

### Testing & Debugging
1. **[verify_llm_flow.py](verify_llm_flow.py)** - Complete verification script
2. **[test_llm_prompt.py](test_llm_prompt.py)** - Show exact prompt
3. **[VERIFY_README.md](VERIFY_README.md)** - Instructions
4. **[DEBUG_LLM.md](DEBUG_LLM.md)** - Debugging guide

### Documentation
1. **[COMBINED_LLM_ANALYSIS.md](docs/COMBINED_LLM_ANALYSIS.md)** - How combined analysis works
2. **[AUTO_DETECTION_WORKFLOW.md](docs/AUTO_DETECTION_WORKFLOW.md)** - Complete detection flow
3. **[DUAL_ANALYSIS.md](docs/DUAL_ANALYSIS.md)** - Runner + generator analysis

### Examples
1. **[test_combined_analysis.py](examples/test_combined_analysis.py)** - Generator with split path
2. **[test_combined_runner.sh](examples/test_combined_runner.sh)** - Runner setting env vars
3. **[test_generator_with_output.py](examples/test_generator_with_output.py)** - Simple generator
4. **[test_runner_simple.sh](examples/test_runner_simple.sh)** - Simple runner

## Common Issues & Solutions

### Issue 1: LLM Not Being Called
**Symptom**: Verification shows "LLM will NOT be called"

**Cause**: Rule-based detection found something

**Solution**:
- Check if detected path is correct
- If yes, great! No need for LLM
- If no, adjust rule-based patterns

### Issue 2: LLM Backend Not Available
**Symptom**: "Backend is NOT AVAILABLE"

**Debug**:
```bash
curl https://taimg-90-101-5-186.a.free.pinggy.link/api/version
```

**Solution**:
- Check network connectivity
- Verify Ollama service is running
- Check firewall/proxy settings

### Issue 3: LLM Returns "NONE"
**Symptom**: LLM is called but returns "NONE"

**Cause**: LLM couldn't find output info in scripts

**Solution**:
1. Check prompt: `cat /tmp/llm_prompt_debug.txt`
2. Verify output logic is in first 1500 chars of scripts
3. Add explicit OUTPUT variables:
   ```python
   OUTPUT_FILE = "workflows/pipeline.yml"
   ```

### Issue 4: Scripts Not Found
**Symptom**: "Files not found" error

**Solution**:
- Verify file paths:
  ```bash
  ls -la /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
  ls -la /home/hsafri/LLM-Fine-Tune/workflow.py
  ```
- Check working directory
- Use absolute paths

## Testing Checklist

Run on your test computer:

- [ ] Copy WorkflowValidator to `/home/hsafri/MAPEAgents/WorkflowValidator/`
- [ ] Run `python3 verify_llm_flow.py`
- [ ] Check: Are files being read? (Step 1-2)
- [ ] Check: Does rule-based detect anything? (Step 3)
- [ ] Check: Is LLM enabled? (Step 5)
- [ ] Check: Is LLM available? (Step 6)
- [ ] Check: What prompt is sent? (Step 7, save to `/tmp/llm_prompt_debug.txt`)
- [ ] Check: What does LLM respond? (Step 8)
- [ ] Run actual validator: `python3.11 cli.py ... -v`
- [ ] Verify output detection works

## Expected Behavior

### Scenario 1: Rule-based detects (best case)
```
Rule-based detection found in generator: workflows/pipeline.yml
→ Return immediately, no LLM needed
→ Fast and efficient
```

### Scenario 2: LLM detects (good case)
```
Rule-based failed
→ Call LLM with both scripts
→ LLM finds: workflows/pipeline.yml
→ Use detected path
```

### Scenario 3: Both fail (fallback case)
```
Rule-based failed
→ LLM returns "NONE"
→ Prompt user interactively
→ User provides path OR presses Enter for stdout
```

## Quick Commands

```bash
# Verify LLM flow
python3 verify_llm_flow.py

# See exact prompt
cat /tmp/llm_prompt_debug.txt

# Run validator with verbose
python3.11 cli.py workflow.py --runner run.sh -v

# Test Ollama
curl https://taimg-90-101-5-186.a.free.pinggy.link/api/version

# Manual override (skip detection)
python3.11 cli.py workflow.py --runner run.sh --generated-workflows workflows/
```

## Next Steps

1. Run `verify_llm_flow.py` on your test computer
2. Check the output at each step
3. Look at the saved prompt: `/tmp/llm_prompt_debug.txt`
4. Share the output if you need help debugging
5. Once working, run the actual validator

# Quick Test - Run This First!

## On Your Test Computer

### Step 1: Go to directory
```bash
cd /home/hsafri/MAPEAgents/WorkflowValidator
```

### Step 2: Run verification
```bash
python3 verify_llm_flow.py
```

### Step 3: Check the output

Look for these key indicators:

#### ✅ GOOD - Rule-based detected:
```
[STEP 3] Testing rule-based detection...
  ✓ MATCHED [OUTPUT variable]: workflows/pipeline.yml

→ LLM will NOT be called (early return)

SUMMARY
✓ Output detected by rule-based patterns
  Final result: workflows/pipeline.yml
```
**Meaning**: Detection works! LLM not needed.

---

#### ✅ GOOD - LLM detected:
```
[STEP 4] Determining if LLM will be called...
  ✓ Rule-based detection failed
  → LLM WILL be called

[STEP 8] Sending prompt to LLM...
  ✅ LLM detected: workflows/pipeline.yml

SUMMARY
✓ LLM analysis was called
```
**Meaning**: LLM is working correctly!

---

#### ❌ BAD - LLM not available:
```
[STEP 6] Testing LLM backend availability...
  ❌ Backend is NOT AVAILABLE
```
**Fix**: Check Ollama connection:
```bash
curl https://taimg-90-101-5-186.a.free.pinggy.link/api/version
```

---

#### ❌ BAD - LLM returns NONE:
```
[STEP 8] Sending prompt to LLM...
  ❌ LLM could not determine output location
```
**Fix**: Check the prompt:
```bash
cat /tmp/llm_prompt_debug.txt
```

Are your scripts included? Is output info visible?

---

### Step 4: If all good, run actual validator
```bash
python3.11 cli.py ../../LLM-Fine-Tune/workflow.py \
  --runner /home/hsafri/LLM-Fine-Tune/run_workdlows.sh \
  --workflow-dir ../../LLM-Fine-Tune/ \
  -l full -m hybrid -v
```

## What You Should See

### When it works:
```
🏃 Runner script detected: run_workdlows.sh
   Generator: workflow.py

🔍 Analyzing runner to detect workflow output location...
   ✓ LLM backend available for intelligent analysis
   Using: Rule-based + LLM analysis
   LLM will analyze BOTH scripts together for better context

   📄 Runner:    /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
   📄 Generator: ../../LLM-Fine-Tune/workflow.py
   🔍 Analyzing both scripts to determine output location...
   ✅ Auto-detected output: workflows/pipeline.yml

   Running: bash /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
   ✅ Runner completed successfully

🔍 Looking for generated workflows at: workflows/pipeline.yml
   Found 1 workflow(s) to validate

📄 Validating pipeline.yml (1/1)...

🔍 Validating workflow (level: full)...
```

### When it needs help:
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
**Just type the path** where your workflows are saved!

## Troubleshooting

### Files not found?
```bash
# Check your files exist
ls -la /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
ls -la /home/hsafri/LLM-Fine-Tune/workflow.py
```

### Permission denied?
```bash
# Make scripts executable
chmod +x verify_llm_flow.py
chmod +x /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
```

### Import errors?
```bash
# Install dependencies
pip3 install --user pyyaml requests click
```

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python3 verify_llm_flow.py` | Verify detection flow |
| `cat /tmp/llm_prompt_debug.txt` | See LLM prompt |
| `python3.11 cli.py ... -v` | Run validator verbose |
| `python3.11 cli.py ... --generated-workflows output/` | Manual path |

## Need Help?

Share the output of:
```bash
python3 verify_llm_flow.py > llm_test_output.txt 2>&1
cat llm_test_output.txt
```

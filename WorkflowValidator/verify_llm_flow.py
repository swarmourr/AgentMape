#!/usr/bin/env python3
"""
Verification script to check if LLM analysis is being called
Run this to see the complete flow and what's happening
"""
import sys
import json
from pathlib import Path

print("=" * 80)
print("VERIFICATION: LLM ANALYSIS FLOW")
print("=" * 80)

# Step 1: Check if files exist
print("\n[STEP 1] Checking file paths...")
runner_path = "/home/hsafri/LLM-Fine-Tune/run_workdlows.sh"
generator_path = "/home/hsafri/LLM-Fine-Tune/workflow.py"

runner_exists = Path(runner_path).exists()
generator_exists = Path(generator_path).exists()

print(f"  Runner:    {runner_path}")
print(f"  Exists:    {runner_exists}")
print(f"  Generator: {generator_path}")
print(f"  Exists:    {generator_exists}")

if not runner_exists or not generator_exists:
    print("\n❌ Files not found. Using example files instead.")
    runner_path = "examples/test_runner_simple.sh"
    generator_path = "examples/test_generator_with_output.py"
    print(f"  Using runner: {runner_path}")
    print(f"  Using generator: {generator_path}")

# Step 2: Read file contents
print("\n[STEP 2] Reading file contents...")
try:
    with open(runner_path, 'r') as f:
        runner_content = f.read()
    print(f"  ✓ Runner read: {len(runner_content)} chars")
    print(f"  First 200 chars:\n{runner_content[:200]}")
except Exception as e:
    print(f"  ❌ Failed to read runner: {e}")
    sys.exit(1)

try:
    with open(generator_path, 'r') as f:
        generator_content = f.read()
    print(f"  ✓ Generator read: {len(generator_content)} chars")
    print(f"  First 200 chars:\n{generator_content[:200]}")
except Exception as e:
    print(f"  ❌ Failed to read generator: {e}")
    sys.exit(1)

# Step 3: Test rule-based detection
print("\n[STEP 3] Testing rule-based detection...")
import re

patterns = [
    (r'>\s*(["\']?)([^"\'\s]+\.ya?ml)\1', "File redirection"),
    (r'OUTPUT[_-]?(?:DIR|FILE|PATH)\s*=\s*["\']([^"\']+)["\']', "OUTPUT variable"),
    (r'(?:-o|--output(?:-dir)?)\s+(["\']?)([^"\'\s]+)\1', "Command arg"),
    (r'open\(["\']([^"\']+\.ya?ml)["\']', "open() function"),
    (r'Path\(["\']([^"\']+\.ya?ml)["\']', "Path() function"),
    (r'(?:save|write|dump)[_-]?(?:to|workflow|yaml|file)?\(["\']([^"\']+)["\']', "Save function"),
    (r'python3?\s+[^\n]+>\s*([^\s]+\.ya?ml)', "Python redirect"),
    (r'yaml\.dump\([^)]+,\s*open\(["\']([^"\']+\.ya?ml)["\']', "yaml.dump"),
    (r'with\s+open\(["\']([^"\']+\.ya?ml)["\']', "with open"),
]

runner_detected = None
generator_detected = None

print("  Checking RUNNER patterns...")
for pattern, desc in patterns:
    match = re.search(pattern, runner_content, re.IGNORECASE)
    if match:
        path = match.group(match.lastindex)
        if path and ('output' in path.lower() or '.yml' in path or '.yaml' in path):
            print(f"    ✓ MATCHED [{desc}]: {path}")
            runner_detected = path
            break

if not runner_detected:
    print("    ✗ No matches in runner")

print("  Checking GENERATOR patterns...")
for pattern, desc in patterns:
    match = re.search(pattern, generator_content, re.IGNORECASE)
    if match:
        path = match.group(match.lastindex)
        if path and ('output' in path.lower() or '.yml' in path or '.yaml' in path):
            print(f"    ✓ MATCHED [{desc}]: {path}")
            generator_detected = path
            break

if not generator_detected:
    print("    ✗ No matches in generator")

# Step 4: Determine if LLM will be called
print("\n[STEP 4] Determining if LLM will be called...")
will_call_llm = not (runner_detected or generator_detected)

if runner_detected:
    print(f"  ✗ Rule-based found in RUNNER: {runner_detected}")
    print(f"  → LLM will NOT be called (early return)")
elif generator_detected:
    print(f"  ✗ Rule-based found in GENERATOR: {generator_detected}")
    print(f"  → LLM will NOT be called (early return)")
else:
    print(f"  ✓ Rule-based detection failed")
    print(f"  → LLM WILL be called")

# Step 5: Check LLM backend configuration
print("\n[STEP 5] Checking LLM backend configuration...")
config_path = Path(__file__).parent / 'validator_config.json'

if not config_path.exists():
    print(f"  ❌ Config not found: {config_path}")
    sys.exit(1)

with open(config_path) as f:
    config = json.load(f)

llm_config = config.get('llm_backend', {})
print(f"  Config file: {config_path}")
print(f"  Enabled:     {llm_config.get('enabled', False)}")
print(f"  Provider:    {llm_config.get('provider', 'N/A')}")
print(f"  Host:        {llm_config.get('host', 'N/A')}")
print(f"  Model:       {llm_config.get('model', 'N/A')}")

if not llm_config.get('enabled'):
    print(f"  ❌ LLM backend is DISABLED")
    print(f"  → Even if rule-based fails, LLM won't be called")
    will_call_llm = False
else:
    print(f"  ✓ LLM backend is ENABLED")

# Step 6: Test LLM backend availability
if llm_config.get('enabled'):
    print("\n[STEP 6] Testing LLM backend availability...")
    try:
        from validators.llm_enhanced.llm_backends import OllamaBackend

        backend = OllamaBackend(llm_config)
        print(f"  ✓ Backend initialized")

        is_available = backend.is_available()
        if is_available:
            print(f"  ✓ Backend is AVAILABLE")
        else:
            print(f"  ❌ Backend is NOT AVAILABLE")
            print(f"  → LLM won't be called even if needed")
            will_call_llm = False

    except Exception as e:
        print(f"  ❌ Failed to initialize backend: {e}")
        will_call_llm = False
else:
    print("\n[STEP 6] Skipped (LLM disabled)")

# Step 7: Show what would be sent to LLM
if will_call_llm:
    print("\n[STEP 7] Building prompt for LLM...")

    prompt = f"""You are analyzing a workflow generation system with two scripts:

1. RUNNER SCRIPT (orchestrator that executes the generator):
```
{runner_content[:1500]}
```

2. GENERATOR SCRIPT (creates the workflow YAML):
```
{generator_content[:1500]}
```

TASK: Determine the EXACT path or pattern where the workflow YAML file(s) will be saved.

Look for:
- Output file paths in generator (e.g., "output/workflow.yml", OUTPUT_FILE = "workflow.yml")
- Output directories in generator (e.g., OUTPUT_DIR = "output")
- File redirection in runner (e.g., > output.yml)
- How runner executes generator (arguments, environment variables)
- Merge information from both scripts to build complete path

IMPORTANT:
- If generator has OUTPUT_DIR="output" and OUTPUT_FILE="workflow.yml", respond: "output/workflow.yml"
- If generator writes to "workflow.yml" and runner redirects > output/, respond: "output/workflow.yml"
- If generator uses variable paths, look for how runner sets them
- Combine directory from one script with filename from another

Respond with ONLY the path/pattern where workflows are saved, or "NONE" if cannot determine.

Examples:
- "output/workflow.yml"
- "generated_workflows/"
- "workflows/*.yml"
- "NONE"

Response:"""

    print(f"  Prompt length: {len(prompt)} chars")
    print(f"  Runner content: {len(runner_content[:1500])} chars (truncated from {len(runner_content)})")
    print(f"  Generator content: {len(generator_content[:1500])} chars (truncated from {len(generator_content)})")

    # Save prompt to file
    prompt_file = "/tmp/llm_prompt_debug.txt"
    with open(prompt_file, 'w') as f:
        f.write(prompt)
    print(f"  ✓ Full prompt saved to: {prompt_file}")

    # Try to call LLM
    if llm_config.get('enabled'):
        print("\n[STEP 8] Sending prompt to LLM...")
        try:
            response = backend.generate(prompt, temperature=0.1, max_tokens=100)
            print(f"  ✓ LLM response received ({len(response)} chars)")
            print(f"\n  RAW RESPONSE:")
            print(f"  {response}")

            # Clean response
            cleaned = response.strip().strip('"\'')
            cleaned = cleaned.split('\n')[0]

            print(f"\n  CLEANED RESPONSE:")
            print(f"  {cleaned}")

            if cleaned.upper() == 'NONE' or not cleaned:
                print(f"\n  ❌ LLM could not determine output location")
            else:
                print(f"\n  ✅ LLM detected: {cleaned}")

        except Exception as e:
            print(f"  ❌ LLM request failed: {e}")
            import traceback
            traceback.print_exc()
else:
    print("\n[STEP 7] LLM will NOT be called")
    print(f"  Reason: Rule-based detection found something OR LLM not available")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Rule-based detected in runner:    {runner_detected if runner_detected else 'No'}")
print(f"Rule-based detected in generator: {generator_detected if generator_detected else 'No'}")
print(f"LLM backend enabled:              {llm_config.get('enabled', False)}")
print(f"LLM backend available:            {is_available if 'is_available' in locals() else 'Not checked'}")
print(f"Will LLM be called:               {will_call_llm}")

if runner_detected or generator_detected:
    print(f"\n✓ Output detected by rule-based patterns")
    print(f"  Final result: {runner_detected or generator_detected}")
elif will_call_llm:
    print(f"\n✓ LLM analysis was called (see above for result)")
else:
    print(f"\n❌ Neither rule-based nor LLM will detect output")
    print(f"  User will be prompted interactively")

print("=" * 80)

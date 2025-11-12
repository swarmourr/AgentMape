#!/usr/bin/env python3
"""
Direct test of LLM with your actual scripts
Shows EXACTLY what request is sent and what response is received
"""
import sys
import json
from pathlib import Path

print("=" * 80)
print("DIRECT LLM TEST")
print("=" * 80)

# Configure paths
runner_path = "/home/hsafri/LLM-Fine-Tune/run_workdlows.sh"
generator_path = "/home/hsafri/LLM-Fine-Tune/workflow.py"

# Check if files exist, use examples if not
if not Path(runner_path).exists():
    print(f"⚠️  Runner not found: {runner_path}")
    print("Using example instead\n")
    runner_path = "examples/test_combined_runner.sh"
    generator_path = "examples/test_combined_analysis.py"

# Read scripts
print(f"Reading scripts...")
print(f"  Runner:    {runner_path}")
print(f"  Generator: {generator_path}\n")

try:
    with open(runner_path, 'r') as f:
        runner_content = f.read()
    print(f"✓ Runner read: {len(runner_content)} chars")
except Exception as e:
    print(f"❌ Failed to read runner: {e}")
    sys.exit(1)

try:
    with open(generator_path, 'r') as f:
        generator_content = f.read()
    print(f"✓ Generator read: {len(generator_content)} chars")
except Exception as e:
    print(f"❌ Failed to read generator: {e}")
    sys.exit(1)

# Load config
print(f"\nLoading LLM configuration...")
config_path = Path(__file__).parent / 'validator_config.json'

try:
    with open(config_path) as f:
        config = json.load(f)
    llm_config = config.get('llm_backend', {})
    print(f"✓ Config loaded")
    print(f"  Enabled: {llm_config.get('enabled')}")
    print(f"  Host:    {llm_config.get('host')}")
    print(f"  Model:   {llm_config.get('model')}")
except Exception as e:
    print(f"❌ Failed to load config: {e}")
    sys.exit(1)

if not llm_config.get('enabled'):
    print(f"\n❌ LLM backend is DISABLED in config")
    print(f"   Edit validator_config.json and set llm_backend.enabled = true")
    sys.exit(1)

# Initialize LLM backend
print(f"\nInitializing LLM backend...")
try:
    from validators.llm_enhanced.llm_backends import OllamaBackend
    backend = OllamaBackend(llm_config)
    print(f"✓ Backend initialized")
except Exception as e:
    print(f"❌ Failed to initialize backend: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check availability
print(f"\nChecking backend availability...")
try:
    if backend.is_available():
        print(f"✓ Backend is AVAILABLE")
    else:
        print(f"❌ Backend is NOT AVAILABLE")
        print(f"   Check if Ollama is running at: {llm_config.get('host')}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Availability check failed: {e}")
    sys.exit(1)

# Build prompt
print(f"\nBuilding prompt...")
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

print(f"✓ Prompt built: {len(prompt)} chars")
print(f"  Runner content sent:    {len(runner_content[:1500])} chars")
print(f"  Generator content sent: {len(generator_content[:1500])} chars")

# Save prompt to file
prompt_file = "/tmp/llm_prompt_test.txt"
with open(prompt_file, 'w') as f:
    f.write(prompt)
print(f"  Saved to: {prompt_file}")

# SHOW THE PROMPT
print("\n" + "=" * 80)
print("REQUEST TO LLM")
print("=" * 80)
print(prompt)
print("=" * 80)
print(f"Prompt length: {len(prompt)} chars")
print(f"Temperature: 0.1")
print(f"Max tokens: 100")
print("=" * 80)

# Send to LLM
print("\n⏳ Sending request to LLM...")
print(f"   Host: {llm_config.get('host')}")
print(f"   Model: {llm_config.get('model')}")
print(f"   Please wait...\n")

try:
    response = backend.generate(prompt, temperature=0.1, max_tokens=100)

    # SHOW THE RESPONSE
    print("=" * 80)
    print("RESPONSE FROM LLM")
    print("=" * 80)
    print(response)
    print("=" * 80)
    print(f"Response length: {len(response)} chars")
    print("=" * 80)

    # Clean and analyze response
    cleaned = response.strip().strip('"\'')
    cleaned = cleaned.split('\n')[0].strip()

    print(f"\nCleaned response: '{cleaned}'")

    if cleaned.upper() == 'NONE' or not cleaned:
        print(f"\n❌ LLM could not determine output location")
        print(f"   The LLM returned: {cleaned}")
        print(f"\n💡 Possible reasons:")
        print(f"   - Output path not visible in first 1500 chars")
        print(f"   - Output path is dynamic/computed at runtime")
        print(f"   - Scripts don't contain explicit output information")
    else:
        print(f"\n✅ SUCCESS! LLM detected path: {cleaned}")

    # Save response
    response_file = "/tmp/llm_response_test.txt"
    with open(response_file, 'w') as f:
        f.write(f"Raw response:\n{response}\n\nCleaned response:\n{cleaned}")
    print(f"\n💾 Response saved to: {response_file}")

except Exception as e:
    print(f"\n❌ LLM request FAILED")
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
print(f"Prompt saved to:   {prompt_file}")
print(f"Response saved to: {response_file}")
print("=" * 80)

#!/usr/bin/env python3
"""
Test script to show exactly what prompt is sent to the LLM
"""
import sys
from pathlib import Path

# Read your actual scripts
runner_path = "/home/hsafri/LLM-Fine-Tune/run_workdlows.sh"
generator_path = "/home/hsafri/LLM-Fine-Tune/workflow.py"

print("=" * 80)
print("TESTING LLM PROMPT GENERATION")
print("=" * 80)

# Check if files exist
if not Path(runner_path).exists():
    print(f"❌ Runner not found: {runner_path}")
    print("Using example runner instead...")
    runner_content = """#!/bin/bash
python3 workflow.py
"""
else:
    with open(runner_path, 'r') as f:
        runner_content = f.read()

if not Path(generator_path).exists():
    print(f"❌ Generator not found: {generator_path}")
    print("Using example generator instead...")
    generator_content = """#!/usr/bin/env python3
OUTPUT_FILE = "output/workflow.yml"
with open(OUTPUT_FILE, 'w') as f:
    yaml.dump(workflow, f)
"""
else:
    with open(generator_path, 'r') as f:
        generator_content = f.read()

print(f"\n📄 Runner script length: {len(runner_content)} chars")
print(f"📄 Generator script length: {len(generator_content)} chars")

# Build the exact prompt that would be sent to LLM
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

print("\n" + "=" * 80)
print("EXACT PROMPT THAT WILL BE SENT TO LLM:")
print("=" * 80)
print(prompt)
print("=" * 80)
print(f"\nTotal prompt length: {len(prompt)} chars")
print(f"Runner content sent: {len(runner_content[:1500])} chars (truncated from {len(runner_content)})")
print(f"Generator content sent: {len(generator_content[:1500])} chars (truncated from {len(generator_content)})")

# Now test if LLM backend is available
print("\n" + "=" * 80)
print("TESTING LLM BACKEND CONNECTION")
print("=" * 80)

try:
    import json
    from validators.llm_enhanced.llm_backends import OllamaBackend

    config_path = Path(__file__).parent / 'validator_config.json'
    with open(config_path) as f:
        config = json.load(f)

    llm_config = config.get('llm_backend', {})
    print(f"✓ Config loaded")
    print(f"  Enabled: {llm_config.get('enabled')}")
    print(f"  Host: {llm_config.get('host')}")
    print(f"  Model: {llm_config.get('model')}")

    backend = OllamaBackend(llm_config)
    print(f"✓ Backend initialized")

    if backend.is_available():
        print(f"✓ Backend is available")

        print("\n" + "=" * 80)
        print("SENDING PROMPT TO LLM...")
        print("=" * 80)

        response = backend.generate(prompt, temperature=0.1, max_tokens=100)

        print("\n" + "=" * 80)
        print("LLM RESPONSE:")
        print("=" * 80)
        print(response)
        print("=" * 80)

        # Clean response
        cleaned = response.strip().strip('"\'')
        cleaned = cleaned.split('\n')[0]

        print(f"\nCleaned response: {cleaned}")

        if cleaned.upper() == 'NONE' or not cleaned:
            print("❌ LLM could not determine output location")
        else:
            print(f"✅ LLM detected: {cleaned}")
    else:
        print("❌ Backend not available")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

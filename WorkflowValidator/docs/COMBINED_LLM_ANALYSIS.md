# Combined LLM Analysis: Runner + Generator

## Overview

The validator now sends **BOTH the runner script AND the generator script** to the LLM simultaneously, allowing it to understand the complete context and intelligently merge information from both files to determine the exact output path.

## Why Combined Analysis?

### Problem: Split Information

Often, the output path is **split across multiple scripts**:

**Example 1: Directory in Runner, Filename in Generator**

Runner (`run.sh`):
```bash
export OUTPUT_DIR="workflows"
python3 generator.py
```

Generator (`generator.py`):
```python
OUTPUT_FILE = "pipeline.yml"
output_path = f"{os.getenv('OUTPUT_DIR')}/{OUTPUT_FILE}"
```

**Solution**: LLM analyzes both → Combines to get: `workflows/pipeline.yml`

---

**Example 2: Directory in Generator, Redirection in Runner**

Generator (`generator.py`):
```python
OUTPUT_DIR = "output"
print(yaml.dump(workflow))  # Prints to stdout
```

Runner (`run.sh`):
```bash
cd output
python3 ../generator.py > workflow.yml
```

**Solution**: LLM analyzes both → Combines to get: `output/workflow.yml`

---

**Example 3: Variable Substitution**

Runner (`run.sh`):
```bash
ENV="production"
python3 generator.py --env $ENV
```

Generator (`generator.py`):
```python
env = args.env
output = f"workflows/{env}/pipeline.yml"
```

**Solution**: LLM analyzes both → Combines to get: `workflows/production/pipeline.yml` or `workflows/*.yml`

## Detection Flow

```
┌─────────────────────────────────────────┐
│  1. Rule-based Pattern Detection       │
│     - Try runner script                 │
│     - Try generator script              │
│     - Fast, no LLM needed               │
└──────────────┬──────────────────────────┘
               │
               ├─ FOUND ──> Use it ✓
               │
               ├─ NOT FOUND
               ▼
┌─────────────────────────────────────────┐
│  2. LLM Combined Analysis               │
│     - Send BOTH scripts to LLM          │
│     - LLM merges information            │
│     - Understands context & flow        │
└──────────────┬──────────────────────────┘
               │
               ├─ FOUND ──> Use it ✓
               │
               ├─ NOT FOUND
               ▼
┌─────────────────────────────────────────┐
│  3. Interactive User Prompt             │
└─────────────────────────────────────────┘
```

## LLM Prompt Structure

The LLM receives both scripts with clear context:

```
You are analyzing a workflow generation system with two scripts:

1. RUNNER SCRIPT (orchestrator that executes the generator):
```
[runner content]
```

2. GENERATOR SCRIPT (creates the workflow YAML):
```
[generator content]
```

TASK: Determine the EXACT path or pattern where the workflow YAML file(s) will be saved.

Look for:
- Output file paths in generator
- Output directories in generator
- File redirection in runner
- How runner executes generator
- Environment variables set by runner and used by generator
- Merge information from both scripts

IMPORTANT:
- If generator has OUTPUT_DIR="output" and OUTPUT_FILE="workflow.yml", respond: "output/workflow.yml"
- If generator writes to "workflow.yml" and runner redirects > output/, respond: "output/workflow.yml"
- Combine directory from one script with filename from another
```

## Use Cases

### Use Case 1: Environment Variable Flow

**Runner**:
```bash
#!/bin/bash
export WORKFLOW_DIR="generated_workflows"
export WORKFLOW_NAME="pipeline_v2.yml"
python3 workflow_generator.py
```

**Generator**:
```python
import os
output_dir = os.getenv('WORKFLOW_DIR', 'output')
output_name = os.getenv('WORKFLOW_NAME', 'workflow.yml')
output_path = f"{output_dir}/{output_name}"
with open(output_path, 'w') as f:
    yaml.dump(workflow, f)
```

**LLM Analysis**:
- Sees runner sets `WORKFLOW_DIR="generated_workflows"`
- Sees runner sets `WORKFLOW_NAME="pipeline_v2.yml"`
- Sees generator uses both via `os.getenv()`
- **Result**: `generated_workflows/pipeline_v2.yml`

---

### Use Case 2: Argument Passing

**Runner**:
```bash
#!/bin/bash
python3 generator.py --output-dir workflows --output-file pipeline.yml
```

**Generator**:
```python
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', default='output')
parser.add_argument('--output-file', default='workflow.yml')
args = parser.parse_args()

output = Path(args.output_dir) / args.output_file
```

**LLM Analysis**:
- Sees runner passes `--output-dir workflows`
- Sees runner passes `--output-file pipeline.yml`
- Sees generator uses both arguments
- **Result**: `workflows/pipeline.yml`

---

### Use Case 3: Directory Change + Relative Path

**Runner**:
```bash
#!/bin/bash
mkdir -p output/experiments
cd output/experiments
python3 ../../generator.py
```

**Generator**:
```python
output_file = "result.yml"
with open(output_file, 'w') as f:
    yaml.dump(workflow, f)
```

**LLM Analysis**:
- Sees runner creates and changes to `output/experiments`
- Sees generator writes to `result.yml` (relative)
- **Result**: `output/experiments/result.yml` or `output/experiments/*.yml`

---

### Use Case 4: Config File Reference

**Runner**:
```bash
#!/bin/bash
python3 generator.py --config config.json
```

**Config** (`config.json`):
```json
{
  "output": {
    "directory": "workflows",
    "filename": "pipeline.yml"
  }
}
```

**Generator**:
```python
config = json.load(open(args.config))
output_dir = config['output']['directory']
output_file = config['output']['filename']
output_path = f"{output_dir}/{output_file}"
```

**LLM Analysis**:
- Sees runner passes `--config config.json`
- Sees generator reads config but can't access config file directly
- **Result**: Asks user or suggests common patterns like `workflows/*.yml`

## Benefits

1. **Handles Split Paths**: Merges directory from one script with filename from another
2. **Understands Flow**: Traces how data flows from runner to generator
3. **Environment Awareness**: Recognizes environment variables set by runner
4. **Argument Tracking**: Follows command-line arguments passed to generator
5. **Context Understanding**: Sees the complete picture, not isolated scripts

## Implementation Details

### Function Signature
```python
def _llm_based_detection(
    content: str,              # Runner script content
    llm_backend,               # LLM backend instance
    generator_content: Optional[str] = None  # Generator script content
) -> Optional[str]:
```

### Analysis Strategy

1. **If both scripts provided**: Use combined analysis prompt
2. **If only runner**: Use single-script analysis prompt
3. **Temperature**: 0.1 (deterministic, focused)
4. **Max tokens**: 100 (just need the path)
5. **Truncation**: First 1500 chars of each script

### CLI Integration

```python
# Read both scripts
detected_pattern = analyze_runner_script(
    runner,
    llm_backend,
    generator_path=workflow  # Generator passed here
)
```

### User Feedback

```
🏃 Runner script detected: run.sh
   Generator: workflow.py

🔍 Analyzing runner to detect workflow output location...
   ✓ LLM backend available for intelligent analysis
   Using: Rule-based + LLM analysis
   LLM will analyze BOTH scripts together for better context

   📄 Runner:    run.sh
   📄 Generator: workflow.py
   🔍 Analyzing both scripts to determine output location...
   ✅ Auto-detected output: workflows/pipeline.yml
```

## Advanced Examples

### Example 1: Multi-stage Pipeline

**Runner**:
```bash
#!/bin/bash
STAGE=$1
OUTPUT_BASE="workflows"

case $STAGE in
  "dev")
    OUTPUT_DIR="$OUTPUT_BASE/dev"
    ;;
  "prod")
    OUTPUT_DIR="$OUTPUT_BASE/prod"
    ;;
esac

export OUTPUT_DIR
python3 generator.py
```

**Generator**:
```python
output_dir = os.getenv('OUTPUT_DIR')
output_file = f"{output_dir}/pipeline.yml"
```

**LLM Result**: `workflows/*/pipeline.yml` or `workflows/dev/pipeline.yml`

---

### Example 2: Timestamp-based Output

**Runner**:
```bash
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
python3 generator.py --timestamp $TIMESTAMP
```

**Generator**:
```python
output = f"workflows/pipeline_{args.timestamp}.yml"
```

**LLM Result**: `workflows/pipeline_*.yml` or `workflows/*.yml`

## Limitations

1. **Config files not analyzed**: If paths are in external config files, LLM may not find them
2. **Dynamic paths**: Runtime-computed paths may not be detectable
3. **Complex logic**: Deeply nested conditionals may confuse detection
4. **Token limits**: Only first 1500 chars of each script sent to LLM

## Fallback Strategy

If combined LLM analysis fails:

1. Ask user interactively for output location
2. Show examples based on detected patterns
3. Allow user to press Enter for stdout capture

## Best Practices

1. **Clear variable names**: Use `OUTPUT_DIR`, `OUTPUT_FILE`, `WORKFLOW_PATH`
2. **Consistent patterns**: Stick to common approaches
3. **Document in comments**: Add comments indicating output paths
4. **Avoid deep nesting**: Keep output logic simple and visible
5. **Test detection**: Run with `-v` to verify auto-detection works

## Testing

Test the combined analysis:

```bash
cd /Users/hamzasafri/Desktop/AgentMape/WorkflowValidator

# Test with split path example
python3 cli.py examples/test_combined_analysis.py \
    --runner examples/test_combined_runner.sh \
    -v

# Expected output:
# ✅ Auto-detected output: workflows/pipeline.yml
```

## Configuration

Ensure LLM backend is enabled in [validator_config.json](../validator_config.json):

```json
{
  "llm_backend": {
    "enabled": true,
    "host": "https://taimg-90-101-5-186.a.free.pinggy.link",
    "model": "glm-4.6:cloud",
    "temperature": 0.1,
    "max_tokens": 4000
  }
}
```

## See Also

- [Auto-Detection Workflow](AUTO_DETECTION_WORKFLOW.md) - Complete detection flow
- [Dual Analysis](DUAL_ANALYSIS.md) - Sequential runner + generator analysis
- [runner_analyzer.py](../runner_analyzer.py) - Implementation

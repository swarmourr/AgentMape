# Dual Analysis: Runner + Generator Detection

## Overview

The validator now performs **dual analysis** when using `--runner` without `--generated-workflows`. It analyzes both:

1. **Runner script** - The orchestrator that executes the generator
2. **Generator script** - The actual workflow generator (if runner doesn't reveal output)

This ensures maximum detection accuracy even when the runner script doesn't explicitly show where workflows are saved.

## Detection Flow

```
┌──────────────────────────────────┐
│  1. Analyze Runner Script        │
│     - Check for output paths     │
│     - Look for redirections      │
│     - Find directory patterns    │
└────────────┬─────────────────────┘
             │
             ├─ FOUND ──> Use detected path
             │
             ├─ NOT FOUND
             ▼
┌──────────────────────────────────┐
│  2. Analyze Generator Script     │
│     - Check Python file I/O      │
│     - Find variable assignments  │
│     - Detect YAML operations     │
└────────────┬─────────────────────┘
             │
             ├─ FOUND ──> Use detected path
             │
             ├─ NOT FOUND
             ▼
┌──────────────────────────────────┐
│  3. Ask User for Path            │
│     - Interactive prompt         │
│     - Show examples              │
└────────────┬─────────────────────┘
             │
             ├─ USER PROVIDES ──> Use it
             │
             ├─ PRESS ENTER
             ▼
┌──────────────────────────────────┐
│  4. Stdout Capture (fallback)    │
└──────────────────────────────────┘
```

## Why Dual Analysis?

### Scenario 1: Output in Runner Script
```bash
# runner.sh
#!/bin/bash
python3 generator.py > output/workflow.yml
```
**Detection**: Found in runner script ✓

### Scenario 2: Output in Generator Script
```bash
# runner.sh
#!/bin/bash
python3 generator.py  # No output indication here
```

```python
# generator.py
OUTPUT_FILE = "workflows/pipeline.yml"

with open(OUTPUT_FILE, 'w') as f:
    yaml.dump(workflow, f)
```
**Detection**: Not found in runner, checks generator → Found ✓

### Scenario 3: Complex Orchestrator
```bash
# runner.sh
#!/bin/bash
export CONFIG=$1
./orchestrate.py --config $CONFIG
```

```python
# orchestrate.py
config = load_config(sys.argv[2])
output_path = f"{config['output_dir']}/workflow.yml"
Path(output_path).write_text(yaml.dump(workflow))
```
**Detection**: Not found in runner, checks generator → Found ✓

## Generator Detection Patterns

The analyzer looks for these patterns in generator scripts:

### Python File Operations
```python
# Pattern 1: open() function
with open('output/workflow.yml', 'w') as f:
    yaml.dump(workflow, f)

# Pattern 2: Path.write_text()
Path('output/workflow.yml').write_text(yaml_content)

# Pattern 3: yaml.dump with file
yaml.dump(workflow, open('output/workflow.yml', 'w'))
```

### Variable Assignments
```python
# Pattern 4: OUTPUT_FILE variable
OUTPUT_FILE = "workflows/pipeline.yml"

# Pattern 5: OUTPUT_DIR variable
OUTPUT_DIR = "generated_workflows"

# Pattern 6: OUTPUT_PATH variable
OUTPUT_PATH = "output/workflow.yml"
```

### Save Functions
```python
# Pattern 7: Custom save functions
save_workflow('output/workflow.yml')
write_yaml('output/workflow.yml', workflow)
dump_to_file('output/workflow.yml', data)
```

## Examples

### Example 1: Simple Runner + Generator

**Runner Script** (`run.sh`):
```bash
#!/bin/bash
python3 workflow_generator.py
```

**Generator Script** (`workflow_generator.py`):
```python
OUTPUT_FILE = "output/pipeline.yml"

workflow = generate_pipeline()
with open(OUTPUT_FILE, 'w') as f:
    yaml.dump(workflow, f)
```

**Command**:
```bash
python3 cli.py workflow_generator.py --runner run.sh
```

**Output**:
```
🏃 Runner script detected: run.sh
   Generator: workflow_generator.py

🔍 Analyzing runner to detect workflow output location...
   Using: Rule-based + LLM analysis
   Analyzing runner: run.sh
   Will also check generator: workflow_generator.py
   No output found in runner, analyzing generator: workflow_generator.py
   ✅ Auto-detected output: output/pipeline.yml
```

### Example 2: Complex Orchestrator

**Runner Script** (`orchestrator.sh`):
```bash
#!/bin/bash
set -e

echo "Starting workflow generation..."
python3 $1 --config $2
echo "Workflow generation complete"
```

**Generator Script** (`advanced_generator.py`):
```python
import argparse
import yaml
from pathlib import Path

OUTPUT_DIR = "generated_workflows"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()

    workflow = generate_from_config(args.config)

    output_path = Path(OUTPUT_DIR) / "pipeline.yml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        yaml.dump(workflow, f)
```

**Command**:
```bash
python3 cli.py advanced_generator.py --runner orchestrator.sh \
    --workflow-args "--config config.json"
```

**Output**:
```
🏃 Runner script detected: orchestrator.sh
   Generator: advanced_generator.py

🔍 Analyzing runner to detect workflow output location...
   Analyzing runner: orchestrator.sh
   Will also check generator: advanced_generator.py
   No output found in runner, analyzing generator: advanced_generator.py
   ✅ Auto-detected output: generated_workflows
```

## Technical Details

### Function Signature
```python
def analyze_runner_script(
    runner_path: str,
    llm_backend=None,
    generator_path: Optional[str] = None
) -> Optional[str]:
```

### Analysis Steps

1. **Read runner script content**
2. **Apply rule-based patterns to runner**
3. **If LLM enabled, apply LLM analysis to runner**
4. **If nothing found and generator_path provided:**
   - Read generator script content
   - Apply rule-based patterns to generator
   - If LLM enabled, apply LLM analysis to generator
5. **Return detected path or None**

### CLI Integration

The CLI automatically passes the generator path:

```python
detected_pattern = analyze_runner_script(
    runner,
    llm_backend,
    generator_path=workflow  # Generator is passed here
)
```

## Benefits

1. **Higher Detection Rate**: Checks both scripts for output locations
2. **Flexible Architecture**: Works with various orchestration patterns
3. **No User Intervention**: Automatically finds outputs without prompting
4. **Smart Fallback**: If generator also doesn't reveal output, asks user
5. **Universal Support**: Works with Python, Shell, and mixed scripts

## Edge Cases Handled

### Case 1: Generator outputs to stdout
```python
# generator.py
print(yaml.dump(workflow))  # Prints to stdout
```
**Detection**: No file output found → Falls back to stdout capture ✓

### Case 2: Dynamic output paths
```python
# generator.py
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
output = f"output/workflow_{timestamp}.yml"
```
**Detection**: Finds pattern `output/workflow_` → Uses `output/*.yml` ✓

### Case 3: Configuration-based output
```python
# generator.py
config = yaml.safe_load(open('config.yml'))
output = config['output_path']  # Path from config file
```
**Detection**: No static path found → Prompts user ✓

## Troubleshooting

### Detection fails for both scripts
- Enable verbose mode: `-v`
- Check pattern matches in logs
- Enable LLM backend for smarter detection
- Use `--generated-workflows` to specify path explicitly

### False positives
- Analyzer might detect temporary files or comments
- Use `--generated-workflows` to override auto-detection

### LLM not analyzing generator
- Verify LLM backend is enabled and available
- Check generator script is readable
- Enable verbose mode to see analysis steps

## Best Practices

1. **Use clear variable names**: `OUTPUT_FILE`, `OUTPUT_DIR`, `OUTPUT_PATH`
2. **Add comments**: `# Save workflow to output/workflow.yml`
3. **Use consistent patterns**: Stick to common file operations
4. **Document output locations**: Add docstrings mentioning output paths
5. **Test detection**: Run with `-v` to verify auto-detection works

## See Also

- [Auto-Detection Workflow](AUTO_DETECTION_WORKFLOW.md) - Complete detection flow
- [Runner Guide](RUNNER_GUIDE.md) - Using `--runner` flag
- [runner_analyzer.py](../runner_analyzer.py) - Detection implementation

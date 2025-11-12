# Auto-Detection Workflow

## Overview

When using `--runner` without `--generated-workflows`, the validator automatically detects where the runner saves workflow files using a three-tier approach:

## Detection Flow

```
┌─────────────────────────────────────┐
│  1. Rule-based Pattern Detection   │
│     - Regex patterns for common     │
│       output paths and redirections │
│     - Fast, no LLM required         │
└──────────────┬──────────────────────┘
               │
               ├─ FOUND ──> Use detected path
               │
               ├─ NOT FOUND
               ▼
┌─────────────────────────────────────┐
│  2. LLM-based Analysis (optional)   │
│     - Intelligent code analysis     │
│     - Requires Ollama enabled       │
└──────────────┬──────────────────────┘
               │
               ├─ FOUND ──> Use detected path
               │
               ├─ NOT FOUND
               ▼
┌─────────────────────────────────────┐
│  3. Interactive User Prompt         │
│     - Ask user for output location  │
│     - Show examples and options     │
└──────────────┬──────────────────────┘
               │
               ├─ USER PROVIDES PATH ──> Use it
               │
               ├─ USER PRESSES ENTER
               ▼
┌─────────────────────────────────────┐
│  4. Stdout Capture (fallback)       │
│     - Run runner and capture stdout │
│     - Works if runner prints YAML   │
└─────────────────────────────────────┘
```

## Rule-based Detection Patterns

The validator looks for these common patterns:

### File Redirection
```bash
python3 generator.py > output/workflow.yml
./generate.sh > workflow.yml
```

### Variable Assignment
```bash
OUTPUT_DIR="output"
OUTPUT_FILE="workflow.yml"
```

### Command-line Arguments
```bash
python3 generator.py -o output/
python3 generator.py --output-dir output/
```

### Python File Operations
```python
open('output/workflow.yml', 'w')
with open('output.yml', 'w') as f:
```

### Directory Creation
```bash
mkdir -p output
cd output && generate_workflow.sh
```

## LLM-based Detection

If rule-based detection fails and LLM is enabled, the validator:

1. Reads the runner script content (first 2000 chars)
2. Sends it to Ollama with a specialized prompt
3. Asks the LLM to identify output paths
4. Validates the LLM response

### Enabling LLM Detection

Edit [validator_config.json](../validator_config.json):

```json
{
  "llm_backend": {
    "enabled": true,
    "provider": "ollama",
    "model": "llama2",
    "base_url": "http://localhost:11434"
  }
}
```

## Interactive Prompt

If both automated methods fail, the user is prompted:

```
❓ Where does the runner save workflow YAML files?
   Examples:
   - output/workflow.yml  (single file)
   - output/             (directory)
   - output/*.yml        (glob pattern)
   - [press Enter to capture stdout instead]

   Output location: _
```

### User Options

1. **Single file**: `output/workflow.yml` - Validates this specific file
2. **Directory**: `output/` - Finds all `.yml` and `.yaml` files in directory
3. **Glob pattern**: `output/*.yml` - Matches files using glob pattern
4. **Press Enter**: Falls back to stdout capture

## Examples

### Example 1: Python runner with output redirection
```bash
# Runner: run_generator.sh
#!/bin/bash
python3 generator.py > output/workflow.yml
```

**Detection**: Rule-based finds `> output/workflow.yml`
**Result**: Auto-detected, no prompt needed

### Example 2: Shell script with mkdir
```bash
# Runner: generate_workflows.sh
#!/bin/bash
mkdir -p generated_workflows
cd generated_workflows
./create_pipeline.py
```

**Detection**: Rule-based finds `mkdir -p generated_workflows` + YAML in script
**Result**: Auto-detected pattern: `generated_workflows/*.yml`

### Example 3: Complex orchestrator
```bash
# Runner: orchestrator.sh
#!/bin/bash
export CONFIG_FILE=$1
source config.sh
./complex_generator --config $CONFIG_FILE
```

**Detection**: Rule-based fails (no obvious output path)
**LLM Analysis**: If enabled, analyzes the code
**Prompt**: User asked for output location
**Result**: User provides `workflows/` or presses Enter for stdout

## Command Examples

### With auto-detection
```bash
# Validator will automatically detect output location
python3 cli.py workflow.py --runner generate.sh
```

### With explicit path (skips detection)
```bash
# Explicitly specify output location
python3 cli.py workflow.py --runner generate.sh --generated-workflows output/*.yml
```

### Verbose mode (see detection details)
```bash
# Show detailed detection process
python3 cli.py workflow.py --runner generate.sh -v
```

## Troubleshooting

### Detection fails with error
- Check runner script syntax
- Verify runner script exists and is readable
- Enable verbose mode: `-v`

### LLM detection not working
- Verify Ollama is running: `curl http://localhost:11434/api/version`
- Check `validator_config.json` has `"enabled": true`
- Ensure model is available: `ollama list`

### Interactive prompt doesn't appear
- Check if running in non-interactive environment
- Use `--generated-workflows` to specify path explicitly
- Verify stdout is not redirected

## Best Practices

1. **Use explicit paths for CI/CD**: Always use `--generated-workflows` in automated environments
2. **Enable LLM for development**: LLM detection works better with complex scripts
3. **Document output locations**: Add comments in runner scripts indicating where files are saved
4. **Use consistent patterns**: Stick to common output directories like `output/`, `generated/`, `workflows/`

## See Also

- [Runner Guide](RUNNER_GUIDE.md) - Complete guide for `--runner` flag
- [Generated Workflows Guide](GENERATED_WORKFLOWS_GUIDE.md) - Using `--generated-workflows`
- [Quick Reference](QUICK_REFERENCE.md) - Common command patterns

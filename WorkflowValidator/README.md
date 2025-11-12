# Pegasus Workflow Validator

Professional workflow validator for Pegasus - validates YAML workflows OR generates YAML from Python descriptors.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Validate YAML workflow
python cli.py workflow.yml

# Generate YAML from Python descriptor
python cli.py workflow_descriptor.py
```

## Features

✅ **Dual Input**: YAML (`.yml`) OR Python (`.py`) files
✅ **Python Validation**: Syntax, imports, security checks
✅ **YAML Generation**: Ollama-assisted (hybrid) or template-based (offline)
✅ **Generator Support**: Auto-detect generators with inline metadata
✅ **Comprehensive Checks**: Structure, paths, integrity, LLM analysis
✅ **Professional Output**: Clear errors with line numbers and fixes
✅ **Ollama Integration**: Uses same endpoint as Analyzer/Planner

## Usage Examples

### Validate YAML
```bash
python cli.py workflow.yml --level standard
python cli.py workflow.yml --level full --format json
```

### Generate from Python Descriptor
```bash
python cli.py workflow_descriptor.py --mode hybrid
python cli.py workflow_descriptor.py --mode offline --output-yaml my_workflow.yml
```

### Validate Generator Scripts

**Option 1: With Runner (Recommended)**
```bash
python cli.py workflow.py \
  --runner ml_training_runner.sh \
  --workflow-dir /path/to/workflow/
```

Use when runner script holds your parameters/configuration.
See [PARAMETER_RUNNER_EXAMPLE.md](PARAMETER_RUNNER_EXAMPLE.md) for ML training example!

**Option 2: Direct Generator**
```bash
python cli.py generate.py \
  --from-generator \
  --workflow-args 'production 4' \
  --workflow-dir /path/to/workflow/
```
Use when generator is directly executable.

### When Orchestrator Uses Generator (Declaration Method)
Declare which generator your orchestrator uses:

**orchestrator.py:**
```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: /opt/workflows/project
  generator_args: production
"""
# ... orchestrator code that calls generator ...
```

**Usage:**
```bash
# Validator auto-detects and validates the declared generator!
python cli.py orchestrator.py
```

See [ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md) for complete guide.

### Validate with Custom Workflow Directory
When your workflow descriptor is invoked by another file, specify the actual workflow directory:
```bash
# If run_workflow.py imports workflow_descriptor.py and the actual workflow files
# are in /path/to/workflow/, use:
python cli.py run_workflow.py --workflow-dir /path/to/workflow/
```

### Validate Workflow with Arguments
For workflows that accept command-line arguments (shell scripts, Python with argparse, etc.):
```bash
# Shell script orchestrator with arguments
python cli.py orchestrator.sh \
  --workflow-dir /path/to/workflow \
  --workflow-args 'production --config=/etc/workflow.conf --workers=4'

# Python workflow with environment specification
python cli.py workflow.py \
  --workflow-dir /home/user/workflows/ml_project \
  --workflow-args '--env=prod --data-dir=/mnt/data'
```

**Note:** The arguments are informational (logged for context) and help document the workflow's execution parameters during validation.

## Configuration

`validator_config.json` - Same JSON format as other MAPE-K components

## Documentation

See examples/ for sample workflows

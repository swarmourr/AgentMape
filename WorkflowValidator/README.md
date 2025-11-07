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
✅ **Comprehensive Checks**: Structure, paths, integrity, LLM analysis
✅ **Professional Output**: Clear errors with line numbers and fixes
✅ **Ollama Integration**: Uses same endpoint as Analyzer/Planner

## Usage Examples

### Validate YAML
```bash
python cli.py workflow.yml --level standard
python cli.py workflow.yml --level full --format json
```

### Generate from Python
```bash
python cli.py workflow_descriptor.py --mode hybrid
python cli.py workflow_descriptor.py --mode offline --output-yaml my_workflow.yml
```

## Configuration

`validator_config.json` - Same JSON format as other MAPE-K components

## Documentation

See examples/ for sample workflows

# Quick Start Guide

## Install
```bash
cd WorkflowValidator
pip install -r requirements.txt
```

## Test
```bash
# Test with YAML
python cli.py examples/example_workflow.yml

# Test with Python descriptor
python cli.py examples/workflow_descriptor.py
```

## Use

### Validate YAML
```bash
python cli.py your_workflow.yml
```

### Generate from Python
```bash
python cli.py your_descriptor.py
```

## Options
- `--level quick|standard|full` - Validation depth
- `--mode hybrid|offline` - Generation mode (.py files only)
- `--format terminal|json|html` - Report format

## Configuration
Edit `validator_config.json` to set Ollama endpoint and model.

Done! 🎉

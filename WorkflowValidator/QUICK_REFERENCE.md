# WorkflowValidator Quick Reference

## Basic Commands

```bash
# Validate YAML
python cli.py workflow.yml

# Validate Python descriptor
python cli.py workflow.py

# Generate YAML without LLM
python cli.py workflow.py --mode offline
```

## Validation Levels

| Level | What It Checks | LLM |
|-------|---------------|-----|
| `quick` | Syntax, required fields | ❌ |
| `standard` | + Dependencies, paths | ✅ |
| `full` | + Integrity, deep analysis | ✅ |

```bash
python cli.py workflow.yml --level full
```

## Output Formats

```bash
# Terminal (default)
python cli.py workflow.yml

# JSON
python cli.py workflow.yml --format json -o report.json

# HTML
python cli.py workflow.yml --format html -o report.html
```

## Advanced Options

### Custom Workflow Directory
Use when your workflow is invoked by an orchestrator:

```bash
python cli.py orchestrator.py --workflow-dir /actual/workflow/path/
```

**When to use:**
- `orchestrator.py` imports `workflow_descriptor.py`
- Shell script wraps Python workflow
- Workflow files are in different directory

### Workflow Arguments
Document the arguments your workflow accepts:

```bash
python cli.py orchestrator.sh \
  --workflow-args 'production --config=/etc/app.conf'
```

**When to use:**
- Shell scripts with parameters
- Python workflows with argparse
- Documenting execution context

## Common Scenarios

### Scenario 1: Simple Validation
```bash
python cli.py my_workflow.yml --level standard
```

### Scenario 2: Python Workflow
```bash
python cli.py workflow_descriptor.py \
  --mode hybrid \
  --output-yaml generated.yml
```

### Scenario 3: Orchestrated Workflow
```bash
python cli.py run_workflow.py \
  --workflow-dir /opt/workflows/ml_pipeline/ \
  --workflow-args '--env=prod --workers=4' \
  --level full \
  -o validation_report.json
```

### Scenario 4: Offline Validation (No Ollama)
```bash
python cli.py workflow.py \
  --mode offline \
  --level quick
```

## Understanding Errors

### Path Errors
```
❌ Transformation executable not found: scripts/train.py
   (resolved to: /wrong/path/scripts/train.py)
```

**Fix:** Use `--workflow-dir` to specify correct base directory

### Import Errors
```
❌ ModuleNotFoundError: No module named 'validators.llm_enhanced.llm_backends.openai_backend'
```

**Fix:** Update code from repository (already fixed in latest version)

### Ollama Errors
```
⚠️ Ollama backend not available at http://...
```

**Fix:** Use `--mode offline` or `--level quick` to skip LLM validation

## Configuration

Edit `validator_config.json`:

```json
{
  "ollama_api_base": "http://localhost:11434",
  "ollama_model": "llama3.3:latest",
  "log_level": "INFO",
  "log_file": "validator.log"
}
```

## Tips & Tricks

1. **Always use absolute paths** for production workflows
2. **Start with `--level quick`** to catch syntax errors fast
3. **Use `--verbose`** to see detailed error traces
4. **Save reports as JSON** for automated processing
5. **Test with `--mode offline`** when developing offline

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Validation PASSED |
| 1 | Validation FAILED |
| 2 | Validation error (exception) |

## Getting Help

```bash
python cli.py --help
```

## Report Issues

Check logs in `validator.log` and run with `--verbose`:

```bash
python cli.py workflow.yml --verbose 2>&1 | tee debug.log
```

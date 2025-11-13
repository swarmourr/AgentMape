# WorkflowValidator Structure

## Core Files (Essential)
```
WorkflowValidator/
├── cli.py                          # Main CLI entry point
├── validator.py                    # Main validator orchestrator
├── validator_config.json           # Configuration
├── models.py                       # Data models
├── report_generator.py             # Terminal/JSON reports
├── report_generator_html.py        # Interactive HTML reports
├── runner_analyzer.py              # Runner script analysis
├── yaml_generator.py               # YAML generation
├── requirements.txt                # Python dependencies
└── README.md                       # Documentation

## Validators
```
validators/
├── rule_based/                     # Fast rule-based validators
│   ├── structure_validator.py     # Workflow structure
│   ├── path_validator.py          # File paths
│   ├── integrity_validator.py     # Data integrity
│   ├── job_input_validator.py     # Job inputs
│   ├── resource_validator.py      # Resource limits
│   ├── dag_validator.py            # DAG dependencies
│   └── python_validator.py         # Python scripts
└── llm_enhanced/                   # LLM validators
    ├── llm_multi_prompt_validator.py  # Multi-prompt LLM validation
    ├── llm_validator.py            # Single LLM validation
    └── llm_backends/
        ├── ollama_backend.py       # Ollama integration
        └── base.py                 # Backend interface

## Examples
```
examples/                           # Test workflows
└── (workflow examples)
```

## Usage
```bash
# Basic validation
python3.11 cli.py workflow.yml

# Full validation with LLM (13 prompts)
python3.11 cli.py workflow.yml -l full -v

# Generate HTML report
python3.11 cli.py workflow.yml -l full -f html-interactive -o report.html
```

## What Was Removed
- ❌ All duplicate/redundant documentation files
- ❌ Test scripts (test_*.py, verify_*.py)
- ❌ Cache directories (__pycache__)
- ❌ Old config files (.validator.yaml)
- ❌ docs/ directory (outdated)

## Clean!
Only essential files remain for running the validator.

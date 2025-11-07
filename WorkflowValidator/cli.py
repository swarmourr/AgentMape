#!/usr/bin/env python3
"""
Command-line interface for Pegasus Workflow Validator
Supports both YAML validation and Python descriptor generation
"""
import click
import sys
from pathlib import Path

from validator import WorkflowValidator
from models import ValidationStatus


@click.command()
@click.argument('workflow', type=click.Path(exists=True))
@click.option('--tc', '--transformation-catalog',
              type=click.Path(exists=True),
              help='Path to transformation catalog')
@click.option('--rc', '--replica-catalog',
              type=click.Path(exists=True),
              help='Path to replica catalog')
@click.option('--level', '-l',
              type=click.Choice(['quick', 'standard', 'full']),
              default='standard',
              help='Validation level (quick=syntax only, standard=default, full=all checks)')
@click.option('--mode', '-m',
              type=click.Choice(['hybrid', 'offline']),
              default='hybrid',
              help='Generation mode for .py files (hybrid=Ollama+rules, offline=rules only)')
@click.option('--output-yaml',
              type=click.Path(),
              help='Output path for generated YAML (for .py inputs)')
@click.option('--format', '-f',
              type=click.Choice(['terminal', 'json', 'html']),
              default='terminal',
              help='Report output format')
@click.option('--output', '-o',
              type=click.Path(),
              help='Output file for report (default: stdout)')
@click.option('--config',
              type=click.Path(exists=True),
              help='Path to validator_config.json')
@click.option('--verbose', '-v',
              is_flag=True,
              help='Verbose output')
def validate(workflow, tc, rc, level, mode, output_yaml, format, output, config, verbose):
    """
    Validate a Pegasus workflow before submission.

    Supports two input types:
    - YAML files (.yml): Direct validation
    - Python descriptors (.py): Generate YAML then validate

    WORKFLOW: Path to workflow file (.yml or .py)

    Examples:

      # Validate existing YAML
      pegasus-validate workflow.yml

      # Generate YAML from Python descriptor (hybrid mode with Ollama)
      pegasus-validate workflow_descriptor.py

      # Generate YAML in offline mode (no LLM)
      pegasus-validate workflow_descriptor.py --mode offline

      # Generate + validate with custom output
      pegasus-validate workflow_descriptor.py --output-yaml my_workflow.yml

      # Full validation with LLM analysis
      pegasus-validate workflow.yml --level full

      # JSON output
      pegasus-validate workflow.yml --format json -o report.json
    """
    try:
        # Detect file type
        file_ext = Path(workflow).suffix.lower()
        is_python = file_ext == '.py'

        if is_python:
            click.echo(f"🐍 Python descriptor detected: {workflow}", err=True)
            click.echo(f"   Mode: {mode}", err=True)
        else:
            click.echo(f"📄 YAML workflow detected: {workflow}", err=True)

        click.echo(f"\n🔍 Validating workflow (level: {level})...\n", err=True)

        # Initialize validator
        validator = WorkflowValidator(config_path=config)

        # Run validation
        report, generated_yaml = validator.validate(
            workflow_path=workflow,
            transformation_catalog_path=tc,
            replica_catalog_path=rc,
            level=level,
            mode=mode,
            output_yaml_path=output_yaml
        )

        # Show generated YAML path
        if generated_yaml:
            click.echo(f"\n✅ YAML generated: {generated_yaml}\n", err=True)

        # Generate report
        report_text = validator.generate_report(report, format=format)

        # Output report
        if output:
            with open(output, 'w') as f:
                f.write(report_text)
            click.echo(f"📊 Report saved to: {output}", err=True)
        else:
            click.echo(report_text)

        # Summary
        if report.overall_status == ValidationStatus.PASSED:
            click.echo(f"\n✅ Validation PASSED - Workflow is ready to submit!", err=True)
            sys.exit(0)
        elif report.overall_status == ValidationStatus.FAILED:
            click.echo(f"\n❌ Validation FAILED - Fix {report.total_errors} error(s) before submission", err=True)
            sys.exit(1)
        else:  # WARNING
            click.echo(f"\n⚠️  Validation PASSED with {report.total_warnings} warning(s)", err=True)
            sys.exit(0)

    except Exception as e:
        click.echo(f"\n❌ Validation failed: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(2)


if __name__ == '__main__':
    validate()

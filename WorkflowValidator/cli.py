#!/usr/bin/env python3
"""
Command-line interface for Pegasus Workflow Validator
Supports both YAML validation and Python descriptor generation
"""
import click
import sys
import re
import yaml as yaml_lib
from pathlib import Path

from validator import WorkflowValidator
from models import ValidationStatus


def _detect_generator_metadata(file_path):
    """
    Detect generator metadata from file comments/docstrings

    Looks for VALIDATOR_CONFIG block in:
    - Python docstrings
    - Shell comments
    - Standalone .validator.yaml file

    Supports two types:
    - type: generator - File IS a generator
    - type: orchestrator - File USES a generator (must specify 'generator' field)

    Returns dict with metadata or None
    """
    try:
        file_path = Path(file_path)

        # Check for .validator.yaml in same directory
        validator_config = file_path.parent / '.validator.yaml'
        if validator_config.exists():
            with open(validator_config) as f:
                config = yaml_lib.safe_load(f)
                if config and 'workflow' in config:
                    wf_config = config['workflow']
                    # Resolve paths relative to .validator.yaml location
                    base_dir = validator_config.parent
                    workflow_dir = wf_config.get('directory', '.')
                    if not Path(workflow_dir).is_absolute():
                        workflow_dir = str(base_dir / workflow_dir)

                    return {
                        'type': 'generator',
                        'workflow_dir': workflow_dir,
                        'default_args': wf_config.get('default_args'),
                        'source': '.validator.yaml'
                    }

        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Look for VALIDATOR_CONFIG in Python docstring or comments
        config_pattern = r'VALIDATOR_CONFIG:\s*\n((?:  .+\n)+)'
        match = re.search(config_pattern, content)

        if match:
            config_block = match.group(1)
            # Parse as YAML
            config_yaml = yaml_lib.safe_load(config_block)

            if config_yaml:
                config_type = config_yaml.get('type')

                if config_type == 'generator':
                    return {
                        'type': 'generator',
                        'workflow_dir': config_yaml.get('workflow_dir'),
                        'default_args': config_yaml.get('default_args'),
                        'source': 'inline'
                    }

                elif config_type == 'orchestrator':
                    # Orchestrator declares which generator it uses
                    generator_file = config_yaml.get('generator')
                    if not generator_file:
                        return None

                    # Resolve generator path relative to orchestrator
                    if not Path(generator_file).is_absolute():
                        generator_file = str(file_path.parent / generator_file)

                    return {
                        'type': 'orchestrator',
                        'generator': generator_file,
                        'workflow_dir': config_yaml.get('workflow_dir'),
                        'default_args': config_yaml.get('generator_args'),
                        'source': 'inline'
                    }

    except Exception:
        pass  # No metadata found or error reading file

    return None


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
@click.option('--workflow-dir',
              type=click.Path(exists=True),
              help='Working directory for the workflow (where relative paths should be resolved from)')
@click.option('--workflow-args',
              type=str,
              help='Arguments to pass to workflow script (e.g., "--workflow-args \'arg1 arg2\'")')
@click.option('--from-generator',
              is_flag=True,
              help='Treat input as a generator script - run it and validate the output YAML')
@click.option('--runner',
              type=click.Path(exists=True),
              help='Script that executes the generator (e.g., orchestrator.sh that calls generator.py)')
@click.option('--verbose', '-v',
              is_flag=True,
              help='Verbose output')
def validate(workflow, tc, rc, level, mode, output_yaml, format, output, config, workflow_dir, workflow_args, from_generator, runner, verbose):
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

      # Workflow with arguments (e.g., shell script or Python with args)
      pegasus-validate orchestrator.sh --workflow-dir /path/to/workflow --workflow-args 'prod --config=/etc/workflow.conf'

      # Simple generator script (outputs YAML to stdout)
      pegasus-validate generate_workflow.py --from-generator --workflow-dir /path/to/workflow

      # Generator with arguments
      pegasus-validate generate.sh --from-generator --workflow-args 'prod 100' --workflow-dir /opt/workflow

      # Use runner script to execute generator
      pegasus-validate generator.py --runner orchestrator.sh --workflow-dir /opt/workflow
    """
    try:
        # Auto-detect generator from metadata in file
        generator_metadata = _detect_generator_metadata(workflow)

        # If generator metadata found and --from-generator not specified, enable it
        if generator_metadata and not from_generator:
            metadata_type = generator_metadata.get('type')

            if metadata_type == 'orchestrator':
                # Orchestrator declares which generator it uses
                click.echo(f"ℹ️  Auto-detected orchestrator configuration", err=True)
                declared_generator = generator_metadata.get('generator')

                if not declared_generator or not Path(declared_generator).exists():
                    click.echo(f"❌ Orchestrator declares generator '{declared_generator}' but file not found", err=True)
                    sys.exit(2)

                click.echo(f"   Orchestrator uses generator: {declared_generator}", err=True)

                # Validate the generator instead of orchestrator
                workflow = declared_generator
                from_generator = True

            else:
                # Type is 'generator'
                click.echo(f"ℹ️  Auto-detected generator configuration", err=True)
                from_generator = True

            # Apply metadata settings
            if not workflow_dir and generator_metadata.get('workflow_dir'):
                workflow_dir = generator_metadata['workflow_dir']
                click.echo(f"   Using workflow_dir from metadata: {workflow_dir}", err=True)

            if not workflow_args and generator_metadata.get('default_args'):
                workflow_args = generator_metadata['default_args']
                click.echo(f"   Using generator_args from metadata: {workflow_args}", err=True)

        # Handle runner (script that executes the generator)
        if runner:
            import subprocess
            import tempfile

            click.echo(f"🏃 Runner script detected: {runner}", err=True)
            click.echo(f"   Generator: {workflow}", err=True)

            # Build command to run the runner
            cmd = []
            runner_ext = Path(runner).suffix.lower()

            if runner_ext == '.py':
                cmd = ['python3', runner]
            elif runner_ext == '.sh':
                cmd = ['bash', runner]
            else:
                cmd = [runner]

            # Add workflow arguments if provided
            if workflow_args:
                cmd.extend(workflow_args.split())

            click.echo(f"   Running: {' '.join(cmd)}", err=True)

            # Run runner and capture output
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=workflow_dir if workflow_dir else Path(runner).parent,
                    timeout=120
                )

                if result.returncode != 0:
                    click.echo(f"❌ Runner failed with exit code {result.returncode}", err=True)
                    if result.stderr:
                        click.echo(f"Error output:\n{result.stderr}", err=True)
                    sys.exit(2)

                generated_yaml_content = result.stdout

                # Check if multiple YAML documents (separated by ---)
                yaml_docs = generated_yaml_content.split('\n---\n')
                num_docs = len([doc for doc in yaml_docs if doc.strip()])

                if num_docs > 1:
                    click.echo(f"✅ Runner produced {num_docs} YAML documents ({len(generated_yaml_content)} bytes)", err=True)
                    click.echo(f"   Validating all {num_docs} workflows...", err=True)

                    # Save each document and validate separately
                    all_reports = []
                    for i, yaml_doc in enumerate(yaml_docs):
                        if not yaml_doc.strip():
                            continue

                        click.echo(f"\n📄 Validating workflow {i+1}/{num_docs}...", err=True)

                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(mode='w', suffix=f'_{i}.yml', delete=False) as f:
                            f.write(yaml_doc)
                            temp_path = f.name

                        # Validate this document (will be handled below)
                        workflow = temp_path
                        # Note: For now, validate only first document
                        # TODO: Support validating all documents and combining reports
                        if i == 0:
                            break

                    from_generator = False  # Already handled

                else:
                    # Single YAML document
                    click.echo(f"✅ Runner produced {len(generated_yaml_content)} bytes of YAML", err=True)

                    # Save to temporary file for validation
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
                        f.write(generated_yaml_content)
                        temp_yaml_path = f.name

                    # Update workflow path to generated YAML
                    workflow = temp_yaml_path
                    from_generator = False  # Already handled

            except subprocess.TimeoutExpired:
                click.echo(f"❌ Runner timed out after 120 seconds", err=True)
                sys.exit(2)
            except Exception as e:
                click.echo(f"❌ Failed to run runner: {e}", err=True)
                sys.exit(2)

        # Handle generator scripts (direct)
        elif from_generator:
            import subprocess
            import tempfile

            click.echo(f"⚙️  Generator script detected: {workflow}", err=True)

            # Build command to run generator
            cmd = []
            file_ext = Path(workflow).suffix.lower()

            if file_ext == '.py':
                cmd = ['python3', workflow]
            elif file_ext == '.sh':
                cmd = ['bash', workflow]
            else:
                cmd = [workflow]

            # Add workflow arguments if provided
            if workflow_args:
                cmd.extend(workflow_args.split())

            click.echo(f"   Running: {' '.join(cmd)}", err=True)

            # Run generator and capture output
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=workflow_dir if workflow_dir else Path(workflow).parent,
                    timeout=120
                )

                if result.returncode != 0:
                    click.echo(f"❌ Generator failed with exit code {result.returncode}", err=True)
                    if result.stderr:
                        click.echo(f"Error output:\n{result.stderr}", err=True)
                    sys.exit(2)

                generated_yaml_content = result.stdout

                # Save to temporary file for validation
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
                    f.write(generated_yaml_content)
                    temp_yaml_path = f.name

                click.echo(f"✅ Generator produced {len(generated_yaml_content)} bytes of YAML", err=True)

                # Update workflow path to generated YAML
                workflow = temp_yaml_path

            except subprocess.TimeoutExpired:
                click.echo(f"❌ Generator timed out after 120 seconds", err=True)
                sys.exit(2)
            except Exception as e:
                click.echo(f"❌ Failed to run generator: {e}", err=True)
                sys.exit(2)

        # Detect file type
        file_ext = Path(workflow).suffix.lower()
        is_python = file_ext == '.py'

        if is_python and not from_generator:
            click.echo(f"🐍 Python descriptor detected: {workflow}", err=True)
            click.echo(f"   Mode: {mode}", err=True)
        elif not from_generator:
            click.echo(f"📄 YAML workflow detected: {workflow}", err=True)

        click.echo(f"\n🔍 Validating workflow (level: {level})...\n", err=True)

        # Initialize validator
        validator = WorkflowValidator(config_path=config)

        # Parse workflow arguments if provided
        parsed_args = workflow_args.split() if workflow_args else None

        # Run validation
        report, generated_yaml = validator.validate(
            workflow_path=workflow,
            transformation_catalog_path=tc,
            replica_catalog_path=rc,
            level=level,
            mode=mode,
            output_yaml_path=output_yaml,
            workflow_dir=workflow_dir,
            workflow_args=parsed_args
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

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
from runner_analyzer import analyze_runner_script, find_generated_workflows


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
@click.option('--generated-workflows',
              type=str,
              help='Path to generated YAML file(s) or directory. Use glob patterns like "output/*.yml" or single file "output/workflow.yml"')
@click.option('--verbose', '-v',
              is_flag=True,
              help='Verbose output')
def validate(workflow, tc, rc, level, mode, output_yaml, format, output, config, workflow_dir, workflow_args, from_generator, runner, generated_workflows, verbose):
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

        # Handle runner with generated workflows path
        if runner and generated_workflows:
            import subprocess
            import glob as glob_module

            click.echo(f"🏃 Runner script detected: {runner}", err=True)
            click.echo(f"   Generator: {workflow}", err=True)
            click.echo(f"   Generated workflows: {generated_workflows}", err=True)

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

            # Run runner (doesn't need to capture stdout)
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

                # Show runner output
                if result.stdout:
                    click.echo(f"✅ Runner completed successfully", err=True)
                if result.stderr:
                    click.echo(result.stderr, err=True)

                # Find generated YAML files
                click.echo(f"\n🔍 Looking for generated workflows...", err=True)

                # Support glob patterns and directories
                yaml_files = []

                # Check if it's a directory
                if Path(generated_workflows).is_dir():
                    yaml_files = list(Path(generated_workflows).glob('*.yml')) + list(Path(generated_workflows).glob('*.yaml'))
                # Check if it's a glob pattern
                elif '*' in generated_workflows or '?' in generated_workflows:
                    yaml_files = [Path(f) for f in glob_module.glob(generated_workflows)]
                # Single file
                elif Path(generated_workflows).exists():
                    yaml_files = [Path(generated_workflows)]
                else:
                    click.echo(f"❌ No workflows found at: {generated_workflows}", err=True)
                    sys.exit(2)

                if not yaml_files:
                    click.echo(f"❌ No YAML files found in: {generated_workflows}", err=True)
                    sys.exit(2)

                click.echo(f"   Found {len(yaml_files)} workflow(s) to validate", err=True)

                # Validate each found workflow
                for i, yaml_file in enumerate(yaml_files):
                    click.echo(f"\n📄 Validating {yaml_file.name} ({i+1}/{len(yaml_files)})...", err=True)

                    # For now, validate first one (TODO: validate all)
                    workflow = str(yaml_file)
                    if i == 0:
                        break

            except subprocess.TimeoutExpired:
                click.echo(f"❌ Runner timed out after 120 seconds", err=True)
                sys.exit(2)
            except Exception as e:
                click.echo(f"❌ Failed to run runner: {e}", err=True)
                if verbose:
                    import traceback
                    traceback.print_exc()
                sys.exit(2)

        # Handle runner with LLM auto-detection of output path
        elif runner:
            import subprocess

            click.echo(f"🏃 Runner script detected: {runner}", err=True)
            click.echo(f"   Generator: {workflow}", err=True)

            # Try to auto-detect where runner saves workflows
            click.echo(f"\n🔍 Analyzing runner to detect workflow output location...", err=True)

            # Initialize LLM backend for analysis (if available)
            llm_backend = None
            llm_available = False
            try:
                from validators.llm_enhanced.llm_backends import OllamaBackend
                validator_config_path = Path(__file__).parent / 'validator_config.json'
                if validator_config_path.exists():
                    import json
                    with open(validator_config_path) as f:
                        validator_config = json.load(f)
                        llm_config = validator_config.get('llm_backend', {})
                        if llm_config.get('enabled', False):
                            llm_backend = OllamaBackend(llm_config)
                            if llm_backend.is_available():
                                llm_available = True
                                click.echo(f"   ✓ LLM backend available for intelligent analysis", err=True)
                            else:
                                if verbose:
                                    click.echo(f"   ⚠️  LLM backend configured but not available", err=True)
                        else:
                            if verbose:
                                click.echo(f"   ⚠️  LLM backend disabled in config", err=True)
                else:
                    if verbose:
                        click.echo(f"   ⚠️  Config file not found: {validator_config_path}", err=True)
            except Exception as e:
                if verbose:
                    click.echo(f"   ⚠️  LLM backend initialization failed: {e}", err=True)
                    import traceback
                    traceback.print_exc()

            # Show analysis method
            if llm_available:
                click.echo(f"   Using: Rule-based + LLM analysis", err=True)
            else:
                click.echo(f"   Using: Rule-based analysis only", err=True)
                click.echo(f"   💡 Tip: Enable LLM in validator_config.json for smarter detection", err=True)

            # Analyze runner script
            detected_pattern = analyze_runner_script(runner, llm_backend)

            if detected_pattern:
                click.echo(f"   ✅ Auto-detected output: {detected_pattern}", err=True)
                generated_workflows = detected_pattern
            else:
                click.echo(f"   ⚠️  Could not auto-detect output location", err=True)

                # Ask user for the output location
                click.echo(f"\n❓ Where does the runner save workflow YAML files?", err=True)
                click.echo(f"   Examples:", err=True)
                click.echo(f"   - output/workflow.yml  (single file)", err=True)
                click.echo(f"   - output/             (directory)", err=True)
                click.echo(f"   - output/*.yml        (glob pattern)", err=True)
                click.echo(f"   - [press Enter to capture stdout instead]", err=True)

                user_input = input("\n   Output location: ").strip()

                if user_input:
                    click.echo(f"   ✓ Using user-specified location: {user_input}", err=True)
                    generated_workflows = user_input
                else:
                    click.echo(f"   Falling back to stdout capture...", err=True)

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

            # If we detected a file-based output pattern, run without capturing stdout
            if generated_workflows:
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

                    # Show runner output
                    if result.stdout:
                        click.echo(f"✅ Runner completed successfully", err=True)
                    if result.stderr:
                        click.echo(result.stderr, err=True)

                    # Find generated YAML files
                    click.echo(f"\n🔍 Looking for generated workflows at: {generated_workflows}", err=True)

                    base_dir = workflow_dir if workflow_dir else str(Path(runner).parent)
                    yaml_files = find_generated_workflows(base_dir, generated_workflows)

                    if not yaml_files:
                        click.echo(f"❌ No YAML files found", err=True)
                        click.echo(f"   Searched: {base_dir}/{generated_workflows}", err=True)
                        sys.exit(2)

                    click.echo(f"   Found {len(yaml_files)} workflow(s) to validate", err=True)

                    # Validate each found workflow
                    for i, yaml_file in enumerate(yaml_files):
                        click.echo(f"\n📄 Validating {yaml_file.name} ({i+1}/{len(yaml_files)})...", err=True)

                        # For now, validate first one (TODO: validate all)
                        workflow = str(yaml_file)
                        if i == 0:
                            break

                except subprocess.TimeoutExpired:
                    click.echo(f"❌ Runner timed out after 120 seconds", err=True)
                    sys.exit(2)
                except Exception as e:
                    click.echo(f"❌ Failed to run runner: {e}", err=True)
                    if verbose:
                        import traceback
                        traceback.print_exc()
                    sys.exit(2)

            # Fallback: capture stdout if no file-based output detected
            else:
                import tempfile

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

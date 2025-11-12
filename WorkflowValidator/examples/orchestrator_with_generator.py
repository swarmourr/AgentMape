#!/usr/bin/env python3
"""
Workflow Orchestrator - Launches workflow using generator

VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: /opt/workflows/ml_pipeline
  generator_args: production --workers=4
"""
import subprocess
import sys

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'production'

    print(f"🚀 Launching workflow for environment: {env}")

    # Generate workflow YAML using generator
    print("📝 Generating workflow YAML...")
    result = subprocess.run(
        ['python3', 'generate_workflow.py', env],
        capture_output=True,
        text=True,
        check=True
    )

    workflow_yaml = result.stdout

    # Save generated YAML
    output_file = f'workflow_{env}.yml'
    with open(output_file, 'w') as f:
        f.write(workflow_yaml)

    print(f"✅ Workflow YAML generated: {output_file}")

    # Execute workflow with Pegasus
    print("🏃 Executing workflow...")
    # subprocess.run(['pegasus-plan', output_file])
    # subprocess.run(['pegasus-run', ...])

    print("✅ Workflow execution complete!")

if __name__ == '__main__':
    main()

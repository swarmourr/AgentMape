#!/usr/bin/env python3
"""
Pegasus Workflow Generator

VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /opt/workflows/ml_pipeline
  default_args: production --workers=4
"""
import sys
import yaml

def generate_workflow(env='dev', workers=1):
    """Generate a dynamic ML workflow"""

    workflow = {
        'name': f'ml_pipeline_{env}',
        'version': '1.0',
        'jobs': []
    }

    # Generate jobs dynamically
    for i in range(int(workers)):
        workflow['jobs'].append({
            'name': f'train_worker_{i}',
            'transformation': 'Train',
            'arguments': [
                '--worker-id', str(i),
                '--env', env
            ]
        })

    workflow['transformations'] = [
        {
            'name': 'Train',
            'pfn': 'scripts/train.py',
            'type': 'stageable'
        }
    ]

    return workflow

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    workers = sys.argv[2] if len(sys.argv) > 2 else '1'

    workflow = generate_workflow(env, workers)
    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()

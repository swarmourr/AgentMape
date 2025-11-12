#!/usr/bin/env python3
"""
Example generator where output path is split between scripts
- OUTPUT_DIR is set by environment/runner
- OUTPUT_FILE is in generator
- LLM must combine both to get: workflows/pipeline.yml
"""
import yaml
import os
from pathlib import Path

# Output directory comes from environment (set by runner)
OUTPUT_DIR = os.getenv('WORKFLOW_OUTPUT_DIR', 'workflows')

# Output filename defined here
OUTPUT_FILE = "pipeline.yml"

def generate_workflow():
    """Generate a simple workflow"""
    workflow = {
        'pegasus': '5.0',
        'name': 'combined_test_pipeline',
        'jobs': [
            {
                'name': 'data_processing',
                'transformation': 'process',
                'arguments': ['--input', 'data.txt'],
                'uses': [
                    {'name': 'data.txt', 'type': 'input'}
                ]
            }
        ],
        'transformations': [
            {
                'name': 'process',
                'pfn': '/usr/bin/process.sh',
                'type': 'stageable'
            }
        ]
    }

    # Combine directory and filename
    output_path = Path(OUTPUT_DIR) / OUTPUT_FILE
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save workflow
    with open(output_path, 'w') as f:
        yaml.dump(workflow, f, default_flow_style=False)

    print(f"Workflow saved to {output_path}")

if __name__ == '__main__':
    generate_workflow()

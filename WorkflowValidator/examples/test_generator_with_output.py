#!/usr/bin/env python3
"""
Example generator that saves workflow to a file
Used to test auto-detection
"""
import yaml
from pathlib import Path

# Output configuration
OUTPUT_FILE = "generated_workflows/pipeline.yml"

def generate_workflow():
    """Generate a simple workflow"""
    workflow = {
        'pegasus': '5.0',
        'name': 'test_pipeline',
        'jobs': [
            {
                'name': 'process_data',
                'transformation': 'process_script',
                'arguments': ['--input', 'data.txt', '--output', 'result.txt'],
                'uses': [
                    {'name': 'data.txt', 'type': 'input'},
                    {'name': 'result.txt', 'type': 'output'}
                ]
            }
        ],
        'transformations': [
            {
                'name': 'process_script',
                'pfn': '/usr/bin/process.sh',
                'type': 'stageable'
            }
        ]
    }

    # Create output directory
    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save workflow to file
    with open(OUTPUT_FILE, 'w') as f:
        yaml.dump(workflow, f, default_flow_style=False)

    print(f"Workflow saved to {OUTPUT_FILE}")

if __name__ == '__main__':
    generate_workflow()

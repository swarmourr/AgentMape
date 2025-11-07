"""
Example Pegasus Workflow Descriptor (Python)

This Python file describes a machine learning workflow.
The WorkflowValidator will:
1. Validate this Python code
2. Generate Pegasus YAML
3. Validate the generated YAML
"""

# Workflow definition
workflow = {
    'name': 'ml_training_pipeline',
    'version': '1.0'
}

# Jobs definition
jobs = [
    {
        'name': 'download_data',
        'transformation': 'Download',
        'arguments': [
            '--url', 'https://example.com/dataset.csv',
            '--output', 'raw_data.csv'
        ],
        'uses': [
            {'name': 'raw_data.csv', 'type': 'output'}
        ]
    },
    {
        'name': 'preprocess_data',
        'transformation': 'Preprocess',
        'parents': ['download_data'],
        'arguments': [
            '--input', 'raw_data.csv',
            '--output', 'clean_data.csv'
        ],
        'uses': [
            {'name': 'raw_data.csv', 'type': 'input'},
            {'name': 'clean_data.csv', 'type': 'output'}
        ]
    },
    {
        'name': 'split_data',
        'transformation': 'SplitData',
        'parents': ['preprocess_data'],
        'arguments': [
            '--input', 'clean_data.csv',
            '--train-output', 'train.csv',
            '--test-output', 'test.csv',
            '--ratio', '0.8'
        ],
        'uses': [
            {'name': 'clean_data.csv', 'type': 'input'},
            {'name': 'train.csv', 'type': 'output'},
            {'name': 'test.csv', 'type': 'output'}
        ]
    },
    {
        'name': 'train_model',
        'transformation': 'TrainModel',
        'parents': ['split_data'],
        'arguments': [
            '--train-data', 'train.csv',
            '--model-output', 'model.pkl',
            '--epochs', '100'
        ],
        'uses': [
            {'name': 'train.csv', 'type': 'input'},
            {'name': 'model.pkl', 'type': 'output'}
        ]
    },
    {
        'name': 'evaluate_model',
        'transformation': 'Evaluate',
        'parents': ['train_model'],
        'arguments': [
            '--model', 'model.pkl',
            '--test-data', 'test.csv',
            '--metrics-output', 'metrics.json'
        ],
        'uses': [
            {'name': 'model.pkl', 'type': 'input'},
            {'name': 'test.csv', 'type': 'input'},
            {'name': 'metrics.json', 'type': 'output'}
        ]
    }
]

# Transformation catalog
transformations = [
    {
        'name': 'Download',
        'pfn': '/usr/bin/wget',
        'type': 'stageable'
    },
    {
        'name': 'Preprocess',
        'pfn': '/home/user/scripts/preprocess.py',
        'type': 'stageable'
    },
    {
        'name': 'SplitData',
        'pfn': '/home/user/scripts/split.py',
        'type': 'stageable'
    },
    {
        'name': 'TrainModel',
        'pfn': '/home/user/scripts/train.py',
        'type': 'stageable'
    },
    {
        'name': 'Evaluate',
        'pfn': '/home/user/scripts/evaluate.py',
        'type': 'stageable'
    }
]

# Replica catalog (input files)
replicas = []

if __name__ == '__main__':
    print(f"Workflow: {workflow['name']}")
    print(f"Jobs: {len(jobs)}")
    print(f"Transformations: {len(transformations)}")

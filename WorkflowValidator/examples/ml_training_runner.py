#!/usr/bin/env python3
"""
ML Training Workflow Runner (Python version)
Executes workflow.py with predefined configuration
"""
import subprocess
import sys

def main():
    # Configuration
    config = {
        'models': [
            'meta-llama/Meta-Llama-3-8B-Instruct',
            'meta-llama/Meta-Llama-3-70B-Instruct',
            'meta-llama/Llama-2-7b-chat-hf',
            'tiiuae/falcon-7b',
            'mistralai/Mistral-7B-Instruct-v0.3'
        ],
        'num_train_epochs': 3,
        'batch_size': 4,
        'save_steps': 5000,
        'learning_rate': 3e-5,
        'use_auth_token': True,
        'auth_token': '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',
        'gpu': 1
    }

    # Build command
    cmd = ['python', 'workflow.py']

    # Add models
    cmd.append('--models')
    cmd.extend(config['models'])

    # Add other parameters
    cmd.extend([
        '--num_train_epochs', str(config['num_train_epochs']),
        '--batch_size', str(config['batch_size']),
        '--save_steps', str(config['save_steps']),
        '--learning_rate', str(config['learning_rate'])
    ])

    if config['use_auth_token']:
        cmd.extend(['--use_auth_token', '--auth_token', config['auth_token']])

    cmd.extend(['--gpu', str(config['gpu'])])

    # Execute
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Output YAML to stdout
    print(result.stdout)

    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

if __name__ == '__main__':
    main()

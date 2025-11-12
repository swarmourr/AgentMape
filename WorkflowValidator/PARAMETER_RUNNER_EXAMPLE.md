# Parameter Configuration Runner Example

## Your Exact Use Case!

You have **workflow.py** that needs complex parameters. Instead of typing them every time, you create a **runner script** that holds all the configuration.

---

## The Problem

Your workflow has many parameters:

```bash
python workflow.py \
  --models meta-llama/Meta-Llama-3-8B-Instruct meta-llama/Meta-Llama-3-70B-Instruct meta-llama/Llama-2-7b-chat-hf tiiuae/falcon-7b mistralai/Mistral-7B-Instruct-v0.3 \
  --num_train_epochs 3 \
  --batch_size 4 \
  --save_steps 5000 \
  --learning_rate 3e-5 \
  --use_auth_token \
  --auth_token YOUR_AUTH_TOKEN \
  --gpu 1
```

**Too long! Hard to maintain!**

---

## The Solution: Runner Script

### Option 1: Shell Script Runner

**ml_training_runner.sh:**
```bash
#!/bin/bash
# ML Training Workflow Runner
# Keeps all parameters organized

# Define the command with parameters
COMMAND="python workflow.py"
MODELS="--models meta-llama/Meta-Llama-3-8B-Instruct meta-llama/Meta-Llama-3-70B-Instruct meta-llama/Llama-2-7b-chat-hf tiiuae/falcon-7b mistralai/Mistral-7B-Instruct-v0.3"
NUM_TRAIN_EPOCHS="--num_train_epochs 3"
BATCH_SIZE="--batch_size 4"
SAVE_STEPS="--save_steps 5000"
LEARNING_RATE="--learning_rate 3e-5"
USE_AUTH_TOKEN="--use_auth_token"
AUTH_TOKEN="--auth_token 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"
GPU="--gpu 1"

# Execute the command
$COMMAND $MODELS $NUM_TRAIN_EPOCHS $BATCH_SIZE $SAVE_STEPS $LEARNING_RATE $USE_AUTH_TOKEN $AUTH_TOKEN $GPU
```

**Now just run:**
```bash
bash ml_training_runner.sh
```

**Clean and simple!**

---

### Option 2: Python Runner

**ml_training_runner.py:**
```python
#!/usr/bin/env python3
"""
ML Training Workflow Runner
Configuration for model training
"""
import subprocess
import sys

def main():
    # All your parameters in one place
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

    # Add training parameters
    cmd.extend([
        '--num_train_epochs', str(config['num_train_epochs']),
        '--batch_size', str(config['batch_size']),
        '--save_steps', str(config['save_steps']),
        '--learning_rate', str(config['learning_rate'])
    ])

    # Add authentication
    if config['use_auth_token']:
        cmd.extend(['--use_auth_token', '--auth_token', config['auth_token']])

    # Add GPU
    cmd.extend(['--gpu', str(config['gpu'])])

    # Execute workflow
    print(f"🚀 Running workflow with config...", file=sys.stderr)
    print(f"   Models: {len(config['models'])}", file=sys.stderr)
    print(f"   Epochs: {config['num_train_epochs']}", file=sys.stderr)
    print(f"   Batch size: {config['batch_size']}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Output YAML to stdout
    print(result.stdout)

    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

if __name__ == '__main__':
    main()
```

**Now just run:**
```bash
python ml_training_runner.py
```

---

## Validate with Validator

### Shell Runner
```bash
python validator/cli.py workflow.py \
  --runner ml_training_runner.sh \
  --workflow-dir /opt/ml_workflows/
```

### Python Runner
```bash
python validator/cli.py workflow.py \
  --runner ml_training_runner.py \
  --workflow-dir /opt/ml_workflows/
```

---

## What Happens

```
🏃 Runner script detected: ml_training_runner.sh
   Generator: workflow.py
   Running: bash ml_training_runner.sh

✅ Runner produced 1,234 bytes of YAML

🔍 Validating workflow (level: standard)...

Running structure validator...
✓ Workflow structure valid
✓ 5 models configured
✓ Training parameters valid

Running path validator...
✓ All model paths validated
✓ Training scripts found

✅ Validation PASSED - Workflow is ready to train!
```

---

## Multiple Configurations

Create different runners for different environments:

**dev_runner.sh:**
```bash
#!/bin/bash
COMMAND="python workflow.py"
MODELS="--models meta-llama/Llama-2-7b-chat-hf"  # Just one model for dev
NUM_TRAIN_EPOCHS="--num_train_epochs 1"  # Quick test
BATCH_SIZE="--batch_size 2"
GPU="--gpu 0"

$COMMAND $MODELS $NUM_TRAIN_EPOCHS $BATCH_SIZE $GPU
```

**prod_runner.sh:**
```bash
#!/bin/bash
COMMAND="python workflow.py"
MODELS="--models meta-llama/Meta-Llama-3-8B-Instruct meta-llama/Meta-Llama-3-70B-Instruct meta-llama/Llama-2-7b-chat-hf tiiuae/falcon-7b mistralai/Mistral-7B-Instruct-v0.3"
NUM_TRAIN_EPOCHS="--num_train_epochs 10"  # Full training
BATCH_SIZE="--batch_size 8"
GPU="--gpu 1"

$COMMAND $MODELS $NUM_TRAIN_EPOCHS $BATCH_SIZE $LEARNING_RATE $USE_AUTH_TOKEN $AUTH_TOKEN $GPU
```

**Validate dev:**
```bash
python cli.py workflow.py --runner dev_runner.sh --workflow-dir /opt/ml/
```

**Validate prod:**
```bash
python cli.py workflow.py --runner prod_runner.sh --workflow-dir /opt/ml/
```

---

## With Dynamic Parameters

Runner can also accept arguments:

**flexible_runner.sh:**
```bash
#!/bin/bash
ENV=${1:-dev}

case $ENV in
    dev)
        EPOCHS=1
        BATCH=2
        MODELS="--models meta-llama/Llama-2-7b-chat-hf"
        ;;
    staging)
        EPOCHS=3
        BATCH=4
        MODELS="--models meta-llama/Meta-Llama-3-8B-Instruct meta-llama/Llama-2-7b-chat-hf"
        ;;
    production)
        EPOCHS=10
        BATCH=8
        MODELS="--models meta-llama/Meta-Llama-3-8B-Instruct meta-llama/Meta-Llama-3-70B-Instruct meta-llama/Llama-2-7b-chat-hf tiiuae/falcon-7b mistralai/Mistral-7B-Instruct-v0.3"
        ;;
esac

python workflow.py $MODELS --num_train_epochs $EPOCHS --batch_size $BATCH --gpu 1
```

**Validate with environment:**
```bash
# Dev environment
python cli.py workflow.py \
  --runner flexible_runner.sh \
  --workflow-args 'dev' \
  --workflow-dir /opt/ml/

# Production environment
python cli.py workflow.py \
  --runner flexible_runner.sh \
  --workflow-args 'production' \
  --workflow-dir /opt/ml/
```

---

## Complete Project Structure

```
/opt/ml_workflows/
├── workflow.py                  # Your workflow generator
├── ml_training_runner.sh        # Shell runner with config
├── ml_training_runner.py        # Python runner with config
├── dev_runner.sh               # Dev configuration
├── prod_runner.sh              # Production configuration
├── scripts/
│   ├── train.py
│   ├── evaluate.py
│   └── deploy.py
└── models/
    └── checkpoints/
```

---

## Benefits

✅ **Organized**: All parameters in one file
✅ **Reusable**: Run the same config anytime
✅ **Version Control**: Track parameter changes in Git
✅ **Environment-Specific**: Different configs for dev/staging/prod
✅ **Easy to Modify**: Change one file, not command line
✅ **Validation**: Validator knows how to run your workflow

---

## Real Workflow Example

**workflow.py** (generates Pegasus YAML):
```python
#!/usr/bin/env python3
import yaml
import sys
import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--num_train_epochs', type=int, required=True)
    parser.add_argument('--batch_size', type=int, required=True)
    parser.add_argument('--save_steps', type=int, required=True)
    parser.add_argument('--learning_rate', type=float, required=True)
    parser.add_argument('--gpu', type=int, required=True)
    parser.add_argument('--use_auth_token', action='store_true')
    parser.add_argument('--auth_token', type=str)
    return parser.parse_args()

def generate_workflow(args):
    workflow = {
        'name': 'ml_training_pipeline',
        'version': '1.0',
        'jobs': []
    }

    # Create training job for each model
    for i, model in enumerate(args.models):
        workflow['jobs'].append({
            'name': f'train_{model.split("/")[-1]}',
            'transformation': 'TrainModel',
            'arguments': [
                '--model', model,
                '--epochs', str(args.num_train_epochs),
                '--batch-size', str(args.batch_size),
                '--learning-rate', str(args.learning_rate),
                '--gpu', str(args.gpu)
            ]
        })

    workflow['transformations'] = [
        {'name': 'TrainModel', 'pfn': 'scripts/train.py', 'type': 'stageable'}
    ]

    return workflow

def main():
    args = parse_args()
    workflow = generate_workflow(args)
    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()
```

**Now validate:**
```bash
python validator/cli.py workflow.py \
  --runner ml_training_runner.sh \
  --workflow-dir /opt/ml_workflows/
```

**Output:**
```
🏃 Runner script detected: ml_training_runner.sh
   Generator: workflow.py
   Running: bash ml_training_runner.sh

✅ Runner produced 1,456 bytes of YAML

🔍 Validating workflow...

Running structure validator...
✓ Workflow: ml_training_pipeline
✓ 5 training jobs created
✓ All transformations defined

Running path validator...
✓ scripts/train.py ✅ (exists, executable)

✅ Validation PASSED - Ready to train 5 models!
```

---

## Summary

**Your pattern:**
```bash
# Complex command → Hard to maintain
python workflow.py --models ... --num_train_epochs ... --batch_size ...

# Runner script → Easy to maintain
bash ml_training_runner.sh

# Validate with runner
python cli.py workflow.py --runner ml_training_runner.sh --workflow-dir /path/
```

**Perfect for:**
- 🎯 ML training workflows with many parameters
- 🎯 Configuration management
- 🎯 Environment-specific setups
- 🎯 Team collaboration (everyone uses same config)

🚀

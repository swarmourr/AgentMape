#!/bin/bash
# ML Training Workflow Runner
# Executes workflow.py with predefined configuration

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

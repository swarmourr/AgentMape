#!/bin/bash
# Simple runner that executes a generator
# This runner doesn't specify output location, so validator must check the generator

echo "Running workflow generator..."
python3 examples/test_generator_with_output.py
echo "Generator completed"

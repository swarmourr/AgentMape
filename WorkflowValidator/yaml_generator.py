"""
YAML Generator - Converts Python workflow descriptors to Pegasus YAML
Supports hybrid (Ollama-assisted) and offline (template-based) modes
"""
import yaml
import json
import logging
import ast
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class YAMLGenerator:
    """Generates Pegasus workflow YAML from Python descriptors"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mode = 'hybrid'  # 'hybrid' or 'offline'
        self.llm_backend = None

    def set_mode(self, mode: str):
        """Set generation mode: 'hybrid' or 'offline'"""
        if mode not in ['hybrid', 'offline']:
            logger.warning(f"Unknown mode '{mode}', using 'hybrid'")
            mode = 'hybrid'
        self.mode = mode
        logger.info(f"Generator mode set to: {mode}")

    def set_llm_backend(self, backend):
        """Set LLM backend for hybrid mode"""
        self.llm_backend = backend

    def generate(self, python_file_path: str, workflow_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate workflow YAML from Python descriptor

        Args:
            python_file_path: Path to Python descriptor file
            workflow_metadata: Metadata extracted from Python file

        Returns:
            Workflow dictionary (ready to dump as YAML)
        """
        logger.info(f"Generating YAML in {self.mode} mode from: {python_file_path}")

        if self.mode == 'hybrid' and self.llm_backend:
            return self._generate_hybrid(python_file_path, workflow_metadata)
        else:
            return self._generate_offline(python_file_path, workflow_metadata)

    def _generate_hybrid(self, python_file_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate YAML using Ollama for intelligent conversion

        Ollama understands Python code structure and generates proper Pegasus YAML
        """
        logger.info("Using Ollama-assisted generation (hybrid mode)")

        try:
            # Read Python source
            with open(python_file_path, 'r') as f:
                python_code = f.read()

            # Create prompt for Ollama
            prompt = self._build_generation_prompt(python_code, metadata)

            # Get Ollama response
            logger.info("Sending generation request to Ollama...")
            response = self.llm_backend.generate_json(prompt)
            logger.info("Received workflow structure from Ollama")

            # Extract workflow from response
            workflow = response.get('workflow', {})

            # Validate basic structure
            if not workflow.get('name'):
                workflow['name'] = Path(python_file_path).stem

            if not workflow.get('jobs'):
                logger.warning("Ollama generated workflow with no jobs, falling back to offline mode")
                return self._generate_offline(python_file_path, metadata)

            return workflow

        except Exception as e:
            logger.error(f"Hybrid generation failed: {e}, falling back to offline mode")
            return self._generate_offline(python_file_path, metadata)

    def _build_generation_prompt(self, python_code: str, metadata: Dict[str, Any]) -> str:
        """Build prompt for Ollama to generate YAML"""

        prompt = f"""You are a Pegasus workflow expert. Convert this Python workflow descriptor to valid Pegasus YAML format.

PYTHON CODE:
```python
{python_code}
```

METADATA:
Imports: {metadata.get('imports', [])}
Variables: {list(metadata.get('variables', {}).keys())}
Functions: {metadata.get('functions', [])}

REQUIREMENTS:
1. Generate a complete Pegasus workflow YAML structure
2. Include: name, jobs, transformations
3. Infer job dependencies from the code logic
4. Create appropriate transformation catalog entries
5. Use proper Pegasus YAML schema

OUTPUT FORMAT (strict JSON):
{{
  "workflow": {{
    "name": "workflow_name",
    "version": "1.0",
    "jobs": [
      {{
        "name": "job_name",
        "transformation": "transformation_name",
        "arguments": ["--arg value"],
        "uses": [
          {{"name": "file.txt", "type": "input"}},
          {{"name": "output.txt", "type": "output"}}
        ],
        "parents": ["parent_job_name"]
      }}
    ],
    "transformations": [
      {{
        "name": "transformation_name",
        "pfn": "/path/to/executable",
        "type": "stageable"
      }}
    ]
  }}
}}

Respond ONLY with valid JSON. No additional text."""

        return prompt

    def _generate_offline(self, python_file_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate YAML using templates and rules (no LLM)

        Uses pattern matching and templates to convert Python to YAML
        """
        logger.info("Using template-based generation (offline mode)")

        # Base workflow structure
        workflow = {
            'name': Path(python_file_path).stem,
            'version': '1.0',
            'jobs': [],
            'transformations': []
        }

        # Try to parse Python code
        try:
            with open(python_file_path, 'r') as f:
                source_code = f.read()

            tree = ast.parse(source_code)

            # Extract workflow components from AST
            jobs, transformations = self._extract_from_ast(tree, metadata)

            workflow['jobs'] = jobs
            workflow['transformations'] = transformations

            # If nothing found, use template
            if not jobs:
                logger.warning("No jobs extracted, using default template")
                workflow = self._generate_template_workflow(Path(python_file_path).stem)

        except Exception as e:
            logger.error(f"Offline generation failed: {e}, using default template")
            workflow = self._generate_template_workflow(Path(python_file_path).stem)

        return workflow

    def _extract_from_ast(self, tree: ast.AST, metadata: Dict[str, Any]) -> tuple:
        """Extract jobs and transformations from Python AST"""
        jobs = []
        transformations = []

        # Look for dictionary literals or assignments that look like workflow components
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id.lower()

                        # Check if this looks like a job definition
                        if 'job' in var_name and isinstance(node.value, (ast.Dict, ast.List)):
                            try:
                                job_data = ast.literal_eval(node.value)
                                if isinstance(job_data, dict):
                                    jobs.append(job_data)
                                elif isinstance(job_data, list):
                                    jobs.extend([j for j in job_data if isinstance(j, dict)])
                            except:
                                pass

                        # Check if this looks like transformation definition
                        elif 'transform' in var_name and isinstance(node.value, (ast.Dict, ast.List)):
                            try:
                                trans_data = ast.literal_eval(node.value)
                                if isinstance(trans_data, dict):
                                    transformations.append(trans_data)
                                elif isinstance(trans_data, list):
                                    transformations.extend([t for t in trans_data if isinstance(t, dict)])
                            except:
                                pass

        return jobs, transformations

    def _generate_template_workflow(self, workflow_name: str) -> Dict[str, Any]:
        """Generate a basic template workflow when no structure is found"""
        return {
            'name': workflow_name,
            'version': '1.0',
            'jobs': [
                {
                    'name': 'example_job',
                    'transformation': 'ExampleTransformation',
                    'arguments': ['--input', 'input.txt', '--output', 'output.txt'],
                    'uses': [
                        {'name': 'input.txt', 'type': 'input'},
                        {'name': 'output.txt', 'type': 'output'}
                    ]
                }
            ],
            'transformations': [
                {
                    'name': 'ExampleTransformation',
                    'pfn': '/path/to/executable',
                    'type': 'stageable'
                }
            ]
        }

    def save_yaml(self, workflow: Dict[str, Any], output_path: str):
        """Save workflow dictionary as YAML file"""
        try:
            with open(output_path, 'w') as f:
                yaml.dump(workflow, f, default_flow_style=False, sort_keys=False)
            logger.info(f"YAML saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save YAML: {e}")
            raise

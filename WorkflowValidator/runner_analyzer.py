"""
LLM-based runner script analyzer
Detects where workflows are saved by analyzing runner code
"""
import re
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


def analyze_runner_script(runner_path: str, llm_backend=None, generator_path: Optional[str] = None) -> Optional[str]:
    """
    Analyze runner script to detect where it saves workflow YAML files
    If not found, also analyzes the generator script

    Args:
        runner_path: Path to runner script
        llm_backend: Optional LLM backend for intelligent analysis
        generator_path: Optional path to generator script (analyzed if runner detection fails)

    Returns:
        Detected output path/pattern or None
    """
    try:
        # Read runner script
        with open(runner_path, 'r') as f:
            runner_content = f.read()

        logger.info(f"Analyzing runner script: {runner_path}")

        # Read generator script if provided
        generator_content = None
        if generator_path and Path(generator_path).exists():
            try:
                with open(generator_path, 'r') as f:
                    generator_content = f.read()
                logger.info(f"Also reading generator script: {generator_path}")
            except Exception as e:
                logger.warning(f"Could not read generator script: {e}")

        # Try rule-based detection on runner first (fast)
        detected = _rule_based_detection(runner_content)
        if detected:
            logger.info(f"Rule-based detection found in runner: {detected}")
            return detected

        # Try rule-based detection on generator if available
        if generator_content:
            detected = _rule_based_detection(generator_content)
            if detected:
                logger.info(f"Rule-based detection found in generator: {detected}")
                return detected

        # If rule-based failed and LLM is available, use LLM with BOTH scripts
        if llm_backend:
            if generator_content:
                logger.info("Using LLM to analyze BOTH runner and generator together...")
                detected = _llm_based_detection(runner_content, llm_backend, generator_content=generator_content)
            else:
                logger.info("Using LLM to analyze runner script only...")
                detected = _llm_based_detection(runner_content, llm_backend)

            if detected:
                logger.info(f"LLM detection found: {detected}")
                return detected

        return None

    except Exception as e:
        logger.error(f"Failed to analyze scripts: {e}")
        return None


def _rule_based_detection(content: str) -> Optional[str]:
    """
    Rule-based detection using regex patterns

    Looks for common patterns:
    - output/workflow.yml
    - > output/*.yml
    - -o output/
    - --output-dir output/
    """
    patterns = [
        # Direct file output: > output/file.yml
        r'>\s*(["\']?)([^"\'\s]+\.ya?ml)\1',

        # Variable assignment: OUTPUT_DIR="output"
        r'OUTPUT[_-]?(?:DIR|FILE|PATH)\s*=\s*["\']([^"\']+)["\']',

        # Command line arg: -o output/ or --output output/
        r'(?:-o|--output(?:-dir)?)\s+(["\']?)([^"\'\s]+)\1',

        # Python write: open('output/file.yml', 'w')
        r'open\(["\']([^"\']+\.ya?ml)["\']',

        # Python Path.write_text or write_bytes
        r'Path\(["\']([^"\']+\.ya?ml)["\']',

        # Save function: save_to('output/')
        r'(?:save|write|dump)[_-]?(?:to|workflow|yaml|file)?\(["\']([^"\']+)["\']',

        # Python3 command redirecting to file
        r'python3?\s+[^\n]+>\s*([^\s]+\.ya?ml)',

        # YAML dump to file: yaml.dump(..., open('file.yml'))
        r'yaml\.dump\([^)]+,\s*open\(["\']([^"\']+\.ya?ml)["\']',

        # with open(...) as f: pattern
        r'with\s+open\(["\']([^"\']+\.ya?ml)["\']',

        # f.write pattern with file variable
        r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*["\']([^"\']+\.ya?ml)["\']',
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            # Get the last captured group (the path)
            path = match.group(match.lastindex)
            logger.debug(f"Pattern {i} matched: {path}")
            if path and ('output' in path.lower() or '.yml' in path or '.yaml' in path):
                return path

    # Check for common output directories with more specific patterns
    common_dir_patterns = [
        r'mkdir\s+-p\s+["\']?([^"\'\s]+)["\']?',  # mkdir -p output
        r'(?:cd|pushd)\s+([^;\n]+)',  # cd output
    ]

    for pattern in common_dir_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            dir_path = match.group(1).strip()
            logger.debug(f"Found directory: {dir_path}")
            # Check if YAML files are written to this directory
            if '.yml' in content or '.yaml' in content:
                return f'{dir_path}/*.yml'

    return None


def _llm_based_detection(content: str, llm_backend, generator_content: Optional[str] = None) -> Optional[str]:
    """
    Use LLM to analyze runner script and detect output paths
    If generator content is provided, analyzes both together for better context
    """
    if generator_content:
        # Analyze both scripts together
        prompt = f"""You are analyzing a workflow generation system with two scripts:

1. RUNNER SCRIPT (orchestrator that executes the generator):
```
{content[:1500]}
```

2. GENERATOR SCRIPT (creates the workflow YAML):
```
{generator_content[:1500]}
```

TASK: Determine the EXACT path or pattern where the workflow YAML file(s) will be saved.

Look for:
- Output file paths in generator (e.g., "output/workflow.yml", OUTPUT_FILE = "workflow.yml")
- Output directories in generator (e.g., OUTPUT_DIR = "output")
- File redirection in runner (e.g., > output.yml)
- How runner executes generator (arguments, environment variables)
- Merge information from both scripts to build complete path

IMPORTANT:
- If generator has OUTPUT_DIR="output" and OUTPUT_FILE="workflow.yml", respond: "output/workflow.yml"
- If generator writes to "workflow.yml" and runner redirects > output/, respond: "output/workflow.yml"
- If generator uses variable paths, look for how runner sets them
- Combine directory from one script with filename from another

Respond with ONLY the path/pattern where workflows are saved, or "NONE" if cannot determine.

Examples:
- "output/workflow.yml"
- "generated_workflows/"
- "workflows/*.yml"
- "NONE"

Response:"""
    else:
        # Single script analysis
        prompt = f"""Analyze this script and determine where it saves workflow YAML files.

Script:
```
{content[:2000]}
```

Look for:
1. Output file paths (e.g., output/workflow.yml)
2. Output directories (e.g., output/, generated/)
3. File redirection (e.g., > output.yml)
4. Variable assignments (e.g., OUTPUT_DIR=output)

Respond with ONLY the path/pattern where workflows are saved, or "NONE" if not found.

Examples:
- "output/workflow.yml"
- "output/"
- "generated/*.yml"
- "NONE"

Response:"""

    try:
        # Log prompt details
        logger.info(f"Sending prompt to LLM (length: {len(prompt)} chars)")
        if generator_content:
            logger.info(f"  Runner content: {len(content[:1500])} chars")
            logger.info(f"  Generator content: {len(generator_content[:1500])} chars")
        logger.debug(f"Full prompt:\n{prompt}")

        response = llm_backend.generate(prompt, temperature=0.1, max_tokens=100)
        logger.info(f"LLM response received (length: {len(response)} chars)")
        logger.debug(f"Raw LLM response: {response}")

        response = response.strip().strip('"\'')

        if response.upper() == 'NONE' or not response:
            logger.info("LLM returned NONE or empty response")
            return None

        # Clean up response
        response = response.split('\n')[0]  # Take first line only
        response = response.strip()

        logger.info(f"Cleaned LLM response: {response}")
        return response if response else None

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def find_generated_workflows(base_dir: str, detected_pattern: Optional[str] = None) -> List[Path]:
    """
    Find generated workflow files

    Args:
        base_dir: Base directory to search from
        detected_pattern: Detected pattern from analysis

    Returns:
        List of found YAML files
    """
    import glob

    base_path = Path(base_dir)
    yaml_files = []

    if detected_pattern:
        # Use detected pattern
        if '*' in detected_pattern:
            # Glob pattern
            yaml_files = [Path(f) for f in glob.glob(str(base_path / detected_pattern))]
        elif Path(detected_pattern).is_dir():
            # Directory
            dir_path = base_path / detected_pattern
            yaml_files = list(dir_path.glob('*.yml')) + list(dir_path.glob('*.yaml'))
        elif (base_path / detected_pattern).exists():
            # Single file
            yaml_files = [base_path / detected_pattern]

    if not yaml_files:
        # Fallback: search common locations
        common_patterns = [
            'output/*.yml',
            'output/*.yaml',
            'generated/*.yml',
            'generated/*.yaml',
            'workflows/*.yml',
            'workflows/*.yaml',
            '*.yml',
            '*.yaml'
        ]

        for pattern in common_patterns:
            files = list(base_path.glob(pattern))
            if files:
                yaml_files.extend(files)
                break

    return yaml_files

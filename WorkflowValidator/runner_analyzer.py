"""
LLM-based runner script analyzer
Detects where workflows are saved by analyzing runner code
"""
import re
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


def analyze_runner_script(runner_path: str, llm_backend=None) -> Optional[str]:
    """
    Analyze runner script to detect where it saves workflow YAML files

    Args:
        runner_path: Path to runner script
        llm_backend: Optional LLM backend for intelligent analysis

    Returns:
        Detected output path/pattern or None
    """
    try:
        with open(runner_path, 'r') as f:
            content = f.read()

        # Try rule-based detection first (fast)
        detected = _rule_based_detection(content)
        if detected:
            logger.info(f"Rule-based detection found: {detected}")
            return detected

        # Fallback to LLM if available
        if llm_backend:
            logger.info("Using LLM to analyze runner script...")
            detected = _llm_based_detection(content, llm_backend)
            if detected:
                logger.info(f"LLM detection found: {detected}")
                return detected

        return None

    except Exception as e:
        logger.error(f"Failed to analyze runner: {e}")
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
        r'OUTPUT[_-]?DIR\s*=\s*["\']?([^"\'\s]+)["\']?',

        # Command line arg: -o output/ or --output output/
        r'(?:-o|--output(?:-dir)?)\s+(["\']?)([^"\'\s]+)\1',

        # Python write: open('output/file.yml', 'w')
        r'open\(["\']([^"\']+\.ya?ml)["\']',

        # Save function: save_to('output/')
        r'save[_-]?(?:to|workflow|yaml)\(["\']([^"\']+)["\']',

        # Python3 command redirecting to file
        r'python3?\s+[^\n]+>\s*([^\s]+\.ya?ml)',
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


def _llm_based_detection(content: str, llm_backend) -> Optional[str]:
    """
    Use LLM to analyze runner script and detect output paths
    """
    prompt = f"""Analyze this script and determine where it saves workflow YAML files.

Script:
```
{content[:2000]}  # First 2000 chars
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
        response = llm_backend.generate(prompt, temperature=0.1, max_tokens=100)
        response = response.strip().strip('"\'')

        if response.upper() == 'NONE' or not response:
            return None

        # Clean up response
        response = response.split('\n')[0]  # Take first line only
        response = response.strip()

        return response if response else None

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
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

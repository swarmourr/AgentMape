"""
LLM-enhanced validator using Ollama for deep analysis
"""
import yaml
import logging
import json
from typing import Dict, List, Any
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext
from validators.llm_enhanced.llm_backends import OllamaBackend

logger = logging.getLogger(__name__)


class LLMValidator:
    """Uses Ollama LLM to perform deep semantic validation"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.prompt_dir = Path(__file__).parent / 'prompts'

        # Initialize Ollama backend
        self.backend = self._init_backend()

    def _init_backend(self):
        """Initialize Ollama LLM backend (same as Analyzer/Planner)"""
        try:
            # Build ollama config from flat JSON config
            ollama_config = {
                'host': self.config.get('ollama_api_base', 'http://localhost:11434'),
                'model': self.config.get('ollama_model', 'glm-4.6:cloud'),
                'temperature': self.config.get('ollama_temperature', 0.1),
                'timeout': self.config.get('ollama_timeout', 60),
                'max_tokens': self.config.get('ollama_max_tokens', 4000)
            }
            backend = OllamaBackend(ollama_config)

            # Check if backend is available
            if backend.is_available():
                logger.info(f"Ollama backend initialized successfully: {ollama_config['model']}")
                return backend
            else:
                logger.warning(f"Ollama backend not available at {ollama_config['host']}")
                return None

        except Exception as e:
            logger.error(f"Failed to initialize Ollama backend: {e}")
            return None

    def validate(self, context: WorkflowContext, checks: List[str] = None) -> ValidatorResult:
        """
        Perform LLM-based validation using Ollama

        Args:
            context: Workflow context
            checks: List of checks to perform (e.g., ['structure', 'code_basic'])

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0

        if not self.backend:
            logger.warning("Ollama backend not available, skipping LLM validation")
            return ValidatorResult(
                name="llm",
                status=ValidationStatus.WARNING,
                duration_seconds=0,
                issues=[ValidationIssue(
                    severity=Severity.WARNING,
                    category=Category.STRUCTURE,
                    message="LLM validation skipped (Ollama not available)",
                    detected_by="llm"
                )],
                checks_performed=0
            )

        # Default checks if none specified
        if not checks:
            checks = ['structure']

        # Perform requested checks
        if 'structure' in checks or 'code_basic' in checks or 'code_deep' in checks:
            struct_issues = self._validate_structure(context)
            issues.extend(struct_issues)
            checks_performed += 1

        # Determine status
        error_count = len([i for i in issues if i.severity in [Severity.CRITICAL, Severity.ERROR]])
        if error_count > 0:
            status = ValidationStatus.FAILED
        elif len(issues) > 0:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASSED

        duration = time.time() - start_time

        return ValidatorResult(
            name="llm",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed
        )

    def _validate_structure(self, context: WorkflowContext) -> List[ValidationIssue]:
        """Use Ollama to validate workflow structure"""
        issues = []

        try:
            # Load prompt template
            prompt_file = self.prompt_dir / 'structure_analysis.txt'
            with open(prompt_file, 'r') as f:
                prompt_template = f.read()

            # Prepare workflow and catalog content
            workflow_yaml = yaml.dump(context.workflow_yaml_content) if context.workflow_yaml_content else "Not available"
            tc_yaml = yaml.dump(context.transformation_catalog) if context.transformation_catalog else "Not available"

            # Fill in prompt
            prompt = prompt_template.format(
                workflow_yaml=workflow_yaml,
                transformation_catalog=tc_yaml
            )

            logger.info("Sending structure validation request to Ollama...")

            # Get LLM response
            response_json = self.backend.generate_json(prompt)

            logger.info("Received response from Ollama")

            # Parse LLM response
            llm_errors = response_json.get('errors', [])
            for error in llm_errors:
                # Convert LLM severity to our enum
                severity_map = {
                    'critical': Severity.CRITICAL,
                    'error': Severity.ERROR,
                    'warning': Severity.WARNING,
                    'info': Severity.INFO
                }
                severity = severity_map.get(error.get('severity', 'warning').lower(), Severity.WARNING)

                issues.append(ValidationIssue(
                    severity=severity,
                    category=Category.STRUCTURE,
                    message=error.get('issue', 'LLM detected an issue'),
                    location=error.get('location'),
                    explanation=error.get('explanation'),
                    impact=error.get('impact'),
                    suggestion=error.get('suggested_fix'),
                    detected_by="llm"
                ))

        except Exception as e:
            logger.error(f"Ollama validation failed: {e}")
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                message=f"LLM validation failed: {e}",
                detected_by="llm"
            ))

        return issues

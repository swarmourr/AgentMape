"""
LLM Multi-Prompt Validator - Uses LLM for ALL validation steps with separate prompts
"""
import logging
import time
from typing import Dict, List, Any
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class LLMMultiPromptValidator:
    """Uses LLM with multiple prompts for comprehensive validation"""

    def __init__(self, llm_backend, config: Dict[str, Any]):
        self.llm_backend = llm_backend
        self.config = config.get('llm_backend', {})
        self.temperature = self.config.get('temperature', 0.1)

    def validate(self, context: WorkflowContext) -> List[ValidatorResult]:
        """
        Run multiple LLM prompts for validation

        Returns:
            List of ValidatorResult (one per prompt)
        """
        results = []

        # PROMPT 1: Structure validation
        logger.info("🤖 [LLM PROMPT 1/7] Validating workflow structure...")
        start = time.time()
        result = self._validate_structure(context)
        results.append(result)
        logger.info(f"✓ LLM structure validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 2: Job dependencies
        logger.info("🤖 [LLM PROMPT 2/7] Validating job dependencies...")
        start = time.time()
        result = self._validate_dependencies(context)
        results.append(result)
        logger.info(f"✓ LLM dependency validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 3: File paths
        logger.info("🤖 [LLM PROMPT 3/7] Validating file paths...")
        start = time.time()
        result = self._validate_paths(context)
        results.append(result)
        logger.info(f"✓ LLM path validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 4: Resource requirements
        logger.info("🤖 [LLM PROMPT 4/7] Validating resource requirements...")
        start = time.time()
        result = self._validate_resources(context)
        results.append(result)
        logger.info(f"✓ LLM resource validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 5: Data integrity
        logger.info("🤖 [LLM PROMPT 5/7] Validating data integrity...")
        start = time.time()
        result = self._validate_integrity(context)
        results.append(result)
        logger.info(f"✓ LLM integrity validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 6: Security checks
        logger.info("🤖 [LLM PROMPT 6/7] Running security checks...")
        start = time.time()
        result = self._validate_security(context)
        results.append(result)
        logger.info(f"✓ LLM security validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 7: Best practices
        logger.info("🤖 [LLM PROMPT 7/7] Checking best practices...")
        start = time.time()
        result = self._validate_best_practices(context)
        results.append(result)
        logger.info(f"✓ LLM best practices check: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        return results

    def _validate_structure(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates workflow structure"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content
        if not workflow:
            return self._empty_result("llm_structure")

        prompt = f"""Analyze this Pegasus workflow structure and find issues:

```yaml
{str(workflow)[:2000]}
```

Check for:
1. Required fields (name, jobs)
2. Job structure (name, transformation, arguments)
3. Catalog structure (transformationCatalog, replicaCatalog)
4. Pegasus 5.0+ format compliance

Return JSON:
{{
  "issues": [
    {{"severity": "error|warning", "message": "description", "location": "where"}}
  ]
}}"""

        response = self._call_llm_and_log(prompt, "llm_structure")
        issues = self._parse_llm_response(response, "llm_structure")

        return ValidatorResult(
            name="llm_structure",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_dependencies(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates job dependencies"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content
        if not workflow or 'jobs' not in workflow:
            return self._empty_result("llm_dependencies")

        jobs = workflow.get('jobs', [])

        prompt = f"""Analyze job dependencies in this workflow:

Jobs: {str(jobs)[:2000]}

Check for:
1. Circular dependencies
2. Missing parent jobs
3. Invalid dependency chains
4. Orphaned jobs

Return JSON:
{{
  "issues": [
    {{"severity": "error|warning", "message": "description", "location": "job:name"}}
  ]
}}"""

        response = self._call_llm_and_log(prompt, "llm_dependencies")
        issues = self._parse_llm_response(response, "llm_dependencies")

        return ValidatorResult(
            name="llm_dependencies",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1
        )

    def _validate_paths(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates file paths"""
        import time
        start_time = time.time()

        tc = context.transformation_catalog
        rc = context.replica_catalog

        prompt = f"""Analyze file paths in these catalogs:

Transformation Catalog: {str(tc)[:1000] if tc else 'None'}
Replica Catalog: {str(rc)[:1000] if rc else 'None'}

Check for:
1. Absolute vs relative paths
2. Path consistency
3. Missing path specifications
4. Suspicious paths

Return JSON:
{{
  "issues": [
    {{"severity": "error|warning", "message": "description", "location": "catalog:item"}}
  ]
}}"""

        response = self._call_llm_and_log(prompt, "llm_paths")
        issues = self._parse_llm_response(response, "llm_paths")

        return ValidatorResult(
            name="llm_paths",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1
        )

    def _validate_resources(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates resource requirements"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content
        if not workflow or 'jobs' not in workflow:
            return self._empty_result("llm_resources")

        jobs = workflow.get('jobs', [])

        prompt = f"""Analyze resource requirements in these jobs:

Jobs: {str(jobs)[:2000]}

Check for:
1. Excessive memory requests (>512GB)
2. Excessive CPU requests (>128 cores)
3. Unrealistic resource combinations
4. Missing resource specifications

Return JSON:
{{
  "issues": [
    {{"severity": "error|warning", "message": "description", "location": "job:name"}}
  ]
}}"""

        response = self._call_llm_and_log(prompt, "llm_resources")
        issues = self._parse_llm_response(response, "llm_resources")

        return ValidatorResult(
            name="llm_resources",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1
        )

    def _validate_integrity(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates data integrity"""
        import time
        start_time = time.time()

        rc = context.replica_catalog

        prompt = f"""Analyze data files in replica catalog:

Replica Catalog: {str(rc)[:2000] if rc else 'None'}

Check for:
1. File format specifications
2. Data consistency
3. Missing metadata
4. Potential data issues

Return JSON:
{{
  "issues": [
    {{"severity": "error|warning", "message": "description", "location": "replica:lfn"}}
  ]
}}"""

        response = self._call_llm_and_log(prompt, "llm_integrity")
        issues = self._parse_llm_response(response, "llm_integrity")

        return ValidatorResult(
            name="llm_integrity",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1
        )

    def _validate_security(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates security"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content

        prompt = f"""Security analysis of this workflow:

Workflow: {str(workflow)[:2000] if workflow else 'None'}

Check for:
1. Hardcoded credentials
2. Unsafe file permissions
3. Command injection risks
4. Insecure paths

Return JSON:
{{
  "issues": [
    {{"severity": "error|warning", "message": "description", "location": "where"}}
  ]
}}"""

        response = self._call_llm_and_log(prompt, "llm_security")
        issues = self._parse_llm_response(response, "llm_security")

        return ValidatorResult(
            name="llm_security",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1
        )

    def _validate_best_practices(self, context: WorkflowContext) -> ValidatorResult:
        """LLM checks best practices"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content

        prompt = f"""Check Pegasus workflow best practices:

Workflow: {str(workflow)[:2000] if workflow else 'None'}

Check for:
1. Naming conventions
2. Documentation/comments
3. Job organization
4. Catalog usage
5. Performance optimizations

Return JSON:
{{
  "issues": [
    {{"severity": "warning|info", "message": "suggestion", "location": "where"}}
  ]
}}"""

        response = self._call_llm_and_log(prompt, "llm_best_practices")
        issues = self._parse_llm_response(response, "llm_best_practices")

        return ValidatorResult(
            name="llm_best_practices",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1
        )

    def _call_llm_and_log(self, prompt: str, validator_name: str) -> str:
        """Call LLM and log the response"""
        response = self.llm_backend.generate(prompt, temperature=self.temperature, max_tokens=1000)

        # Log the LLM response
        logger.info("📝 LLM Analysis:")
        logger.info(response[:800] if len(response) > 800 else response)
        logger.info("")

        return response

    def _parse_llm_response(self, response: str, validator_name: str) -> List[ValidationIssue]:
        """Parse LLM JSON response into ValidationIssues"""
        import json
        import re

        issues = []

        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                for issue in data.get('issues', []):
                    severity_str = issue.get('severity', 'warning').lower()
                    severity_map = {
                        'critical': Severity.CRITICAL,
                        'error': Severity.ERROR,
                        'warning': Severity.WARNING,
                        'info': Severity.INFO
                    }
                    severity = severity_map.get(severity_str, Severity.WARNING)

                    issues.append(ValidationIssue(
                        severity=severity,
                        category=Category.STRUCTURE,
                        message=issue.get('message', 'Issue detected by LLM'),
                        location=issue.get('location'),
                        detected_by="llm"
                    ))
        except Exception as e:
            logger.warning(f"Failed to parse LLM response for {validator_name}: {e}")

        return issues

    def _determine_status(self, issues: List[ValidationIssue]) -> ValidationStatus:
        """Determine status from issues"""
        if not issues:
            return ValidationStatus.PASSED

        has_errors = any(i.severity in [Severity.CRITICAL, Severity.ERROR] for i in issues)
        if has_errors:
            return ValidationStatus.FAILED

        return ValidationStatus.WARNING

    def _empty_result(self, name: str) -> ValidatorResult:
        """Return empty result"""
        return ValidatorResult(
            name=name,
            status=ValidationStatus.PASSED,
            duration_seconds=0,
            issues=[],
            checks_performed=0
        )

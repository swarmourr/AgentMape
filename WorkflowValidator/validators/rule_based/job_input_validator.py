"""
Job Input Validator - Validates that job input files exist in replica catalog
"""
import os
import logging
from typing import Dict, List, Any, Set, Tuple
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class JobInputValidator:
    """Validates that all job input files are declared in replica catalog"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('job_inputs', {})
        self.check_input_files = self.config.get('check_input_files', True)
        self.check_output_conflicts = self.config.get('check_output_conflicts', True)

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Validate job input/output files

        Args:
            context: Workflow context with workflow YAML and catalogs

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0
        validated_jobs = []

        if not context.workflow_yaml_content:
            return ValidatorResult(
                name="job_inputs",
                status=ValidationStatus.PASSED,
                duration_seconds=0,
                issues=[],
                checks_performed=0
            )

        # Get jobs
        jobs = context.workflow_yaml_content.get('jobs', [])

        # Get available replicas (LFNs)
        available_lfns = self._get_available_lfns(context)

        for job in jobs:
            if not isinstance(job, dict):
                continue

            job_name = job.get('name', 'unknown')
            uses = job.get('uses', [])

            if not uses:
                continue

            checks_performed += 1
            input_files = []
            output_files = []
            missing_inputs = []
            conflicting_outputs = []

            for use in uses:
                if not isinstance(use, dict):
                    continue

                lfn = use.get('lfn') or use.get('name')
                use_type = use.get('type', 'input')

                if not lfn:
                    continue

                if use_type == 'input':
                    input_files.append(lfn)
                    # Check if input file exists in replica catalog
                    if self.check_input_files and lfn not in available_lfns:
                        missing_inputs.append(lfn)
                        issues.append(ValidationIssue(
                            severity=Severity.ERROR,
                            category=Category.DEPENDENCIES,
                            message=f"Job '{job_name}' requires input file '{lfn}' not found in replica catalog",
                            location=f"job:{job_name}",
                            explanation=f"Input file '{lfn}' is declared in job uses but not available in replicaCatalog",
                            impact="Job will fail when trying to access this input file",
                            suggestion=f"Add '{lfn}' to replicaCatalog with a valid PFN",
                            detected_by="rule"
                        ))

                elif use_type == 'output':
                    output_files.append(lfn)
                    # Check if output file will overwrite existing replica
                    if self.check_output_conflicts and lfn in available_lfns:
                        conflicting_outputs.append(lfn)
                        issues.append(ValidationIssue(
                            severity=Severity.WARNING,
                            category=Category.DEPENDENCIES,
                            message=f"Job '{job_name}' output file '{lfn}' already exists in replica catalog",
                            location=f"job:{job_name}",
                            explanation=f"Output file '{lfn}' may overwrite existing file",
                            impact="Existing file will be overwritten",
                            suggestion="Consider using a different output filename or remove existing file",
                            detected_by="rule"
                        ))

            # Track validated job
            if input_files or output_files:
                validated_jobs.append({
                    "job_name": job_name,
                    "input_files": input_files,
                    "output_files": output_files,
                    "missing_inputs": missing_inputs,
                    "conflicting_outputs": conflicting_outputs,
                    "status": "OK" if not missing_inputs else "ERROR"
                })
                logger.info(f"Validated job inputs: {job_name} - {len(input_files)} inputs, {len(output_files)} outputs")

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
            name="job_inputs",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed,
            metadata={"validated_jobs": validated_jobs}
        )

    def _get_available_lfns(self, context: WorkflowContext) -> Set[str]:
        """Extract all available LFNs from replica catalog"""
        lfns = set()

        if not context.replica_catalog:
            return lfns

        # Handle both formats
        replicas = None
        if 'replicaCatalog' in context.replica_catalog and 'replicas' in context.replica_catalog['replicaCatalog']:
            replicas = context.replica_catalog['replicaCatalog']['replicas']
        elif 'replicas' in context.replica_catalog:
            replicas = context.replica_catalog['replicas']

        if replicas:
            for replica in replicas:
                if isinstance(replica, dict) and 'lfn' in replica:
                    lfns.add(replica['lfn'])

        return lfns

"""
Resource Validator - Validates job resource requirements are reasonable
"""
import logging
from typing import Dict, List, Any
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class ResourceValidator:
    """Validates job resource requirements"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('resources', {})
        self.max_memory_gb = self.config.get('max_memory_gb', 512)
        self.max_cpus = self.config.get('max_cpus', 128)
        self.max_disk_gb = self.config.get('max_disk_gb', 10000)
        self.warn_memory_gb = self.config.get('warn_memory_gb', 256)
        self.warn_cpus = self.config.get('warn_cpus', 64)

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Validate resource requirements

        Args:
            context: Workflow context with workflow YAML

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0
        validated_resources = []

        if not context.workflow_yaml_content:
            return ValidatorResult(
                name="resources",
                status=ValidationStatus.PASSED,
                duration_seconds=0,
                issues=[],
                checks_performed=0
            )

        jobs = context.workflow_yaml_content.get('jobs', [])

        for job in jobs:
            if not isinstance(job, dict):
                continue

            job_name = job.get('name', 'unknown')
            profiles = job.get('profiles', {})

            if not profiles:
                continue

            checks_performed += 1

            # Check Condor profile
            condor = profiles.get('condor', {})
            env = profiles.get('env', {})

            resource_info = {
                "job_name": job_name,
                "memory_gb": None,
                "cpus": None,
                "disk_gb": None,
                "issues": []
            }

            # Validate memory
            if 'request_memory' in condor:
                memory_str = str(condor['request_memory'])
                memory_gb = self._parse_memory(memory_str)
                resource_info["memory_gb"] = memory_gb

                if memory_gb and memory_gb > self.max_memory_gb:
                    resource_info["issues"].append("excessive_memory")
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        category=Category.RESOURCES,
                        message=f"Job '{job_name}' requests excessive memory: {memory_gb}GB (max: {self.max_memory_gb}GB)",
                        location=f"job:{job_name}",
                        explanation=f"Requested memory exceeds system limits",
                        impact="Job may not be scheduled or will fail",
                        suggestion=f"Reduce memory request to {self.max_memory_gb}GB or less",
                        detected_by="rule"
                    ))
                elif memory_gb and memory_gb > self.warn_memory_gb:
                    resource_info["issues"].append("high_memory")
                    issues.append(ValidationIssue(
                        severity=Severity.WARNING,
                        category=Category.RESOURCES,
                        message=f"Job '{job_name}' requests high memory: {memory_gb}GB",
                        location=f"job:{job_name}",
                        explanation=f"High memory requests may result in longer queue times",
                        suggestion=f"Consider if {memory_gb}GB is necessary",
                        detected_by="rule"
                    ))

            # Validate CPUs
            if 'request_cpus' in condor:
                cpus = int(condor['request_cpus'])
                resource_info["cpus"] = cpus

                if cpus > self.max_cpus:
                    resource_info["issues"].append("excessive_cpus")
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        category=Category.RESOURCES,
                        message=f"Job '{job_name}' requests excessive CPUs: {cpus} (max: {self.max_cpus})",
                        location=f"job:{job_name}",
                        explanation=f"Requested CPUs exceed system limits",
                        impact="Job may not be scheduled",
                        suggestion=f"Reduce CPU request to {self.max_cpus} or less",
                        detected_by="rule"
                    ))
                elif cpus > self.warn_cpus:
                    resource_info["issues"].append("high_cpus")
                    issues.append(ValidationIssue(
                        severity=Severity.WARNING,
                        category=Category.RESOURCES,
                        message=f"Job '{job_name}' requests high CPU count: {cpus}",
                        location=f"job:{job_name}",
                        explanation=f"High CPU requests may result in longer queue times",
                        suggestion=f"Verify that job can effectively use {cpus} CPUs",
                        detected_by="rule"
                    ))

            # Validate disk
            if 'request_disk' in condor:
                disk_str = str(condor['request_disk'])
                disk_gb = self._parse_disk(disk_str)
                resource_info["disk_gb"] = disk_gb

                if disk_gb and disk_gb > self.max_disk_gb:
                    resource_info["issues"].append("excessive_disk")
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        category=Category.RESOURCES,
                        message=f"Job '{job_name}' requests excessive disk: {disk_gb}GB (max: {self.max_disk_gb}GB)",
                        location=f"job:{job_name}",
                        explanation=f"Requested disk exceeds system limits",
                        impact="Job may not be scheduled",
                        suggestion=f"Reduce disk request to {self.max_disk_gb}GB or less",
                        detected_by="rule"
                    ))

            validated_resources.append(resource_info)
            logger.info(f"Validated resources: {job_name} - {resource_info.get('memory_gb')}GB RAM, {resource_info.get('cpus')} CPUs")

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
            name="resources",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed,
            metadata={"validated_resources": validated_resources}
        )

    def _parse_memory(self, memory_str: str) -> float:
        """Parse memory string to GB"""
        try:
            memory_str = str(memory_str).strip().upper()

            if 'GB' in memory_str or 'G' in memory_str:
                return float(memory_str.replace('GB', '').replace('G', '').strip())
            elif 'MB' in memory_str or 'M' in memory_str:
                return float(memory_str.replace('MB', '').replace('M', '').strip()) / 1024
            elif 'KB' in memory_str or 'K' in memory_str:
                return float(memory_str.replace('KB', '').replace('K', '').strip()) / (1024 * 1024)
            else:
                # Assume bytes
                return float(memory_str) / (1024 * 1024 * 1024)
        except:
            return None

    def _parse_disk(self, disk_str: str) -> float:
        """Parse disk string to GB"""
        return self._parse_memory(disk_str)  # Same logic

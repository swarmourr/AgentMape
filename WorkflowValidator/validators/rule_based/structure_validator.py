"""
Structure validator - validates workflow YAML structure and dependencies
"""
import yaml
import logging
from typing import Dict, List, Any, Set
from pathlib import Path
import networkx as nx

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class StructureValidator:
    """Validates workflow structure, dependencies, and DAG"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('structure', {})
        self.required_fields = self.config.get('required_fields', ['name', 'jobs', 'transformations'])
        self.check_circular = self.config.get('check_circular_dependencies', True)
        self.check_orphans = self.config.get('check_orphan_jobs', True)

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Validate workflow structure

        Args:
            context: Workflow context with YAML and catalogs

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0

        # Load workflow YAML if not already loaded
        if context.workflow_yaml_content is None:
            try:
                with open(context.workflow_yaml_path, 'r') as f:
                    context.workflow_yaml_content = yaml.safe_load(f)
            except Exception as e:
                issues.append(ValidationIssue(
                    severity=Severity.CRITICAL,
                    category=Category.SYNTAX,
                    message=f"Cannot parse workflow YAML: {e}",
                    location=context.workflow_yaml_path,
                    detected_by="rule"
                ))
                return ValidatorResult(
                    name="structure",
                    status=ValidationStatus.FAILED,
                    duration_seconds=time.time() - start_time,
                    issues=issues,
                    checks_performed=1
                )

        workflow = context.workflow_yaml_content

        # Check 1: Required fields
        issues.extend(self._check_required_fields(workflow, context.workflow_yaml_path))
        checks_performed += 1

        # Check 2: Job structure
        if 'jobs' in workflow:
            issues.extend(self._check_jobs(workflow['jobs'], context.workflow_yaml_path))
            checks_performed += 1

            # Check 3: Dependencies
            if self.check_circular:
                issues.extend(self._check_dependencies(workflow['jobs'], context.workflow_yaml_path))
                checks_performed += 1

            # Check 4: Cross-references with transformation catalog
            if context.transformation_catalog:
                issues.extend(self._check_transformations(
                    workflow['jobs'],
                    context.transformation_catalog,
                    context.workflow_yaml_path
                ))
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
            name="structure",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed
        )

    def _check_required_fields(self, workflow: Dict, file_path: str) -> List[ValidationIssue]:
        """Check if required top-level fields exist"""
        issues = []

        for field in self.required_fields:
            if field not in workflow:
                issues.append(ValidationIssue(
                    severity=Severity.CRITICAL,
                    category=Category.STRUCTURE,
                    message=f"Required field '{field}' missing from workflow",
                    location=file_path,
                    explanation=f"Pegasus workflows must have a '{field}' field",
                    suggestion=f"Add '{field}' field to workflow YAML",
                    detected_by="rule"
                ))

        return issues

    def _check_jobs(self, jobs: List[Dict], file_path: str) -> List[ValidationIssue]:
        """Check job definitions"""
        issues = []

        if not jobs or len(jobs) == 0:
            issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                category=Category.STRUCTURE,
                message="Workflow has no jobs defined",
                location=file_path,
                explanation="A workflow must have at least one job",
                suggestion="Add job definitions to the 'jobs' section",
                detected_by="rule"
            ))
            return issues

        job_names = set()

        for idx, job in enumerate(jobs):
            # Check required job fields
            if 'name' not in job:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.STRUCTURE,
                    message=f"Job at index {idx} missing 'name' field",
                    location=f"{file_path}:job[{idx}]",
                    suggestion="Add 'name' field to job definition",
                    detected_by="rule"
                ))
                continue

            job_name = job['name']

            # Check for duplicate names
            if job_name in job_names:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.STRUCTURE,
                    message=f"Duplicate job name: '{job_name}'",
                    location=f"{file_path}:job[{idx}]",
                    explanation="Job names must be unique within a workflow",
                    suggestion=f"Rename one of the jobs named '{job_name}'",
                    detected_by="rule"
                ))
            else:
                job_names.add(job_name)

            # Check transformation field
            if 'transformation' not in job:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.STRUCTURE,
                    message=f"Job '{job_name}' missing 'transformation' field",
                    location=f"{file_path}:job[{idx}]",
                    suggestion="Add 'transformation' field specifying which transformation to use",
                    detected_by="rule"
                ))

        return issues

    def _check_dependencies(self, jobs: List[Dict], file_path: str) -> List[ValidationIssue]:
        """Check job dependencies and detect cycles"""
        issues = []

        # Build job name set
        job_names = {job['name'] for job in jobs if 'name' in job}

        # Build dependency graph
        graph = nx.DiGraph()
        for job in jobs:
            if 'name' not in job:
                continue

            job_name = job['name']
            graph.add_node(job_name)

            # Check parent dependencies
            if 'parents' in job:
                for parent in job.get('parents', []):
                    if parent not in job_names:
                        issues.append(ValidationIssue(
                            severity=Severity.ERROR,
                            category=Category.DEPENDENCIES,
                            message=f"Job '{job_name}' depends on non-existent job '{parent}'",
                            location=f"{file_path}:job:{job_name}",
                            explanation=f"Job '{parent}' is not defined in the workflow",
                            suggestion=f"Either add job '{parent}' or remove it from dependencies",
                            detected_by="rule"
                        ))
                    else:
                        graph.add_edge(parent, job_name)

        # Check for cycles
        try:
            cycles = list(nx.simple_cycles(graph))
            if cycles:
                for cycle in cycles:
                    cycle_str = " → ".join(cycle + [cycle[0]])
                    issues.append(ValidationIssue(
                        severity=Severity.CRITICAL,
                        category=Category.DEPENDENCIES,
                        message=f"Circular dependency detected: {cycle_str}",
                        location=file_path,
                        explanation="Workflows must form a DAG (no cycles)",
                        impact="Workflow cannot be executed (infinite loop)",
                        suggestion=f"Break the cycle by removing one dependency",
                        detected_by="rule"
                    ))
        except Exception as e:
            logger.warning(f"Error checking for cycles: {e}")

        # Check for orphan jobs (if enabled)
        if self.check_orphans and len(graph.nodes) > 1:
            # Find root nodes (no incoming edges)
            root_nodes = [n for n in graph.nodes if graph.in_degree(n) == 0]

            # Find all reachable nodes from roots
            reachable = set()
            for root in root_nodes:
                reachable.update(nx.descendants(graph, root))
                reachable.add(root)

            # Find orphans (unreachable nodes)
            orphans = set(graph.nodes) - reachable
            if orphans:
                for orphan in orphans:
                    issues.append(ValidationIssue(
                        severity=Severity.WARNING,
                        category=Category.DEPENDENCIES,
                        message=f"Job '{orphan}' is unreachable (orphan)",
                        location=f"{file_path}:job:{orphan}",
                        explanation="This job cannot be reached from any entry point",
                        suggestion="Add dependency from another job or remove if not needed",
                        detected_by="rule"
                    ))

        return issues

    def _check_transformations(self, jobs: List[Dict], tc: Dict, file_path: str) -> List[ValidationIssue]:
        """Check if transformations exist in catalog"""
        issues = []

        # Get transformation names from catalog
        tc_names = set()
        if 'transformations' in tc:
            for trans in tc['transformations']:
                if 'name' in trans:
                    tc_names.add(trans['name'])

        # Check each job's transformation
        for job in jobs:
            if 'name' not in job or 'transformation' not in job:
                continue

            job_name = job['name']
            trans_name = job['transformation']

            if trans_name not in tc_names:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.STRUCTURE,
                    message=f"Job '{job_name}' uses undefined transformation '{trans_name}'",
                    location=f"{file_path}:job:{job_name}",
                    explanation=f"Transformation '{trans_name}' not found in transformation catalog",
                    suggestion=f"Add '{trans_name}' to transformation catalog or use a different transformation",
                    detected_by="rule"
                ))

        return issues

"""
DAG Validator - Validates workflow dependency graph (no cycles, valid parents)
"""
import logging
from typing import Dict, List, Any, Set
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class DAGValidator:
    """Validates workflow forms a valid Directed Acyclic Graph"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('dag', {})
        self.check_cycles = self.config.get('check_cycles', True)
        self.check_missing_parents = self.config.get('check_missing_parents', True)

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Validate DAG structure

        Args:
            context: Workflow context with workflow YAML

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0
        dag_info = {
            "total_jobs": 0,
            "jobs_with_parents": 0,
            "max_depth": 0,
            "cycles_detected": []
        }

        if not context.workflow_yaml_content:
            return ValidatorResult(
                name="dag",
                status=ValidationStatus.PASSED,
                duration_seconds=0,
                issues=[],
                checks_performed=0
            )

        jobs = context.workflow_yaml_content.get('jobs', [])
        job_names = set()
        dependencies = {}  # job_name -> list of parent names

        # Build dependency graph
        for job in jobs:
            if not isinstance(job, dict):
                continue

            job_name = job.get('name', 'unknown')
            job_names.add(job_name)
            parents = job.get('parents', []) or job.get('parent', [])

            if isinstance(parents, str):
                parents = [parents]

            dependencies[job_name] = parents

        dag_info["total_jobs"] = len(job_names)

        # Check 1: Missing parents
        if self.check_missing_parents:
            checks_performed += 1
            for job_name, parents in dependencies.items():
                for parent in parents:
                    if parent not in job_names:
                        issues.append(ValidationIssue(
                            severity=Severity.ERROR,
                            category=Category.STRUCTURE,
                            message=f"Job '{job_name}' has undefined parent: '{parent}'",
                            location=f"job:{job_name}",
                            explanation=f"Parent job '{parent}' does not exist in workflow",
                            impact="Workflow submission will fail",
                            suggestion=f"Add job '{parent}' to workflow or remove from parents list",
                            detected_by="rule"
                        ))

                if parents:
                    dag_info["jobs_with_parents"] += 1

        # Check 2: Cycles in dependency graph
        if self.check_cycles:
            checks_performed += 1
            cycles = self._detect_cycles(dependencies)
            dag_info["cycles_detected"] = cycles

            for cycle in cycles:
                cycle_str = " -> ".join(cycle)
                issues.append(ValidationIssue(
                    severity=Severity.CRITICAL,
                    category=Category.STRUCTURE,
                    message=f"Circular dependency detected: {cycle_str}",
                    location=f"jobs:{','.join(cycle)}",
                    explanation="Workflow contains a cycle which prevents execution",
                    impact="Workflow cannot be executed - Pegasus requires a DAG",
                    suggestion="Remove one of the dependencies to break the cycle",
                    detected_by="rule"
                ))

        # Calculate max depth
        if not cycles:
            dag_info["max_depth"] = self._calculate_max_depth(dependencies)
            logger.info(f"DAG validated: {dag_info['total_jobs']} jobs, max depth: {dag_info['max_depth']}")

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
            name="dag",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed,
            metadata=dag_info
        )

    def _detect_cycles(self, dependencies: Dict[str, List[str]]) -> List[List[str]]:
        """Detect cycles in dependency graph using DFS"""
        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node: str) -> bool:
            """DFS with cycle detection"""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            # Visit all parents
            for parent in dependencies.get(node, []):
                if parent not in visited:
                    if dfs(parent):
                        return True
                elif parent in rec_stack:
                    # Found cycle - extract cycle from path
                    cycle_start = path.index(parent)
                    cycle = path[cycle_start:] + [parent]
                    cycles.append(cycle)
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        # Check all nodes
        for job_name in dependencies:
            if job_name not in visited:
                dfs(job_name)

        return cycles

    def _calculate_max_depth(self, dependencies: Dict[str, List[str]]) -> int:
        """Calculate maximum depth of DAG"""
        depth_cache = {}

        def get_depth(job_name: str) -> int:
            """Get depth of job (memoized)"""
            if job_name in depth_cache:
                return depth_cache[job_name]

            parents = dependencies.get(job_name, [])
            if not parents:
                depth_cache[job_name] = 0
                return 0

            max_parent_depth = max([get_depth(p) for p in parents], default=-1)
            depth = max_parent_depth + 1
            depth_cache[job_name] = depth
            return depth

        if not dependencies:
            return 0

        return max([get_depth(job) for job in dependencies.keys()], default=0)

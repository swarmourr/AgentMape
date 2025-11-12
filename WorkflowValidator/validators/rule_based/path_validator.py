"""
Path validator - validates file paths and executables exist
"""
import os
import logging
from typing import Dict, List, Any
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class PathValidator:
    """Validates that all file paths exist and are accessible"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('paths', {})
        self.check_exists = self.config.get('check_file_exists', True)
        self.check_readable = self.config.get('check_readable', True)
        self.check_executable = self.config.get('check_executable', True)
        self.check_shebang = self.config.get('check_shebang', True)

    def _resolve_path(self, file_path: str, base_dir: str = None) -> str:
        """
        Resolve a file path, making it relative to the workflow directory if needed

        Args:
            file_path: The path to resolve
            base_dir: Base directory (workflow file location) to resolve relative paths from

        Returns:
            Resolved absolute path
        """
        # If already absolute, return as is
        if os.path.isabs(file_path):
            return file_path

        # If base_dir provided and path is relative, resolve from base_dir
        if base_dir and not os.path.isabs(file_path):
            resolved = os.path.join(base_dir, file_path)
            logger.debug(f"Resolved '{file_path}' to '{resolved}' (base: {base_dir})")
            return resolved

        # Otherwise return as is (will be checked from current working directory)
        return file_path

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Validate all file paths

        Args:
            context: Workflow context with catalogs

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0

        # Get base directory for resolving relative paths
        base_dir = context.base_directory

        # Validate transformation executables
        if context.transformation_catalog:
            trans_issues, trans_checks = self._validate_transformations(context.transformation_catalog, base_dir)
            issues.extend(trans_issues)
            checks_performed += trans_checks

        # Validate input files from replica catalog
        if context.replica_catalog:
            replica_issues, replica_checks = self._validate_replicas(context.replica_catalog, base_dir)
            issues.extend(replica_issues)
            checks_performed += replica_checks

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
            name="paths",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed
        )

    def _validate_transformations(self, tc: Dict, base_dir: str = None) -> tuple:
        """Validate transformation executable paths"""
        issues = []
        checks = 0

        if 'transformations' not in tc:
            return issues, checks

        for trans in tc['transformations']:
            if 'name' not in trans:
                continue

            trans_name = trans['name']
            checks += 1

            # Get PFN (physical file path)
            pfn = None
            if 'pfn' in trans:
                pfn = trans['pfn']
            elif 'site' in trans and 'pfn' in trans['site']:
                pfn = trans['site']['pfn']

            if not pfn:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    category=Category.PATHS,
                    message=f"Transformation '{trans_name}' has no PFN specified",
                    location=f"transformation:{trans_name}",
                    suggestion="Add 'pfn' field with path to executable",
                    detected_by="rule"
                ))
                continue

            # Resolve path relative to workflow directory
            resolved_pfn = self._resolve_path(pfn, base_dir)

            # Check if file exists
            if self.check_exists and not os.path.exists(resolved_pfn):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.PATHS,
                    message=f"Transformation executable not found: {pfn}",
                    location=f"transformation:{trans_name}",
                    explanation=f"File does not exist at specified path (resolved to: {resolved_pfn})",
                    impact="Job will fail when trying to execute transformation",
                    suggestion=f"Create file at {pfn} or update PFN in catalog",
                    detected_by="rule"
                ))
                continue

            # Check if readable
            if self.check_readable and not os.access(resolved_pfn, os.R_OK):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.PATHS,
                    message=f"Transformation executable not readable: {pfn}",
                    location=f"transformation:{trans_name}",
                    suggestion=f"Fix file permissions: chmod +r {resolved_pfn}",
                    detected_by="rule"
                ))

            # Check if executable
            if self.check_executable and not os.access(resolved_pfn, os.X_OK):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.PATHS,
                    message=f"Transformation file not executable: {pfn}",
                    location=f"transformation:{trans_name}",
                    explanation="Script must have execute permission",
                    suggestion=f"Fix file permissions: chmod +x {resolved_pfn}",
                    detected_by="rule"
                ))

            # Check shebang for scripts
            if self.check_shebang and resolved_pfn.endswith(('.py', '.sh', '.pl', '.rb')):
                shebang_issue = self._check_shebang(resolved_pfn, trans_name)
                if shebang_issue:
                    issues.append(shebang_issue)

        return issues, checks

    def _check_shebang(self, file_path: str, trans_name: str) -> ValidationIssue:
        """Check if script has proper shebang line"""
        try:
            with open(file_path, 'r') as f:
                first_line = f.readline().strip()

            if not first_line.startswith('#!'):
                # Determine expected shebang based on extension
                ext = Path(file_path).suffix
                expected_shebang = {
                    '.py': '#!/usr/bin/env python3',
                    '.sh': '#!/bin/bash',
                    '.pl': '#!/usr/bin/env perl',
                    '.rb': '#!/usr/bin/env ruby'
                }.get(ext, '#!/bin/bash')

                return ValidationIssue(
                    severity=Severity.WARNING,
                    category=Category.PATHS,
                    message=f"Script missing shebang line: {file_path}",
                    location=f"transformation:{trans_name}",
                    explanation="Scripts should start with shebang to specify interpreter",
                    suggestion=f"Add '{expected_shebang}' as first line",
                    detected_by="rule"
                )

        except Exception as e:
            logger.debug(f"Could not check shebang for {file_path}: {e}")

        return None

    def _validate_replicas(self, rc: Dict, base_dir: str = None) -> tuple:
        """Validate replica catalog file paths"""
        issues = []
        checks = 0

        # Handle both 'replicaCatalog.replicas' (Pegasus 5.0+) and 'replicas' (older format)
        replicas = None
        if 'replicaCatalog' in rc and 'replicas' in rc['replicaCatalog']:
            replicas = rc['replicaCatalog']['replicas']
        elif 'replicas' in rc:
            replicas = rc['replicas']

        if not replicas:
            return issues, checks

        for replica in replicas:
            if 'lfn' not in replica:
                continue

            lfn = replica['lfn']
            checks += 1

            # Get PFN - handle both 'pfn' (old format) and 'pfns' (Pegasus 5.0+ array format)
            pfns_to_check = []

            if 'pfn' in replica:
                # Old format: single pfn
                pfns_to_check.append(replica['pfn'])
            elif 'pfns' in replica:
                # New format: array of pfns with site info
                for pfn_entry in replica['pfns']:
                    if isinstance(pfn_entry, dict) and 'pfn' in pfn_entry:
                        pfns_to_check.append(pfn_entry['pfn'])
                    elif isinstance(pfn_entry, str):
                        pfns_to_check.append(pfn_entry)

            if not pfns_to_check:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    category=Category.PATHS,
                    message=f"Replica '{lfn}' has no PFN specified",
                    location=f"replica:{lfn}",
                    suggestion="Add 'pfn' field or 'pfns' array with physical file path(s)",
                    detected_by="rule"
                ))
                continue

            # Check each PFN (usually just one)
            for pfn in pfns_to_check:
                # Resolve path relative to workflow directory
                resolved_pfn = self._resolve_path(pfn, base_dir)

                # Check if file exists
                if self.check_exists and not os.path.exists(resolved_pfn):
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        category=Category.PATHS,
                        message=f"Input file not found: {pfn}",
                        location=f"replica:{lfn}",
                        explanation=f"File does not exist at specified path (resolved to: {resolved_pfn})",
                        impact="Workflow will fail when trying to access this file",
                        suggestion=f"Create file at {pfn} or update PFN in replica catalog",
                        detected_by="rule"
                    ))
                    continue

                # Check if readable
                if self.check_readable and not os.access(resolved_pfn, os.R_OK):
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        category=Category.PATHS,
                        message=f"Input file not readable: {pfn}",
                        location=f"replica:{lfn}",
                        suggestion=f"Fix file permissions: chmod +r {resolved_pfn}",
                        detected_by="rule"
                    ))

                # Check file size (warn if empty)
                try:
                    size = os.path.getsize(resolved_pfn)
                    if size == 0:
                        issues.append(ValidationIssue(
                            severity=Severity.WARNING,
                            category=Category.PATHS,
                            message=f"Input file is empty: {pfn}",
                            location=f"replica:{lfn}",
                            explanation="File exists but has zero bytes",
                            suggestion="Check if file is complete or was truncated",
                            detected_by="rule"
                        ))
                except Exception as e:
                    logger.debug(f"Could not check file size for {pfn}: {e}")

        return issues, checks

"""
Integrity validator - validates data files are readable and not corrupted
"""
import os
import logging
from typing import Dict, List, Any
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class IntegrityValidator:
    """Validates data integrity and file formats"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('integrity', {})
        self.check_readability = self.config.get('check_file_readability', True)
        self.check_corruption = self.config.get('check_file_corruption', True)
        self.validate_csv = self.config.get('validate_csv_format', True)
        self.max_file_size_mb = self.config.get('max_file_size_mb', 1000)

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Validate data integrity

        Args:
            context: Workflow context with replica catalog

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0

        # Validate files from replica catalog
        if context.replica_catalog and 'replicas' in context.replica_catalog:
            for replica in context.replica_catalog['replicas']:
                if 'lfn' not in replica or 'pfn' not in replica:
                    continue

                lfn = replica['lfn']
                pfn = replica['pfn']

                if not os.path.exists(pfn):
                    continue  # Already caught by path validator

                # Check file size
                try:
                    size_mb = os.path.getsize(pfn) / (1024 * 1024)
                    if size_mb > self.max_file_size_mb:
                        logger.info(f"Skipping integrity check for large file: {pfn} ({size_mb:.1f} MB)")
                        continue
                except Exception as e:
                    logger.debug(f"Could not get file size for {pfn}: {e}")
                    continue

                # Check readability
                if self.check_readability:
                    issue = self._check_readability(pfn, lfn)
                    if issue:
                        issues.append(issue)
                    checks_performed += 1

                # Check format for CSV files
                if self.validate_csv and pfn.endswith('.csv'):
                    issue = self._check_csv_format(pfn, lfn)
                    if issue:
                        issues.append(issue)
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
            name="integrity",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed
        )

    def _check_readability(self, file_path: str, lfn: str) -> ValidationIssue:
        """Check if file can be read"""
        try:
            with open(file_path, 'rb') as f:
                # Try to read first 1KB
                f.read(1024)
            return None

        except IOError as e:
            return ValidationIssue(
                severity=Severity.ERROR,
                category=Category.INTEGRITY,
                message=f"Cannot read file: {file_path}",
                location=f"replica:{lfn}",
                explanation=f"I/O error when reading file: {e}",
                impact="Workflow will fail when trying to read this file",
                suggestion="File may be corrupted or locked. Check file integrity.",
                detected_by="rule"
            )

        except Exception as e:
            return ValidationIssue(
                severity=Severity.WARNING,
                category=Category.INTEGRITY,
                message=f"Error checking file: {file_path}",
                location=f"replica:{lfn}",
                explanation=str(e),
                detected_by="rule"
            )

    def _check_csv_format(self, file_path: str, lfn: str) -> ValidationIssue:
        """Check if CSV file is properly formatted"""
        try:
            import pandas as pd

            # Try to read the CSV
            df = pd.read_csv(file_path, nrows=100)  # Only read first 100 rows

            # Check if it has columns
            if len(df.columns) == 0:
                return ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.INTEGRITY,
                    message=f"CSV file has no columns: {file_path}",
                    location=f"replica:{lfn}",
                    suggestion="Check CSV file format",
                    detected_by="rule"
                )

            # Check if it has data
            if len(df) == 0:
                return ValidationIssue(
                    severity=Severity.WARNING,
                    category=Category.INTEGRITY,
                    message=f"CSV file is empty: {file_path}",
                    location=f"replica:{lfn}",
                    suggestion="File has no data rows",
                    detected_by="rule"
                )

            return None

        except pd.errors.EmptyDataError:
            return ValidationIssue(
                severity=Severity.WARNING,
                category=Category.INTEGRITY,
                message=f"CSV file is empty: {file_path}",
                location=f"replica:{lfn}",
                detected_by="rule"
            )

        except Exception as e:
            return ValidationIssue(
                severity=Severity.ERROR,
                category=Category.INTEGRITY,
                message=f"Cannot parse CSV file: {file_path}",
                location=f"replica:{lfn}",
                explanation=f"CSV parsing error: {e}",
                suggestion="Check CSV file format and encoding",
                detected_by="rule"
            )

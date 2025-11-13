"""
Integrity validator - validates data files are readable and not corrupted
Uses pegasus-integrity command when available, falls back to basic checks
"""
import os
import logging
import subprocess
import shutil
from typing import Dict, List, Any, Optional
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext
from integrity_baseline import IntegrityBaseline

logger = logging.getLogger(__name__)


class IntegrityValidator:
    """Validates data integrity and file formats"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('integrity', {})
        self.check_readability = self.config.get('check_file_readability', True)
        self.check_corruption = self.config.get('check_file_corruption', True)
        self.validate_csv = self.config.get('validate_csv_format', True)
        self.max_file_size_mb = self.config.get('max_file_size_mb', 1000)
        self.use_pegasus_integrity = self.config.get('use_pegasus_integrity', True)
        self.use_baseline = self.config.get('use_baseline', True)
        self.baseline_path = self.config.get('baseline_path', '.workflow_integrity.json')
        self.create_baseline_if_missing = self.config.get('create_baseline_if_missing', True)

        # Check if pegasus-integrity is available
        self.pegasus_integrity_available = self._check_pegasus_integrity_available()

        # Initialize baseline manager
        self.baseline_manager = IntegrityBaseline(self.baseline_path)

    def _check_pegasus_integrity_available(self) -> bool:
        """Check if pegasus-integrity command is available"""
        try:
            result = shutil.which('pegasus-integrity')
            if result:
                logger.info("✓ pegasus-integrity command found, will use it for validation")
                return True
            else:
                logger.info("pegasus-integrity command not found, using fallback checks")
                return False
        except Exception as e:
            logger.debug(f"Error checking for pegasus-integrity: {e}")
            return False

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Validate data integrity using pegasus-integrity if available

        Args:
            context: Workflow context with replica catalog

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0
        validated_files = []  # Track which files were validated

        # Method 1: Try pegasus-integrity first if available
        if self.use_pegasus_integrity and self.pegasus_integrity_available and context.workflow_yaml_path:
            logger.info("🔍 Running pegasus-integrity check...")
            pegasus_issues = self._run_pegasus_integrity(context.workflow_yaml_path)
            if pegasus_issues is not None:
                issues.extend(pegasus_issues)
                checks_performed += 1

                if pegasus_issues:
                    logger.info(f"pegasus-integrity found {len(pegasus_issues)} issue(s)")
                else:
                    logger.info("✓ pegasus-integrity validation passed")

                duration = time.time() - start_time
                return ValidatorResult(
                    name="integrity",
                    status=ValidationStatus.FAILED if issues else ValidationStatus.PASSED,
                    duration_seconds=duration,
                    issues=issues,
                    checks_performed=checks_performed,
                    metadata={"method": "pegasus-integrity", "validated_files": validated_files}
                )
            else:
                logger.warning("pegasus-integrity check failed, falling back")

        # Method 2: Try baseline verification if enabled
        if self.use_baseline:
            baseline = self.baseline_manager.load_baseline()

            if baseline:
                # Baseline exists - verify against it
                logger.info(f"📋 Verifying against baseline: {self.baseline_path}")
                baseline_issues = self.baseline_manager.verify_against_baseline(
                    baseline,
                    context.replica_catalog,
                    context.transformation_catalog
                )

                # Convert baseline issues to ValidationIssue objects
                for issue in baseline_issues:
                    severity_map = {
                        'critical': Severity.CRITICAL,
                        'error': Severity.ERROR,
                        'warning': Severity.WARNING,
                        'info': Severity.INFO
                    }
                    severity = severity_map.get(issue['severity'], Severity.WARNING)

                    issues.append(ValidationIssue(
                        severity=severity,
                        category=Category.INTEGRITY,
                        message=issue['message'],
                        location=f"replica:{issue.get('lfn', 'unknown')}",
                        explanation=f"Baseline verification: {issue['type']}",
                        detected_by="baseline"
                    ))

                checks_performed += 1

                if baseline_issues:
                    logger.info(f"📋 Baseline check found {len(baseline_issues)} issue(s)")
                else:
                    logger.info("✓ Baseline verification passed")

                duration = time.time() - start_time
                return ValidatorResult(
                    name="integrity",
                    status=self._determine_status(issues),
                    duration_seconds=duration,
                    issues=issues,
                    checks_performed=checks_performed,
                    metadata={"method": "baseline", "baseline_path": self.baseline_path, "validated_files": validated_files}
                )

            elif self.create_baseline_if_missing and context.workflow_yaml_path:
                # No baseline exists - create one
                logger.info(f"📝 No baseline found, creating new baseline: {self.baseline_path}")
                baseline = self.baseline_manager.generate_baseline(
                    context.workflow_yaml_path,
                    context.replica_catalog,
                    context.transformation_catalog
                )

                # Save baseline
                saved_path = self.baseline_manager.save_baseline(baseline)
                logger.info(f"💾 Baseline created with {baseline['statistics']['total_files']} files")

                # Add info message about baseline creation
                issues.append(ValidationIssue(
                    severity=Severity.INFO,
                    category=Category.INTEGRITY,
                    message=f"Created integrity baseline with {baseline['statistics']['total_files']} files",
                    location="baseline",
                    explanation=f"Baseline saved to: {saved_path}",
                    suggestion="Future validations will verify against this baseline",
                    detected_by="baseline"
                ))

                duration = time.time() - start_time
                return ValidatorResult(
                    name="integrity",
                    status=ValidationStatus.PASSED,
                    duration_seconds=duration,
                    issues=issues,
                    checks_performed=1,
                    metadata={"method": "baseline_created", "baseline_path": saved_path, "statistics": baseline['statistics']}
                )

        # Validate files from replica catalog
        # Handle both 'replicaCatalog.replicas' (Pegasus 5.0+) and 'replicas' (older format)
        replicas = None
        if context.replica_catalog:
            if 'replicaCatalog' in context.replica_catalog and 'replicas' in context.replica_catalog['replicaCatalog']:
                replicas = context.replica_catalog['replicaCatalog']['replicas']
            elif 'replicas' in context.replica_catalog:
                replicas = context.replica_catalog['replicas']

        if replicas:
            for replica in replicas:
                if 'lfn' not in replica:
                    continue

                lfn = replica['lfn']

                # Get PFN - handle both 'pfn' (old format) and 'pfns' (Pegasus 5.0+ array format)
                pfns_to_check = []

                if 'pfn' in replica:
                    pfns_to_check.append(replica['pfn'])
                elif 'pfns' in replica:
                    for pfn_entry in replica['pfns']:
                        if isinstance(pfn_entry, dict) and 'pfn' in pfn_entry:
                            pfns_to_check.append(pfn_entry['pfn'])
                        elif isinstance(pfn_entry, str):
                            pfns_to_check.append(pfn_entry)

                if not pfns_to_check:
                    continue

                # Check each PFN
                for pfn in pfns_to_check:
                    if not os.path.exists(pfn):
                        continue  # Already caught by path validator

                    logger.info(f"Checking integrity: {lfn} -> {pfn}")

                    # Check file size
                    file_size_bytes = 0
                    try:
                        file_size_bytes = os.path.getsize(pfn)
                        size_mb = file_size_bytes / (1024 * 1024)
                        if size_mb > self.max_file_size_mb:
                            logger.info(f"Skipping integrity check for large file: {pfn} ({size_mb:.1f} MB)")
                            continue
                    except Exception as e:
                        logger.debug(f"Could not get file size for {pfn}: {e}")
                        continue

                    # Check readability
                    has_issues = False
                    checks_list = []

                    if self.check_readability:
                        issue = self._check_readability(pfn, lfn)
                        if issue:
                            issues.append(issue)
                            has_issues = True
                        else:
                            checks_list.append("readable")
                        checks_performed += 1

                    # Check format for CSV files
                    if self.validate_csv and pfn.endswith('.csv'):
                        issue = self._check_csv_format(pfn, lfn)
                        if issue:
                            issues.append(issue)
                            has_issues = True
                        else:
                            checks_list.append("valid_csv")
                        checks_performed += 1

                    if not has_issues:
                        logger.info(f"✓ Integrity OK: {lfn}")
                        validated_files.append({
                            "lfn": lfn,
                            "pfn": pfn,
                            "size_bytes": file_size_bytes,
                            "checks": checks_list,
                            "status": "OK"
                        })

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
            checks_performed=checks_performed,
            metadata={"validated_files": validated_files}
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

    def _run_pegasus_integrity(self, workflow_yaml_path: str) -> Optional[List[ValidationIssue]]:
        """
        Run pegasus-integrity command and parse output

        Args:
            workflow_yaml_path: Path to the workflow YAML file

        Returns:
            List of ValidationIssue or None if command failed
        """
        try:
            # Run pegasus-integrity command
            result = subprocess.run(
                ['pegasus-integrity', workflow_yaml_path],
                capture_output=True,
                text=True,
                timeout=60
            )

            issues = []

            # Parse output
            if result.returncode != 0:
                # pegasus-integrity found issues or failed
                output = result.stderr if result.stderr else result.stdout

                if output:
                    # Parse the output line by line
                    for line in output.strip().split('\n'):
                        line = line.strip()
                        if not line:
                            continue

                        # Try to extract meaningful error messages
                        if 'ERROR' in line.upper() or 'FAIL' in line.upper():
                            issues.append(ValidationIssue(
                                severity=Severity.ERROR,
                                category=Category.INTEGRITY,
                                message=f"Integrity check failed: {line}",
                                location="workflow",
                                explanation="pegasus-integrity detected an issue",
                                impact="Workflow may fail during execution",
                                suggestion="Run 'pegasus-integrity' manually for detailed output",
                                detected_by="pegasus-integrity"
                            ))
                        elif 'WARN' in line.upper():
                            issues.append(ValidationIssue(
                                severity=Severity.WARNING,
                                category=Category.INTEGRITY,
                                message=f"Integrity warning: {line}",
                                location="workflow",
                                detected_by="pegasus-integrity"
                            ))
                        elif 'missing' in line.lower() or 'not found' in line.lower():
                            issues.append(ValidationIssue(
                                severity=Severity.ERROR,
                                category=Category.INTEGRITY,
                                message=f"Missing file or resource: {line}",
                                location="replica_catalog",
                                explanation="Referenced file does not exist",
                                impact="Workflow will fail when trying to access this file",
                                suggestion="Ensure all input files exist and are accessible",
                                detected_by="pegasus-integrity"
                            ))
                        elif 'corrupt' in line.lower():
                            issues.append(ValidationIssue(
                                severity=Severity.CRITICAL,
                                category=Category.INTEGRITY,
                                message=f"File corruption detected: {line}",
                                location="replica_catalog",
                                explanation="File appears to be corrupted",
                                impact="Workflow execution will fail",
                                suggestion="Replace corrupted file with a valid copy",
                                detected_by="pegasus-integrity"
                            ))

                    # If no specific issues parsed but command failed, add generic error
                    if not issues and result.returncode != 0:
                        issues.append(ValidationIssue(
                            severity=Severity.ERROR,
                            category=Category.INTEGRITY,
                            message="Integrity check failed",
                            location="workflow",
                            explanation=f"pegasus-integrity exited with code {result.returncode}",
                            suggestion=f"Run 'pegasus-integrity {workflow_yaml_path}' manually to see detailed output",
                            detected_by="pegasus-integrity"
                        ))

            # If returncode is 0, no issues found
            return issues

        except subprocess.TimeoutExpired:
            logger.error("pegasus-integrity command timed out after 60s")
            return None

        except FileNotFoundError:
            logger.error("pegasus-integrity command not found")
            return None

        except Exception as e:
            logger.error(f"Error running pegasus-integrity: {e}")
            return None

    def _determine_status(self, issues: List[ValidationIssue]) -> ValidationStatus:
        """Determine validation status from issues"""
        if not issues:
            return ValidationStatus.PASSED

        has_errors = any(i.severity in [Severity.CRITICAL, Severity.ERROR] for i in issues)
        if has_errors:
            return ValidationStatus.FAILED

        return ValidationStatus.WARNING

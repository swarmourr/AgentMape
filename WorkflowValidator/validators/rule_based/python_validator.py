"""
Python descriptor validator - validates Python workflow descriptors
Checks imports, syntax, structure before generating YAML
"""
import ast
import os
import sys
import logging
from typing import Dict, List, Any, Set, Tuple
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class PythonValidator:
    """Validates Python workflow descriptor files"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('python', {})
        self.check_imports = self.config.get('check_imports', True)
        self.check_syntax = self.config.get('check_syntax', True)
        self.check_structure = self.config.get('check_structure', True)
        self.allowed_imports = self.config.get('allowed_imports', [
            'pegasus', 'Pegasus', 'os', 'sys', 'pathlib', 'typing'
        ])

    def validate(self, python_file_path: str) -> ValidatorResult:
        """
        Validate Python descriptor file

        Args:
            python_file_path: Path to .py file

        Returns:
            Validation result
        """
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0

        # Check 1: File exists
        if not os.path.exists(python_file_path):
            issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                category=Category.SYNTAX,
                message=f"Python descriptor file not found: {python_file_path}",
                location=python_file_path,
                detected_by="rule"
            ))
            return ValidatorResult(
                name="python_descriptor",
                status=ValidationStatus.FAILED,
                duration_seconds=time.time() - start_time,
                issues=issues,
                checks_performed=1
            )

        # Read Python file
        try:
            with open(python_file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
        except Exception as e:
            issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                category=Category.SYNTAX,
                message=f"Cannot read Python file: {e}",
                location=python_file_path,
                detected_by="rule"
            ))
            return ValidatorResult(
                name="python_descriptor",
                status=ValidationStatus.FAILED,
                duration_seconds=time.time() - start_time,
                issues=issues,
                checks_performed=1
            )

        # Check 2: Python syntax
        if self.check_syntax:
            syntax_issues = self._validate_syntax(source_code, python_file_path)
            issues.extend(syntax_issues)
            checks_performed += 1

            # If syntax errors, stop here
            if any(i.severity == Severity.CRITICAL for i in syntax_issues):
                return ValidatorResult(
                    name="python_descriptor",
                    status=ValidationStatus.FAILED,
                    duration_seconds=time.time() - start_time,
                    issues=issues,
                    checks_performed=checks_performed
                )

        # Parse AST for further checks
        try:
            tree = ast.parse(source_code, filename=python_file_path)
        except SyntaxError as e:
            # Should have been caught above, but just in case
            issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                category=Category.SYNTAX,
                message=f"Python syntax error: {e.msg}",
                location=f"{python_file_path}:{e.lineno}",
                detected_by="rule"
            ))
            return ValidatorResult(
                name="python_descriptor",
                status=ValidationStatus.FAILED,
                duration_seconds=time.time() - start_time,
                issues=issues,
                checks_performed=checks_performed
            )

        # Check 3: Imports validation
        if self.check_imports:
            import_issues = self._validate_imports(tree, python_file_path)
            issues.extend(import_issues)
            checks_performed += 1

        # Check 4: Structure validation
        if self.check_structure:
            structure_issues = self._validate_structure(tree, python_file_path)
            issues.extend(structure_issues)
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
            name="python_descriptor",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed
        )

    def _validate_syntax(self, source_code: str, file_path: str) -> List[ValidationIssue]:
        """Validate Python syntax"""
        issues = []

        try:
            compile(source_code, file_path, 'exec')
        except SyntaxError as e:
            issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                category=Category.SYNTAX,
                message=f"Python syntax error: {e.msg}",
                location=f"{file_path}:{e.lineno}:{e.offset}",
                explanation=f"Invalid Python syntax at line {e.lineno}",
                suggestion=f"Fix syntax error: {e.text.strip() if e.text else 'Check line'}",
                detected_by="rule"
            ))
        except Exception as e:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                category=Category.SYNTAX,
                message=f"Python compilation error: {str(e)}",
                location=file_path,
                detected_by="rule"
            ))

        return issues

    def _validate_imports(self, tree: ast.AST, file_path: str) -> List[ValidationIssue]:
        """Validate import statements"""
        issues = []
        imported_modules = set()
        dangerous_imports = {'subprocess', 'os.system', 'eval', 'exec', '__import__'}

        for node in ast.walk(tree):
            # Check 'import module'
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    imported_modules.add(module_name)

                    # Check for dangerous imports
                    if module_name in dangerous_imports:
                        issues.append(ValidationIssue(
                            severity=Severity.WARNING,
                            category=Category.SECURITY,
                            message=f"Potentially dangerous import: {module_name}",
                            location=f"{file_path}:{node.lineno}",
                            explanation=f"Import '{module_name}' can be used for unsafe operations",
                            suggestion="Ensure this import is necessary and used safely",
                            detected_by="rule"
                        ))

            # Check 'from module import ...'
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module if node.module else ''
                imported_modules.add(module_name)

                # Check for dangerous imports
                for alias in node.names:
                    full_name = f"{module_name}.{alias.name}" if module_name else alias.name
                    if alias.name in dangerous_imports or full_name in dangerous_imports:
                        issues.append(ValidationIssue(
                            severity=Severity.WARNING,
                            category=Category.SECURITY,
                            message=f"Potentially dangerous import: {full_name}",
                            location=f"{file_path}:{node.lineno}",
                            suggestion="Review security implications of this import",
                            detected_by="rule"
                        ))

        # Check if required imports are present
        required_imports = ['pegasus', 'Pegasus']
        has_pegasus = any(imp in str(imported_modules) for imp in required_imports)

        if not has_pegasus:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                message="No Pegasus imports found",
                location=file_path,
                explanation="Expected to find Pegasus-related imports for workflow definition",
                suggestion="Add: from Pegasus.DAX3 import * or similar Pegasus imports",
                detected_by="rule"
            ))

        return issues

    def _validate_structure(self, tree: ast.AST, file_path: str) -> List[ValidationIssue]:
        """Validate Python workflow structure"""
        issues = []

        # Look for workflow definition patterns
        has_workflow_def = False
        has_jobs = False
        has_transformations = False

        # Common workflow patterns to look for
        workflow_keywords = {'workflow', 'dax', 'jobs', 'transformations', 'catalog'}

        for node in ast.walk(tree):
            # Check for variable assignments
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id.lower()
                        if any(kw in name for kw in workflow_keywords):
                            has_workflow_def = True
                            if 'job' in name:
                                has_jobs = True
                            if 'transform' in name:
                                has_transformations = True

            # Check for function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    attr_name = node.func.attr.lower()
                    if any(kw in attr_name for kw in workflow_keywords):
                        has_workflow_def = True

        # Validate structure
        if not has_workflow_def:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                message="No workflow definition pattern found",
                location=file_path,
                explanation="Expected to find workflow, jobs, or transformation definitions",
                suggestion="Define workflow components using Pegasus API or dictionary structures",
                detected_by="rule"
            ))

        return issues

    def extract_workflow_info(self, python_file_path: str) -> Dict[str, Any]:
        """
        Extract workflow information from Python descriptor

        Returns:
            Dictionary with workflow metadata
        """
        metadata = {
            'imports': [],
            'variables': {},
            'functions': [],
            'classes': []
        }

        try:
            with open(python_file_path, 'r') as f:
                source_code = f.read()

            tree = ast.parse(source_code, filename=python_file_path)

            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        metadata['imports'].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module if node.module else ''
                    for alias in node.names:
                        metadata['imports'].append(f"{module}.{alias.name}")

            # Extract top-level assignments
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            metadata['variables'][target.id] = ast.unparse(node.value)

                elif isinstance(node, ast.FunctionDef):
                    metadata['functions'].append(node.name)

                elif isinstance(node, ast.ClassDef):
                    metadata['classes'].append(node.name)

        except Exception as e:
            logger.error(f"Failed to extract workflow info: {e}")

        return metadata

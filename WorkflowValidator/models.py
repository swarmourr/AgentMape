"""
Data models for validation results and reports
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import json


class Severity(Enum):
    """Error severity levels"""
    CRITICAL = "critical"  # Workflow will definitely fail
    ERROR = "error"        # Likely to fail
    WARNING = "warning"    # May cause issues
    INFO = "info"          # Suggestion for improvement


class Category(Enum):
    """Error categories"""
    SYNTAX = "syntax"
    STRUCTURE = "structure"
    DEPENDENCIES = "dependencies"
    PATHS = "paths"
    INTEGRITY = "integrity"
    RESOURCES = "resources"
    SECURITY = "security"
    DATA_QUALITY = "data_quality"
    CODE = "code"
    PERFORMANCE = "performance"


class ValidationStatus(Enum):
    """Overall validation status"""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class ValidationIssue:
    """Represents a single validation issue"""
    severity: Severity
    category: Category
    message: str
    location: Optional[str] = None  # e.g., "workflow.yml:45" or "job:train_model"
    explanation: Optional[str] = None  # Detailed explanation
    impact: Optional[str] = None  # What happens if not fixed
    suggestion: Optional[str] = None  # How to fix
    code_snippet: Optional[str] = None  # Code example of fix
    detected_by: str = "rule"  # "rule" or "llm"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "location": self.location,
            "explanation": self.explanation,
            "impact": self.impact,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
            "detected_by": self.detected_by
        }


@dataclass
class ValidatorResult:
    """Result from a single validator"""
    name: str  # Validator name
    status: ValidationStatus
    duration_seconds: float
    issues: List[ValidationIssue] = field(default_factory=list)
    checks_performed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        """Count of critical and error issues"""
        return len([i for i in self.issues
                   if i.severity in [Severity.CRITICAL, Severity.ERROR]])

    @property
    def warning_count(self) -> int:
        """Count of warnings"""
        return len([i for i in self.issues if i.severity == Severity.WARNING])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "duration_seconds": round(self.duration_seconds, 2),
            "checks_performed": self.checks_performed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": self.metadata
        }


@dataclass
class ValidationReport:
    """Complete validation report"""
    workflow_path: str
    overall_status: ValidationStatus
    validator_results: List[ValidatorResult]
    total_duration_seconds: float
    timestamp: str
    validator_version: str = "1.0.0"

    @property
    def total_issues(self) -> int:
        """Total number of issues across all validators"""
        return sum(len(result.issues) for result in self.validator_results)

    @property
    def total_errors(self) -> int:
        """Total critical and error issues"""
        return sum(result.error_count for result in self.validator_results)

    @property
    def total_warnings(self) -> int:
        """Total warnings"""
        return sum(result.warning_count for result in self.validator_results)

    @property
    def critical_issues(self) -> List[ValidationIssue]:
        """Get all critical issues"""
        issues = []
        for result in self.validator_results:
            issues.extend([i for i in result.issues if i.severity == Severity.CRITICAL])
        return issues

    @property
    def all_issues(self) -> List[ValidationIssue]:
        """Get all issues from all validators"""
        issues = []
        for result in self.validator_results:
            issues.extend(result.issues)
        return issues

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "workflow_path": self.workflow_path,
            "timestamp": self.timestamp,
            "validator_version": self.validator_version,
            "overall_status": self.overall_status.value,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "summary": {
                "total_issues": self.total_issues,
                "total_errors": self.total_errors,
                "total_warnings": self.total_warnings,
                "validators_run": len(self.validator_results)
            },
            "validators": [result.to_dict() for result in self.validator_results]
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class WorkflowContext:
    """Context about the workflow being validated"""
    workflow_yaml_path: str
    workflow_yaml_content: Optional[Dict[str, Any]] = None
    transformation_catalog_path: Optional[str] = None
    transformation_catalog: Optional[Dict[str, Any]] = None
    replica_catalog_path: Optional[str] = None
    replica_catalog: Optional[Dict[str, Any]] = None
    transformation_scripts: Dict[str, str] = field(default_factory=dict)  # name -> content
    data_samples: Dict[str, Any] = field(default_factory=dict)  # file -> sample data
    metadata: Dict[str, Any] = field(default_factory=dict)

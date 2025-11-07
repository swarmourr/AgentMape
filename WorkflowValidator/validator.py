"""
Main workflow validator orchestrator
Supports both YAML validation and Python descriptor generation + validation
"""
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from models import ValidationReport, ValidationStatus, WorkflowContext
from validators.rule_based import StructureValidator, PathValidator, IntegrityValidator
from validators.rule_based.python_validator import PythonValidator
from validators.llm_enhanced import LLMValidator
from report_generator import ReportGenerator
from yaml_generator import YAMLGenerator

logger = logging.getLogger(__name__)


class WorkflowValidator:
    """
    Main workflow validator that orchestrates all validation checks

    Supports two input types:
    1. YAML files (.yml): Direct validation
    2. Python descriptors (.py): Generate YAML then validate
    """

    def __init__(self, config_path: str = None):
        """
        Initialize validator

        Args:
            config_path: Path to validator_config.json. If None, uses default config.
        """
        # Load configuration (JSON like other components)
        if config_path is None:
            config_path = Path(__file__).parent / 'validator_config.json'

        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Initialize validators
        self.structure_validator = StructureValidator(self.config)
        self.path_validator = PathValidator(self.config)
        self.integrity_validator = IntegrityValidator(self.config)
        self.python_validator = PythonValidator(self.config)
        self.llm_validator = LLMValidator(self.config)

        # Initialize YAML generator
        self.yaml_generator = YAMLGenerator(self.config)
        self.yaml_generator.set_llm_backend(self.llm_validator.backend)

        # Initialize report generator
        self.report_generator = ReportGenerator(self.config)

        # Configure logging
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging based on configuration"""
        log_level = self.config.get('log_level', 'INFO')

        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def validate(
        self,
        workflow_path: str,
        transformation_catalog_path: Optional[str] = None,
        replica_catalog_path: Optional[str] = None,
        level: str = 'standard',
        mode: str = 'hybrid',
        output_yaml_path: Optional[str] = None
    ) -> Tuple[ValidationReport, Optional[str]]:
        """
        Validate a Pegasus workflow

        Args:
            workflow_path: Path to workflow YAML file
            transformation_catalog_path: Path to transformation catalog (optional)
            replica_catalog_path: Path to replica catalog (optional)
            level: Validation level ('quick', 'standard', 'full')

        Returns:
            ValidationReport with all results
        """
        import time
        start_time = time.time()

        logger.info(f"Starting validation of workflow: {workflow_path}")
        logger.info(f"Validation level: {level}")

        # Build workflow context
        context = self._build_context(
            workflow_path,
            transformation_catalog_path,
            replica_catalog_path
        )

        # Determine which validators to run based on level
        validation_config = self.config.get('validation_levels', {}).get(level, {})
        if not validation_config:
            logger.warning(f"Unknown validation level '{level}', using 'standard'")
            validation_config = self.config.get('validation_levels', {}).get('standard', {})

        validator_names = validation_config.get('validators', ['syntax', 'required_fields', 'dependencies', 'paths'])
        use_llm = validation_config.get('use_llm', False)
        llm_checks = validation_config.get('llm_checks', [])

        # Run validators
        results = []

        # Always run structure validator (includes syntax, required fields, dependencies)
        if any(v in validator_names for v in ['syntax', 'required_fields', 'dependencies']):
            logger.info("Running structure validator...")
            result = self.structure_validator.validate(context)
            results.append(result)

        # Run path validator
        if 'paths' in validator_names:
            logger.info("Running path validator...")
            result = self.path_validator.validate(context)
            results.append(result)

        # Run integrity validator
        if 'integrity' in validator_names:
            logger.info("Running integrity validator...")
            result = self.integrity_validator.validate(context)
            results.append(result)

        # Run LLM validator if enabled
        if use_llm and llm_checks:
            logger.info("Running LLM validator...")
            result = self.llm_validator.validate(context, checks=llm_checks)
            results.append(result)

        # Determine overall status
        has_errors = any(r.status == ValidationStatus.FAILED for r in results)
        has_warnings = any(r.status == ValidationStatus.WARNING for r in results)

        if has_errors:
            overall_status = ValidationStatus.FAILED
        elif has_warnings:
            overall_status = ValidationStatus.WARNING
        else:
            overall_status = ValidationStatus.PASSED

        # Build report
        total_duration = time.time() - start_time

        report = ValidationReport(
            workflow_path=workflow_path,
            overall_status=overall_status,
            validator_results=results,
            total_duration_seconds=total_duration,
            timestamp=datetime.now().isoformat()
        )

        logger.info(f"Validation complete: {overall_status.value} ({total_duration:.2f}s)")

        return report

    def _build_context(
        self,
        workflow_path: str,
        tc_path: Optional[str],
        rc_path: Optional[str]
    ) -> WorkflowContext:
        """Build workflow context by loading all necessary files"""

        context = WorkflowContext(
            workflow_yaml_path=workflow_path
        )

        # Load workflow YAML
        try:
            with open(workflow_path, 'r') as f:
                context.workflow_yaml_content = yaml.safe_load(f)
            logger.debug("Loaded workflow YAML")
        except Exception as e:
            logger.error(f"Failed to load workflow YAML: {e}")

        # Load transformation catalog
        if tc_path:
            context.transformation_catalog_path = tc_path
            try:
                with open(tc_path, 'r') as f:
                    context.transformation_catalog = yaml.safe_load(f)
                logger.debug("Loaded transformation catalog")
            except Exception as e:
                logger.warning(f"Failed to load transformation catalog: {e}")
        else:
            # Try to find transformation catalog in workflow
            if context.workflow_yaml_content and 'transformations' in context.workflow_yaml_content:
                context.transformation_catalog = context.workflow_yaml_content
                logger.debug("Using transformations from workflow YAML")

        # Load replica catalog
        if rc_path:
            context.replica_catalog_path = rc_path
            try:
                with open(rc_path, 'r') as f:
                    context.replica_catalog = yaml.safe_load(f)
                logger.debug("Loaded replica catalog")
            except Exception as e:
                logger.warning(f"Failed to load replica catalog: {e}")
        else:
            # Try to find replica catalog in workflow
            if context.workflow_yaml_content and 'replicas' in context.workflow_yaml_content:
                context.replica_catalog = context.workflow_yaml_content
                logger.debug("Using replicas from workflow YAML")

        return context

    def generate_report(self, report: ValidationReport, format: str = 'terminal') -> str:
        """
        Generate formatted report

        Args:
            report: ValidationReport
            format: Output format ('terminal', 'json', 'html')

        Returns:
            Formatted report string
        """
        return self.report_generator.generate(report, format=format)

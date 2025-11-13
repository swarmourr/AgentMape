"""
LLM Multi-Prompt Validator - Uses LLM for ALL validation steps with separate prompts
"""
import logging
import time
from typing import Dict, List, Any
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class LLMMultiPromptValidator:
    """Uses LLM with multiple prompts for comprehensive validation"""

    def __init__(self, llm_backend, config: Dict[str, Any]):
        self.llm_backend = llm_backend
        self.config = config.get('llm_backend', {})
        self.temperature = self.config.get('temperature', 0.1)
        self.max_tokens = self.config.get('max_tokens', 200000)
        self.chunk_size = 50000  # Characters per chunk for large workflows

    def validate(self, context: WorkflowContext) -> List[ValidatorResult]:
        """
        Run multiple LLM prompts for validation

        Returns:
            List of ValidatorResult (one per prompt)
        """
        results = []

        # PROMPT 1: Structure validation
        logger.info("🤖 [LLM PROMPT 1/7] Validating workflow structure...")
        start = time.time()
        result = self._validate_structure(context)
        results.append(result)
        logger.info(f"✓ LLM structure validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 2: Job dependencies
        logger.info("🤖 [LLM PROMPT 2/7] Validating job dependencies...")
        start = time.time()
        result = self._validate_dependencies(context)
        results.append(result)
        logger.info(f"✓ LLM dependency validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 3: File paths
        logger.info("🤖 [LLM PROMPT 3/7] Validating file paths...")
        start = time.time()
        result = self._validate_paths(context)
        results.append(result)
        logger.info(f"✓ LLM path validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 4: Resource requirements
        logger.info("🤖 [LLM PROMPT 4/7] Validating resource requirements...")
        start = time.time()
        result = self._validate_resources(context)
        results.append(result)
        logger.info(f"✓ LLM resource validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 5: Data integrity
        logger.info("🤖 [LLM PROMPT 5/7] Validating data integrity...")
        start = time.time()
        result = self._validate_integrity(context)
        results.append(result)
        logger.info(f"✓ LLM integrity validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 6: Security checks
        logger.info("🤖 [LLM PROMPT 6/7] Running security checks...")
        start = time.time()
        result = self._validate_security(context)
        results.append(result)
        logger.info(f"✓ LLM security validation: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        # PROMPT 7: Best practices
        logger.info("🤖 [LLM PROMPT 7/7] Checking best practices...")
        start = time.time()
        result = self._validate_best_practices(context)
        results.append(result)
        logger.info(f"✓ LLM best practices check: {time.time() - start:.3f}s")
        logger.info("-" * 80)

        return results

    def _validate_structure(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates workflow structure"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content
        if not workflow:
            return self._empty_result("llm_structure")

        workflow_str = str(workflow)

        # Check if workflow is too large for single prompt
        if len(workflow_str) > self.chunk_size:
            logger.info(f"📦 Large workflow detected ({len(workflow_str)} chars), analyzing in chunks...")
            return self._validate_structure_chunked(context, workflow_str, start_time)

        prompt = f"""You are an expert Pegasus Workflow Management System validator with deep knowledge of:
- Pegasus 5.0+ architecture and best practices
- Scientific workflow design patterns
- Distributed computing environments
- Data provenance and reproducibility

Analyze this COMPLETE Pegasus workflow and provide a comprehensive validation report:

```yaml
{workflow_str}
```

Your analysis should cover:

1. STRUCTURAL INTEGRITY:
   - Verify all required fields (name, jobs, pegasus version)
   - Validate job definitions (name, transformation, arguments, uses)
   - Check catalog structure (transformationCatalog, replicaCatalog format)
   - Ensure Pegasus 5.0+ format compliance

2. SEMANTIC CORRECTNESS:
   - Do jobs reference valid transformations?
   - Are input files declared in replica catalog?
   - Are arguments properly structured?
   - Are there any logical inconsistencies?

3. DESIGN QUALITY:
   - Is the workflow well-organized?
   - Are naming conventions clear and consistent?
   - Is there proper documentation?
   - Are there any code smells or anti-patterns?

If you need MORE INFORMATION to complete your analysis, include in your response:
- "needs_clarification": true
- "questions": ["specific question 1", "specific question 2"]

Return JSON format:
{{
  "analysis_summary": "Brief overview of your findings",
  "issues": [
    {{
      "severity": "critical|error|warning|info",
      "category": "structure|semantics|design|performance|security",
      "message": "Clear description of the issue",
      "location": "Exact location (e.g., 'job:TrainModel', 'line 45')",
      "explanation": "Why this is a problem",
      "impact": "What will happen if not fixed",
      "suggestion": "How to fix it with specific code example if possible"
    }}
  ],
  "strengths": ["Things done well in this workflow"],
  "needs_clarification": false,
  "questions": []
}}"""

        response = self._call_llm_and_log(prompt, "llm_structure")
        issues = self._parse_llm_response(response, "llm_structure")

        return ValidatorResult(
            name="llm_structure",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_dependencies(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates job dependencies"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content
        if not workflow or 'jobs' not in workflow:
            return self._empty_result("llm_dependencies")

        jobs = workflow.get('jobs', [])

        prompt = f"""You are a workflow dependency analysis expert specializing in:
- Directed Acyclic Graph (DAG) theory
- Parallel workflow execution patterns
- Data flow dependencies
- Resource scheduling optimization

Perform a DEEP ANALYSIS of job dependencies in this workflow:

```python
{str(jobs)}
```

Your comprehensive analysis must include:

1. GRAPH TOPOLOGY:
   - Is this a valid DAG (no cycles)?
   - What is the critical path?
   - What is the maximum parallelism?
   - Are there bottleneck jobs?

2. DEPENDENCY CORRECTNESS:
   - Do all parent jobs exist?
   - Are there missing dependencies (jobs that should depend on each other)?
   - Are there unnecessary dependencies (over-constrained)?
   - Are there orphaned jobs with no connections?

3. EXECUTION EFFICIENCY:
   - Can jobs be parallelized better?
   - Are dependencies properly ordered for data flow?
   - Are there opportunities to reduce critical path length?

4. DATA FLOW VALIDATION:
   - Do child jobs correctly wait for parent outputs?
   - Are there potential race conditions?

If you need MORE DETAILS about:
- Execution environment
- Data sizes
- Job runtime estimates
- Resource availability

Set "needs_clarification": true and ask specific questions.

Return JSON:
{{
  "analysis_summary": "Overview of dependency graph analysis",
  "graph_metrics": {{
    "total_jobs": <number>,
    "max_depth": <number>,
    "max_parallelism": <number>,
    "critical_path_jobs": ["job1", "job2"]
  }},
  "issues": [
    {{
      "severity": "critical|error|warning|info",
      "category": "cycle|missing_parent|orphaned|optimization|data_flow",
      "message": "Issue description",
      "location": "job:name",
      "explanation": "Why this matters",
      "impact": "Effect on workflow execution",
      "suggestion": "How to fix with example"
    }}
  ],
  "optimization_suggestions": ["Specific recommendations"],
  "needs_clarification": false,
  "questions": []
}}"""

        response = self._call_llm_and_log(prompt, "llm_dependencies")
        issues = self._parse_llm_response(response, "llm_dependencies")

        return ValidatorResult(
            name="llm_dependencies",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_paths(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates file paths"""
        import time
        start_time = time.time()

        tc = context.transformation_catalog
        rc = context.replica_catalog

        prompt = f"""You are a filesystem and path validation expert with expertise in:
- POSIX and Unix filesystem standards
- Distributed file systems (NFS, Lustre, GPFS)
- Storage best practices for HPC environments
- Path security and access control

Perform COMPREHENSIVE PATH ANALYSIS of these catalogs:

TRANSFORMATION CATALOG:
```yaml
{str(tc) if tc else 'None'}
```

REPLICA CATALOG:
```yaml
{str(rc) if rc else 'None'}
```

Your analysis must cover:

1. PATH VALIDITY:
   - Are paths well-formed and valid?
   - Absolute vs relative paths appropriateness
   - Path separator consistency
   - Special characters handling

2. ACCESSIBILITY:
   - Will paths be accessible from execution environment?
   - Are there potential permission issues?
   - Cross-platform compatibility concerns?
   - Network path vs local path considerations

3. SECURITY:
   - Are there paths that traverse sensitive directories?
   - Hardcoded paths that should be configurable?
   - Potential path injection vulnerabilities?

4. BEST PRACTICES:
   - Consistent path structure?
   - Use of environment variables where appropriate?
   - Proper use of workflow-relative paths?

If you need MORE INFORMATION about:
- Execution environment (cluster, cloud, local)
- Filesystem type and mount points
- Security policies
- User permissions

Set "needs_clarification": true.

Return JSON:
{{
  "analysis_summary": "Path analysis overview",
  "path_statistics": {{
    "total_paths": <number>,
    "absolute_paths": <number>,
    "relative_paths": <number>,
    "network_paths": <number>
  }},
  "issues": [
    {{
      "severity": "critical|error|warning|info",
      "category": "invalid|inaccessible|security|best_practice",
      "message": "Issue description",
      "location": "catalog:item",
      "path": "problematic path",
      "explanation": "Why this is problematic",
      "impact": "Consequences",
      "suggestion": "Recommended fix with example"
    }}
  ],
  "recommendations": ["Path structure improvements"],
  "needs_clarification": false,
  "questions": []
}}"""

        response = self._call_llm_and_log(prompt, "llm_paths")
        issues = self._parse_llm_response(response, "llm_paths")

        return ValidatorResult(
            name="llm_paths",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_resources(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates resource requirements"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content
        if not workflow or 'jobs' not in workflow:
            return self._empty_result("llm_resources")

        jobs = workflow.get('jobs', [])

        prompt = f"""You are a High-Performance Computing (HPC) resource allocation expert with knowledge of:
- Job scheduling systems (HTCondor, Slurm, PBS)
- Memory and CPU allocation strategies
- Resource contention and optimization
- Cost estimation for cloud and HPC resources

Perform DETAILED RESOURCE ANALYSIS for all jobs:

```python
{str(jobs)}
```

Your analysis must evaluate:

1. RESOURCE FEASIBILITY:
   - Are memory requests realistic for the execution environment?
   - Are CPU requests achievable on target systems?
   - Are disk/storage requirements reasonable?
   - Do resource combinations make sense?

2. RESOURCE EFFICIENCY:
   - Are resources over-provisioned (waste)?
   - Are resources under-provisioned (will fail)?
   - Is there opportunity for resource consolidation?
   - Can jobs share resources better?

3. COST IMPLICATIONS:
   - High-cost resource allocations
   - Long-running jobs with expensive resources
   - Opportunities to reduce costs without performance loss

4. SCHEDULING IMPACT:
   - Will these requests cause long queue times?
   - Are there jobs that block others due to large requests?
   - Fair-share policy compliance?

If you need MORE CONTEXT about:
- Available hardware specifications
- Budget constraints
- Queue policies and limits
- Historical job performance data

Set "needs_clarification": true.

Return JSON:
{{
  "analysis_summary": "Resource allocation analysis",
  "resource_totals": {{
    "total_memory_gb": <number>,
    "total_cpus": <number>,
    "peak_concurrent_load": "estimate"
  }},
  "issues": [
    {{
      "severity": "critical|error|warning|info",
      "category": "excessive|insufficient|inefficient|costly",
      "message": "Issue description",
      "location": "job:name",
      "current_allocation": "current resource specs",
      "explanation": "Why this is problematic",
      "impact": "Effect on execution/cost/time",
      "suggestion": "Recommended allocation with justification"
    }}
  ],
  "cost_analysis": "Estimated cost impact if available",
  "optimization_opportunities": ["Specific recommendations"],
  "needs_clarification": false,
  "questions": []
}}"""

        response = self._call_llm_and_log(prompt, "llm_resources")
        issues = self._parse_llm_response(response, "llm_resources")

        return ValidatorResult(
            name="llm_resources",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_integrity(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates data integrity"""
        import time
        start_time = time.time()

        rc = context.replica_catalog

        prompt = f"""You are a data integrity and quality assurance specialist with expertise in:
- Scientific data formats and standards
- Data provenance and lineage
- File format validation
- Data quality assessment methodologies

Perform COMPREHENSIVE DATA INTEGRITY ANALYSIS:

```yaml
{str(rc) if rc else 'None'}
```

Your analysis must include:

1. FORMAT SPECIFICATION:
   - Are file formats clearly specified?
   - Format consistency across related files
   - Compatibility with downstream tools
   - Metadata completeness

2. DATA QUALITY:
   - Size consistency (suspiciously small/large files)
   - Expected vs actual data characteristics
   - Missing or incomplete data indicators
   - Potential corruption signs

3. PROVENANCE & DOCUMENTATION:
   - Is data source documented?
   - Version information present?
   - Checksums or integrity hashes?
   - License and usage rights clear?

4. REPRODUCIBILITY:
   - Can this data be regenerated if lost?
   - Is there backup/redundancy?
   - Are dependencies documented?

If you need MORE INFORMATION about:
- Expected file formats and schemas
- Data generation process
- Quality thresholds
- Domain-specific requirements

Set "needs_clarification": true.

Return JSON:
{{
  "analysis_summary": "Data integrity assessment",
  "data_statistics": {{
    "total_files": <number>,
    "total_size_estimate": "approximate size",
    "format_diversity": ["list of formats"]
  }},
  "issues": [
    {{
      "severity": "critical|error|warning|info",
      "category": "format|quality|provenance|reproducibility",
      "message": "Issue description",
      "location": "replica:lfn",
      "file_details": "relevant file information",
      "explanation": "Why this matters for data integrity",
      "impact": "Risk to workflow reliability",
      "suggestion": "How to improve with example"
    }}
  ],
  "quality_score": "Overall data quality assessment",
  "recommendations": ["Data management improvements"],
  "needs_clarification": false,
  "questions": []
}}"""

        response = self._call_llm_and_log(prompt, "llm_integrity")
        issues = self._parse_llm_response(response, "llm_integrity")

        return ValidatorResult(
            name="llm_integrity",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_security(self, context: WorkflowContext) -> ValidatorResult:
        """LLM validates security"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content

        prompt = f"""You are a cybersecurity expert specializing in:
- Workflow security and attack vectors
- Secure coding practices for scientific computing
- Data privacy and compliance (GDPR, HIPAA, etc.)
- Access control and authentication
- OWASP Top 10 vulnerabilities

Perform THOROUGH SECURITY AUDIT of this workflow:

```yaml
{str(workflow) if workflow else 'None'}
```

Your security assessment must cover:

1. CREDENTIAL & SECRET MANAGEMENT:
   - Hardcoded passwords, API keys, tokens
   - Credentials in plain text
   - Insecure credential storage
   - Missing encryption for sensitive data

2. INJECTION VULNERABILITIES:
   - Command injection risks in arguments
   - Path traversal vulnerabilities
   - SQL injection (if databases involved)
   - Script injection possibilities

3. ACCESS CONTROL:
   - Overly permissive file permissions
   - Missing authentication mechanisms
   - Privilege escalation risks
   - Unauthorized access opportunities

4. DATA SECURITY:
   - Sensitive data exposure
   - Insecure data transmission
   - Missing data validation/sanitization
   - PII (Personal Identifiable Information) handling

5. SUPPLY CHAIN SECURITY:
   - Untrusted data sources
   - Unverified external dependencies
   - Potential malicious inputs

6. COMPLIANCE & PRIVACY:
   - Regulatory compliance issues
   - Data retention policies
   - Audit trail requirements

If you need MORE CONTEXT about:
- Security policies and requirements
- Compliance frameworks (HIPAA, GDPR, etc.)
- Threat model and risk appetite
- Execution environment security

Set "needs_clarification": true.

Return JSON:
{{
  "analysis_summary": "Security posture assessment",
  "risk_level": "low|medium|high|critical",
  "compliance_status": "compliant|needs_review|non_compliant",
  "issues": [
    {{
      "severity": "critical|error|warning|info",
      "category": "credentials|injection|access_control|data_security|compliance",
      "message": "Security issue description",
      "location": "exact location",
      "vulnerability_type": "specific CVE or vulnerability class",
      "explanation": "Why this is a security risk",
      "exploit_scenario": "How this could be exploited",
      "impact": "Potential damage",
      "suggestion": "How to fix securely with code example"
    }}
  ],
  "security_recommendations": ["Prioritized security improvements"],
  "needs_clarification": false,
  "questions": []
}}"""

        response = self._call_llm_and_log(prompt, "llm_security")
        issues = self._parse_llm_response(response, "llm_security")

        return ValidatorResult(
            name="llm_security",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_best_practices(self, context: WorkflowContext) -> ValidatorResult:
        """LLM checks best practices"""
        import time
        start_time = time.time()

        workflow = context.workflow_yaml_content

        prompt = f"""You are a Pegasus workflow architect and software engineering best practices expert with knowledge of:
- Clean code principles (SOLID, DRY, KISS)
- Software design patterns
- Scientific workflow design methodologies
- Performance optimization strategies
- Maintainability and technical debt assessment

Perform COMPREHENSIVE BEST PRACTICES REVIEW:

```yaml
{str(workflow) if workflow else 'None'}
```

Your review must evaluate:

1. CODE QUALITY:
   - Clear and consistent naming conventions
   - Proper documentation and comments
   - Code organization and modularity
   - Readability and maintainability

2. DESIGN PATTERNS:
   - Proper use of Pegasus features
   - Workflow composition patterns
   - Reusability and parameterization
   - Separation of concerns

3. PERFORMANCE:
   - Efficient job structuring
   - Optimal parallelization
   - Resource utilization
   - Bottleneck identification

4. MAINTAINABILITY:
   - Version control readiness
   - Configuration management
   - Testing and validation approach
   - Error handling and recovery

5. DOCUMENTATION:
   - Workflow purpose and scope
   - Input/output specifications
   - Dependencies documented
   - Usage examples

6. REPRODUCIBILITY:
   - Deterministic execution
   - Environment specifications
   - Data versioning
   - Provenance tracking

7. COLLABORATION:
   - Team workflow standards
   - Naming conventions consistency
   - Modularity for team development

If you need MORE CONTEXT about:
- Team size and structure
- Project lifecycle stage
- Target users (developers vs end-users)
- Existing standards or style guides

Set "needs_clarification": true.

Return JSON:
{{
  "analysis_summary": "Overall quality assessment",
  "quality_score": {{
    "code_quality": "score 1-10",
    "design": "score 1-10",
    "performance": "score 1-10",
    "maintainability": "score 1-10",
    "documentation": "score 1-10"
  }},
  "issues": [
    {{
      "severity": "warning|info",
      "category": "naming|documentation|design|performance|maintainability",
      "message": "Improvement suggestion",
      "location": "specific location",
      "current_practice": "what's currently done",
      "explanation": "Why current approach could be better",
      "best_practice": "Recommended approach",
      "suggestion": "Specific improvement with code example",
      "effort": "low|medium|high",
      "impact": "low|medium|high"
    }}
  ],
  "strengths": ["Things done well - positive reinforcement"],
  "quick_wins": ["Easy improvements with high impact"],
  "long_term_improvements": ["Strategic improvements"],
  "needs_clarification": false,
  "questions": []
}}"""

        response = self._call_llm_and_log(prompt, "llm_best_practices")
        issues = self._parse_llm_response(response, "llm_best_practices")

        return ValidatorResult(
            name="llm_best_practices",
            status=self._determine_status(issues),
            duration_seconds=time.time() - start_time,
            issues=issues,
            checks_performed=1,
            metadata={"llm_response": response}
        )

    def _validate_structure_chunked(self, context: WorkflowContext, workflow_str: str, start_time: float) -> ValidatorResult:
        """Validate large workflow in chunks"""
        import time

        all_issues = []
        chunks = []

        # Split into chunks
        for i in range(0, len(workflow_str), self.chunk_size):
            chunk = workflow_str[i:i + self.chunk_size]
            chunks.append(chunk)

        logger.info(f"📦 Sending workflow in {len(chunks)} chunks...")

        # Validate each chunk
        for idx, chunk in enumerate(chunks):
            logger.info(f"🔍 Analyzing chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)...")

            prompt = f"""Analyze this part ({idx + 1}/{len(chunks)}) of a Pegasus workflow:

```yaml
{chunk}
```

Check for:
1. Required fields (name, jobs)
2. Job structure issues
3. Catalog structure issues
4. Pegasus 5.0+ format compliance

Return JSON:
{{
  "issues": [
    {{"severity": "error|warning", "message": "description", "location": "where"}}
  ]
}}"""

            response = self._call_llm_and_log(prompt, f"llm_structure_chunk_{idx+1}")
            issues = self._parse_llm_response(response, "llm_structure")
            all_issues.extend(issues)

        logger.info(f"✓ Analyzed {len(chunks)} chunks, found {len(all_issues)} issues")

        return ValidatorResult(
            name="llm_structure",
            status=self._determine_status(all_issues),
            duration_seconds=time.time() - start_time,
            issues=all_issues,
            checks_performed=len(chunks),
            metadata={"chunks": len(chunks), "total_chars": len(workflow_str)}
        )

    def _call_llm_and_log(self, prompt: str, validator_name: str) -> str:
        """Call LLM and log the response"""
        response = self.llm_backend.generate(prompt, temperature=self.temperature, max_tokens=self.max_tokens)

        # Log the COMPLETE LLM response (no truncation)
        logger.info("📝 LLM Analysis:")
        logger.info(response)
        logger.info("")

        return response

    def _parse_llm_response(self, response: str, validator_name: str) -> List[ValidationIssue]:
        """Parse LLM JSON response into ValidationIssues"""
        import json
        import re

        issues = []

        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                for issue in data.get('issues', []):
                    severity_str = issue.get('severity', 'warning').lower()
                    severity_map = {
                        'critical': Severity.CRITICAL,
                        'error': Severity.ERROR,
                        'warning': Severity.WARNING,
                        'info': Severity.INFO
                    }
                    severity = severity_map.get(severity_str, Severity.WARNING)

                    issues.append(ValidationIssue(
                        severity=severity,
                        category=Category.STRUCTURE,
                        message=issue.get('message', 'Issue detected by LLM'),
                        location=issue.get('location'),
                        detected_by="llm"
                    ))
        except Exception as e:
            logger.warning(f"Failed to parse LLM response for {validator_name}: {e}")

        return issues

    def _determine_status(self, issues: List[ValidationIssue]) -> ValidationStatus:
        """Determine status from issues"""
        if not issues:
            return ValidationStatus.PASSED

        has_errors = any(i.severity in [Severity.CRITICAL, Severity.ERROR] for i in issues)
        if has_errors:
            return ValidationStatus.FAILED

        return ValidationStatus.WARNING

    def _empty_result(self, name: str) -> ValidatorResult:
        """Return empty result"""
        return ValidatorResult(
            name=name,
            status=ValidationStatus.PASSED,
            duration_seconds=0,
            issues=[],
            checks_performed=0
        )

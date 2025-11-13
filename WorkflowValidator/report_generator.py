"""
Report generator for validation results
"""
import json
from typing import Dict, Any
from models import ValidationReport, Severity, ValidationStatus
from llm_response_aggregator import LLMResponseAggregator


class ReportGenerator:
    """Generates validation reports in different formats"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('output_config', {})
        self.use_colors = self.config.get('use_colors', True)
        self.verbosity = self.config.get('verbosity', 'brief')  # brief, standard, detailed
        self.show_suggestions = self.config.get('show_suggestions', True)
        self.llm_report_mode = self.config.get('llm_report_mode', 'consolidated')
        self.show_raw_llm_responses = self.config.get('show_raw_llm_responses', False)
        self.max_issues_shown = self.config.get('max_issues_shown', 10)
        self.max_recommendations = self.config.get('max_recommendations', 5)
        self.show_validator_details = self.config.get('show_validator_details', False)
        self.show_strengths = self.config.get('show_strengths', True)

    def generate(self, report: ValidationReport, format: str = None) -> str:
        """
        Generate report in specified format

        Args:
            report: ValidationReport object
            format: Output format ('terminal', 'json', 'html', 'html-interactive')

        Returns:
            Formatted report string
        """
        if format is None:
            format = self.config.get('default_format', 'terminal')

        if format == 'json':
            return self._generate_json(report)
        elif format == 'html-interactive':
            # Use enhanced interactive HTML
            from report_generator_html import InteractiveHTMLReportGenerator
            html_gen = InteractiveHTMLReportGenerator(self.config)
            return html_gen.generate(report)
        elif format == 'html':
            return self._generate_html(report)
        else:  # terminal
            return self._generate_terminal(report)

    def _generate_json(self, report: ValidationReport) -> str:
        """Generate JSON report"""
        return report.to_json(indent=2)

    def _generate_terminal(self, report: ValidationReport) -> str:
        """Generate terminal-friendly report with colors"""
        lines = []

        # Brief mode: Ultra compact output
        if self.verbosity == 'brief':
            return self._generate_brief_report(report)

        # Standard/Detailed mode: Full output
        # Header
        lines.append("")
        lines.append("═" * 80)
        lines.append("🔍  PEGASUS WORKFLOW VALIDATION REPORT")
        lines.append("═" * 80)
        lines.append("")
        lines.append(f"Workflow: {report.workflow_path}")

        if self.verbosity == 'detailed':
            lines.append(f"Validated: {report.timestamp}")
            lines.append(f"Duration: {report.total_duration_seconds:.2f}s")
        lines.append("")

        # Overall status
        status_symbol = self._get_status_symbol(report.overall_status)
        lines.append(f"Overall Status: {status_symbol} {report.overall_status.value.upper()}")
        lines.append("")

        # Summary
        lines.append("─" * 80)
        lines.append("📊 SUMMARY")
        lines.append("─" * 80)
        lines.append(f"  Total Issues: {report.total_issues}")
        lines.append(f"  ├─ Errors:    {report.total_errors}")
        lines.append(f"  └─ Warnings:  {report.total_warnings}")
        lines.append("")

        # Per-validator results (only in detailed mode)
        if self.verbosity == 'detailed' or self.show_validator_details:
            lines.append("─" * 80)
            lines.append("🔧 VALIDATOR RESULTS")
            lines.append("─" * 80)
            lines.append("")

            for result in report.validator_results:
                status_symbol = self._get_status_symbol(result.status)
                lines.append(f"{status_symbol} {result.name.upper()} ({result.duration_seconds:.2f}s)")
                lines.append(f"   Checks performed: {result.checks_performed}")
                lines.append(f"   Errors: {result.error_count}, Warnings: {result.warning_count}")

                # Show validated files details for integrity and path validators
                if result.name in ['integrity', 'paths'] and 'validated_files' in result.metadata:
                    validated_files = result.metadata['validated_files']
                    if validated_files:
                        lines.append(f"   Files validated: {len(validated_files)}")
                        if self.verbosity == 'detailed':
                            for file_info in validated_files[:5]:  # Show first 5
                                lfn = file_info.get('lfn', 'unknown')
                                size_bytes = file_info.get('size_bytes', 0)
                                checks = file_info.get('checks', [])
                                status = file_info.get('status', 'OK')

                                # Format size
                                if size_bytes < 1024:
                                    size_str = f"{size_bytes}B"
                                elif size_bytes < 1024 * 1024:
                                    size_str = f"{size_bytes / 1024:.1f}KB"
                                else:
                                    size_str = f"{size_bytes / (1024 * 1024):.1f}MB"

                                checks_str = ", ".join(checks) if checks else "existence"
                                lines.append(f"      ✓ {lfn} ({size_str}) - {checks_str}")

                            if len(validated_files) > 5:
                                lines.append(f"      ... and {len(validated_files) - 5} more files")

                lines.append("")

        # Consolidated LLM Analysis
        llm_results = [r for r in report.validator_results if r.name.startswith('llm_')]
        if llm_results and any('llm_response' in r.metadata for r in llm_results):
            lines.append("─" * 80)
            lines.append("🤖 CONSOLIDATED LLM ANALYSIS")
            lines.append("─" * 80)
            lines.append("")

            if self.llm_report_mode == 'consolidated':
                # Aggregate all LLM responses
                aggregator = LLMResponseAggregator()
                for result in llm_results:
                    if 'llm_response' in result.metadata:
                        aggregator.add_response(result.name, result.metadata['llm_response'])

                consolidated = aggregator.aggregate()

                # Executive Summary
                lines.append("📋 EXECUTIVE SUMMARY")
                lines.append("")
                lines.extend(consolidated['executive_summary'].split('\n'))
                lines.append("")

                # Questions (if any)
                if consolidated.get('questions'):
                    lines.append("❓ CLARIFICATION NEEDED")
                    lines.append("")
                    for q in consolidated['questions'][:5]:
                        lines.append(f"   • {q}")
                    lines.append("")

                # Top Recommendations (limited)
                if consolidated.get('top_recommendations'):
                    lines.append("💡 TOP RECOMMENDATIONS (Prioritized)")
                    lines.append("")
                    max_recs = self.max_recommendations if self.verbosity == 'standard' else 10
                    recs_to_show = consolidated['top_recommendations'][:max_recs]
                    for i, rec in enumerate(recs_to_show, 1):
                        lines.append(f"   {i}. {rec}")
                    if len(consolidated['top_recommendations']) > max_recs:
                        remaining = len(consolidated['top_recommendations']) - max_recs
                        lines.append(f"   ... and {remaining} more (use --verbosity detailed to see all)")
                    lines.append("")

                # Key Strengths (only if enabled)
                if self.show_strengths and consolidated.get('top_strengths'):
                    lines.append("💪 KEY STRENGTHS")
                    lines.append("")
                    max_strengths = 3 if self.verbosity == 'standard' else 5
                    for strength in consolidated['top_strengths'][:max_strengths]:
                        lines.append(f"   ✓ {strength}")
                    lines.append("")

                # Issues by Category (summary)
                if consolidated.get('issues_by_category'):
                    lines.append("📊 ISSUES BY CATEGORY")
                    lines.append("")
                    for category, issues in consolidated['issues_by_category'].items():
                        lines.append(f"   • {category.upper()}: {len(issues)} issue(s)")
                    lines.append("")

                # Optionally show raw responses
                if self.show_raw_llm_responses:
                    lines.append("─" * 80)
                    lines.append("📄 RAW LLM RESPONSES (Debug Mode)")
                    lines.append("─" * 80)
                    lines.append("")
                    for result in llm_results:
                        if 'llm_response' in result.metadata:
                            lines.append(f"🔹 {result.name.upper()}")
                            lines.append("   " + "─" * 75)
                            llm_response = result.metadata['llm_response']
                            for line in llm_response.split('\n'):
                                lines.append(f"   {line}")
                            lines.append("   " + "─" * 75)
                            lines.append("")

            else:
                # Show individual responses (old behavior)
                for result in llm_results:
                    if 'llm_response' in result.metadata:
                        lines.append(f"🔹 {result.name.upper()}")
                        lines.append("   " + "─" * 75)
                        llm_response = result.metadata['llm_response']
                        for line in llm_response.split('\n'):
                            lines.append(f"   {line}")
                        lines.append("   " + "─" * 75)
                        lines.append("")

        # Detailed issues (limited by max_issues_shown)
        if report.total_issues > 0:
            lines.append("─" * 80)
            lines.append("🚨 ISSUES FOUND")
            lines.append("─" * 80)
            lines.append("")

            # Group by severity
            critical = [i for i in report.all_issues if i.severity == Severity.CRITICAL]
            errors = [i for i in report.all_issues if i.severity == Severity.ERROR]
            warnings = [i for i in report.all_issues if i.severity == Severity.WARNING]

            issues_shown = 0
            max_issues = self.max_issues_shown if self.verbosity == 'standard' else 999

            if critical:
                lines.append(f"🔴 CRITICAL ({len(critical)})")
                lines.append("")
                for issue in critical[:max_issues - issues_shown]:
                    lines.extend(self._format_issue(issue))
                    issues_shown += 1
                if len(critical) > (max_issues - issues_shown):
                    lines.append(f"   ... and {len(critical) - (max_issues - issues_shown)} more critical issues")
                lines.append("")

            if errors and issues_shown < max_issues:
                lines.append(f"❌ ERRORS ({len(errors)})")
                lines.append("")
                for issue in errors[:max_issues - issues_shown]:
                    lines.extend(self._format_issue(issue))
                    issues_shown += 1
                if len(errors) > (max_issues - issues_shown):
                    lines.append(f"   ... and {len(errors) - (max_issues - issues_shown)} more errors")
                lines.append("")

            if warnings and issues_shown < max_issues:
                lines.append(f"⚠️  WARNINGS ({len(warnings)})")
                lines.append("")
                warnings_to_show = min(len(warnings), max_issues - issues_shown)
                for issue in warnings[:warnings_to_show]:
                    lines.extend(self._format_issue(issue))
                    issues_shown += 1
                if len(warnings) > warnings_to_show:
                    lines.append(f"   ... and {len(warnings) - warnings_to_show} more warnings")
                lines.append("")

            if issues_shown < report.total_issues:
                lines.append(f"💡 Showing {issues_shown} of {report.total_issues} issues. Use --verbosity detailed to see all.")
                lines.append("")

        # Footer
        lines.append("═" * 80)

        if report.overall_status == ValidationStatus.PASSED:
            lines.append("✅ VALIDATION PASSED")
            lines.append("")
            lines.append("Workflow is ready for submission!")
        elif report.overall_status == ValidationStatus.FAILED:
            lines.append("❌ VALIDATION FAILED")
            lines.append("")
            lines.append(f"Fix {report.total_errors} error(s) before submitting workflow")
        else:
            lines.append("⚠️  VALIDATION PASSED WITH WARNINGS")
            lines.append("")
            lines.append(f"Consider addressing {report.total_warnings} warning(s) to improve reliability")

        lines.append("═" * 80)
        lines.append("")

        return "\n".join(lines)

    def _format_issue(self, issue) -> list:
        """Format a single issue for terminal output"""
        lines = []

        # Issue header
        category_emoji = {
            'syntax': '📝',
            'structure': '🏗️',
            'dependencies': '🔗',
            'paths': '📂',
            'integrity': '🔐',
            'resources': '⚙️',
            'code': '💻',
            'data_quality': '📊'
        }.get(issue.category.value, '🔍')

        lines.append(f"{category_emoji} {issue.message}")

        if issue.location:
            lines.append(f"   Location: {issue.location}")

        if self.verbosity in ['standard', 'verbose'] and issue.explanation:
            lines.append(f"   Reason: {issue.explanation}")

        if issue.impact:
            lines.append(f"   Impact: {issue.impact}")

        if self.show_suggestions and issue.suggestion:
            lines.append(f"   💡 Fix: {issue.suggestion}")

        if self.verbosity == 'verbose' and issue.code_snippet:
            lines.append("   Code:")
            for code_line in issue.code_snippet.split('\n'):
                lines.append(f"      {code_line}")

        lines.append("")

        return lines

    def _get_status_symbol(self, status: ValidationStatus) -> str:
        """Get emoji for status"""
        if status == ValidationStatus.PASSED:
            return "✅"
        elif status == ValidationStatus.FAILED:
            return "❌"
        else:
            return "⚠️"

    def _generate_brief_report(self, report: ValidationReport) -> str:
        """Generate ultra-compact brief report"""
        lines = []

        # One-line header
        status_symbol = self._get_status_symbol(report.overall_status)
        lines.append("")
        lines.append(f"{status_symbol} {report.overall_status.value.upper()} | {report.total_errors} errors, {report.total_warnings} warnings | {report.total_duration_seconds:.1f}s")
        lines.append("")

        # LLM Executive Summary only (most important)
        llm_results = [r for r in report.validator_results if r.name.startswith('llm_')]
        if llm_results and any('llm_response' in r.metadata for r in llm_results):
            aggregator = LLMResponseAggregator()
            for result in llm_results:
                if 'llm_response' in result.metadata:
                    aggregator.add_response(result.name, result.metadata['llm_response'])

            consolidated = aggregator.aggregate()

            # Just the executive summary
            lines.append("🤖 LLM ANALYSIS")
            lines.append("─" * 60)
            lines.extend(consolidated['executive_summary'].split('\n'))
            lines.append("")

            # Critical issues only
            if consolidated['critical_issues'] > 0 or consolidated['error_issues'] > 0:
                lines.append("🚨 CRITICAL ACTIONS NEEDED:")
                count = 0
                for category, issues in consolidated.get('issues_by_category', {}).items():
                    for issue in issues:
                        if issue.get('severity') in ['critical', 'error']:
                            lines.append(f"   • {issue.get('message', 'Unknown issue')}")
                            count += 1
                            if count >= 3:  # Max 3 critical issues in brief mode
                                break
                    if count >= 3:
                        break

                if consolidated['critical_issues'] + consolidated['error_issues'] > 3:
                    remaining = consolidated['critical_issues'] + consolidated['error_issues'] - 3
                    lines.append(f"   ... and {remaining} more critical/error issues")
                lines.append("")

            # Top 3 recommendations
            if consolidated.get('top_recommendations'):
                lines.append("💡 TOP ACTIONS:")
                for i, rec in enumerate(consolidated['top_recommendations'][:3], 1):
                    lines.append(f"   {i}. {rec}")
                if len(consolidated['top_recommendations']) > 3:
                    lines.append(f"   ... +{len(consolidated['top_recommendations']) - 3} more")
                lines.append("")

        else:
            # No LLM results, show critical issues from rule-based validators
            if report.total_issues > 0:
                lines.append("🚨 ISSUES:")
                critical = [i for i in report.all_issues if i.severity == Severity.CRITICAL][:3]
                errors = [i for i in report.all_issues if i.severity == Severity.ERROR][:3]

                for issue in critical + errors:
                    lines.append(f"   • [{issue.severity.value.upper()}] {issue.message}")

                if report.total_issues > 6:
                    lines.append(f"   ... and {report.total_issues - 6} more issues")
                lines.append("")

        # Footer with hint
        lines.append("─" * 60)
        lines.append("💡 Use --verbosity standard for detailed report")
        lines.append("💡 Use --verbosity detailed for full analysis")
        lines.append("")

        return "\n".join(lines)

    def _generate_html(self, report: ValidationReport) -> str:
        """Generate HTML report (basic implementation)"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Workflow Validation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f0f0f0; padding: 20px; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        .warning {{ color: orange; }}
        .issue {{ border-left: 4px solid #ddd; padding-left: 10px; margin: 10px 0; }}
        .critical {{ border-color: red; }}
        .error {{ border-color: orange; }}
        .validator-result {{ margin: 20px 0; padding: 15px; background: #f9f9f9; border-radius: 5px; }}
        .llm-analysis {{ background: #fff; padding: 15px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; font-family: monospace; white-space: pre-wrap; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Workflow Validation Report</h1>
        <p><strong>Workflow:</strong> {report.workflow_path}</p>
        <p><strong>Status:</strong> <span class="{report.overall_status.value}">{report.overall_status.value.upper()}</span></p>
        <p><strong>Issues:</strong> {report.total_errors} errors, {report.total_warnings} warnings</p>
    </div>

    <h2>Validator Results</h2>
"""

        # Add validator results (without individual LLM responses)
        for result in report.validator_results:
            status_class = result.status.value
            html += f"""
    <div class="validator-result">
        <h3>{result.name.upper()}</h3>
        <p><strong>Status:</strong> <span class="{status_class}">{result.status.value}</span></p>
        <p><strong>Duration:</strong> {result.duration_seconds:.2f}s</p>
        <p><strong>Checks:</strong> {result.checks_performed}</p>
        <p><strong>Issues:</strong> {result.error_count} errors, {result.warning_count} warnings</p>
    </div>
"""

        # Consolidated LLM Analysis
        llm_results = [r for r in report.validator_results if r.name.startswith('llm_')]
        if llm_results and any('llm_response' in r.metadata for r in llm_results):
            aggregator = LLMResponseAggregator()
            for result in llm_results:
                if 'llm_response' in result.metadata:
                    aggregator.add_response(result.name, result.metadata['llm_response'])

            consolidated = aggregator.aggregate()

            html += """
    <h2>🤖 Consolidated LLM Analysis</h2>
    <div class="validator-result">
        <h3>📋 Executive Summary</h3>
        <pre style="white-space: pre-wrap; font-family: inherit;">""" + consolidated['executive_summary'] + """</pre>
"""

            if consolidated.get('top_recommendations'):
                html += """
        <h3>💡 Top Priority Recommendations</h3>
        <ol>
"""
                for rec in consolidated['top_recommendations'][:10]:
                    html += f"            <li>{rec}</li>\n"
                html += """
        </ol>
"""

            if consolidated.get('top_strengths'):
                html += """
        <h3>💪 Key Strengths</h3>
        <ul>
"""
                for strength in consolidated['top_strengths']:
                    html += f"            <li>{strength}</li>\n"
                html += """
        </ul>
"""

            if consolidated.get('questions'):
                html += """
        <h3>❓ Clarification Needed</h3>
        <ul>
"""
                for q in consolidated['questions'][:5]:
                    html += f"            <li>{q}</li>\n"
                html += """
        </ul>
"""

            html += """
    </div>
"""

        html += """
    <h2>Issues</h2>
"""

        for issue in report.all_issues:
            severity_class = issue.severity.value
            html += f"""
    <div class="issue {severity_class}">
        <strong>[{issue.severity.value.upper()}]</strong> {issue.message}<br>
        {f'<em>Location:</em> {issue.location}<br>' if issue.location else ''}
        {f'<em>Suggestion:</em> {issue.suggestion}<br>' if issue.suggestion else ''}
    </div>
"""

        html += """
</body>
</html>
"""
        return html

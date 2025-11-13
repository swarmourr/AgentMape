"""
Enhanced HTML Report Generator with interactive features
"""
import json
from typing import Dict, Any
from models import ValidationReport, Severity, ValidationStatus


class InteractiveHTMLReportGenerator:
    """Generates interactive HTML reports with collapsible sections and search"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('output_config', {})

    def generate(self, report: ValidationReport) -> str:
        """Generate interactive HTML report"""

        # Prepare data
        total_jobs_validated = sum([
            len(r.metadata.get('validated_jobs', []))
            for r in report.validator_results
            if 'validated_jobs' in r.metadata
        ])

        total_files_validated = sum([
            len(r.metadata.get('validated_files', []))
            for r in report.validator_results
            if 'validated_files' in r.metadata
        ])

        status_color = {
            ValidationStatus.PASSED: '#28a745',
            ValidationStatus.WARNING: '#ffc107',
            ValidationStatus.FAILED: '#dc3545'
        }

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workflow Validation Report - {report.workflow_path}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            padding: 20px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
        }}

        .header h1 {{
            font-size: 32px;
            margin-bottom: 10px;
        }}

        .header .workflow-path {{
            opacity: 0.9;
            font-size: 14px;
            margin-bottom: 20px;
            word-break: break-all;
        }}

        .status-badge {{
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 14px;
            text-transform: uppercase;
            background: {status_color.get(report.overall_status, '#6c757d')};
        }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 40px;
            background: #f8f9fa;
        }}

        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}

        .stat-card .label {{
            color: #6c757d;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }}

        .stat-card .value {{
            font-size: 32px;
            font-weight: 700;
            color: #2c3e50;
        }}

        .content {{
            padding: 40px;
        }}

        .section {{
            margin-bottom: 30px;
        }}

        .section-title {{
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #2c3e50;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .validator-card {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
        }}

        .validator-card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }}

        .validator-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .validator-name {{
            font-weight: 600;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .validator-stats {{
            display: flex;
            gap: 20px;
            font-size: 14px;
            color: #6c757d;
        }}

        .validator-details {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            display: none;
        }}

        .validator-details.active {{
            display: block;
        }}

        .file-list {{
            background: white;
            border-radius: 4px;
            padding: 15px;
            margin-top: 10px;
        }}

        .file-item {{
            padding: 8px;
            border-bottom: 1px solid #f0f0f0;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
        }}

        .file-item:last-child {{
            border-bottom: none;
        }}

        .issue {{
            background: white;
            border-left: 4px solid;
            border-radius: 4px;
            padding: 15px;
            margin-bottom: 15px;
        }}

        .issue.critical {{
            border-color: #dc3545;
            background: #fff5f5;
        }}

        .issue.error {{
            border-color: #fd7e14;
            background: #fff8f5;
        }}

        .issue.warning {{
            border-color: #ffc107;
            background: #fffbf0;
        }}

        .issue-header {{
            font-weight: 600;
            margin-bottom: 8px;
        }}

        .issue-body {{
            color: #6c757d;
            font-size: 14px;
        }}

        .issue-suggestion {{
            margin-top: 10px;
            padding: 10px;
            background: rgba(102, 126, 234, 0.1);
            border-radius: 4px;
            font-size: 13px;
        }}

        .toggle-icon {{
            transition: transform 0.3s ease;
        }}

        .toggle-icon.active {{
            transform: rotate(180deg);
        }}

        .search-box {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 20px;
        }}

        .search-box:focus {{
            outline: none;
            border-color: #667eea;
        }}

        .footer {{
            padding: 20px 40px;
            background: #f8f9fa;
            text-align: center;
            color: #6c757d;
            font-size: 12px;
        }}

        .status-icon {{
            font-size: 24px;
        }}

        @media print {{
            body {{ background: white; }}
            .container {{ box-shadow: none; }}
            .validator-details {{ display: block !important; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Workflow Validation Report</h1>
            <div class="workflow-path">📄 {report.workflow_path}</div>
            <div>
                <span class="status-badge">{self._get_status_icon(report.overall_status)} {report.overall_status.value.upper()}</span>
            </div>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="label">Total Issues</div>
                <div class="value">{report.total_issues}</div>
            </div>
            <div class="stat-card" style="border-color: #dc3545;">
                <div class="label">Errors</div>
                <div class="value" style="color: #dc3545;">{report.total_errors}</div>
            </div>
            <div class="stat-card" style="border-color: #ffc107;">
                <div class="label">Warnings</div>
                <div class="value" style="color: #ffc107;">{report.total_warnings}</div>
            </div>
            <div class="stat-card" style="border-color: #28a745;">
                <div class="label">Duration</div>
                <div class="value" style="font-size: 24px;">{report.total_duration_seconds:.2f}s</div>
            </div>
            <div class="stat-card" style="border-color: #17a2b8;">
                <div class="label">Files Validated</div>
                <div class="value" style="font-size: 24px;">{total_files_validated}</div>
            </div>
            <div class="stat-card" style="border-color: #6f42c1;">
                <div class="label">Jobs Checked</div>
                <div class="value" style="font-size: 24px;">{total_jobs_validated}</div>
            </div>
        </div>

        <div class="content">
            <div class="section">
                <div class="section-title">🔧 Validation Results</div>
                <input type="text" class="search-box" id="searchBox" placeholder="Search validators, files, or issues...">

"""

        # Add validator cards
        for result in report.validator_results:
            status_icon = self._get_status_icon(result.status)
            html += self._generate_validator_card(result, status_icon)

        # Add issues section
        if report.total_issues > 0:
            html += f"""
            <div class="section">
                <div class="section-title">🚨 Issues Found</div>
"""

            critical = [i for i in report.all_issues if i.severity == Severity.CRITICAL]
            errors = [i for i in report.all_issues if i.severity == Severity.ERROR]
            warnings = [i for i in report.all_issues if i.severity == Severity.WARNING]

            if critical:
                html += f"<h3 style='color: #dc3545; margin-bottom: 15px;'>🔴 Critical Issues ({len(critical)})</h3>"
                for issue in critical:
                    html += self._generate_issue_card(issue, "critical")

            if errors:
                html += f"<h3 style='color: #fd7e14; margin-bottom: 15px;'>❌ Errors ({len(errors)})</h3>"
                for issue in errors:
                    html += self._generate_issue_card(issue, "error")

            if warnings:
                html += f"<h3 style='color: #ffc107; margin-bottom: 15px;'>⚠️ Warnings ({len(warnings)})</h3>"
                for issue in warnings:
                    html += self._generate_issue_card(issue, "warning")

            html += "</div>"

        html += f"""
        </div>

        <div class="footer">
            Generated on {report.timestamp} | Validator v{report.validator_version}
        </div>
    </div>

    <script>
        // Toggle validator details
        document.querySelectorAll('.validator-card').forEach(card => {{
            card.addEventListener('click', (e) => {{
                const details = card.querySelector('.validator-details');
                const icon = card.querySelector('.toggle-icon');
                details.classList.toggle('active');
                icon.classList.toggle('active');
            }});
        }});

        // Search functionality
        document.getElementById('searchBox').addEventListener('input', (e) => {{
            const query = e.target.value.toLowerCase();
            document.querySelectorAll('.validator-card, .issue').forEach(item => {{
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(query) ? 'block' : 'none';
            }});
        }});
    </script>
</body>
</html>
"""
        return html

    def _generate_validator_card(self, result, status_icon: str) -> str:
        """Generate HTML for a validator card"""
        card = f"""
                <div class="validator-card">
                    <div class="validator-header">
                        <div class="validator-name">
                            <span class="status-icon">{status_icon}</span>
                            <span>{result.name.upper()}</span>
                        </div>
                        <div class="validator-stats">
                            <span>⏱️ {result.duration_seconds:.2f}s</span>
                            <span>✓ {result.checks_performed} checks</span>
                            <span>❌ {result.error_count} errors</span>
                            <span>⚠️ {result.warning_count} warnings</span>
                            <span class="toggle-icon">▼</span>
                        </div>
                    </div>
                    <div class="validator-details">
"""

        # Add validated files if available
        if 'validated_files' in result.metadata:
            files = result.metadata['validated_files']
            if files:
                card += f"""
                        <div>
                            <strong>📁 Files Validated ({len(files)}):</strong>
                            <div class="file-list">
"""
                for file_info in files[:10]:  # Show first 10
                    lfn = file_info.get('lfn', 'unknown')
                    size = file_info.get('size_bytes', 0)
                    checks = ', '.join(file_info.get('checks', []))

                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f}KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f}MB"

                    card += f"""
                                <div class="file-item">✓ {lfn} ({size_str}) - {checks}</div>
"""

                if len(files) > 10:
                    card += f"""
                                <div class="file-item" style="color: #6c757d;">... and {len(files) - 10} more files</div>
"""

                card += """
                            </div>
                        </div>
"""

        # Add validated jobs if available
        if 'validated_jobs' in result.metadata:
            jobs = result.metadata['validated_jobs']
            if jobs:
                card += f"""
                        <div style="margin-top: 15px;">
                            <strong>⚙️ Jobs Validated ({len(jobs)}):</strong>
                            <div class="file-list">
"""
                for job_info in jobs[:10]:
                    job_name = job_info.get('job_name', 'unknown')
                    inputs = len(job_info.get('input_files', []))
                    outputs = len(job_info.get('output_files', []))
                    card += f"""
                                <div class="file-item">✓ {job_name} ({inputs} inputs, {outputs} outputs)</div>
"""

                if len(jobs) > 10:
                    card += f"""
                                <div class="file-item" style="color: #6c757d;">... and {len(jobs) - 10} more jobs</div>
"""

                card += """
                            </div>
                        </div>
"""

        # Add DAG info if available
        if result.name == 'dag' and result.metadata:
            card += f"""
                        <div style="margin-top: 15px;">
                            <strong>📊 DAG Statistics:</strong>
                            <div class="file-list">
                                <div class="file-item">Total Jobs: {result.metadata.get('total_jobs', 0)}</div>
                                <div class="file-item">Jobs with Dependencies: {result.metadata.get('jobs_with_parents', 0)}</div>
                                <div class="file-item">Max Depth: {result.metadata.get('max_depth', 0)}</div>
                                <div class="file-item">Cycles Detected: {len(result.metadata.get('cycles_detected', []))}</div>
                            </div>
                        </div>
"""

        card += """
                    </div>
                </div>
"""
        return card

    def _generate_issue_card(self, issue, severity_class: str) -> str:
        """Generate HTML for an issue card"""
        card = f"""
                <div class="issue {severity_class}">
                    <div class="issue-header">{issue.message}</div>
                    <div class="issue-body">
"""

        if issue.location:
            card += f"<div><strong>Location:</strong> {issue.location}</div>"

        if issue.explanation:
            card += f"<div><strong>Reason:</strong> {issue.explanation}</div>"

        if issue.impact:
            card += f"<div><strong>Impact:</strong> {issue.impact}</div>"

        card += "</div>"

        if issue.suggestion:
            card += f"""
                    <div class="issue-suggestion">
                        💡 <strong>Suggestion:</strong> {issue.suggestion}
                    </div>
"""

        card += "</div>"
        return card

    def _get_status_icon(self, status: ValidationStatus) -> str:
        """Get emoji for status"""
        if status == ValidationStatus.PASSED:
            return "✅"
        elif status == ValidationStatus.FAILED:
            return "❌"
        else:
            return "⚠️"

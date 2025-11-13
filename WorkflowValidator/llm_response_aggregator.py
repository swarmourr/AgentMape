"""
LLM Response Aggregator - Consolidates and deduplicates LLM findings
"""
import json
import re
from typing import List, Dict, Any
from collections import defaultdict


class LLMResponseAggregator:
    """Aggregates multiple LLM responses into a consolidated analysis"""

    def __init__(self):
        self.responses = []

    def add_response(self, validator_name: str, response: str):
        """Add an LLM response to aggregate"""
        self.responses.append({
            'validator': validator_name,
            'response': response
        })

    def aggregate(self) -> Dict[str, Any]:
        """
        Aggregate all LLM responses into a consolidated report

        Returns:
            Dict with consolidated analysis, deduped issues, and key insights
        """
        all_issues = []
        all_strengths = []
        all_recommendations = []
        questions = []
        metrics = {}

        # Parse each response
        for item in self.responses:
            validator = item['validator']
            response = item['response']

            try:
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())

                    # Collect issues
                    for issue in data.get('issues', []):
                        issue['source'] = validator
                        all_issues.append(issue)

                    # Collect strengths
                    strengths = data.get('strengths', [])
                    if isinstance(strengths, list):
                        all_strengths.extend(strengths)

                    # Collect recommendations
                    recommendations = data.get('recommendations', [])
                    if isinstance(recommendations, list):
                        all_recommendations.extend(recommendations)
                    elif isinstance(data.get('optimization_suggestions'), list):
                        all_recommendations.extend(data.get('optimization_suggestions', []))
                    elif isinstance(data.get('security_recommendations'), list):
                        all_recommendations.extend(data.get('security_recommendations', []))
                    elif isinstance(data.get('quick_wins'), list):
                        all_recommendations.extend(data.get('quick_wins', []))

                    # Collect questions
                    if data.get('needs_clarification') and data.get('questions'):
                        questions.extend(data.get('questions', []))

                    # Collect metrics
                    if 'graph_metrics' in data:
                        metrics['graph'] = data['graph_metrics']
                    if 'quality_score' in data:
                        metrics['quality'] = data['quality_score']
                    if 'resource_totals' in data:
                        metrics['resources'] = data['resource_totals']
                    if 'risk_level' in data:
                        metrics['security_risk'] = data['risk_level']

            except Exception as e:
                # If parsing fails, extract key information from text
                continue

        # Deduplicate and prioritize
        deduped_issues = self._deduplicate_issues(all_issues)
        top_strengths = self._deduplicate_list(all_strengths)[:5]  # Top 5 strengths
        top_recommendations = self._prioritize_recommendations(all_recommendations)[:10]  # Top 10
        unique_questions = self._deduplicate_list(questions)

        # Group issues by category
        issues_by_category = defaultdict(list)
        for issue in deduped_issues:
            category = issue.get('category', 'general')
            issues_by_category[category].append(issue)

        # Create consolidated summary
        return {
            'total_issues': len(deduped_issues),
            'critical_issues': len([i for i in deduped_issues if i.get('severity') == 'critical']),
            'error_issues': len([i for i in deduped_issues if i.get('severity') == 'error']),
            'warning_issues': len([i for i in deduped_issues if i.get('severity') == 'warning']),
            'issues_by_category': dict(issues_by_category),
            'top_strengths': top_strengths,
            'top_recommendations': top_recommendations,
            'questions': unique_questions,
            'metrics': metrics,
            'executive_summary': self._generate_executive_summary(
                deduped_issues, top_strengths, top_recommendations, metrics
            )
        }

    def _deduplicate_issues(self, issues: List[Dict]) -> List[Dict]:
        """Deduplicate similar issues and calibrate severity"""
        seen = {}
        deduped = []

        for issue in issues:
            # First, calibrate severity based on execution blocking
            issue = self._calibrate_severity(issue)

            # Create key based on message and location
            message = issue.get('message', '').lower()
            location = issue.get('location', '')
            key = f"{message[:100]}:{location}"

            if key not in seen:
                seen[key] = issue
                deduped.append(issue)
            else:
                # If we see the same issue again, keep the more severe one
                existing = seen[key]
                severity_order = {'critical': 4, 'error': 3, 'warning': 2, 'info': 1}
                new_severity = severity_order.get(issue.get('severity', 'info'), 1)
                existing_severity = severity_order.get(existing.get('severity', 'info'), 1)

                if new_severity > existing_severity:
                    # Replace with more severe version
                    deduped.remove(existing)
                    deduped.append(issue)
                    seen[key] = issue

        # Sort by severity
        severity_order = {'critical': 4, 'error': 3, 'warning': 2, 'info': 1}
        deduped.sort(key=lambda x: severity_order.get(x.get('severity', 'info'), 1), reverse=True)

        return deduped

    def _calibrate_severity(self, issue: Dict) -> Dict:
        """
        Calibrate severity based on whether it actually blocks execution
        Uses the 'will_block_execution' field from LLM reasoning
        """
        import logging
        logger = logging.getLogger(__name__)

        message_lower = issue.get('message', '').lower()
        current_severity = issue.get('severity', 'warning')
        will_block = issue.get('will_block_execution', None)

        # If LLM explicitly said it won't block, downgrade severity
        if will_block is False:
            if current_severity in ['critical', 'error']:
                issue['severity'] = 'warning'
                issue['message'] = issue['message'] + " (not a blocker)"
                logger.debug(f"Downgraded: {message_lower[:50]}... (won't block)")

        # Common false-positive patterns - downgrade even if LLM missed it
        false_critical_patterns = {
            'missing memory': 'warning',
            'missing cpu': 'warning',
            'no memory specification': 'warning',
            'no cpu specification': 'warning',
            'missing resource': 'warning',
            'no error handling': 'info',
            'missing documentation': 'info',
            'no checksum': 'info',
            'naming convention': 'info',
            'could be optimized': 'info',
            'consider adding': 'info',
            'recommend': 'info',
            'suggestion': 'info'
        }

        for pattern, correct_severity in false_critical_patterns.items():
            if pattern in message_lower:
                severity_order = {'critical': 4, 'error': 3, 'warning': 2, 'info': 1}
                if severity_order.get(current_severity, 0) > severity_order.get(correct_severity, 0):
                    issue['severity'] = correct_severity
                    logger.debug(f"Calibrated '{pattern}': {current_severity} → {correct_severity}")
                break

        # Patterns that ARE genuinely critical - upgrade if needed
        real_critical_patterns = [
            'file not found',
            'file does not exist',
            'cannot find file',
            'missing required file',
            'circular dependency',
            'deadlock',
            'infinite loop',
            'invalid reference',
            'corrupted',
            'permission denied',
            'syntax error',
            'parse error'
        ]

        for pattern in real_critical_patterns:
            if pattern in message_lower:
                if will_block is not False:
                    if issue['severity'] not in ['critical', 'error']:
                        issue['severity'] = 'error'
                        logger.debug(f"Upgraded for pattern '{pattern}'")
                break

        return issue

    def _deduplicate_list(self, items: List[str]) -> List[str]:
        """Deduplicate list while preserving order"""
        seen = set()
        result = []
        for item in items:
            normalized = item.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                result.append(item)
        return result

    def _prioritize_recommendations(self, recommendations: List[str]) -> List[str]:
        """Prioritize and deduplicate recommendations"""
        # Deduplicate first
        deduped = self._deduplicate_list(recommendations)

        # Priority keywords (higher priority recommendations mentioned first)
        high_priority_keywords = [
            'critical', 'security', 'vulnerability', 'data loss',
            'corruption', 'failure', 'error', 'fix', 'immediate'
        ]
        medium_priority_keywords = [
            'optimize', 'improve', 'enhance', 'performance', 'efficiency'
        ]

        # Score each recommendation
        scored = []
        for rec in deduped:
            score = 0
            rec_lower = rec.lower()

            # High priority
            if any(kw in rec_lower for kw in high_priority_keywords):
                score += 10

            # Medium priority
            elif any(kw in rec_lower for kw in medium_priority_keywords):
                score += 5

            # Shorter recommendations are usually more actionable
            if len(rec) < 100:
                score += 2

            scored.append((score, rec))

        # Sort by score (descending)
        scored.sort(key=lambda x: x[0], reverse=True)

        return [rec for score, rec in scored]

    def _generate_executive_summary(self, issues: List[Dict], strengths: List[str],
                                   recommendations: List[str], metrics: Dict) -> str:
        """Generate a concise executive summary"""
        lines = []

        # Overall health
        critical_count = len([i for i in issues if i.get('severity') == 'critical'])
        error_count = len([i for i in issues if i.get('severity') == 'error'])
        warning_count = len([i for i in issues if i.get('severity') == 'warning'])

        if critical_count > 0:
            lines.append(f"⚠️ CRITICAL: Workflow has {critical_count} critical issue(s) that must be fixed before deployment.")
        elif error_count > 0:
            lines.append(f"⚠️ ERRORS: Workflow has {error_count} error(s) that should be addressed.")
        elif warning_count > 0:
            lines.append(f"✓ GOOD: Workflow is functional but has {warning_count} warning(s) for improvement.")
        else:
            lines.append("✅ EXCELLENT: Workflow passes all LLM checks with no issues.")

        # Key metrics
        if metrics:
            lines.append("\n📊 Key Metrics:")
            if 'quality' in metrics:
                lines.append(f"   • Code Quality Scores: {metrics['quality']}")
            if 'graph' in metrics:
                graph = metrics['graph']
                lines.append(f"   • DAG: {graph.get('total_jobs', 'N/A')} jobs, max parallelism: {graph.get('max_parallelism', 'N/A')}")
            if 'security_risk' in metrics:
                lines.append(f"   • Security Risk Level: {metrics['security_risk']}")

        # Top issue categories
        if issues:
            categories = defaultdict(int)
            for issue in issues:
                categories[issue.get('category', 'general')] += 1

            top_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
            lines.append(f"\n🔍 Main Issue Categories:")
            for cat, count in top_cats:
                lines.append(f"   • {cat}: {count} issue(s)")

        # Strengths highlight
        if strengths:
            lines.append(f"\n💪 Key Strengths:")
            for strength in strengths[:3]:
                lines.append(f"   • {strength}")

        # Top recommendations
        if recommendations:
            lines.append(f"\n💡 Top Priority Actions:")
            for rec in recommendations[:3]:
                lines.append(f"   • {rec}")

        return "\n".join(lines)

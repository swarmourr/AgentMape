"""
Enhanced Replica File Handler for Scientific Workflows
Provides intelligent replica file detection, validation, and repair strategies
Designed specifically for Pegasus-WMS workflows
"""

import os
import re
import json
import yaml
import hashlib
import glob
from typing import Dict, List, Optional, Tuple, Any
from difflib import SequenceMatcher
from pathlib import Path
from enum import Enum


class RepairStrategy(Enum):
    """Types of repair strategies for missing replicas"""
    TYPO_FIX = "typo_fix_at_source"           # High confidence name fix
    SYMLINK_CREATE = "create_symlink"         # File exists elsewhere
    CATALOG_UPDATE = "update_replica_catalog" # Update catalog entry
    GENERATOR_FIX = "fix_generator_script"    # Fix workflow generator
    MANUAL_INTERVENTION = "manual_required"   # Cannot auto-fix
    DATA_RELOCATED = "data_relocated"         # Data moved to new location


class RiskLevel(Enum):
    """Risk levels for replica fixes"""
    LOW = "low"           # Safe to auto-execute
    MEDIUM = "medium"     # Review recommended
    HIGH = "high"         # Approval required
    CRITICAL = "critical" # Manual only


class ReplicaHelper:
    """Enhanced replica handling with scientific workflow awareness"""

    def __init__(self, monitor_url: str = "http://localhost:8080"):
        self.monitor_url = monitor_url
        self._file_cache = {}  # Cache file validations

    def detect_workflow_generator(self, workflow_context: Dict) -> Optional[Dict[str, str]]:
        """
        Detect if workflow has a generator script
        Returns dict with generator info or None
        """
        # Check if generator already identified in context
        if 'workflow_generator' in workflow_context:
            return workflow_context['workflow_generator']

        # Try to find generator from common locations
        submit_dir = workflow_context.get('workflow_dir') or workflow_context.get('iwd', '')

        if not submit_dir or not os.path.exists(submit_dir):
            return None

        # Common generator script patterns
        generator_patterns = [
            'workflow_generator.py',
            'workflow-generator.py',
            'generate_workflow.py',
            'generate-workflow.py',
            '*_workflow.py',
            'workflow.py'
        ]

        # Search in submit directory and parent directories
        search_dirs = [
            submit_dir,
            os.path.dirname(submit_dir),
            os.path.dirname(os.path.dirname(submit_dir))
        ]

        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue

            for pattern in generator_patterns:
                matches = glob.glob(os.path.join(search_dir, pattern))
                if matches:
                    # Found potential generator
                    generator_path = matches[0]
                    return {
                        'path': generator_path,
                        'name': os.path.basename(generator_path),
                        'directory': os.path.dirname(generator_path),
                        'detected': True
                    }

        return None

    def calculate_similarity_score(self, target: str, candidate: str) -> Dict[str, Any]:
        """
        Enhanced similarity scoring with multiple factors
        Returns score (0-1) and detailed breakdown
        """
        target_lower = target.lower()
        candidate_lower = candidate.lower()

        # Base similarity using SequenceMatcher
        base_similarity = SequenceMatcher(None, target_lower, candidate_lower).ratio()

        # Factor 1: Exact match (case insensitive)
        if target_lower == candidate_lower:
            return {
                "score": 1.0,
                "confidence": "exact_match",
                "reason": "Exact match (case insensitive)",
                "factors": {"exact_match": 1.0}
            }

        # Factor 2: Extension match bonus
        target_ext = os.path.splitext(target)[1]
        candidate_ext = os.path.splitext(candidate)[1]
        extension_match = target_ext.lower() == candidate_ext.lower() if target_ext and candidate_ext else False
        extension_bonus = 0.15 if extension_match else 0

        # Factor 3: Stem similarity (without extension)
        target_stem = os.path.splitext(target)[0]
        candidate_stem = os.path.splitext(candidate)[0]
        stem_similarity = SequenceMatcher(None, target_stem.lower(), candidate_stem.lower()).ratio()

        # Factor 4: Number substitution detection (data1 vs data2)
        target_no_nums = re.sub(r'\d+', 'N', target_lower)
        candidate_no_nums = re.sub(r'\d+', 'N', candidate_lower)
        number_pattern_match = target_no_nums == candidate_no_nums

        # Factor 5: Common typo patterns
        typo_distance = self._check_typo_distance(target_lower, candidate_lower)
        is_likely_typo = typo_distance == 1  # Only 1 char difference

        # Factor 6: Length similarity
        len_ratio = min(len(target), len(candidate)) / max(len(target), len(candidate))

        # Calculate weighted score
        score = base_similarity

        if extension_match:
            score = min(1.0, score + extension_bonus)

        if is_likely_typo and extension_match:
            score = min(1.0, score + 0.2)

        if number_pattern_match and extension_match:
            score = min(1.0, score + 0.1)

        # Determine confidence level
        confidence = "low"
        reason = []

        if score >= 0.95:
            confidence = "very_high"
            reason.append("Nearly identical")
        elif score >= 0.85:
            confidence = "high"
            if is_likely_typo:
                reason.append("Likely typo (1 char diff)")
            if extension_match:
                reason.append("Same file type")
        elif score >= 0.70:
            confidence = "medium"
            if number_pattern_match:
                reason.append("Number variation (data1 vs data2)")
        else:
            confidence = "low"
            reason.append("Low similarity")

        return {
            "score": round(score, 3),
            "confidence": confidence,
            "reason": ", ".join(reason) if reason else "Different files",
            "factors": {
                "base_similarity": round(base_similarity, 3),
                "extension_match": extension_match,
                "stem_similarity": round(stem_similarity, 3),
                "number_pattern_match": number_pattern_match,
                "likely_typo": is_likely_typo,
                "length_ratio": round(len_ratio, 3)
            }
        }

    def _check_typo_distance(self, str1: str, str2: str) -> int:
        """Calculate edit distance (number of single-char changes needed)"""
        if len(str1) > len(str2):
            str1, str2 = str2, str1

        distances = range(len(str1) + 1)
        for i2, c2 in enumerate(str2):
            distances_ = [i2 + 1]
            for i1, c1 in enumerate(str1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_

        return distances[-1]

    def rank_similar_files(self, target_filename: str, available_files: List[Dict],
                          min_score: float = 0.6) -> List[Dict]:
        """
        Rank available files by similarity to target
        Returns sorted list with detailed scoring
        """
        ranked = []

        for file_info in available_files:
            if file_info.get('is_dir', False):
                continue

            filename = file_info.get('name', '')
            similarity = self.calculate_similarity_score(target_filename, filename)

            if similarity['score'] >= min_score:
                ranked.append({
                    "filename": filename,
                    "full_path": file_info.get('path', ''),
                    "size": file_info.get('size', 0),
                    "modified": file_info.get('modified', ''),
                    "similarity": similarity
                })

        # Sort by score (highest first)
        ranked.sort(key=lambda x: x['similarity']['score'], reverse=True)

        return ranked

    def validate_file_equivalence(self, target_info: Dict, candidate_info: Dict) -> Dict[str, Any]:
        """
        Validate if two files are scientifically equivalent
        Returns validation result with risk assessment
        """
        validation = {
            "equivalent": False,
            "confidence": "low",
            "checks_passed": [],
            "checks_failed": [],
            "risk_level": RiskLevel.HIGH.value,
            "safe_to_replace": False
        }

        target_size = target_info.get('size', 0)
        candidate_size = candidate_info.get('size', 0)

        # Check 1: File size comparison
        if target_size > 0 and candidate_size > 0:
            size_diff_pct = abs(target_size - candidate_size) / max(target_size, candidate_size) * 100

            if size_diff_pct < 1:  # Within 1%
                validation['checks_passed'].append("size_match_exact")
            elif size_diff_pct < 5:  # Within 5%
                validation['checks_passed'].append("size_match_close")
            else:
                validation['checks_failed'].append(f"size_mismatch_{int(size_diff_pct)}pct")

        # Check 2: File extension match
        target_ext = os.path.splitext(target_info.get('filename', ''))[1]
        candidate_ext = os.path.splitext(candidate_info.get('filename', ''))[1]

        if target_ext.lower() == candidate_ext.lower():
            validation['checks_passed'].append("extension_match")
        else:
            validation['checks_failed'].append("extension_mismatch")

        # Check 3: Name similarity
        name_similarity = self.calculate_similarity_score(
            target_info.get('filename', ''),
            candidate_info.get('filename', '')
        )

        if name_similarity['confidence'] in ['very_high', 'high']:
            validation['checks_passed'].append("name_very_similar")
        elif name_similarity['confidence'] == 'medium':
            validation['checks_passed'].append("name_moderately_similar")
        else:
            validation['checks_failed'].append("name_dissimilar")

        # Determine overall validation
        passed_count = len(validation['checks_passed'])
        failed_count = len(validation['checks_failed'])

        if passed_count >= 2 and failed_count == 0:
            validation['equivalent'] = True
            validation['confidence'] = "high"
            validation['risk_level'] = RiskLevel.LOW.value
            validation['safe_to_replace'] = True
        elif passed_count >= 2 and failed_count == 1:
            validation['equivalent'] = True
            validation['confidence'] = "medium"
            validation['risk_level'] = RiskLevel.MEDIUM.value
            validation['safe_to_replace'] = False  # Requires approval
        else:
            validation['equivalent'] = False
            validation['confidence'] = "low"
            validation['risk_level'] = RiskLevel.HIGH.value
            validation['safe_to_replace'] = False

        return validation

    def determine_repair_strategy(self, missing_file: str, similar_files: List[Dict],
                                  workflow_context: Dict) -> Dict[str, Any]:
        """
        Determine best repair strategy based on analysis
        Returns strategy with risk assessment and steps
        """
        if not similar_files:
            return {
                "strategy": RepairStrategy.MANUAL_INTERVENTION.value,
                "risk_level": RiskLevel.CRITICAL.value,
                "confidence": 0.0,
                "reason": "No similar files found - data truly missing",
                "requires_approval": True,
                "auto_executable": False,
                "recommended_actions": [
                    "Verify the expected file path is correct",
                    "Check if file should be created by previous workflow step",
                    "Ensure input data is properly staged",
                    "Contact workflow administrator"
                ]
            }

        # Best match
        best_match = similar_files[0]
        similarity = best_match['similarity']

        # Strategy 1: High confidence typo fix
        if similarity['confidence'] in ['very_high', 'high'] and similarity['score'] >= 0.90:
            # Check if this is a generator issue or catalog issue
            workflow_generator = workflow_context.get('workflow_generator', {})

            if workflow_generator.get('path'):
                strategy = RepairStrategy.GENERATOR_FIX.value
                reason = "Fix typo in workflow generator to use correct filename"
            else:
                strategy = RepairStrategy.CATALOG_UPDATE.value
                reason = "Update replica catalog with correct filename"

            return {
                "strategy": strategy,
                "risk_level": RiskLevel.LOW.value,
                "confidence": similarity['score'],
                "reason": f"Very similar file found: {best_match['filename']} ({reason})",
                "requires_approval": False,
                "auto_executable": True,
                "best_match": best_match,
                "recommended_actions": self._get_strategy_steps(strategy, missing_file, best_match, workflow_context)
            }

        # Strategy 2: Medium confidence - requires validation
        elif similarity['confidence'] == 'medium' and similarity['score'] >= 0.70:
            return {
                "strategy": RepairStrategy.CATALOG_UPDATE.value,
                "risk_level": RiskLevel.MEDIUM.value,
                "confidence": similarity['score'],
                "reason": f"Similar file found but requires validation: {best_match['filename']}",
                "requires_approval": True,
                "auto_executable": False,
                "best_match": best_match,
                "recommended_actions": [
                    f"Validate if '{best_match['filename']}' can replace '{missing_file}'",
                    "Check file contents match expected format",
                    "Verify scientific data integrity",
                    "Update replica catalog if confirmed"
                ]
            }

        # Strategy 3: Low confidence - manual intervention
        else:
            return {
                "strategy": RepairStrategy.MANUAL_INTERVENTION.value,
                "risk_level": RiskLevel.HIGH.value,
                "confidence": similarity['score'],
                "reason": f"Potentially related files found but low confidence",
                "requires_approval": True,
                "auto_executable": False,
                "candidates": similar_files[:3],
                "recommended_actions": [
                    "Manual review required to determine correct file",
                    "Check workflow documentation for expected inputs",
                    "Verify data provenance",
                    "Contact data provider or workflow author"
                ]
            }

    def _get_strategy_steps(self, strategy: str, missing_file: str,
                           best_match: Dict, workflow_context: Dict) -> List[str]:
        """Generate specific action steps for repair strategy"""
        steps = []

        if strategy == RepairStrategy.GENERATOR_FIX.value:
            generator_path = workflow_context.get('workflow_generator', {}).get('path', 'workflow_generator.py')
            steps = [
                f"Locate workflow generator script: {generator_path}",
                f"Find reference to '{missing_file}' in generator",
                f"Update to use correct filename: '{best_match['filename']}'",
                "Regenerate workflow with corrected configuration",
                "Submit regenerated workflow"
            ]

        elif strategy == RepairStrategy.CATALOG_UPDATE.value:
            steps = [
                f"Identify replica catalog location",
                f"Add or update entry for '{missing_file}'",
                f"Point to actual file: {best_match['full_path']}",
                "Use pegasus-rc-client or update YAML directly",
                "Validate catalog with pegasus-plan --dax"
            ]

        elif strategy == RepairStrategy.SYMLINK_CREATE.value:
            target_dir = os.path.dirname(workflow_context.get('iwd', ''))
            steps = [
                f"Create symlink in expected location",
                f"ln -s {best_match['full_path']} {os.path.join(target_dir, missing_file)}",
                "Verify symlink points to correct file",
                "Retry workflow execution"
            ]

        return steps

    def parse_replica_catalog(self, catalog_content: str, catalog_format: str = "yaml") -> Dict[str, Any]:
        """
        Parse Pegasus replica catalog
        Supports YAML and simple text formats
        """
        replicas = []

        try:
            if catalog_format == "yaml":
                data = yaml.safe_load(catalog_content)

                # Pegasus 5.0+ format
                if 'replicas' in data:
                    for replica in data.get('replicas', []):
                        replicas.append({
                            "lfn": replica.get('lfn', ''),
                            "pfn": replica.get('pfn', ''),
                            "site": replica.get('site', 'local'),
                            "checksum": replica.get('checksum', {}),
                            "metadata": replica.get('metadata', {})
                        })

                # Check for pegasus section
                elif 'pegasus' in data:
                    pegasus_data = data.get('pegasus', {})
                    if 'replicas' in pegasus_data:
                        for replica in pegasus_data['replicas']:
                            replicas.append({
                                "lfn": replica.get('lfn', ''),
                                "pfn": replica.get('pfn', ''),
                                "site": replica.get('site', 'local')
                            })

            elif catalog_format == "text":
                # Simple text format: lfn pfn [site]
                for line in catalog_content.strip().split('\n'):
                    if line.strip() and not line.startswith('#'):
                        parts = line.split()
                        if len(parts) >= 2:
                            replicas.append({
                                "lfn": parts[0],
                                "pfn": parts[1],
                                "site": parts[2] if len(parts) > 2 else "local"
                            })

        except Exception as e:
            print(f"Error parsing replica catalog: {e}")

        return {
            "replicas": replicas,
            "count": len(replicas),
            "format": catalog_format
        }

    def find_replica_in_catalog(self, lfn: str, catalog: Dict) -> Optional[Dict]:
        """Find a specific replica entry in parsed catalog"""
        for replica in catalog.get('replicas', []):
            if replica['lfn'] == lfn:
                return replica
        return None

    def generate_pegasus_commands(self, strategy: str, missing_file: str,
                                 replacement_file: str, workflow_context: Dict) -> List[str]:
        """
        Generate proper Pegasus commands for replica fixes
        Avoids manual YAML editing
        """
        commands = []

        if strategy == RepairStrategy.CATALOG_UPDATE.value:
            # Use pegasus-rc-client to add replica
            site = workflow_context.get('execution_site', 'local')
            commands.append(
                f"pegasus-rc-client insert "
                f"--lfn {missing_file} "
                f"--pfn file://{replacement_file} "
                f"--site {site}"
            )

        elif strategy == RepairStrategy.GENERATOR_FIX.value:
            # Commands to regenerate workflow
            generator_path = workflow_context.get('workflow_generator', {}).get('path')
            if generator_path:
                commands.append(f"# Edit {generator_path} to fix filename")
                commands.append(f"# Then regenerate workflow:")
                commands.append(f"python {generator_path}")

        return commands

    def create_repair_plan(self, missing_file_path: str, directory_listing: List[Dict],
                          workflow_context: Dict) -> Dict[str, Any]:
        """
        Create comprehensive repair plan for missing replica
        This is the main entry point for replica problem solving
        """
        missing_filename = os.path.basename(missing_file_path)
        directory = os.path.dirname(missing_file_path)

        # Step 0: Detect workflow generator for better recommendations
        workflow_generator = self.detect_workflow_generator(workflow_context)
        if workflow_generator:
            workflow_context['workflow_generator'] = workflow_generator
            print(f"  ℹ️  Detected workflow generator: {workflow_generator['name']}")

        # Step 1: Rank similar files
        similar_files = self.rank_similar_files(missing_filename, directory_listing)

        # Step 2: Determine strategy
        strategy_info = self.determine_repair_strategy(
            missing_filename,
            similar_files,
            workflow_context
        )

        # Step 3: Generate commands if applicable
        commands = []
        if strategy_info.get('best_match') and strategy_info.get('auto_executable'):
            commands = self.generate_pegasus_commands(
                strategy_info['strategy'],
                missing_filename,
                strategy_info['best_match']['full_path'],
                workflow_context
            )

        # Step 4: Assemble comprehensive plan
        plan = {
            "problem_type": "missing_replica",
            "missing_file": missing_file_path,
            "directory_checked": directory,
            "files_found": len(directory_listing),
            "similar_files_count": len(similar_files),
            "strategy": strategy_info['strategy'],
            "risk_level": strategy_info['risk_level'],
            "confidence": strategy_info['confidence'],
            "requires_approval": strategy_info['requires_approval'],
            "auto_executable": strategy_info.get('auto_executable', False),
            "explanation": strategy_info['reason'],
            "similar_files": similar_files[:5],  # Top 5 matches
            "recommended_actions": strategy_info.get('recommended_actions', []),
            "commands": commands,
            "avoid_actions": [
                "DO NOT manually edit braindump.yml (generated file)",
                "DO NOT use yq/sed to modify YAML directly",
                "DO NOT assume files are equivalent without validation"
            ]
        }

        return plan


# Example usage
if __name__ == "__main__":
    helper = ReplicaHelper()

    # Test similarity scoring
    test_cases = [
        ("data1.json", "data.json"),
        ("data1.json", "data2.json"),
        ("workflow.yml", "workflow.yaml"),
        ("input_file.txt", "Input_File.txt"),
        ("train.csv", "test.csv")
    ]

    print("Similarity Scoring Tests:")
    print("=" * 80)
    for target, candidate in test_cases:
        result = helper.calculate_similarity_score(target, candidate)
        print(f"\nTarget: {target}")
        print(f"Candidate: {candidate}")
        print(f"Score: {result['score']} ({result['confidence']})")
        print(f"Reason: {result['reason']}")

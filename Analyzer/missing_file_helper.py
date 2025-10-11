"""
Smart Missing File Detection and Suggestion Helper
Detects missing file errors and suggests corrections using directory listings
"""

import os
import re
import requests
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher


class MissingFileHelper:
    """Helper to detect and suggest fixes for missing file errors"""

    def __init__(self, monitor_url: str = "http://localhost:8080"):
        self.monitor_url = monitor_url
        self._processed_workflows = {}  # Cache: workflow_id -> set of processed files

    def detect_missing_file_errors(self, analysis_result: Dict, logs: str) -> List[Dict]:
        """
        Detect missing file errors from analysis results and logs
        Returns list of missing file information
        """
        missing_files = []

        # Pattern 1: Direct "No such file or directory" errors
        pattern1 = re.compile(r"(?:reading from file|cannot access|failed to open)\s+([^\s:]+):\s*\(errno \d+\)\s*No such file", re.IGNORECASE)
        matches1 = pattern1.findall(logs)
        for file_path in matches1:
            missing_files.append({
                "file_path": file_path,
                "error_type": "no_such_file",
                "source": "logs"
            })

        # Pattern 2: Replica not found errors
        pattern2 = re.compile(r"replica.*not found|missing.*replica|(?:lfn|file).*(?:not|doesn't)\s+exist", re.IGNORECASE)
        if pattern2.search(logs):
            # Try to extract file paths from replica errors
            path_pattern = re.compile(r"(?:lfn|file|path)[:\s]+([^\s,]+)", re.IGNORECASE)
            for path in path_pattern.findall(logs):
                if path and not path.startswith(('http', 'ftp')):
                    missing_files.append({
                        "file_path": path,
                        "error_type": "replica_not_found",
                        "source": "logs"
                    })

        # Pattern 3: Check analysis problems for data/file errors
        problems = analysis_result.get('problems_and_solutions', [])
        for problem in problems:
            category = problem.get('category', '').lower()
            description = problem.get('description', '').lower()

            if 'data' in category or 'file' in description or 'missing' in description:
                # Try to extract file paths from problem description
                path_pattern = re.compile(r"['\"]([/\w\-\.]+)['\"]")
                paths = path_pattern.findall(problem.get('description', ''))
                for path in paths:
                    if '/' in path:  # Looks like a file path
                        missing_files.append({
                            "file_path": path,
                            "error_type": "data_problem",
                            "source": "analysis",
                            "problem": problem
                        })

        return missing_files

    def request_directory_listing(self, directory_path: str, workflow_id: str = "") -> Optional[List[Dict]]:
        """
        Request directory listing from Monitor
        Returns list of file info or None on error
        """
        try:
            url = f"{self.monitor_url}/api/files/list-directory"
            response = requests.post(url, json={
                "directory_path": directory_path,
                "workflow_id": workflow_id,
                "requester": "analyzer_missing_file_helper",
                "pattern": "*"  # Get all files
            }, timeout=5)

            if response.status_code == 200:
                data = response.json()
                return data.get('files', [])
            else:
                print(f"⚠️  Failed to list directory {directory_path}: {response.status_code}")
                return None

        except Exception as e:
            print(f"⚠️  Error requesting directory listing: {e}")
            return None

    def find_similar_filenames(self, target_filename: str, available_files: List[Dict], threshold: float = 0.6) -> List[Tuple[str, float]]:
        """
        Find similar filenames using fuzzy matching
        Returns list of (filename, similarity_score) sorted by score (highest first)
        """
        similarities = []
        target_lower = target_filename.lower()

        for file_info in available_files:
            if file_info.get('is_dir', False):
                continue  # Skip directories

            filename = file_info.get('name', '')
            filename_lower = filename.lower()

            # Calculate similarity
            similarity = SequenceMatcher(None, target_lower, filename_lower).ratio()

            # Bonus for exact case-insensitive match
            if target_lower == filename_lower:
                similarity = 1.0

            # Bonus for same extension
            target_ext = os.path.splitext(target_filename)[1]
            file_ext = os.path.splitext(filename)[1]
            if target_ext and file_ext and target_ext.lower() == file_ext.lower():
                similarity += 0.1

            # Only include if above threshold
            if similarity >= threshold:
                similarities.append((filename, similarity, file_info.get('path')))

        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities

    def enhance_analysis_with_suggestions(self, analysis_result: Dict, logs: str, workflow_id: str = "") -> Dict:
        """
        Main method: Detect missing files and enhance analysis with smart suggestions
        Only runs when missing file errors are detected (not in a loop)
        """
        # Check if we should run this enhancement
        missing_files = self.detect_missing_file_errors(analysis_result, logs)

        if not missing_files:
            # No missing file errors detected - skip enhancement
            return analysis_result

        # Initialize workflow cache if needed
        if workflow_id not in self._processed_workflows:
            self._processed_workflows[workflow_id] = set()

        # Filter out already processed files
        new_missing_files = [
            mf for mf in missing_files
            if mf.get('file_path') not in self._processed_workflows[workflow_id]
        ]

        if not new_missing_files:
            # All files already processed - skip to prevent loop
            print(f"⏭️  All missing files already processed for {workflow_id}, skipping suggestions")
            return analysis_result

        print(f"🔍 Detected {len(new_missing_files)} NEW missing file error(s)")

        # Track suggestions
        suggestions_added = 0

        # Process each missing file
        for missing_info in new_missing_files[:3]:  # Limit to first 3 to avoid too many requests
            file_path = missing_info.get('file_path', '')
            if not file_path or not os.path.isabs(file_path):
                continue

            # Mark as processed
            self._processed_workflows[workflow_id].add(file_path)

            # Extract directory and filename
            directory = os.path.dirname(file_path)
            target_filename = os.path.basename(file_path)

            print(f"📂 Checking directory: {directory}")
            print(f"🎯 Looking for: {target_filename}")

            # Request directory listing
            files = self.request_directory_listing(directory, workflow_id)

            if not files:
                # Directory listing failed or empty - report this
                print(f"⚠️  Directory not accessible or empty: {directory}")
                enhanced_solution = self._create_not_found_solution(
                    missing_info, target_filename, directory, directory_accessible=False
                )
                problems = analysis_result.get('problems_and_solutions', [])
                problems.append(enhanced_solution)
                analysis_result['problems_and_solutions'] = problems
                suggestions_added += 1
                continue

            # Find similar filenames
            similar = self.find_similar_filenames(target_filename, files, threshold=0.6)

            if similar:
                print(f"✨ Found {len(similar)} similar file(s)")

                # Create enhanced problem/solution with suggestions
                enhanced_solution = self._create_enhanced_solution(
                    missing_info, target_filename, similar, directory
                )

                # Add to analysis result
                problems = analysis_result.get('problems_and_solutions', [])
                problems.append(enhanced_solution)
                analysis_result['problems_and_solutions'] = problems

                suggestions_added += 1
            else:
                # No similar files found - report directory contents
                print(f"❌ No similar files found in {directory}")
                print(f"   Directory contains {len(files)} file(s), but none match '{target_filename}'")
                enhanced_solution = self._create_not_found_solution(
                    missing_info, target_filename, directory, directory_accessible=True, file_count=len(files)
                )
                problems = analysis_result.get('problems_and_solutions', [])
                problems.append(enhanced_solution)
                analysis_result['problems_and_solutions'] = problems
                suggestions_added += 1

        # Add metadata
        if suggestions_added > 0:
            analysis_result['missing_file_suggestions'] = {
                "detected": len(missing_files),
                "suggestions_added": suggestions_added,
                "helper_used": True
            }
            print(f"✅ Added {suggestions_added} smart suggestion(s)")

        return analysis_result

    def _create_enhanced_solution(self, missing_info: Dict, target_filename: str,
                                   similar_files: List[Tuple], directory: str) -> Dict:
        """Create an enhanced problem/solution with file suggestions"""

        # Build suggestion text
        suggestions_text = []
        for filename, score, full_path in similar_files[:3]:  # Top 3 matches
            score_pct = int(score * 100)
            suggestions_text.append(f"  • {filename} (similarity: {score_pct}%)")

        suggestions_str = "\n".join(suggestions_text)

        # Determine likely issue
        if similar_files[0][1] > 0.9:
            issue_type = "The file name has a slight typo or case mismatch"
        elif similar_files[0][1] > 0.7:
            issue_type = "The file name is similar but not exact"
        else:
            issue_type = "There are potentially related files in the directory"

        return {
            "problem": f"Missing File: {target_filename}",
            "description": f"The file '{target_filename}' was not found at the expected location '{directory}'. {issue_type}.",
            "solution": f"Check the file name carefully. The following similar files were found in the same directory:\n\n{suggestions_str}\n\nYou may need to:\n1. Correct the file name in your workflow configuration\n2. Rename the actual file to match the expected name\n3. Check for case sensitivity issues (especially on Linux systems)",
            "priority": "high",
            "category": "data_error",
            "smart_suggestion": True,
            "similar_files": [
                {"name": f[0], "similarity": f[1], "path": f[2]}
                for f in similar_files[:3]
            ]
        }

    def _create_not_found_solution(self, missing_info: Dict, target_filename: str,
                                     directory: str, directory_accessible: bool, file_count: int = 0) -> Dict:
        """Create a conclusive report when file not found and no similar alternatives exist"""

        full_path = os.path.join(directory, target_filename)

        if not directory_accessible:
            # Directory doesn't exist or couldn't be accessed
            description = (
                f"The workflow expected to find '{target_filename}' at '{full_path}', "
                f"but the directory '{directory}' could not be accessed or does not exist."
            )
            solution = (
                f"The workflow could not find the file at the expected location.\n\n"
                f"Possible causes:\n"
                f"1. The directory path '{directory}' does not exist\n"
                f"2. The workflow does not have permission to access this directory\n"
                f"3. The path is incorrect in the workflow configuration\n\n"
                f"Actions needed:\n"
                f"• Verify the directory path exists on the execution node\n"
                f"• Check file permissions and ownership\n"
                f"• Update the workflow configuration with the correct path\n"
                f"• Ensure input files are properly staged before workflow execution"
            )
        else:
            # Directory exists but file not found and no similar matches
            description = (
                f"The workflow expected to find '{target_filename}' at '{full_path}', "
                f"but the file does not exist. The directory was checked and contains {file_count} file(s), "
                f"but none match the expected filename (no similar names found)."
            )
            solution = (
                f"The file '{target_filename}' was not found in the directory.\n\n"
                f"Directory checked: {directory}\n"
                f"Files found in directory: {file_count}\n"
                f"Similar matches: None (checked for typos and case variations)\n\n"
                f"Actions needed:\n"
                f"1. Verify the exact filename - it may have been misnamed\n"
                f"2. Check if the file was supposed to be created by a previous workflow step\n"
                f"3. Ensure the workflow configuration specifies the correct filename\n"
                f"4. If this is a replica/input file, verify it was properly registered in the replica catalog\n"
                f"5. Check if the file needs to be manually created or transferred to this location"
            )

        return {
            "problem": f"Missing File: {target_filename}",
            "description": description,
            "solution": solution,
            "priority": "high",
            "category": "data_error",
            "smart_suggestion": True,
            "file_not_found": True,
            "directory_checked": directory,
            "directory_accessible": directory_accessible,
            "files_in_directory": file_count,
            "similar_files": []
        }


# Example usage
if __name__ == "__main__":
    # Test the helper
    helper = MissingFileHelper()

    # Mock analysis result with a missing file error
    test_analysis = {
        "problems_and_solutions": [
            {
                "problem": "File not found",
                "description": "Cannot read file '/path/to/data.txt'",
                "category": "data_error"
            }
        ]
    }

    test_logs = """
    Error: reading from file /var/lib/condor/execute/dir_7822/falcon-7b.zip: (errno 2) No such file or directory
    """

    # Enhance analysis
    enhanced = helper.enhance_analysis_with_suggestions(test_analysis, test_logs, "test-workflow")

    print("Enhanced analysis:", enhanced)

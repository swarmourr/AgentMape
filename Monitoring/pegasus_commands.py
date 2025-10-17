"""
Pegasus WMS Command Execution Module
Provides direct access to Pegasus commands for real-time workflow data
"""

import subprocess
import json
import re
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PegasusCommandExecutor:
    """Executes Pegasus WMS commands and parses output"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._command_cache = {}  # Cache recent command results
        self._cache_ttl = 10  # Cache for 10 seconds

    def execute_command(self, command: List[str], cache_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a shell command and return structured result

        Args:
            command: List of command parts (e.g., ['pegasus-status', '/path/to/submit'])
            cache_key: Optional key for caching (workflow_id + command type)

        Returns:
            Dict with 'success', 'output', 'error', 'exit_code'
        """
        # Check cache first
        if cache_key and cache_key in self._command_cache:
            cached_result, cached_time = self._command_cache[cache_key]
            age = (datetime.now() - cached_time).total_seconds()
            if age < self._cache_ttl:
                logger.info(f"Using cached result for {cache_key} (age: {age:.1f}s)")
                return cached_result

        try:
            logger.info(f"Executing: {' '.join(command)}")

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=os.getcwd()
            )

            response = {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.returncode,
                "command": ' '.join(command),
                "timestamp": datetime.now().isoformat()
            }

            # Cache successful results
            if cache_key and response['success']:
                self._command_cache[cache_key] = (response, datetime.now())

            return response

        except subprocess.TimeoutExpired:
            logger.error(f"Command timeout: {' '.join(command)}")
            return {
                "success": False,
                "output": "",
                "error": f"Command timed out after {self.timeout} seconds",
                "exit_code": -1,
                "command": ' '.join(command),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": -1,
                "command": ' '.join(command),
                "timestamp": datetime.now().isoformat()
            }

    def get_workflow_status(self, submit_dir: str) -> Dict[str, Any]:
        """
        Execute pegasus-status command

        Returns workflow state, progress, job counts
        """
        cache_key = f"{submit_dir}_status"
        result = self.execute_command(
            ['pegasus-status', submit_dir],
            cache_key=cache_key
        )

        if not result['success']:
            return {
                "success": False,
                "error": result['error'],
                "raw_output": result['output']
            }

        # Parse pegasus-status output
        output = result['output']
        parsed = self._parse_pegasus_status(output)

        return {
            "success": True,
            "status": parsed,
            "raw_output": output,
            "timestamp": result['timestamp']
        }

    def _parse_pegasus_status(self, output: str) -> Dict[str, Any]:
        """Parse pegasus-status output into structured data"""
        status = {
            "state": "unknown",
            "percent_done": 0,
            "total_jobs": 0,
            "succeeded": 0,
            "failed": 0,
            "running": 0,
            "ready": 0,
            "queued": 0,
            "unsubmitted": 0
        }

        # Extract state (e.g., "Status: Running")
        state_match = re.search(r'Status:\s+(\w+)', output, re.IGNORECASE)
        if state_match:
            status['state'] = state_match.group(1)

        # Extract progress (e.g., "Progress: 45%")
        progress_match = re.search(r'Progress:\s+(\d+(?:\.\d+)?)%', output, re.IGNORECASE)
        if progress_match:
            status['percent_done'] = float(progress_match.group(1))

        # Extract job counts from summary section
        # Example: "Total jobs    : 10 (100.0%)"
        patterns = {
            'total_jobs': r'Total\s+jobs\s*:\s*(\d+)',
            'succeeded': r'(?:jobs\s+succeeded|# jobs succeeded)\s*:\s*(\d+)',
            'failed': r'(?:jobs\s+failed|# jobs failed)\s*:\s*(\d+)',
            'running': r'(?:jobs\s+running|# jobs running)\s*:\s*(\d+)',
            'ready': r'(?:jobs\s+ready|# jobs ready)\s*:\s*(\d+)',
            'queued': r'(?:jobs\s+queued|# jobs queued)\s*:\s*(\d+)',
            'unsubmitted': r'(?:jobs\s+unsubmitted|# jobs unsubmitted)\s*:\s*(\d+)'
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                status[key] = int(match.group(1))

        # Also try parsing tabular summary format
        # Example format:
        # UNREADY READY  PRE  IN_Q  POST  DONE  FAIL %DONE  STATE  DAGNAME
        #    6      0     0    1     0     1     0    12.5 Running falcon-7b-0.dag
        table_match = re.search(
            r'UNREADY\s+READY\s+PRE\s+IN_Q\s+POST\s+DONE\s+FAIL\s+%DONE\s+STATE\s+DAGNAME\s*\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\w+)\s+(.+)',
            output,
            re.MULTILINE
        )

        if table_match:
            unready = int(table_match.group(1))
            ready = int(table_match.group(2))
            pre = int(table_match.group(3))
            in_q = int(table_match.group(4))
            post = int(table_match.group(5))
            done = int(table_match.group(6))
            fail = int(table_match.group(7))
            percent_done = float(table_match.group(8))
            state = table_match.group(9)

            logger.info(f"Parsed tabular status: {unready} UNREADY, {ready} READY, {in_q} IN_Q, {done} DONE, {fail} FAIL")

            # Update status with tabular data
            status['state'] = state.lower()
            status['percent_done'] = percent_done
            status['unsubmitted'] = unready
            status['ready'] = ready
            status['queued'] = in_q  # IN_Q means queued
            status['succeeded'] = done
            status['failed'] = fail
            status['running'] = pre + post  # PRE and POST are execution states
            status['total_jobs'] = unready + ready + pre + in_q + post + done + fail

        return status

    def get_workflow_statistics(self, submit_dir: str, stat_type: str = "summary") -> Dict[str, Any]:
        """
        Execute pegasus-statistics command

        Args:
            submit_dir: Workflow submit directory
            stat_type: Type of stats (summary, all, workflow, jobs)

        Returns detailed workflow statistics
        """
        cache_key = f"{submit_dir}_statistics_{stat_type}"

        # Build command based on stat type
        if stat_type == "all":
            command = ['pegasus-statistics', '-s', 'all', submit_dir]
        elif stat_type == "workflow":
            command = ['pegasus-statistics', '-s', 'workflow', submit_dir]
        elif stat_type == "jobs":
            command = ['pegasus-statistics', '-s', 'jobs', submit_dir]
        else:  # summary
            command = ['pegasus-statistics', '-s', 'summary', submit_dir]

        result = self.execute_command(command, cache_key=cache_key)

        if not result['success']:
            return {
                "success": False,
                "error": result['error'],
                "raw_output": result['output']
            }

        # Parse statistics output
        output = result['output']
        parsed = self._parse_pegasus_statistics(output, stat_type)

        return {
            "success": True,
            "statistics": parsed,
            "stat_type": stat_type,
            "raw_output": output,
            "timestamp": result['timestamp']
        }

    def _parse_pegasus_statistics(self, output: str, stat_type: str) -> Dict[str, Any]:
        """Parse pegasus-statistics output into structured data"""
        stats = {
            "summary": {},
            "workflow_stats": {},
            "job_stats": []
        }

        # Extract workflow cumulative times
        # Example: "Workflow wall time : 123.45 sec"
        time_patterns = {
            'workflow_wall_time': r'Workflow\s+wall\s+time\s*:\s*([\d.]+)',
            'workflow_cpu_time': r'Workflow\s+(?:cumulative\s+)?CPU\s+time\s*:\s*([\d.]+)',
            'workflow_cumulative_time': r'Cumulative\s+job\s+wall\s+time\s*:\s*([\d.]+)'
        }

        for key, pattern in time_patterns.items():
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                stats['workflow_stats'][key] = float(match.group(1))

        # Extract job-level statistics if available
        # This would need more sophisticated parsing based on actual pegasus-statistics output format
        # For now, store raw sections

        return stats

    def get_workflow_analyzer_output(self, submit_dir: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Execute pegasus-analyzer command to get root cause analysis

        This is the KEY command for getting root cause vs cascade errors!

        Args:
            submit_dir: Workflow submit directory
            verbose: Use verbose mode for detailed analysis

        Returns analysis with root causes identified
        """
        cache_key = f"{submit_dir}_analyzer"

        command = ['pegasus-analyzer']
        if verbose:
            command.append('-v')
        command.extend(['-t', submit_dir])

        result = self.execute_command(command, cache_key=cache_key)

        if not result['success']:
            return {
                "success": False,
                "error": result['error'],
                "raw_output": result['output']
            }

        # Parse analyzer output
        output = result['output']
        parsed = self._parse_pegasus_analyzer(output)

        return {
            "success": True,
            "analysis": parsed,
            "raw_output": output,
            "timestamp": result['timestamp']
        }

    def _parse_pegasus_analyzer(self, output: str) -> Dict[str, Any]:
        """
        Parse pegasus-analyzer output to extract root causes

        Pegasus-analyzer intelligently identifies:
        - Root cause failures (parent errors)
        - Cascade failures (caused by parent)
        - Held jobs with reasons
        - Failed jobs with error types
        """
        analysis = {
            "workflow_status": "unknown",
            "total_jobs": 0,
            "succeeded": 0,
            "failed": 0,
            "held": 0,
            "unsubmitted": 0,
            "failed_jobs": [],
            "held_jobs": [],
            "root_causes": [],
            "has_failures": False
        }

        # Extract summary statistics
        summary_match = re.search(
            r'Total\s+jobs\s*:\s*(\d+).*?'
            r'#\s+jobs\s+succeeded\s*:\s*(\d+).*?'
            r'#\s+jobs\s+failed\s*:\s*(\d+).*?'
            r'#\s+jobs\s+held\s*:\s*(\d+)',
            output,
            re.DOTALL
        )

        if summary_match:
            analysis['total_jobs'] = int(summary_match.group(1))
            analysis['succeeded'] = int(summary_match.group(2))
            analysis['failed'] = int(summary_match.group(3))
            analysis['held'] = int(summary_match.group(4))

        # Extract workflow status
        status_match = re.search(r'Workflow\s+Status\s*:\s*(\w+)', output, re.IGNORECASE)
        if status_match:
            analysis['workflow_status'] = status_match.group(1)

        # Parse failed jobs section
        failed_section = re.search(
            r'\*+Failing\s+jobs\'?\s+details\*+\n(.*?)(?:\n\*+|$)',
            output,
            re.DOTALL | re.IGNORECASE
        )

        if failed_section:
            analysis['has_failures'] = True
            failed_text = failed_section.group(1)

            # Extract individual failed jobs
            job_blocks = re.finditer(
                r'={20,}([^=]+)={20,}\n(.*?)(?=\n={20,}|$)',
                failed_text,
                re.DOTALL
            )

            for job_match in job_blocks:
                job_name = job_match.group(1).strip()
                job_details = job_match.group(2)

                # Extract error information
                error_info = {
                    "job_name": job_name,
                    "error_type": "unknown",
                    "error_message": "",
                    "is_root_cause": False
                }

                # Check for specific error patterns
                if 'SyntaxError' in job_details:
                    error_info['error_type'] = 'syntax_error'
                    error_info['is_root_cause'] = True
                elif 'MemoryError' in job_details or 'cgroup memory limit' in job_details:
                    error_info['error_type'] = 'memory_exceeded'
                    error_info['is_root_cause'] = True
                elif 'No such file' in job_details or 'FileNotFoundError' in job_details:
                    error_info['error_type'] = 'file_not_found'
                    error_info['is_root_cause'] = True
                elif 'POST_SCRIPT_FAILED' in job_details:
                    error_info['error_type'] = 'post_script_failed'
                    # This might be cascade - check context
                elif 'Transfer failure' in job_details:
                    error_info['error_type'] = 'transfer_failed'

                # Extract first error line as message
                error_lines = job_details.strip().split('\n')
                if error_lines:
                    error_info['error_message'] = error_lines[0][:200]

                analysis['failed_jobs'].append(error_info)

                # Add to root causes if identified
                if error_info['is_root_cause']:
                    analysis['root_causes'].append({
                        "job": job_name,
                        "type": error_info['error_type'],
                        "message": error_info['error_message']
                    })

        # Parse held jobs section
        held_section = re.search(
            r'\*+Held\s+jobs\'?\s+details\*+\n(.*?)(?:\n\*+|$)',
            output,
            re.DOTALL | re.IGNORECASE
        )

        if held_section:
            held_text = held_section.group(1)

            # Extract individual held jobs
            job_blocks = re.finditer(
                r'={20,}([^=]+)={20,}\n(.*?)(?=\n={20,}|$)',
                held_text,
                re.DOTALL
            )

            for job_match in job_blocks:
                job_name = job_match.group(1).strip()
                job_details = job_match.group(2)

                held_info = {
                    "job_name": job_name,
                    "hold_reason": "unknown",
                    "details": job_details[:500]  # First 500 chars
                }

                # Extract hold reason
                reason_match = re.search(r'Hold\s+reason\s*:\s*(.+)', job_details, re.IGNORECASE)
                if reason_match:
                    held_info['hold_reason'] = reason_match.group(1).strip()

                analysis['held_jobs'].append(held_info)

        return analysis

    def get_workflow_metadata(self, submit_dir: str) -> Dict[str, Any]:
        """
        Read braindump.yml for workflow metadata
        (Not a command, but useful supplementary info)
        """
        braindump_path = os.path.join(submit_dir, 'braindump.yml')

        if not os.path.exists(braindump_path):
            return {
                "success": False,
                "error": "braindump.yml not found"
            }

        try:
            import yaml
            with open(braindump_path, 'r') as f:
                metadata = yaml.safe_load(f)

            return {
                "success": True,
                "metadata": metadata,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_workflow_jobs(self, submit_dir: str) -> Dict[str, Any]:
        """
        Get workflow jobs structure using pegasus-status --long

        Returns job list with states, dependencies, and execution info
        """
        cache_key = f"{submit_dir}_jobs"

        command = ['pegasus-status', '--long', '--noqueue', submit_dir]
        result = self.execute_command(command, cache_key=cache_key)

        if not result['success']:
            return {
                "success": False,
                "error": result['error'],
                "raw_output": result['output']
            }

        # Parse job information
        output = result['output']
        parsed = self._parse_pegasus_jobs(output)

        return {
            "success": True,
            "jobs": parsed,
            "raw_output": output,
            "timestamp": result['timestamp']
        }

    def _parse_pegasus_jobs(self, output: str) -> List[Dict[str, Any]]:
        """Parse pegasus-status --long output to extract job information"""
        jobs = []

        # First try to parse individual job lines (detailed format)
        # Example format:
        # UNRDY  preprocess_ID0000001
        # RUN    process_ID0000002
        # POST   merge_ID0000003
        # DONE   finalize_ID0000004

        job_pattern = re.compile(r'^\s*(UNRDY|READY|PRE|SUBMIT|RUN|POST|DONE|FAIL|ERR|HELD)\s+([^\s]+)', re.MULTILINE)

        for match in job_pattern.finditer(output):
            state = match.group(1).strip()
            job_name = match.group(2).strip()

            # Map Pegasus states to standard states
            state_map = {
                'UNRDY': 'unsubmitted',
                'READY': 'ready',
                'PRE': 'pre_script',
                'SUBMIT': 'queued',
                'RUN': 'running',
                'POST': 'post_script',
                'DONE': 'success',
                'FAIL': 'failed',
                'ERR': 'failed',
                'HELD': 'held'
            }

            jobs.append({
                "job_name": job_name,
                "state": state_map.get(state, state.lower()),
                "raw_state": state,
                "job_type": self._infer_job_type(job_name)
            })

        # If no jobs found, try parsing tabular summary format
        # Example format:
        # UNREADY READY  PRE  IN_Q  POST  DONE  FAIL %DONE  STATE  DAGNAME
        #    6      0     0    1     0     1     0    12.5 Running falcon-7b-0.dag
        if not jobs:
            logger.info("No individual jobs found, parsing tabular summary format")

            # Find the summary table (header line with UNREADY, READY, etc.)
            table_match = re.search(
                r'UNREADY\s+READY\s+PRE\s+IN_Q\s+POST\s+DONE\s+FAIL\s+%DONE\s+STATE\s+DAGNAME\s*\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\w+)\s+(.+)',
                output,
                re.MULTILINE
            )

            if table_match:
                unready = int(table_match.group(1))
                ready = int(table_match.group(2))
                pre = int(table_match.group(3))
                in_q = int(table_match.group(4))
                post = int(table_match.group(5))
                done = int(table_match.group(6))
                fail = int(table_match.group(7))
                percent_done = float(table_match.group(8))
                state = table_match.group(9)
                dagname = table_match.group(10).strip()

                logger.info(f"Parsed tabular format: {unready} UNREADY, {ready} READY, {in_q} IN_Q, {done} DONE, {fail} FAIL")

                # Create synthetic job entries based on counts
                job_id = 1
                for i in range(unready):
                    jobs.append({
                        "job_name": f"{dagname}_unready_{job_id}",
                        "state": "unsubmitted",
                        "raw_state": "UNREADY",
                        "job_type": "compute"
                    })
                    job_id += 1

                for i in range(ready):
                    jobs.append({
                        "job_name": f"{dagname}_ready_{job_id}",
                        "state": "ready",
                        "raw_state": "READY",
                        "job_type": "compute"
                    })
                    job_id += 1

                for i in range(pre):
                    jobs.append({
                        "job_name": f"{dagname}_pre_{job_id}",
                        "state": "pre_script",
                        "raw_state": "PRE",
                        "job_type": "compute"
                    })
                    job_id += 1

                for i in range(in_q):
                    jobs.append({
                        "job_name": f"{dagname}_queued_{job_id}",
                        "state": "queued",
                        "raw_state": "IN_Q",
                        "job_type": "compute"
                    })
                    job_id += 1

                for i in range(post):
                    jobs.append({
                        "job_name": f"{dagname}_post_{job_id}",
                        "state": "post_script",
                        "raw_state": "POST",
                        "job_type": "compute"
                    })
                    job_id += 1

                for i in range(done):
                    jobs.append({
                        "job_name": f"{dagname}_done_{job_id}",
                        "state": "success",
                        "raw_state": "DONE",
                        "job_type": "compute"
                    })
                    job_id += 1

                for i in range(fail):
                    jobs.append({
                        "job_name": f"{dagname}_failed_{job_id}",
                        "state": "failed",
                        "raw_state": "FAIL",
                        "job_type": "compute"
                    })
                    job_id += 1

                logger.info(f"Created {len(jobs)} synthetic job entries from tabular summary")

        return jobs

    def _infer_job_type(self, job_name: str) -> str:
        """Infer job type from job name"""
        name_lower = job_name.lower()

        if 'stage_in' in name_lower or 'stagein' in name_lower:
            return 'stage_in'
        elif 'stage_out' in name_lower or 'stageout' in name_lower:
            return 'stage_out'
        elif 'register' in name_lower:
            return 'register'
        elif 'cleanup' in name_lower:
            return 'cleanup'
        else:
            return 'compute'

    def clear_cache(self):
        """Clear command result cache"""
        self._command_cache.clear()
        logger.info("Cleared Pegasus command cache")


# Example usage
if __name__ == "__main__":
    executor = PegasusCommandExecutor()

    # Test with a submit directory
    submit_dir = "/home/hsafri/LLM-Fine-Tune/generated_workflows/hsafri/pegasus/falcon-7b/run0048"

    print("=" * 80)
    print("TESTING PEGASUS COMMANDS")
    print("=" * 80)

    # Test status
    print("\n1. pegasus-status:")
    status_result = executor.get_workflow_status(submit_dir)
    print(json.dumps(status_result, indent=2))

    # Test analyzer (ROOT CAUSE ANALYSIS)
    print("\n2. pegasus-analyzer (ROOT CAUSE DETECTION):")
    analyzer_result = executor.get_workflow_analyzer_output(submit_dir)
    print(json.dumps(analyzer_result['analysis'], indent=2))

    if analyzer_result['analysis']['root_causes']:
        print("\n🎯 ROOT CAUSES FOUND:")
        for rc in analyzer_result['analysis']['root_causes']:
            print(f"  • {rc['job']}: {rc['type']} - {rc['message']}")

    # Test statistics
    print("\n3. pegasus-statistics:")
    stats_result = executor.get_workflow_statistics(submit_dir, "summary")
    print(json.dumps(stats_result['statistics'], indent=2))

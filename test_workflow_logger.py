#!/usr/bin/env python3
"""
Test script for workflow-specific interaction logger
Demonstrates creating a separate database for a workflow
"""

import sys
import os
import time

# Add Analyzer directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Analyzer'))

from workflow_interaction_logger import get_workflow_logger, close_workflow_logger

def test_workflow_logging():
    """Test the workflow-specific logger"""

    # Use a test workflow ID
    workflow_id = "test-workflow-12345"

    print(f"\n{'='*80}")
    print(f"Testing Workflow-Specific Logger for: {workflow_id}")
    print(f"{'='*80}\n")

    # Create logger for this workflow
    wf_logger = get_workflow_logger(workflow_id)

    try:
        # 1. Log analysis start event
        print("1. Logging analysis start event...")
        wf_logger.log_event("analysis_start", {
            "workflow_id": workflow_id,
            "workflow_dir": "/home/test/workflows/run001",
            "analysis_type": "failed"
        })

        # 2. Log some print statements
        print("2. Logging print statements...")
        wf_logger.log_print("Starting analysis for workflow")
        wf_logger.log_print("Loading workflow data...")
        wf_logger.log_print("Preparing LLM prompt...", level="info")

        # 3. Log JSON data
        print("3. Logging JSON data...")
        workflow_data = {
            "jobs": ["job1", "job2", "job3"],
            "status": "failed",
            "transformations": ["transform1", "transform2"]
        }
        wf_logger.log_json(workflow_data, label="workflow_yaml")

        # 4. Log LLM request
        print("4. Logging LLM request...")
        test_prompt = """Given the following Pegasus workflow failure logs:

        Workflow Status: failed
        Total jobs: 34
        Jobs failed: 1

        Analyze the error and provide solutions."""

        interaction_id = wf_logger.log_llm_request(
            prompt=test_prompt,
            metadata={
                "attempt": 1,
                "max_retries": 3,
                "ollama_model": "llama3.3:latest",
                "analysis_type": "failed"
            }
        )

        # Simulate LLM call
        print("5. Simulating LLM call...")
        time.sleep(0.5)  # Simulate delay

        # 6. Log LLM response
        print("6. Logging LLM response...")
        test_response = """{
            "problems_and_solutions": [
                {
                    "problem": "Memory limit exceeded",
                    "solution": "Increase memory allocation to 2048 MB",
                    "priority": "high"
                }
            ],
            "confidence_score": 0.95
        }"""

        parsed_result = {
            "problems_and_solutions": [
                {
                    "problem": "Memory limit exceeded",
                    "solution": "Increase memory allocation to 2048 MB",
                    "priority": "high"
                }
            ],
            "confidence_score": 0.95
        }

        wf_logger.log_llm_response(
            interaction_id=interaction_id,
            response=test_response,
            success=True,
            latency_ms=523.45,
            parsed_result=parsed_result
        )

        # 7. Log final result
        print("7. Logging final result...")
        final_result = {
            "workflow_id": workflow_id,
            "analysis_type": "failed",
            "total_issues": 1,
            "problems_and_solutions": parsed_result["problems_and_solutions"],
            "confidence_score": 0.95
        }
        wf_logger.log_json(final_result, label="final_analysis_result")

        # 8. Log completion event
        print("8. Logging completion event...")
        wf_logger.log_event("analysis_complete", {
            "success": True,
            "problems_found": 1,
            "total_latency_ms": 523.45
        })

        # Get summary
        summary = wf_logger.get_session_summary()

        print(f"\n{'='*80}")
        print("SESSION SUMMARY")
        print(f"{'='*80}")
        print(f"Workflow ID: {summary['workflow_id']}")
        print(f"Session ID: {summary['session_id']}")
        print(f"Database: {summary['database_path']}")
        print(f"\nCounts:")
        print(f"  - LLM Interactions: {summary['counts']['llm_interactions']}")
        print(f"  - Outputs: {summary['counts']['outputs']}")
        print(f"  - Events: {summary['counts']['events']}")
        print(f"\nLLM Stats:")
        print(f"  - Total: {summary['llm_stats']['total']}")
        print(f"  - Successful: {summary['llm_stats']['successful']}")
        print(f"  - Success Rate: {summary['llm_stats']['success_rate']:.1f}%")
        print(f"  - Avg Latency: {summary['llm_stats']['average_latency_ms']:.2f}ms")
        print(f"{'='*80}\n")

    finally:
        # Close the logger
        close_workflow_logger(workflow_id)

    # Show where the database was created
    db_path = f"workflow_logs/{workflow_id}/interactions.json"
    print(f"✅ Database created at: {db_path}")
    print(f"\nTo view the database:")
    print(f"  cat {db_path} | python3 -m json.tool")
    print(f"\nOr with jq:")
    print(f"  cat {db_path} | jq .")
    print(f"\nOr with Python:")
    print(f"  python3 -c \"from tinydb import TinyDB; db = TinyDB('{db_path}'); print('Tables:', db.tables())\"")
    print()


if __name__ == "__main__":
    test_workflow_logging()

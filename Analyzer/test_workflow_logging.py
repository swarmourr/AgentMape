#!/usr/bin/env python3
"""
Test script to verify workflow logging integration
"""
import sys
sys.path.insert(0, '.')

from workflow_interaction_logger import get_workflow_logger, close_workflow_logger

def test_workflow_logger():
    """Test the workflow logger with a sample workflow"""

    print("\n" + "="*80)
    print("TESTING WORKFLOW INTERACTION LOGGER")
    print("="*80)

    # Test workflow ID
    test_workflow_id = "test_workflow_123"

    print(f"\n1. Initializing logger for workflow: {test_workflow_id}")
    wf_logger = get_workflow_logger(test_workflow_id)

    print("\n2. Logging analysis start event...")
    wf_logger.log_event("analysis_started", {"analysis_type": "failed"})

    print("\n3. Logging LLM request...")
    interaction_id = wf_logger.log_llm_request(
        prompt="Analyze this workflow failure...",
        metadata={
            "attempt": 1,
            "max_retries": 3,
            "ollama_model": "llama3.3:latest",
            "analysis_type": "failed",
            "use_json_format": True
        }
    )
    print(f"   Interaction ID: {interaction_id}")

    print("\n4. Logging LLM response...")
    wf_logger.log_llm_response(
        interaction_id=interaction_id,
        response='{"problems_and_solutions": [{"problem": "Test problem", "solution": "Test solution"}]}',
        success=True,
        latency_ms=1234.56
    )

    print("\n5. Logging custom print statement...")
    wf_logger.log_print(
        message="This is a test print statement",
        level="info",
        context={"source": "test_script"}
    )

    print("\n6. Logging completion event...")
    wf_logger.log_event("analysis_completed", {
        "status": "success",
        "llm_used": True,
        "fallback_mode": False
    })

    print("\n7. Closing logger...")
    close_workflow_logger(test_workflow_id)

    print("\n" + "="*80)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("="*80)

    print(f"\n📁 Check the logs at: workflow_logs/{test_workflow_id}/interactions.json")
    print()

if __name__ == "__main__":
    try:
        test_workflow_logger()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

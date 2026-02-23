#!/usr/bin/env python3
"""
Test script to verify workflow logging integration for Planner
"""
import sys
sys.path.insert(0, '.')

from workflow_interaction_logger import get_workflow_logger, close_workflow_logger

def test_planner_logger():
    """Test the workflow logger with a sample planning workflow"""

    print("\n" + "="*80)
    print("TESTING PLANNER WORKFLOW INTERACTION LOGGER")
    print("="*80)

    # Test workflow ID
    test_workflow_id = "test_planner_workflow_456"

    print(f"\n1. Initializing logger for workflow: {test_workflow_id}")
    wf_logger = get_workflow_logger(test_workflow_id)

    print("\n2. Logging planning start event...")
    wf_logger.log_event("planning_started", {
        "use_multi_stage": True,
        "has_additional_files": False
    })

    print("\n3. Logging LLM request (plan generation)...")
    interaction_id = wf_logger.log_llm_request(
        prompt="Generate repair plan for workflow failure...",
        metadata={
            "ollama_model": "llama3.3:latest",
            "plan_type": "repair",
            "prompt_length": 5432,
            "temperature": 0.1,
            "format": "json"
        }
    )
    print(f"   Interaction ID: {interaction_id}")

    print("\n4. Logging LLM response (plan)...")
    wf_logger.log_llm_response(
        interaction_id=interaction_id,
        response='{"plan_steps": [{"action": "test_action", "details": "test details"}]}',
        success=True,
        latency_ms=2456.78
    )

    print("\n5. Logging plan creation print...")
    wf_logger.log_print(
        message="✓ Repair plan generated successfully",
        level="info",
        context={"source": "planner", "plan_type": "repair"}
    )

    print("\n6. Logging planning completion event...")
    wf_logger.log_event("planning_completed", {
        "status": "success",
        "llm_used": True,
        "plan_id": "test_plan_123"
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
        test_planner_logger()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

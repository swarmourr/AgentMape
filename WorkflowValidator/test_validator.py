#!/usr/bin/env python3
"""
Quick test script for WorkflowValidator
"""
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from validator import WorkflowValidator

def test_basic_validation():
    """Test basic validation without LLM"""
    print("=" * 60)
    print("Testing WorkflowValidator - Basic Validation")
    print("=" * 60)
    print()

    # Initialize validator
    print("1. Initializing validator...")
    try:
        validator = WorkflowValidator()
        print("   ✅ Validator initialized successfully")
    except Exception as e:
        print(f"   ❌ Failed to initialize: {e}")
        return False

    # Test validation
    example_workflow = Path(__file__).parent / 'examples' / 'example_workflow.yml'

    if not example_workflow.exists():
        print(f"   ❌ Example workflow not found: {example_workflow}")
        return False

    print(f"2. Validating workflow: {example_workflow.name}")
    try:
        report = validator.validate(
            workflow_path=str(example_workflow),
            level='quick'  # Quick validation (no LLM)
        )
        print(f"   ✅ Validation completed in {report.total_duration_seconds:.2f}s")
    except Exception as e:
        print(f"   ❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Print summary
    print()
    print("3. Validation Summary:")
    print(f"   Status: {report.overall_status.value.upper()}")
    print(f"   Total issues: {report.total_issues}")
    print(f"   Errors: {report.total_errors}")
    print(f"   Warnings: {report.total_warnings}")
    print()

    # Print detailed report
    print("4. Detailed Report:")
    print("-" * 60)
    report_text = validator.generate_report(report, format='terminal')
    print(report_text)

    return True


def test_config_loading():
    """Test configuration loading"""
    print("=" * 60)
    print("Testing Configuration Loading")
    print("=" * 60)
    print()

    try:
        validator = WorkflowValidator()
        config = validator.config

        print("Configuration loaded successfully:")
        print(f"  - Agent ID: {config.get('agent_identity', {}).get('id')}")
        print(f"  - LLM Backend: {config.get('default_llm_backend')}")
        print(f"  - Ollama Model: {config.get('ollama_model')}")
        print(f"  - HTTP Port: {config.get('http_port')}")
        print()

        return True

    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return False


def main():
    """Run all tests"""
    print()
    print("╔" + "=" * 58 + "╗")
    print("║  WorkflowValidator Test Suite                            ║")
    print("╚" + "=" * 58 + "╝")
    print()

    all_passed = True

    # Test 1: Config loading
    if not test_config_loading():
        all_passed = False

    print()

    # Test 2: Basic validation
    if not test_basic_validation():
        all_passed = False

    print()
    print("=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)
    print()

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())

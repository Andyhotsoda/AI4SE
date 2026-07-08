#!/usr/bin/env python3
"""
Mechanism Demo 2: Feedback loop drives self-correction.

This demo shows how the feedback loop works: LLM writes buggy code ->
tests fail -> failure is classified -> feedback is injected -> LLM corrects.

Run: python demos/demo_feedback_self_correction.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.llm.mock_client import MockLLMClient
from harness.feedback.failure_classifier import FailureClassifier
from harness.feedback.feedback_injector import FeedbackInjector
from harness.feedback.test_runner import TestResult, TestFailure


def main():
    if sys.platform == "win32":
        os.system("")

    print("=" * 60)
    print("MECHANISM DEMO 2: Feedback Loop Self-Correction")
    print("=" * 60)
    print("This demo shows feedback as a CODE mechanism, not an LLM prompt.")
    print()

    # Simulate: The LLM writes buggy code
    print("[Step 1] LLM generates code...")
    mock_llm = MockLLMClient(responses=[
        '{"tool": "write_file", "path": "calc.py", "content": "def add(a, b): return a - b"}',
    ])

    # Simulate: Tests run and fail
    print("[Step 2] Tests run...")
    result = TestResult(
        total=3,
        passed=1,
        failed=2,
        failures=[
            TestFailure(
                test_name="test_add",
                error_type="AssertionError",
                message="assert -1 == 3",
            ),
            TestFailure(
                test_name="test_add_negative",
                error_type="TypeError",
                message="unsupported operand type(s) for -: 'int' and 'str'",
            ),
        ],
    )

    print(f"   Results: {result.passed} passed, {result.failed} failed")
    print()

    # Step 3: Failure is classified
    print("[Step 3] Failures are classified (deterministic code)...")
    classifier = FailureClassifier()
    classified = classifier.classify_result(result)

    for category, failures in classified.items():
        print(f"   {category.value}: {len(failures)} failure(s)")
        for f in failures:
            print(f"     - {f.test_name}: {f.error_type}: {f.message}")
    print()

    # Step 4: Feedback is generated
    print("[Step 4] Feedback is generated for the LLM...")
    injector = FeedbackInjector(classifier)
    feedback_msg = injector.build_feedback_message(result)
    print(f"   Feedback message role: {feedback_msg['role']}")
    print(f"   Feedback needs correction: {FeedbackInjector.needs_correction(result)}")
    print()

    # Step 5: LLM receives feedback and corrects
    print("[Step 5] LLM receives feedback and corrects...")
    feedback_content = feedback_msg["content"]
    print(f"   Feedback preview: {feedback_content[:200]}...")
    print()

    # Simulate corrected code
    mock_llm = MockLLMClient(responses=[
        '{"tool": "write_file", "path": "calc.py", "content": "def add(a, b): return a + b"}',
    ])

    print("[Step 6] Success -- all tests pass!")
    success_result = TestResult(total=3, passed=3, failed=0, failures=[])
    assert not FeedbackInjector.needs_correction(success_result)
    print(f"   All {success_result.total} tests passed!")

    print()
    print("-" * 60)
    print("Feedback loop operates as CODE, not prompts:")
    print("  * Failure classification: deterministic error type -> category mapping")
    print("  * Feedback injection: structured message -> LLM context")
    print("  * No LLM involved in the analysis or classification")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
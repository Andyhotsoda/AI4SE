"""Feedback injector — formats test feedback for LLM context."""

from __future__ import annotations

from harness.feedback.test_runner import TestResult
from harness.feedback.failure_classifier import FailureClassifier


class FeedbackInjector:
    """
    Injects feedback into the LLM's conversation context.

    This is the mechanism that closes the feedback loop:
    Agent acts → Tests run → Results parsed → Feedback generated → LLM receives it
    """

    def __init__(self, classifier: FailureClassifier | None = None):
        self._classifier = classifier or FailureClassifier()

    def build_feedback_message(self, result: TestResult) -> dict[str, str]:
        """
        Build a feedback message to inject into the LLM conversation.

        Args:
            result: The test result to build feedback from.

        Returns:
            A message dict with 'role' and 'content' for the LLM context.
        """
        feedback = self._classifier.generate_feedback(result)

        return {
            "role": "user",
            "content": (
                f"[SYSTEM FEEDBACK]\n"
                f"The following is feedback from the test harness. "
                f"Use this to correct your previous actions.\n\n"
                f"{feedback}"
            ),
        }

    def build_success_message(self) -> dict[str, str]:
        """Build a message indicating all tests passed."""
        return {
            "role": "user",
            "content": (
                f"[SYSTEM FEEDBACK]\n"
                f"All tests passed. The task is complete."
            ),
        }

    def build_error_message(self, error: str) -> dict[str, str]:
        """Build a message indicating a test execution error."""
        return {
            "role": "user",
            "content": (
                f"[SYSTEM FEEDBACK]\n"
                f"An error occurred while running tests:\n"
                f"{error}\n\n"
                f"Please fix the issue and try again."
            ),
        }

    @staticmethod
    def needs_correction(result: TestResult) -> bool:
        """Check if the test result indicates a need for correction."""
        return not result.all_passed or result.total == 0
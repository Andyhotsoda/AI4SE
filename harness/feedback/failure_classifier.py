"""
Failure classifier — categorizes test failures to guide LLM self-correction.

Classifications:
- SYNTAX_ERROR: The code doesn't parse/compile
- IMPORT_ERROR: Missing dependency
- TYPE_ERROR: Type mismatch
- ASSERTION_FAILURE: Logic error — test assertion failed
- RUNTIME_ERROR: Exception during execution
- TEST_ERROR: Test framework error (not the code under test)
- UNKNOWN: Unclassified failure
"""

from __future__ import annotations

from enum import Enum

from harness.feedback.test_runner import TestFailure, TestResult


class FailureCategory(str, Enum):
    """Categories of test failures."""
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    TYPE_ERROR = "type_error"
    ASSERTION_FAILURE = "assertion_failure"
    RUNTIME_ERROR = "runtime_error"
    TEST_ERROR = "test_error"
    UNKNOWN = "unknown"


class FailureClassifier:
    """
    Classifies test failures into categories for targeted feedback.

    Each category maps to specific guidance for the LLM,
    enabling more effective self-correction.
    """

    # Error type → failure category mapping
    ERROR_TYPE_MAP = {
        "SyntaxError": FailureCategory.SYNTAX_ERROR,
        "IndentationError": FailureCategory.SYNTAX_ERROR,
        "TabError": FailureCategory.SYNTAX_ERROR,
        "ImportError": FailureCategory.IMPORT_ERROR,
        "ModuleNotFoundError": FailureCategory.IMPORT_ERROR,
        "TypeError": FailureCategory.TYPE_ERROR,
        "AttributeError": FailureCategory.RUNTIME_ERROR,
        "NameError": FailureCategory.RUNTIME_ERROR,
        "ValueError": FailureCategory.RUNTIME_ERROR,
        "KeyError": FailureCategory.RUNTIME_ERROR,
        "IndexError": FailureCategory.RUNTIME_ERROR,
        "ZeroDivisionError": FailureCategory.RUNTIME_ERROR,
        "FileNotFoundError": FailureCategory.RUNTIME_ERROR,
        "AssertionError": FailureCategory.ASSERTION_FAILURE,
        "AssertionFailure": FailureCategory.ASSERTION_FAILURE,
    }

    # Guidance hints for each category
    GUIDANCE = {
        FailureCategory.SYNTAX_ERROR: (
            "There is a syntax error in the code. Check for missing colons, "
            "incorrect indentation, or invalid Python syntax."
        ),
        FailureCategory.IMPORT_ERROR: (
            "A required module or package is missing. Check the import statement "
            "and ensure the dependency is installed or the file exists."
        ),
        FailureCategory.TYPE_ERROR: (
            "There is a type mismatch. Check that the function receives the "
            "expected types and returns the correct type."
        ),
        FailureCategory.ASSERTION_FAILURE: (
            "A test assertion failed. The code produced an unexpected result. "
            "Review the expected vs actual values and fix the logic."
        ),
        FailureCategory.RUNTIME_ERROR: (
            "A runtime error occurred. The code raised an exception during "
            "execution. Check error handling and edge cases."
        ),
        FailureCategory.TEST_ERROR: (
            "The test itself has an error, not the code under test. "
            "Check the test setup, fixtures, and test syntax."
        ),
        FailureCategory.UNKNOWN: (
            "An unknown failure occurred. Review the error message and traceback "
            "to determine the cause."
        ),
    }

    def classify(self, failure: TestFailure) -> FailureCategory:
        """
        Classify a single test failure.

        Args:
            failure: The TestFailure to classify.

        Returns:
            The FailureCategory.
        """
        return self.ERROR_TYPE_MAP.get(failure.error_type, FailureCategory.UNKNOWN)

    def classify_result(self, result: TestResult) -> dict[FailureCategory, list[TestFailure]]:
        """
        Classify all failures in a test result.

        Args:
            result: The TestResult to classify.

        Returns:
            Dict mapping FailureCategory → list of TestFailures.
        """
        classified: dict[FailureCategory, list[TestFailure]] = {}
        for failure in result.failures:
            category = self.classify(failure)
            if category not in classified:
                classified[category] = []
            classified[category].append(failure)
        return classified

    def generate_feedback(self, result: TestResult) -> str:
        """
        Generate a natural language feedback message for the LLM.

        This is NOT a prompt — it's structured data that the harness
        injects into the LLM's context to enable self-correction.

        Args:
            result: The TestResult to generate feedback for.

        Returns:
            A feedback message for the LLM context.
        """
        if result.all_passed and result.total > 0:
            return f"[OK] All {result.total} tests passed."

        if result.total == 0:
            return "[WARN] No tests were found or run."

        classified = self.classify_result(result)
        lines = [
            f"[FAIL] Test Results: {result.passed} passed, {result.failed} failed, {result.errors} errors",
            "",
        ]

        for category, failures in classified.items():
            lines.append(f"## {category.value.replace('_', ' ').title()}")
            lines.append(f"**Guidance:** {self.GUIDANCE[category]}")
            lines.append("")
            for f in failures:
                lines.append(f"- **{f.test_name}**: {f.message}")
            lines.append("")

        lines.append("Please fix the failing tests and re-run.")

        return "\n".join(lines)

    @staticmethod
    def get_guidance(category: FailureCategory) -> str:
        """Get the guidance message for a failure category."""
        return FailureClassifier.GUIDANCE.get(
            category,
            FailureClassifier.GUIDANCE[FailureCategory.UNKNOWN],
        )
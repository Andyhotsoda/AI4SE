"""Test runner — executes test suites and captures results."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TestFailure:
    """A single test failure."""
    test_name: str
    error_type: str = "Unknown"
    message: str = ""
    traceback: str = ""
    file_path: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class TestResult:
    """Structured test results from a test run."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    raw_output: str = ""
    exit_code: int = 0

    @property
    def success_rate(self) -> float:
        """Percentage of tests that passed."""
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0


class SuiteRunner:
    """Runs test suites and captures structured results."""
    __test__ = False

    def __init__(self, working_dir: str = ".", timeout_seconds: int = 60):
        self._working_dir = working_dir
        self._timeout = timeout_seconds

    async def run_pytest(self, test_path: str = "tests/") -> TestResult:
        """
        Run pytest and parse the results.

        Args:
            test_path: Path to the tests to run.

        Returns:
            TestResult with structured test data.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "python", "-m", "pytest",
                test_path,
                "-v",
                "--tb=short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._working_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout,
            )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            return self._parse_pytest_output(stdout_str, process.returncode or 0)

        except asyncio.TimeoutError:
            return TestResult(
                errors=1,
                raw_output=f"Test run timed out after {self._timeout}s",
                exit_code=-1,
            )
        except FileNotFoundError:
            return TestResult(
                errors=1,
                raw_output="pytest not found. Is it installed?",
                exit_code=-1,
            )

    def _parse_pytest_output(self, output: str, exit_code: int) -> TestResult:
        """Parse pytest output into structured test results."""
        result = TestResult(raw_output=output, exit_code=exit_code)

        # Parse the summary line: "X passed, Y failed, Z errors"
        import re
        summary_match = re.search(
            r"(\d+)\s+passed.*?(\d+)\s+failed.*?(\d+)\s+error",
            output,
        )
        if summary_match:
            result.passed = int(summary_match.group(1))
            result.failed = int(summary_match.group(2))
            result.errors = int(summary_match.group(3))
        else:
            # Try simpler formats
            passed_m = re.search(r"(\d+)\s+passed", output)
            failed_m = re.search(r"(\d+)\s+failed", output)
            if passed_m:
                result.passed = int(passed_m.group(1))
            if failed_m:
                result.failed = int(failed_m.group(1))

        result.total = result.passed + result.failed + result.errors

        # Parse individual failures
        failures = self._parse_failures(output)
        result.failures = failures

        return result

    def _parse_failures(self, output: str) -> list[TestFailure]:
        """Parse individual test failures from pytest output."""
        import re
        failures = []

        # Find FAILED test entries
        # Pattern: "FAILED tests/path.py::TestClass::test_name - AssertionError: message"
        failed_pattern = re.compile(
            r"FAILED\s+(\S+?)(?::(\S+))?\s*-\s*(\w+):\s*(.*)",
            re.MULTILINE,
        )
        for match in failed_pattern.finditer(output):
            file_path = match.group(1)
            test_name = match.group(2) or file_path
            error_type = match.group(3)
            message = match.group(4)

            failures.append(TestFailure(
                test_name=test_name,
                error_type=error_type,
                message=message,
                file_path=file_path,
            ))

        return failures

    async def run_command(self, command: str) -> TestResult:
        """Run an arbitrary test command and capture results."""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._working_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout,
            )

            output = stdout.decode("utf-8", errors="replace")
            if process.returncode != 0:
                output += "\n" + stderr.decode("utf-8", errors="replace")

            return TestResult(
                passed=1 if process.returncode == 0 else 0,
                failed=0 if process.returncode == 0 else 1,
                raw_output=output,
                exit_code=process.returncode or 0,
            )

        except asyncio.TimeoutError:
            return TestResult(
                errors=1,
                raw_output=f"Command timed out after {self._timeout}s",
                exit_code=-1,
            )
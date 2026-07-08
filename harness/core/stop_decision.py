"""Stop decision — determines when the agent loop should terminate."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StopReason(Enum):
    """Reasons for the agent loop to stop."""
    TASK_COMPLETE = "task_complete"       # Agent explicitly stopped
    MAX_ITERATIONS = "max_iterations"     # Hit iteration limit
    MAX_FAILURES = "max_failures"         # Too many consecutive failures
    LLM_ERROR = "llm_error"              # LLM returned an error
    MANUAL_STOP = "manual_stop"          # User interrupted


@dataclass
class StopDecision:
    """Result of the stop decision evaluation."""
    should_stop: bool
    reason: StopReason = StopReason.TASK_COMPLETE
    message: str = ""


class StopDecisionEngine:
    """
    Evaluates whether the agent loop should terminate.

    Considers: max iterations, consecutive failures, explicit stop signals,
    and LLM errors.
    """

    def __init__(
        self,
        max_iterations: int = 50,
        max_consecutive_failures: int = 5,
    ):
        self._max_iterations = max_iterations
        self._max_consecutive_failures = max_consecutive_failures
        self._iteration = 0
        self._consecutive_failures = 0

    def evaluate(
        self,
        agent_stopped: bool = False,
        action_succeeded: bool | None = None,
        llm_error: bool = False,
        manual_stop: bool = False,
    ) -> StopDecision:
        """
        Evaluate whether the loop should stop.

        Args:
            agent_stopped: Whether the agent emitted a stop/finish action.
            action_succeeded: Whether the last action succeeded (None if no action).
            llm_error: Whether the LLM call itself failed.
            manual_stop: Whether the user manually interrupted.

        Returns:
            StopDecision with should_stop flag and reason.
        """
        self._iteration += 1

        # Track consecutive failures
        if action_succeeded is False:
            self._consecutive_failures += 1
        elif action_succeeded is True:
            self._consecutive_failures = 0

        # Priority order of stop checks

        if manual_stop:
            return StopDecision(True, StopReason.MANUAL_STOP, "User interrupted")

        if llm_error:
            return StopDecision(True, StopReason.LLM_ERROR, "LLM error encountered")

        if agent_stopped:
            return StopDecision(True, StopReason.TASK_COMPLETE, "Agent signaled completion")

        if self._consecutive_failures >= self._max_consecutive_failures:
            return StopDecision(
                True,
                StopReason.MAX_FAILURES,
                f"Too many consecutive failures ({self._consecutive_failures})",
            )

        if self._iteration >= self._max_iterations:
            return StopDecision(
                True,
                StopReason.MAX_ITERATIONS,
                f"Reached max iterations ({self._max_iterations})",
            )

        return StopDecision(False, StopReason.TASK_COMPLETE, "")

    def reset(self) -> None:
        """Reset iteration and failure counters."""
        self._iteration = 0
        self._consecutive_failures = 0

    @property
    def iteration(self) -> int:
        return self._iteration

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
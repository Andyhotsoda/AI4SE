"""
Human-in-the-Loop (HITL) state machine.

A proper finite state machine for requesting, tracking, and resolving
human approval for dangerous actions.

States: IDLE -> AWAITING_APPROVAL -> APPROVED/DENIED/TIMED_OUT -> IDLE
Transitions are pure functions of (state, event) pairs — fully deterministic
and testable without any LLM.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from harness.tools.base import Action


class HITLState(Enum):
    """States of the HITL state machine."""
    IDLE = "idle"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


class HITLEvent(Enum):
    """Events that trigger state transitions."""
    REQUEST_APPROVAL = "request_approval"
    APPROVE = "approve"
    DENY = "deny"
    TIMEOUT = "timeout"
    RESET = "reset"


class InvalidTransition(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    action: Action
    reason: str
    danger_level: str = "UNKNOWN"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ApprovalRecord:
    """Record of a completed approval request."""
    action: Action
    reason: str
    result: HITLState
    timestamp: datetime


@dataclass
class HITLResult:
    """Result of an HITL approval request."""
    approved: bool
    state: HITLState
    action: Action
    message: str = ""


# Type for the approval callback: takes ApprovalRequest, returns bool (approved)
ApprovalCallback = Callable[[ApprovalRequest], Awaitable[bool]]


class HITLStateMachine:
    """
    HITL state machine for human-in-the-loop approval.

    States and transitions:
        IDLE + REQUEST_APPROVAL -> AWAITING_APPROVAL (starts timeout)
        AWAITING_APPROVAL + APPROVE -> APPROVED
        AWAITING_APPROVAL + DENY -> DENIED
        AWAITING_APPROVAL + TIMEOUT -> TIMED_OUT
        APPROVED + RESET -> IDLE
        DENIED + RESET -> IDLE
        TIMED_OUT + RESET -> IDLE

    The approval_callback is injectable — in tests, it's a mock that returns
    immediately; in production, it presents a console prompt.
    """

    # State transition table: (current_state, event) -> new_state
    TRANSITIONS: dict[tuple[HITLState, HITLEvent], HITLState] = {
        (HITLState.IDLE, HITLEvent.REQUEST_APPROVAL): HITLState.AWAITING_APPROVAL,
        (HITLState.AWAITING_APPROVAL, HITLEvent.APPROVE): HITLState.APPROVED,
        (HITLState.AWAITING_APPROVAL, HITLEvent.DENY): HITLState.DENIED,
        (HITLState.AWAITING_APPROVAL, HITLEvent.TIMEOUT): HITLState.TIMED_OUT,
        (HITLState.APPROVED, HITLEvent.RESET): HITLState.IDLE,
        (HITLState.DENIED, HITLEvent.RESET): HITLState.IDLE,
        (HITLState.TIMED_OUT, HITLEvent.RESET): HITLState.IDLE,
    }

    def __init__(
        self,
        timeout_seconds: int = 120,
        approval_callback: ApprovalCallback | None = None,
    ):
        self._timeout = timeout_seconds
        self._approval_callback = approval_callback
        self.state = HITLState.IDLE
        self._current_request: Optional[ApprovalRequest] = None
        self._history: list[ApprovalRecord] = []

    def transition(self, event: HITLEvent) -> HITLState:
        """
        Execute a state transition.

        Args:
            event: The event to process.

        Returns:
            The new state.

        Raises:
            InvalidTransition: If the transition is not allowed.
        """
        key = (self.state, event)
        if key not in self.TRANSITIONS:
            raise InvalidTransition(
                f"Cannot transition from {self.state.value} with event {event.value}"
            )
        self.state = self.TRANSITIONS[key]
        return self.state

    def can_transition(self, event: HITLEvent) -> bool:
        """Check if a transition is valid from the current state."""
        return (self.state, event) in self.TRANSITIONS

    async def request_approval(self, action: Action, reason: str) -> HITLResult:
        """
        Request human approval for an action.

        Blocks until approved, denied, or timed out.
        The approval_callback (if provided) is called to get the user's decision.

        Args:
            action: The action requiring approval.
            reason: Human-readable reason why approval is needed.

        Returns:
            HITLResult with the approval decision.
        """
        # Transition to AWAITING_APPROVAL
        self.transition(HITLEvent.REQUEST_APPROVAL)
        self._current_request = ApprovalRequest(
            action=action,
            reason=reason,
            danger_level="UNKNOWN",
        )

        try:
            if self._approval_callback:
                # Use the injected callback (test mode)
                approved = await asyncio.wait_for(
                    self._approval_callback(self._current_request),
                    timeout=self._timeout,
                )
            else:
                # Default: console-based approval
                approved = await asyncio.wait_for(
                    self._console_approval(self._current_request),
                    timeout=self._timeout,
                )

            if approved:
                self.transition(HITLEvent.APPROVE)
            else:
                self.transition(HITLEvent.DENY)

        except asyncio.TimeoutError:
            self.transition(HITLEvent.TIMEOUT)

        # Record the result
        self._history.append(ApprovalRecord(
            action=action,
            reason=reason,
            result=self.state,
            timestamp=datetime.now(),
        ))

        result = HITLResult(
            approved=(self.state == HITLState.APPROVED),
            state=self.state,
            action=action,
            message=self._result_message(),
        )

        # Reset to IDLE for next request
        self.transition(HITLEvent.RESET)
        return result

    async def _console_approval(self, request: ApprovalRequest) -> bool:
        """Present approval request to the user via console."""
        print(f"\n{'='*60}")
        print("!!! DANGEROUS ACTION REQUIRES APPROVAL !!!")
        print(f"{'='*60}")
        print(f"Action: {request.action.tool_name}")
        print(f"Parameters: {request.action.parameters}")
        print(f"Reason: {request.reason}")
        print(f"{'='*60}")

        try:
            response = input("Approve? [y/N]: ").strip().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def _result_message(self) -> str:
        """Generate a human-readable result message."""
        messages = {
            HITLState.APPROVED: "Action approved by human operator.",
            HITLState.DENIED: "Action denied by human operator.",
            HITLState.TIMED_OUT: f"Approval timed out after {self._timeout}s.",
        }
        return messages.get(self.state, "Unknown HITL result.")

    @property
    def history(self) -> list[ApprovalRecord]:
        """Get the history of approval requests."""
        return list(self._history)

    @property
    def is_awaiting(self) -> bool:
        """Check if currently awaiting approval."""
        return self.state == HITLState.AWAITING_APPROVAL

    @property
    def timeout(self) -> int:
        return self._timeout

    def reset(self) -> None:
        """Force reset to IDLE state."""
        self.state = HITLState.IDLE
        self._current_request = None
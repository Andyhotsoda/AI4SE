"""Tests for the HITL state machine — deterministic, no LLM needed."""

import asyncio

import pytest

from harness.tools.base import Action
from harness.governance.hitl import (
    HITLStateMachine,
    HITLState,
    HITLEvent,
    InvalidTransition,
    ApprovalRequest,
)


class TestHITLStateMachine:
    """Tests for the HITL state machine."""

    def setup_method(self):
        self.hitl = HITLStateMachine(timeout_seconds=5)
        # Verify initial state
        assert self.hitl.state == HITLState.IDLE

    def test_initial_state_is_idle(self):
        """Initial state should be IDLE."""
        assert self.hitl.state == HITLState.IDLE
        assert not self.hitl.is_awaiting

    def test_valid_transition_to_awaiting(self):
        """IDLE -> AWAITING_APPROVAL should be valid."""
        new_state = self.hitl.transition(HITLEvent.REQUEST_APPROVAL)
        assert new_state == HITLState.AWAITING_APPROVAL
        assert self.hitl.is_awaiting

    def test_invalid_transition_raises(self):
        """Invalid transitions should raise InvalidTransition."""
        with pytest.raises(InvalidTransition):
            self.hitl.transition(HITLEvent.APPROVE)  # Can't approve from IDLE

    def test_awaiting_to_approved(self):
        """AWAITING_APPROVAL -> APPROVED should be valid."""
        self.hitl.transition(HITLEvent.REQUEST_APPROVAL)
        new_state = self.hitl.transition(HITLEvent.APPROVE)
        assert new_state == HITLState.APPROVED

    def test_awaiting_to_denied(self):
        """AWAITING_APPROVAL -> DENIED should be valid."""
        self.hitl.transition(HITLEvent.REQUEST_APPROVAL)
        new_state = self.hitl.transition(HITLEvent.DENY)
        assert new_state == HITLState.DENIED

    def test_awaiting_to_timed_out(self):
        """AWAITING_APPROVAL -> TIMED_OUT should be valid."""
        self.hitl.transition(HITLEvent.REQUEST_APPROVAL)
        new_state = self.hitl.transition(HITLEvent.TIMEOUT)
        assert new_state == HITLState.TIMED_OUT

    def test_reset_from_approved(self):
        """APPROVED -> IDLE via RESET."""
        self.hitl.transition(HITLEvent.REQUEST_APPROVAL)
        self.hitl.transition(HITLEvent.APPROVE)
        new_state = self.hitl.transition(HITLEvent.RESET)
        assert new_state == HITLState.IDLE

    def test_reset_from_denied(self):
        """DENIED -> IDLE via RESET."""
        self.hitl.transition(HITLEvent.REQUEST_APPROVAL)
        self.hitl.transition(HITLEvent.DENY)
        new_state = self.hitl.transition(HITLEvent.RESET)
        assert new_state == HITLState.IDLE

    def test_can_transition(self):
        """can_transition should accurately report valid transitions."""
        assert self.hitl.can_transition(HITLEvent.REQUEST_APPROVAL)
        assert not self.hitl.can_transition(HITLEvent.APPROVE)
        assert not self.hitl.can_transition(HITLEvent.DENY)

    async def test_request_approval_approved(self):
        """Full approval flow: request -> approve -> result."""
        hitl = HITLStateMachine(
            timeout_seconds=5,
            approval_callback=lambda req: asyncio.sleep(0, result=True),
        )
        # Need to make callback return True
        async def approve_callback(req):
            return True

        hitl = HITLStateMachine(timeout_seconds=5, approval_callback=approve_callback)
        action = Action(tool_name="shell", parameters={"command": "rm file"})
        result = await hitl.request_approval(action, "Test approval")

        assert result.approved is True
        assert result.state == HITLState.APPROVED
        assert hitl.state == HITLState.IDLE  # Reset after request
        assert len(hitl.history) == 1

    async def test_request_approval_denied(self):
        """Full denial flow: request -> deny -> result."""
        async def deny_callback(req):
            return False

        hitl = HITLStateMachine(timeout_seconds=5, approval_callback=deny_callback)
        action = Action(tool_name="shell", parameters={"command": "rm file"})
        result = await hitl.request_approval(action, "Test denial")

        assert result.approved is False
        assert result.state == HITLState.DENIED
        assert len(hitl.history) == 1

    async def test_request_approval_timeout(self):
        """Approval should time out if callback takes too long."""
        async def slow_callback(req):
            await asyncio.sleep(10)  # Longer than timeout
            return True

        hitl = HITLStateMachine(timeout_seconds=0.1, approval_callback=slow_callback)
        action = Action(tool_name="shell", parameters={"command": "rm file"})
        result = await hitl.request_approval(action, "Test timeout")

        assert result.approved is False
        assert result.state == HITLState.TIMED_OUT

    def test_history_records_approvals(self):
        """History should correctly record all approval requests."""
        # We'll test via the full request_approval flow
        pass

    def test_force_reset(self):
        """Force reset should return to IDLE from any state."""
        self.hitl.transition(HITLEvent.REQUEST_APPROVAL)
        assert self.hitl.state == HITLState.AWAITING_APPROVAL
        self.hitl.reset()
        assert self.hitl.state == HITLState.IDLE

    def test_all_transitions_are_valid(self):
        """All transitions in the TRANSITIONS table should work."""
        for (state, event), new_state in HITLStateMachine.TRANSITIONS.items():
            hitl = HITLStateMachine()
            hitl.state = state  # Force state
            result = hitl.transition(event)
            assert result == new_state, f"Transition ({state}, {event}) -> {new_state} failed"
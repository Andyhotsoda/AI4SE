"""
Action Interceptor — central guardrail dispatcher.

The ActionInterceptor is the single entry point for governance. It runs
the full governance pipeline on every action before execution:

    1. DangerClassifier → determines danger level
    2. PolicyEngine → evaluates safety rules → verdict
    3. HITLStateMachine → requests human approval if needed
    4. ScopeFence → validates paths and commands
    5. Sandbox → optionally isolates execution

All components are injectable, making the interceptor fully testable
with mock LLM and mock approval callbacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from harness.tools.base import Action, DangerLevel
from harness.governance.danger_classifier import DangerClassifier
from harness.governance.policy_engine import PolicyEngine
from harness.governance.hitl import HITLStateMachine, HITLState
from harness.governance.scope_fence import ScopeFence
from harness.governance.sandbox import Sandbox


class InterceptVerdict(str, Enum):
    """Possible verdicts from the action interceptor."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    SANDBOX = "SANDBOX"


@dataclass
class InterceptResult:
    """Result of the governance pipeline for an action."""
    allowed: bool
    verdict: InterceptVerdict = InterceptVerdict.ALLOW
    reason: str = ""
    danger_level: DangerLevel = DangerLevel.SAFE
    use_sandbox: bool = False
    matched_rule: Optional[str] = None


class ActionInterceptor:
    """
    Central guardrail. Every action passes through this before execution.

    Pipeline:
        Action → classify danger → evaluate policy → HITL → scope fence → sandbox → Execute

    Usage:
        interceptor = ActionInterceptor(
            classifier=DangerClassifier(),
            policy=PolicyEngine.create_default_policy(),
            hitl=HITLStateMachine(approval_callback=console_approval),
            fence=ScopeFence(allowed_directories=["."]),
            sandbox=Sandbox(strategy="subprocess"),
        )
        result = await interceptor.intercept(action)
        if result.allowed:
            # Execute the action
            ...
    """

    def __init__(
        self,
        classifier: DangerClassifier,
        policy: PolicyEngine,
        hitl: HITLStateMachine,
        fence: ScopeFence,
        sandbox: Sandbox,
    ):
        self._classifier = classifier
        self._policy = policy
        self._hitl = hitl
        self._fence = fence
        self._sandbox = sandbox

    async def intercept(self, action: Action) -> InterceptResult:
        """
        Run the full governance pipeline on an action.

        Args:
            action: The action to evaluate.

        Returns:
            InterceptResult indicating whether to proceed and how.
        """
        # Step 1: Classify danger
        danger_level = self._classifier.classify(action)

        # Step 2: Evaluate policy
        policy_verdict = self._policy.evaluate(action, danger_level)

        # Step 3: Handle DENY verdict
        if policy_verdict.verdict == "DENY":
            return InterceptResult(
                allowed=False,
                verdict=InterceptVerdict.DENY,
                reason=policy_verdict.reason,
                danger_level=danger_level,
                matched_rule=policy_verdict.matched_rule,
            )

        # Step 4: Handle ASK verdict — request human approval
        if policy_verdict.verdict == "ASK":
            hitl_result = await self._hitl.request_approval(
                action, policy_verdict.reason
            )
            if not hitl_result.approved:
                return InterceptResult(
                    allowed=False,
                    verdict=InterceptVerdict.DENY,
                    reason=(
                        f"Human denied action: {policy_verdict.reason}"
                        if hitl_result.state == HITLState.DENIED
                        else f"Approval timed out: {policy_verdict.reason}"
                    ),
                    danger_level=danger_level,
                    matched_rule=policy_verdict.matched_rule,
                )

        # Step 5: Scope fence validation
        if action.tool_name in ("read_file", "write_file", "list_directory"):
            path = action.parameters.get("path", "")
            if path:
                fence_result = self._fence.validate_path(path)
                if not fence_result.allowed:
                    return InterceptResult(
                        allowed=False,
                        verdict=InterceptVerdict.DENY,
                        reason=fence_result.reason,
                        danger_level=danger_level,
                        matched_rule="scope_fence",
                    )

        if action.tool_name == "shell":
            command = action.parameters.get("command", "")
            if command:
                fence_result = self._fence.validate_command(command)
                if not fence_result.allowed:
                    return InterceptResult(
                        allowed=False,
                        verdict=InterceptVerdict.DENY,
                        reason=fence_result.reason,
                        danger_level=danger_level,
                        matched_rule="scope_fence",
                    )

        # Step 6: Determine sandbox requirements
        use_sandbox = policy_verdict.verdict == "SANDBOX"

        verdict = InterceptVerdict.SANDBOX if use_sandbox else InterceptVerdict.ALLOW

        return InterceptResult(
            allowed=True,
            verdict=verdict,
            reason="Action approved",
            danger_level=danger_level,
            use_sandbox=use_sandbox,
            matched_rule=policy_verdict.matched_rule,
        )

    @property
    def classifier(self) -> DangerClassifier:
        return self._classifier

    @property
    def policy(self) -> PolicyEngine:
        return self._policy

    @property
    def hitl(self) -> HITLStateMachine:
        return self._hitl

    @property
    def fence(self) -> ScopeFence:
        return self._fence
"""
Declarative safety policy engine.

Evaluates priority-ordered rules against actions. Each rule specifies
a condition (field matching with regex/equals/in operators) and a verdict
(ALLOW/DENY/ASK/SANDBOX). Rules are deterministic — no LLM involved.

The policy engine is the core of the "declarative safety policy" requirement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from harness.tools.base import Action, DangerLevel


@dataclass
class PolicyRule:
    """A single rule in the safety policy."""
    name: str
    description: str = ""
    priority: int = 0  # Higher = evaluated first
    condition: dict[str, Any] = field(default_factory=dict)
    verdict: str = "ASK"  # ALLOW, DENY, ASK, SANDBOX
    reason: str = ""


@dataclass
class PolicyVerdict:
    """Result of policy evaluation."""
    verdict: str  # ALLOW, DENY, ASK, SANDBOX
    reason: str = ""
    matched_rule: str = "default"


class PolicyEngine:
    """
    Evaluates a set of policy rules against an action.

    Rules are evaluated in priority order (highest first).
    The first matching rule determines the verdict.
    If no rule matches, the default verdict is applied.

    Usage:
        engine = PolicyEngine([
            PolicyRule(
                name="deny-root-deletion",
                priority=1000,
                condition={"danger_level": "CRITICAL"},
                verdict="DENY",
                reason="System-level destruction is permanently blocked.",
            ),
            PolicyRule(
                name="allow-safe",
                priority=100,
                condition={"danger_level": "SAFE"},
                verdict="ALLOW",
                reason="Safe operations are always allowed.",
            ),
        ], default_verdict="ASK")
    """

    def __init__(self, rules: list[PolicyRule] | None = None, default_verdict: str = "ASK"):
        self._rules = sorted(
            rules or [],
            key=lambda r: r.priority,
            reverse=True,  # Highest priority first
        )
        self._default_verdict = default_verdict

    def evaluate(self, action: Action, danger_level: DangerLevel) -> PolicyVerdict:
        """
        Evaluate all rules against an action. Returns the first match.

        Args:
            action: The action to evaluate.
            danger_level: Pre-classified danger level of the action.

        Returns:
            PolicyVerdict with the verdict and reasoning.
        """
        context = self._build_context(action, danger_level)

        for rule in self._rules:
            if self._rule_matches(rule, context):
                return PolicyVerdict(
                    verdict=rule.verdict,
                    reason=rule.reason,
                    matched_rule=rule.name,
                )

        return PolicyVerdict(
            verdict=self._default_verdict,
            reason="No policy rule matched; applying default verdict.",
            matched_rule="default",
        )

    def _build_context(self, action: Action, danger_level: DangerLevel) -> dict:
        """Build a context dict for rule matching."""
        return {
            "tool_name": action.tool_name,
            "danger_level": danger_level.name,
            "command": action.parameters.get("command", ""),
            "file_path": action.parameters.get("path", ""),
            "content": action.parameters.get("content", ""),
        }

    def _rule_matches(self, rule: PolicyRule, context: dict) -> bool:
        """Check if a rule's condition matches the action context."""
        for field, condition in rule.condition.items():
            if field not in context:
                return False

            if isinstance(condition, dict):
                # Operator-based condition
                if not self._eval_operator_condition(context[field], condition):
                    return False
            else:
                # Direct value match
                if context[field] != condition:
                    return False

        return True

    def _eval_operator_condition(self, value: Any, condition: dict) -> bool:
        """
        Evaluate an operator-based condition.

        Supported operators:
        - regex: value matches regex pattern
        - equals: value equals
        - in: value is in list
        - not_in: value is not in list
        """
        if "regex" in condition:
            return bool(re.search(condition["regex"], str(value)))
        if "equals" in condition:
            return value == condition["equals"]
        if "in" in condition:
            return value in condition["in"]
        if "not_in" in condition:
            return value not in condition["not_in"]
        return False

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a rule and re-sort by priority."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name. Returns True if found and removed."""
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                self._rules.pop(i)
                return True
        return False

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    @property
    def default_verdict(self) -> str:
        return self._default_verdict

    @classmethod
    def create_default_policy(cls) -> "PolicyEngine":
        """Create a PolicyEngine with sensible default rules."""
        return cls(
            rules=[
                PolicyRule(
                    name="deny-critical",
                    description="Never allow critical-level actions",
                    priority=1000,
                    condition={"danger_level": "CRITICAL"},
                    verdict="DENY",
                    reason="This action could destroy the system. It is permanently blocked.",
                ),
                PolicyRule(
                    name="ask-dangerous-shell",
                    description="Require human approval for dangerous shell commands",
                    priority=500,
                    condition={
                        "danger_level": "DANGEROUS",
                        "tool_name": "shell",
                    },
                    verdict="ASK",
                    reason="Dangerous shell command requires human approval.",
                ),
                PolicyRule(
                    name="sandbox-warning-shell",
                    description="Run warning-level shell commands in sandbox",
                    priority=200,
                    condition={
                        "danger_level": "WARNING",
                        "tool_name": "shell",
                    },
                    verdict="SANDBOX",
                    reason="Running in sandbox for safety.",
                ),
                PolicyRule(
                    name="allow-safe",
                    description="Allow all safe operations",
                    priority=100,
                    condition={"danger_level": "SAFE"},
                    verdict="ALLOW",
                    reason="Safe operations are always allowed.",
                ),
            ],
            default_verdict="ASK",
        )

    @classmethod
    def create_strict_policy(cls) -> "PolicyEngine":
        """Create a very strict PolicyEngine."""
        return cls(
            rules=[
                PolicyRule(
                    name="deny-critical",
                    priority=1000,
                    condition={"danger_level": "CRITICAL"},
                    verdict="DENY",
                    reason="System-level destruction is permanently blocked.",
                ),
                PolicyRule(
                    name="deny-dangerous",
                    priority=900,
                    condition={"danger_level": "DANGEROUS"},
                    verdict="ASK",
                    reason="Dangerous actions require human approval.",
                ),
                PolicyRule(
                    name="ask-warning",
                    priority=500,
                    condition={"danger_level": "WARNING"},
                    verdict="ASK",
                    reason="Warning-level actions require human approval.",
                ),
                PolicyRule(
                    name="allow-safe",
                    priority=100,
                    condition={"danger_level": "SAFE"},
                    verdict="ALLOW",
                    reason="Safe operations are always allowed.",
                ),
            ],
            default_verdict="ASK",
        )

    @classmethod
    def create_permissive_policy(cls) -> "PolicyEngine":
        """Create a permissive PolicyEngine (only blocks critical)."""
        return cls(
            rules=[
                PolicyRule(
                    name="deny-critical",
                    priority=1000,
                    condition={"danger_level": "CRITICAL"},
                    verdict="DENY",
                    reason="System-level destruction is permanently blocked.",
                ),
                PolicyRule(
                    name="allow-others",
                    priority=100,
                    condition={},
                    verdict="ALLOW",
                    reason="Permissive mode: allow all non-critical actions.",
                ),
            ],
            default_verdict="ALLOW",
        )
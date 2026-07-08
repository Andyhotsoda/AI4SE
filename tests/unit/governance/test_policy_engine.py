"""Tests for the PolicyEngine — deterministic, no LLM needed."""

import pytest

from harness.tools.base import Action, DangerLevel
from harness.governance.policy_engine import (
    PolicyEngine,
    PolicyRule,
    PolicyVerdict,
)


class TestPolicyEngine:
    """Tests for the declarative PolicyEngine."""

    def setup_method(self):
        self.engine = PolicyEngine.create_default_policy()

    def test_default_policy_denies_critical(self):
        """Critical actions should be DENIED by default policy."""
        action = Action(tool_name="shell", parameters={"command": "rm -rf /"})
        verdict = self.engine.evaluate(action, DangerLevel.CRITICAL)
        assert verdict.verdict == "DENY"
        assert verdict.matched_rule == "deny-critical"

    def test_default_policy_asks_dangerous_shell(self):
        """Dangerous shell commands should be ASK by default policy."""
        action = Action(tool_name="shell", parameters={"command": "git push --force"})
        verdict = self.engine.evaluate(action, DangerLevel.DANGEROUS)
        assert verdict.verdict == "ASK"
        assert verdict.matched_rule == "ask-dangerous-shell"

    def test_default_policy_sandboxes_warning_shell(self):
        """Warning-level shell commands should be SANDBOX by default policy."""
        action = Action(tool_name="shell", parameters={"command": "git commit -m 'fix'"})
        verdict = self.engine.evaluate(action, DangerLevel.WARNING)
        assert verdict.verdict == "SANDBOX"
        assert verdict.matched_rule == "sandbox-warning-shell"

    def test_default_policy_allows_safe(self):
        """Safe actions should be ALLOWED by default policy."""
        action = Action(tool_name="read_file", parameters={"path": "main.py"})
        verdict = self.engine.evaluate(action, DangerLevel.SAFE)
        assert verdict.verdict == "ALLOW"
        assert verdict.matched_rule == "allow-safe"

    def test_no_match_uses_default(self):
        """When no rule matches, use default verdict."""
        engine = PolicyEngine(rules=[], default_verdict="ASK")
        action = Action(tool_name="shell", parameters={"command": "echo hello"})
        verdict = engine.evaluate(action, DangerLevel.WARNING)
        assert verdict.verdict == "ASK"
        assert verdict.matched_rule == "default"

    def test_higher_priority_wins(self):
        """Higher priority rules should match first."""
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="high-priority",
                    priority=100,
                    condition={"tool_name": "shell"},
                    verdict="ALLOW",
                    reason="High priority allows all shell",
                ),
                PolicyRule(
                    name="low-priority",
                    priority=10,
                    condition={"tool_name": "shell"},
                    verdict="DENY",
                    reason="Low priority denies all shell",
                ),
            ],
            default_verdict="ASK",
        )
        action = Action(tool_name="shell", parameters={"command": "ls"})
        verdict = engine.evaluate(action, DangerLevel.WARNING)
        assert verdict.verdict == "ALLOW"
        assert verdict.matched_rule == "high-priority"

    def test_regex_condition(self):
        """Regex conditions should match."""
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="block-rm",
                    priority=100,
                    condition={"command": {"regex": r"rm\s+"}},
                    verdict="DENY",
                    reason="Deletion commands are blocked",
                ),
            ],
            default_verdict="ALLOW",
        )
        action = Action(tool_name="shell", parameters={"command": "rm -rf build"})
        verdict = engine.evaluate(action, DangerLevel.WARNING)
        assert verdict.verdict == "DENY"
        assert verdict.matched_rule == "block-rm"

    def test_in_operator_condition(self):
        """'in' operator conditions should match."""
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="block-tools",
                    priority=100,
                    condition={"tool_name": {"in": ["shell", "write_file"]}},
                    verdict="ASK",
                    reason="Shell and write need approval",
                ),
            ],
            default_verdict="ALLOW",
        )
        action = Action(tool_name="write_file", parameters={"path": "test.py"})
        verdict = engine.evaluate(action, DangerLevel.WARNING)
        assert verdict.verdict == "ASK"

    def test_not_in_operator_condition(self):
        """'not_in' operator conditions should match."""
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="allow-safe-tools",
                    priority=100,
                    condition={"tool_name": {"not_in": ["shell", "write_file"]}},
                    verdict="ALLOW",
                    reason="Non-shell, non-write tools are safe",
                ),
            ],
            default_verdict="ASK",
        )
        action = Action(tool_name="read_file", parameters={"path": "main.py"})
        verdict = engine.evaluate(action, DangerLevel.SAFE)
        assert verdict.verdict == "ALLOW"

    def test_equals_condition(self):
        """'equals' operator conditions should match."""
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="exact-command",
                    priority=100,
                    condition={"command": {"equals": "ls"}},
                    verdict="ALLOW",
                    reason="Exact ls is safe",
                ),
            ],
            default_verdict="ASK",
        )
        action = Action(tool_name="shell", parameters={"command": "ls"})
        verdict = engine.evaluate(action, DangerLevel.WARNING)
        assert verdict.verdict == "ALLOW"

    def test_add_rule(self):
        """Adding a rule should work."""
        engine = PolicyEngine([], default_verdict="ASK")
        engine.add_rule(PolicyRule(
            name="new-rule",
            priority=50,
            condition={"danger_level": "SAFE"},
            verdict="ALLOW",
        ))
        assert len(engine.rules) == 1
        action = Action(tool_name="read_file", parameters={})
        verdict = engine.evaluate(action, DangerLevel.SAFE)
        assert verdict.verdict == "ALLOW"

    def test_remove_rule(self):
        """Removing a rule should work."""
        engine = PolicyEngine.create_default_policy()
        original_count = len(engine.rules)
        removed = engine.remove_rule("allow-safe")
        assert removed is True
        assert len(engine.rules) == original_count - 1

    def test_remove_nonexistent_rule(self):
        """Removing a non-existent rule should return False."""
        engine = PolicyEngine.create_default_policy()
        removed = engine.remove_rule("nonexistent")
        assert removed is False

    def test_strict_policy(self):
        """Strict policy should be more restrictive."""
        engine = PolicyEngine.create_strict_policy()
        action = Action(tool_name="write_file", parameters={"path": "test.py"})
        verdict = engine.evaluate(action, DangerLevel.WARNING)
        assert verdict.verdict == "ASK"  # Even WARNING requires ASK

    def test_permissive_policy(self):
        """Permissive policy should allow more."""
        engine = PolicyEngine.create_permissive_policy()
        action = Action(tool_name="shell", parameters={"command": "git push --force"})
        verdict = engine.evaluate(action, DangerLevel.DANGEROUS)
        assert verdict.verdict == "ALLOW"  # Only CRITICAL is blocked

    def test_multiple_conditions_all_must_match(self):
        """All conditions in a rule must match (AND logic)."""
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    name="specific-shell",
                    priority=100,
                    condition={
                        "tool_name": "shell",
                        "danger_level": "DANGEROUS",
                    },
                    verdict="DENY",
                    reason="Dangerous shell is denied",
                ),
            ],
            default_verdict="ALLOW",
        )
        # Shell but SAFE — should not match
        action = Action(tool_name="shell", parameters={"command": "ls"})
        verdict = engine.evaluate(action, DangerLevel.SAFE)
        assert verdict.verdict == "ALLOW"  # Rule shouldn't match
        assert verdict.matched_rule == "default"
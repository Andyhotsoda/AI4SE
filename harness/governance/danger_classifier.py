"""Danger classifier — deterministic danger level classification for actions.

Classifies actions into 4 levels: SAFE, WARNING, DANGEROUS, CRITICAL.
Uses regex patterns and action type rules — NO LLM involved.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from harness.tools.base import Action, DangerLevel


# Shell command patterns by danger level
CRITICAL_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/", "Recursive root deletion"),
    (r"rm\s+-rf\s+/\s*--no-preserve-root", "Root deletion with no-preserve-root"),
    (r"mkfs\.", "Filesystem formatting"),
    (r"dd\s+if=.*of=/dev/", "Raw disk writes"),
    (r">\s*/dev/sd[a-z]", "Overwriting block devices"),
    (r"chmod\s+777\s+/", "World-writable root"),
    (r"chmod\s+-R\s+777\s+/", "Recursive world-writable root"),
    (r"curl.*\|\s*(ba)?sh", "Remote script execution via pipe"),
    (r"wget.*\|\s*(ba)?sh", "Remote script execution via pipe"),
    (r"eval\s+", "Dynamic code evaluation"),
    (r"shutdown\s", "System shutdown"),
    (r"reboot\s", "System reboot"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "Fork bomb"),
]

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s", "Recursive deletion in project"),
    (r"rm\s+-r\s", "Recursive deletion"),
    (r"rm\s+", "File deletion"),
    (r"git\s+push\s+--force", "Force push to remote"),
    (r"git\s+push\s+-f", "Force push to remote"),
    (r"git\s+push\s+--delete", "Delete remote branch"),
    (r"git\s+reset\s+--hard", "Hard git reset"),
    (r"pip\s+install", "Package installation"),
    (r"npm\s+install\s+-g", "Global npm install"),
    (r"sudo\s+", "Privilege escalation"),
    (r"docker\s+rm\s", "Docker container removal"),
    (r"docker\s+rmi\s", "Docker image removal"),
    (r"docker\s+system\s+prune", "Docker system prune"),
    (r"chmod\s+", "Permission changes"),
    (r"chown\s+", "Ownership changes"),
    (r"pip\s+uninstall", "Package uninstallation"),
    (r"npm\s+uninstall", "Package uninstallation"),
]

WARNING_PATTERNS: list[tuple[str, str]] = [
    (r"git\s+commit", "Git commit"),
    (r"git\s+push\b(?!\s+--force|\s+-f|\s+--delete)", "Git push (non-force)"),
    (r"mv\s+", "File move/rename"),
    (r"cp\s+", "File copy"),
    (r"pip\s+freeze", "Package list export"),
    (r"docker\s+build", "Docker build"),
    (r"docker\s+run", "Docker run"),
    (r"make\s+install", "Make install"),
    (r"pip\s+install\s+--user", "User package install"),
    (r"npm\s+install\b(?!\s+-g)", "Local npm install"),
]


class DangerClassifier:
    """
    Deterministic danger level classifier for actions.

    Classification rules:
    - SAFE: Read-only operations (read_file, list_directory)
    - WARNING: Write operations within project scope (write_file, mv, cp)
    - DANGEROUS: Destructive operations, network access, git push
    - CRITICAL: System-level destruction

    All classification is done by code (regex patterns + action type rules),
    NOT by LLM prompts.
    """

    def __init__(self, custom_rules: list[Callable[[Action], Optional[DangerLevel]]] | None = None):
        self._custom_rules = custom_rules or []

    def classify(self, action: Action) -> DangerLevel:
        """
        Classify an action's danger level deterministically.

        Args:
            action: The action to classify.

        Returns:
            DangerLevel enum value.
        """
        # Check custom rules first (highest priority)
        for rule in self._custom_rules:
            level = rule(action)
            if level is not None:
                return level

        # Built-in classification based on tool type
        return self._builtin_classify(action)

    def _builtin_classify(self, action: Action) -> DangerLevel:
        """Built-in classification by tool type."""
        tool_name = action.tool_name

        if tool_name == "read_file":
            return DangerLevel.SAFE

        if tool_name == "list_directory":
            return DangerLevel.SAFE

        if tool_name == "write_file":
            return DangerLevel.WARNING

        if tool_name == "shell":
            return self._classify_shell_command(action)

        if tool_name in ("run_tests",):
            return DangerLevel.WARNING

        # Unknown tools default to WARNING
        return DangerLevel.WARNING

    def _classify_shell_command(self, action: Action) -> DangerLevel:
        """Classify a shell command based on its content."""
        command = action.parameters.get("command", "")
        if not command:
            return DangerLevel.WARNING

        # Check CRITICAL patterns first
        for pattern, _description in CRITICAL_PATTERNS:
            if re.search(pattern, command):
                return DangerLevel.CRITICAL

        # Check DANGEROUS patterns
        for pattern, _description in DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return DangerLevel.DANGEROUS

        # Check WARNING patterns
        for pattern, _description in WARNING_PATTERNS:
            if re.search(pattern, command):
                return DangerLevel.WARNING

        # Default for shell commands: if it's read-only, it's SAFE
        if self._is_read_only_command(command):
            return DangerLevel.SAFE

        return DangerLevel.WARNING

    @staticmethod
    def _is_read_only_command(command: str) -> bool:
        """Check if a command appears to be read-only."""
        read_only_patterns = [
            r"^(ls|dir|cat|head|tail|less|more|find|grep|wc|sort|uniq|echo|pwd|whoami|date|which|type|git\s+status|git\s+log|git\s+diff|git\s+branch|python\s+\S+\s+--version|python\s+-m\s+pytest|pytest)",
            r"^(python|python3)\s+-c\s+",
        ]
        for pattern in read_only_patterns:
            if re.search(pattern, command.strip()):
                return True
        return False

    @staticmethod
    def get_risk_description(level: DangerLevel) -> str:
        """Get a human-readable description of a danger level."""
        descriptions = {
            DangerLevel.SAFE: "Read-only operation, no side effects",
            DangerLevel.WARNING: "Write operation within project scope",
            DangerLevel.DANGEROUS: "Destructive operation or network access",
            DangerLevel.CRITICAL: "System-level destruction risk",
        }
        return descriptions.get(level, "Unknown risk level")

    @staticmethod
    def get_command_danger_reason(command: str) -> Optional[str]:
        """Get the reason a command was classified at its danger level."""
        for pattern, description in CRITICAL_PATTERNS:
            if re.search(pattern, command):
                return description
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return description
        for pattern, description in WARNING_PATTERNS:
            if re.search(pattern, command):
                return description
        return None
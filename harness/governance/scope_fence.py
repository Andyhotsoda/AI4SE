"""
Scope fence — restricts agent operations to a defined boundary.

Features:
- Allowed directories: agent can only operate within these paths
- Allowed commands: agent can only execute commands in this whitelist
- Allowed file extensions: agent can only create/modify files with these extensions
- Denied patterns: files matching these patterns are off-limits

All path validation uses resolved absolute paths to prevent
path traversal attacks (e.g., ../../etc/passwd).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FenceVerdict:
    """Result of a scope fence validation."""
    allowed: bool
    reason: str = ""


class ScopeFence:
    """
    Restricts agent operations to a defined scope.

    Usage:
        fence = ScopeFence(
            allowed_directories=["/home/user/project"],
            allowed_commands=["python", "git", "pytest", "make"],
        )
        verdict = fence.validate_path("/home/user/project/main.py")
        # FenceVerdict(allowed=True, reason="")
    """

    DEFAULT_ALLOWED_EXTENSIONS = [
        ".py", ".txt", ".md", ".yaml", ".yml", ".json",
        ".toml", ".cfg", ".ini", ".gitignore", ".html",
        ".css", ".js", ".ts", ".jsx", ".tsx", ".csv",
        ".xml", ".rst", ".sh", ".bat", ".ps1", ".sql",
        ".env.example", ".template",
    ]

    DEFAULT_DENIED_PATTERNS = [
        r"\.env$",            # Environment files with secrets
        r"\.pem$",            # Private keys
        r"\.key$",            # Key files
        r"\.pfx$",            # Certificate stores
        r"credentials",       # Credential files
        r"[\\/]\.git[\\/]",   # Git internals
        r"[\\/]\.hg[\\/]",    # Mercurial internals
        r"[\\/]\.svn[\\/]",   # SVN internals
        r"[\\/]__pycache__",  # Python cache
        r"[\\/]\.pytest_cache",# Pytest cache
        r"[\\/]node_modules[\\/]", # Node modules
    ]

    def __init__(
        self,
        allowed_directories: list[str],
        allowed_commands: list[str] | None = None,
        allowed_extensions: list[str] | None = None,
        denied_patterns: list[str] | None = None,
    ):
        self._allowed_dirs = [Path(d).resolve() for d in allowed_directories]
        self._allowed_commands = allowed_commands or []
        self._allowed_extensions = allowed_extensions or self.DEFAULT_ALLOWED_EXTENSIONS
        self._denied_patterns = denied_patterns or self.DEFAULT_DENIED_PATTERNS

    def validate_path(self, path: str | Path) -> FenceVerdict:
        """
        Check if a file path is within the allowed scope.

        Validates:
        1. Path is under an allowed directory
        2. Path doesn't match any denied pattern
        3. File extension is allowed (if the file has an extension)

        Args:
            path: The file path to validate.

        Returns:
            FenceVerdict with allowed flag and reason.
        """
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError) as e:
            return FenceVerdict(False, f"Invalid path: {e}")

        # Check if under any allowed directory
        in_allowed_dir = any(
            str(resolved).startswith(str(allowed_dir))
            for allowed_dir in self._allowed_dirs
        )
        if not in_allowed_dir:
            return FenceVerdict(
                False,
                f"Path '{path}' is outside allowed directories: {[str(d) for d in self._allowed_dirs]}",
            )

        # Check denied patterns
        for pattern in self._denied_patterns:
            if re.search(pattern, str(resolved)):
                return FenceVerdict(
                    False,
                    f"Path '{path}' matches denied pattern '{pattern}'",
                )

        # Check extension (only if the file has an extension)
        if resolved.suffix:
            if resolved.suffix not in self._allowed_extensions:
                return FenceVerdict(
                    False,
                    f"File extension '{resolved.suffix}' is not allowed. "
                    f"Allowed: {self._allowed_extensions}",
                )

        return FenceVerdict(True, "")

    def validate_command(self, command: str) -> FenceVerdict:
        """
        Check if a shell command is within the allowed scope.

        If allowed_commands is empty, all commands are allowed.

        Args:
            command: The shell command to validate.

        Returns:
            FenceVerdict with allowed flag and reason.
        """
        if not self._allowed_commands:
            # No whitelist means all commands are allowed
            return FenceVerdict(True, "")

        if not command or not command.strip():
            return FenceVerdict(False, "Empty command")

        # Extract the base command (first word)
        base_cmd = command.strip().split()[0] if command.strip() else ""

        # Handle paths like /usr/bin/python or python3 -> python
        if "/" in base_cmd:
            base_cmd = Path(base_cmd).name

        if base_cmd not in self._allowed_commands:
            return FenceVerdict(
                False,
                f"Command '{base_cmd}' is not in allowed commands: {self._allowed_commands}",
            )

        return FenceVerdict(True, "")

    @property
    def allowed_directories(self) -> list[str]:
        return [str(d) for d in self._allowed_dirs]

    @property
    def allowed_commands(self) -> list[str]:
        return list(self._allowed_commands)

    @property
    def allowed_extensions(self) -> list[str]:
        return list(self._allowed_extensions)
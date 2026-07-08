"""Tests for the ScopeFence — deterministic, no LLM needed."""

import tempfile
from pathlib import Path

import pytest

from harness.governance.scope_fence import ScopeFence, FenceVerdict


class TestScopeFence:
    """Tests for the ScopeFence."""

    def setup_method(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.fence = ScopeFence(
            allowed_directories=[str(self.project_dir)],
            allowed_commands=["python", "pytest", "git", "make", "echo"],
        )

    def test_path_within_allowed_dir(self):
        """Path within allowed directory should be valid."""
        file_path = self.project_dir / "main.py"
        file_path.write_text("test")
        verdict = self.fence.validate_path(str(file_path))
        assert verdict.allowed is True

    def test_path_outside_allowed_dir(self):
        """Path outside allowed directory should be denied."""
        verdict = self.fence.validate_path("/etc/passwd")
        assert verdict.allowed is False
        assert "outside" in verdict.reason.lower()

    def test_path_traversal_blocked(self):
        """Path traversal using '../' should be blocked."""
        # Create a path that resolves outside the project
        traversal = self.project_dir / ".." / ".." / "etc" / "passwd"
        verdict = self.fence.validate_path(str(traversal))
        assert verdict.allowed is False

    def test_denied_pattern_env_file(self):
        """'.env' files should be denied by default."""
        env_path = self.project_dir / ".env"
        env_path.write_text("SECRET=123")
        verdict = self.fence.validate_path(str(env_path))
        assert verdict.allowed is False

    def test_denied_pattern_pem_file(self):
        """'.pem' files should be denied by default."""
        pem_path = self.project_dir / "key.pem"
        pem_path.write_text("KEY")
        verdict = self.fence.validate_path(str(pem_path))
        assert verdict.allowed is False

    def test_denied_pattern_credentials(self):
        """'credentials' files should be denied by default."""
        cred_path = self.project_dir / "credentials"
        cred_path.write_text("creds")
        verdict = self.fence.validate_path(str(cred_path))
        assert verdict.allowed is False

    def test_denied_pattern_git_internals(self):
        """'.git/' directory should be denied by default."""
        git_path = self.project_dir / ".git" / "config"
        git_path.parent.mkdir(exist_ok=True)
        if not git_path.exists():
            git_path.write_text("config")
        verdict = self.fence.validate_path(str(git_path))
        assert verdict.allowed is False

    def test_python_extension_allowed(self):
        """Python files should be allowed."""
        py_path = self.project_dir / "test.py"
        py_path.write_text("x=1")
        verdict = self.fence.validate_path(str(py_path))
        assert verdict.allowed is True

    def test_disallowed_extension_blocked(self):
        """Files with disallowed extensions should be blocked."""
        exe_path = self.project_dir / "malware.exe"
        exe_path.write_text("malware")
        verdict = self.fence.validate_path(str(exe_path))
        assert verdict.allowed is False

    def test_command_in_whitelist(self):
        """Whitelisted commands should be allowed."""
        verdict = self.fence.validate_command("python -m pytest")
        assert verdict.allowed is True

    def test_command_not_in_whitelist(self):
        """Non-whitelisted commands should be denied."""
        verdict = self.fence.validate_command("curl https://evil.com")
        assert verdict.allowed is False
        assert "curl" in verdict.reason

    def test_empty_command_list_allows_all(self):
        """Empty allowed_commands list should allow all commands."""
        fence = ScopeFence(allowed_directories=["."], allowed_commands=[])
        verdict = fence.validate_command("anything goes")
        assert verdict.allowed is True

    def test_empty_command_blocked(self):
        """Empty command should be blocked."""
        verdict = self.fence.validate_command("")
        assert verdict.allowed is False

    def test_command_with_path_resolved(self):
        """Commands with full paths should be resolved to basename."""
        fence = ScopeFence(
            allowed_directories=["."],
            allowed_commands=["python"],
        )
        verdict = fence.validate_command("/usr/bin/python script.py")
        assert verdict.allowed is True

    def test_nonexistent_path_returns_error(self):
        """Non-existent path should return an error verdict."""
        verdict = self.fence.validate_path("/nonexistent/path/file.txt")
        assert verdict.allowed is False

    def test_properties(self):
        """Properties should return correct values."""
        assert self.project_dir.name in self.fence.allowed_directories[0]
        assert "python" in self.fence.allowed_commands
        assert ".py" in self.fence.allowed_extensions
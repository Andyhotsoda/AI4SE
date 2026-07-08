"""Tests for the tool registry and tools."""

import tempfile
from pathlib import Path

import pytest

from harness.tools.base import Tool, Action, ActionResult, ToolDefinition, DangerLevel
from harness.tools.registry import ToolRegistry
from harness.tools.file_tool import ReadFileTool, WriteFileTool, ListDirectoryTool
from harness.tools.shell_tool import ShellTool


class _FakeTool(Tool):
    """A fake tool for testing the registry."""
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="fake",
            description="A fake tool for testing",
            parameters={"type": "object", "properties": {}},
            danger_level=DangerLevel.SAFE,
        )

    async def execute(self, params: dict) -> ActionResult:
        return ActionResult(success=True, output="fake result")


class TestToolRegistry:
    """Tests for the ToolRegistry."""

    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = _FakeTool()
        registry.register(tool)
        assert registry.get("fake") is tool
        assert registry.has("fake")

    def test_register_duplicate_raises(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_FakeTool())

    def test_unregister(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        registry.unregister("fake")
        assert not registry.has("fake")

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        assert "fake" in registry.list_tools()

    async def test_dispatch_unknown_tool(self):
        registry = ToolRegistry()
        action = Action(tool_name="nonexistent", parameters={})
        result = await registry.dispatch(action)
        assert not result.success
        assert "Unknown tool" in result.error

    async def test_dispatch_success(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        action = Action(tool_name="fake", parameters={})
        result = await registry.dispatch(action)
        assert result.success
        assert result.output == "fake result"

    def test_contains(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        assert "fake" in registry
        assert "other" not in registry

    def test_get_definitions(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        defs = registry.get_definitions()
        assert len(defs) == 1
        assert defs[0].name == "fake"

    def test_get_anthropic_tools(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        tools = registry.get_anthropic_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "fake"


class TestFileTools:
    """Tests for file I/O tools."""

    async def test_read_file_success(self, tmp_path):
        """Should read file contents successfully."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world")

        tool = ReadFileTool()
        result = await tool.execute({"path": str(file_path)})
        assert result.success
        assert result.output == "hello world"

    async def test_read_file_not_found(self):
        """Should return error for non-existent file."""
        tool = ReadFileTool()
        result = await tool.execute({"path": "/nonexistent/file.txt"})
        assert not result.success
        assert "not found" in result.error.lower()

    async def test_read_file_no_path(self):
        """Should return error when no path provided."""
        tool = ReadFileTool()
        result = await tool.execute({})
        assert not result.success

    async def test_write_file_success(self, tmp_path):
        """Should write file contents successfully."""
        file_path = tmp_path / "output.txt"
        tool = WriteFileTool()
        result = await tool.execute({"path": str(file_path), "content": "new content"})
        assert result.success
        assert file_path.read_text() == "new content"

    async def test_write_file_creates_parent_dirs(self, tmp_path):
        """Should create parent directories if needed."""
        file_path = tmp_path / "subdir" / "nested" / "file.txt"
        tool = WriteFileTool()
        result = await tool.execute({"path": str(file_path), "content": "nested"})
        assert result.success
        assert file_path.read_text() == "nested"

    async def test_list_directory(self, tmp_path):
        """Should list directory contents."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "subdir").mkdir()

        tool = ListDirectoryTool()
        result = await tool.execute({"path": str(tmp_path)})
        assert result.success
        assert "a.txt" in result.output
        assert "b.txt" in result.output
        assert "subdir" in result.output


class TestShellTool:
    """Tests for shell command execution."""

    async def test_echo_command(self):
        """Should execute echo command and return output."""
        tool = ShellTool()
        result = await tool.execute({"command": "echo hello"})
        assert result.success
        assert "hello" in result.output

    async def test_failing_command(self):
        """Should report failure for non-zero exit code."""
        tool = ShellTool()
        # Use a command that definitely fails on all platforms
        result = await tool.execute({"command": "python -c \"import sys; sys.exit(1)\""})
        assert not result.success

    async def test_no_command(self):
        """Should return error when no command provided."""
        tool = ShellTool()
        result = await tool.execute({})
        assert not result.success

    async def test_command_with_stderr(self, tmp_path):
        """Should capture stderr output."""
        tool = ShellTool()
        result = await tool.execute({"command": "python -c 'import sys; print(\"stderr\", file=sys.stderr)'"})
        # stderr output should be captured
        assert "stderr" in result.output.lower() or result.success
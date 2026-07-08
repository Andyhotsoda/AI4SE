"""File I/O tools: read, write, and list directory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from harness.tools.base import Tool, ActionResult, ToolDefinition, DangerLevel


class ReadFileTool(Tool):
    """Read contents of a file."""

    def __init__(self, max_size_bytes: int = 10 * 1024 * 1024):
        self._max_size = max_size_bytes

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read the contents of a file at the given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (relative to working directory).",
                    },
                },
                "required": ["path"],
            },
            danger_level=DangerLevel.SAFE,
        )

    async def execute(self, params: dict[str, Any]) -> ActionResult:
        path = params.get("path", "")
        if not path:
            return ActionResult(success=False, error="No path provided")

        try:
            file_path = Path(path).resolve()
            if not file_path.exists():
                return ActionResult(
                    success=False,
                    error=f"File not found: {path}",
                )
            if not file_path.is_file():
                return ActionResult(
                    success=False,
                    error=f"Not a file: {path}",
                )
            if file_path.stat().st_size > self._max_size:
                return ActionResult(
                    success=False,
                    error=f"File too large: {file_path.stat().st_size} bytes (max {self._max_size})",
                )

            content = file_path.read_text(encoding="utf-8")
            return ActionResult(
                success=True,
                output=content,
                metadata={"path": str(file_path), "size": len(content)},
            )
        except UnicodeDecodeError:
            return ActionResult(
                success=False,
                error=f"Cannot read file as UTF-8 text: {path}",
            )
        except PermissionError:
            return ActionResult(
                success=False,
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"Failed to read file: {type(e).__name__}: {e}",
            )


class WriteFileTool(Tool):
    """Write content to a file."""

    def __init__(self, max_size_bytes: int = 10 * 1024 * 1024):
        self._max_size = max_size_bytes

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="Write content to a file at the given path. Creates the file if it doesn't exist, overwrites if it does.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to write the file to (relative to working directory).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
            danger_level=DangerLevel.WARNING,
        )

    async def execute(self, params: dict[str, Any]) -> ActionResult:
        path = params.get("path", "")
        content = params.get("content", "")

        if not path:
            return ActionResult(success=False, error="No path provided")
        if len(content) > self._max_size:
            return ActionResult(
                success=False,
                error=f"Content too large: {len(content)} bytes (max {self._max_size})",
            )

        try:
            file_path = Path(path).resolve()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ActionResult(
                success=True,
                output=f"Wrote {len(content)} bytes to {path}",
                metadata={"path": str(file_path), "size": len(content)},
            )
        except PermissionError:
            return ActionResult(
                success=False,
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"Failed to write file: {type(e).__name__}: {e}",
            )


class ListDirectoryTool(Tool):
    """List contents of a directory."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_directory",
            description="List files and directories at the given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory to list (relative to working directory).",
                    },
                },
                "required": ["path"],
            },
            danger_level=DangerLevel.SAFE,
        )

    async def execute(self, params: dict[str, Any]) -> ActionResult:
        path = params.get("path", ".")
        try:
            dir_path = Path(path).resolve()
            if not dir_path.exists():
                return ActionResult(
                    success=False,
                    error=f"Directory not found: {path}",
                )
            if not dir_path.is_dir():
                return ActionResult(
                    success=False,
                    error=f"Not a directory: {path}",
                )

            entries = []
            for entry in sorted(dir_path.iterdir()):
                entry_type = "dir" if entry.is_dir() else "file"
                entries.append(f"{entry_type:5} {entry.name}")

            output = "\n".join(entries) if entries else "(empty directory)"
            return ActionResult(
                success=True,
                output=output,
                metadata={"path": str(dir_path), "count": len(entries)},
            )
        except PermissionError:
            return ActionResult(
                success=False,
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"Failed to list directory: {type(e).__name__}: {e}",
            )
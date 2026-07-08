"""Tool registry — registration and dispatch of tools."""

from __future__ import annotations

from typing import Any, Optional

from harness.tools.base import Tool, Action, ActionResult, ToolDefinition


class ToolRegistry:
    """
    Registry for agent tools. Handles registration, lookup, and dispatch.

    Usage:
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(ShellTool())

        action = Action(tool_name="shell", parameters={"command": "pytest"})
        result = await registry.dispatch(action)
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ValueError if tool name already registered."""
        name = tool.definition.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    def get_definitions(self) -> list[ToolDefinition]:
        """Return all tool definitions for LLM context."""
        return [tool.definition for tool in self._tools.values()]

    def get_anthropic_tools(self) -> list[dict]:
        """Return all tool definitions in Anthropic format."""
        return [tool.definition.to_anthropic_schema() for tool in self._tools.values()]

    def get_openai_tools(self) -> list[dict]:
        """Return all tool definitions in OpenAI format."""
        return [tool.definition.to_openai_schema() for tool in self._tools.values()]

    async def dispatch(self, action: Action) -> ActionResult:
        """
        Dispatch an action to the appropriate tool.

        Args:
            action: The action to dispatch.

        Returns:
            ActionResult from the tool execution.

        Raises:
            KeyError: If the tool is not registered.
        """
        tool = self._tools.get(action.tool_name)
        if tool is None:
            return ActionResult(
                success=False,
                error=f"Unknown tool: '{action.tool_name}'. Available tools: {self.list_tools()}",
            )

        try:
            # Validate parameters
            validation_error = tool.validate_params(action.parameters)
            if validation_error:
                return ActionResult(success=False, error=validation_error)

            return await tool.execute(action.parameters)
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"Tool execution failed: {type(e).__name__}: {e}",
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
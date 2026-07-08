"""
Context builder — assembles the LLM context from all sources.

Organizes: system prompt, task, conversation history, project memory,
tool definitions, and last feedback signal into a single messages list
for the LLM completion call.
"""

from __future__ import annotations

from harness.tools.registry import ToolRegistry
from harness.memory.session_store import SessionStore
from harness.memory.project_store import ProjectStore


DEFAULT_SYSTEM_PROMPT = """You are a helpful coding assistant. You converse naturally with the user while executing coding tasks.

When you need to perform an action (read/write files, run commands), embed a JSON tool call in your response:

{"tool": "write_file", "path": "hello.py", "content": "print('Hello, World!')"}

Available tools:
- read_file: {"tool": "read_file", "path": "file.py"}
- write_file: {"tool": "write_file", "path": "file.py", "content": "full content\\nwith newlines"}
- list_directory: {"tool": "list_directory", "path": "."}
- shell: {"tool": "shell", "command": "python hello.py"}
- stop: {"tool": "stop", "reason": "done"}

RULES:
1. Talk naturally — explain what you're doing, then embed the JSON tool call.
2. Put each JSON tool call on its own line, separate from your text.
3. For write_file, put the ENTIRE file content as a single escaped string.
4. After creating/modifying code, run it to verify.
5. You can chain multiple actions in one response to complete a task efficiently.
6. When the task is done, just say so without a tool call, or use the stop tool.
7. Stay within the project directory. Dangerous commands (rm -rf, sudo) are blocked.
"""


class ContextBuilder:
    """
    Assembles the full LLM context from system prompt, task, history,
    tool definitions, project memory, and feedback signals.
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        tool_registry: ToolRegistry | None = None,
        session_store: SessionStore | None = None,
        project_store: ProjectStore | None = None,
    ):
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._tool_registry = tool_registry
        self._session_store = session_store
        self._project_store = project_store

    def build(self, include_tools: bool = True) -> list[dict[str, str]]:
        """
        Build the full messages list for the LLM completion call.

        Args:
            include_tools: Whether to include tool descriptions.

        Returns:
            List of message dicts with 'role' and 'content'.
        """
        messages = []

        # 1. System prompt
        system_content = self._build_system_prompt(include_tools)
        messages.append({"role": "system", "content": system_content})

        # 2. Project memory (if available)
        if self._project_store:
            project_context = self._project_store.get_for_context()
            if project_context:
                messages.append({
                    "role": "system",
                    "content": f"Project context:\n{project_context}",
                })

        # 3. Conversation history
        if self._session_store:
            messages.extend(self._session_store.get_messages_for_llm())

        return messages

    def _build_system_prompt(self, include_tools: bool) -> str:
        """Build the system prompt with tool descriptions."""
        prompt = self._system_prompt

        if include_tools and self._tool_registry:
            tools_desc = self._format_tools()
            prompt = prompt.replace("{tools_description}", tools_desc)

        return prompt

    def _format_tools(self) -> str:
        """Format tool definitions for the system prompt."""
        if not self._tool_registry:
            return "No tools available."

        lines = []
        for tool_def in self._tool_registry.get_definitions():
            lines.append(f"- **{tool_def.name}**: {tool_def.description}")
        return "\n".join(lines)

    def build_feedback_context(self, feedback_message: dict[str, str]) -> None:
        """Add a feedback message to the session store."""
        if self._session_store:
            self._session_store.add_turn(
                role=feedback_message["role"],
                content=feedback_message["content"],
            )

    @property
    def system_prompt(self) -> str:
        return self._system_prompt
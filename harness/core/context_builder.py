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


DEFAULT_SYSTEM_PROMPT = """You are a coding agent. Your task is to help write and modify code.

You have access to the following tools:
{tools_description}

For each action, respond with a JSON object in the format:
```json
{{"tool": "tool_name", "param1": "value1", ...}}
```

Available tools:
- read_file: Read a file's contents. Parameters: {{"path": "path/to/file"}}
- write_file: Write content to a file. Parameters: {{"path": "path/to/file", "content": "content"}}
- list_directory: List directory contents. Parameters: {{"path": "path/to/dir"}}
- shell: Execute a shell command. Parameters: {{"command": "the command"}}
- stop: Signal task completion. Parameters: {{"reason": "why you're done"}}

IMPORTANT SAFETY RULES:
1. All actions are checked by a governance guardrail before execution.
2. Dangerous commands (rm -rf, sudo, etc.) will be blocked or require human approval.
3. Stay within the project directory.
4. After making changes, run the tests to verify your work.

Respond with ONE action at a time. After each action, you will receive the result.
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

    def build(self, task: str, include_tools: bool = True) -> list[dict[str, str]]:
        """
        Build the full messages list for the LLM completion call.

        Args:
            task: The user's task description.
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

        # 4. Task (if this is the first turn)
        if not self._session_store or self._session_store.turn_count == 0:
            messages.append({"role": "user", "content": task})

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
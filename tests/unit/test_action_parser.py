"""Tests for action parser."""

from harness.core.action_parser import ActionParser


class TestActionParser:
    """Tests for the ActionParser."""

    def test_parse_simple_json_action(self):
        """Should parse a simple JSON action."""
        output = '{"tool": "shell", "command": "pytest"}'
        actions = ActionParser.parse(output)
        assert len(actions) == 1
        assert actions[0].tool_name == "shell"
        assert actions[0].parameters["command"] == "pytest"

    def test_parse_json_block(self):
        """Should parse JSON from markdown code block."""
        output = '''```json
{"tool": "read_file", "path": "main.py"}
```'''
        actions = ActionParser.parse(output)
        assert len(actions) == 1
        assert actions[0].tool_name == "read_file"
        assert actions[0].parameters["path"] == "main.py"

    def test_parse_multiple_json_blocks(self):
        """Should parse multiple JSON blocks."""
        output = '''```json
{"tool": "read_file", "path": "main.py"}
```
```json
{"tool": "shell", "command": "pytest"}
```'''
        actions = ActionParser.parse(output)
        assert len(actions) == 2
        assert actions[0].tool_name == "read_file"
        assert actions[1].tool_name == "shell"

    def test_parse_nested_parameters(self):
        """Should parse action with nested parameters dict."""
        output = '{"tool": "write_file", "parameters": {"path": "test.py", "content": "x=1"}}'
        actions = ActionParser.parse(output)
        assert len(actions) == 1
        assert actions[0].tool_name == "write_file"
        assert actions[0].parameters["path"] == "test.py"
        assert actions[0].parameters["content"] == "x=1"

    def test_invalid_json_returns_empty(self):
        """Should return empty list for invalid JSON."""
        output = "not json at all"
        actions = ActionParser.parse(output)
        assert len(actions) == 0

    def test_unknown_tool_ignored(self):
        """Should ignore actions with unknown tool names."""
        output = '{"tool": "unknown_tool", "param": "value"}'
        actions = ActionParser.parse(output)
        assert len(actions) == 0

    def test_has_stop_action(self):
        """Should detect stop actions."""
        actions = ActionParser.parse('{"tool": "stop", "reason": "done"}')
        assert ActionParser.has_stop_action(actions)

    def test_has_finish_action(self):
        """Should detect finish actions."""
        actions = ActionParser.parse('{"tool": "finish", "reason": "all tests pass"}')
        assert ActionParser.has_stop_action(actions)

    def test_get_stop_reason(self):
        """Should extract reason from stop action."""
        actions = ActionParser.parse('{"tool": "stop", "reason": "task complete"}')
        reason = ActionParser.get_stop_reason(actions)
        assert reason == "task complete"

    def test_parse_tool_name_alias(self):
        """Should support 'tool_name' as alias for 'tool'."""
        output = '{"tool_name": "shell", "command": "ls"}'
        actions = ActionParser.parse(output)
        assert len(actions) == 1
        assert actions[0].tool_name == "shell"
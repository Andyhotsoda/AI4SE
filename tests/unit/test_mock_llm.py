"""Tests for Mock LLM client."""

import pytest

from harness.llm.mock_client import MockLLMClient


class TestMockLLMClient:
    """Tests for the deterministic mock LLM client."""

    async def test_script_mode_returns_in_order(self):
        """In script mode, responses should be returned in order."""
        mock = MockLLMClient(responses=[
            "first response",
            "second response",
            "third response",
        ])

        r1 = await mock.complete([{"role": "user", "content": "hello"}])
        r2 = await mock.complete([{"role": "user", "content": "hello again"}])
        r3 = await mock.complete([{"role": "user", "content": "hello once more"}])

        assert r1.content == "first response"
        assert r2.content == "second response"
        assert r3.content == "third response"
        assert mock.call_count == 3

    async def test_script_mode_returns_default_after_exhaustion(self):
        """After scripted responses are exhausted, return default."""
        mock = MockLLMClient(responses=["only one"], default_response="default")

        r1 = await mock.complete([{"role": "user", "content": "hi"}])
        r2 = await mock.complete([{"role": "user", "content": "hi again"}])

        assert r1.content == "only one"
        assert r2.content == "default"

    async def test_pattern_mode_matches_regex(self):
        """Pattern mode should match input against regex patterns."""
        mock = MockLLMClient(responses={
            "read": '{"tool": "read_file", "path": "main.py"}',
            "test": '{"tool": "shell", "command": "pytest"}',
        })

        r1 = await mock.complete([{"role": "user", "content": "please read the file"}])
        r2 = await mock.complete([{"role": "user", "content": "run the tests now"}])

        assert "read_file" in r1.content
        assert "pytest" in r2.content

    async def test_pattern_mode_case_insensitive(self):
        """Pattern matching should be case insensitive."""
        mock = MockLLMClient(responses={
            "DELETE": '{"tool": "shell", "command": "rm file"}',
        })

        r = await mock.complete([{"role": "user", "content": "please delete the file"}])
        assert "rm file" in r.content

    async def test_counts_tokens(self):
        """Token counting should work roughly."""
        mock = MockLLMClient()
        # ~4 chars per token
        token_count = mock.count_tokens("hello world!")  # 12 chars
        assert token_count == 3  # 12 // 4 = 3

    async def test_records_call_history(self):
        """Call history should record all calls."""
        mock = MockLLMClient(responses=["a", "b"])

        await mock.complete([{"role": "user", "content": "msg1"}])
        await mock.complete([{"role": "user", "content": "msg2"}])

        history = mock.call_history
        assert len(history) == 2
        assert history[0]["call_index"] == 0
        assert history[1]["call_index"] == 1
        assert history[0]["messages"][0]["content"] == "msg1"

    async def test_reset_clears_state(self):
        """Reset should clear call count and history."""
        mock = MockLLMClient(responses=["a", "b"])

        await mock.complete([{"role": "user", "content": "msg"}])
        assert mock.call_count == 1

        mock.reset()
        assert mock.call_count == 0
        assert len(mock.call_history) == 0

    async def test_no_responses_uses_default(self):
        """With no responses configured, should use default."""
        mock = MockLLMClient(default_response="fallback")

        r = await mock.complete([{"role": "user", "content": "anything"}])
        assert r.content == "fallback"

    async def test_response_model_field(self):
        """Response should have model='mock'."""
        mock = MockLLMClient(responses=["test"])
        r = await mock.complete([{"role": "user", "content": "hi"}])
        assert r.model == "mock"

    async def test_usage_in_response(self):
        """Response should include token usage."""
        mock = MockLLMClient(responses=["test response"])
        r = await mock.complete([{"role": "user", "content": "hello"}])
        assert "input_tokens" in r.usage
        assert "output_tokens" in r.usage
        assert r.usage["input_tokens"] > 0
        assert r.usage["output_tokens"] > 0
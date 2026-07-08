"""Tests for stop decision engine."""

from harness.core.stop_decision import StopDecisionEngine, StopReason


class TestStopDecisionEngine:
    """Tests for the stop decision engine."""

    def test_should_not_stop_initially(self):
        """Should not stop on first iteration with no issues."""
        engine = StopDecisionEngine(max_iterations=10)
        decision = engine.evaluate()
        assert not decision.should_stop

    def test_should_stop_on_agent_stop_signal(self):
        """Should stop when agent emits stop action."""
        engine = StopDecisionEngine(max_iterations=10)
        decision = engine.evaluate(agent_stopped=True)
        assert decision.should_stop
        assert decision.reason == StopReason.TASK_COMPLETE

    def test_should_stop_on_max_iterations(self):
        """Should stop when max iterations reached."""
        engine = StopDecisionEngine(max_iterations=3)
        engine.evaluate()
        engine.evaluate()
        decision = engine.evaluate()
        assert decision.should_stop
        assert decision.reason == StopReason.MAX_ITERATIONS

    def test_should_stop_on_max_consecutive_failures(self):
        """Should stop when too many consecutive failures."""
        engine = StopDecisionEngine(max_consecutive_failures=3)
        engine.evaluate(action_succeeded=False)
        engine.evaluate(action_succeeded=False)
        decision = engine.evaluate(action_succeeded=False)
        assert decision.should_stop
        assert decision.reason == StopReason.MAX_FAILURES

    def test_success_resets_failure_count(self):
        """A successful action should reset the consecutive failure count."""
        engine = StopDecisionEngine(max_consecutive_failures=3)
        engine.evaluate(action_succeeded=False)
        engine.evaluate(action_succeeded=False)
        engine.evaluate(action_succeeded=True)  # Reset
        engine.evaluate(action_succeeded=False)
        engine.evaluate(action_succeeded=False)
        decision = engine.evaluate(action_succeeded=False)
        # total failures since last success = 3
        assert decision.should_stop
        assert decision.reason == StopReason.MAX_FAILURES

    def test_should_stop_on_llm_error(self):
        """Should stop on LLM error."""
        engine = StopDecisionEngine()
        decision = engine.evaluate(llm_error=True)
        assert decision.should_stop
        assert decision.reason == StopReason.LLM_ERROR

    def test_should_stop_on_manual_stop(self):
        """Should stop on manual user interruption."""
        engine = StopDecisionEngine()
        decision = engine.evaluate(manual_stop=True)
        assert decision.should_stop
        assert decision.reason == StopReason.MANUAL_STOP

    def test_reset_clears_counters(self):
        """Reset should clear iteration and failure counters."""
        engine = StopDecisionEngine()
        engine.evaluate(action_succeeded=False)
        engine.evaluate(action_succeeded=False)
        assert engine.iteration == 2
        assert engine.consecutive_failures == 2

        engine.reset()
        assert engine.iteration == 0
        assert engine.consecutive_failures == 0

    def test_stop_reason_priority(self):
        """Manual stop should have highest priority."""
        engine = StopDecisionEngine()
        decision = engine.evaluate(
            agent_stopped=True,
            manual_stop=True,
        )
        assert decision.should_stop
        assert decision.reason == StopReason.MANUAL_STOP
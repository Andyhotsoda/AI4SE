"""
Agent main loop — the central orchestrator.

The Agent class is the heart of the harness. It wires together all six
dimensions (decision, tools, memory, governance, feedback, config) into
a single run loop:

    context → LLM → parse → govern → execute → feedback → memory → stop?
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from harness.llm.base import LLMClient, LLMError
from harness.tools.base import Action, ActionResult
from harness.tools.registry import ToolRegistry
from harness.core.action_parser import ActionParser
from harness.core.stop_decision import StopDecisionEngine, StopReason
from harness.core.context_builder import ContextBuilder
from harness.governance.action_interceptor import ActionInterceptor, InterceptResult
from harness.governance.sandbox import Sandbox
from harness.feedback.test_runner import SuiteRunner, TestResult
from harness.feedback.failure_classifier import FailureClassifier
from harness.feedback.feedback_injector import FeedbackInjector
from harness.memory.session_store import SessionStore
from harness.memory.project_store import ProjectStore


@dataclass
class AgentTurn:
    """Record of a single agent turn (iteration)."""
    iteration: int
    llm_response: str
    actions: list[Action]
    intercept_results: list[InterceptResult]
    action_results: list[ActionResult]
    feedback: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentResult:
    """Final result of the agent run."""
    success: bool
    stop_reason: StopReason
    message: str = ""
    turns: list[AgentTurn] = field(default_factory=list)
    total_iterations: int = 0
    total_actions: int = 0


class Agent:
    """
    The main agent orchestrator.

    Usage:
        agent = Agent(
            llm=mock_llm,  # or AnthropicClient
            tools=registry,
            interceptor=governor,
            config=config,
        )
        result = await agent.run("Write a Python function that adds two numbers")
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        interceptor: ActionInterceptor,
        sandbox: Sandbox,
        context_builder: ContextBuilder,
        test_runner: SuiteRunner,
        feedback_injector: FeedbackInjector,
        session_store: SessionStore,
        project_store: ProjectStore,
        max_iterations: int = 50,
        max_consecutive_failures: int = 5,
    ):
        self._llm = llm
        self._tools = tools
        self._interceptor = interceptor
        self._sandbox = sandbox
        self._context_builder = context_builder
        self._test_runner = test_runner
        self._feedback_injector = feedback_injector
        self._session_store = session_store
        self._project_store = project_store

        self._stop_engine = StopDecisionEngine(
            max_iterations=max_iterations,
            max_consecutive_failures=max_consecutive_failures,
        )
        self._turns: list[AgentTurn] = []

    async def run(self, task: str) -> AgentResult:
        """
        Run the agent main loop.

        Args:
            task: The user's task description.

        Returns:
            AgentResult with the final outcome.
        """
        self._stop_engine.reset()
        self._turns = []

        while True:
            # 1. Build context
            messages = self._context_builder.build(task, include_tools=True)

            # 2. Call LLM
            try:
                llm_response = await self._llm.complete(messages)
            except LLMError as e:
                decision = self._stop_engine.evaluate(llm_error=True)
                return AgentResult(
                    success=False,
                    stop_reason=decision.reason,
                    message=f"LLM error: {e}",
                    turns=self._turns,
                    total_iterations=self._stop_engine.iteration,
                )

            # Record LLM response in session
            self._session_store.add_turn(
                role="assistant",
                content=llm_response.content,
            )

            # 3. Parse actions
            actions = ActionParser.parse(llm_response.content)

            # 4. Process each action through governance and tools
            intercept_results = []
            action_results = []
            all_succeeded = True

            for action in actions:
                # 4a. Governance intercept
                intercept_result = await self._interceptor.intercept(action)
                intercept_results.append(intercept_result)

                if not intercept_result.allowed:
                    # Inject denial feedback
                    denial_msg = (
                        f"Action '{action.tool_name}' was blocked: {intercept_result.reason}"
                    )
                    self._session_store.add_turn(role="feedback", content=denial_msg)
                    all_succeeded = False
                    continue

                # 4b. Execute (possibly sandboxed)
                if intercept_result.use_sandbox:
                    result = await self._sandbox.execute(action, self._tools.dispatch)
                else:
                    result = await self._tools.dispatch(action)

                action_results.append(result)

                # Record action result in session
                result_msg = (
                    f"Action result: {result.output}"
                    if result.success
                    else f"Action failed: {result.error}"
                )
                self._session_store.add_turn(role="feedback", content=result_msg)

                if not result.success:
                    all_succeeded = False

            # 5. Run feedback loop (tests)
            feedback = await self._run_feedback()

            # 6. Record turn
            turn = AgentTurn(
                iteration=self._stop_engine.iteration + 1,
                llm_response=llm_response.content,
                actions=actions,
                intercept_results=intercept_results,
                action_results=action_results,
                feedback=feedback,
            )
            self._turns.append(turn)

            # 7. Check stop conditions
            agent_stopped = ActionParser.has_stop_action(actions)
            decision = self._stop_engine.evaluate(
                agent_stopped=agent_stopped,
                action_succeeded=all_succeeded if actions else None,
            )

            if decision.should_stop:
                return AgentResult(
                    success=(decision.reason == StopReason.TASK_COMPLETE),
                    stop_reason=decision.reason,
                    message=decision.message,
                    turns=self._turns,
                    total_iterations=self._stop_engine.iteration,
                    total_actions=sum(len(t.actions) for t in self._turns),
                )

    async def _run_feedback(self) -> Optional[str]:
        """Run the feedback loop (tests) and inject results into context."""
        try:
            test_result = await self._test_runner.run_pytest()

            if FeedbackInjector.needs_correction(test_result):
                feedback_msg = self._feedback_injector.build_feedback_message(test_result)
                self._context_builder.build_feedback_context(feedback_msg)
                classifier = FailureClassifier()
                return classifier.generate_feedback(test_result)
            return None
        except Exception:
            return None  # Feedback is best-effort

    @property
    def turns(self) -> list[AgentTurn]:
        return list(self._turns)

    @property
    def iteration_count(self) -> int:
        return self._stop_engine.iteration
"""
Agent main loop — natural language + auto-planning.

The agent converses naturally with the user, embedding JSON tool calls
in its responses when it needs to execute actions. It decides its own
next steps and stops when the task is complete.
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
from harness.memory.session_store import SessionStore
from harness.memory.project_store import ProjectStore


@dataclass
class ToolExecution:
    """Record of a single tool execution within a turn."""
    action: Action
    result: ActionResult
    allowed: bool
    blocked_reason: str = ""


@dataclass
class AgentTurn:
    """Record of a single agent turn."""
    iteration: int
    full_response: str          # Full LLM response (natural language + tool calls)
    natural_text: str           # Just the natural language part
    tool_executions: list[ToolExecution] = field(default_factory=list)
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
    Natural-language agent with auto-planning.

    The agent:
    1. Converses in natural language
    2. Embeds JSON tool calls when it needs to act
    3. Decides its own next steps
    4. Stops when task is complete or user interrupts
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        interceptor: ActionInterceptor,
        sandbox: Sandbox,
        context_builder: ContextBuilder,
        session_store: SessionStore,
        project_store: ProjectStore,
        max_iterations: int = 30,
        max_consecutive_failures: int = 5,
        on_turn: callable = None,  # Callback(turn: AgentTurn) for streaming
    ):
        self._llm = llm
        self._tools = tools
        self._interceptor = interceptor
        self._sandbox = sandbox
        self._context_builder = context_builder
        self._session_store = session_store
        self._project_store = project_store
        self._on_turn = on_turn

        self._stop_engine = StopDecisionEngine(
            max_iterations=max_iterations,
            max_consecutive_failures=max_consecutive_failures,
        )
        self._turns: list[AgentTurn] = []

    async def run(self, task: str) -> AgentResult:
        """Run the agent on a task. Returns when done or interrupted."""
        self._stop_engine.reset()
        self._turns = []

        # Add user task to session
        self._session_store.add_turn(role="user", content=task)

        while True:
            # 1. Build context
            messages = self._context_builder.build()

            # 2. Call LLM
            try:
                llm_response = await self._llm.complete(messages)
            except LLMError as e:
                decision = self._stop_engine.evaluate(llm_error=True)
                return AgentResult(
                    success=False, stop_reason=decision.reason,
                    message=f"LLM error: {e}", turns=self._turns,
                    total_iterations=self._stop_engine.iteration,
                )

            full_response = llm_response.content

            # 3. Parse actions from the response
            actions = ActionParser.parse(full_response)

            # 4. Extract natural language (remove JSON tool calls)
            natural_text = ActionParser.extract_text(full_response)

            # 5. Record LLM response in session
            self._session_store.add_turn(role="assistant", content=full_response)

            # 6. Execute each tool call
            tool_executions = []
            all_succeeded = True

            for action in actions:
                # 6a. Governance check
                intercept = await self._interceptor.intercept(action)

                if not intercept.allowed:
                    tool_executions.append(ToolExecution(
                        action=action,
                        result=ActionResult(success=False, error=intercept.reason),
                        allowed=False,
                        blocked_reason=intercept.reason,
                    ))
                    # Inject blocked feedback
                    self._session_store.add_turn(
                        role="feedback",
                        content=f"Action blocked: {intercept.reason}",
                    )
                    all_succeeded = False
                    continue

                # 6b. Execute
                if intercept.use_sandbox:
                    result = await self._sandbox.execute(action, self._tools.dispatch)
                else:
                    result = await self._tools.dispatch(action)

                tool_executions.append(ToolExecution(
                    action=action, result=result, allowed=True,
                ))

                # Feed result back
                result_msg = f"Result of {action.tool_name}: {result.output if result.success else result.error}"
                self._session_store.add_turn(role="feedback", content=result_msg)

                if not result.success:
                    all_succeeded = False

            # 7. Record turn
            turn = AgentTurn(
                iteration=self._stop_engine.iteration + 1,
                full_response=full_response,
                natural_text=natural_text,
                tool_executions=tool_executions,
            )
            self._turns.append(turn)

            # Stream to callback
            if self._on_turn:
                self._on_turn(turn)

            # 8. Check stop conditions
            agent_stopped = ActionParser.has_stop_action(actions)

            # Agent also "stops" when it has no tool calls (just talking)
            if not actions and natural_text.strip():
                agent_stopped = True

            decision = self._stop_engine.evaluate(
                agent_stopped=agent_stopped,
                action_succeeded=all_succeeded if actions else None,
            )

            if decision.should_stop:
                return AgentResult(
                    success=(decision.reason in (StopReason.TASK_COMPLETE,)),
                    stop_reason=decision.reason,
                    message=natural_text if not ActionParser.has_stop_action(actions) else decision.message,
                    turns=self._turns,
                    total_iterations=self._stop_engine.iteration,
                    total_actions=sum(len(t.tool_executions) for t in self._turns),
                )

    @property
    def turns(self) -> list[AgentTurn]:
        return list(self._turns)

    @property
    def iteration_count(self) -> int:
        return self._stop_engine.iteration
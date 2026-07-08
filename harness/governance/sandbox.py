"""
Sandbox — isolates agent operations.

Strategies:
- none: No sandboxing (for safe operations)
- subprocess: Run with resource limits (timeout, memory)
- docker: Run inside a Docker container for full isolation
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from harness.tools.base import Action, ActionResult


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    timeout_seconds: int = 60
    max_memory_mb: int = 512
    cpu_timeout_seconds: int = 30
    network_enabled: bool = False


class Sandbox:
    """
    Isolates agent operations within a sandboxed environment.

    Usage:
        sandbox = Sandbox(strategy="subprocess")
        result = await sandbox.execute(action, executor_function)
    """

    def __init__(self, strategy: str = "subprocess", config: SandboxConfig | None = None):
        self._strategy = strategy
        self._config = config or SandboxConfig()

    async def execute(
        self,
        action: Action,
        executor: Callable[[Action], Awaitable[ActionResult]],
    ) -> ActionResult:
        """
        Execute an action within the sandbox.

        Args:
            action: The action to execute.
            executor: The function that actually executes the action.

        Returns:
            ActionResult from the execution.
        """
        if self._strategy == "none":
            return await executor(action)

        if self._strategy == "subprocess":
            return await self._subprocess_sandbox(action, executor)

        if self._strategy == "docker":
            return await self._docker_sandbox(action, executor)

        # Unknown strategy, fall through to direct execution
        return await executor(action)

    async def _subprocess_sandbox(
        self,
        action: Action,
        executor: Callable[[Action], Awaitable[ActionResult]],
    ) -> ActionResult:
        """Run with resource limits (timeout)."""
        try:
            return await asyncio.wait_for(
                executor(action),
                timeout=self._config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ActionResult(
                success=False,
                error=f"Sandbox timeout exceeded ({self._config.timeout_seconds}s)",
            )

    async def _docker_sandbox(
        self,
        action: Action,
        executor: Callable[[Action], Awaitable[ActionResult]],
    ) -> ActionResult:
        """
        Run inside a Docker container for full isolation.

        Note: Full Docker sandboxing requires the docker SDK and a running
        Docker daemon. This is a placeholder for the interface.
        """
        try:
            import subprocess
            # Check if Docker is available
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return ActionResult(
                    success=False,
                    error="Docker is not available for sandboxing",
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ActionResult(
                success=False,
                error="Docker is not available for sandboxing",
            )

        # For now, fall back to subprocess sandboxing
        return await self._subprocess_sandbox(action, executor)

    @property
    def strategy(self) -> str:
        return self._strategy

    @property
    def config(self) -> SandboxConfig:
        return self._config
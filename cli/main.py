"""CLI entry point for the Coding Agent Harness."""

import asyncio
import sys
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import click
from harness.config.secrets import SecretsManager


@click.group()
@click.version_option(version="1.0.0")
def main():
    """Coding Agent Harness -- DeepSeek-powered coding agent with natural language interaction."""
    pass


@main.command()
@click.option("--task", "-t", required=True, help="Task for the agent.")
@click.option("--model", "-m", default="deepseek-chat", help="DeepSeek model.")
@click.option("--max-iterations", "-n", default=30, help="Max iterations.")
@click.option("--work-dir", "-d", default=".", help="Working directory.")
def run(task: str, model: str, max_iterations: int, work_dir: str):
    """Run a single task."""
    click.echo(f"Model: {model}  |  Dir: {os.path.abspath(work_dir)}")
    click.echo()
    asyncio.run(_run_agent(task, work_dir, model, max_iterations))


async def _run_agent(
    task: str, work_dir: str, model: str, max_iterations: int,
    session=None, project=None,
):
    from harness.llm.base import LLMAuthenticationError
    from harness.llm.deepseek_client import DeepSeekClient
    from harness.tools.registry import ToolRegistry
    from harness.tools.file_tool import ReadFileTool, WriteFileTool, ListDirectoryTool
    from harness.tools.shell_tool import ShellTool
    from harness.governance.danger_classifier import DangerClassifier
    from harness.governance.policy_engine import PolicyEngine
    from harness.governance.hitl import HITLStateMachine
    from harness.governance.scope_fence import ScopeFence
    from harness.governance.sandbox import Sandbox
    from harness.governance.action_interceptor import ActionInterceptor
    from harness.memory.session_store import SessionStore
    from harness.memory.project_store import ProjectStore
    from harness.core.context_builder import ContextBuilder
    from harness.core.agent import Agent

    try:
        llm = DeepSeekClient(model=model)
    except LLMAuthenticationError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Run: harness setup-key")
        sys.exit(1)

    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListDirectoryTool())
    registry.register(ShellTool(working_dir=work_dir))

    interceptor = ActionInterceptor(
        classifier=DangerClassifier(),
        policy=PolicyEngine.create_default_policy(),
        hitl=HITLStateMachine(timeout_seconds=120),
        fence=ScopeFence(allowed_directories=[os.path.abspath(work_dir)]),
        sandbox=Sandbox(strategy="subprocess"),
    )

    if session is None:
        session = SessionStore()
    if project is None:
        project = ProjectStore(store_path=os.path.join(work_dir, ".harness", "memory"))

    context = ContextBuilder(
        tool_registry=registry,
        session_store=session,
        project_store=project,
    )

    agent = Agent(
        llm=llm,
        tools=registry,
        interceptor=interceptor,
        sandbox=Sandbox(strategy="subprocess"),
        context_builder=context,
        session_store=session,
        project_store=project,
        max_iterations=max_iterations,
        max_consecutive_failures=5,
        on_turn=_on_turn,
    )

    click.echo("=" * 60)
    try:
        result = await agent.run(task)
        _print_result(result)
        return session, project
    except KeyboardInterrupt:
        click.echo("\nInterrupted.")
        return session, project


def _on_turn(turn):
    """Callback: print agent output as it happens."""
    if turn.natural_text:
        click.echo(f"\n{turn.natural_text}")
    for te in turn.tool_executions:
        if te.allowed:
            status = "[OK]" if te.result.success else "[FAIL]"
            click.echo(f"  {status} {te.action.tool_name}: {te.result.output[:200]}")
        else:
            click.echo(f"  [BLOCKED] {te.action.tool_name}: {te.blocked_reason}")


def _print_result(result):
    click.echo("=" * 60)
    click.echo(f"Done | {result.total_iterations} turns | {result.total_actions} actions")
    click.echo(f"Reason: {result.stop_reason.value}")
    click.echo("=" * 60)


@main.command()
@click.option("--task", "-t", default=None, help="Initial task.")
@click.option("--model", "-m", default="deepseek-chat", help="DeepSeek model.")
@click.option("--work-dir", "-d", default=".", help="Working directory.")
def interactive(task: str | None, model: str, work_dir: str):
    """Start interactive session with conversation memory."""
    from harness.memory.session_store import SessionStore
    from harness.memory.project_store import ProjectStore

    click.echo("=" * 60)
    click.echo("Coding Agent Harness")
    click.echo(f"Model: {model}  |  Dir: {os.path.abspath(work_dir)}")
    click.echo("Type 'quit' to exit, 'clear' to reset memory.")
    click.echo("=" * 60)

    session = SessionStore()
    project = ProjectStore(store_path=os.path.join(work_dir, ".harness", "memory"))

    if task:
        click.echo(f"\nYou: {task}\n")
        session, project = asyncio.run(
            _run_agent(task, work_dir, model, 30, session, project)
        )

    while True:
        try:
            user_input = click.prompt("\nYou", type=str).strip()
        except (KeyboardInterrupt, EOFError):
            click.echo("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            click.echo("Goodbye!")
            break
        if user_input.lower() == "clear":
            session = SessionStore()
            click.echo("Memory cleared.")
            continue
        if not user_input:
            continue

        session, project = asyncio.run(
            _run_agent(user_input, work_dir, model, 30, session, project)
        )


@main.command()
@click.option("--port", "-p", default=8000, help="WebUI port.")
def web(port: int):
    """Start the WebUI server."""
    import sys, os
    # Add project root to path so webui.py can be found
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import uvicorn
    from webui import app
    click.echo(f"WebUI starting at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


@main.command()
def demo():
    """Run mechanism demos (no API key needed)."""
    import subprocess
    demo_dir = os.path.join(os.path.dirname(__file__), "..", "demos")
    for d in ["demo_guardrail_intercept.py", "demo_feedback_self_correction.py", "demo_deep_governance.py"]:
        path = os.path.join(demo_dir, d)
        if os.path.exists(path):
            click.echo(f"\n{'='*60}\nRunning: {d}\n{'='*60}")
            subprocess.run([sys.executable, path])


@main.command()
def test():
    """Run all unit tests."""
    import subprocess
    sys.exit(subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"]).returncode)


@main.command()
def setup_key():
    """Securely store DeepSeek API key."""
    secrets = SecretsManager()
    if secrets.has_api_key("deepseek"):
        click.echo(f"Status: {secrets.get_key_status('deepseek')}")
        if not click.confirm("Update existing key?"):
            return
        secrets.delete_api_key("deepseek")
    try:
        key = SecretsManager.prompt_for_key("deepseek")
        secrets.store_api_key(key, "deepseek")
        click.echo(f"Stored. {secrets.get_key_status('deepseek')}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)


@main.command()
def key_status():
    """Check API key status."""
    secrets = SecretsManager()
    click.echo(f"DeepSeek: {secrets.get_key_status('deepseek')}")


@main.command()
def delete_key():
    """Delete stored API key."""
    secrets = SecretsManager()
    if secrets.has_api_key("deepseek") and click.confirm("Delete DeepSeek key?"):
        secrets.delete_api_key("deepseek")
        click.echo("Deleted.")


if __name__ == "__main__":
    main()
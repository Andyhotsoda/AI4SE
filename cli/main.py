"""CLI entry point for the Coding Agent Harness."""

import asyncio
import sys
import os

# Windows: use SelectorEventLoop to avoid ProactorEventLoop subprocess issues
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import click
from harness.config.secrets import SecretsManager


@click.group()
@click.version_option(version="1.0.0")
def main():
    """Coding Agent Harness -- wraps DeepSeek LLM into a reliable, governed coding agent."""
    pass


@main.command()
@click.option("--task", "-t", required=True, help="The task for the agent to perform.")
@click.option("--model", "-m", default="deepseek-chat", help="DeepSeek model name.")
@click.option("--max-iterations", "-n", default=20, help="Maximum iterations.")
@click.option("--work-dir", "-d", default=".", help="Working directory for the agent.")
def run(task: str, model: str, max_iterations: int, work_dir: str):
    """Run the agent on a coding task.

    \b
    Examples:
      harness run -t "Write a Python function that calculates fibonacci numbers"
      harness run -t "Add type hints to all functions in src/" -d ./myproject
    """
    click.echo(f"Model: {model}")
    click.echo(f"Task: {task}")
    click.echo(f"Working directory: {os.path.abspath(work_dir)}")
    click.echo()

    asyncio.run(_run_agent(task, work_dir, model, max_iterations))


async def _run_agent(task: str, work_dir: str, model: str, max_iterations: int):
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
    from harness.feedback.test_runner import SuiteRunner
    from harness.feedback.failure_classifier import FailureClassifier
    from harness.feedback.feedback_injector import FeedbackInjector
    from harness.memory.session_store import SessionStore
    from harness.memory.project_store import ProjectStore
    from harness.core.context_builder import ContextBuilder
    from harness.core.agent import Agent

    # 1. Create DeepSeek LLM client
    try:
        llm = DeepSeekClient(model=model)
    except LLMAuthenticationError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("\nSet up your DeepSeek API key:")
        click.echo("  harness setup-key")
        click.echo("  or set DEEPSEEK_API_KEY environment variable")
        sys.exit(1)

    # 2. Build tools
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListDirectoryTool())
    registry.register(ShellTool(working_dir=work_dir))

    # 3. Build governance
    interceptor = ActionInterceptor(
        classifier=DangerClassifier(),
        policy=PolicyEngine.create_default_policy(),
        hitl=HITLStateMachine(timeout_seconds=120),
        fence=ScopeFence(allowed_directories=[os.path.abspath(work_dir)]),
        sandbox=Sandbox(strategy="subprocess"),
    )

    # 4. Build memory
    session = SessionStore()
    project = ProjectStore(store_path=os.path.join(work_dir, ".harness", "memory"))

    # 5. Build context
    context = ContextBuilder(
        tool_registry=registry,
        session_store=session,
        project_store=project,
    )

    # 6. Build feedback
    test_runner = SuiteRunner(working_dir=work_dir)
    feedback_injector = FeedbackInjector(FailureClassifier())

    # 7. Build agent
    agent = Agent(
        llm=llm,
        tools=registry,
        interceptor=interceptor,
        sandbox=Sandbox(strategy="subprocess"),
        context_builder=context,
        test_runner=test_runner,
        feedback_injector=feedback_injector,
        session_store=session,
        project_store=project,
        max_iterations=max_iterations,
        max_consecutive_failures=5,
    )

    # 8. Run
    click.echo("=" * 60)
    click.echo("Agent starting...")
    click.echo("=" * 60)

    try:
        result = await agent.run(task)

        click.echo()
        click.echo("=" * 60)
        click.echo("AGENT FINISHED")
        click.echo(f"Status: {'SUCCESS' if result.success else 'STOPPED'}")
        click.echo(f"Reason: {result.stop_reason.value}")
        click.echo(f"Iterations: {result.total_iterations}")
        click.echo(f"Total actions: {result.total_actions}")
        if result.message:
            click.echo(f"Message: {result.message}")
        click.echo("=" * 60)

    except KeyboardInterrupt:
        click.echo("\nAgent interrupted by user.")
        sys.exit(0)


@main.command()
@click.option("--task", "-t", default=None, help="Optional initial task.")
@click.option("--model", "-m", default="deepseek-chat", help="DeepSeek model name.")
@click.option("--work-dir", "-d", default=".", help="Working directory for the agent.")
def interactive(task: str | None, model: str, work_dir: str):
    """Start an interactive agent session.

    Type your tasks and the agent will execute them.
    Type 'quit' or 'exit' to end the session.
    """
    click.echo("=" * 60)
    click.echo("Coding Agent Harness - Interactive Mode")
    click.echo(f"Model: {model}")
    click.echo(f"Working directory: {os.path.abspath(work_dir)}")
    click.echo("Type 'quit' or 'exit' to end the session.")
    click.echo("=" * 60)

    if task:
        click.echo(f"\nInitial task: {task}")
        asyncio.run(_run_agent(task, work_dir, model, 20))

    while True:
        try:
            user_input = click.prompt("\nTask", type=str).strip()
        except (KeyboardInterrupt, EOFError):
            click.echo("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            click.echo("Goodbye!")
            break

        if not user_input:
            continue

        asyncio.run(_run_agent(user_input, work_dir, model, 20))


@main.command()
def demo():
    """Run all mechanism demonstrations (no API key needed)."""
    click.echo("Running mechanism demonstrations...")
    import subprocess
    demo_dir = os.path.join(os.path.dirname(__file__), "..", "demos")
    demos = [
        "demo_guardrail_intercept.py",
        "demo_feedback_self_correction.py",
        "demo_deep_governance.py",
    ]
    for d in demos:
        path = os.path.join(demo_dir, d)
        if os.path.exists(path):
            click.echo(f"\n{'='*60}")
            click.echo(f"Running: {d}")
            click.echo(f"{'='*60}")
            subprocess.run([sys.executable, path])


@main.command()
def test():
    """Run all unit tests."""
    click.echo("Running all tests...")
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
    )
    sys.exit(result.returncode)


@main.command()
def setup_key():
    """Securely store your DeepSeek API key in the system keychain."""
    secrets = SecretsManager()
    provider = "deepseek"

    if secrets.has_api_key(provider):
        click.echo(f"Status: {secrets.get_key_status(provider)}")
        if click.confirm("Do you want to update the existing key?"):
            secrets.delete_api_key(provider)
        else:
            return

    try:
        key = SecretsManager.prompt_for_key(provider)
        secrets.store_api_key(key, provider)
        click.echo(f"API key stored securely")
        click.echo(f"Status: {secrets.get_key_status(provider)}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def key_status():
    """Check the status of the stored API key (without revealing it)."""
    secrets = SecretsManager()
    click.echo(f"DeepSeek API Key: {secrets.get_key_status('deepseek')}")
    if not secrets.is_keyring_available():
        click.echo("Warning: System keyring may not be available.")


@main.command()
def delete_key():
    """Delete the stored DeepSeek API key."""
    secrets = SecretsManager()
    if secrets.has_api_key("deepseek"):
        if click.confirm("Delete stored DeepSeek API key?"):
            secrets.delete_api_key("deepseek")
            click.echo("API key deleted.")
    else:
        click.echo("No DeepSeek API key found.")


if __name__ == "__main__":
    main()
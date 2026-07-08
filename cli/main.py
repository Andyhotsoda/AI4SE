"""CLI entry point for the Coding Agent Harness."""

import asyncio
import sys
from pathlib import Path

import click

from harness.config.loader import ConfigLoader
from harness.config.secrets import SecretsManager


@click.group()
@click.version_option(version="1.0.0")
def main():
    """Coding Agent Harness — wraps an LLM into a reliable, governed coding agent."""
    pass


@main.command()
@click.option("--task", "-t", required=True, help="The task for the agent to perform.")
@click.option("--config", "-c", default=None, help="Path to harness config file.")
@click.option("--model", "-m", default=None, help="Anthropic model to use.")
def run(task: str, config: str | None, model: str | None):
    """Run the agent on a task."""
    click.echo(f"Running agent with task: {task}")
    click.echo("(Real LLM integration — requires ANTHROPIC_API_KEY)")
    # Full agent run would go here
    click.echo("Use 'harness demo' to run mechanism demonstrations.")


@main.command()
def demo():
    """Run all mechanism demonstrations."""
    click.echo("Running mechanism demonstrations...")
    import subprocess
    demos = [
        "demos/demo_guardrail_intercept.py",
        "demos/demo_feedback_self_correction.py",
        "demos/demo_deep_governance.py",
    ]
    for demo in demos:
        click.echo(f"\n{'='*60}")
        click.echo(f"Running: {demo}")
        click.echo(f"{'='*60}")
        subprocess.run([sys.executable, demo])


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
@click.option("--provider", "-p", default="anthropic", help="LLM provider.")
def setup_key(provider: str):
    """Securely store an API key in the system keychain."""
    secrets = SecretsManager()

    if secrets.has_api_key(provider):
        click.echo(f"Status: {secrets.get_key_status(provider)}")
        if click.confirm("Do you want to update the existing key?"):
            secrets.delete_api_key(provider)
        else:
            return

    try:
        key = SecretsManager.prompt_for_key(provider)
        secrets.store_api_key(key, provider)
        click.echo(f"✓ API key stored securely for {provider}")
        click.echo(f"Status: {secrets.get_key_status(provider)}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--provider", "-p", default="anthropic", help="LLM provider.")
def key_status(provider: str):
    """Check the status of the stored API key (without revealing it)."""
    secrets = SecretsManager()
    click.echo(f"API Key ({provider}): {secrets.get_key_status(provider)}")
    if not secrets.is_keyring_available():
        click.echo("Warning: System keyring may not be available.")


@main.command()
@click.option("--provider", "-p", default="anthropic", help="LLM provider.")
def delete_key(provider: str):
    """Delete the stored API key."""
    secrets = SecretsManager()
    if secrets.has_api_key(provider):
        if click.confirm(f"Delete stored {provider} API key?"):
            secrets.delete_api_key(provider)
            click.echo("✓ API key deleted.")
    else:
        click.echo(f"No {provider} API key found.")


if __name__ == "__main__":
    main()
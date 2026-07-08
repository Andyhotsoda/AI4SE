"""Pydantic configuration schema for the Coding Agent Harness."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SandboxStrategy(str, Enum):
    """Sandbox isolation strategy."""
    NONE = "none"
    SUBPROCESS = "subprocess"
    DOCKER = "docker"


class GovernanceConfig(BaseModel):
    """Configuration for the governance/guardrail system."""
    enabled: bool = True
    default_verdict: str = Field(
        default="ASK",
        description="Default verdict when no policy rule matches: ALLOW, DENY, ASK, SANDBOX",
    )
    hitl_timeout_seconds: int = Field(
        default=120,
        ge=10,
        le=3600,
        description="Timeout for human-in-the-loop approval requests",
    )
    sandbox_strategy: SandboxStrategy = Field(
        default=SandboxStrategy.SUBPROCESS,
        description="Sandbox isolation strategy",
    )
    policy_file: Optional[str] = Field(
        default=None,
        description="Path to custom safety policy YAML file",
    )
    allowed_directories: list[str] = Field(
        default_factory=lambda: ["."],
        description="Directories the agent is allowed to operate within",
    )
    allowed_commands: list[str] = Field(
        default_factory=list,
        description="Shell commands the agent is allowed to execute (empty = all allowed)",
    )


class ToolsConfig(BaseModel):
    """Configuration for the tool system."""
    shell_timeout_seconds: int = Field(default=30, ge=1, le=600)
    max_file_size_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)  # 10 MB
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [
            ".py", ".txt", ".md", ".yaml", ".yml", ".json",
            ".toml", ".cfg", ".ini", ".gitignore", ".html",
            ".css", ".js", ".ts", ".jsx", ".tsx", ".csv",
        ]
    )


class MemoryConfig(BaseModel):
    """Configuration for the memory system."""
    store_path: str = Field(default=".harness/memory", description="Path to memory storage")
    max_history_turns: int = Field(default=50, ge=1, le=500)
    persist_across_sessions: bool = True


class LLMConfig(BaseModel):
    """Configuration for the LLM provider."""
    provider: str = Field(default="anthropic", description="LLM provider name")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model identifier")
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)


class AgentConfig(BaseModel):
    """Top-level agent configuration."""
    max_iterations: int = Field(default=50, ge=1, le=1000)
    max_consecutive_failures: int = Field(default=5, ge=1, le=50)
    working_directory: str = Field(default=".", description="Agent working directory")
    system_prompt: Optional[str] = Field(default=None, description="Custom system prompt")

    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @field_validator("working_directory")
    @classmethod
    def validate_working_directory(cls, v: str) -> str:
        path = Path(v).resolve()
        if not path.exists():
            raise ValueError(f"Working directory does not exist: {path}")
        return str(path)


class HarnessConfig(BaseModel):
    """Root configuration for the entire harness."""
    agent: AgentConfig = Field(default_factory=AgentConfig)
    version: str = Field(default="1.0.0", description="Config schema version")
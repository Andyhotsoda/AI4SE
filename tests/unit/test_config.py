"""Tests for configuration schema and loader."""

import os
import tempfile

from harness.config.schema import HarnessConfig, AgentConfig, GovernanceConfig, SandboxStrategy
from harness.config.loader import ConfigLoader


class TestConfigSchema:
    """Tests for the Pydantic config schema."""

    def test_default_config_is_valid(self):
        """Default configuration should be valid without any arguments."""
        config = HarnessConfig()
        assert config.agent.max_iterations == 50
        assert config.agent.governance.enabled is True
        assert config.agent.llm.provider == "anthropic"

    def test_agent_config_defaults(self):
        """AgentConfig should have sensible defaults."""
        config = AgentConfig()
        assert config.max_iterations == 50
        assert config.max_consecutive_failures == 5
        assert config.governance.default_verdict == "ASK"
        assert config.llm.model == "claude-sonnet-4-20250514"

    def test_governance_config_defaults(self):
        """GovernanceConfig should have sensible defaults."""
        config = GovernanceConfig()
        assert config.enabled is True
        assert config.hitl_timeout_seconds == 120
        assert config.sandbox_strategy == SandboxStrategy.SUBPROCESS
        assert config.allowed_directories == ["."]

    def test_governance_config_validation(self):
        """GovernanceConfig should validate hitl_timeout bounds."""
        # Valid: within bounds
        valid = GovernanceConfig(hitl_timeout_seconds=60)
        assert valid.hitl_timeout_seconds == 60

    def test_custom_working_directory(self):
        """AgentConfig should resolve relative path to absolute."""
        config = AgentConfig(working_directory=".")
        # "." should be resolved to an absolute path
        assert os.path.isabs(config.working_directory)
        assert config.working_directory != "."

    def test_config_equality(self):
        """Two default configs should be equal."""
        c1 = HarnessConfig()
        c2 = HarnessConfig()
        assert c1 == c2


class TestConfigLoader:
    """Tests for the YAML config loader."""

    def test_load_defaults(self):
        """Loading defaults should return a valid config."""
        config = ConfigLoader.load_defaults()
        assert isinstance(config, HarnessConfig)
        assert config.agent.max_iterations == 50

    def test_load_from_yaml_file(self):
        """Should load config from a YAML file."""
        yaml_content = """
version: "1.0.0"
agent:
  max_iterations: 100
  governance:
    hitl_timeout_seconds: 60
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            config = ConfigLoader.load(f.name)

        assert config.agent.max_iterations == 100
        assert config.agent.governance.hitl_timeout_seconds == 60

        os.unlink(f.name)

    def test_env_var_override(self):
        """Environment variables should override config values."""
        os.environ["HARNESS_MAX_ITERATIONS"] = "25"
        try:
            config = ConfigLoader.load_defaults()
            assert config.agent.max_iterations == 25
        finally:
            del os.environ["HARNESS_MAX_ITERATIONS"]

    def test_env_var_governance_override(self):
        """Environment variable should override governance settings."""
        os.environ["HARNESS_GOVERNANCE_ENABLED"] = "false"
        os.environ["HARNESS_HITL_TIMEOUT"] = "30"
        try:
            config = ConfigLoader.load_defaults()
            assert config.agent.governance.enabled is False
            assert config.agent.governance.hitl_timeout_seconds == 30
        finally:
            del os.environ["HARNESS_GOVERNANCE_ENABLED"]
            del os.environ["HARNESS_HITL_TIMEOUT"]
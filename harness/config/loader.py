"""YAML/JSON configuration loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

from harness.config.schema import HarnessConfig, AgentConfig


class ConfigLoader:
    """Loads and merges configuration from files, env vars, and defaults."""

    DEFAULT_CONFIG_PATHS = [
        "harness.yaml",
        "harness.yml",
        ".harness.yaml",
        ".harness.yml",
        ".harness/config.yaml",
        ".harness/config.yml",
    ]

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> HarnessConfig:
        """
        Load configuration with precedence:
        1. Explicit config_path parameter
        2. Auto-discovery of harness.yaml in project root
        3. Environment variable overrides
        4. Defaults
        """
        config_dict = {}

        # Try to auto-discover config file
        discovered_path = config_path or cls._discover_config()
        if discovered_path:
            config_dict = cls._load_yaml(discovered_path)

        # Apply environment variable overrides
        config_dict = cls._apply_env_overrides(config_dict)

        return HarnessConfig(**config_dict)

    @classmethod
    def load_defaults(cls) -> HarnessConfig:
        """Load default configuration with environment variable overrides applied."""
        config_dict = cls._apply_env_overrides({})
        return HarnessConfig(**config_dict)

    @classmethod
    def _discover_config(cls) -> Optional[str]:
        """Auto-discover harness config file in standard locations."""
        for path in cls.DEFAULT_CONFIG_PATHS:
            if os.path.isfile(path):
                return path
        return None

    @classmethod
    def _load_yaml(cls, path: str) -> dict:
        """Load and parse a YAML configuration file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}

    @classmethod
    def _apply_env_overrides(cls, config: dict) -> dict:
        """Apply environment variable overrides to config dict.

        Each env var maps to a tuple of keys representing the path
        in the config dict, with the last element being a converter function.
        """
        # Map: env_var -> (path, converter)
        env_map = {
            "HARNESS_MAX_ITERATIONS": (("agent", "max_iterations"), int),
            "HARNESS_MAX_FAILURES": (("agent", "max_consecutive_failures"), int),
            "HARNESS_WORK_DIR": (("agent", "working_directory"), str),
            "HARNESS_MODEL": (("agent", "llm", "model"), str),
            "ANTHROPIC_MODEL": (("agent", "llm", "model"), str),
            "HARNESS_HITL_TIMEOUT": (("agent", "governance", "hitl_timeout_seconds"), int),
            "HARNESS_GOVERNANCE_ENABLED": (
                ("agent", "governance", "enabled"),
                lambda v: v.lower() == "true",
            ),
        }

        for env_var, (path, converter) in env_map.items():
            value = os.environ.get(env_var)
            if value is None:
                continue

            # Navigate to the parent dict, creating intermediate dicts as needed
            target = config
            for key in path[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]

            # Set the value
            try:
                target[path[-1]] = converter(value)
            except (ValueError, TypeError):
                pass  # Skip invalid env values

        return config
"""Project store — persistent project-level conventions and knowledge."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


class ProjectStore:
    """
    Key-value store for project conventions and knowledge.

    Persists across sessions to a JSON file, enabling the agent
    to remember project conventions, past decisions, and patterns.
    """

    def __init__(self, store_path: str = ".harness/memory"):
        self._store_path = Path(store_path)
        self._data: dict[str, Any] = {}
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value and persist to disk."""
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def get_all(self) -> dict[str, Any]:
        """Get all stored key-value pairs."""
        return dict(self._data)

    def get_conventions(self) -> dict[str, str]:
        """Get all project conventions as a dict for LLM context."""
        conventions = {}
        for key, value in self._data.items():
            if key.startswith("convention:"):
                conventions[key.removeprefix("convention:")] = str(value)
        return conventions

    def set_convention(self, name: str, value: str) -> None:
        """Set a project convention."""
        self.set(f"convention:{name}", value)

    def get_for_context(self) -> str:
        """
        Format project memory for inclusion in the LLM system prompt.

        Returns:
            A formatted string of project conventions and knowledge.
        """
        parts = []
        conventions = self.get_conventions()
        if conventions:
            parts.append("## Project Conventions")
            for name, value in conventions.items():
                parts.append(f"- **{name}**: {value}")

        # Include non-convention data
        other = {k: v for k, v in self._data.items() if not k.startswith("convention:")}
        if other:
            parts.append("\n## Project Knowledge")
            for key, value in other.items():
                parts.append(f"- **{key}**: {value}")

        return "\n".join(parts) if parts else ""

    def clear(self) -> None:
        """Clear all stored data."""
        self._data.clear()
        self._save()

    def _load(self) -> None:
        """Load data from disk."""
        data_file = self._store_path / "project.json"
        if data_file.exists():
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}

    def _save(self) -> None:
        """Save data to disk."""
        self._store_path.mkdir(parents=True, exist_ok=True)
        data_file = self._store_path / "project.json"
        try:
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, default=str)
        except IOError:
            pass  # Fail silently — memory is non-critical

    @property
    def store_path(self) -> str:
        return str(self._store_path)
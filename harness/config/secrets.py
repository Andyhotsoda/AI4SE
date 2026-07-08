"""Secure credential storage using the system keyring.

Uses the `keyring` library for cross-platform operating system keychain access:
- Windows: Credential Manager
- macOS: Keychain
- Linux: Secret Service / KWallet

When the keyring backend is unavailable (e.g., in Docker containers),
falls back to environment variables and .env file only.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Lazy import keyring — it may fail in headless/Docker environments
# where no keyring backend is available (no dbus, no secret service).
_keyring = None
_keyring_error = None

try:
    import keyring as _keyring_module
    # Test that a backend is actually available
    _keyring_module.get_keyring()
    _keyring = _keyring_module
except Exception as e:
    _keyring_error = str(e)

SERVICE_NAME = "coding-agent-harness"
API_KEY_ENTRY = "anthropic-api-key"


class SecretsManager:
    """Manages secure storage of API keys and other credentials.

    When the system keyring backend is available, keys are stored securely
    in the OS keychain. When unavailable (e.g., Docker containers), the
    manager falls back to environment variables only — no persistent storage
    is attempted.
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        self._service = service_name
        self._keyring_available = _keyring is not None

    def store_api_key(self, key: str, provider: str = "deepseek") -> None:
        """
        Store an API key securely in the system keychain.

        Args:
            key: The API key to store.
            provider: The LLM provider name (default: deepseek).

        Raises:
            RuntimeError: If the keyring backend is not available.
        """
        if not self._keyring_available:
            raise RuntimeError(
                "System keyring is not available in this environment. "
                "Use environment variables instead:\n"
                f"  export {provider.upper()}_API_KEY=your-key\n"
                "Or pass the key explicitly via the --api-key CLI option."
            )
        entry_name = f"{provider}-api-key"
        _keyring.set_password(self._service, entry_name, key)

    def retrieve_api_key(self, provider: str = "deepseek") -> Optional[str]:
        """
        Retrieve an API key from the system keychain.

        Args:
            provider: The LLM provider name.

        Returns:
            The stored API key, or None if not found or keyring unavailable.
        """
        if not self._keyring_available:
            return None
        entry_name = f"{provider}-api-key"
        try:
            return _keyring.get_password(self._service, entry_name)
        except Exception:
            return None

    def delete_api_key(self, provider: str = "deepseek") -> bool:
        """
        Delete an API key from the system keychain.

        Args:
            provider: The LLM provider name.

        Returns:
            True if the key was deleted, False if it didn't exist or keyring unavailable.
        """
        if not self._keyring_available:
            return False
        entry_name = f"{provider}-api-key"
        try:
            _keyring.delete_password(self._service, entry_name)
            return True
        except Exception:
            return False

    def has_api_key(self, provider: str = "deepseek") -> bool:
        """
        Check if an API key is stored.

        Args:
            provider: The LLM provider name.

        Returns:
            True if a key exists in the keyring.
        """
        return self.retrieve_api_key(provider) is not None

    def get_key_status(self, provider: str = "deepseek") -> str:
        """
        Get a human-readable status of the stored key (without revealing it).

        Returns:
            A status string like 'stored (sk-ant-...xyz)' or 'not stored'.
        """
        if not self._keyring_available:
            return "keyring unavailable — use environment variables"

        key = self.retrieve_api_key(provider)
        if key is None:
            return "not stored"
        if len(key) <= 8:
            return "stored (too short — possibly invalid)"
        return f"stored ({key[:8]}...{key[-4:]})"

    def store_credential(self, name: str, value: str) -> None:
        """Store an arbitrary credential."""
        if not self._keyring_available:
            raise RuntimeError("System keyring is not available.")
        _keyring.set_password(self._service, name, value)

    def retrieve_credential(self, name: str) -> Optional[str]:
        """Retrieve an arbitrary credential."""
        if not self._keyring_available:
            return None
        try:
            return _keyring.get_password(self._service, name)
        except Exception:
            return None

    def delete_credential(self, name: str) -> bool:
        """Delete an arbitrary credential."""
        if not self._keyring_available:
            return False
        try:
            _keyring.delete_password(self._service, name)
            return True
        except Exception:
            return False

    @staticmethod
    def prompt_for_key(provider: str = "deepseek") -> str:
        """
        Prompt the user to enter an API key securely (hidden input).

        Uses getpass for hidden input.
        """
        import getpass

        print(f"\nEnter your {provider.upper()} API key (input will be hidden):")
        key = getpass.getpass("> ").strip()
        if not key:
            raise ValueError("API key cannot be empty")
        return key

    @staticmethod
    def is_keyring_available() -> bool:
        """Check if the system keyring backend is available."""
        return _keyring is not None

    @staticmethod
    def get_keyring_error() -> Optional[str]:
        """Get the error message if keyring is unavailable."""
        return _keyring_error

    def get_available_backend_info(self) -> str:
        """Get info about the keyring backend being used."""
        if not self._keyring_available:
            return f"unavailable: {_keyring_error or 'unknown reason'}"
        try:
            backend = _keyring.get_keyring()
            return f"{backend.__class__.__module__}.{backend.__class__.__name__}"
        except Exception:
            return "unknown / unavailable"
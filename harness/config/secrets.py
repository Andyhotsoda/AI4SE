"""Secure credential storage using the system keyring.

Uses the `keyring` library for cross-platform operating system keychain access:
- Windows: Credential Manager
- macOS: Keychain
- Linux: Secret Service / KWallet
"""

from __future__ import annotations

import sys
from typing import Optional

import keyring

SERVICE_NAME = "coding-agent-harness"
API_KEY_ENTRY = "anthropic-api-key"


class SecretsManager:
    """Manages secure storage of API keys and other credentials."""

    def __init__(self, service_name: str = SERVICE_NAME):
        self._service = service_name

    def store_api_key(self, key: str, provider: str = "anthropic") -> None:
        """
        Store an API key securely in the system keychain.

        Args:
            key: The API key to store.
            provider: The LLM provider name (default: anthropic).
        """
        entry_name = f"{provider}-api-key"
        keyring.set_password(self._service, entry_name, key)

    def retrieve_api_key(self, provider: str = "anthropic") -> Optional[str]:
        """
        Retrieve an API key from the system keychain.

        Args:
            provider: The LLM provider name.

        Returns:
            The stored API key, or None if not found.
        """
        entry_name = f"{provider}-api-key"
        return keyring.get_password(self._service, entry_name)

    def delete_api_key(self, provider: str = "anthropic") -> bool:
        """
        Delete an API key from the system keychain.

        Args:
            provider: The LLM provider name.

        Returns:
            True if the key was deleted, False if it didn't exist.
        """
        entry_name = f"{provider}-api-key"
        try:
            keyring.delete_password(self._service, entry_name)
            return True
        except keyring.errors.PasswordDeleteError:
            return False

    def has_api_key(self, provider: str = "anthropic") -> bool:
        """
        Check if an API key is stored.

        Args:
            provider: The LLM provider name.

        Returns:
            True if a key exists.
        """
        return self.retrieve_api_key(provider) is not None

    def get_key_status(self, provider: str = "anthropic") -> str:
        """
        Get a human-readable status of the stored key (without revealing it).

        Returns:
            A status string like 'stored (sk-ant-...xyz)' or 'not stored'.
        """
        key = self.retrieve_api_key(provider)
        if key is None:
            return "not stored"
        if len(key) <= 8:
            return "stored (too short — possibly invalid)"
        return f"stored ({key[:8]}...{key[-4:]})"

    def store_credential(self, name: str, value: str) -> None:
        """Store an arbitrary credential."""
        keyring.set_password(self._service, name, value)

    def retrieve_credential(self, name: str) -> Optional[str]:
        """Retrieve an arbitrary credential."""
        return keyring.get_password(self._service, name)

    def delete_credential(self, name: str) -> bool:
        """Delete an arbitrary credential."""
        try:
            keyring.delete_password(self._service, name)
            return True
        except keyring.errors.PasswordDeleteError:
            return False

    @staticmethod
    def prompt_for_key(provider: str = "anthropic") -> str:
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
        try:
            # Try to get the current backend
            backend = keyring.get_keyring()
            return backend is not None
        except Exception:
            return False

    def get_available_backend_info(self) -> str:
        """Get info about the keyring backend being used."""
        try:
            backend = keyring.get_keyring()
            return f"{backend.__class__.__module__}.{backend.__class__.__name__}"
        except Exception:
            return "unknown / unavailable"
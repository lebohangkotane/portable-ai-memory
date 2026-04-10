"""Abstract base class for platform import adapters.

Each adapter converts a platform-specific export format into PAM's universal schema.
To add a new platform, implement this interface in a new file (e.g., gemini.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from pam.vault.models import Conversation


class PlatformAdapter(ABC):
    """Base class for all platform import adapters."""

    # Subclasses must set these
    platform_name: str  # e.g. "chatgpt", "claude", "gemini"
    supported_formats: list[str]  # e.g. [".zip", ".json"]
    description: str  # Human-readable description

    @abstractmethod
    def detect(self, path: Path) -> bool:
        """Return True if this adapter can handle the given file.

        Should check file extension, magic bytes, or internal structure
        to determine if this is a valid export from the platform.
        """
        ...

    @abstractmethod
    def parse(self, path: Path) -> Iterator[Conversation]:
        """Yield normalized conversations from the export file.

        Each conversation should be fully populated with messages,
        timestamps, and platform-specific metadata normalized into
        the universal schema.
        """
        ...

    @abstractmethod
    def get_platform_metadata(self, path: Path) -> dict:
        """Extract platform-specific metadata from the export.

        Returns info like: account name, export date range,
        total conversation count, platform version, etc.
        """
        ...

    def validate(self, path: Path) -> list[str]:
        """Validate an export file and return a list of warnings/errors.

        Default implementation checks file existence and extension.
        Override for deeper validation.
        """
        issues: list[str] = []
        if not path.exists():
            issues.append(f"File not found: {path}")
            return issues
        if path.suffix not in self.supported_formats:
            issues.append(
                f"Unexpected format '{path.suffix}'. "
                f"Expected one of: {', '.join(self.supported_formats)}"
            )
        return issues


# Registry of available adapters
_ADAPTER_REGISTRY: dict[str, type[PlatformAdapter]] = {}


def register_adapter(adapter_cls: type[PlatformAdapter]) -> type[PlatformAdapter]:
    """Decorator to register a platform adapter."""
    _ADAPTER_REGISTRY[adapter_cls.platform_name] = adapter_cls
    return adapter_cls


def get_adapter(platform: str) -> PlatformAdapter:
    """Get an adapter instance by platform name."""
    if platform not in _ADAPTER_REGISTRY:
        available = ", ".join(sorted(_ADAPTER_REGISTRY.keys()))
        raise ValueError(
            f"No adapter for platform '{platform}'. Available: {available}"
        )
    return _ADAPTER_REGISTRY[platform]()


def list_adapters() -> dict[str, type[PlatformAdapter]]:
    """Return all registered adapters."""
    return dict(_ADAPTER_REGISTRY)


def auto_detect_adapter(path: Path) -> PlatformAdapter | None:
    """Try all registered adapters and return the first one that detects the file."""
    for adapter_cls in _ADAPTER_REGISTRY.values():
        adapter = adapter_cls()
        if adapter.detect(path):
            return adapter
    return None

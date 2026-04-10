"""Tests for privacy filtering."""

from pam.context.privacy import PrivacyConfig, PlatformRule
from pam.vault.models import (
    AccessControl,
    Memory,
    MemoryType,
    Platform,
    Provenance,
    Sensitivity,
)


def _make_memory(
    mem_type: MemoryType = MemoryType.FACT,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    share_with: list[str] | None = None,
    deny_to: list[str] | None = None,
) -> Memory:
    return Memory(
        type=mem_type,
        content="Test memory",
        provenance=Provenance(platform=Platform.CHATGPT),
        access_control=AccessControl(
            sensitivity=sensitivity,
            share_with=share_with or [],
            deny_to=deny_to or [],
        ),
    )


def test_default_deny_blocks_all():
    config = PrivacyConfig(default_policy="deny", rules=[])
    memories = [_make_memory()]
    filtered = config.filter_memories(memories, "unknown_platform")
    assert len(filtered) == 0


def test_platform_rule_allows():
    config = PrivacyConfig(
        default_policy="deny",
        rules=[
            PlatformRule(
                platform="claude",
                allowed_types=["fact", "skill"],
                max_sensitivity=Sensitivity.PRIVATE,
            ),
        ],
    )
    memories = [
        _make_memory(MemoryType.FACT),
        _make_memory(MemoryType.SKILL),
        _make_memory(MemoryType.EPISODE),  # Not allowed
    ]
    filtered = config.filter_memories(memories, "claude")
    assert len(filtered) == 2
    assert all(m.type in (MemoryType.FACT, MemoryType.SKILL) for m in filtered)


def test_sensitivity_filtering():
    config = PrivacyConfig(
        default_policy="deny",
        rules=[
            PlatformRule(
                platform="chatgpt",
                allowed_types=["fact"],
                max_sensitivity=Sensitivity.PUBLIC,
            ),
        ],
    )
    memories = [
        _make_memory(MemoryType.FACT, Sensitivity.PUBLIC),
        _make_memory(MemoryType.FACT, Sensitivity.PRIVATE),  # Blocked
        _make_memory(MemoryType.FACT, Sensitivity.SENSITIVE),  # Blocked
    ]
    filtered = config.filter_memories(memories, "chatgpt")
    assert len(filtered) == 1


def test_memory_level_deny():
    config = PrivacyConfig(
        default_policy="deny",
        rules=[
            PlatformRule(
                platform="claude",
                allowed_types=["fact"],
                max_sensitivity=Sensitivity.PRIVATE,
            ),
        ],
    )
    memories = [
        _make_memory(MemoryType.FACT, deny_to=["claude"]),
    ]
    filtered = config.filter_memories(memories, "claude")
    assert len(filtered) == 0


def test_wildcard_rule():
    config = PrivacyConfig(
        default_policy="deny",
        rules=[
            PlatformRule(
                platform="*",
                allowed_types=["preference"],
                max_sensitivity=Sensitivity.PUBLIC,
            ),
        ],
    )
    memories = [_make_memory(MemoryType.PREFERENCE)]
    filtered = config.filter_memories(memories, "some_new_platform")
    assert len(filtered) == 1


def test_default_config():
    config = PrivacyConfig.default()
    assert len(config.rules) > 0
    # Claude should have access to facts
    rule = config.get_rule("claude")
    assert rule is not None
    assert "fact" in rule.allowed_types

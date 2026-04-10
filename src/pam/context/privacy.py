"""Privacy and access control for memory sharing.

Implements the per-platform filtering model:
  Default: DENY ALL — nothing shared unless explicitly allowed.
  Users configure rules per platform specifying which memory types and
  sensitivity levels each AI platform can access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pam.vault.models import Memory, MemoryType, Sensitivity


@dataclass
class PlatformRule:
    """Access rule for a specific platform."""

    platform: str
    allowed_types: list[str] = field(default_factory=list)
    denied_types: list[str] = field(default_factory=list)
    max_sensitivity: Sensitivity = Sensitivity.PUBLIC


@dataclass
class PrivacyConfig:
    """Privacy configuration for the vault."""

    default_policy: str = "deny"  # "deny" or "allow"
    rules: list[PlatformRule] = field(default_factory=list)

    def get_rule(self, platform: str) -> PlatformRule | None:
        """Get the rule for a specific platform."""
        for rule in self.rules:
            if rule.platform == platform:
                return rule
        # Check for wildcard
        for rule in self.rules:
            if rule.platform == "*":
                return rule
        return None

    def filter_memories(
        self, memories: list[Memory], target_platform: str
    ) -> list[Memory]:
        """Filter memories based on access rules for a target platform."""
        rule = self.get_rule(target_platform)

        if rule is None:
            if self.default_policy == "deny":
                return []
            return memories

        sensitivity_order = {
            Sensitivity.PUBLIC: 0,
            Sensitivity.PRIVATE: 1,
            Sensitivity.SENSITIVE: 2,
        }
        max_level = sensitivity_order.get(rule.max_sensitivity, 0)

        filtered = []
        for mem in memories:
            # Check sensitivity level
            mem_level = sensitivity_order.get(mem.access_control.sensitivity, 2)
            if mem_level > max_level:
                continue

            # Check type-based rules
            mem_type = mem.type.value
            if rule.denied_types and mem_type in rule.denied_types:
                continue
            if rule.allowed_types and mem_type not in rule.allowed_types:
                continue

            # Check memory-level access control
            if mem.access_control.deny_to and target_platform in mem.access_control.deny_to:
                continue
            if mem.access_control.share_with and target_platform not in mem.access_control.share_with:
                # If share_with is set, only those platforms get access
                continue

            filtered.append(mem)

        return filtered

    def to_dict(self) -> dict:
        return {
            "default_policy": self.default_policy,
            "rules": [
                {
                    "platform": r.platform,
                    "allowed_types": r.allowed_types,
                    "denied_types": r.denied_types,
                    "max_sensitivity": r.max_sensitivity.value,
                }
                for r in self.rules
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PrivacyConfig:
        rules = []
        for r in data.get("rules", []):
            rules.append(
                PlatformRule(
                    platform=r["platform"],
                    allowed_types=r.get("allowed_types", []),
                    denied_types=r.get("denied_types", []),
                    max_sensitivity=Sensitivity(r.get("max_sensitivity", "public")),
                )
            )
        return cls(
            default_policy=data.get("default_policy", "deny"),
            rules=rules,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> PrivacyConfig:
        if not path.exists():
            return cls.default()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def default(cls) -> PrivacyConfig:
        """Create default privacy config — permissive for getting started."""
        return cls(
            default_policy="deny",
            rules=[
                PlatformRule(
                    platform="claude",
                    allowed_types=["fact", "preference", "skill", "identity", "goal"],
                    max_sensitivity=Sensitivity.PRIVATE,
                ),
                PlatformRule(
                    platform="chatgpt",
                    allowed_types=["fact", "preference", "skill", "identity", "goal"],
                    max_sensitivity=Sensitivity.PRIVATE,
                ),
                PlatformRule(
                    platform="gemini",
                    allowed_types=["fact", "preference", "skill", "identity", "goal"],
                    max_sensitivity=Sensitivity.PRIVATE,
                ),
                PlatformRule(
                    platform="*",
                    allowed_types=["preference", "skill"],
                    max_sensitivity=Sensitivity.PUBLIC,
                ),
            ],
        )

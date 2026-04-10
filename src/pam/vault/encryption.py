"""Vault encryption utilities.

Provides AES-256-GCM encryption for the vault passphrase and key derivation.
For SQLite encryption, we use sqlcipher via the database module.
This module handles the key derivation and optional keyfile management.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from base64 import b64decode, b64encode
from pathlib import Path

# PBKDF2 parameters
PBKDF2_ITERATIONS = 600_000
SALT_LENGTH = 32
KEY_LENGTH = 32  # 256 bits


def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from a passphrase using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=KEY_LENGTH,
    )


def generate_salt() -> bytes:
    """Generate a cryptographically secure random salt."""
    return os.urandom(SALT_LENGTH)


def generate_vault_key() -> str:
    """Generate a random vault encryption key (hex-encoded, for sqlcipher PRAGMA key)."""
    return secrets.token_hex(KEY_LENGTH)


def save_keyfile(key: str, path: Path) -> None:
    """Save a vault key to a keyfile (base64-encoded)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = b64encode(key.encode("utf-8")).decode("ascii")
    path.write_text(encoded, encoding="utf-8")
    # Restrict permissions on Unix-like systems
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows doesn't support Unix permissions


def load_keyfile(path: Path) -> str:
    """Load a vault key from a keyfile."""
    encoded = path.read_text(encoding="utf-8").strip()
    return b64decode(encoded).decode("utf-8")


def verify_passphrase(passphrase: str, salt: bytes, expected_hash: bytes) -> bool:
    """Verify a passphrase against a stored hash."""
    derived = derive_key(passphrase, salt)
    return hmac.compare_digest(derived, expected_hash)

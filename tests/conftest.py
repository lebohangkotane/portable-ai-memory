"""Shared test fixtures for PAM tests."""

import tempfile
from pathlib import Path

import pytest

from pam.vault.database import VaultDB


@pytest.fixture
def tmp_vault():
    """Create a temporary vault database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_vault.db"
        with VaultDB(path) as db:
            yield db


@pytest.fixture
def tmp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

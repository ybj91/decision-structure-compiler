"""Shared test fixtures."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dsc.storage.filesystem import FileSystemStorage


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Provide a temporary data directory."""
    return tmp_path / "dsc_data"


@pytest.fixture
def storage(tmp_data_dir: Path) -> FileSystemStorage:
    """Provide a FileSystemStorage backed by a temp directory."""
    return FileSystemStorage(tmp_data_dir)

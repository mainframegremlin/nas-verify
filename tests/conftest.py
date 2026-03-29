import pytest
from pathlib import Path
import tempfile
import os


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def sample_files(tmp_path: Path) -> Path:
    """Create a small tree of files for testing."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file1.txt").write_text("hello world")
    (tmp_path / "file2.txt").write_text("foo bar baz")
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")
    (tmp_path / "@eaDir").mkdir()
    (tmp_path / "@eaDir" / "thumb.jpg").write_bytes(b"\xff\xd8\xff")
    return tmp_path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"

import hashlib
from pathlib import Path

from nas_verify.scanner import compute_sha256, should_exclude, iter_files, build_file_record


def test_compute_sha256_matches_hashlib(tmp_path: Path) -> None:
    f = tmp_path / "test.bin"
    data = b"the quick brown fox" * 1000
    f.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert compute_sha256(f) == expected


def test_compute_sha256_small_chunk(tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    data = b"chunk test data"
    f.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert compute_sha256(f, chunk_size=4) == expected


def test_should_exclude_eadir(tmp_path: Path) -> None:
    patterns = ["**/@eaDir/**"]
    p = tmp_path / "@eaDir" / "thumb.jpg"
    assert should_exclude(p, tmp_path, patterns)


def test_should_exclude_simple_name(tmp_path: Path) -> None:
    patterns = ["Thumbs.db"]
    p = tmp_path / "subdir" / "Thumbs.db"
    assert should_exclude(p, tmp_path, patterns)


def test_should_not_exclude_normal_file(tmp_path: Path) -> None:
    patterns = ["**/@eaDir/**", "Thumbs.db"]
    p = tmp_path / "important.txt"
    assert not should_exclude(p, tmp_path, patterns)


def test_iter_files_yields_files(sample_files: Path) -> None:
    files = list(iter_files(sample_files, []))
    names = {f.name for f in files}
    assert "file1.txt" in names
    assert "file2.txt" in names
    assert "nested.txt" in names


def test_iter_files_excludes_eadir(sample_files: Path) -> None:
    files = list(iter_files(sample_files, ["**/@eaDir/**"]))
    names = {f.name for f in files}
    assert "thumb.jpg" not in names


def test_build_file_record(sample_files: Path) -> None:
    f = sample_files / "file1.txt"
    record = build_file_record(f, "2024-01-01T00:00:00+00:00", 1024 * 1024)
    assert record.file_path == f.as_posix()  # absolute path
    assert record.file_size == len("hello world")
    assert len(record.checksum) == 64  # SHA-256 hex
    assert record.scan_time == "2024-01-01T00:00:00+00:00"

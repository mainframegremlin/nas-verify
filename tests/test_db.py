from pathlib import Path

import pytest

from nas_verify.db import Database, FileRecord


@pytest.fixture
def db(db_path: Path) -> Database:
    d = Database(db_path)
    d.init_schema()
    return d


def test_begin_scan_returns_id(db: Database) -> None:
    with db:
        scan_id = db.begin_scan("/mnt/nas")
        assert isinstance(scan_id, int)
        assert scan_id > 0


def test_upsert_and_get_baseline(db: Database) -> None:
    with db:
        scan_id = db.begin_scan("/mnt/nas")
        record = FileRecord(
            file_path="docs/file.txt",
            file_size=100,
            mtime=1700000000.0,
            checksum="abc123" * 10 + "ab",
            scan_time="2024-01-01T00:00:00+00:00",
        )
        db.upsert_file(scan_id, record)
        db.flush()

        baseline = db.get_baseline()
        assert "docs/file.txt" in baseline
        got = baseline["docs/file.txt"]
        assert got.checksum == record.checksum
        assert got.file_size == 100


def test_baseline_upsert_updates_existing(db: Database) -> None:
    with db:
        scan_id = db.begin_scan("/mnt/nas")
        r1 = FileRecord("a.txt", 10, 1000.0, "a" * 64, "2024-01-01T00:00:00+00:00")
        db.upsert_file(scan_id, r1)
        db.flush()

        scan_id2 = db.begin_scan("/mnt/nas")
        r2 = FileRecord("a.txt", 20, 2000.0, "b" * 64, "2024-01-02T00:00:00+00:00")
        db.upsert_file(scan_id2, r2)
        db.flush()

        baseline = db.get_baseline()
        assert baseline["a.txt"].checksum == "b" * 64
        assert baseline["a.txt"].file_size == 20


def test_finalize_scan_updates_counts(db: Database) -> None:
    with db:
        scan_id = db.begin_scan("/mnt/nas")
        db.finalize_scan(scan_id, total_files=42, total_bytes=1024)
        summary = db.get_scan_summary(scan_id)
        assert summary["total_files"] == 42
        assert summary["total_bytes"] == 1024


def test_iter_baseline(db: Database) -> None:
    with db:
        scan_id = db.begin_scan("/mnt/nas")
        for i in range(5):
            db.upsert_file(scan_id, FileRecord(
                f"file{i}.txt", i * 10, float(i), "c" * 64, "2024-01-01T00:00:00+00:00"
            ))
        db.flush()

        records = list(db.iter_baseline())
        assert len(records) == 5

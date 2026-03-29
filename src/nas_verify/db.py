from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


@dataclass
class FileRecord:
    file_path: str
    file_size: int
    mtime: float
    checksum: str
    scan_time: str
    scan_id: Optional[int] = None
    id: Optional[int] = None


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS scans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_time   TEXT    NOT NULL,
                root_path   TEXT    NOT NULL,
                total_files INTEGER NOT NULL DEFAULT 0,
                total_bytes INTEGER NOT NULL DEFAULT 0,
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS file_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id     INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                file_path   TEXT    NOT NULL,
                file_size   INTEGER NOT NULL,
                mtime       REAL    NOT NULL,
                checksum    TEXT    NOT NULL,
                scan_time   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS baseline (
                file_path   TEXT    PRIMARY KEY,
                file_size   INTEGER NOT NULL,
                mtime       REAL    NOT NULL,
                checksum    TEXT    NOT NULL,
                scan_id     INTEGER NOT NULL REFERENCES scans(id),
                updated_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_file_records_path
                ON file_records(file_path);

            CREATE INDEX IF NOT EXISTS idx_file_records_scan_id
                ON file_records(scan_id);

            CREATE INDEX IF NOT EXISTS idx_file_records_scan_path
                ON file_records(scan_id, file_path);
        """)
        self._conn.commit()

    def begin_scan(self, root_path: str, notes: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO scans (scan_time, root_path, notes) VALUES (?, ?, ?)",
            (_now_utc(), root_path, notes or None),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def finalize_scan(self, scan_id: int, total_files: int, total_bytes: int) -> None:
        self._conn.execute(
            "UPDATE scans SET total_files=?, total_bytes=? WHERE id=?",
            (total_files, total_bytes, scan_id),
        )
        self._conn.commit()

    def upsert_file(self, scan_id: int, record: FileRecord) -> None:
        now = _now_utc()
        self._conn.execute(
            """INSERT INTO file_records
               (scan_id, file_path, file_size, mtime, checksum, scan_time)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (scan_id, record.file_path, record.file_size,
             record.mtime, record.checksum, record.scan_time),
        )
        self._conn.execute(
            """INSERT INTO baseline (file_path, file_size, mtime, checksum, scan_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(file_path) DO UPDATE SET
                   file_size  = excluded.file_size,
                   mtime      = excluded.mtime,
                   checksum   = excluded.checksum,
                   scan_id    = excluded.scan_id,
                   updated_at = excluded.updated_at""",
            (record.file_path, record.file_size, record.mtime,
             record.checksum, scan_id, now),
        )

    def get_baseline(self) -> dict[str, FileRecord]:
        cur = self._conn.execute(
            "SELECT file_path, file_size, mtime, checksum, scan_id FROM baseline"
        )
        result: dict[str, FileRecord] = {}
        for row in cur:
            result[row["file_path"]] = FileRecord(
                file_path=row["file_path"],
                file_size=row["file_size"],
                mtime=row["mtime"],
                checksum=row["checksum"],
                scan_time="",
                scan_id=row["scan_id"],
            )
        return result

    def iter_baseline(self) -> Iterator[FileRecord]:
        cur = self._conn.execute(
            "SELECT file_path, file_size, mtime, checksum, scan_id FROM baseline"
        )
        for row in cur:
            yield FileRecord(
                file_path=row["file_path"],
                file_size=row["file_size"],
                mtime=row["mtime"],
                checksum=row["checksum"],
                scan_time="",
                scan_id=row["scan_id"],
            )

    def get_scan_summary(self, scan_id: int) -> dict[str, object]:
        cur = self._conn.execute("SELECT * FROM scans WHERE id=?", (scan_id,))
        row = cur.fetchone()
        if row is None:
            return {}
        return dict(row)

    def clear_baseline(self) -> None:
        """Remove all baseline entries (used before a full rebuild scan)."""
        self._conn.execute("DELETE FROM baseline")
        self._conn.commit()

    def flush(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

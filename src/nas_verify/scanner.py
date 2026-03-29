from __future__ import annotations

import fnmatch
import hashlib
import os
from collections.abc import Callable, Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import AppConfig
from .db import Database, FileRecord


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    buf = bytearray(chunk_size)
    view = memoryview(buf)
    with open(file_path, "rb") as fh:
        while True:
            n = fh.readinto(view)
            if not n:
                break
            h.update(view[:n])
    return h.hexdigest()


def should_exclude(path: Path, root: Path, patterns: list[str]) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
        # Strip leading "**/" so patterns like "**/@eaDir/**" also match at root level
        stripped = pattern.lstrip("*").lstrip("/")
        if stripped and stripped != pattern and fnmatch.fnmatch(rel, stripped):
            return True
        # Also match against just the filename for simple patterns like "Thumbs.db"
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def iter_files(
    root: Path,
    exclude_patterns: list[str],
) -> Generator[Path, None, None]:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dir_path = Path(dirpath)

        # Prune excluded directories in-place to avoid descending into them
        dirnames[:] = [
            d for d in dirnames
            if not should_exclude(dir_path / d, root, exclude_patterns)
        ]

        for filename in filenames:
            file_path = dir_path / filename
            if file_path.is_symlink():
                continue
            if should_exclude(file_path, root, exclude_patterns):
                continue
            yield file_path


def build_file_record(
    file_path: Path,
    scan_time: str,
    chunk_size: int,
) -> FileRecord:
    stat = file_path.stat()
    checksum = compute_sha256(file_path, chunk_size)
    return FileRecord(
        file_path=file_path.as_posix(),  # absolute path — unambiguous across multiple mounts
        file_size=stat.st_size,
        mtime=stat.st_mtime,
        checksum=checksum,
        scan_time=scan_time,
    )


def run_scan(
    config: AppConfig,
    db: Database,
    scan_id: int,
    progress_callback: Optional[Callable[[Path, int], None]] = None,
) -> tuple[int, int]:
    scan_time = datetime.now(timezone.utc).isoformat()
    total_files = 0
    total_bytes = 0

    for mount_path in config.mount_paths:
        for file_path in iter_files(mount_path, config.exclude_patterns):
            try:
                record = build_file_record(file_path, scan_time, config.chunk_size)
            except OSError:
                # File disappeared or is unreadable — skip silently
                continue

            db.upsert_file(scan_id, record)
            total_files += 1
            total_bytes += record.file_size

            if progress_callback is not None:
                progress_callback(file_path, record.file_size)

            # Commit in batches to avoid holding a huge transaction
            if total_files % 500 == 0:
                db.flush()

    db.flush()
    return total_files, total_bytes

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from .db import FileRecord

ChangeType = Literal["new", "missing", "changed", "corrupted"]


@dataclass
class FileDiff:
    change_type: ChangeType
    file_path: str
    old_checksum: Optional[str]
    new_checksum: Optional[str]
    old_size: Optional[int]
    new_size: Optional[int]


@dataclass
class VerifyReport:
    scan_id: int
    verify_time: str
    root_path: str
    total_checked: int
    diffs: list[FileDiff]

    @property
    def has_failures(self) -> bool:
        return len(self.diffs) > 0

    @property
    def summary_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"new": 0, "missing": 0, "changed": 0, "corrupted": 0}
        for diff in self.diffs:
            counts[diff.change_type] += 1
        return counts


def build_verify_report(
    scan_id: int,
    root_path: str,
    current_files: dict[str, FileRecord],
    baseline: dict[str, FileRecord],
) -> VerifyReport:
    verify_time = datetime.now(timezone.utc).isoformat()
    diffs: list[FileDiff] = []

    # Files in current scan
    for path, cur in current_files.items():
        if path not in baseline:
            diffs.append(FileDiff(
                change_type="new",
                file_path=path,
                old_checksum=None,
                new_checksum=cur.checksum,
                old_size=None,
                new_size=cur.file_size,
            ))
        else:
            base = baseline[path]
            if cur.checksum != base.checksum:
                diffs.append(FileDiff(
                    change_type="corrupted",
                    file_path=path,
                    old_checksum=base.checksum,
                    new_checksum=cur.checksum,
                    old_size=base.file_size,
                    new_size=cur.file_size,
                ))
            elif cur.mtime != base.mtime or cur.file_size != base.file_size:
                diffs.append(FileDiff(
                    change_type="changed",
                    file_path=path,
                    old_checksum=base.checksum,
                    new_checksum=cur.checksum,
                    old_size=base.file_size,
                    new_size=cur.file_size,
                ))

    # Files in baseline but not in current scan
    for path in baseline:
        if path not in current_files:
            base = baseline[path]
            diffs.append(FileDiff(
                change_type="missing",
                file_path=path,
                old_checksum=base.checksum,
                new_checksum=None,
                old_size=base.file_size,
                new_size=None,
            ))

    return VerifyReport(
        scan_id=scan_id,
        verify_time=verify_time,
        root_path=root_path,
        total_checked=len(current_files),
        diffs=diffs,
    )


def print_report(report: VerifyReport) -> None:
    counts = report.summary_counts
    print(f"\n{'='*60}")
    print(f"  NAS Verify Report — {report.verify_time}")
    print(f"  Root: {report.root_path}")
    print(f"  Files checked: {report.total_checked}")
    print(f"{'='*60}")

    if not report.has_failures:
        print("  OK — all files match baseline.\n")
        return

    print(f"  CORRUPTED : {counts['corrupted']}")
    print(f"  MISSING   : {counts['missing']}")
    print(f"  CHANGED   : {counts['changed']}")
    print(f"  NEW       : {counts['new']}")
    print(f"{'='*60}\n")

    icons = {"corrupted": "[CORRUPTED]", "missing": "[MISSING]", "changed": "[CHANGED]", "new": "[NEW]"}
    for change_type in ("corrupted", "missing", "changed", "new"):
        items = [d for d in report.diffs if d.change_type == change_type]
        if not items:
            continue
        print(f"{icons[change_type]} ({len(items)} file(s)):")
        for diff in items:
            if change_type == "corrupted":
                print(f"  {diff.file_path}")
                print(f"    old: {diff.old_checksum}")
                print(f"    new: {diff.new_checksum}")
            elif change_type == "missing":
                print(f"  {diff.file_path}  (was {diff.old_size} bytes)")
            elif change_type == "changed":
                print(f"  {diff.file_path}  ({diff.old_size} → {diff.new_size} bytes)")
            elif change_type == "new":
                print(f"  {diff.file_path}  ({diff.new_size} bytes)")
        print()


def write_json_diff(report: VerifyReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scan_id": report.scan_id,
        "verify_time": report.verify_time,
        "root_path": report.root_path,
        "total_checked": report.total_checked,
        "summary": report.summary_counts,
        "diffs": [
            {
                "change_type": d.change_type,
                "file_path": d.file_path,
                "old_checksum": d.old_checksum,
                "new_checksum": d.new_checksum,
                "old_size": d.old_size,
                "new_size": d.new_size,
            }
            for d in report.diffs
        ],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

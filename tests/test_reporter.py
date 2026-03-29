import json
from pathlib import Path

from nas_verify.db import FileRecord
from nas_verify.reporter import build_verify_report, write_json_diff


def _rec(path: str, checksum: str, size: int = 100, mtime: float = 1000.0) -> FileRecord:
    return FileRecord(
        file_path=path,
        file_size=size,
        mtime=mtime,
        checksum=checksum,
        scan_time="2024-01-01T00:00:00+00:00",
    )


def test_no_diffs_when_identical() -> None:
    files = {"a.txt": _rec("a.txt", "a" * 64)}
    baseline = {"a.txt": _rec("a.txt", "a" * 64)}
    report = build_verify_report(1, "/mnt/nas", files, baseline)
    assert not report.has_failures
    assert report.total_checked == 1


def test_corrupted_detected() -> None:
    files = {"a.txt": _rec("a.txt", "b" * 64)}
    baseline = {"a.txt": _rec("a.txt", "a" * 64)}
    report = build_verify_report(1, "/mnt/nas", files, baseline)
    assert report.has_failures
    assert report.summary_counts["corrupted"] == 1
    assert report.diffs[0].change_type == "corrupted"


def test_missing_detected() -> None:
    files: dict[str, FileRecord] = {}
    baseline = {"gone.txt": _rec("gone.txt", "a" * 64)}
    report = build_verify_report(1, "/mnt/nas", files, baseline)
    assert report.summary_counts["missing"] == 1


def test_new_file_detected() -> None:
    files = {"new.txt": _rec("new.txt", "c" * 64)}
    baseline: dict[str, FileRecord] = {}
    report = build_verify_report(1, "/mnt/nas", files, baseline)
    assert report.summary_counts["new"] == 1


def test_changed_metadata_only() -> None:
    # Same checksum but different mtime — "changed" not "corrupted"
    files = {"a.txt": _rec("a.txt", "a" * 64, size=200, mtime=2000.0)}
    baseline = {"a.txt": _rec("a.txt", "a" * 64, size=100, mtime=1000.0)}
    report = build_verify_report(1, "/mnt/nas", files, baseline)
    assert report.summary_counts["changed"] == 1
    assert report.summary_counts["corrupted"] == 0


def test_write_json_diff(tmp_path: Path) -> None:
    files = {"a.txt": _rec("a.txt", "b" * 64)}
    baseline = {"a.txt": _rec("a.txt", "a" * 64)}
    report = build_verify_report(1, "/mnt/nas", files, baseline)

    out = tmp_path / "diff.json"
    write_json_diff(report, out)

    data = json.loads(out.read_text())
    assert data["summary"]["corrupted"] == 1
    assert len(data["diffs"]) == 1
    assert data["diffs"][0]["file_path"] == "a.txt"

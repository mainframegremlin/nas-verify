from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from tqdm import tqdm

from .config import AppConfig, ConfigError, load_config
from .db import Database, FileRecord
from .notifier import send_alert
from .reporter import VerifyReport, build_verify_report, print_report, write_json_diff
from .scanner import iter_files, build_file_record, run_scan


DEFAULT_CONFIG = Path.home() / ".config" / "nas-verify" / "config.toml"


@click.group()
@click.option(
    "--config", "-c",
    default=None,
    type=click.Path(dir_okay=False),
    help=f"Path to config.toml (default: {DEFAULT_CONFIG})",
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[str]) -> None:
    """nas-verify: SHA-256 integrity verifier for SMB-mounted NAS shares."""
    ctx.ensure_object(dict)
    config_path = Path(config) if config else DEFAULT_CONFIG
    try:
        ctx.obj["config"] = load_config(config_path)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--notes", default="", help="Optional label for this scan session")
@click.option(
    "--rebuild",
    is_flag=True,
    default=False,
    help="Clear the existing baseline before scanning (use when adding new shares)",
)
@click.pass_context
def scan(ctx: click.Context, notes: str, rebuild: bool) -> None:
    """Walk all configured NAS mounts and record SHA-256 checksums for all files."""
    cfg: AppConfig = ctx.obj["config"]

    missing = [p for p in cfg.mount_paths if not p.exists()]
    if missing:
        for p in missing:
            click.echo(f"Error: mount path does not exist: {p}", err=True)
        sys.exit(1)

    root_str = ", ".join(str(p) for p in cfg.mount_paths)
    click.echo(f"Scanning {root_str} ...")

    with Database(cfg.db_path) as db:
        db.init_schema()
        if rebuild:
            db.clear_baseline()
            click.echo("Baseline cleared.")
        scan_id = db.begin_scan(root_str, notes)

        with tqdm(unit="file", dynamic_ncols=True, desc="Scanning") as pbar:
            def on_file(path: Path, size: int) -> None:
                pbar.set_postfix_str(path.name[:50], refresh=False)
                pbar.update(1)

            total_files, total_bytes = run_scan(cfg, db, scan_id, on_file)

        db.finalize_scan(scan_id, total_files, total_bytes)

    click.echo(
        f"\nScan complete. {total_files} files, "
        f"{total_bytes / (1024**3):.2f} GiB indexed. (scan_id={scan_id})"
    )


@cli.command()
@click.option(
    "--json-out",
    default=None,
    type=click.Path(dir_okay=False),
    help="Write JSON diff log to this path (auto-named if omitted)",
)
@click.option(
    "--no-email",
    is_flag=True,
    default=False,
    help="Suppress email alert even on failure",
)
@click.pass_context
def verify(ctx: click.Context, json_out: Optional[str], no_email: bool) -> None:
    """Re-hash all files and compare against the stored baseline."""
    cfg: AppConfig = ctx.obj["config"]

    missing = [p for p in cfg.mount_paths if not p.exists()]
    if missing:
        for p in missing:
            click.echo(f"Error: mount path does not exist: {p}", err=True)
        sys.exit(1)

    with Database(cfg.db_path) as db:
        db.init_schema()
        baseline = db.get_baseline()

    if not baseline:
        click.echo(
            "No baseline found. Run `nas-verify scan` first.",
            err=True,
        )
        sys.exit(1)

    root_str = ", ".join(str(p) for p in cfg.mount_paths)
    click.echo(f"Verifying {root_str} against {len(baseline)} baseline records ...")

    scan_time = datetime.now(timezone.utc).isoformat()
    current_files: dict[str, FileRecord] = {}

    with tqdm(unit="file", dynamic_ncols=True, desc="Verifying") as pbar:
        for mount_path in cfg.mount_paths:
            for file_path in iter_files(mount_path, cfg.exclude_patterns):
                try:
                    record = build_file_record(file_path, scan_time, cfg.chunk_size)
                except OSError:
                    continue
                current_files[record.file_path] = record
                pbar.set_postfix_str(file_path.name[:50], refresh=False)
                pbar.update(1)

    # Use a fake scan_id of 0 for verify-only runs (no DB write)
    report = build_verify_report(
        scan_id=0,
        root_path=root_str,
        current_files=current_files,
        baseline=baseline,
    )

    print_report(report)

    if report.has_failures:
        # Determine JSON diff output path
        if json_out:
            diff_path = Path(json_out)
        else:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            diff_path = Path(f"nas-verify-diff-{ts}.json")

        write_json_diff(report, diff_path)
        click.echo(f"Diff log written to: {diff_path}")

        if not no_email and cfg.email.enabled:
            try:
                send_alert(cfg.email, report, diff_path)
                click.echo("Alert email sent.")
            except Exception as e:
                click.echo(f"Warning: failed to send email alert: {e}", err=True)

        sys.exit(1)

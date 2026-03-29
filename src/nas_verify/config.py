from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


class ConfigError(Exception):
    pass


@dataclass
class EmailConfig:
    enabled: bool
    smtp_host: str
    smtp_port: int
    use_tls: bool
    username: str
    password: str
    from_addr: str
    to_addrs: list[str]
    subject_template: str = (
        "NAS Integrity Alert on {hostname} — {n_corrupted} corrupted, "
        "{n_missing} missing [{date}]"
    )


@dataclass
class AppConfig:
    mount_paths: list[Path]
    db_path: Path
    exclude_patterns: list[str] = field(default_factory=list)
    chunk_size: int = 1024 * 1024
    email: EmailConfig = field(
        default_factory=lambda: EmailConfig(
            enabled=False,
            smtp_host="",
            smtp_port=587,
            use_tls=True,
            username="",
            password="",
            from_addr="",
            to_addrs=[],
        )
    )


def load_config(config_path: Path) -> AppConfig:
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {config_path}")
    except Exception as e:
        raise ConfigError(f"Failed to parse config: {e}") from e

    try:
        nas = data.get("nas", {})
        # Support both mount_paths (list) and mount_path (single, for compat)
        raw_paths = nas.get("mount_paths")
        if raw_paths is None:
            single = nas.get("mount_path")
            if not single:
                raise ConfigError("Missing required field: [nas] mount_paths")
            raw_paths = [single]
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ConfigError("[nas] mount_paths must be a non-empty list")

        db = data.get("database", {})
        db_path_str = db.get("db_path", "~/.local/share/nas-verify/checksums.db")

        scan = data.get("scan", {})
        exclude_patterns: list[str] = scan.get("exclude_patterns", [
            "**/@eaDir/**",
            "**/#recycle/**",
            "**/.SynologyWorkingDirectory/**",
            "**/.DS_Store",
            "**/Thumbs.db",
        ])
        chunk_size: int = int(scan.get("chunk_size", 1024 * 1024))

        email_data = data.get("email", {})
        # Password: prefer env var
        password = os.environ.get("NAS_VERIFY_SMTP_PASSWORD", email_data.get("password", ""))
        subject_tmpl = email_data.get(
            "subject",
            "NAS Integrity Alert on {hostname} — {n_corrupted} corrupted, "
            "{n_missing} missing [{date}]",
        )
        email_cfg = EmailConfig(
            enabled=bool(email_data.get("enabled", False)),
            smtp_host=str(email_data.get("smtp_host", "")),
            smtp_port=int(email_data.get("smtp_port", 587)),
            use_tls=bool(email_data.get("use_tls", True)),
            username=str(email_data.get("username", "")),
            password=password,
            from_addr=str(email_data.get("from_addr", "")),
            to_addrs=list(email_data.get("to_addrs", [])),
            subject_template=subject_tmpl,
        )

        return AppConfig(
            mount_paths=[Path(p).expanduser() for p in raw_paths],
            db_path=Path(db_path_str).expanduser(),
            exclude_patterns=exclude_patterns,
            chunk_size=chunk_size,
            email=email_cfg,
        )
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"Invalid config: {e}") from e

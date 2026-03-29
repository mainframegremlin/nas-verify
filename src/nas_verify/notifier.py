from __future__ import annotations

import smtplib
import socket
from datetime import datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from .config import EmailConfig
from .reporter import VerifyReport


def _build_subject(template: str, report: VerifyReport) -> str:
    counts = report.summary_counts
    return template.format(
        hostname=socket.gethostname(),
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        n_corrupted=counts["corrupted"],
        n_missing=counts["missing"],
        n_new=counts["new"],
        n_changed=counts["changed"],
    )


def _build_body(report: VerifyReport) -> str:
    counts = report.summary_counts
    lines = [
        f"NAS integrity check completed at {report.verify_time}",
        f"Root path: {report.root_path}",
        f"Files checked: {report.total_checked}",
        "",
        "Summary:",
        f"  Corrupted : {counts['corrupted']}",
        f"  Missing   : {counts['missing']}",
        f"  Changed   : {counts['changed']}",
        f"  New       : {counts['new']}",
        "",
    ]
    if counts["corrupted"]:
        lines.append("Corrupted files:")
        for d in report.diffs:
            if d.change_type == "corrupted":
                lines.append(f"  {d.file_path}")
                lines.append(f"    old: {d.old_checksum}")
                lines.append(f"    new: {d.new_checksum}")
        lines.append("")
    if counts["missing"]:
        lines.append("Missing files:")
        for d in report.diffs:
            if d.change_type == "missing":
                lines.append(f"  {d.file_path}")
        lines.append("")
    lines.append("See attached JSON diff for full details.")
    return "\n".join(lines)


def send_alert(
    config: EmailConfig,
    report: VerifyReport,
    json_diff_path: Optional[Path] = None,
) -> None:
    if not config.enabled:
        return
    if not config.to_addrs:
        raise ValueError("Email enabled but no to_addrs configured")

    msg = MIMEMultipart()
    msg["From"] = config.from_addr
    msg["To"] = ", ".join(config.to_addrs)
    msg["Subject"] = _build_subject(config.subject_template, report)
    msg.attach(MIMEText(_build_body(report), "plain"))

    if json_diff_path and json_diff_path.exists():
        with open(json_diff_path, "rb") as f:
            part = MIMEBase("application", "json")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=json_diff_path.name,
        )
        msg.attach(part)

    if config.smtp_port == 465:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port) as smtp:
            if config.username:
                smtp.login(config.username, config.password)
            smtp.sendmail(config.from_addr, config.to_addrs, msg.as_string())
    else:
        with smtplib.SMTP(config.smtp_host, config.smtp_port) as smtp:
            if config.use_tls:
                smtp.starttls()
            if config.username:
                smtp.login(config.username, config.password)
            smtp.sendmail(config.from_addr, config.to_addrs, msg.as_string())

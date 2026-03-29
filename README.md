# nas-verify

SHA-256 integrity verifier for SMB-mounted Synology NAS shares. Scans your NAS, stores a checksum baseline in SQLite, and alerts you when files are corrupted, missing, or changed.

## How it works

- **scan** — walks all configured mount points, computes a SHA-256 checksum for every file, and stores the results in a local SQLite database. Run this once to establish a baseline, then again periodically to update it.
- **verify** — re-hashes every file and compares against the stored baseline. Reports corrupted, missing, changed, and new files. Writes a JSON diff log and optionally sends an email alert on failure.

---

## Requirements

- Python 3.10+
- Linux with `cifs-utils` installed
- A Synology NAS with SMB enabled

---

## Installation

```bash
git clone https://github.com/mainframegremlin/nas-verify.git
cd nas-verify

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

---

## First-time setup

### 1. Mount your first NAS share

**Install cifs-utils (varies based on pkg manager):**

```bash
sudo apt update && sudo apt install cifs-utils
```

**Create the credentials file** (keeps your password out of fstab):

```bash
sudo nano /etc/nas-credentials
```

```
username=your_synology_username
password=your_synology_password
domain=WORKGROUP
```

```bash
sudo chmod 600 /etc/nas-credentials
```

**Create the mount point** (named after the NAS share):

```bash
sudo mkdir -p /mnt/nas/pictures
```

> Name each mount point after the share it contains — `/mnt/nas/pictures`, `/mnt/nas/videos`, `/mnt/nas/documents`, etc. This keeps things readable as you add more shares.

**Add to `/etc/fstab`** (replace `NAS_IP` with your Synology's IP):

```
//NAS_IP/pictures  /mnt/nas/pictures  cifs  credentials=/etc/nas-credentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,_netdev,noauto,x-systemd.automount,x-systemd.idle-timeout=60  0  0
```

> Tip: run `id` to confirm your uid/gid. On most single-user installs it's 1000.

**Mount and verify:**

```bash
sudo systemctl daemon-reload
sudo mount /mnt/nas/pictures
ls /mnt/nas/pictures
```

### 2. Configure nas-verify

```bash
mkdir -p ~/.config/nas-verify
cp config.toml.example ~/.config/nas-verify/config.toml
nano ~/.config/nas-verify/config.toml
```

Set your mount paths:

```toml
[nas]
mount_paths = [
    "/mnt/nas/pictures",
]
```

### 3. Run your first scan

```bash
nas-verify scan --notes "initial baseline"
```

---

## Usage

### Scan (build or update the baseline)

```bash
nas-verify scan
nas-verify scan --notes "after adding videos share"
nas-verify scan --rebuild   # clear baseline and start fresh
```

### Verify (check files against baseline)

```bash
nas-verify verify
nas-verify verify --json-out /path/to/diff.json
nas-verify verify --no-email   # suppress alert even if email is configured
```

Use `--config` to point at a different config file:

```bash
nas-verify --config /path/to/other.toml verify
```

Exits with code `0` if all files match, `1` if any problems are found — suitable for use in cron or scripts.

### Example output

```
============================================================
  NAS Verify Report — 2026-03-29T21:27:01+00:00
  Root: /mnt/nas/pictures, /mnt/nas/videos
  Files checked: 831
============================================================
  OK — all files match baseline.
```

On failure:

```
============================================================
  CORRUPTED :  1
  MISSING   :  2
  CHANGED   :  0
  NEW       :  3
============================================================

[CORRUPTED] (1 file(s)):
  2024/summer/DSCF1154.JPG
    old: a3f1...
    new: 9bc2...

[MISSING] (2 file(s)):
  2023/holiday/IMG_0042.JPG  (was 4821304 bytes)
  ...
```

---

## Adding a new NAS share

### 1. Create the mount point

Name it after the share (e.g. adding a `videos` share):

```bash
sudo mkdir -p /mnt/nas/videos
```

### 2. Add to `/etc/fstab`

```bash
sudo nano /etc/fstab
```

Add a new line following the same pattern — share name matches the mount point name:

```
//NAS_IP/videos  /mnt/nas/videos  cifs  credentials=/etc/nas-credentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,_netdev,noauto,x-systemd.automount,x-systemd.idle-timeout=60  0  0
```

### 3. Mount it

```bash
sudo systemctl daemon-reload
sudo mount /mnt/nas/videos
ls /mnt/nas/videos
```

### 4. Add it to `~/.config/nas-verify/config.toml`

```toml
[nas]
mount_paths = [
    "/mnt/nas/pictures",
    "/mnt/nas/videos",
]
```

### 5. Rebuild the baseline

```bash
nas-verify scan --rebuild --notes "added videos share"
```

The `--rebuild` flag clears the old baseline before scanning so there are no stale entries from previous mount configurations.

---

## Automating with cron

Run verification nightly at 2 AM:

```bash
sudo mkdir -p /var/log/nas-verify
sudo chown $USER /var/log/nas-verify

crontab -e
```

Add:

```cron
0 2 * * * /home/youruser/code/nas-verify/.venv/bin/nas-verify verify --json-out /var/log/nas-verify/diff-$(date +\%Y\%m\%d).json >> /var/log/nas-verify/verify.log 2>&1
```

---

## Email alerts

Set `enabled = true` in the `[email]` section of `~/.config/nas-verify/config.toml` and fill in your SMTP details. The alert includes a summary in the message body and attaches the full JSON diff log.

Store your SMTP password as an environment variable rather than in the config file:

```bash
export NAS_VERIFY_SMTP_PASSWORD="yourpassword"
```

---

## Configuration reference

```toml
[nas]
mount_paths = [                        # one entry per share, named after the share
    "/mnt/nas/pictures",
    # "/mnt/nas/videos",
]

[database]
db_path = "~/.local/share/nas-verify/checksums.db"

[scan]
exclude_patterns = [
    "**/@eaDir/**",                    # Synology thumbnail cache
    "**/#recycle/**",                  # Synology recycle bin
    "**/.SynologyWorkingDirectory/**",
    "**/.DS_Store",
    "**/Thumbs.db",
]
chunk_size = 1048576                   # read buffer in bytes (increase for faster NAS)

[email]
enabled = false
smtp_host = "smtp.example.com"
smtp_port = 587                        # 587 = STARTTLS, 465 = SMTP_SSL
use_tls = true
username = "alerts@example.com"
password = ""                          # prefer NAS_VERIFY_SMTP_PASSWORD env var
from_addr = "nas-verify <alerts@example.com>"
to_addrs = ["you@example.com"]
```

---

## Troubleshooting mounts


| Problem                    | Fix                                                 |
| -------------------------- | --------------------------------------------------- |
| `vers=3.0` fails           | Try `vers=2.1` in fstab (older DSM versions)        |
| Permission denied on files | Check `uid`/`gid` in fstab match output of `id`     |
| Authentication failure     | Check `/etc/nas-credentials`; review DSM Log Center |
| Mount hangs at boot        | Ensure `_netdev` is in fstab options                |
| Can't reach NAS            | `ping NAS_IP` — check network and DSM firewall      |


---

## Running tests

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```


# Recommended Process

## Day-to-day

Run `verify` on a nightly cron job. This re-hashes every file and compares against the baseline—it's your corruption detection pass.

```bash
nas-verify verify
```

You don't need to do anything else unless you're actively adding or changing files on the NAS.

---

## After adding new files

When you copy new photos, videos, or other files to the NAS, run a plain `scan` to baseline them. New files will otherwise show up as `new` on every verify until they're scanned.

```bash
nas-verify scan --notes "added summer 2026 photos"
```

`scan` adds new files to the baseline and updates any that changed, without touching records for files that weren't modified.

---

## After adding a new share

When you mount a new share and add it to `config.toml`, run `scan` with `--rebuild` to start clean. `--rebuild` clears the existing baseline first, then rescans everything across all configured mounts.

```bash
nas-verify scan --rebuild --notes "added videos share"
```

Use `--rebuild` sparingly. It wipes the baseline entirely before rescanning.

---

## When NOT to use --rebuild

Don't use `--rebuild` as a routine step. It's only appropriate when:

- You've added or removed a mount path in `config.toml`
- You've moved files around and want to reset rather than triage the diff
- Something has gone wrong with the baseline and you want to start fresh

For everything else, a plain `scan` is sufficient.

---

## Summary


| Situation                         | Command                                  |
| --------------------------------- | ---------------------------------------- |
| Routine integrity check           | `nas-verify verify` (automated, nightly) |
| Added new files to NAS            | `nas-verify scan`                        |
| Added a new share                 | `nas-verify scan --rebuild`              |
| Something went wrong, start fresh | `nas-verify scan --rebuild`              |



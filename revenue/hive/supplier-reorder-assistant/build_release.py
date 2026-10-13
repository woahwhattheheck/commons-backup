#!/usr/bin/env python3
"""Build a standalone supplier reorder desk from an explicit source allowlist."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

ROOT_NAME = "supplier-reorder-desk"
SCHEMA = "commons-supplier-reorder-release-v1"
# No directory recursion: workspaces, exports, caches, and arbitrary files are
# not distribution inputs. Build from a clean, trusted checkout.
SOURCE_FILES = (
    "reorder_assistant.py", "desk.py", "desk.html", "workspace_backup.py",
    "README.md", "BROWSER.md", "BACKUP.md", "CSV_IMPORT.md",
    "examples/stock.csv", "examples/rules.csv", "examples/catalog.csv",
    "examples/receipts.csv",
)
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
START_HERE = """# Supplier Reorder Desk\n
This folder is the runnable application, not a link to a repository. Use Python
3.11 or later with its standard-library SQLite support. No pip install, account,
API key, or network service is required. Extract the entire ZIP before running.
The packaged examples are fictional; do not mix them with real inventory.

## Open the local browser desk

Open a terminal in this extracted supplier-reorder-desk folder and run:

```sh
python desk.py --db ./workspace.sqlite3 --port 8086
```

Open http://127.0.0.1:8086 in a browser on the same computer. Use the desk's sample
or import your stock, rules and supplier catalog CSVs. Review the unsent draft
and any flagged alternatives, then import receipt CSVs. Close with Ctrl+C;
restart with the same --db path to reopen saved plans and receipt history.
Use python3 instead of python on systems where that is the Python 3 command.
The service binds only to this computer. This package is not an authenticated
public hosted service; do not expose it through a public proxy or tunnel.

## Try the command-line example

Run these commands in this extracted folder; each is a single line:

```sh
python reorder_assistant.py plan --stock examples/stock.csv --rules examples/rules.csv --catalog examples/catalog.csv --as-of 2026-09-08 --out example-plan.json
python reorder_assistant.py receive --stock examples/stock.csv --plan example-plan.json --receipts examples/receipts.csv --out-stock example-stock.csv --out-log example-receipts.json
```

No order is sent. Alternatives require explicit review. For later receipts keep
the updated stock with its complete log, use new output filenames, and pass
--prior-log as explained in README.md. Never treat a draft as received stock.
README.md's initial repository cd instruction is unnecessary in this folder.
Developer test commands in the source docs refer to files not in this package.

## Back up the complete browser workspace

```sh
python workspace_backup.py snapshot --db ./workspace.sqlite3 --out ./workspace-backup.zip
python workspace_backup.py restore --archive ./workspace-backup.zip --db ./restored.sqlite3
python desk.py --db ./restored.sqlite3 --port 8087
```

Snapshot and restore destinations must be new files. Backups are unencrypted;
keep them and the live workspace private. See BACKUP.md for limits and BROWSER.md
for browser operations. manifest.json describes the bundled file bytes; it is
not an authenticity signature or a statement about real supplier deliveries.

This code-only distribution contains no pre-existing workspace or customer data.
The release builder intentionally excludes runtime databases, exports, and new
optional adapters. The application retains its own documented limitations.
"""


class ReleaseError(ValueError):
    """The selected source cannot be safely packaged as this distribution."""


def _source_bytes(root: Path, name: str) -> bytes:
    path = root
    for component in Path(name).parts:
        path = path / component
        if path.is_symlink():
            raise ReleaseError(f"release source must not be a symlink: {name}")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ReleaseError(f"release source must be a regular file: {name}")
    if info.st_size > MAX_FILE_BYTES:
        raise ReleaseError(f"release source is too large: {name}")
    with path.open("rb") as handle:
        content = handle.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ReleaseError(f"release source is too large: {name}")
    return content


def release_bytes(source_dir: Path) -> bytes:
    """Snapshot allowlisted inputs, then build deterministic ZIP_STORED bytes."""
    root = Path(source_dir).resolve(strict=True)
    if not root.is_dir():
        raise ReleaseError("release source must be a directory")
    payload = {name: _source_bytes(root, name) for name in SOURCE_FILES}
    payload["START_HERE.md"] = START_HERE.encode("utf-8")
    if sum(map(len, payload.values())) > MAX_TOTAL_BYTES:
        raise ReleaseError("release source exceeds the total size limit")
    manifest = {
        "schema": SCHEMA,
        "application": ROOT_NAME,
        "files": [
            {"path": name, "bytes": len(content),
             "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in sorted(payload.items())
        ],
    }
    payload["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(payload.items()):
            member = zipfile.ZipInfo(f"{ROOT_NAME}/{name}", (1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, content)
    return buffer.getvalue()


def build_release(source_dir: Path, output: Path) -> dict[str, object]:
    """Publish a completed archive without replacing an existing destination."""
    output = Path(output)
    if os.path.lexists(output):
        raise ReleaseError(f"release output already exists: {output}")
    data = release_bytes(source_dir)
    staging = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".reorder-release-", delete=False) as handle:
            staging = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # A competing publisher may have created output since the preflight.
        # link fails instead of replacing its archive, including symlink aliases.
        os.link(staging, output)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
    return {"archive": str(output), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "source_files": len(SOURCE_FILES)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_release(args.source_dir, args.out)
    except (ReleaseError, OSError, ValueError) as exc:
        parser.exit(2, f"release error: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

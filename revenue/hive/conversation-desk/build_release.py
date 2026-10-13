#!/usr/bin/env python3
"""Build a standalone Conversation Desk from an explicit source allowlist."""
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

ROOT_NAME = "conversation-desk"
SCHEMA = "commons-conversation-desk-release-v1"
# Never recurse the product directory: databases, screenshots, exports, caches,
# restore artifacts, logs and customer files are not release inputs.
SOURCE_FILES = ("app.py", "index.html", "desk.js", "README.md")
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
START_HERE = """# Conversation Desk — standalone release

This extracted folder is the runnable local application. It does not require a
repository checkout, pip install, account, API key or remote model. Python 3.10+
with the standard library is sufficient. Optional screenshot transcription uses
an independently installed local Tesseract executable; manual transcript entry
and every other feature work without it.

## Start the desk

Open a terminal in this extracted `conversation-desk` folder and run:

```sh
python3 app.py --db ./conversation-desk.sqlite3 --port 8769
```

Then open http://127.0.0.1:8769 on the same computer. Use `python` instead of
`python3` where that is the Python 3 command. The SQLite database is created in
this folder and is private runtime data; it is not part of the release ZIP.

The service binds to loopback by default and has no authentication. Do not put
it behind a public proxy or tunnel, and do not use a shared public instance for
private chats. Draft suggestions are local templates built from the words and
intent you provide. Nothing is automatically sent to a dating or messaging
platform.

## Core workflow

1. Create a conversation or use the fictional example.
2. Paste or correct the transcript and write the point you want to communicate.
3. Generate three tone options, edit the one you prefer and save it.
4. Reopen the same local database to continue later.
5. Export your workspace as JSON or delete individual data / erase the workspace.

See `README.md` for the full data, OCR, revision, deletion and security limits.
`manifest.json` records exact packaged file hashes; it is an integrity inventory,
not a signature. This code-only distribution intentionally contains no database,
screenshot, export, restore input, log, cache, secret or customer conversation.
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
            {
                "path": name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(payload.items())
        ],
    }
    payload["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(payload.items()):
            member = zipfile.ZipInfo(
                f"{ROOT_NAME}/{name}", (1980, 1, 1, 0, 0, 0)
            )
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, content)
    return buffer.getvalue()


def build_release(source_dir: Path, output: Path) -> dict[str, object]:
    """Publish one complete archive without replacing an existing destination."""
    output = Path(output)
    if os.path.lexists(output):
        raise ReleaseError(f"release output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    data = release_bytes(source_dir)
    staging = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=".conversation-release-", delete=False
        ) as handle:
            staging = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Exclusive hard-link publication preserves a peer-created destination.
        os.link(staging, output)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
    return {
        "archive": str(output),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source_files": len(SOURCE_FILES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path, default=Path(__file__).resolve().parent
    )
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

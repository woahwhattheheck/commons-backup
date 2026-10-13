"""Package only the standalone bugfix page. No network, build or deployment.

Python 3.9+; standard library only. Run from an isolated/cloud workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from typing import Any
import zipfile

SOURCE_PATH = Path("sites/bugfix/index.html")
ARCHIVE_NAME = "bugfix-deploy.zip"
RECEIPT_NAME = "package-receipt.json"


def build_package(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    """Create a new output directory with the ZIP and a separate checksum receipt.

    Read one explicit source file, never a directory glob. An existing output
    directory is never overwritten. Errors propagate; no deployment is implied.
    """
    source = Path(repo_root) / SOURCE_PATH
    if source.is_symlink():
        raise ValueError("The page must be a regular file, not a symbolic link")
    data = source.read_bytes()
    text = data.decode("utf-8")
    if not text.lstrip().lower().startswith("<!doctype html>"):
        raise ValueError("The source is not the expected UTF-8 HTML document")

    # Stored entries avoid compressor-version differences. Preserve page bytes.
    buffer = io.BytesIO()
    entry = zipfile.ZipInfo("index.html", date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    entry.compress_type = zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(entry, data)
    archive_bytes = buffer.getvalue()
    git_blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "operation": "package_only",
        "source_path": SOURCE_PATH.as_posix(),
        "source_bytes": len(data),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "source_git_blob_sha1": hashlib.sha1(git_blob).hexdigest(),
        "archive_file": ARCHIVE_NAME,
        "archive_members": ["index.html"],
        "archive_bytes": len(archive_bytes),
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "deployment_performed": False,
    }
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")

    # Validate and construct in memory before creating output. Never clobber a
    # previous package or silently combine it with handoff notes or other files.
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / ARCHIVE_NAME).open("xb") as handle:
        handle.write(archive_bytes)
    with (destination / RECEIPT_NAME).open("xb") as handle:
        handle.write(receipt_bytes)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="New output directory; never overwritten")
    args = parser.parse_args(argv)
    try:
        receipt = build_package(args.repo_root, args.output)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f"Package not completed: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

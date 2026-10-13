#!/usr/bin/env python3
"""Build or verify a curated, reproducible standalone trade-quote ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

FILES = (
    "trade_quote.py", "build_release.py", "README.md", "RELEASE.md",
    "examples/pricing-rules.json", "examples/request.json",
    "examples/request-missing.json", "examples/site-photo.svg",
)
START_HERE = """TRADE QUOTE TO SCHEDULE - FICTIONAL DEMONSTRATION

Extract the archive into an empty directory. Install Python 3.10 or newer
with its standard library, including sqlite3. No Git checkout or pip install
is needed. Open a terminal in the extracted directory and read RELEASE.md.
On Windows, use py in place of python3 when appropriate.

python3 trade_quote.py quote --request examples/request.json --rules examples/pricing-rules.json --issued-on 2026-09-08 --out-dir out
python3 trade_quote.py serve --quotes-dir out --schedule out/schedule.csv

Open the acceptance_url stored in out/Q-*.json; choose 2026-09-15 at 09:00
for this fixed-date fictional example. Stop the server with Ctrl-C.
For a real quote, supply actual measurements, reviewed pricing and the
appropriate issue date. Keep the resulting output files in this workspace.
Nothing in the demonstration sends a message, takes a payment or writes to
an external calendar. This is not a deployment or a customer installation.
"""


class ReleaseError(ValueError):
    """The release could not be built or its bytes do not match its manifest."""


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_release(output: Path, *, root: Path | None = None) -> dict:
    root = (root or Path(__file__).resolve().parent).resolve()
    output = Path(output).absolute()
    payload = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve() != root / name:
            raise ReleaseError(f"required release file is missing or linked: {name}")
        if output.resolve() == path.resolve() or (output.exists() and output.samefile(path)):
            raise ReleaseError(f"output would replace a release source: {name}")
        payload[name] = path.read_bytes()
    payload["START_HERE.txt"] = START_HERE.encode("utf-8")
    manifest = {"schema": "commons-trade-release-v1", "files": {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(payload.items())
    }}
    payload["MANIFEST.json"] = _json(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".trade-release-", suffix=".zip", delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        verify_archive(temporary)
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"archive": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "files": len(payload)}


def verify_archive(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            expected = set(FILES) | {"START_HERE.txt", "MANIFEST.json"}
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected:
                raise ReleaseError("archive file list differs from the release contents")
            manifest = json.loads(archive.read("MANIFEST.json"))
            if not isinstance(manifest, dict) or manifest.get("schema") != "commons-trade-release-v1":
                raise ReleaseError("unsupported release manifest")
            records = manifest.get("files")
            if not isinstance(records, dict) or set(records) != expected - {"MANIFEST.json"}:
                raise ReleaseError("manifest file list differs from the release contents")
            for name, record in records.items():
                data = archive.read(name)
                actual = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                if record != actual:
                    raise ReleaseError(f"manifest mismatch: {name}")
            return manifest
    except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot verify release: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path, help="archive to build")
    mode.add_argument("--verify", type=Path, help="archive to check without extracting")
    args = parser.parse_args()
    try:
        result = build_release(args.out) if args.out else verify_archive(args.verify)
        print(json.dumps(result, sort_keys=True))
    except (ReleaseError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

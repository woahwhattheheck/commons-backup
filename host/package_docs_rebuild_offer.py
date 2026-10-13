#!/usr/bin/env python3
"""Package the finished Docs Rebuild Repair documents; no network or dependencies."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "revenue" / "services" / "docs-rebuild-repair"
DOCUMENTS = ("offer.md", "delivery-checklist.md")


def build_package(source: Path, output: Path) -> dict[str, object]:
    """Create a deterministic ZIP at a new path, after reading all documents."""
    contents = {}
    for name in DOCUMENTS:
        path = source / name
        if path.is_symlink():
            raise ValueError(f"Document must be a regular file: {name}")
        data = path.read_bytes()
        if not data.decode("utf-8").strip():
            raise ValueError(f"Document is empty: {name}")
        contents[name] = data
    manifest = {
        "schema_version": 1,
        "offer_id": "docs-rebuild-repair-v1",
        "audience": "internal_sales_enablement",
        "files": {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(contents.items())
        },
    }
    contents["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    payload = buffer.getvalue()
    with output.open("xb") as handle:
        handle.write(payload)
    return {"path": str(output), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New ZIP file; parent directory must exist")
    args = parser.parse_args()
    try:
        result = build_package(SOURCE, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Package not created: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create a deterministic source-only VeriCodeGen harness ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

FILES = (
    "__init__.py",
    "core.py",
    "cli.py",
    "package.py",
    "README.md",
    "REPORT_TEMPLATE.md",
    "test_harness.py",
)
EPOCH = (1980, 1, 1, 0, 0, 0)


def build(root: Path, destination: Path) -> dict:
    payloads: dict[str, bytes] = {}
    manifest_rows = []
    for rel in FILES:
        data = (root / rel).read_bytes()
        payloads[rel] = data
        manifest_rows.append({"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "schema": "vericodegen.refactor-source-package/v1",
        "files": manifest_rows,
        "unsigned": True,
        "competition_submission": False,
    }
    payloads["SHA256SUMS.json"] = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    destination.mkdir(parents=True, exist_ok=True)
    out = destination / "vericodegen-lean-refactor-harness.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in sorted(payloads):
            info = zipfile.ZipInfo(rel, EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, payloads[rel])
    return {"zip": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "files": len(manifest_rows)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--dest", required=True)
    ns = ap.parse_args()
    print(json.dumps(build(Path(ns.root).resolve(), Path(ns.dest).resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

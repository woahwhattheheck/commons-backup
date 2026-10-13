#!/usr/bin/env python3
"""Create a checksum manifest for the scoped continuity publication."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
files = {}
for path in sorted(HERE.rglob("*")):
    if path.is_file() and path.name != "MANIFEST.json" and "__pycache__" not in path.parts:
        data = path.read_bytes()
        files[str(path.relative_to(HERE))] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
manifest = {
    "schema_version": 1,
    "current_archive_sha256": "401d2dbcaf2a089386a145bd0237b79070dfda730d4cf582ad814a59a778a86d",
    "source_manifest_sha256": "051a5eddac522986c5b43f972b1597ef96415c9669f65b17c66c172844c50ca1",
    "seed": 9922023,
    "seats": [0, 1],
    "full_trace_divergences": 0,
    "files": files,
}
(HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(hashlib.sha256((HERE / "MANIFEST.json").read_bytes()).hexdigest())

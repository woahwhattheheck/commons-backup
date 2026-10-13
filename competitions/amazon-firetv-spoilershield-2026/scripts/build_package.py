#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DIST = ROOT / "dist"
FILES = ["index.html", "styles.css", "core.js", "demo_episode.js", "config.js", "app.js"]

DIST.mkdir(exist_ok=True)
zip_path = DIST / "spoilershield-firetv-webapp.zip"
manifest = {}
for name in FILES:
    data = (WEB / name).read_bytes()
    manifest[name] = hashlib.sha256(data).hexdigest()
manifest_bytes = (json.dumps({"schema": "spoilershield/package-manifest-v1", "files": manifest}, sort_keys=True, separators=(",", ":")) + "\n").encode()

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for name in FILES:
        info = zipfile.ZipInfo(name, date_time=(2026, 9, 13, 12, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        zf.writestr(info, (WEB / name).read_bytes())
    info = zipfile.ZipInfo("PACKAGE-MANIFEST.json", date_time=(2026, 9, 13, 12, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    zf.writestr(info, manifest_bytes)

print(f"{zip_path} sha256={hashlib.sha256(zip_path.read_bytes()).hexdigest()}")

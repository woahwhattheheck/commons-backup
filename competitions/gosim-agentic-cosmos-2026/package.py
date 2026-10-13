from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

FILES = ["README.md", "manifest.json", "observer.py", "replay.py", "demo.py", "test_observer.py", "package.py"]
EPOCH = (2020, 1, 1, 0, 0, 0)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(outdir: Path) -> dict:
    root = Path(__file__).resolve().parent
    outdir.mkdir(parents=True, exist_ok=True)
    members = {name: digest((root / name).read_bytes()) for name in FILES}
    manifest = (json.dumps({"files": members, "source_only": True, "official_submission": False}, sort_keys=True, separators=(",", ":")) + "\n").encode()
    sbom = outdir / "agentic-cosmos-sbom.json"
    sbom.write_bytes(manifest)
    archive = outdir / "agentic-cosmos-foundation.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(FILES):
            info = zipfile.ZipInfo(name, EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, (root / name).read_bytes())
        info = zipfile.ZipInfo("SBOM.json", EPOCH)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        zf.writestr(info, manifest)
    return {"zip_sha256": digest(archive.read_bytes()), "sbom_sha256": digest(manifest)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: package.py OUTDIR")
    print(json.dumps(build(Path(sys.argv[1])), sort_keys=True))

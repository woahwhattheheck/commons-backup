#!/usr/bin/env python3
"""Build the deterministic synthetic INPRS v2 file-backed handoff."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_LEGACY_BUILDER = Path(__file__).with_name("_build_synthetic_file_handoff_v1.py")
_spec = importlib.util.spec_from_file_location("inprs_file_handoff_builder_v1", _LEGACY_BUILDER)
if _spec is None or _spec.loader is None:
    raise RuntimeError("unable to load retained v1 synthetic builder")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

_ACCEPT_PATH = Path(__file__).with_name("file_backed_acceptance.py")
_accept_spec = importlib.util.spec_from_file_location("inprs_file_backed_acceptance_v2", _ACCEPT_PATH)
if _accept_spec is None or _accept_spec.loader is None:
    raise RuntimeError("unable to load v2 acceptance root")
_accept = importlib.util.module_from_spec(_accept_spec)
_accept_spec.loader.exec_module(_accept)

OPPORTUNITY_ID = _accept.OPPORTUNITY_ID
SOURCE_SYSTEM = _accept.SOURCE_SYSTEM
canonical_manifest_bytes = _accept.canonical_manifest_bytes
source_record_digest = _accept.source_record_digest
_sha = _accept._sha


def build(root: Path) -> tuple[Path, Path, str]:
    manifest_path, bundle_path, _ = _legacy.build(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    contracts = {
        row["legacy_id"]: row
        for row in bundle.get("contracts", [])
        if isinstance(row, dict) and isinstance(row.get("legacy_id"), str)
    }
    for row in manifest.get("contracts", []):
        cid = row.get("legacy_id")
        candidate = contracts.get(cid)
        if not isinstance(candidate, dict):
            raise RuntimeError(f"synthetic candidate missing contract {cid!r}")
        paths = row.get("version_paths")
        history = candidate.get("version_history")
        if not isinstance(paths, list) or not isinstance(history, list) or len(paths) != len(history):
            raise RuntimeError(f"synthetic version topology invalid for {cid!r}")
        row["version_roots"] = [
            {"revision": entry["revision"], "path": path, "sha256": entry["sha256"]}
            for path, entry in zip(paths, history)
        ]
    manifest["schema_version"] = _accept.SCHEMA_VERSION
    manifest_raw = canonical_manifest_bytes(manifest)
    manifest_path.write_bytes(manifest_raw)
    return manifest_path, bundle_path, _sha(manifest_raw)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    manifest, bundle, pin = build(args.output)
    print(json.dumps({"manifest": str(manifest), "bundle": str(bundle), "manifest_sha256": pin}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

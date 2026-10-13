#!/usr/bin/env python3
"""Offline source-change rehearsal; stdout only, no provider or filesystem writes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from . import preflight as p
except ImportError:
    import preflight as p


def run_demo() -> dict:
    """Run five source-binding cases through real compile and verify APIs."""
    source = {"repo": "https://example.test/team/sample", "commit_sha": "1" * 40,
              "subdir": "apps/example"}
    request = {"schema": p.REQUEST_SCHEMA, "provider": "synthetic-host",
               "source": source, "target": {"project_id": "synthetic-project"},
               "manifest_policy": {"evaluation_epoch": 1000, "max_age_seconds": 100}}
    manifest = {"schema": p.MANIFEST_SCHEMA, "provider": "synthetic-host",
                "captured_at_epoch": 950, "actions": [
                    {"name": "deploy-project", "kind": "DEPLOY_EXISTING_PROJECT",
                     "source_binding": "existing_project_binding"}]}
    binding = {"schema": p.BINDING_SCHEMA, "provider": "synthetic-host",
               "project_id": "synthetic-project", "source": dict(source)}
    changed = json.loads(p.canonical_bytes(request))
    changed["source"]["commit_sha"] = "2" * 40
    updated_binding = json.loads(p.canonical_bytes(binding))
    updated_binding["source"] = dict(changed["source"])
    stale_manifest = dict(manifest, captured_at_epoch=899)
    cases = [
        ("no-source-record", request, manifest, None, p.HOLD_UNBOUND),
        ("matching-source-record", request, manifest, binding, p.READY),
        ("new-commit-old-record", changed, manifest, binding, p.HOLD_UNBOUND),
        ("new-commit-updated-record", changed, manifest, updated_binding, p.READY),
        ("stale-capability-record", changed, stale_manifest, updated_binding, p.HOLD_AMBIGUOUS),
    ]
    results = []
    for case_id, req, man, bind, expected in cases:
        request_raw, manifest_raw = p.canonical_bytes(req), p.canonical_bytes(man)
        binding_raw = p.canonical_bytes(bind) if bind is not None else None
        report = p.compile_bytes(request_raw, manifest_raw, binding_raw)
        if report["status"] != expected:
            raise p.DomainError(f"demo case {case_id}: unexpected status")
        verified = p.verify_bytes(request_raw, manifest_raw, p.canonical_bytes(report), binding_raw)
        if p.canonical_bytes(verified) != p.canonical_bytes(report):
            raise p.DomainError(f"demo case {case_id}: verification mismatch")
        if not all(value is False for value in report["external_authority"].values()):
            raise p.DomainError(f"demo case {case_id}: unexpected external authority")
        results.append({"case_id": case_id, "inputs": {"request": req, "manifest": man,
                       "project_binding": bind}, "report": report})
    root = Path(__file__).resolve().parent
    return {
        "schema": "deploy-source-change-rehearsal.v1",
        "evidence_class": "SYNTHETIC_OFFLINE_REHEARSAL",
        "notice": "Planning evidence only. No deployment, provider authentication or live capability assertion.",
        "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in ("preflight.py", "demo.py")},
        "cases": results,
    }


def main() -> int:
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

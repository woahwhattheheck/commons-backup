#!/usr/bin/env python3
"""Head-first source lease reconciliation using one pre-fetched Git comparison.

No GitHub/Slack requests or changes: called only at recovery/collision/publication
boundaries. File overlap alone never proves completion.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA = re.compile(r"^[0-9a-fA-F]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH = re.compile(r"^[A-Za-z0-9_./-]+$")


def _paths(raw: Any, label: str) -> list[str]:
    if not isinstance(raw, list) or any(not isinstance(p, str) for p in raw):
        raise ValueError(f"{label} must be a list of strings")
    cleaned: set[str] = set()
    for path in raw:
        p = path.replace("\\", "/").strip().strip("/")
        if not p or p.startswith("../") or "/../" in p or p.startswith("./") or "/./" in p or p.endswith("/.."):
            raise ValueError(f"invalid {label} path")
        cleaned.add(p)
    return sorted(cleaned)


def _overlap(first: str, second: str) -> bool:
    """Recognize exact file or directory scope, not partial name prefixes."""
    return first == second or first.startswith(second + "/") or second.startswith(first + "/")


def reconcile(record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one stale source lease without calling any external provider."""
    if not isinstance(record, dict):
        raise ValueError("record must be a JSON object")
    op = record.get("operation_id")
    repo = record.get("repo")
    branch = record.get("branch")
    owner = record.get("owner")
    if not all(isinstance(x, str) and x.strip() for x in (op, repo, branch, owner)):
        raise ValueError("operation_id, repo, branch, owner are required nonempty strings")
    if not REPO.fullmatch(repo) or not BRANCH.fullmatch(branch) or ".." in branch:
        raise ValueError("invalid repo or branch")
    if record.get("lease_kind", "source") not in ("source", "publication", "claim"):
        raise ValueError("lease_kind must be source, publication, or claim")

    expected = record.get("expected_head")
    observed = record.get("observed_head")
    if not isinstance(expected, str) or not isinstance(observed, str):
        raise ValueError("expected_head and observed_head must be strings")
    claimed = _paths(record.get("claimed_paths", []), "claimed_paths")
    changed = _paths(record.get("touched_paths", []), "touched_paths")
    if not isinstance(record.get("comparison_complete", False), bool):
        raise ValueError("comparison_complete must be a boolean")
    if not isinstance(record.get("stale", False), bool):
        raise ValueError("stale must be a boolean")

    proof = record.get("completion_proof") or {}
    if not isinstance(proof, dict):
        raise ValueError("completion_proof must be object")
    if proof.get("verified", False) is not False and proof.get("verified") is not True:
        raise ValueError("completion_proof.verified must be boolean")
    overlap = sorted(p for p in changed if any(_overlap(p, s) for s in claimed))
    evidence_valid = proof.get("verified") is True and isinstance(proof.get("reference"), str) and bool(proof["reference"].strip())

    output: dict[str, Any] = {
        "operation_id": op.strip(), "repo": repo.lower(), "branch": branch,
        "owner": owner.strip(), "origin": record.get("origin", ""),
        "lease_kind": record.get("lease_kind", "source"),
        "expected_head": expected.lower(), "observed_head": observed.lower(),
        "claimed_paths": claimed, "touched_paths": changed,
        "overlap_paths": overlap, "comparison_complete": record.get("comparison_complete", False),
        "provider_readback": record.get("provider_readback", ""),
        "status": "INCOMPLETE_EVIDENCE", "next_expected_head": None,
        "retire_source_lease": False,
        "publication_lease_unchanged": True, "claim_custody_unchanged": True,
        "guidance": "Verify current branch head and comparison once before recovery; never infer release from Slack alone.",
    }

    # Source evidence cannot waive publication or compensation claim custody.
    if output["lease_kind"] != "source":
        output["status"] = "SEPARATE_CUSTODY"
        output["guidance"] = "Source proof cannot retire publication or bounty/claim ownership."
    elif not SHA.fullmatch(expected) or not SHA.fullmatch(observed) or not output["provider_readback"]:
        output["guidance"] = "Full 40-character SHA identities and provider readback are required."
    elif expected.lower() == observed.lower():
        output["status"] = "UNCHANGED_STALE" if record.get("stale", False) else "HEAD_UNCHANGED"
        output["guidance"] = "No branch advance; refresh owner activity and TAKE before reassigning."
    elif not record.get("comparison_complete", False) or not claimed or not changed:
        output["guidance"] = "Head changed but full path comparison or source scope is missing; preserve CAS fence."
    elif overlap:
        if evidence_valid:
            output["status"] = "VERIFIED_COMPLETION"
            output["retire_source_lease"] = True
            output["guidance"] = "Verified completion can retire source lease only; preserve publication and claim custody."
        else:
            output["status"] = "COLLISION_RECONCILIATION"
            output["guidance"] = "Claimed paths changed. Reconcile exact source and owner receipt before duplicate work."
    else:
        output["status"] = "ORTHOGONAL_ADVANCE"
        output["next_expected_head"] = observed.lower()
        output["guidance"] = "Disjoint change. Reconfirm ownership, use new expected head with CAS; never force update."
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="provider comparison and source lease JSON object")
    parser.add_argument("--compact", action="store_true", help="one JSON line")
    args = parser.parse_args(argv)
    try:
        out = reconcile(json.loads(args.snapshot.read_text(encoding="utf-8")))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(out, sort_keys=True, indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

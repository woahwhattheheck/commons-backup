#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify that a built archive changes only the land overlay boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_candidate import BASE_ARCHIVE_SHA256, BASE_MAIN_SHA256, read_archive, sha256

ALLOWED_CHANGED = {"main.py"}
ALLOWED_ADDED = {"canonical_main.py", "land_overlay.py", "LAND-74-98.json"}


def verify(base: Path, candidate: Path) -> dict:
    base_bytes = base.read_bytes()
    if sha256(base_bytes) != BASE_ARCHIVE_SHA256:
        raise ValueError("base archive is not the pinned current TITAN")
    before = read_archive(base)
    after = read_archive(candidate)
    if sha256(before["main.py"].data) != BASE_MAIN_SHA256:
        raise ValueError("base main.py is not pinned")
    before_names, after_names = set(before), set(after)
    removed = sorted(before_names - after_names)
    added = sorted(after_names - before_names)
    changed = sorted(
        name for name in before_names & after_names if before[name].data != after[name].data
    )
    if removed:
        raise ValueError(f"candidate removed members: {removed}")
    if set(added) != ALLOWED_ADDED:
        raise ValueError(f"unexpected added members: {added}")
    if set(changed) != ALLOWED_CHANGED:
        raise ValueError(f"unexpected changed members: {changed}")
    if after["canonical_main.py"].data != before["main.py"].data:
        raise ValueError("canonical_main.py is not the exact base entrypoint")
    internal = json.loads(after["LAND-74-98.json"].data)
    for name, expected in internal["injected"].items():
        if sha256(after[name].data) != expected:
            raise ValueError(f"internal hash mismatch for {name}")
    report = {
        "status": "PASS",
        "base_archive_sha256": sha256(base_bytes),
        "candidate_archive_sha256": sha256(candidate.read_bytes()),
        "changed_existing_members": changed,
        "added_members": added,
        "unchanged_members": len(before_names) - len(changed),
        "policy_delta": internal["policy_delta"],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.base, args.candidate)
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

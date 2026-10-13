#!/usr/bin/env python3
"""Resolve explicit opponent cold-start failures without losing first attempts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    replacements = []
    for source in sorted((args.panel / "raw").glob("*/*.json")):
        arm = source.parent.name
        report = json.loads(source.read_text())
        resolved = copy.deepcopy(report)
        for index, game in enumerate(report.get("games", [])):
            if game.get("status") == "complete":
                continue
            seed, seat, opponent = game["seed"], game["candidate_seat"], game["opponent"]
            replica_path = args.panel / "replications" / arm / f"{seed}.json"
            replica = json.loads(replica_path.read_text())
            matches = [g for g in replica.get("games", [])
                       if g.get("seed") == seed and g.get("candidate_seat") == seat
                       and g.get("opponent") == opponent and g.get("status") == "complete"]
            if len(matches) != 1:
                raise ValueError(f"no unique complete replication for {(arm, seed, seat, opponent)}")
            resolved["games"][index] = matches[0]
            replacements.append({
                "cell": {"arm": arm, "seed": seed, "candidate_seat": seat,
                         "opponent": opponent},
                "original_report": str(source), "original_sha256": digest(source),
                "original_failure": game.get("failure"),
                "replication_report": str(replica_path),
                "replication_sha256": digest(replica_path),
                "resolution": "replace failed cell only; retain all other original games",
            })
        target = args.output / "raw" / arm / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n")
    manifest = {"schema": "titan.widefield.runtime-resolution.v1",
                "replacements": replacements,
                "original_attempts_retained_at": str(args.panel / "attempts")}
    (args.output / "runtime-resolution.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

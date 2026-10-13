#!/usr/bin/env python3
"""Run a fictional end-to-end media-rights desk rehearsal through the real CLI."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "rights_ops.py"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def write_json(path: Path, value) -> None:
    path.write_bytes(canonical(value))


def run_cli(*args: str):
    proc = subprocess.run(
        [sys.executable, str(CLI), *map(str, args)],
        cwd=HERE,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"CLI failed rc={proc.returncode}: {' '.join(map(str, args))}\n{proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CLI emitted non-JSON output: {proc.stdout!r}") from exc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path, help="new or empty rehearsal directory")
    ns = ap.parse_args(argv)
    root = ns.output
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise SystemExit("output must be a new or empty directory")
    else:
        root.mkdir(parents=True)

    db = root / "desk.sqlite3"
    manifest_path = root / "manifest.json"
    before_path = root / "placement-before.json"
    exact_path = root / "placement-exact.json"
    after_path = root / "placement-after.json"
    bundle = root / "handoff"
    bundle.mkdir()

    manifest = {
        "schema": "media-rights-ops/v1",
        "assets": [
            {"asset_id": "fictional-cut", "sha256": "a" * 64, "parent_asset_id": None}
        ],
        "grants": [
            {
                "grant_id": "fictional-grant",
                "asset_id": "fictional-cut",
                "authority_ref": "fictional-owner-row-1",
                "valid_from": "2026-10-01T00:00:00.100000Z",
                "valid_until": "2026-10-31T23:59:59.900000Z",
                "channels": ["web"],
                "territories": ["US"],
            }
        ],
    }
    common = {
        "asset_id": "fictional-cut",
        "channel": "web",
        "territory": "US",
        "starts_at": "2026-10-04T23:00:00.100000Z",
    }
    before = {**common, "request_id": "before-revoke", "ends_at": "2026-10-05T00:00:00Z"}
    exact = {**common, "request_id": "exact-revoke", "ends_at": "2026-10-05T00:00:00.250000Z"}
    after = {**common, "request_id": "after-revoke", "ends_at": "2026-10-05T00:00:00.500000Z"}
    write_json(manifest_path, manifest)
    write_json(before_path, before)
    write_json(exact_path, exact)
    write_json(after_path, after)

    events = []
    events.append(["import", run_cli("import", db, manifest_path, "--at", "2026-09-30T12:00:00.123456Z")])
    events.append(["place-before", run_cli("place", db, before_path, "--at", "2026-10-01T12:00:00.100001Z")])
    events.append(["place-exact", run_cli("place", db, exact_path, "--at", "2026-10-01T12:00:00.100002Z")])
    events.append(["place-after", run_cli("place", db, after_path, "--at", "2026-10-01T12:00:00.100003Z")])

    # Equivalent syntax proves canonical replay identity rather than creating a fourth row.
    after_replay = dict(after)
    after_replay["ends_at"] = "2026-10-05T00:00:00.5Z"
    write_json(after_path, after_replay)
    events.append(["repeat-after", run_cli("place", db, after_path, "--at", "2026-10-01T12:00:00.200000Z")])

    events.append(["revoke", run_cli("revoke", db, "fictional-grant", "--at", "2026-10-05T00:00:00.250000Z")])
    queue = run_cli("queues", db, "--as-of", "2026-10-05T00:00:00.250000Z", "--horizon-days", "30")
    events.append(["queues", queue])
    export_result = run_cli("export", db, bundle, "--as-of", "2026-10-05T00:00:00.250000Z", "--horizon-days", "30")
    events.append(["export", export_result])

    snapshot = json.loads((bundle / "snapshot.json").read_text(encoding="utf-8"))
    exported_queue = json.loads((bundle / "queues.json").read_text(encoding="utf-8"))
    with (bundle / "placements.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    summary = (bundle / "summary.md").read_text(encoding="utf-8")
    receipt = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))

    if exported_queue != queue:
        raise RuntimeError("standalone and exported queue projections differ")
    retract_ids = [row["request_id"] for row in queue["retraction_review"]]
    if retract_ids != ["after-revoke"]:
        raise RuntimeError(f"unexpected retraction queue: {retract_ids}")
    if len(snapshot["placements"]) != 3 or len(csv_rows) != 3:
        raise RuntimeError("repeat request created or hid a placement")
    if events[4][1]["status"] != "IDEMPOTENT_REPLAY":
        raise RuntimeError("equivalent repeated request was not idempotent")
    if "Placements: 3" not in summary or "Retraction review rows: 1" not in summary:
        raise RuntimeError("Markdown handoff counts do not match reopened data")

    file_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(bundle.iterdir())
        if path.is_file()
    }
    result = {
        "schema": "media-rights-ops-rehearsal/v1",
        "fictional": True,
        "events": [{"step": step, "result": value} for step, value in events],
        "boundary": {
            "revoked_at": "2026-10-05T00:00:00.250000Z",
            "retraction_request_ids": retract_ids,
            "not_retracted_request_ids": ["before-revoke", "exact-revoke"],
        },
        "reopened": {
            "snapshot_placements": len(snapshot["placements"]),
            "csv_placements": len(csv_rows),
            "standalone_equals_exported_queues": True,
            "markdown_counts_match": True,
            "receipt_schema": receipt["schema"],
        },
        "handoff_sha256": file_hashes,
    }
    write_json(root / "rehearsal-result.json", result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

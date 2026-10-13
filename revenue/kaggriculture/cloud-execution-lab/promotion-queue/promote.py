#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Promotion queue CLI.

    promote.py submit --name <id> --artifact <file> --games <file> --policy <json>
    promote.py run [--id <submission> | --all] --predecessors <config.json>
    promote.py list [--status pending|running|passed|failed]
    promote.py status <submission>
    promote.py rerun <submission>
    promote.py receipt <submission> [--verify]
    promote.py pin <file>

Pipeline: submit (hash-pin inputs) -> run (FIFO paired gate vs frozen
control AND vs LAND) -> signed tamper-evident receipt. The gate itself is
always the existing titan-v3-paired-game-gate scripts; this CLI is the
orchestration and receipt layer around them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pq import POLICY_VERSION  # noqa: E402
from pq.pinning import PinStore, sha256_file  # noqa: E402
from pq.receipts import ReceiptStore  # noqa: E402
from pq.runner import (  # noqa: E402
    Attempt,
    RunError,
    load_predecessor_config,
)
from pq.signing import SigningError, load_key  # noqa: E402
from pq.store import Queue, QueueError  # noqa: E402


def _signing_key(args) -> bytes | None:
    path = getattr(args, "signing_key", None)
    if not path:
        return None
    try:
        return load_key(Path(path))
    except SigningError as exc:
        print(f"signing key error: {exc}")
        raise SystemExit(2)


def _state_dir(args) -> Path:
    return Path(args.state_dir).expanduser().resolve()


def cmd_submit(args) -> int:
    state = _state_dir(args)
    pins = PinStore(state / "pin-store")
    queue = Queue(state / "queue")
    policy_path = Path(args.policy)
    manifest = pins.pin(
        {
            "candidate_artifact": Path(args.artifact),
            "candidate_games": Path(args.games),
            "policy": policy_path,
        },
        note=args.note or "",
    )
    existing = queue.find_by_input_digest(manifest["input_digest"])
    if existing is not None:
        print(f"DUPLICATE {existing['id']} status={existing['status']}")
        print(f"pin {manifest['pin_id']} already queued; not re-enqueued.")
        return 0
    entry, created = queue.submit(
        submission_id=manifest["pin_id"],
        name=args.name,
        pin_id=manifest["pin_id"],
        input_digest=manifest["input_digest"],
        note=args.note or "",
    )
    assert created
    print(f"SUBMITTED {entry['id']} status=pending")
    print(f"pin {manifest['pin_id']} input_digest={manifest['input_digest'][:16]}...")
    for name, rec in manifest["inputs"].items():
        print(f"  {name}: sha256={rec['sha256'][:16]}... bytes={rec['bytes']}")
    return 0


def cmd_pin(args) -> int:
    path = Path(args.file)
    digest = sha256_file(path)
    print(f"{digest}  {path}")
    return 0


def _run_one(queue, pins, receipts, entry, config, policy, attempt_obj, strategy,
              signing_key=None, config_sha256=None) -> int:
    submission_id = entry["id"]
    pin_manifest = pins.get_pin(entry["pin_id"])
    ok, problems = pins.verify_pin(entry["pin_id"])
    if not ok:
        queue.set_status(submission_id, "failed")
        print(f"FAILED {submission_id}: pin verification failed: {problems}")
        return 1
    queue.set_status(submission_id, "running")
    attempt_n = len([a for a in entry["attempts"] if a.get("kind") != "requeue"]) + 1
    try:
        outcome = attempt_obj.execute(
            submission_id=submission_id,
            candidate_name=entry["name"],
            pin_manifest=pin_manifest,
            config=config,
            policy=policy,
            strategy=strategy,
        )
    except (RunError, QueueError) as exc:
        queue.set_status(submission_id, "failed")
        queue.record_attempt(
            submission_id,
            {"n": attempt_n, "kind": "run", "error": str(exc)[:2000]},
        )
        print(f"FAILED {submission_id}: {exc}")
        return 1
    prev_digest = None
    if entry["last_receipt"]:
        try:
            prev = receipts.load(entry["last_receipt"])
            prev_digest = (prev.get("integrity") or {}).get("digest")
        except KeyError:
            prev_digest = None
    receipt = receipts.build(
        submission_id=submission_id,
        attempt_n=attempt_n,
        policy_version=config.get("policy_version", POLICY_VERSION),
        pin_manifest=pin_manifest,
        predecessors=outcome["predecessor_identity"],
        comparisons=outcome["comparisons"],
        verdict=outcome["verdict"],
        timings=outcome["timings"],
        prev_receipt_digest=prev_digest,
        extra={
            "strategy": outcome["strategy"],
            "gate_sha256": outcome["gate_sha256"],
            "config_sha256": config_sha256,
        },
        signing_key=signing_key,
    )
    receipt_path = receipts.save(receipt)
    status = "passed" if outcome["verdict"] == "PROMOTE" else "failed"
    queue.record_attempt(
        submission_id,
        {
            "n": attempt_n,
            "kind": "run",
            "verdict": outcome["verdict"],
            "strategy": outcome["strategy"],
            "receipt_id": receipt["receipt_id"],
            "duration_ms": outcome["timings"]["duration_ms"],
        },
    )
    queue.set_status(submission_id, status)
    print(f"{outcome['verdict']} {submission_id} status={status}")
    print(f"receipt {receipt['receipt_id']} -> {receipt_path}")
    print(f"strategy={outcome['strategy']} "
          f"duration_ms={outcome['timings']['duration_ms']}")
    for comp in outcome["comparisons"]:
        print(f"  slot={comp['slot']} verdict={comp['verdict']} "
              f"exit={comp['exit_code']} failed_checks={comp.get('failed_checks')}")
    return 0 if status == "passed" else 1


def cmd_run(args) -> int:
    state = _state_dir(args)
    pins = PinStore(state / "pin-store")
    queue = Queue(state / "queue")
    receipts = ReceiptStore(state)
    config = load_predecessor_config(args.predecessors)
    # Pin the predecessor config itself: the receipt binds the exact bytes
    # that selected the engine/runner/slots, so a config swap mid-run is
    # detectable from the sealed receipt alone.
    config_record = pins.put_blob(Path(args.predecessors))
    config_sha256 = config_record["sha256"]
    signing_key = _signing_key(args)
    attempt_obj = Attempt(
        state_dir=state,
        gate_dir=Path(args.gate_dir) if args.gate_dir else None
        or (Path(__file__).resolve().parent.parent / "titan-v3-paired-game-gate"),
    )
    if args.id:
        entries = [queue.get(args.id)]
        if entries[0]["status"] != "pending":
            print(f"SKIP {args.id}: status={entries[0]['status']} (use rerun first)")
            return 2
    else:
        from pq.store import STATUS_PENDING as _PENDING

        entries = sorted(
            queue.list(_PENDING), key=lambda e: e["created_at"]
        )
        if not entries:
            print("queue empty: nothing pending")
            return 0
    code = 0
    for entry in entries:
        # refresh entry (status may have changed)
        entry = queue.get(entry["id"])
        if entry["status"] != "pending":
            print(f"SKIP {entry['id']}: status={entry['status']}")
            continue
        policy = json.loads(
            pins.blob_path(
                pins.get_pin(entry["pin_id"])["inputs"]["policy"]["sha256"]
            ).read_text(encoding="utf-8")
        )
        rc = _run_one(
            queue, pins, receipts, entry, config, policy, attempt_obj, args.strategy,
            signing_key=signing_key, config_sha256=config_sha256,
        )
        code = code or rc
    return code


def cmd_list(args) -> int:
    queue = Queue(_state_dir(args) / "queue")
    entries = queue.list(args.status)
    entries.sort(key=lambda e: e["created_at"])
    for entry in entries:
        attempts = len([a for a in entry["attempts"] if a.get("kind") == "run"])
        print(f"{entry['id']}  {entry['name']}  {entry['status']}  "
              f"attempts={attempts} last_receipt={entry['last_receipt']}")
    if not entries:
        print("(empty)")
    return 0


def cmd_status(args) -> int:
    queue = Queue(_state_dir(args) / "queue")
    try:
        entry = queue.get(args.id)
    except QueueError as exc:
        print(str(exc))
        return 1
    print(json.dumps(entry, indent=2, sort_keys=True))
    return 0


def cmd_rerun(args) -> int:
    queue = Queue(_state_dir(args) / "queue")
    try:
        entry = queue.rerun(args.id)
    except QueueError as exc:
        print(str(exc))
        return 1
    print(f"REQUEUED {entry['id']} status=pending "
          f"(history kept: {len(entry['attempts'])} attempt records)")
    return 0


def cmd_receipt(args) -> int:
    state = _state_dir(args)
    queue = Queue(state / "queue")
    receipts = ReceiptStore(state)
    try:
        entry = queue.get(args.id)
    except QueueError as exc:
        print(str(exc))
        return 1
    if not entry["last_receipt"]:
        print(f"{args.id}: no receipt yet")
        return 1
    receipt = receipts.load(entry["last_receipt"])
    if args.verify:
        key = _signing_key(args)
        ok, reason = receipts.verify(receipt, signing_key=key)
        what = "OK" if ok else "TAMPERED"
        signed = " +signature" if key else ""
        print(f"verify {receipt['receipt_id']}: {what}{signed} ({reason})")
        return 0 if ok else 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        default=".promotion-queue-state",
        help="queue state directory (default: ./.promotion-queue-state)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("submit", help="hash-pin a candidate and enqueue it")
    p.add_argument("--name", required=True, help="candidate name")
    p.add_argument("--artifact", required=True, help="candidate artifact file")
    p.add_argument("--games", required=True, help="candidate GAMES.jsonl panel")
    p.add_argument("--policy", required=True, help="gate policy JSON file")
    p.add_argument("--note", default="", help="submitter note")
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser("pin", help="print the SHA-256 of a file")
    p.add_argument("file")
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("run", help="run pending promotions through the gate")
    p.add_argument("--id", default=None, help="run one submission")
    p.add_argument("--all", action="store_true", help="run all pending (FIFO)")
    p.add_argument("--predecessors", required=True, help="predecessor config JSON")
    p.add_argument("--gate-dir", default=None, help="titan-v3-paired-game-gate dir")
    p.add_argument(
        "--signing-key", default=None,
        help="file with raw key bytes to HMAC-sign the sealed receipt",
    )
    p.add_argument(
        "--strategy",
        default="auto",
        choices=("auto", "paired", "dual"),
        help="gate strategy (default: auto)",
    )
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("list", help="list queue entries")
    p.add_argument("--status", default=None,
                   choices=("pending", "running", "passed", "failed"))
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="show one queue entry")
    p.add_argument("id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("rerun", help="requeue a submission (history is kept)")
    p.add_argument("id")
    p.set_defaults(func=cmd_rerun)

    p = sub.add_parser("receipt", help="show or verify the latest receipt")
    p.add_argument("id")
    p.add_argument("--verify", action="store_true")
    p.add_argument(
        "--signing-key", default=None,
        help="verify the receipt's HMAC signature against this key file",
    )
    p.set_defaults(func=cmd_receipt)

    args = parser.parse_args(argv)
    if args.command == "run" and not args.id and not args.all:
        parser.error("run needs --id or --all")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

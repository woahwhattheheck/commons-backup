from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .core import ContractError, DocumentSnapshot, Ledger, compile_ledger, read_workspace, verify_bundle, write_bundle, write_workspace


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="civic-ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init")
    init.add_argument("--meeting-id", required=True)
    init.add_argument("--workspace", required=True)

    add = sub.add_parser("add")
    add.add_argument("--workspace", required=True)
    add.add_argument("--doc-id", required=True)
    add.add_argument("--kind", choices=["agenda", "minutes", "addendum"], required=True)
    add.add_argument("--source-url", required=True)
    add.add_argument("--observed-at", required=True)
    add.add_argument("--input", required=True)

    comp = sub.add_parser("compile")
    comp.add_argument("--workspace", required=True)
    comp.add_argument("--output-dir", required=True)
    comp.add_argument("--as-of", default=None)
    comp.add_argument("--max-source-age-days", type=int, default=90)

    ver = sub.add_parser("verify")
    ver.add_argument("--output-dir", required=True)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            write_workspace(Ledger(args.meeting_id), args.workspace)
            print(json.dumps({"ok": True, "workspace": args.workspace, "meeting_id": args.meeting_id}, sort_keys=True))
        elif args.cmd == "add":
            ledger = read_workspace(args.workspace)
            text = Path(args.input).read_text("utf-8")
            snap = DocumentSnapshot.create(
                meeting_id=ledger.meeting_id, doc_id=args.doc_id, kind=args.kind, source_url=args.source_url,
                observed_at=args.observed_at, text=text,
            )
            changed = ledger.add(snap)
            write_workspace(ledger, args.workspace)
            print(json.dumps({"ok": True, "added": changed, "doc_id": snap.doc_id, "sha256": snap.sha256}, sort_keys=True))
        elif args.cmd == "compile":
            ledger = read_workspace(args.workspace)
            compiled = compile_ledger(ledger, as_of=args.as_of or utc_now(), max_source_age_days=args.max_source_age_days)
            manifest = write_bundle(compiled, args.output_dir)
            print(json.dumps({"ok": True, "manifest": manifest}, sort_keys=True))
        elif args.cmd == "verify":
            print(json.dumps(verify_bundle(args.output_dir), sort_keys=True))
        return 0
    except (ContractError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

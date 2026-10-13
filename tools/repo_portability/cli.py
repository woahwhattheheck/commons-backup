from __future__ import annotations

import argparse
import json
import sys

from .portability import PortabilityError, create_snapshot, verify_snapshot, write_migration_plan


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline verified Git repository portability")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("snapshot", help="create and independently verify a full cold snapshot")
    s.add_argument("--repo", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--label")

    v = sub.add_parser("verify", help="independently verify a snapshot bundle + canonical manifest")
    v.add_argument("--bundle", required=True)
    v.add_argument("--manifest", required=True)

    m = sub.add_parser("plan", help="compile an owner-authored migration inventory to a non-authorizing plan")
    m.add_argument("--inventory", required=True)
    m.add_argument("--out", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            result = create_snapshot(args.repo, args.out, repository_label=args.label)
            print(json.dumps({"status": "SNAPSHOT_VERIFIED", "bundle_sha256": result["bundle"]["sha256"]}, sort_keys=True))
            return 0
        if args.command == "verify":
            result = verify_snapshot(args.bundle, args.manifest)
            print(json.dumps({"status": "SNAPSHOT_VERIFIED", "bundle_sha256": result["bundle"]["sha256"]}, sort_keys=True))
            return 0
        if args.command == "plan":
            result = write_migration_plan(args.inventory, args.out)
            print(json.dumps({"status": "PLAN_COMPILED_NO_ACTION_EXECUTED", "inventory_sha256": result["inventory_sha256"]}, sort_keys=True))
            return 0
        raise AssertionError(args.command)
    except PortabilityError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .gate import MAX_JSON_BYTES, ProvenanceInputError, assess_bundle, verify_receipt


def _load(path: str):
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise ProvenanceInputError("input must be an ordinary file")
    if source.stat().st_size > MAX_JSON_BYTES:
        raise ProvenanceInputError("input exceeds size limit")
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceInputError("input is not valid UTF-8 JSON") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sapio-elain-provenance-gate")
    sub = parser.add_subparsers(dest="command", required=True)
    assess = sub.add_parser("assess")
    assess.add_argument("bundle")
    verify = sub.add_parser("verify")
    verify.add_argument("bundle")
    verify.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "assess":
            result = assess_bundle(_load(args.bundle))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0 if result["outcome"] == "QA_REVIEW_READY_EVIDENCE_ONLY" else 3
        ok = verify_receipt(_load(args.bundle), _load(args.receipt))
        print(json.dumps({"receipt_integrity_valid": ok, "current_release_authority": False}, sort_keys=True))
        return 0 if ok else 2
    except ProvenanceInputError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

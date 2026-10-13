from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from contract_fixture import run_acceptance
from contract_gate import EvidenceInputError, attach_signature, canonical_manifest_bytes, prepare_manifest


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only cross-network shipment evidence gate")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="evaluate shipments and emit an unsigned digest-bound manifest")
    prepare.add_argument("input", help="JSON array of shipment evidence")

    attach = sub.add_parser("attach", help="attach a buyer-controlled detached signature to a prepared manifest")
    attach.add_argument("prepared", help="prepared manifest JSON")
    attach.add_argument("--signer-id", required=True)
    attach.add_argument("--algorithm", required=True)
    attach.add_argument("--signature", required=True)

    sub.add_parser("acceptance", help="run and emit the frozen 240-shipment synthetic acceptance manifest")
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare":
            output = prepare_manifest(_load(args.input))
        elif args.command == "attach":
            output = attach_signature(
                _load(args.prepared),
                signer_id=args.signer_id,
                algorithm=args.algorithm,
                signature=args.signature,
            )
        else:
            output = run_acceptance()
        sys.stdout.buffer.write(canonical_manifest_bytes(output))
        return 0
    except (EvidenceInputError, json.JSONDecodeError, OSError) as exc:
        code = exc.code if isinstance(exc, EvidenceInputError) else "MALFORMED_INPUT"
        sys.stderr.write(json.dumps({"status": "ERROR", "code": code, "message": str(exc)}, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path

from intake_gate import build_receipt, canonical_json, verify_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a TenderProof paid-pilot intake")
    parser.add_argument("intake", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    data = json.loads(args.intake.read_text(encoding="utf-8"))
    receipt = build_receipt(data)
    if not verify_receipt(receipt):
        raise SystemExit("internal receipt verification failed")
    text = canonical_json(receipt) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(f"{receipt['gate']['state']} {receipt['receipt']['payload_sha256']}")
    return 0 if receipt["gate"]["state"] == "READY_FOR_DELIVERY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

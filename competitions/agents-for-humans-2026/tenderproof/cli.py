from __future__ import annotations

import argparse
import json
from pathlib import Path

from core import build_packet, canonical_json, verify_packet


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile an offline TenderProof evidence-bound RFP packet")
    parser.add_argument("--rfp", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    rfp_text = args.rfp.read_text(encoding="utf-8")
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    packet = build_packet(rfp_text, evidence, as_of=args.as_of)
    if not verify_packet(packet):
        raise SystemExit("internal verification failed")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(packet) + "\n", encoding="utf-8")
    print(f"{packet['decision']['state']} {packet['receipt']['payload_sha256']} {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path

from strands_agent import build_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenderProof through Strands Agents")
    parser.add_argument("--rfp", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    rfp = args.rfp.read_text(encoding="utf-8")
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    agent = build_agent()
    prompt = (
        "Process this RFP end to end. Use the extraction, compile, and verify tools; never assert unsupported facts.\n\n"
        f"AS_OF: {args.as_of}\n\nRFP:\n{rfp}\n\nEVIDENCE_JSON:\n{json.dumps(evidence, sort_keys=True)}"
    )
    result = agent(prompt)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

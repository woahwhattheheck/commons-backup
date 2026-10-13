from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .fixture import build_fixture, canonical_fixture_bytes
    from .gate import HOLD, RELEASE_READY, validate_packets
except ImportError:
    from fixture import build_fixture, canonical_fixture_bytes
    from gate import HOLD, RELEASE_READY, validate_packets


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical streaming rendition fixture.")
    parser.add_argument("--expect-ready", type=int)
    parser.add_argument("--expect-hold", type=int)
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    packets, fault_assets = build_fixture()
    fixture_sha = hashlib.sha256(canonical_fixture_bytes()).hexdigest()
    if fixture_sha != manifest["fixture"]["canonical_sha256"]:
        raise SystemExit("canonical fixture SHA-256 does not match manifest")
    if fault_assets != manifest["fixture"]["fault_assets"]:
        raise SystemExit("fixture fault map does not match manifest")

    validation = validate_packets(packets)
    results = validation["results"]
    ready = sum(row["status"] == RELEASE_READY for row in results)
    hold = sum(row["status"] == HOLD for row in results)

    if validation["projection_sha256"] != manifest["projection_sha256"]:
        raise SystemExit("projection SHA-256 does not match manifest")
    if ready != manifest["fixture"]["release_ready"] or hold != manifest["fixture"]["hold"]:
        raise SystemExit("result counts do not match manifest")
    if args.expect_ready is not None and ready != args.expect_ready:
        raise SystemExit(f"expected {args.expect_ready} ready, got {ready}")
    if args.expect_hold is not None and hold != args.expect_hold:
        raise SystemExit(f"expected {args.expect_hold} hold, got {hold}")

    out = {
        "fixture_sha256": fixture_sha,
        "projection_sha256": validation["projection_sha256"],
        "total": len(results),
        "release_ready": ready,
        "hold": hold,
    }
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

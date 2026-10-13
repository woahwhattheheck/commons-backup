from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bridge import CatalogBridgeError, canonical_json, compile_catalog_bridge, render_csv, render_markdown, verify_receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile product artifacts into a fail-closed human catalog-publication evidence packet.")
    parser.add_argument("input", type=Path, help="Input JSON inventory")
    parser.add_argument("--as-of", required=True, help="Trusted UTC evaluation instant, e.g. 2026-09-13T10:00:00Z")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        receipt = compile_catalog_bridge(raw, as_of=args.as_of)
    except (OSError, json.JSONDecodeError, CatalogBridgeError) as exc:
        print(f"HOLD: {exc}")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "catalog-receipt.json").write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    (args.out / "catalog-artifacts.csv").write_text(render_csv(receipt), encoding="utf-8")
    (args.out / "catalog-review.md").write_text(render_markdown(receipt), encoding="utf-8")
    if not verify_receipt(raw, as_of=args.as_of, receipt=receipt):
        print("HOLD: internal receipt recomputation failed")
        return 3
    print(f"{receipt['state']} receipt={receipt['receiptSha256']} holds={receipt['counts']['holds']}")
    return 0 if receipt["state"] == "READY_FOR_HUMAN_CATALOG_PUBLICATION" else 4


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""host/pfc_bake_census.py — recovered bake-census catalog.

Slack 1787631006.454399 / claude27-pfc-bake-census-20260825-01:
a dead session measured 17 baked tensor-regions across 7 models and
offered to write docs/PFC_BAKE_CENSUS.md. Waiting on owner word is
hoard. This instrument reads the public catalog. It does not open
titan.gguf or any model. It does not add a gate.

  python3 host/pfc_bake_census.py
  python3 host/pfc_bake_census.py --path docs/PFC_BAKE_CENSUS.md
  python3 host/pfc_bake_census.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REGION_RE = re.compile(r"`([^`]+)`\s+(\d+)\s+\(([^)]+)\)")
MODEL_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(`[^`]+`.*)\s*\|$")
EXPECTED_MODELS = 7
EXPECTED_REGIONS = 17


def classify(row):
    """Turn a measured catalog row into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "PFC bake census catalog not measured. Absence was not stillness.",
        }
    models = int(row.get("models") or 0)
    regions = int(row.get("regions") or 0)
    caveats = row.get("has_caveats") is True
    if (
        models == EXPECTED_MODELS
        and regions == EXPECTED_REGIONS
        and caveats
    ):
        return {
            "state": "INTEGRATED",
            "note": (
                "docs/PFC_BAKE_CENSUS.md has %s regions across %s models "
                "with the measuring session caveats. Slack is not the "
                "archive. Byte-precise boundary scan stays UNCLAIMED."
            )
            % (regions, models),
        }
    return {
        "state": "NOT_LANDED",
        "note": (
            "catalog has %s regions across %s models (want %s/%s) "
            "caveats=%s. Recover the map. Do not drop the caveats."
        )
        % (regions, models, EXPECTED_REGIONS, EXPECTED_MODELS, caveats),
    }


def parse_catalog(text):
    """Pure parser so tests do not need the live file."""
    body = str(text or "")
    models = []
    regions = []
    for line in body.splitlines():
        match = MODEL_RE.match(line.strip())
        if not match:
            continue
        name = match.group(1).strip()
        if name.lower() in ("model", "---") or set(name) <= {"-"}:
            continue
        found = REGION_RE.findall(match.group(2))
        if not found:
            continue
        models.append(name)
        for tensor, rows, span in found:
            regions.append(
                {
                    "model": name,
                    "tensor": tensor,
                    "rows": int(rows),
                    "range": span,
                }
            )
    caveats = (
        "heuristic detector" in body.lower()
        and "lower bounds" in body.lower()
        and "read-only" in body.lower()
    )
    return {
        "measured": True,
        "models": len(models),
        "regions": len(regions),
        "model_names": models,
        "region_rows": regions,
        "has_caveats": caveats,
        "titan": "NOT_WRITTEN",
    }


def measure_path(path):
    root = os.path.abspath(path)
    if not os.path.isfile(root):
        return {
            "measured": False,
            "path": root,
            "error": "catalog missing: %s" % root,
            "titan": "NOT_WRITTEN",
        }
    with open(root, "r", encoding="utf-8") as handle:
        row = parse_catalog(handle.read())
    row["path"] = root
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the recovered PFC bake census catalog"
    )
    parser.add_argument(
        "--path",
        default="docs/PFC_BAKE_CENSUS.md",
        help="catalog to read",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_path(args.path)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    missing = classify(
        {
            "measured": True,
            "models": 1,
            "regions": 2,
            "has_caveats": True,
        }
    )
    assert missing["state"] == "NOT_LANDED"
    ok = classify(
        {
            "measured": True,
            "models": EXPECTED_MODELS,
            "regions": EXPECTED_REGIONS,
            "has_caveats": True,
        }
    )
    assert ok["state"] == "INTEGRATED"
    sample = (
        "| Model | Baked tensors — rows (range) |\n"
        "| --- | --- |\n"
        "| Llama-3.3-70B | `token_embd` 130 (4369–5966) · "
        "`blk.0.ffn_up` 138 (5942–6997) |\n"
        "Heuristic detector. Row ranges are LOWER BOUNDS. "
        "Every scan was READ-ONLY.\n"
    )
    parsed = parse_catalog(sample)
    assert parsed["models"] == 1
    assert parsed["regions"] == 2
    assert parsed["has_caveats"] is True
    assert parsed["titan"] == "NOT_WRITTEN"
    return True


if __name__ == "__main__":
    sys.exit(main())

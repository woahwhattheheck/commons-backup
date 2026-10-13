#!/usr/bin/env python3
"""Fail-closed readiness gate for Hutter MixerLab benchmark evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from mixerlab import verify_receipt

DEFAULT_RULES = Path(__file__).with_name("rules.json")


def evaluate(receipt: dict, rules: dict) -> dict:
    reasons: list[str] = []
    try:
        verify_receipt(receipt)
    except (ValueError, TypeError, KeyError) as exc:
        reasons.append(f"invalid_receipt:{exc}")

    corpus = rules["corpus"]
    threshold = rules["record"]["one_percent_integer_ceiling_exclusive"]
    resources = rules["resources"]

    if receipt.get("evidence_class") != "official-enwik9-local":
        reasons.append("evidence_class_not_official_enwik9_local")
    if receipt.get("input_bytes") != corpus["bytes"]:
        reasons.append("input_size_not_enwik9")
    pinned_sha = corpus.get("sha256")
    if not pinned_sha:
        reasons.append("official_enwik9_sha256_not_pinned")
    elif receipt.get("input_sha256") != pinned_sha:
        reasons.append("input_sha256_not_pinned_enwik9")
    if receipt.get("roundtrip") is not True:
        reasons.append("roundtrip_not_proven")
    total = receipt.get("total_accounted_bytes")
    if not isinstance(total, int) or total >= threshold:
        reasons.append("one_percent_size_threshold_not_met")
    if receipt.get("gpu_used") is not False:
        reasons.append("gpu_prohibition_not_proven")
    if receipt.get("network_used") is not False:
        reasons.append("network_independence_not_proven")
    rss = receipt.get("peak_rss_bytes_linux_interpretation")
    if not isinstance(rss, int) or rss >= resources["max_ram_bytes_exclusive"]:
        reasons.append("ram_limit_not_proven")

    # Official runtime admissibility is machine-relative in the Hutter rules.
    # A local wall-clock number alone cannot prove it, so require a separately
    # recorded rule-machine verification rather than inferring success.
    runtime = receipt.get("official_rule_machine_runtime")
    if not isinstance(runtime, dict) or runtime.get("verified") is not True:
        reasons.append("official_rule_machine_runtime_not_verified")

    # Temp-disk use and program-size packaging need evidence from the final
    # candidate run/package, not an assumption from this Python process.
    temp_disk = receipt.get("temporary_disk_peak_bytes")
    if not isinstance(temp_disk, int) or temp_disk >= resources["max_temp_disk_bytes_exclusive"]:
        reasons.append("temp_disk_limit_not_proven")
    package = receipt.get("program_package_sha256")
    if not isinstance(package, str) or len(package) != 64:
        reasons.append("program_package_not_bound")

    return {
        "schema": "hutter-mixerlab-readiness-v1",
        "status": "READY" if not reasons else "BLOCKED",
        "reasons": sorted(set(reasons)),
        "record_bytes": rules["record"]["current_total_bytes"],
        "one_percent_total_must_be_below": threshold,
        "receipt_sha256": receipt.get("receipt_sha256"),
    }


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args(argv)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    rules = json.loads(args.rules.read_text(encoding="utf-8"))
    result = evaluate(receipt, rules)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(cli())

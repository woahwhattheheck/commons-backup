from __future__ import annotations

import argparse
import json
from copy import deepcopy

from .proof import build_proof, verify_receipt

AS_OF = "2026-09-13T09:15:00Z"
OBSERVED = "2026-09-13T09:00:00Z"


def _sha(seed: str) -> str:
    import hashlib
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _record(i: int, *, side: str, version: int = 1) -> dict:
    return {
        "record_id": f"synthetic-{i:04d}",
        "version": version,
        "observed_at": OBSERVED,
        "fields": {
            "case_id": f"case-{i:04d}",
            "value": i * 10,
            "lineage": f"batch-{i // 25:02d}",
            "side_note": side,
        },
        "evidence_sha256": _sha(f"evidence-{i}"),
    }


def build_fixture() -> tuple[dict, list[dict], list[dict]]:
    spec = {
        "schema": "reconciliation-proof/v1",
        "profile": "synthetic-300",
        "required_fields": ["case_id", "value", "lineage"],
        "ignored_fields": ["side_note"],
        "require_evidence_identity": True,
        "require_version_identity": True,
        "max_records_per_side": 500,
    }
    left = [_record(i, side="left") for i in range(300)]
    right = [_record(i, side="right") for i in range(300)]

    # 240 clean records: 0..239.
    # 10 field mismatch: 240..249.
    for i in range(240, 250):
        right[i]["fields"]["value"] += 1

    # 10 missing left: 250..259; 10 missing right: 260..269.
    left = [r for r in left if not 250 <= int(r["record_id"].split("-")[-1]) < 260]
    right = [r for r in right if not 260 <= int(r["record_id"].split("-")[-1]) < 270]

    # 10 version mismatch: 270..279.
    for row in right:
        i = int(row["record_id"].split("-")[-1])
        if 270 <= i < 280:
            row["version"] = 2

    # 10 evidence mismatch: 280..289.
    for row in right:
        i = int(row["record_id"].split("-")[-1])
        if 280 <= i < 290:
            row["evidence_sha256"] = _sha(f"different-evidence-{i}")

    # 10 same-version conflicts on left: 290..299.
    additions = []
    for row in left:
        i = int(row["record_id"].split("-")[-1])
        if 290 <= i < 300:
            conflict = deepcopy(row)
            conflict["fields"]["value"] += 99
            additions.append(conflict)
    left.extend(additions)

    # Five byte-identical replay inputs per side prove retry collapse without
    # changing the 300 record-key outcome population.
    left.extend(deepcopy(left[i]) for i in range(5))
    right.extend(deepcopy(right[i]) for i in range(5))
    return spec, left, right


def run_acceptance() -> dict:
    spec, left, right = build_fixture()
    receipt = build_proof(spec, left, right, as_of=AS_OF)
    verify_receipt(receipt)
    expected_reasons = {
        "FIELD_MISMATCH": 10,
        "MISSING_LEFT": 10,
        "MISSING_RIGHT": 10,
        "VERSION_MISMATCH": 10,
        "EVIDENCE_MISMATCH": 10,
        "LEFT_VERSION_CONFLICT": 10,
    }
    actual = {key: 0 for key in expected_reasons}
    for row in receipt["outcomes"]:
        for reason in row["reasons"]:
            if reason in actual:
                actual[reason] += 1
    counts = receipt["counts"]
    checks = {
        "record_keys": counts["record_keys"] == 300,
        "matched": counts["matched"] == 240,
        "missing_left": counts["missing_left"] == 10,
        "missing_right": counts["missing_right"] == 10,
        "conflicted": counts["conflicted"] == 10,
        "mismatched": counts["mismatched"] == 50,
        "left_exact_replays": counts["left_exact_replays"] == 5,
        "left_conflicting_inputs": counts["left_conflicting_inputs"] == 10,
        "right_exact_replays": counts["right_exact_replays"] == 5,
        "reason_distribution": actual == expected_reasons,
        "status": receipt["status"] == "HOLD",
        "receipt_valid": verify_receipt(receipt),
    }
    return {
        "schema": "reconciliation-proof-acceptance/v1",
        "passed": all(checks.values()),
        "checks": checks,
        "counts": counts,
        "reason_distribution": actual,
        "receipt_sha256": receipt["receipt_sha256"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args(argv)
    result = run_acceptance()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if (result["passed"] or not args.require_pass) else 1


if __name__ == "__main__":
    raise SystemExit(main())

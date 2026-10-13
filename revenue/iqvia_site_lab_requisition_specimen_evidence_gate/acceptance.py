"""Executable acceptance contract for the frozen v2 180-packet fixture."""
from __future__ import annotations

import hashlib

from .fixtures import expected_holds, frozen_packets
from .gate import (
    CODES,
    STATUS_HOLD,
    STATUS_READY,
    evaluate_batch,
    output_manifest,
    render_csv,
    render_json,
    verify_report,
)


def run_acceptance() -> dict[str, object]:
    packets = frozen_packets()
    report_a = evaluate_batch(packets)
    report_b = evaluate_batch(frozen_packets())
    json_a, json_b = render_json(report_a), render_json(report_b)
    csv_a, csv_b = render_csv(report_a), render_csv(report_b)

    if report_a["packet_count"] != 180:
        raise AssertionError("acceptance requires exactly 180 packets")
    if report_a["status_counts"] != {STATUS_READY: 145, STATUS_HOLD: 35}:
        raise AssertionError("acceptance requires 145 evidence-consistent / 35 hold")
    if report_a["reason_counts"] != {code: 5 for code in CODES}:
        raise AssertionError("acceptance requires exactly five holds per reason family")
    if json_a != json_b or csv_a != csv_b:
        raise AssertionError("acceptance outputs must be byte-identical on rerun")
    if not verify_report(frozen_packets(), report_a):
        raise AssertionError("acceptance report must fully recompile")

    rows = {row["packet_id"]: row for row in report_a["results"]}
    expected = expected_holds()
    held_ids = set()
    for code, packet_ids in expected.items():
        for packet_id in packet_ids:
            held_ids.add(packet_id)
            if rows[packet_id]["status"] != STATUS_HOLD:
                raise AssertionError(f"{packet_id} must hold")
            if rows[packet_id]["reason_codes"] != [code]:
                raise AssertionError(f"{packet_id} must emit only {code}")

    for i in range(1, 146):
        row = rows[f"SLR-{i:04d}"]
        if row["status"] != STATUS_READY or row["reason_codes"]:
            raise AssertionError(f"SLR-{i:04d} must be evidence-consistent with no reason code")

    if held_ids != {f"SLR-{i:04d}" for i in range(146, 181)}:
        raise AssertionError("held packet IDs do not match the frozen contract")

    manifest = output_manifest(report_a)
    return {
        "status": "PASS",
        "packets": 180,
        "ready": 145,
        "hold": 35,
        "reason_counts": report_a["reason_counts"],
        "batch_digest": report_a["batch_digest"],
        "json_sha256": hashlib.sha256(json_a).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_a).hexdigest(),
        "manifest": manifest,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_acceptance(), sort_keys=True, indent=2))

"""Deterministic synthetic acceptance fixture for the CrownBio provenance gate."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any, Dict, Iterable, List

from .gate import GateLedger, HOLD, READY, verify_decision, verify_manifest

EXPECTED_HOLD_GROUPS = {
    "MODEL_LINEAGE_MISMATCH": 4,
    "STUDY_LINEAGE_MISMATCH": 4,
    "ASSAY_OUT_OF_DECLARED_SCOPE": 4,
    "ACCREDITATION_SCOPE_STALE": 4,
    "QC_NOT_READY": 4,
    "ARTIFACT_DIGEST_SENTINEL": 4,
}


def make_ready_packet(index: int) -> Dict[str, Any]:
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("index must be a non-negative integer")
    study_id = f"std_demo_{index // 30:02d}"
    model_id = f"mdl_line_{index % 7:02d}"
    passage = 2 + (index % 8)
    return {
        "packet_id": f"pkt_demo_{index:03d}",
        "sponsor_id": "spn_demo",
        "study_id": study_id,
        "model_id": model_id,
        "passage": passage,
        "allowed_passage_min": 1,
        "allowed_passage_max": 12,
        "declared_use": "translational_validation",
        "allowed_uses": ["biomarker_assay", "translational_validation"],
        "site_id": "site_sandiego",
        "assay_id": "ihc_panel",
        "assay_version": "v2.1",
        "accreditation_scope_id": "scp_demo_2026",
        "accreditation_site_id": "site_sandiego",
        "accreditation_assays": {
            "ihc_panel": ["v2.0", "v2.1"],
            "ngs_panel": ["v4.2"],
        },
        "accreditation_valid_through": "2027-12-17",
        "sample_id": f"smp_demo_{index:03d}",
        "custody_study_id": study_id,
        "custody_model_id": model_id,
        "custody_passage": passage,
        "qc_state": "released_for_study",
        "artifact_id": f"art_demo_{index:03d}",
        "artifact_sha256": f"{index + 1:064x}",
        "artifact_study_id": study_id,
        "artifact_model_id": model_id,
        "artifact_passage": passage,
        "recorded_at": "2026-09-13T10:00:00Z",
        "event_id": f"evt_demo_{index:03d}",
    }


def build_fixture() -> List[Dict[str, Any]]:
    packets = [make_ready_packet(i) for i in range(150)]
    for index in range(126, 130):
        packets[index]["artifact_model_id"] = "mdl_wrong"
    for index in range(130, 134):
        packets[index]["artifact_study_id"] = "std_wrong"
    for index in range(134, 138):
        packets[index]["assay_version"] = "v9.9"
    for index in range(138, 142):
        packets[index]["accreditation_valid_through"] = "2026-09-12"
    for index in range(142, 146):
        packets[index]["qc_state"] = "hold_for_review"
    for index in range(146, 150):
        packets[index]["artifact_sha256"] = "0" * 64
    return packets


def run_acceptance() -> Dict[str, Any]:
    packets = build_fixture()
    ledger = GateLedger()
    decisions = [ledger.apply(packet) for packet in packets]

    status_counts = Counter(decision.status for decision in decisions)
    reason_counts: Counter[str] = Counter()
    for decision in decisions:
        reason_counts.update(decision.reasons)

    before_replays = ledger.entry_count
    replay_decisions = [ledger.apply(deepcopy(packet)) for packet in packets[:10]]
    after_replays = ledger.entry_count

    changed = deepcopy(packets[0])
    changed["artifact_sha256"] = "f" * 64
    conflict = ledger.apply(changed)

    manifest = ledger.canonical_manifest()
    checks = {
        "total_exact": len(decisions) == 150,
        "ready_exact": status_counts[READY] == 126,
        "hold_exact": status_counts[HOLD] == 24,
        "hold_groups_exact": dict(sorted(reason_counts.items())) == dict(sorted(EXPECTED_HOLD_GROUPS.items())),
        "decisions_verify": all(verify_decision(decision) for decision in decisions),
        "replay_count_exact": len(replay_decisions) == 10,
        "replays_marked": all(decision.replayed for decision in replay_decisions),
        "replays_collapsed": before_replays == after_replays == 150,
        "changed_event_holds": conflict.status == HOLD and conflict.reasons == ("EVENT_ID_CHANGED_PAYLOAD",),
        "manifest_entry_count": manifest["entry_count"] == 151,
        "manifest_valid": verify_manifest(manifest),
    }
    passed = all(checks.values())
    return {
        "passed": passed,
        "total": len(decisions),
        "study_ready": status_counts[READY],
        "hold": status_counts[HOLD],
        "hold_reasons": dict(sorted(reason_counts.items())),
        "exact_replays": len(replay_decisions),
        "changed_event_conflict": conflict.to_dict(),
        "manifest_digest": manifest["manifest_digest"],
        "checks": checks,
    }


def main() -> int:
    result = run_acceptance()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

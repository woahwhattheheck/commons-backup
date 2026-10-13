#!/usr/bin/env python3
"""ATS asphalt project-spec-to-result control LIMS.

Demand: ats-asphalt-spec-result-lims-01
Buyer: Asphalt Testing Solutions & Engineering / Tanya Nash

Consultation/project intake. Sample/COC custody. Binder, emulsion,
mix, and performance method routing against a controlled specification
revision. Conditioning and calibration evidence. Exception ownership.
Named-human report release.

60 synthetic jobs across four asphalt service classes. 48 valid enter
worklists once. 12 HOLD with exact truth-set codes: MISSING_SPEC,
WRONG_UNIT, INSUFFICIENT_QUANTITY, DUPLICATE_ID, METHOD_REVISION,
EXPIRED_CALIBRATION. Mock instrument file yields one Hamburg OOS and
one binder invalid-review hold. Replay adds zero records. Audit hash
is deterministic.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay simulated/read-only.
No live QC decision, production write, or automatic release.
PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "ats-asphalt-spec-result-lims-01"
SCHEMA = "commons-ats-asphalt-spec-result-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Asphalt Testing Solutions & Engineering / Tanya Nash"
HUMAN_RELEASER = "RELEASER"
FIXTURE_DATE = "2026-08-31"
SERVICE_CLASSES = ("BINDER", "EMULSION", "MIX", "PERFORMANCE")
HOLD_CODES = (
    "MISSING_SPEC",
    "WRONG_UNIT",
    "INSUFFICIENT_QUANTITY",
    "DUPLICATE_ID",
    "METHOD_REVISION",
    "EXPIRED_CALIBRATION",
)
OOS_SAMPLE_ID = "ATS-PERF-01"
INVALID_SAMPLE_ID = "ATS-BIND-01"
GOLDEN_AUDIT_SHA256 = "3c09bd0ca3c6f03194611a5d7aca63f2e80df7e596ef8f7137801a1cdd9bbae9"

CLASS_SPEC: dict[str, dict[str, Any]] = {
    "BINDER": {
        "method": "AASHTO T 315",
        "method_revision": "T315-22",
        "wrong_revision": "T315-16",
        "spec_id": "AASHTO M 320",
        "spec_revision": "M320-23",
        "grade": "PG 76-22",
        "unit": "kPa",
        "wrong_unit": "psi",
        "min_quantity_g": 500,
        "instrument_id": "DSR-TAMPA-01",
        "calibration_due": "2026-12-31",
        "expired_cal": "2025-06-30",
        "conditioning": "AASHTO T 240 RTFO",
        "result_key": "g_star_sin_delta_kpa",
        "in_spec_value": 2.42,
        "spec_min": 2.20,
        "worklist_route": "BINDER_DSR_WORKLIST",
        "report_route": "SIM_BINDER_PG_REPORT",
        "proposal_family": "PG-CONSULT",
    },
    "EMULSION": {
        "method": "AASHTO T 59",
        "method_revision": "T59-22",
        "wrong_revision": "T59-16",
        "spec_id": "AASHTO M 208",
        "spec_revision": "M208-22",
        "grade": "CSS-1h",
        "unit": "percent",
        "wrong_unit": "g_per_ml",
        "min_quantity_g": 3800,
        "instrument_id": "EMUL-OVEN-01",
        "calibration_due": "2026-11-15",
        "expired_cal": "2025-01-01",
        "conditioning": "T59 residue evaporation 163C",
        "result_key": "residue_percent",
        "in_spec_value": 63.4,
        "spec_min": 57.0,
        "worklist_route": "EMULSION_RESIDUE_WORKLIST",
        "report_route": "SIM_EMULSION_REPORT",
        "proposal_family": "EMUL-QC",
    },
    "MIX": {
        "method": "AASHTO T 308",
        "method_revision": "T308-22",
        "wrong_revision": "T308-10",
        "spec_id": "FDOT 334",
        "spec_revision": "334-23",
        "grade": "SP-12.5",
        "unit": "percent",
        "wrong_unit": "lb_per_ton",
        "min_quantity_g": 25000,
        "instrument_id": "IGN-OVEN-01",
        "calibration_due": "2026-10-01",
        "expired_cal": "2025-03-01",
        "conditioning": "ignition CF-SP12.5",
        "result_key": "ac_percent",
        "in_spec_value": 5.20,
        "spec_min": 4.80,
        "spec_max": 5.60,
        "worklist_route": "MIX_IGNITION_WORKLIST",
        "report_route": "SIM_MIX_DESIGN_REPORT",
        "proposal_family": "SP-MIX",
    },
    "PERFORMANCE": {
        "method": "AASHTO T 324",
        "method_revision": "T324-22",
        "wrong_revision": "T324-14",
        "spec_id": "FDOT 334",
        "spec_revision": "334-23",
        "grade": "SP-12.5 Hamburg 50C",
        "unit": "mm",
        "wrong_unit": "inch",
        "min_quantity_g": 20000,
        "instrument_id": "HWTD-01",
        "calibration_due": "2026-09-30",
        "expired_cal": "2025-02-15",
        "conditioning": "50C water bath 30 min",
        "result_key": "rut_depth_mm_20k",
        "in_spec_value": 8.4,
        "spec_max": 12.5,
        "oos_value": 14.8,
        "worklist_route": "HAMBURG_WORKLIST",
        "report_route": "SIM_HAMBURG_REPORT",
        "proposal_family": "PERF-HWTD",
    },
}

GOLDEN_COUNTS = {
    "input_rows": 60,
    "worklist": 48,
    "hold": 12,
    "in_spec": 46,
    "oos_review_hold": 1,
    "invalid_review_hold": 1,
    "human_releasable": 46,
    "human_released": 46,
    "autonomous_released": 0,
}

PREFIX = {
    "BINDER": "BIND",
    "EMULSION": "EMUL",
    "MIX": "MIX",
    "PERFORMANCE": "PERF",
}
ROW_LETTER = {
    "BINDER": "B",
    "EMULSION": "E",
    "MIX": "M",
    "PERFORMANCE": "P",
}


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def job_id(sample_id: str, project_id: str, method_revision: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "project_id": project_id,
            "method_revision": method_revision,
        }
    )
    return "ATS-" + digest[:12]


def lineage_digest(row: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "sample_id": row.get("sample_id"),
            "project_id": row.get("project_id"),
            "coc_id": row.get("coc_id"),
            "method": row.get("method"),
            "method_revision": row.get("method_revision"),
            "spec_id": row.get("spec_id"),
            "spec_revision": row.get("spec_revision"),
            "service_class": row.get("service_class"),
        }
    )


def _base_row(service_class: str, index: int) -> dict[str, Any]:
    spec = CLASS_SPEC[service_class]
    letter = ROW_LETTER[service_class]
    token = PREFIX[service_class]
    sample_id = f"ATS-{token}-{index:02d}"
    project_id = f"ATS-PRJ-{letter}{index:02d}"
    return {
        "row_id": f"{letter}{index:02d}",
        "service_class": service_class,
        "sample_id": sample_id,
        "project_id": project_id,
        "proposal_id": f"ATS-{spec['proposal_family']}-{index:02d}",
        "coc_id": f"ATS-COC-{letter}{index:02d}",
        "method": spec["method"],
        "method_revision": spec["method_revision"],
        "spec_id": spec["spec_id"],
        "spec_revision": spec["spec_revision"],
        "grade": spec["grade"],
        "unit": spec["unit"],
        "quantity_g": spec["min_quantity_g"],
        "instrument_id": spec["instrument_id"],
        "calibration_due": spec["calibration_due"],
        "conditioning": spec["conditioning"],
        "custody_complete": True,
        "consultation_complete": True,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """60-row PASS fixture for ats-asphalt-spec-result-lims-01.

    Fifteen jobs per asphalt service class. Rows 01-12 of each class are
    valid. Rows 13-15 carry the six exact hold codes, two of each.
    """
    rows: list[dict[str, Any]] = []
    for service_class in SERVICE_CLASSES:
        spec = CLASS_SPEC[service_class]
        for index in range(1, 13):
            rows.append(_base_row(service_class, index))
        defect13 = _base_row(service_class, 13)
        defect14 = _base_row(service_class, 14)
        defect15 = _base_row(service_class, 15)
        if service_class in {"BINDER", "MIX"}:
            defect13["spec_id"] = ""
            defect13["spec_revision"] = ""
            defect14["unit"] = spec["wrong_unit"]
            defect15["quantity_g"] = int(spec["min_quantity_g"] * 0.2)
        else:
            first = _base_row(service_class, 1)
            defect13["sample_id"] = first["sample_id"]
            defect14["method_revision"] = spec["wrong_revision"]
            defect15["calibration_due"] = spec["expired_cal"]
        rows.extend([defect13, defect14, defect15])
    if len(rows) != 60:
        raise RuntimeError("acceptance fixture must be exactly 60 rows, got %s" % len(rows))
    counts = {name: 0 for name in SERVICE_CLASSES}
    for row in rows:
        counts[row["service_class"]] += 1
    if any(count != 15 for count in counts.values()):
        raise RuntimeError("acceptance fixture must be 15 jobs per service class, got %s" % counts)
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "accessions": {},
        "holds": [],
        "events": [],
        "sample_index": {},
        "interface_live": False,
        "qc_decisions": 0,
        "production_writes": 0,
        "billing_writes": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def normalize_intake(row: dict[str, Any]) -> dict[str, Any]:
    service_class = _text(row.get("service_class")).upper()
    return {
        "row_id": _text(row.get("row_id")),
        "service_class": service_class,
        "sample_id": _text(row.get("sample_id")),
        "project_id": _text(row.get("project_id")),
        "proposal_id": _text(row.get("proposal_id")),
        "coc_id": _text(row.get("coc_id")),
        "method": _text(row.get("method")),
        "method_revision": _text(row.get("method_revision")),
        "spec_id": _text(row.get("spec_id")),
        "spec_revision": _text(row.get("spec_revision")),
        "grade": _text(row.get("grade")),
        "unit": _text(row.get("unit")),
        "quantity_g": _number(row.get("quantity_g")),
        "instrument_id": _text(row.get("instrument_id")),
        "calibration_due": _text(row.get("calibration_due")),
        "conditioning": _text(row.get("conditioning")),
        "custody_complete": _flag(row.get("custody_complete")),
        "consultation_complete": _flag(row.get("consultation_complete")),
    }


def classify_intake(norm: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    if norm["service_class"] not in CLASS_SPEC:
        return {"ok": False, "code": "MISSING_SPEC"}
    spec = CLASS_SPEC[norm["service_class"]]
    if norm["sample_id"] and norm["sample_id"] in journal["sample_index"]:
        return {"ok": False, "code": "DUPLICATE_ID"}
    if not norm["spec_id"] or not norm["spec_revision"]:
        return {"ok": False, "code": "MISSING_SPEC"}
    if norm["unit"] != spec["unit"]:
        return {"ok": False, "code": "WRONG_UNIT"}
    if norm["quantity_g"] < float(spec["min_quantity_g"]):
        return {"ok": False, "code": "INSUFFICIENT_QUANTITY"}
    if norm["method"] != spec["method"] or norm["method_revision"] != spec["method_revision"]:
        return {"ok": False, "code": "METHOD_REVISION"}
    if not norm["calibration_due"] or norm["calibration_due"] < FIXTURE_DATE:
        return {"ok": False, "code": "EXPIRED_CALIBRATION"}
    if not norm["sample_id"] or not norm["project_id"] or not norm["coc_id"]:
        return {"ok": False, "code": "MISSING_SPEC"}
    if not norm["custody_complete"] or not norm["consultation_complete"]:
        return {"ok": False, "code": "MISSING_SPEC"}
    return {"ok": True}


def _hold(
    journal: dict[str, Any],
    *,
    row_id: str,
    sample_id: str | None,
    project_id: str | None,
    service_class: str,
    code: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hold = {
        "row_id": row_id,
        "sample_id": sample_id,
        "project_id": project_id,
        "service_class": service_class,
        "code": code,
        "state": "HOLD",
    }
    if extra:
        hold.update(extra)
    fingerprint = sha256_hex(hold)
    existing = {sha256_hex(item) for item in journal["holds"]}
    if fingerprint not in existing:
        journal["holds"].append(hold)
        _event(journal, "HOLD", hold)
    return {"kind": "HOLD", "duplicate": fingerprint in existing, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_intake(row)
    acc_id = None
    if norm["sample_id"] and norm["project_id"] and norm["method_revision"]:
        acc_id = job_id(norm["sample_id"], norm["project_id"], norm["method_revision"])
        if acc_id in journal["accessions"]:
            _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "sample_id": norm["sample_id"]})
            return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "sample_id": norm["sample_id"]}
    verdict = classify_intake(norm, journal)
    if not verdict["ok"]:
        extra = {}
        if verdict["code"] == "DUPLICATE_ID":
            extra["first_accession_id"] = journal["sample_index"].get(norm["sample_id"])
        return _hold(
            journal,
            row_id=norm["row_id"],
            sample_id=norm["sample_id"] or None,
            project_id=norm["project_id"] or None,
            service_class=norm["service_class"],
            code=verdict["code"],
            extra=extra or None,
        )

    spec = CLASS_SPEC[norm["service_class"]]
    if acc_id is None:
        acc_id = job_id(norm["sample_id"], norm["project_id"], norm["method_revision"])

    lineage = {
        "sample_id": norm["sample_id"],
        "project_id": norm["project_id"],
        "proposal_id": norm["proposal_id"],
        "coc_id": norm["coc_id"],
        "service_class": norm["service_class"],
        "method": norm["method"],
        "method_revision": norm["method_revision"],
        "spec_id": norm["spec_id"],
        "spec_revision": norm["spec_revision"],
        "grade": norm["grade"],
        "lineage_sha256": lineage_digest(norm),
    }
    record = {
        "accession_id": acc_id,
        "row_id": norm["row_id"],
        "sample_id": norm["sample_id"],
        "project_id": norm["project_id"],
        "proposal_id": norm["proposal_id"],
        "coc_id": norm["coc_id"],
        "service_class": norm["service_class"],
        "method": norm["method"],
        "method_revision": norm["method_revision"],
        "spec_id": norm["spec_id"],
        "spec_revision": norm["spec_revision"],
        "grade": norm["grade"],
        "unit": norm["unit"],
        "quantity_g": norm["quantity_g"],
        "instrument_id": norm["instrument_id"],
        "calibration_due": norm["calibration_due"],
        "conditioning": norm["conditioning"],
        "route": spec["worklist_route"],
        "state": "WORKLIST",
        "simulated_result": None,
        "result_state": None,
        "review_hold": None,
        "released": False,
        "released_by": None,
        "report_route": None,
        "report_status": "BLOCKED_MISSING_RESULT",
        "interface_state": "SIMULATED",
        "interface_live": False,
        "qc_decision_live": False,
        "lineage": lineage,
        "adapters": {
            "proposal": "SIMULATED_READ_ONLY",
            "coc": "SIMULATED_READ_ONLY",
            "lims": "SIMULATED_READ_ONLY",
            "instrument": "SIMULATED_READ_ONLY",
            "spec": "SIMULATED_READ_ONLY",
            "report": "SIMULATED_READ_ONLY",
        },
    }
    journal["accessions"][acc_id] = record
    journal["sample_index"][norm["sample_id"]] = acc_id
    _event(
        journal,
        "WORKLIST",
        {
            "accession_id": acc_id,
            "sample_id": norm["sample_id"],
            "project_id": norm["project_id"],
            "service_class": norm["service_class"],
            "route": spec["worklist_route"],
            "lineage_sha256": lineage["lineage_sha256"],
        },
    )
    return {"kind": "WORKLIST", "accession_id": acc_id, "route": spec["worklist_route"]}


def _mock_result_for(record: dict[str, Any]) -> dict[str, Any]:
    spec = CLASS_SPEC[record["service_class"]]
    key = spec["result_key"]
    if record["sample_id"] == INVALID_SAMPLE_ID:
        return {
            "disposition": "INVALID",
            "review_hold": "REVIEW_HOLD_INVALID",
            "reason": "MISSING_RTFO_CONDITIONING_EVIDENCE",
            key: None,
            "conditioning_evidence": None,
        }
    if record["sample_id"] == OOS_SAMPLE_ID:
        return {
            "disposition": "OOS",
            "review_hold": "REVIEW_HOLD_OOS",
            "reason": "HAMBURG_RUT_EXCEEDS_334_23",
            key: spec["oos_value"],
            "spec_max_mm": spec["spec_max"],
            "conditioning_evidence": record["conditioning"],
        }
    payload: dict[str, Any] = {
        "disposition": "IN_SPEC",
        "review_hold": None,
        "reason": None,
        key: spec["in_spec_value"],
        "conditioning_evidence": record["conditioning"],
    }
    if "spec_min" in spec:
        payload["spec_min"] = spec["spec_min"]
    if "spec_max" in spec:
        payload["spec_max"] = spec["spec_max"]
    return payload


def import_simulated_result(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record["simulated_result"] is not None:
        return {"ok": True, "duplicate": True, "result": record["simulated_result"]}
    payload = _mock_result_for(record)
    record["simulated_result"] = deepcopy(payload)
    disposition = payload["disposition"]
    if disposition == "INVALID":
        record["result_state"] = "REVIEW_HOLD_INVALID"
        record["review_hold"] = "REVIEW_HOLD_INVALID"
        record["report_status"] = "REVIEW_HOLD_INVALID"
        record["state"] = "HOLD"
    elif disposition == "OOS":
        record["result_state"] = "REVIEW_HOLD_OOS"
        record["review_hold"] = "REVIEW_HOLD_OOS"
        record["report_status"] = "REVIEW_HOLD_OOS"
        record["state"] = "HOLD"
    else:
        record["result_state"] = "IN_SPEC"
        record["review_hold"] = None
        record["report_status"] = "READY_FOR_HUMAN_RELEASE"
        record["state"] = "REVIEW"
    _event(
        journal,
        "SIMULATED_RESULT",
        {
            "accession_id": accession_id_value,
            "sample_id": record["sample_id"],
            "disposition": disposition,
            "review_hold": record["review_hold"],
            "adapter": "SIMULATED_INSTRUMENT",
        },
    )
    return {
        "ok": True,
        "duplicate": False,
        "disposition": disposition,
        "report_status": record["report_status"],
    }


def release_report(
    journal: dict[str, Any],
    accession_id_value: str,
    *,
    actor_role: str,
    actor: str,
    acknowledge_oos: bool = False,
) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    role = _text(actor_role).upper()
    if role != HUMAN_RELEASER:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "actor_role": role or None,
            },
        )
        return {
            "ok": False,
            "code": "AUTONOMOUS_RELEASE_DENIED",
            "report_status": record["report_status"],
        }
    if record["review_hold"] == "REVIEW_HOLD_INVALID":
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "REVIEW_HOLD_INVALID",
                "report_status": "REVIEW_HOLD_INVALID",
            },
        )
        return {"ok": False, "code": "REVIEW_HOLD_INVALID", "report_status": "REVIEW_HOLD_INVALID"}
    if record["review_hold"] == "REVIEW_HOLD_OOS" and not acknowledge_oos:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "REVIEW_HOLD_OOS",
                "report_status": "REVIEW_HOLD_OOS",
            },
        )
        return {"ok": False, "code": "REVIEW_HOLD_OOS", "report_status": "REVIEW_HOLD_OOS"}
    if record["report_status"] != "READY_FOR_HUMAN_RELEASE" and not record["released"] and not (
        record["review_hold"] == "REVIEW_HOLD_OOS" and acknowledge_oos
    ):
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "REPORT_BLOCKED",
                "report_status": record["report_status"],
            },
        )
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": record["report_status"]}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    spec = CLASS_SPEC[record["service_class"]]
    route = spec["report_route"]
    record["released"] = True
    record["released_by"] = _text(actor) or "human-releaser"
    record["report_status"] = "RELEASED"
    record["report_route"] = route
    record["state"] = "RELEASED"
    record["lineage"]["report_route"] = route
    _event(
        journal,
        "RELEASED",
        {
            "accession_id": accession_id_value,
            "released_by": record["released_by"],
            "report_route": route,
            "adapter": "SIMULATED_REPORT",
        },
    )
    return {"ok": True, "duplicate": False, "report_status": "RELEASED", "report_route": route}


def apply_simulated_file(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [import_simulated_result(journal, acc_id) for acc_id in sorted(journal["accessions"])]


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in sorted(journal["accessions"])
    ]


def authorized_human_release(journal: dict[str, Any], actor: str = "tanya-nash-reviewer") -> list[dict[str, Any]]:
    return [
        release_report(journal, acc_id, actor_role=HUMAN_RELEASER, actor=actor)
        for acc_id in sorted(journal["accessions"])
    ]


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before = set(journal["accessions"])
    before_holds = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["accessions"]) - before
    return {
        "added_accessions": sorted(added),
        "added_accession_count": len(added),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
    }


def _count_state(journal: dict[str, Any], inbound_len: int) -> dict[str, int]:
    accessioned = list(journal["accessions"].values())
    in_spec = sum(1 for item in accessioned if item.get("result_state") == "IN_SPEC")
    oos = sum(1 for item in accessioned if item.get("review_hold") == "REVIEW_HOLD_OOS")
    invalid = sum(1 for item in accessioned if item.get("review_hold") == "REVIEW_HOLD_INVALID")
    released = sum(1 for item in accessioned if item.get("released"))
    return {
        "input_rows": inbound_len,
        "worklist": len(accessioned),
        "hold": len(journal["holds"]),
        "in_spec": in_spec,
        "oos_review_hold": oos,
        "invalid_review_hold": invalid,
        "human_releasable": in_spec,
        "human_released": released,
        "autonomous_released": 0,
    }


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    accessions = sorted(
        journal["accessions"].values(),
        key=lambda item: (item["service_class"], item["sample_id"]),
    )
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "counts": counts,
        "holds": deepcopy(journal["holds"]),
        "accessions": [
            {
                "accession_id": item["accession_id"],
                "sample_id": item["sample_id"],
                "project_id": item["project_id"],
                "coc_id": item["coc_id"],
                "service_class": item["service_class"],
                "method": item["method"],
                "method_revision": item["method_revision"],
                "spec_id": item["spec_id"],
                "spec_revision": item["spec_revision"],
                "route": item["route"],
                "state": item["state"],
                "result_state": item["result_state"],
                "review_hold": item["review_hold"],
                "released": item["released"],
                "report_route": item["report_route"],
                "lineage_sha256": item["lineage"]["lineage_sha256"],
            }
            for item in accessions
        ],
        "events": deepcopy(journal["events"]),
        "adapters": {
            "proposal": "SIMULATED_READ_ONLY",
            "coc": "SIMULATED_READ_ONLY",
            "lims": "SIMULATED_READ_ONLY",
            "instrument": "SIMULATED_READ_ONLY",
            "spec": "SIMULATED_READ_ONLY",
            "report": "SIMULATED_READ_ONLY",
            "qc_decision": "NOT_WRITTEN",
            "production_write": "NOT_SENT",
        },
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    result_effects = apply_simulated_file(journal)
    autonomous = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)

    accessioned = sorted(
        journal["accessions"].values(),
        key=lambda item: (item["service_class"], item["sample_id"]),
    )
    hold_codes = sorted(item["code"] for item in journal["holds"])
    counts = _count_state(journal, len(inbound))
    routes = {item["sample_id"]: item["route"] for item in accessioned}
    lineage = {item["sample_id"]: item["lineage"]["lineage_sha256"] for item in accessioned}
    class_counts = {name: 0 for name in SERVICE_CLASSES}
    for item in accessioned:
        class_counts[item["service_class"]] += 1
    hold_class_counts = {name: 0 for name in SERVICE_CLASSES}
    for item in journal["holds"]:
        if item["service_class"] in hold_class_counts:
            hold_class_counts[item["service_class"]] += 1
    audit = _audit_payload(journal, counts)
    audit_sha256 = sha256_hex(audit)

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": counts["input_rows"],
        "worklist": counts["worklist"],
        "hold": counts["hold"],
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "in_spec": counts["in_spec"],
        "oos_review_hold": counts["oos_review_hold"],
        "invalid_review_hold": counts["invalid_review_hold"],
        "human_releasable": counts["human_releasable"],
        "human_released": counts["human_released"],
        "autonomous_released": 0,
        "class_worklist": class_counts,
        "class_holds": hold_class_counts,
        "routes": routes,
        "lineage": lineage,
        "accession_ids": [item["accession_id"] for item in accessioned],
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "result_effects": result_effects,
        "autonomous_release_effects": autonomous,
        "human_release_effects": human,
        "accessions": accessioned,
        "holds": deepcopy(journal["holds"]),
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "qc_decisions": 0,
        "production_writes": 0,
        "billing_writes": 0,
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "audit": audit,
        "audit_sha256": audit_sha256,
    }
    body["manifest_sha256"] = sha256_hex(
        {
            key: value
            for key, value in body.items()
            if key
            not in {
                "manifest_sha256",
                "effects",
                "result_effects",
                "autonomous_release_effects",
                "human_release_effects",
                "accessions",
                "events",
            }
        }
    )
    return body


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {key: result.get(key) for key in GOLDEN_COUNTS}
    return {
        "expected": dict(GOLDEN_COUNTS),
        "actual": actual,
        "match": actual == GOLDEN_COUNTS,
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    for key, expected in GOLDEN_COUNTS.items():
        if result.get(key) != expected:
            failures.append(f"{key}!={expected} actual={result.get(key)}")
    if result.get("hold_code_set") != sorted(HOLD_CODES):
        failures.append("hold_code_set")
    if result.get("class_worklist") != {name: 12 for name in SERVICE_CLASSES}:
        failures.append("class_worklist")
    if result.get("class_holds") != {name: 3 for name in SERVICE_CLASSES}:
        failures.append("class_holds")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if result.get("qc_decisions") != 0:
        failures.append("qc_decisions")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    oos = next((item for item in result.get("accessions") or [] if item.get("sample_id") == OOS_SAMPLE_ID), None)
    invalid = next((item for item in result.get("accessions") or [] if item.get("sample_id") == INVALID_SAMPLE_ID), None)
    if oos is None or oos.get("review_hold") != "REVIEW_HOLD_OOS" or oos.get("released"):
        failures.append("oos_not_held")
    if invalid is None or invalid.get("review_hold") != "REVIEW_HOLD_INVALID" or invalid.get("released"):
        failures.append("invalid_not_held")
    if len(set(result.get("accession_ids") or [])) != 48:
        failures.append("accession_ids_not_unique")
    if len(set((result.get("lineage") or {}).values())) != 48:
        failures.append("lineage_not_unique")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if sha256_hex(first["audit"]) != first.get("audit_sha256"):
        failures.append("audit_hash_not_self")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "audit_sha256": first.get("audit_sha256"),
        "expected": GOLDEN_COUNTS,
        "actual": expected_actual(first)["actual"],
        "hold_code_set": first.get("hold_code_set"),
        "class_worklist": first.get("class_worklist"),
        "replay_added_accessions": replay.get("added_accession_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

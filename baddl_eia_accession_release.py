#!/usr/bin/env python3
"""Florida BADDL EIA accession + human-release LIMS.

Demand: baddl-eia-accession-release-lims-01
Buyer: Florida BADDL / Y. Reddy Bommineni

VS 10-11 / VSPS / GVL intake normalization. Exact sample-ID
reconciliation. Signature and completeness gates. Simulated analyzer
results. Named human release. Report routing, provenance, audit export.

24 synthetic fixtures: eight paper VS 10-11, eight VSPS, eight GVL.
One unsigned paper form and one duplicate tube ID stay HOLD.
Exactly 22 enter the EIA worklist. Simulated file: 19 negative,
two positive, one invalid. Authorized human releases 21; invalid
remains HOLD.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay simulated.
No PHI, live animal status, regulatory submission, billing, or
automatic result release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "baddl-eia-accession-release-lims-01"
SCHEMA = "commons-baddl-eia-accession-release-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Florida BADDL / Y. Reddy Bommineni"
HUMAN_RELEASER = "RELEASER"
ASSAY = "EIA"
WORKLIST_ROUTE = "EIA_WORKLIST"
SOURCES = ("PAPER_VS1011", "VSPS", "GVL")
CURRENT_PAPER_VERSION = "VS10-11-CURRENT"
REPORT_ROUTES = {
    "PAPER_VS1011": "SIM_PAPER_REPORT",
    "VSPS": "SIM_VSPS_PORTAL",
    "GVL": "SIM_GVL_PORTAL",
}
SIMULATED_RESULTS = {
    "SYN-EIA-G05": "POSITIVE",
    "SYN-EIA-G06": "POSITIVE",
    "SYN-EIA-G07": "INVALID",
}
HOLD_INTAKE = ("HOLD_UNSIGNED_FORM", "HOLD_DUPLICATE_TUBE_ID")
GOLDEN_AUDIT_SHA256 = "1849cde855a07b5eef7c389e36c3896bd257161d6d6970292ad17509b55cd204"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def accession_id(sample_id: str, tube_id: str, source: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "source": source,
            "tube_id": tube_id,
        }
    )
    return "BADDL-EIA-" + digest[:12]


def _row(
    row_id: str,
    source: str,
    index: int,
    *,
    signature_present: bool = True,
    tube_id: str | None = None,
    sample_id: str | None = None,
) -> dict[str, Any]:
    prefix = {"PAPER_VS1011": "P", "VSPS": "V", "GVL": "G"}[source]
    token = f"SYN-EIA-{prefix}{index:02d}"
    form_version = CURRENT_PAPER_VERSION if source == "PAPER_VS1011" else f"{source}-CURRENT"
    return {
        "row_id": row_id,
        "source": source,
        "form_version": form_version,
        "form_id": f"SYN-FORM-{prefix}{index:02d}",
        "sample_id": token if sample_id is None else sample_id,
        "tube_id": token if tube_id is None else tube_id,
        "owner_ref": f"SYN-OWN-{prefix}{index:02d}",
        "animal_ref": f"SYN-EQ-{prefix}{index:02d}",
        "species": "equine",
        "vet_ref": f"SYN-VET-{prefix}{index:02d}",
        "vet_accredited": True,
        "signature_present": signature_present,
        "complete": True,
        "assay": ASSAY,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """24-row PASS fixture for baddl-eia-accession-release-lims-01.

    Eight paper VS 10-11, eight VSPS, eight GVL. P08 is unsigned paper.
    G08 reuses G07's tube ID. Remaining 22 enter the EIA worklist.
    """
    rows: list[dict[str, Any]] = []
    for i in range(1, 9):
        rows.append(_row(f"P{i:02d}", "PAPER_VS1011", i, signature_present=(i != 8)))
    for i in range(1, 9):
        rows.append(_row(f"V{i:02d}", "VSPS", i))
    for i in range(1, 9):
        if i == 8:
            rows.append(
                _row(
                    "G08",
                    "GVL",
                    8,
                    tube_id="SYN-EIA-G07",
                    sample_id="SYN-EIA-G08",
                )
            )
        else:
            rows.append(_row(f"G{i:02d}", "GVL", i))
    if len(rows) != 24:
        raise RuntimeError("acceptance fixture must be exactly 24 rows, got %s" % len(rows))
    sources = [row["source"] for row in rows]
    if sources.count("PAPER_VS1011") != 8 or sources.count("VSPS") != 8 or sources.count("GVL") != 8:
        raise RuntimeError("acceptance fixture source split must be 8/8/8")
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "accessions": {},
        "holds": [],
        "events": [],
        "tube_index": {},
        "interface_live": False,
        "animal_status_writes": 0,
        "regulatory_submits": 0,
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
    source = _text(row.get("source")).upper()
    sample_id = _text(row.get("sample_id"))
    tube_id = _text(row.get("tube_id"))
    form_id = _text(row.get("form_id"))
    form_version = _text(row.get("form_version"))
    vet_ref = _text(row.get("vet_ref"))
    signature_present = _flag(row.get("signature_present"))
    complete = _flag(row.get("complete"))
    vet_accredited = _flag(row.get("vet_accredited"))
    return {
        "row_id": _text(row.get("row_id")),
        "source": source,
        "form_version": form_version,
        "form_id": form_id,
        "sample_id": sample_id,
        "tube_id": tube_id,
        "owner_ref": _text(row.get("owner_ref")),
        "animal_ref": _text(row.get("animal_ref")),
        "species": _text(row.get("species")) or "equine",
        "vet_ref": vet_ref,
        "vet_accredited": vet_accredited,
        "signature_present": signature_present,
        "complete": complete,
        "assay": _text(row.get("assay")) or ASSAY,
        "sample_tube_match": bool(sample_id) and sample_id == tube_id,
    }


def classify_intake(norm: dict[str, Any]) -> dict[str, Any]:
    if norm["source"] not in SOURCES:
        return {"ok": False, "code": "HOLD_UNKNOWN_SOURCE"}
    if not norm["sample_id"] or not norm["tube_id"] or not norm["form_id"] or not norm["form_version"]:
        return {"ok": False, "code": "HOLD_INCOMPLETE"}
    if not norm["complete"] or not norm["vet_ref"] or not norm["vet_accredited"]:
        return {"ok": False, "code": "HOLD_INCOMPLETE"}
    if norm["source"] == "PAPER_VS1011" and not norm["signature_present"]:
        return {"ok": False, "code": "HOLD_UNSIGNED_FORM"}
    if not norm["sample_tube_match"]:
        return {"ok": False, "code": "HOLD_SAMPLE_TUBE_MISMATCH"}
    return {"ok": True}


def _hold(
    journal: dict[str, Any],
    *,
    row_id: str,
    sample_id: str | None,
    tube_id: str | None,
    source: str,
    code: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hold = {
        "row_id": row_id,
        "sample_id": sample_id,
        "tube_id": tube_id,
        "source": source,
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
    verdict = classify_intake(norm)
    if not verdict["ok"] and verdict["code"] != "HOLD_SAMPLE_TUBE_MISMATCH":
        return _hold(
            journal,
            row_id=norm["row_id"],
            sample_id=norm["sample_id"] or None,
            tube_id=norm["tube_id"] or None,
            source=norm["source"],
            code=verdict["code"],
        )

    acc_id = accession_id(norm["sample_id"], norm["tube_id"], norm["source"])
    if acc_id in journal["accessions"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "sample_id": norm["sample_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "sample_id": norm["sample_id"]}

    if norm["tube_id"] and norm["tube_id"] in journal["tube_index"]:
        return _hold(
            journal,
            row_id=norm["row_id"],
            sample_id=norm["sample_id"],
            tube_id=norm["tube_id"],
            source=norm["source"],
            code="HOLD_DUPLICATE_TUBE_ID",
            extra={"first_accession_id": journal["tube_index"][norm["tube_id"]]},
        )

    if not verdict["ok"]:
        return _hold(
            journal,
            row_id=norm["row_id"],
            sample_id=norm["sample_id"] or None,
            tube_id=norm["tube_id"] or None,
            source=norm["source"],
            code=verdict["code"],
        )

    record = {
        "accession_id": acc_id,
        "row_id": norm["row_id"],
        "sample_id": norm["sample_id"],
        "tube_id": norm["tube_id"],
        "source": norm["source"],
        "form_id": norm["form_id"],
        "form_version": norm["form_version"],
        "owner_ref": norm["owner_ref"],
        "animal_ref": norm["animal_ref"],
        "species": norm["species"],
        "vet_ref": norm["vet_ref"],
        "vet_accredited": True,
        "signature_present": norm["signature_present"],
        "assay": ASSAY,
        "route": WORKLIST_ROUTE,
        "state": "WORKLIST",
        "simulated_result": None,
        "result_state": None,
        "released": False,
        "released_by": None,
        "report_route": None,
        "report_status": "BLOCKED_MISSING_RESULT",
        "interface_state": "SIMULATED",
        "interface_live": False,
        "animal_status": None,
        "regulatory_submitted": False,
        "billed": False,
        "provenance": {
            "source": norm["source"],
            "form_id": norm["form_id"],
            "sample_id": norm["sample_id"],
            "tube_id": norm["tube_id"],
            "accession_id": acc_id,
            "worklist_id": acc_id,
            "result_id": None,
            "report_route": None,
        },
    }
    journal["accessions"][acc_id] = record
    journal["tube_index"][norm["tube_id"]] = acc_id
    _event(
        journal,
        "WORKLIST",
        {
            "accession_id": acc_id,
            "sample_id": norm["sample_id"],
            "tube_id": norm["tube_id"],
            "source": norm["source"],
            "route": WORKLIST_ROUTE,
        },
    )
    return {"kind": "WORKLIST", "accession_id": acc_id, "route": WORKLIST_ROUTE}


def import_simulated_result(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record["simulated_result"] is not None:
        return {"ok": True, "duplicate": True, "result": record["simulated_result"]}
    result = SIMULATED_RESULTS.get(record["sample_id"], "NEGATIVE")
    record["simulated_result"] = result
    record["provenance"]["result_id"] = f"{accession_id_value}:{result}"
    if result == "INVALID":
        record["result_state"] = "HOLD_INVALID_RESULT"
        record["report_status"] = "HOLD_INVALID_RESULT"
        record["state"] = "HOLD"
    else:
        record["result_state"] = result
        record["report_status"] = "READY_FOR_HUMAN_RELEASE"
        record["state"] = "REVIEW"
    _event(
        journal,
        "SIMULATED_RESULT",
        {
            "accession_id": accession_id_value,
            "sample_id": record["sample_id"],
            "result": result,
            "adapter": "SIMULATED_ANALYZER",
        },
    )
    return {"ok": True, "duplicate": False, "result": result, "report_status": record["report_status"]}


def release_report(
    journal: dict[str, Any],
    accession_id_value: str,
    *,
    actor_role: str,
    actor: str,
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
    if record["simulated_result"] == "INVALID":
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "HOLD_INVALID_RESULT",
                "report_status": "HOLD_INVALID_RESULT",
            },
        )
        return {"ok": False, "code": "HOLD_INVALID_RESULT", "report_status": "HOLD_INVALID_RESULT"}
    if record["report_status"] != "READY_FOR_HUMAN_RELEASE" and not record["released"]:
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
    route = REPORT_ROUTES[record["source"]]
    record["released"] = True
    record["released_by"] = _text(actor) or "human-releaser"
    record["report_status"] = "RELEASED"
    record["report_route"] = route
    record["state"] = "RELEASED"
    record["provenance"]["report_route"] = route
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
    effects = []
    for acc_id in sorted(journal["accessions"]):
        effects.append(import_simulated_result(journal, acc_id))
    return effects


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in sorted(journal["accessions"])
    ]


def authorized_human_release(journal: dict[str, Any], actor: str = "releaser-1") -> list[dict[str, Any]]:
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


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    accessions = sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
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
                "tube_id": item["tube_id"],
                "source": item["source"],
                "route": item["route"],
                "state": item["state"],
                "simulated_result": item["simulated_result"],
                "released": item["released"],
                "report_route": item["report_route"],
                "provenance": item["provenance"],
            }
            for item in accessions
        ],
        "events": deepcopy(journal["events"]),
        "adapters": {
            "analyzer": "SIMULATED",
            "vsps_portal": "SIMULATED",
            "gvl_portal": "SIMULATED",
            "agency": "SIMULATED",
            "billing": "SIMULATED_NO_WRITE",
            "animal_status": "NOT_WRITTEN",
            "regulatory_submit": "NOT_SENT",
        },
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    result_effects = apply_simulated_file(journal)
    autonomous = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)

    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
    hold_codes = sorted(item["code"] for item in journal["holds"])
    result_counts = {"NEGATIVE": 0, "POSITIVE": 0, "INVALID": 0}
    for item in accessioned:
        if item["simulated_result"] in result_counts:
            result_counts[item["simulated_result"]] += 1
    released = [item for item in accessioned if item["released"]]
    invalid_holds = [
        item for item in accessioned if item["simulated_result"] == "INVALID" and not item["released"]
    ]
    routes = {item["sample_id"]: item["route"] for item in accessioned}
    report_routes = {item["sample_id"]: item["report_route"] for item in released}

    counts = {
        "input_rows": len(inbound),
        "worklist": len(accessioned),
        "hold": len(journal["holds"]),
        "negative": result_counts["NEGATIVE"],
        "positive": result_counts["POSITIVE"],
        "invalid": result_counts["INVALID"],
        "human_releasable": result_counts["NEGATIVE"] + result_counts["POSITIVE"],
        "human_released": len(released),
        "invalid_hold": len(invalid_holds),
        "autonomous_released": 0,
    }
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
        "negative": counts["negative"],
        "positive": counts["positive"],
        "invalid": counts["invalid"],
        "human_releasable": counts["human_releasable"],
        "human_released": counts["human_released"],
        "invalid_hold": counts["invalid_hold"],
        "autonomous_released": 0,
        "routes": routes,
        "report_routes": report_routes,
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
        "animal_status_writes": 0,
        "regulatory_submits": 0,
        "billing_writes": 0,
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "audit": audit,
        "audit_sha256": audit_sha256,
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key not in {"manifest_sha256", "effects", "result_effects", "autonomous_release_effects", "human_release_effects", "accessions", "events"}}
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    expected = {
        "input_rows": 24,
        "worklist": 22,
        "hold": 2,
        "negative": 19,
        "positive": 2,
        "invalid": 1,
        "human_releasable": 21,
        "human_released": 21,
        "invalid_hold": 1,
        "autonomous_released": 0,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            failures.append(f"{key}!={value} actual={result.get(key)}")
    if result.get("hold_codes") != ["HOLD_DUPLICATE_TUBE_ID", "HOLD_UNSIGNED_FORM"]:
        failures.append("hold_codes")
    if len(set(result.get("accession_ids") or [])) != 22:
        failures.append("accession_ids_not_unique")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("animal_status_writes") != 0:
        failures.append("animal_status_writes")
    if result.get("regulatory_submits") != 0:
        failures.append("regulatory_submits")
    if result.get("billing_writes") != 0:
        failures.append("billing_writes")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    if any(item.get("animal_status") for item in result.get("accessions") or []):
        failures.append("animal_status_present")
    if any(item.get("regulatory_submitted") for item in result.get("accessions") or []):
        failures.append("regulatory_submitted")
    if any(item.get("billed") for item in result.get("accessions") or []):
        failures.append("billed")
    unsigned = next((item for item in result.get("holds") or [] if item.get("code") == "HOLD_UNSIGNED_FORM"), None)
    duplicate = next((item for item in result.get("holds") or [] if item.get("code") == "HOLD_DUPLICATE_TUBE_ID"), None)
    if unsigned is None or unsigned.get("row_id") != "P08" or unsigned.get("source") != "PAPER_VS1011":
        failures.append("unsigned_paper")
    if duplicate is None or duplicate.get("row_id") != "G08" or duplicate.get("tube_id") != "SYN-EIA-G07":
        failures.append("duplicate_tube")
    invalid = next((item for item in result.get("accessions") or [] if item.get("sample_id") == "SYN-EIA-G07"), None)
    if invalid is None or invalid.get("released") or invalid.get("simulated_result") != "INVALID":
        failures.append("invalid_not_held")
    positives = [item["sample_id"] for item in result.get("accessions") or [] if item.get("simulated_result") == "POSITIVE"]
    if sorted(positives) != ["SYN-EIA-G05", "SYN-EIA-G06"]:
        failures.append("positives")
    if not all(item.get("route") == WORKLIST_ROUTE for item in result.get("accessions") or []):
        failures.append("routes")
    expected_reports = {
        item["sample_id"]: REPORT_ROUTES[item["source"]]
        for item in result.get("accessions") or []
        if item.get("released")
    }
    if result.get("report_routes") != expected_reports:
        failures.append("report_routes")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "input_rows",
        "worklist",
        "hold",
        "negative",
        "positive",
        "invalid",
        "human_releasable",
        "human_released",
        "invalid_hold",
        "autonomous_released",
    )
    expected = {
        "input_rows": 24,
        "worklist": 22,
        "hold": 2,
        "negative": 19,
        "positive": 2,
        "invalid": 1,
        "human_releasable": 21,
        "human_released": 21,
        "invalid_hold": 1,
        "autonomous_released": 0,
    }
    actual = {key: result.get(key) for key in keys}
    return {"expected": expected, "actual": actual, "match": expected == actual}


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if sha256_hex(first["audit"]) != sha256_hex(second["audit"]):
        failures.append("audit_replay_mismatch")
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "command": "python3 baddl_eia_accession_release.py",
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "hold_codes": first.get("hold_codes"),
        "audit_sha256": first.get("audit_sha256"),
        "manifest_sha256": first.get("manifest_sha256"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "truth_gate": TRUTH_GATE,
        "interfaces": "SIMULATED",
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

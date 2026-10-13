#!/usr/bin/env python3
"""Kincell Bio RTP commercial QC-release LIMS bridge.

Demand: kincell-rtp-qc-release-bridge-lims-01
Buyer pairing: Kincell Bio RTP / Melodie Bryce

Exact posted fixture only. 300 synthetic samples from 30 batches.
30 seeded exceptions. Simulated Veeva QMS + ERP payloads.
Named QA must act before release. No automatic release.

Simulated / de-identified only. No live QMS/ERP/LIMS. No PHI.
No production writes. cash_usd=0. HOLD / BUILD-AND-VERIFY.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PACK = Path(__file__).resolve().parent
FIXTURE_PATH = PACK / "fixture.json"

DEMAND_ID = "kincell-rtp-qc-release-bridge-lims-01"
SCHEMA = "commons-kincell-rtp-qc-release-bridge-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Kincell Bio RTP / Melodie Bryce"
SITE = "RTP"
NAMED_QA_ROLE = "NAMED_QA"
NAMED_QA_ACTOR = "qa-named-1"
COMMAND = "python3 revenue/kincell_rtp_qc_release_bridge/runner.py"

SAMPLE_SLOTS = (
    {"slot": 1, "plan": "IN_PROCESS", "lab": "QC", "assay": "POTENCY"},
    {"slot": 2, "plan": "IN_PROCESS", "lab": "QC", "assay": "VIABILITY"},
    {"slot": 3, "plan": "IN_PROCESS", "lab": "QC", "assay": "IDENTITY"},
    {"slot": 4, "plan": "IN_PROCESS", "lab": "QC", "assay": "ENDOTOXIN"},
    {"slot": 5, "plan": "FINAL", "lab": "QC", "assay": "VECTOR_COPY"},
    {"slot": 6, "plan": "FINAL", "lab": "MICROBIOLOGY", "assay": "RAPID_STERILITY"},
    {"slot": 7, "plan": "FINAL", "lab": "MICROBIOLOGY", "assay": "MYCOPLASMA"},
    {"slot": 8, "plan": "STABILITY", "lab": "STABILITY", "assay": "STABILITY_ASSAY"},
    {"slot": 9, "plan": "STABILITY", "lab": "STABILITY", "assay": "STABILITY_ASSAY"},
    {"slot": 10, "plan": "STABILITY", "lab": "QC", "assay": "APPEARANCE"},
)

SPECS = {
    "POTENCY": {"lo": 80.0, "hi": 120.0, "unit": "pct", "clean": 100.0, "fail": 64.0},
    "VIABILITY": {"lo": 70.0, "hi": 100.0, "unit": "pct", "clean": 88.0, "fail": 52.0},
    "IDENTITY": {"lo": 1.0, "hi": 1.0, "unit": "match", "clean": 1.0, "fail": 0.0},
    "ENDOTOXIN": {"lo": 0.0, "hi": 5.0, "unit": "EU_per_mL", "clean": 1.25, "fail": 9.5},
    "VECTOR_COPY": {"lo": 1.0, "hi": 5.0, "unit": "copies", "clean": 3.0, "fail": 8.0},
    "RAPID_STERILITY": {"lo": 0.0, "hi": 0.0, "unit": "growth", "clean": 0.0, "fail": 1.0},
    "MYCOPLASMA": {"lo": 0.0, "hi": 0.0, "unit": "detected", "clean": 0.0, "fail": 1.0},
    "STABILITY_ASSAY": {"lo": 80.0, "hi": 120.0, "unit": "pct", "clean": 96.0, "fail": 61.0},
    "APPEARANCE": {"lo": 1.0, "hi": 1.0, "unit": "pass", "clean": 1.0, "fail": 0.0},
}

METHOD_IDS = {
    "POTENCY": "METH-RTP-POTENCY-v1",
    "VIABILITY": "METH-RTP-VIABILITY-v1",
    "IDENTITY": "METH-RTP-IDENTITY-v1",
    "ENDOTOXIN": "METH-RTP-ENDOTOXIN-v1",
    "VECTOR_COPY": "METH-RTP-VCN-v1",
    "RAPID_STERILITY": "METH-RTP-RAPID-STERILITY-v1",
    "MYCOPLASMA": "METH-RTP-MYCOPLASMA-v1",
    "STABILITY_ASSAY": "METH-RTP-STABILITY-v1",
    "APPEARANCE": "METH-RTP-APPEARANCE-v1",
}


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _program(batch_no: int) -> str:
    return "AUTOLOGOUS" if batch_no <= 15 else "ALLOGENEIC"


def _timestamp(epoch: str, batch_no: int, slot: int) -> str:
    base = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    stamp = base + timedelta(hours=batch_no - 1, minutes=slot - 1)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _in_spec(value: float, spec: dict[str, float]) -> bool:
    return spec["lo"] <= value <= spec["hi"]


def exception_kind_for_batch(fixture: dict[str, Any], batch_no: int) -> dict[str, Any]:
    kinds = fixture["exception_kinds"]
    return deepcopy(kinds[(batch_no - 1) % len(kinds)])


def build_acceptance_fixture(fixture: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = fixture if fixture is not None else load_fixture()
    epoch = spec["timestamp_epoch"]
    rows: list[dict[str, Any]] = []
    for batch_no in range(1, spec["batch_count"] + 1):
        kind = exception_kind_for_batch(spec, batch_no)
        batch_id = f"SYN-RTP-BATCH-{batch_no:02d}"
        for slot_meta in SAMPLE_SLOTS:
            slot = int(slot_meta["slot"])
            assay = slot_meta["assay"]
            assay_spec = SPECS[assay]
            is_exception = slot == int(kind["slot"])
            calculated = assay_spec["fail"] if is_exception else assay_spec["clean"]
            method_status = "GAP" if is_exception and kind["code"] == "METHOD_VALIDATION_GAP" else "VALIDATED"
            if is_exception and kind["code"] == "METHOD_VALIDATION_GAP":
                calculated = 0.0
            sample_id = f"SYN-RTP-B{batch_no:02d}-S{slot:02d}"
            result_id = f"SYN-RTP-RES-B{batch_no:02d}-S{slot:02d}"
            row = {
                "sample_id": sample_id,
                "result_id": result_id,
                "batch_id": batch_id,
                "batch_no": batch_no,
                "slot": slot,
                "site": SITE,
                "program": _program(batch_no),
                "plan": slot_meta["plan"],
                "lab": slot_meta["lab"],
                "assay": assay,
                "method_id": METHOD_IDS[assay],
                "method_validation_status": method_status,
                "spec_lo": assay_spec["lo"],
                "spec_hi": assay_spec["hi"],
                "spec_unit": assay_spec["unit"],
                "calculated": calculated,
                "in_spec": _in_spec(calculated, assay_spec) and method_status == "VALIDATED",
                "timestamp": _timestamp(epoch, batch_no, slot),
                "exception": is_exception,
                "exception_code": kind["code"] if is_exception else None,
                "qms_kind": kind["qms_kind"] if is_exception else None,
            }
            rows.append(row)
    if len(rows) != spec["sample_count"]:
        raise RuntimeError("acceptance fixture must be exactly %s samples, got %s" % (spec["sample_count"], len(rows)))
    return rows


def truth_set_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": row["sample_id"],
        "result_id": row["result_id"],
        "batch_id": row["batch_id"],
        "spec_lo": row["spec_lo"],
        "spec_hi": row["spec_hi"],
        "spec_unit": row["spec_unit"],
        "calculated": row["calculated"],
        "timestamp": row["timestamp"],
        "expected_state": "EXCEPTION" if row["exception"] else "RELEASED",
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "samples": {},
        "results": {},
        "qms_events": {},
        "erp_payloads": {},
        "events": [],
        "interface_live": False,
        "production_writes": 0,
        "phi_records": 0,
        "billing_writes": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def _erp_payload(batch_id: str, program: str, sample_ids: list[str]) -> dict[str, Any]:
    return {
        "interface": "SIMULATED_ERP_READONLY",
        "live": False,
        "site": SITE,
        "batch_id": batch_id,
        "program": program,
        "disposition": "HOLD",
        "sample_ids": sample_ids,
        "cash_usd": 0,
    }


def _qms_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "interface": "SIMULATED_VEEVA_QMS_READONLY",
        "live": False,
        "event_id": f"SIM-QMS-{row['batch_id'][-2:]}",
        "kind": row["qms_kind"],
        "exception_code": row["exception_code"],
        "sample_id": row["sample_id"],
        "result_id": row["result_id"],
        "batch_id": row["batch_id"],
        "opened": True,
    }


def import_sample(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    sample_id = row["sample_id"]
    result_id = row["result_id"]
    if sample_id in journal["samples"]:
        existing = journal["samples"][sample_id]
        if existing["result_id"] == result_id:
            _event(journal, "REPLAY_NOOP", {"sample_id": sample_id, "result_id": result_id})
            return {"kind": "REPLAY_NOOP", "sample_id": sample_id, "result_id": result_id}
        raise RuntimeError("duplicate sample with different result: %s" % sample_id)
    if result_id in journal["results"]:
        raise RuntimeError("duplicate result: %s" % result_id)

    state = "EXCEPTION" if row["exception"] else "READY_FOR_NAMED_QA"
    record = {
        "sample_id": sample_id,
        "result_id": result_id,
        "batch_id": row["batch_id"],
        "batch_no": row["batch_no"],
        "slot": row["slot"],
        "site": row["site"],
        "program": row["program"],
        "plan": row["plan"],
        "lab": row["lab"],
        "assay": row["assay"],
        "method_id": row["method_id"],
        "method_validation_status": row["method_validation_status"],
        "spec_lo": row["spec_lo"],
        "spec_hi": row["spec_hi"],
        "spec_unit": row["spec_unit"],
        "calculated": row["calculated"],
        "in_spec": row["in_spec"],
        "timestamp": row["timestamp"],
        "exception": row["exception"],
        "exception_code": row["exception_code"],
        "qms_kind": row["qms_kind"],
        "qms_event_id": None,
        "state": state,
        "released": False,
        "released_by": None,
        "interface_live": False,
    }
    journal["samples"][sample_id] = record
    journal["results"][result_id] = sample_id
    _event(
        journal,
        "IMPORTED",
        {
            "sample_id": sample_id,
            "result_id": result_id,
            "batch_id": row["batch_id"],
            "state": state,
        },
    )

    if row["exception"]:
        qms = _qms_payload(row)
        event_id = qms["event_id"]
        if event_id not in journal["qms_events"]:
            qms["payload_sha256"] = sha256_hex(qms)
            journal["qms_events"][event_id] = qms
            record["qms_event_id"] = event_id
            _event(journal, "QMS_OPENED", {"event_id": event_id, "sample_id": sample_id, "kind": qms["kind"]})
        return {"kind": "EXCEPTION", "sample_id": sample_id, "qms_event_id": event_id}

    return {"kind": "READY_FOR_NAMED_QA", "sample_id": sample_id}


def import_rows(journal: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_samples = set(journal["samples"])
    before_results = set(journal["results"])
    before_qms = set(journal["qms_events"])
    before_erp = set(journal["erp_payloads"])
    effects = [import_sample(journal, row) for row in rows]
    _ensure_erp_payloads(journal)
    changed = (
        (set(journal["samples"]) - before_samples)
        | (set(journal["results"]) - before_results)
        | (set(journal["qms_events"]) - before_qms)
        | (set(journal["erp_payloads"]) - before_erp)
    )
    return {
        "effects": effects,
        "changed_records": len(changed),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "sample_count": len(journal["samples"]),
        "result_count": len(journal["results"]),
        "qms_count": len(journal["qms_events"]),
    }


def _ensure_erp_payloads(journal: dict[str, Any]) -> None:
    by_batch: dict[str, list[dict[str, Any]]] = {}
    for record in journal["samples"].values():
        by_batch.setdefault(record["batch_id"], []).append(record)
    for batch_id, records in by_batch.items():
        if batch_id in journal["erp_payloads"]:
            continue
        sample_ids = [item["sample_id"] for item in sorted(records, key=lambda item: item["slot"])]
        payload = _erp_payload(batch_id, records[0]["program"], sample_ids)
        payload["payload_sha256"] = sha256_hex({k: v for k, v in payload.items() if k != "payload_sha256"})
        journal["erp_payloads"][batch_id] = payload
        _event(journal, "ERP_HASHED", {"batch_id": batch_id, "payload_sha256": payload["payload_sha256"]})


def release_sample(journal: dict[str, Any], sample_id: str, *, actor_role: str, actor: str) -> dict[str, Any]:
    record = journal["samples"].get(sample_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_SAMPLE"}
    if record["released"]:
        return {"ok": True, "duplicate": True, "state": "RELEASED"}
    role = str(actor_role or "").strip().upper()
    if role != NAMED_QA_ROLE:
        code = "RELEASE_BLOCKED_AUTONOMOUS" if role == "SYSTEM" else "RELEASE_BLOCKED_NAMED_QA_MISSING"
        _event(journal, "RELEASE_BLOCKED", {"sample_id": sample_id, "code": code, "actor_role": role or None})
        return {"ok": False, "code": code, "state": record["state"]}
    if record["exception"] or record["state"] == "EXCEPTION":
        _event(
            journal,
            "RELEASE_BLOCKED",
            {"sample_id": sample_id, "code": "RELEASE_BLOCKED_OPEN_QMS", "qms_event_id": record["qms_event_id"]},
        )
        return {"ok": False, "code": "RELEASE_BLOCKED_OPEN_QMS", "state": "EXCEPTION"}
    record["released"] = True
    record["released_by"] = actor
    record["state"] = "RELEASED"
    _event(journal, "RELEASED", {"sample_id": sample_id, "released_by": actor, "role": NAMED_QA_ROLE})
    return {"ok": True, "duplicate": False, "state": "RELEASED"}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_sample(journal, sample_id, actor_role="SYSTEM", actor="autonomous")
        for sample_id in sorted(journal["samples"])
    ]


def named_qa_release(journal: dict[str, Any], actor: str = NAMED_QA_ACTOR) -> list[dict[str, Any]]:
    return [
        release_sample(journal, sample_id, actor_role=NAMED_QA_ROLE, actor=actor)
        for sample_id in sorted(journal["samples"])
    ]


def _bundle_sha(items: list[str]) -> str:
    return sha256_hex(items)


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any], truth_matches: int) -> dict[str, Any]:
    samples = [deepcopy(journal["samples"][key]) for key in sorted(journal["samples"])]
    qms = [deepcopy(journal["qms_events"][key]) for key in sorted(journal["qms_events"])]
    erp = [deepcopy(journal["erp_payloads"][key]) for key in sorted(journal["erp_payloads"])]
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "site": SITE,
        "counts": counts,
        "truth_set_matches": truth_matches,
        "samples": [
            {
                "sample_id": item["sample_id"],
                "result_id": item["result_id"],
                "batch_id": item["batch_id"],
                "spec_lo": item["spec_lo"],
                "spec_hi": item["spec_hi"],
                "spec_unit": item["spec_unit"],
                "calculated": item["calculated"],
                "timestamp": item["timestamp"],
                "state": item["state"],
                "exception_code": item["exception_code"],
                "qms_event_id": item["qms_event_id"],
                "released": item["released"],
                "method_id": item["method_id"],
                "method_validation_status": item["method_validation_status"],
            }
            for item in samples
        ],
        "qms_events": qms,
        "erp_payloads": erp,
        "events": deepcopy(journal["events"]),
        "adapters": {
            "qc": "SIMULATED",
            "microbiology": "SIMULATED",
            "stability": "SIMULATED",
            "veeva_qms": "SIMULATED_READONLY",
            "erp": "SIMULATED_READONLY",
            "lims": "SIMULATED",
        },
    }


def match_truth_set(journal: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    matches = 0
    for row in rows:
        truth = truth_set_row(row)
        actual = journal["samples"].get(row["sample_id"])
        if actual is None:
            continue
        if (
            actual["sample_id"] == truth["sample_id"]
            and actual["result_id"] == truth["result_id"]
            and actual["batch_id"] == truth["batch_id"]
            and actual["spec_lo"] == truth["spec_lo"]
            and actual["spec_hi"] == truth["spec_hi"]
            and actual["spec_unit"] == truth["spec_unit"]
            and actual["calculated"] == truth["calculated"]
            and actual["timestamp"] == truth["timestamp"]
            and actual["state"] == truth["expected_state"]
        ):
            matches += 1
    return matches


def run_gate(rows: list[dict[str, Any]] | None = None, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture(spec))
    journal = empty_journal()
    first_import = import_rows(journal, inbound)
    autonomous = attempt_autonomous_release(journal)
    human = named_qa_release(journal)
    replay = import_rows(journal, inbound)
    truth_matches = match_truth_set(journal, inbound)

    samples = list(journal["samples"].values())
    released = [item for item in samples if item["released"]]
    exceptions = [item for item in samples if item["exception"]]
    qms_by_sample = {item["sample_id"]: item for item in journal["qms_events"].values()}
    erp_hashes = [journal["erp_payloads"][key]["payload_sha256"] for key in sorted(journal["erp_payloads"])]
    qms_hashes = [journal["qms_events"][key]["payload_sha256"] for key in sorted(journal["qms_events"])]
    counts = {
        "samples": len(samples),
        "batches": len(journal["erp_payloads"]),
        "exceptions": len(exceptions),
        "qms_events": len(journal["qms_events"]),
        "duplicate_samples": len(samples) - len({item["sample_id"] for item in samples}),
        "duplicate_results": len(journal["results"]) - len(set(journal["results"])),
        "truth_set_matches": truth_matches,
        "released_without_named_qa": sum(1 for item in autonomous if item.get("ok")),
        "released_after_named_qa": len(released),
        "exception_hold": sum(1 for item in exceptions if not item["released"]),
        "replay_changed_records": replay["changed_records"],
    }
    audit = _audit_payload(journal, counts, truth_matches)
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "command": COMMAND,
        "counts": counts,
        "hold_codes": sorted({item["exception_code"] for item in exceptions if item["exception_code"]}),
        "qms_kinds": sorted({item["kind"] for item in journal["qms_events"].values()}),
        "erp_hashes": erp_hashes,
        "qms_hashes": qms_hashes,
        "erp_bundle_sha256": _bundle_sha(erp_hashes),
        "qms_bundle_sha256": _bundle_sha(qms_hashes),
        "first_import": {k: v for k, v in first_import.items() if k != "effects"},
        "replay": {k: v for k, v in replay.items() if k != "effects"},
        "autonomous_release_effects": autonomous,
        "named_qa_release_effects": human,
        "samples": sorted(samples, key=lambda item: item["sample_id"]),
        "qms_events": [journal["qms_events"][key] for key in sorted(journal["qms_events"])],
        "erp_payloads": [journal["erp_payloads"][key] for key in sorted(journal["erp_payloads"])],
        "qms_by_exception_sample": qms_by_sample,
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "phi_records": 0,
        "billing_writes": 0,
        "automatic_release": False,
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "golden_audit_sha256": spec.get("golden_audit_sha256"),
        "golden_erp_bundle_sha256": spec.get("golden_erp_bundle_sha256"),
        "golden_qms_bundle_sha256": spec.get("golden_qms_bundle_sha256"),
    }
    return body


def pass_contract(result: dict[str, Any], fixture: dict[str, Any] | None = None) -> list[str]:
    spec = fixture if fixture is not None else load_fixture()
    expected = spec["expected"]
    failures: list[str] = []
    counts = result.get("counts") or {}
    for key, value in expected.items():
        if counts.get(key) != value:
            failures.append(f"{key}!={value} actual={counts.get(key)}")
    if len(result.get("samples") or []) != 300:
        failures.append("sample_rows")
    sample_ids = [item["sample_id"] for item in result.get("samples") or []]
    result_ids = [item["result_id"] for item in result.get("samples") or []]
    if len(sample_ids) != len(set(sample_ids)):
        failures.append("duplicate_sample_ids")
    if len(result_ids) != len(set(result_ids)):
        failures.append("duplicate_result_ids")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("phi_records") != 0:
        failures.append("phi_records")
    if result.get("billing_writes") != 0:
        failures.append("billing_writes")
    if result.get("automatic_release") is not False:
        failures.append("automatic_release")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if not all(item.get("code") == "RELEASE_BLOCKED_AUTONOMOUS" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_not_blocked")
    exceptions = [item for item in result.get("samples") or [] if item.get("exception")]
    if len(exceptions) != 30:
        failures.append("exception_count")
    qms_events = {item["event_id"]: item for item in result.get("qms_events") or []}
    for item in exceptions:
        event = qms_events.get(item.get("qms_event_id") or "")
        if event is None:
            failures.append("missing_qms:%s" % item["sample_id"])
            continue
        if event.get("kind") != item.get("qms_kind") or event.get("sample_id") != item["sample_id"]:
            failures.append("qms_mismatch:%s" % item["sample_id"])
        if event.get("live") is not False:
            failures.append("qms_live:%s" % item["sample_id"])
    if any(item.get("released") for item in exceptions):
        failures.append("exception_released")
    if result.get("replay", {}).get("changed_records") != 0:
        failures.append("replay_changed")
    golden_audit = spec.get("golden_audit_sha256")
    if golden_audit and golden_audit != "PIN_AFTER_FIRST_RUN":
        if result.get("audit_sha256") != golden_audit:
            failures.append("audit_sha256")
        if result.get("erp_bundle_sha256") != spec.get("golden_erp_bundle_sha256"):
            failures.append("erp_bundle_sha256")
        if result.get("qms_bundle_sha256") != spec.get("golden_qms_bundle_sha256"):
            failures.append("qms_bundle_sha256")
    if sha256_hex(result.get("audit")) != result.get("audit_sha256"):
        failures.append("audit_hash_internal")
    return failures


def expected_actual(result: dict[str, Any], fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    expected = spec["expected"]
    actual = {key: (result.get("counts") or {}).get(key) for key in expected}
    return {"expected": expected, "actual": actual, "match": expected == actual}


def main() -> int:
    fixture = load_fixture()
    first = run_gate(fixture=fixture)
    second = run_gate(fixture=fixture)
    failures = pass_contract(first, fixture)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_replay_mismatch")
    if first.get("erp_bundle_sha256") != second.get("erp_bundle_sha256"):
        failures.append("erp_replay_mismatch")
    if first.get("qms_bundle_sha256") != second.get("qms_bundle_sha256"):
        failures.append("qms_replay_mismatch")
    counts = expected_actual(first, fixture)
    report = {
        "ok": not failures,
        "failures": failures,
        "command": COMMAND,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "audit_sha256": first.get("audit_sha256"),
        "erp_bundle_sha256": first.get("erp_bundle_sha256"),
        "qms_bundle_sha256": first.get("qms_bundle_sha256"),
        "replay_changed_records": first.get("counts", {}).get("replay_changed_records"),
        "truth_gate": TRUTH_GATE,
        "interfaces": "SIMULATED",
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

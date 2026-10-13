#!/usr/bin/env python3
"""Made Scientific Princeton LabVantage Rapid-QC Scale-Up Pack.

Demand: made-scientific-princeton-rapid-qc-lims-01
Buyer pairing: Made Scientific Princeton / Irving Ford

Exact posted fixture only. 200 synthetic batches / 2,400 samples.
40 predefined OOS / duplicate / late / interface-failure cases.
Four simulated endpoints: LabVantage, AutoloMATE MES, Veeva QMS, NetSuite ERP.
Named human must act before release. No automatic release. No core replacement.

Synthetic / mocked read-only. No live methods, batches, QMS, ERP, billing,
or material disposition. No PHI. cash_usd=0. HOLD / BUILD-AND-VERIFY.
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

DEMAND_ID = "made-scientific-princeton-rapid-qc-lims-01"
SCHEMA = "commons-made-scientific-princeton-rapid-qc-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Made Scientific Princeton / Irving Ford"
SITE = "Princeton"
NAMED_QA_ROLE = "NAMED_QA"
NAMED_QA_ACTOR = "qa-named-princeton-1"
COMMAND = "python3 revenue/made_scientific_princeton_rapid_qc/runner.py"
ENDPOINTS = ("LABVANTAGE", "AUTOLOMATE_MES", "VEEVA_QMS", "NETSUITE_ERP")

SAMPLE_SLOTS = (
    {"slot": 1, "plan": "FINAL", "lab": "MICROBIOLOGY", "assay": "RAPID_STERILITY"},
    {"slot": 2, "plan": "FINAL", "lab": "QC", "assay": "ENDOTOXIN"},
    {"slot": 3, "plan": "FINAL", "lab": "MICROBIOLOGY", "assay": "MYCOPLASMA"},
    {"slot": 4, "plan": "IN_PROCESS", "lab": "QC", "assay": "IDENTITY"},
    {"slot": 5, "plan": "FINAL", "lab": "QC", "assay": "POTENCY"},
    {"slot": 6, "plan": "IN_PROCESS", "lab": "QC", "assay": "VIABILITY"},
    {"slot": 7, "plan": "FINAL", "lab": "QC", "assay": "APPEARANCE"},
    {"slot": 8, "plan": "FINAL", "lab": "QC", "assay": "VECTOR_COPY"},
    {"slot": 9, "plan": "IN_PROCESS", "lab": "QC", "assay": "RESIDUAL"},
    {"slot": 10, "plan": "STABILITY", "lab": "STABILITY", "assay": "STABILITY_ASSAY"},
    {"slot": 11, "plan": "IN_PROCESS", "lab": "QC", "assay": "METABOLITE"},
    {"slot": 12, "plan": "FINAL", "lab": "QC", "assay": "PH"},
)

SPECS = {
    "RAPID_STERILITY": {"lo": 0.0, "hi": 0.0, "unit": "growth", "clean": 0.0, "fail": 1.0},
    "ENDOTOXIN": {"lo": 0.0, "hi": 5.0, "unit": "EU_per_mL", "clean": 1.25, "fail": 9.5},
    "MYCOPLASMA": {"lo": 0.0, "hi": 0.0, "unit": "detected", "clean": 0.0, "fail": 1.0},
    "IDENTITY": {"lo": 1.0, "hi": 1.0, "unit": "match", "clean": 1.0, "fail": 0.0},
    "POTENCY": {"lo": 80.0, "hi": 120.0, "unit": "pct", "clean": 100.0, "fail": 64.0},
    "VIABILITY": {"lo": 70.0, "hi": 100.0, "unit": "pct", "clean": 88.0, "fail": 52.0},
    "APPEARANCE": {"lo": 1.0, "hi": 1.0, "unit": "pass", "clean": 1.0, "fail": 0.0},
    "VECTOR_COPY": {"lo": 1.0, "hi": 5.0, "unit": "copies", "clean": 3.0, "fail": 8.0},
    "RESIDUAL": {"lo": 0.0, "hi": 2.0, "unit": "ppm", "clean": 0.4, "fail": 6.0},
    "STABILITY_ASSAY": {"lo": 80.0, "hi": 120.0, "unit": "pct", "clean": 96.0, "fail": 61.0},
    "METABOLITE": {"lo": 0.0, "hi": 10.0, "unit": "mM", "clean": 4.0, "fail": 18.0},
    "PH": {"lo": 6.8, "hi": 7.6, "unit": "pH", "clean": 7.2, "fail": 5.1},
}

METHOD_IDS = {
    "RAPID_STERILITY": "METH-PRN-RAPID-STERILITY-v1",
    "ENDOTOXIN": "METH-PRN-ENDOTOXIN-v1",
    "MYCOPLASMA": "METH-PRN-MYCOPLASMA-v1",
    "IDENTITY": "METH-PRN-IDENTITY-v1",
    "POTENCY": "METH-PRN-POTENCY-v1",
    "VIABILITY": "METH-PRN-VIABILITY-v1",
    "APPEARANCE": "METH-PRN-APPEARANCE-v1",
    "VECTOR_COPY": "METH-PRN-VCN-v1",
    "RESIDUAL": "METH-PRN-RESIDUAL-v1",
    "STABILITY_ASSAY": "METH-PRN-STABILITY-v1",
    "METABOLITE": "METH-PRN-METABOLITE-v1",
    "PH": "METH-PRN-PH-v1",
}

ENDPOINT_INTERFACES = {
    "LABVANTAGE": "SIMULATED_LABVANTAGE_READONLY",
    "AUTOLOMATE_MES": "SIMULATED_AUTOLOMATE_MES_READONLY",
    "VEEVA_QMS": "SIMULATED_VEEVA_QMS_READONLY",
    "NETSUITE_ERP": "SIMULATED_NETSUITE_ERP_READONLY",
}


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _timestamp(epoch: str, batch_no: int, slot: int, extra_hours: int = 0) -> str:
    base = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    stamp = base + timedelta(hours=batch_no - 1 + extra_hours, minutes=slot - 1)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _in_spec(value: float, spec: dict[str, float]) -> bool:
    return spec["lo"] <= value <= spec["hi"]


def failure_index(fixture: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    index: dict[tuple[int, int], dict[str, Any]] = {}
    for item in fixture["predefined_failures"]:
        key = (int(item["batch_no"]), int(item["slot"]))
        if key in index:
            raise RuntimeError("duplicate predefined failure key %s" % (key,))
        index[key] = deepcopy(item)
    return index


def build_acceptance_fixture(fixture: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = fixture if fixture is not None else load_fixture()
    epoch = spec["timestamp_epoch"]
    sla_hours = int(spec["rapid_qc_sla_hours"])
    failures = failure_index(spec)
    rows: list[dict[str, Any]] = []
    for batch_no in range(1, spec["batch_count"] + 1):
        batch_id = f"SYN-PRN-BATCH-{batch_no:03d}"
        for slot_meta in SAMPLE_SLOTS:
            slot = int(slot_meta["slot"])
            assay = slot_meta["assay"]
            assay_spec = SPECS[assay]
            fail = failures.get((batch_no, slot))
            kind = fail["kind"] if fail else None
            extra_hours = sla_hours + 4 if kind == "LATE" else 0
            calculated = assay_spec["fail"] if kind == "OOS" else assay_spec["clean"]
            timestamp = _timestamp(epoch, batch_no, slot, extra_hours=extra_hours)
            on_time = extra_hours == 0
            sample_id = f"SYN-PRN-B{batch_no:03d}-S{slot:02d}"
            result_id = f"SYN-PRN-RES-B{batch_no:03d}-S{slot:02d}"
            twin_id = f"SYN-PRN-TWIN-B{batch_no:03d}-S{slot:02d}" if kind == "DUPLICATE" else None
            row = {
                "sample_id": sample_id,
                "result_id": result_id,
                "batch_id": batch_id,
                "batch_no": batch_no,
                "slot": slot,
                "site": SITE,
                "plan": slot_meta["plan"],
                "lab": slot_meta["lab"],
                "assay": assay,
                "method_id": METHOD_IDS[assay],
                "spec_lo": assay_spec["lo"],
                "spec_hi": assay_spec["hi"],
                "spec_unit": assay_spec["unit"],
                "calculated": calculated,
                "in_spec": _in_spec(calculated, assay_spec),
                "timestamp": timestamp,
                "on_time": on_time,
                "exception": fail is not None,
                "exception_kind": kind,
                "hold": fail["hold"] if fail else None,
                "deviation": fail["deviation"] if fail else None,
                "case_no": fail["case_no"] if fail else None,
                "twin_attempt_id": twin_id,
            }
            rows.append(row)
    if len(rows) != spec["sample_count"]:
        raise RuntimeError("acceptance fixture must be exactly %s samples, got %s" % (spec["sample_count"], len(rows)))
    if sum(1 for row in rows if row["exception"]) != spec["failure_count"]:
        raise RuntimeError("acceptance fixture must seed exactly %s failures" % spec["failure_count"])
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
        "expected_state": "HOLD" if row["exception"] else "RELEASED",
        "hold": row["hold"],
        "deviation": row["deviation"],
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "samples": {},
        "results": {},
        "rejected_twins": {},
        "holds": {},
        "endpoints": {name: {} for name in ENDPOINTS},
        "events": [],
        "interface_live": False,
        "production_writes": 0,
        "phi_records": 0,
        "billing_writes": 0,
        "disposition_writes": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def _endpoint_payload(row: dict[str, Any], endpoint: str, state: str) -> dict[str, Any]:
    payload = {
        "interface": ENDPOINT_INTERFACES[endpoint],
        "endpoint": endpoint,
        "live": False,
        "site": SITE,
        "sample_id": row["sample_id"],
        "result_id": row["result_id"],
        "batch_id": row["batch_id"],
        "state": state,
        "hold": row["hold"] if state == "HOLD" else None,
        "deviation": row["deviation"] if state == "HOLD" else None,
        "cash_usd": 0,
        "disposition": "HOLD" if state != "RELEASED" else "HUMAN_RELEASED",
    }
    payload["payload_sha256"] = sha256_hex({k: v for k, v in payload.items() if k != "payload_sha256"})
    return payload


def _write_endpoint(journal: dict[str, Any], row: dict[str, Any], endpoint: str, state: str) -> None:
    payload = _endpoint_payload(row, endpoint, state)
    journal["endpoints"][endpoint][row["sample_id"]] = payload


def _apply_hold(journal: dict[str, Any], record: dict[str, Any], row: dict[str, Any]) -> None:
    hold_id = f"SYN-PRN-HOLD-{row['case_no']:02d}"
    hold = {
        "hold_id": hold_id,
        "sample_id": row["sample_id"],
        "batch_id": row["batch_id"],
        "kind": row["exception_kind"],
        "hold": row["hold"],
        "deviation": row["deviation"],
        "specified": True,
        "live": False,
    }
    journal["holds"][hold_id] = hold
    record["hold_id"] = hold_id
    record["state"] = "HOLD"
    record["exception"] = True
    record["exception_kind"] = row["exception_kind"]
    record["hold"] = row["hold"]
    record["deviation"] = row["deviation"]
    for endpoint in ENDPOINTS:
        _write_endpoint(journal, row, endpoint, "HOLD")
    _event(
        journal,
        "HOLD_OPENED",
        {
            "hold_id": hold_id,
            "sample_id": row["sample_id"],
            "kind": row["exception_kind"],
            "hold": row["hold"],
            "deviation": row["deviation"],
        },
    )


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

    record = {
        "sample_id": sample_id,
        "result_id": result_id,
        "batch_id": row["batch_id"],
        "batch_no": row["batch_no"],
        "slot": row["slot"],
        "site": row["site"],
        "plan": row["plan"],
        "lab": row["lab"],
        "assay": row["assay"],
        "method_id": row["method_id"],
        "spec_lo": row["spec_lo"],
        "spec_hi": row["spec_hi"],
        "spec_unit": row["spec_unit"],
        "calculated": row["calculated"],
        "in_spec": row["in_spec"],
        "timestamp": row["timestamp"],
        "on_time": row["on_time"],
        "exception": False,
        "exception_kind": None,
        "hold": None,
        "deviation": None,
        "hold_id": None,
        "state": "READY_FOR_NAMED_QA",
        "released": False,
        "released_by": None,
        "interface_live": False,
        "twin_attempt_id": row["twin_attempt_id"],
    }
    journal["samples"][sample_id] = record
    journal["results"][result_id] = sample_id
    _event(
        journal,
        "IMPORTED",
        {"sample_id": sample_id, "result_id": result_id, "batch_id": row["batch_id"]},
    )

    if row["exception_kind"] == "DUPLICATE":
        twin_id = row["twin_attempt_id"]
        journal["rejected_twins"][twin_id] = {
            "twin_attempt_id": twin_id,
            "sample_id": sample_id,
            "result_id": result_id,
            "reason": "DUPLICATE_ACCESSION",
            "kept": False,
        }
        _event(journal, "DUPLICATE_REJECTED", {"twin_attempt_id": twin_id, "sample_id": sample_id})
        _apply_hold(journal, record, row)
        return {"kind": "HOLD", "sample_id": sample_id, "hold": row["hold"]}

    if row["exception_kind"] == "INTERFACE_FAILURE":
        _write_endpoint(journal, row, "LABVANTAGE", "READY_FOR_NAMED_QA")
        _write_endpoint(journal, row, "AUTOLOMATE_MES", "READY_FOR_NAMED_QA")
        _event(journal, "INTERFACE_GAP", {"sample_id": sample_id, "missing": ["VEEVA_QMS", "NETSUITE_ERP"]})
        _apply_hold(journal, record, row)
        return {"kind": "HOLD", "sample_id": sample_id, "hold": row["hold"]}

    if row["exception_kind"] in {"OOS", "LATE"}:
        _apply_hold(journal, record, row)
        return {"kind": "HOLD", "sample_id": sample_id, "hold": row["hold"]}

    for endpoint in ENDPOINTS:
        _write_endpoint(journal, row, endpoint, "READY_FOR_NAMED_QA")
    return {"kind": "READY_FOR_NAMED_QA", "sample_id": sample_id}


def import_rows(journal: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_samples = set(journal["samples"])
    before_results = set(journal["results"])
    before_holds = set(journal["holds"])
    before_endpoints = {name: set(journal["endpoints"][name]) for name in ENDPOINTS}
    effects = [import_sample(journal, row) for row in rows]
    after_endpoints = {name: set(journal["endpoints"][name]) for name in ENDPOINTS}
    changed_endpoints = set()
    for name in ENDPOINTS:
        changed_endpoints |= after_endpoints[name] - before_endpoints[name]
    changed = (
        (set(journal["samples"]) - before_samples)
        | (set(journal["results"]) - before_results)
        | (set(journal["holds"]) - before_holds)
        | changed_endpoints
    )
    return {
        "effects": effects,
        "changed_records": len(changed),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "sample_count": len(journal["samples"]),
        "result_count": len(journal["results"]),
        "hold_count": len(journal["holds"]),
    }


def reconcile_endpoints(journal: dict[str, Any]) -> dict[str, Any]:
    mismatches = 0
    orphans = 0
    for sample_id, record in journal["samples"].items():
        states = []
        for endpoint in ENDPOINTS:
            payload = journal["endpoints"][endpoint].get(sample_id)
            if payload is None:
                orphans += 1
                continue
            states.append(payload["state"])
        if len(states) != 4 or len(set(states)) != 1:
            mismatches += 1
        elif record["state"] != states[0]:
            mismatches += 1
    return {"mismatches": mismatches, "orphans": orphans, "reconciled": mismatches == 0 and orphans == 0}


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
    if record["exception"] or record["state"] == "HOLD":
        _event(
            journal,
            "RELEASE_BLOCKED",
            {"sample_id": sample_id, "code": "RELEASE_BLOCKED_OPEN_HOLD", "hold_id": record["hold_id"]},
        )
        return {"ok": False, "code": "RELEASE_BLOCKED_OPEN_HOLD", "state": "HOLD"}
    record["released"] = True
    record["released_by"] = actor
    record["state"] = "RELEASED"
    row = {
        "sample_id": record["sample_id"],
        "result_id": record["result_id"],
        "batch_id": record["batch_id"],
        "hold": None,
        "deviation": None,
    }
    for endpoint in ENDPOINTS:
        _write_endpoint(journal, row, endpoint, "RELEASED")
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


def _endpoint_hashes(journal: dict[str, Any]) -> dict[str, Any]:
    hashes: dict[str, list[str]] = {}
    bundles: dict[str, str] = {}
    payloads: dict[str, list[dict[str, Any]]] = {}
    for name in ENDPOINTS:
        ordered = [journal["endpoints"][name][key] for key in sorted(journal["endpoints"][name])]
        payloads[name] = ordered
        digest = [item["payload_sha256"] for item in ordered]
        hashes[name] = digest
        bundles[name] = _bundle_sha(digest)
    return {"hashes": hashes, "bundles": bundles, "payloads": payloads}


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any], truth_matches: int, bundles: dict[str, str]) -> dict[str, Any]:
    samples = [deepcopy(journal["samples"][key]) for key in sorted(journal["samples"])]
    holds = [deepcopy(journal["holds"][key]) for key in sorted(journal["holds"])]
    twins = [deepcopy(journal["rejected_twins"][key]) for key in sorted(journal["rejected_twins"])]
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
                "exception_kind": item["exception_kind"],
                "hold": item["hold"],
                "deviation": item["deviation"],
                "hold_id": item["hold_id"],
                "released": item["released"],
                "method_id": item["method_id"],
            }
            for item in samples
        ],
        "holds": holds,
        "rejected_twins": twins,
        "endpoint_bundles": bundles,
        "events": deepcopy(journal["events"]),
        "adapters": {
            "labvantage": "SIMULATED_READONLY",
            "autolomate_mes": "SIMULATED_READONLY",
            "veeva_qms": "SIMULATED_READONLY",
            "netsuite_erp": "SIMULATED_READONLY",
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
            and actual["hold"] == truth["hold"]
            and actual["deviation"] == truth["deviation"]
        ):
            matches += 1
    return matches


def orphan_count(journal: dict[str, Any]) -> int:
    samples = journal["samples"]
    by_batch: dict[str, list[str]] = {}
    orphans = 0
    for sample_id, record in samples.items():
        if not record.get("batch_id"):
            orphans += 1
        by_batch.setdefault(record["batch_id"], []).append(sample_id)
        for endpoint in ENDPOINTS:
            if sample_id not in journal["endpoints"][endpoint]:
                orphans += 1
    for sample_ids in by_batch.values():
        if len(sample_ids) != 12:
            orphans += abs(12 - len(sample_ids))
    expected_batches = {f"SYN-PRN-BATCH-{n:03d}" for n in range(1, 201)}
    orphans += len(expected_batches.symmetric_difference(by_batch))
    orphans += len(journal["rejected_twins"])  # twins are rejected, not leftover samples
    # rejected twins are not orphans; they are documented rejections. Subtract them.
    orphans -= len(journal["rejected_twins"])
    return orphans


def run_gate(rows: list[dict[str, Any]] | None = None, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture(spec))
    journal = empty_journal()
    first_import = import_rows(journal, inbound)
    autonomous = attempt_autonomous_release(journal)
    human = named_qa_release(journal)
    replay = import_rows(journal, inbound)
    truth_matches = match_truth_set(journal, inbound)
    reconcile = reconcile_endpoints(journal)
    endpoint_meta = _endpoint_hashes(journal)

    samples = list(journal["samples"].values())
    released = [item for item in samples if item["released"]]
    failures = [item for item in samples if item["exception"]]
    counts = {
        "batches": len({item["batch_id"] for item in samples}),
        "samples": len(samples),
        "failures": len(failures),
        "oos": sum(1 for item in failures if item["exception_kind"] == "OOS"),
        "duplicate": sum(1 for item in failures if item["exception_kind"] == "DUPLICATE"),
        "late": sum(1 for item in failures if item["exception_kind"] == "LATE"),
        "interface_failure": sum(1 for item in failures if item["exception_kind"] == "INTERFACE_FAILURE"),
        "specified_holds": len(journal["holds"]),
        "valid_reconciled": sum(
            1
            for item in samples
            if not item["exception"]
            and all(journal["endpoints"][name][item["sample_id"]]["state"] == item["state"] for name in ENDPOINTS)
        ),
        "four_endpoint_reconciled": sum(
            1
            for item in samples
            if all(
                item["sample_id"] in journal["endpoints"][name]
                and journal["endpoints"][name][item["sample_id"]]["state"] == item["state"]
                for name in ENDPOINTS
            )
        ),
        "duplicate_samples": len(samples) - len({item["sample_id"] for item in samples}),
        "orphans": orphan_count(journal),
        "released_without_named_qa": sum(1 for item in autonomous if item.get("ok")),
        "released_after_named_qa": len(released),
        "failure_hold": sum(1 for item in failures if item["state"] == "HOLD" and not item["released"]),
        "replay_changed_records": replay["changed_records"],
    }
    audit = _audit_payload(journal, counts, truth_matches, endpoint_meta["bundles"])
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "command": COMMAND,
        "counts": counts,
        "hold_codes": sorted({item["hold"] for item in failures if item["hold"]}),
        "deviation_codes": sorted({item["deviation"] for item in failures if item["deviation"]}),
        "labvantage_bundle_sha256": endpoint_meta["bundles"]["LABVANTAGE"],
        "mes_bundle_sha256": endpoint_meta["bundles"]["AUTOLOMATE_MES"],
        "qms_bundle_sha256": endpoint_meta["bundles"]["VEEVA_QMS"],
        "erp_bundle_sha256": endpoint_meta["bundles"]["NETSUITE_ERP"],
        "first_import": {k: v for k, v in first_import.items() if k != "effects"},
        "replay": {k: v for k, v in replay.items() if k != "effects"},
        "reconcile": reconcile,
        "autonomous_release_effects": autonomous,
        "named_qa_release_effects": human,
        "samples": sorted(samples, key=lambda item: item["sample_id"]),
        "holds": [journal["holds"][key] for key in sorted(journal["holds"])],
        "rejected_twins": [journal["rejected_twins"][key] for key in sorted(journal["rejected_twins"])],
        "endpoints": endpoint_meta["payloads"],
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "phi_records": 0,
        "billing_writes": 0,
        "disposition_writes": 0,
        "automatic_release": False,
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "golden_audit_sha256": spec.get("golden_audit_sha256"),
        "golden_labvantage_bundle_sha256": spec.get("golden_labvantage_bundle_sha256"),
        "golden_mes_bundle_sha256": spec.get("golden_mes_bundle_sha256"),
        "golden_qms_bundle_sha256": spec.get("golden_qms_bundle_sha256"),
        "golden_erp_bundle_sha256": spec.get("golden_erp_bundle_sha256"),
        "truth_set_matches": truth_matches,
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
    if len(result.get("samples") or []) != 2400:
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
    if result.get("disposition_writes") != 0:
        failures.append("disposition_writes")
    if result.get("automatic_release") is not False:
        failures.append("automatic_release")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if not all(item.get("code") == "RELEASE_BLOCKED_AUTONOMOUS" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_not_blocked")
    held = [item for item in result.get("samples") or [] if item.get("exception")]
    if len(held) != 40:
        failures.append("failure_count")
    if len(result.get("holds") or []) != 40:
        failures.append("hold_rows")
    if any(item.get("released") for item in held):
        failures.append("failure_released")
    if not all(item.get("specified") for item in result.get("holds") or []):
        failures.append("hold_not_specified")
    if result.get("replay", {}).get("changed_records") != 0:
        failures.append("replay_changed")
    if result.get("reconcile", {}).get("reconciled") is not True:
        failures.append("endpoints_not_reconciled")
    if result.get("truth_set_matches") != 2400:
        failures.append("truth_set_matches")
    if len(result.get("rejected_twins") or []) != 10:
        failures.append("rejected_twins")
    golden_audit = spec.get("golden_audit_sha256")
    if golden_audit and golden_audit != "PIN_AFTER_FIRST_RUN":
        if result.get("audit_sha256") != golden_audit:
            failures.append("audit_sha256")
        if result.get("labvantage_bundle_sha256") != spec.get("golden_labvantage_bundle_sha256"):
            failures.append("labvantage_bundle_sha256")
        if result.get("mes_bundle_sha256") != spec.get("golden_mes_bundle_sha256"):
            failures.append("mes_bundle_sha256")
        if result.get("qms_bundle_sha256") != spec.get("golden_qms_bundle_sha256"):
            failures.append("qms_bundle_sha256")
        if result.get("erp_bundle_sha256") != spec.get("golden_erp_bundle_sha256"):
            failures.append("erp_bundle_sha256")
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
    for key in ("labvantage_bundle_sha256", "mes_bundle_sha256", "qms_bundle_sha256", "erp_bundle_sha256"):
        if first.get(key) != second.get(key):
            failures.append("%s_replay_mismatch" % key)
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
        "labvantage_bundle_sha256": first.get("labvantage_bundle_sha256"),
        "mes_bundle_sha256": first.get("mes_bundle_sha256"),
        "qms_bundle_sha256": first.get("qms_bundle_sha256"),
        "erp_bundle_sha256": first.get("erp_bundle_sha256"),
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

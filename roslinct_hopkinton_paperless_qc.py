#!/usr/bin/env python3
"""RoslinCT Hopkinton paperless QC sample-and-release LIMS.

Demand: roslinct-hopkinton-paperless-qc-lims-01
Buyer: RoslinCT US Hopkinton / Lisa Mello

Accession, custody, internal/external test scheduling, read-only
instrument-result ingestion, stability/retain inventory, CoA
reconciliation, Part 11-style audit/e-signature records, incumbent-LIMS
adapter, and named-human QA release.

240 synthetic samples across RAW, IN_PROCESS, RELEASE, RETAIN, and
STABILITY. Twelve mock instruments. Three mock contract labs. Twenty-four
seeded label/temperature/duplicate/late/OOS exceptions. Exactly 216
valid samples traverse expected states once; all 24 enter prescribed
holds. Replay creates zero changes. No release without a named human.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay simulated/read-only.
No real Part 11 validation claim. No production writes, reports,
billing, transfers, material disposition, or automatic release.
PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "roslinct-hopkinton-paperless-qc-lims-01"
SCHEMA = "commons-roslinct-hopkinton-paperless-qc-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "RoslinCT US Hopkinton / Lisa Mello"
HUMAN_RELEASER = "QA_RELEASER"
HUMAN_ACTOR = "qa-human-01"
SPEC_MIN = 0.0
SPEC_MAX = 10.0
IN_SPEC_VALUE = 5.0
OOS_VALUE = 99.0
COLD_MIN_C = 2.0
COLD_MAX_C = 8.0
CLASSES = ("RAW", "IN_PROCESS", "RELEASE", "RETAIN", "STABILITY")
CLASS_PANEL = {
    "RAW": "IDENTITY",
    "IN_PROCESS": "IN_PROCESS_QC",
    "RELEASE": "POTENCY",
    "RETAIN": "RETAIN_ID",
    "STABILITY": "STABILITY_ASSAY",
}
CLASS_PREFIX = {
    "RAW": "RAW",
    "IN_PROCESS": "IPC",
    "RELEASE": "REL",
    "RETAIN": "RET",
    "STABILITY": "STB",
}
INSTRUMENTS = tuple(f"INST-{index:02d}" for index in range(1, 13))
CONTRACT_LABS = ("CLAB-ALPHA", "CLAB-BRAVO", "CLAB-CHARLIE")
HOLD_CODES = (
    "HOLD_LABEL",
    "HOLD_TEMPERATURE",
    "HOLD_DUPLICATE",
    "HOLD_LATE",
    "HOLD_OOS",
)
EXPECTED_HOLD_CODES = [
    "HOLD_DUPLICATE",
    "HOLD_LABEL",
    "HOLD_LATE",
    "HOLD_OOS",
    "HOLD_TEMPERATURE",
]
EXPECTED_STATES = (
    "ACCESSIONED",
    "IN_CUSTODY",
    "SCHEDULED",
    "RESULTS_INGESTED",
    "INVENTORY_RECORDED",
    "COA_RECONCILED",
    "READY_FOR_HUMAN_RELEASE",
    "RELEASED",
)
GOLDEN_AUDIT_SHA256 = "93e5ce0ef00ca6de9ac87203b67ec05f9eb80d1cb10ffb284b1948a195dab83a"
GOLDEN_CUSTODY_SHA256 = "185cea2779565cbc000a2caeabd021c6405b05ee7d83afdf4cccd0cc0cd646a9"
GOLDEN_RESULTS_SHA256 = "2973a64b14ac91f8a5358bf0a6b80790439c885d630b058da3cb826d4affd1fc"


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


def accession_id(sample_id: str, sample_class: str, label_id: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "label_id": label_id,
            "sample_class": sample_class,
            "sample_id": sample_id,
        }
    )
    return "RCT-" + digest[:12]


def _token(sample_class: str, index: int) -> str:
    return f"SYN-RCT-{CLASS_PREFIX[sample_class]}-{index:02d}"


def _exception_for(sample_class: str, index: int) -> str | None:
    if sample_class == "STABILITY":
        return {45: "LABEL", 46: "TEMPERATURE", 47: "DUPLICATE", 48: "LATE"}.get(index)
    return {44: "LABEL", 45: "TEMPERATURE", 46: "DUPLICATE", 47: "LATE", 48: "OOS"}.get(index)


def _row(sample_class: str, index: int) -> dict[str, Any]:
    token = _token(sample_class, index)
    exception = _exception_for(sample_class, index)
    sample_id = _token(sample_class, 1) if exception == "DUPLICATE" else token
    label_id = "" if exception == "LABEL" else token
    receipt_temp_c = 25.0 if exception == "TEMPERATURE" else 4.0
    result_value = OOS_VALUE if exception == "OOS" else IN_SPEC_VALUE
    result_at = "2026-08-31T20:00:00Z" if exception == "LATE" else "2026-08-31T16:00:00Z"
    return {
        "row_id": f"{CLASS_PREFIX[sample_class]}-{index:02d}",
        "sample_id": sample_id,
        "label_id": label_id,
        "sample_class": sample_class,
        "panel": CLASS_PANEL[sample_class],
        "receipt_temp_c": receipt_temp_c,
        "collected_at": "2026-08-31T08:00:00Z",
        "received_at": "2026-08-31T10:00:00Z",
        "due_at": "2026-08-31T18:00:00Z",
        "result_at": result_at,
        "result_value": result_value,
        "spec_min": SPEC_MIN,
        "spec_max": SPEC_MAX,
        "exception_type": exception,
        "synthetic": True,
        "deidentified": True,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """240-row PASS fixture for roslinct-hopkinton-paperless-qc-lims-01.

    48 rows in each of five classes. Last rows of each class seed the
    24 label/temperature/duplicate/late/OOS holds. Remaining 216 are valid.
    """
    rows: list[dict[str, Any]] = []
    for sample_class in CLASSES:
        for index in range(1, 49):
            rows.append(_row(sample_class, index))
    if len(rows) != 240:
        raise RuntimeError("acceptance fixture must be exactly 240 rows, got %s" % len(rows))
    by_class = {name: 0 for name in CLASSES}
    exceptions = {name: 0 for name in ("LABEL", "TEMPERATURE", "DUPLICATE", "LATE", "OOS")}
    for row in rows:
        by_class[row["sample_class"]] += 1
        if row["exception_type"]:
            exceptions[row["exception_type"]] += 1
    if any(count != 48 for count in by_class.values()):
        raise RuntimeError("acceptance fixture must be 48 rows per class")
    if sum(exceptions.values()) != 24:
        raise RuntimeError("acceptance fixture must seed exactly 24 exceptions, got %s" % exceptions)
    if exceptions != {"LABEL": 5, "TEMPERATURE": 5, "DUPLICATE": 5, "LATE": 5, "OOS": 4}:
        raise RuntimeError("exception split must be 5/5/5/5/4, got %s" % exceptions)
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
        "esignatures": [],
        "interface_live": False,
        "production_writes": 0,
        "billing_writes": 0,
        "material_disposition": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    prev = journal["events"][-1]["record_hash"] if journal["events"] else "GENESIS"
    body = {
        "seq": len(journal["events"]) + 1,
        "kind": kind,
        **deepcopy(payload),
    }
    body["prev_hash"] = prev
    body["record_hash"] = sha256_hex({"prev": prev, "body": {k: v for k, v in body.items() if k not in {"prev_hash", "record_hash"}}})
    journal["events"].append(body)


def _esign(journal: dict[str, Any], *, meaning: str, actor: str, accession_id_value: str, kind: str) -> None:
    prev = journal["esignatures"][-1]["record_hash"] if journal["esignatures"] else "ESIGN-GENESIS"
    record = {
        "seq": len(journal["esignatures"]) + 1,
        "accession_id": accession_id_value,
        "actor": actor,
        "kind": kind,
        "meaning": meaning,
        "signed_at": "2026-08-31T12:00:00Z",
        "part11_style": True,
        "part11_validated": False,
        "adapter": "SIMULATED_ESIGN",
    }
    record["prev_hash"] = prev
    record["record_hash"] = sha256_hex({"prev": prev, "body": {k: v for k, v in record.items() if k not in {"prev_hash", "record_hash"}}})
    journal["esignatures"].append(record)
    _event(
        journal,
        "ESIGN",
        {
            "accession_id": accession_id_value,
            "actor": actor,
            "kind": kind,
            "meaning": meaning,
            "record_hash": record["record_hash"],
        },
    )


def normalize_intake(row: dict[str, Any]) -> dict[str, Any]:
    sample_class = _text(row.get("sample_class")).upper()
    return {
        "row_id": _text(row.get("row_id")),
        "sample_id": _text(row.get("sample_id")),
        "label_id": _text(row.get("label_id")),
        "sample_class": sample_class,
        "panel": _text(row.get("panel")) or CLASS_PANEL.get(sample_class, ""),
        "receipt_temp_c": _number(row.get("receipt_temp_c")),
        "collected_at": _text(row.get("collected_at")),
        "received_at": _text(row.get("received_at")),
        "due_at": _text(row.get("due_at")),
        "result_at": _text(row.get("result_at")),
        "result_value": _number(row.get("result_value")),
        "spec_min": _number(row.get("spec_min")) if row.get("spec_min") is not None else SPEC_MIN,
        "spec_max": _number(row.get("spec_max")) if row.get("spec_max") is not None else SPEC_MAX,
        "exception_type": _text(row.get("exception_type")).upper() or None,
        "synthetic": _flag(row.get("synthetic")) if "synthetic" in row else True,
        "deidentified": _flag(row.get("deidentified")) if "deidentified" in row else True,
    }


def _expected_token(norm: dict[str, Any]) -> str:
    return _token(norm["sample_class"], int(norm["row_id"].split("-")[-1]))


def classify_intake(norm: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    if norm["sample_class"] not in CLASSES:
        return {"ok": False, "code": "HOLD_UNKNOWN_CLASS"}
    expected = _expected_token(norm) if norm["row_id"] else ""
    if not norm["sample_id"] or not norm["label_id"] or norm["exception_type"] == "LABEL" or norm["label_id"] != expected:
        return {"ok": False, "code": "HOLD_LABEL"}
    if (
        norm["receipt_temp_c"] < COLD_MIN_C
        or norm["receipt_temp_c"] > COLD_MAX_C
        or norm["exception_type"] == "TEMPERATURE"
    ):
        return {"ok": False, "code": "HOLD_TEMPERATURE"}
    if norm["sample_id"] in journal["sample_index"] or norm["exception_type"] == "DUPLICATE":
        return {"ok": False, "code": "HOLD_DUPLICATE"}
    if norm["result_at"] > norm["due_at"] or norm["exception_type"] == "LATE":
        return {"ok": False, "code": "HOLD_LATE"}
    if (
        norm["result_value"] < norm["spec_min"]
        or norm["result_value"] > norm["spec_max"]
        or norm["exception_type"] == "OOS"
    ):
        return {"ok": False, "code": "HOLD_OOS"}
    if norm["sample_id"] != expected:
        return {"ok": False, "code": "HOLD_LABEL"}
    return {"ok": True}


def _hold(
    journal: dict[str, Any],
    *,
    row_id: str,
    sample_id: str | None,
    sample_class: str,
    code: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hold = {
        "row_id": row_id,
        "sample_id": sample_id,
        "sample_class": sample_class,
        "code": code,
        "state": "HOLD",
        "testing_started": False,
    }
    if extra:
        hold.update(extra)
    already = next(
        (
            item
            for item in journal["holds"]
            if item.get("row_id") == row_id and item.get("code") == code
        ),
        None,
    )
    if already is not None:
        return {"kind": "HOLD", "duplicate": True, **deepcopy(already)}
    journal["holds"].append(hold)
    _event(journal, "HOLD", hold)
    _esign(
        journal,
        meaning="HOLD recorded; no testing or release",
        actor="SYSTEM-HOLD",
        accession_id_value=row_id,
        kind="HOLD",
    )
    return {"kind": "HOLD", "duplicate": False, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_intake(row)
    acc_id = accession_id(norm["sample_id"], norm["sample_class"], norm["label_id"])
    if acc_id in journal["accessions"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "sample_id": norm["sample_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "sample_id": norm["sample_id"]}
    verdict = classify_intake(norm, journal)
    if not verdict["ok"]:
        extra = {}
        if verdict["code"] == "HOLD_DUPLICATE" and norm["sample_id"] in journal["sample_index"]:
            extra["first_accession_id"] = journal["sample_index"][norm["sample_id"]]
        return _hold(
            journal,
            row_id=norm["row_id"],
            sample_id=norm["sample_id"] or None,
            sample_class=norm["sample_class"],
            code=verdict["code"],
            extra=extra or None,
        )

    record = {
        "accession_id": acc_id,
        "row_id": norm["row_id"],
        "sample_id": norm["sample_id"],
        "label_id": norm["label_id"],
        "sample_class": norm["sample_class"],
        "panel": norm["panel"],
        "receipt_temp_c": norm["receipt_temp_c"],
        "collected_at": norm["collected_at"],
        "received_at": norm["received_at"],
        "due_at": norm["due_at"],
        "result_at": norm["result_at"],
        "result_value": None,
        "spec_min": norm["spec_min"],
        "spec_max": norm["spec_max"],
        "seed_result_value": norm["result_value"],
        "state": "ACCESSIONED",
        "states_seen": ["ACCESSIONED"],
        "schedule_kind": None,
        "destination": None,
        "instrument": None,
        "contract_lab": None,
        "custody": None,
        "result": None,
        "inventory": None,
        "coa": None,
        "released": False,
        "released_by": None,
        "report_status": "BLOCKED_MISSING_RESULT",
        "interface_state": "SIMULATED",
        "interface_live": False,
        "incumbent_lims": "SIMULATED_READ_ONLY",
        "production_write": False,
        "billed": False,
        "material_disposition": False,
        "testing_started": False,
    }
    journal["accessions"][acc_id] = record
    journal["sample_index"][norm["sample_id"]] = acc_id
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "sample_id": norm["sample_id"],
            "sample_class": norm["sample_class"],
            "adapter": "SIM_INCUMBENT_LIMS",
        },
    )
    _esign(
        journal,
        meaning="Synthetic accession recorded; incumbent LIMS remains authoritative",
        actor="SYSTEM-ACCESSION",
        accession_id_value=acc_id,
        kind="ACCESSION",
    )
    return {"kind": "ACCESSION", "accession_id": acc_id, "sample_class": norm["sample_class"]}


def _advance(record: dict[str, Any], state: str) -> None:
    if state not in record["states_seen"]:
        record["states_seen"].append(state)
    record["state"] = state


def record_custody(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record.get("custody"):
        return {"ok": True, "duplicate": True, "state": record["state"]}
    custody = {
        "accession_id": accession_id_value,
        "sample_id": record["sample_id"],
        "from_node": "RECEIVING",
        "to_node": "QC_HOLDING",
        "received_at": record["received_at"],
        "temp_c": record["receipt_temp_c"],
        "adapter": "SIMULATED_CUSTODY",
    }
    custody["digest"] = sha256_hex(custody)
    record["custody"] = custody
    _advance(record, "IN_CUSTODY")
    _event(journal, "CUSTODY", {"accession_id": accession_id_value, "digest": custody["digest"]})
    return {"ok": True, "duplicate": False, "digest": custody["digest"]}


def _assign_destination(valid_index: int) -> dict[str, str]:
    if valid_index < 180:
        instrument = INSTRUMENTS[valid_index % 12]
        return {
            "schedule_kind": "INTERNAL",
            "destination": instrument,
            "instrument": instrument,
            "contract_lab": "",
        }
    lab = CONTRACT_LABS[(valid_index - 180) % 3]
    return {
        "schedule_kind": "EXTERNAL",
        "destination": lab,
        "instrument": "",
        "contract_lab": lab,
    }


def schedule_test(journal: dict[str, Any], accession_id_value: str, valid_index: int) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record.get("schedule_kind"):
        return {"ok": True, "duplicate": True, "destination": record["destination"]}
    assignment = _assign_destination(valid_index)
    record.update(assignment)
    record["testing_started"] = True
    _advance(record, "SCHEDULED")
    _event(
        journal,
        "SCHEDULED",
        {
            "accession_id": accession_id_value,
            "schedule_kind": assignment["schedule_kind"],
            "destination": assignment["destination"],
            "adapter": "SIMULATED_SCHEDULER",
        },
    )
    return {"ok": True, "duplicate": False, **assignment}


def ingest_result(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record.get("result"):
        return {"ok": True, "duplicate": True, "state": record["state"]}
    adapter = "SIMULATED_CONTRACT_LAB" if record["schedule_kind"] == "EXTERNAL" else "SIMULATED_INSTRUMENT"
    result = {
        "accession_id": accession_id_value,
        "sample_id": record["sample_id"],
        "panel": record["panel"],
        "value": record["seed_result_value"],
        "result_at": record["result_at"],
        "destination": record["destination"],
        "adapter": adapter,
        "read_only": True,
    }
    result["digest"] = sha256_hex(result)
    record["result"] = result
    record["result_value"] = record["seed_result_value"]
    record["report_status"] = "BLOCKED_MISSING_COA"
    _advance(record, "RESULTS_INGESTED")
    _event(journal, "RESULT", {"accession_id": accession_id_value, "digest": result["digest"], "adapter": adapter})
    return {"ok": True, "duplicate": False, "digest": result["digest"]}


def record_inventory(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record.get("inventory"):
        return {"ok": True, "duplicate": True}
    kind = {
        "RETAIN": "RETAIN",
        "STABILITY": "STABILITY",
        "RAW": "RAW_RETAIN_SLOT",
        "IN_PROCESS": "IN_PROCESS_RETAIN_SLOT",
        "RELEASE": "RELEASE_RETAIN_SLOT",
    }[record["sample_class"]]
    inventory = {
        "accession_id": accession_id_value,
        "sample_id": record["sample_id"],
        "kind": kind,
        "adapter": "SIMULATED_INVENTORY",
        "disposition": "NONE",
    }
    record["inventory"] = inventory
    _advance(record, "INVENTORY_RECORDED")
    _event(journal, "INVENTORY", {"accession_id": accession_id_value, "kind": kind})
    return {"ok": True, "kind": kind}


def reconcile_coa(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record.get("coa"):
        return {"ok": True, "duplicate": True}
    payload = {
        "accession_id": accession_id_value,
        "sample_id": record["sample_id"],
        "panel": record["panel"],
        "value": record["result_value"],
        "spec_min": record["spec_min"],
        "spec_max": record["spec_max"],
        "custody_digest": record["custody"]["digest"],
        "result_digest": record["result"]["digest"],
    }
    digest = sha256_hex(payload)
    in_spec = record["spec_min"] <= record["result_value"] <= record["spec_max"]
    record["coa"] = {"digest": digest, "in_spec": in_spec, "adapter": "SIMULATED_COA"}
    if not in_spec:
        record["report_status"] = "HOLD_OOS"
        _advance(record, "HOLD")
        return {"ok": False, "code": "HOLD_OOS"}
    _advance(record, "COA_RECONCILED")
    record["report_status"] = "READY_FOR_HUMAN_RELEASE"
    _advance(record, "READY_FOR_HUMAN_RELEASE")
    _event(journal, "COA", {"accession_id": accession_id_value, "digest": digest})
    _esign(
        journal,
        meaning="CoA reconciled on synthetic fixture; release still requires named QA",
        actor="SYSTEM-COA",
        accession_id_value=accession_id_value,
        kind="COA_REVIEW",
    )
    return {"ok": True, "digest": digest}


def advance_valid(journal: dict[str, Any]) -> None:
    valid_ids = sorted(journal["accessions"])
    for acc_id in valid_ids:
        record_custody(journal, acc_id)
    for index, acc_id in enumerate(valid_ids):
        schedule_test(journal, acc_id, index)
        ingest_result(journal, acc_id)
        record_inventory(journal, acc_id)
        reconcile_coa(journal, acc_id)


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
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "report_status": record["report_status"]}
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
    record["released"] = True
    record["released_by"] = _text(actor) or HUMAN_ACTOR
    record["report_status"] = "RELEASED"
    _advance(record, "RELEASED")
    _esign(
        journal,
        meaning="Named human QA release of synthetic fixture record",
        actor=record["released_by"],
        accession_id_value=accession_id_value,
        kind="QA_RELEASE",
    )
    _event(
        journal,
        "RELEASED",
        {"accession_id": accession_id_value, "released_by": record["released_by"]},
    )
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in sorted(journal["accessions"])
    ]


def authorized_human_release(journal: dict[str, Any], actor: str = HUMAN_ACTOR) -> list[dict[str, Any]]:
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


def _compact_accessions(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "accession_id": item["accession_id"],
            "sample_id": item["sample_id"],
            "sample_class": item["sample_class"],
            "panel": item["panel"],
            "state": item["state"],
            "states_seen": item["states_seen"],
            "schedule_kind": item["schedule_kind"],
            "destination": item["destination"],
            "released": item["released"],
            "custody_digest": None if item["custody"] is None else item["custody"]["digest"],
            "result_digest": None if item["result"] is None else item["result"]["digest"],
            "coa_digest": None if item["coa"] is None else item["coa"]["digest"],
        }
        for item in sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
    ]


def _canonical_digests(journal: dict[str, Any]) -> dict[str, str]:
    custody = [
        item["custody"]
        for item in sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
        if item.get("custody")
    ]
    results = [
        item["result"]
        for item in sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
        if item.get("result")
    ]
    return {
        "custody_sha256": sha256_hex(custody),
        "results_sha256": sha256_hex(results),
    }


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any], digests: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "counts": counts,
        "holds": deepcopy(journal["holds"]),
        "accessions": _compact_accessions(journal),
        "esignatures": deepcopy(journal["esignatures"]),
        "events": deepcopy(journal["events"]),
        "digests": digests,
        "adapters": {
            "incumbent_lims": "SIMULATED_READ_ONLY",
            "instruments": "SIMULATED",
            "contract_labs": "SIMULATED",
            "qms": "SIMULATED",
            "delivery": "SIMULATED_NO_WRITE",
            "billing": "SIMULATED_NO_WRITE",
            "material_disposition": "NOT_PERFORMED",
            "part11": "STYLE_ONLY_NOT_VALIDATED",
        },
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    advance_valid(journal)
    autonomous = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)

    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
    hold_codes = sorted(item["code"] for item in journal["holds"])
    unique_hold_codes = sorted(set(hold_codes))
    released = [item for item in accessioned if item["released"]]
    instruments_used = sorted({item["instrument"] for item in accessioned if item.get("instrument")})
    labs_used = sorted({item["contract_lab"] for item in accessioned if item.get("contract_lab")})
    class_counts = {name: 0 for name in CLASSES}
    for item in accessioned:
        class_counts[item["sample_class"]] += 1
    hold_class_counts = {name: 0 for name in CLASSES}
    for item in journal["holds"]:
        hold_class_counts[item["sample_class"]] += 1
    full_path = [
        item
        for item in accessioned
        if item["states_seen"] == list(EXPECTED_STATES)
    ]
    digests = _canonical_digests(journal)
    counts = {
        "input_rows": len(inbound),
        "valid_completed": len(full_path),
        "hold": len(journal["holds"]),
        "accessioned": len(accessioned),
        "human_released": len(released),
        "autonomous_released": 0,
        "instruments": len(instruments_used),
        "contract_labs": len(labs_used),
        "esignatures": len(journal["esignatures"]),
        "testing_started_on_hold": sum(1 for item in journal["holds"] if item.get("testing_started")),
    }
    audit = _audit_payload(journal, counts, digests)
    audit_sha256 = sha256_hex(audit)

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": counts["input_rows"],
        "valid_completed": counts["valid_completed"],
        "hold": counts["hold"],
        "hold_codes": unique_hold_codes,
        "hold_code_counts": {
            code: sum(1 for item in journal["holds"] if item["code"] == code) for code in unique_hold_codes
        },
        "accessioned": counts["accessioned"],
        "human_released": counts["human_released"],
        "autonomous_released": 0,
        "instruments": instruments_used,
        "contract_labs": labs_used,
        "class_counts": class_counts,
        "hold_class_counts": hold_class_counts,
        "accession_ids": [item["accession_id"] for item in accessioned],
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "human_release_effects": human,
        "accessions": accessioned,
        "holds": deepcopy(journal["holds"]),
        "events": deepcopy(journal["events"]),
        "esignatures": deepcopy(journal["esignatures"]),
        "esignature_complete": bool(journal["esignatures"]) and all(
            item.get("record_hash") for item in journal["esignatures"]
        ),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "billing_writes": 0,
        "material_disposition": 0,
        "automatic_releases": 0,
        "autonomous_certification": False,
        "autonomous_release": False,
        "part11_validated": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "custody_sha256": digests["custody_sha256"],
        "results_sha256": digests["results_sha256"],
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
                "autonomous_release_effects",
                "human_release_effects",
                "accessions",
                "events",
                "esignatures",
                "audit",
            }
        }
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    expected = {
        "input_rows": 240,
        "valid_completed": 216,
        "hold": 24,
        "accessioned": 216,
        "human_released": 216,
        "autonomous_released": 0,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            failures.append(f"{key}!={value} actual={result.get(key)}")
    if result.get("hold_codes") != EXPECTED_HOLD_CODES:
        failures.append("hold_codes")
    if result.get("hold_code_counts") != {
        "HOLD_DUPLICATE": 5,
        "HOLD_LABEL": 5,
        "HOLD_LATE": 5,
        "HOLD_OOS": 4,
        "HOLD_TEMPERATURE": 5,
    }:
        failures.append("hold_code_counts")
    if result.get("class_counts") != {
        "RAW": 43,
        "IN_PROCESS": 43,
        "RELEASE": 43,
        "RETAIN": 43,
        "STABILITY": 44,
    }:
        failures.append("class_counts")
    if result.get("hold_class_counts") != {
        "RAW": 5,
        "IN_PROCESS": 5,
        "RELEASE": 5,
        "RETAIN": 5,
        "STABILITY": 4,
    }:
        failures.append("hold_class_counts")
    if result.get("instruments") != list(INSTRUMENTS):
        failures.append("instruments")
    if result.get("contract_labs") != list(CONTRACT_LABS):
        failures.append("contract_labs")
    if len(set(result.get("accession_ids") or [])) != 216:
        failures.append("accession_ids_not_unique")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("billing_writes") != 0:
        failures.append("billing_writes")
    if result.get("material_disposition") != 0:
        failures.append("material_disposition")
    if result.get("automatic_releases") != 0:
        failures.append("automatic_releases")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if result.get("part11_validated") is not False:
        failures.append("part11_validated")
    if result.get("esignature_complete") is not True:
        failures.append("esignature_complete")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    if any(item.get("testing_started") for item in result.get("holds") or []):
        failures.append("hold_started_testing")
    if any(item.get("production_write") or item.get("billed") or item.get("material_disposition") for item in result.get("accessions") or []):
        failures.append("forbidden_side_effects")
    if result.get("custody_sha256") != GOLDEN_CUSTODY_SHA256:
        failures.append("custody_sha256")
    if result.get("results_sha256") != GOLDEN_RESULTS_SHA256:
        failures.append("results_sha256")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "input_rows": 240,
        "valid_completed": 216,
        "hold": 24,
        "accessioned": 216,
        "human_released": 216,
        "autonomous_released": 0,
        "instruments": 12,
        "contract_labs": 3,
    }
    actual = {
        "input_rows": result.get("input_rows"),
        "valid_completed": result.get("valid_completed"),
        "hold": result.get("hold"),
        "accessioned": result.get("accessioned"),
        "human_released": result.get("human_released"),
        "autonomous_released": result.get("autonomous_released"),
        "instruments": len(result.get("instruments") or []),
        "contract_labs": len(result.get("contract_labs") or []),
    }
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
    if first.get("custody_sha256") != second.get("custody_sha256"):
        failures.append("custody_replay_mismatch")
    if first.get("results_sha256") != second.get("results_sha256"):
        failures.append("results_replay_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "command": "python3 roslinct_hopkinton_paperless_qc.py",
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "hold_codes": first.get("hold_codes"),
        "hold_code_counts": first.get("hold_code_counts"),
        "class_counts": first.get("class_counts"),
        "audit_sha256": first.get("audit_sha256"),
        "custody_sha256": first.get("custody_sha256"),
        "results_sha256": first.get("results_sha256"),
        "manifest_sha256": first.get("manifest_sha256"),
        "esignatures": len(first.get("esignatures") or []),
        "replay_added_accessions": replay.get("added_accession_count"),
        "truth_gate": TRUTH_GATE,
        "interfaces": "SIMULATED",
        "part11_validated": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

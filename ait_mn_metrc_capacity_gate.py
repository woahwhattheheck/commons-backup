#!/usr/bin/env python3
"""AIT Minnesota METRC capacity + R&D gate.

Read-only QBench-order ↔ Metrc/state-monitoring package ↔ physical
accession reconciliation. Compliance and R&D queues stay visibly
separate. Source pointers are immutable. Staging is reviewer-controlled.
Named human release only. Adapters never write Metrc/state.

Demand: ait-mn-metrc-capacity-gate-lims-01
Buyer: Adams Independent Testing / Mark Adams

Acceptance: replay 120 synthetic fixtures — 80 valid licensed-compliance,
20 valid R&D, 8 invalid/missing licenses, 6 duplicate package/sample IDs,
6 designation mismatches. PASS only if exactly 100 accession and 20 HOLD;
all 20 R&D remain segregated and cannot enter the compliance-release
queue; replay creates zero duplicates; every record has source
hash/provenance; named human release only.

HOLD / BUILD-AND-VERIFY. Synthetic fixtures and read-only adapters only.
No Metrc/state write, compliance decision, outreach, prospect-facing
demo, or automatic result/CoA release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "ait-mn-metrc-capacity-gate-lims-01"
SCHEMA = "commons-ait-mn-metrc-capacity-gate-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
HUMAN_RELEASER = "RELEASER"
ADAPTER_MODE = "READ_ONLY"

VALID_COMPLIANCE = 80
VALID_RND = 20
INVALID_LICENSE = 8
DUPLICATE_IDS = 6
DESIGNATION_MISMATCH = 6
FIXTURE_ROWS = (
    VALID_COMPLIANCE
    + VALID_RND
    + INVALID_LICENSE
    + DUPLICATE_IDS
    + DESIGNATION_MISMATCH
)
EXPECTED_ACCESSION = VALID_COMPLIANCE + VALID_RND
EXPECTED_HOLD = INVALID_LICENSE + DUPLICATE_IDS + DESIGNATION_MISMATCH

HOLD_CODES = (
    "INVALID_OR_MISSING_LICENSE",
    "DUPLICATE_PACKAGE_OR_SAMPLE",
    "DESIGNATION_MISMATCH",
)

VALID_LICENSES = frozenset(f"MN-LIC-{i:04d}" for i in range(1, VALID_COMPLIANCE + 1))
DESIGNATIONS = frozenset({"COMPLIANCE", "R_AND_D"})


class AdapterWriteDenied(RuntimeError):
    """Read-only adapters refuse every write."""


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def accession_id(package_id: str, sample_id: str, designation: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "package_id": package_id,
            "sample_id": sample_id,
            "designation": designation,
        }
    )
    return "AIT-" + digest[:12]


def _pkg(prefix: str, n: int) -> str:
    return f"1A40MNSYN{prefix}{n:07d}"


def _sample(prefix: str, n: int) -> str:
    return f"AIT-S-{prefix}-{n:04d}"


def _order(prefix: str, n: int) -> str:
    return f"QB-{prefix}-{n:04d}"


def _phys(prefix: str, n: int) -> str:
    return f"AIT-A-{prefix}-{n:04d}"


def _row(
    row_id: str,
    *,
    kind: str,
    designation: str,
    n: int,
    prefix: str,
    license_number: str,
    qbench_designation: str | None = None,
    metrc_designation: str | None = None,
    physical_designation: str | None = None,
    package_id: str | None = None,
    sample_id: str | None = None,
) -> dict[str, Any]:
    package = package_id or _pkg(prefix, n)
    sample = sample_id or _sample(prefix, n)
    qb_des = qbench_designation or designation
    mt_des = metrc_designation or designation
    ph_des = physical_designation or designation
    return {
        "row_id": row_id,
        "kind": kind,
        "qbench": {
            "order_id": _order(prefix, n),
            "sample_id": sample,
            "package_id": package,
            "designation": qb_des,
            "license_number": license_number,
            "lab": "AIT-MN-SYN",
        },
        "metrc": {
            "package_id": package,
            "sample_id": sample,
            "designation": mt_des,
            "license_number": license_number,
            "state": "MN",
            "monitoring": "STATE_READ_ONLY",
        },
        "physical": {
            "accession_id": _phys(prefix, n),
            "sample_id": sample,
            "package_id": package,
            "designation": ph_des,
            "received": True,
        },
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """120-row PASS fixture for ait-mn-metrc-capacity-gate-lims-01."""
    rows: list[dict[str, Any]] = []
    for i in range(1, VALID_COMPLIANCE + 1):
        rows.append(
            _row(
                f"C{i:03d}",
                kind="VALID_COMPLIANCE",
                designation="COMPLIANCE",
                n=i,
                prefix="C",
                license_number=f"MN-LIC-{i:04d}",
            )
        )
    for i in range(1, VALID_RND + 1):
        rows.append(
            _row(
                f"R{i:03d}",
                kind="VALID_RND",
                designation="R_AND_D",
                n=i,
                prefix="R",
                license_number="",
            )
        )
    for i in range(1, 5):
        rows.append(
            _row(
                f"L{i:03d}",
                kind="MISSING_LICENSE",
                designation="COMPLIANCE",
                n=i,
                prefix="L",
                license_number="",
            )
        )
    for i in range(5, INVALID_LICENSE + 1):
        rows.append(
            _row(
                f"L{i:03d}",
                kind="INVALID_LICENSE",
                designation="COMPLIANCE",
                n=i,
                prefix="L",
                license_number=f"XX-VOID-{i:04d}",
            )
        )
    for i in range(1, DUPLICATE_IDS + 1):
        original = rows[i - 1]
        rows.append(
            _row(
                f"D{i:03d}",
                kind="DUPLICATE",
                designation="COMPLIANCE",
                n=900 + i,
                prefix="D",
                license_number=f"MN-LIC-{i:04d}",
                package_id=original["metrc"]["package_id"],
                sample_id=original["physical"]["sample_id"],
            )
        )
    for i in range(1, DESIGNATION_MISMATCH + 1):
        rows.append(
            _row(
                f"M{i:03d}",
                kind="DESIGNATION_MISMATCH",
                designation="COMPLIANCE",
                n=i,
                prefix="M",
                license_number=f"MN-LIC-{i:04d}",
                qbench_designation="COMPLIANCE",
                metrc_designation="R_AND_D" if i % 2 else "COMPLIANCE",
                physical_designation="COMPLIANCE" if i % 2 else "R_AND_D",
            )
        )
    if len(rows) != FIXTURE_ROWS:
        raise RuntimeError("acceptance fixture must be exactly %s rows, got %s" % (FIXTURE_ROWS, len(rows)))
    return rows


class ReadOnlyQBenchAdapter:
    mode = ADAPTER_MODE

    def fetch_order(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(row["qbench"])
        return {"adapter": "qbench", "mode": self.mode, "payload": payload}

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise AdapterWriteDenied("QBench adapter is read-only")


class ReadOnlyMetrcAdapter:
    mode = ADAPTER_MODE

    def fetch_package(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(row["metrc"])
        return {"adapter": "metrc", "mode": self.mode, "payload": payload}

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise AdapterWriteDenied("Metrc/state adapter is read-only")

    def submit_result(self, *_args: Any, **_kwargs: Any) -> None:
        raise AdapterWriteDenied("Metrc/state adapter refuses result/CoA write")


class ReadOnlyPhysicalAdapter:
    mode = ADAPTER_MODE

    def fetch_accession(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(row["physical"])
        return {"adapter": "physical", "mode": self.mode, "payload": payload}

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise AdapterWriteDenied("Physical accession adapter is read-only")


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "accessions": {},
        "holds": [],
        "events": [],
        "seen_package_ids": set(),
        "seen_sample_ids": set(),
        "compliance_queue": [],
        "rnd_queue": [],
        "compliance_release_queue": [],
        "adapters": {
            "qbench": ADAPTER_MODE,
            "metrc": ADAPTER_MODE,
            "physical": ADAPTER_MODE,
        },
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def read_sources(row: dict[str, Any]) -> dict[str, Any]:
    qbench = ReadOnlyQBenchAdapter().fetch_order(row)
    metrc = ReadOnlyMetrcAdapter().fetch_package(row)
    physical = ReadOnlyPhysicalAdapter().fetch_accession(row)
    pointers = {
        "qbench": {
            "id": qbench["payload"]["order_id"],
            "sha256": sha256_hex(qbench["payload"]),
            "adapter": "qbench",
            "mode": ADAPTER_MODE,
        },
        "metrc": {
            "id": metrc["payload"]["package_id"],
            "sha256": sha256_hex(metrc["payload"]),
            "adapter": "metrc",
            "mode": ADAPTER_MODE,
        },
        "physical": {
            "id": physical["payload"]["accession_id"],
            "sha256": sha256_hex(physical["payload"]),
            "adapter": "physical",
            "mode": ADAPTER_MODE,
        },
    }
    return {
        "qbench": qbench["payload"],
        "metrc": metrc["payload"],
        "physical": physical["payload"],
        "source_pointers": pointers,
        "provenance_sha256": sha256_hex(pointers),
    }


def _license_ok(number: str, designation: str) -> bool:
    if designation == "R_AND_D":
        return True
    return number in VALID_LICENSES


def classify_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    sources = read_sources(row)
    qb = sources["qbench"]
    mt = sources["metrc"]
    ph = sources["physical"]
    designations = {qb["designation"], mt["designation"], ph["designation"]}
    package_id = _text(mt.get("package_id")) or _text(qb.get("package_id"))
    sample_id = _text(ph.get("sample_id")) or _text(qb.get("sample_id"))
    license_number = _text(qb.get("license_number")) or _text(mt.get("license_number"))

    base = {
        "row_id": _text(row.get("row_id")),
        "package_id": package_id,
        "sample_id": sample_id,
        "license_number": license_number or None,
        "source_pointers": sources["source_pointers"],
        "provenance_sha256": sources["provenance_sha256"],
    }

    if len(designations) != 1 or designations == {""} or not designations.issubset(DESIGNATIONS):
        return {"ok": False, "code": "DESIGNATION_MISMATCH", "designation": None, **base}

    designation = next(iter(designations))
    if not _license_ok(license_number, designation):
        return {"ok": False, "code": "INVALID_OR_MISSING_LICENSE", "designation": designation, **base}

    acc_id = accession_id(package_id, sample_id, designation)
    existing_acc = journal["accessions"].get(acc_id)
    if existing_acc is not None:
        if existing_acc.get("provenance_sha256") == sources["provenance_sha256"]:
            return {
                "ok": True,
                "replay": True,
                "designation": designation,
                "accession_id": acc_id,
                "queue": existing_acc["queue"],
                **base,
            }
        return {"ok": False, "code": "DUPLICATE_PACKAGE_OR_SAMPLE", "designation": designation, **base}
    if package_id in journal["seen_package_ids"] or sample_id in journal["seen_sample_ids"]:
        return {"ok": False, "code": "DUPLICATE_PACKAGE_OR_SAMPLE", "designation": designation, **base}

    return {
        "ok": True,
        "replay": False,
        "designation": designation,
        "accession_id": acc_id,
        "queue": "rnd" if designation == "R_AND_D" else "compliance",
        **base,
    }


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    verdict = classify_row(journal, row)
    if not verdict["ok"]:
        hold = {
            "row_id": verdict["row_id"],
            "package_id": verdict["package_id"],
            "sample_id": verdict["sample_id"],
            "code": verdict["code"],
            "designation": verdict.get("designation"),
            "license_number": verdict.get("license_number"),
            "source_pointers": verdict["source_pointers"],
            "provenance_sha256": verdict["provenance_sha256"],
            "queue": "hold",
            "state": "HOLD",
        }
        fingerprint = sha256_hex(
            {key: hold[key] for key in ("row_id", "package_id", "sample_id", "code", "provenance_sha256")}
        )
        existing = {sha256_hex({key: item[key] for key in ("row_id", "package_id", "sample_id", "code", "provenance_sha256")}) for item in journal["holds"]}
        if fingerprint not in existing:
            journal["holds"].append(hold)
            _event(journal, "HOLD", {"row_id": hold["row_id"], "code": hold["code"]})
        return {"kind": "HOLD", "duplicate": fingerprint in existing, **hold}

    acc_id = verdict["accession_id"]
    existing_acc = journal["accessions"].get(acc_id)
    if existing_acc is not None:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "sample_id": verdict["sample_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "sample_id": verdict["sample_id"]}

    record = {
        "accession_id": acc_id,
        "row_id": verdict["row_id"],
        "package_id": verdict["package_id"],
        "sample_id": verdict["sample_id"],
        "designation": verdict["designation"],
        "queue": verdict["queue"],
        "license_number": verdict["license_number"],
        "source_pointers": verdict["source_pointers"],
        "provenance_sha256": verdict["provenance_sha256"],
        "state": "ACCESSIONED",
        "staged": False,
        "released": False,
        "released_by": None,
        "coa_released": False,
        "interface_state": ADAPTER_MODE,
        "interface_live": False,
    }
    journal["accessions"][acc_id] = record
    journal["seen_package_ids"].add(verdict["package_id"])
    journal["seen_sample_ids"].add(verdict["sample_id"])
    if verdict["queue"] == "rnd":
        journal["rnd_queue"].append(acc_id)
    else:
        journal["compliance_queue"].append(acc_id)
    _event(
        journal,
        "ACCESSION",
        {"accession_id": acc_id, "queue": verdict["queue"], "designation": verdict["designation"]},
    )
    return {"kind": "ACCESSION", "accession_id": acc_id, "queue": verdict["queue"]}


def stage_for_release(
    journal: dict[str, Any],
    accession_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record["designation"] == "R_AND_D" or record["queue"] == "rnd":
        _event(journal, "STAGE_DENIED", {"accession_id": accession_id_value, "code": "RND_SEGREGATED"})
        return {"ok": False, "code": "RND_SEGREGATED", "queue": "rnd"}
    if _text(actor_role).upper() != HUMAN_RELEASER or not _text(actor):
        _event(journal, "STAGE_DENIED", {"accession_id": accession_id_value, "code": "NAMED_HUMAN_REQUIRED"})
        return {"ok": False, "code": "NAMED_HUMAN_REQUIRED"}
    record["staged"] = True
    record["state"] = "STAGED"
    _event(journal, "STAGED", {"accession_id": accession_id_value, "actor": _text(actor)})
    return {"ok": True, "state": "STAGED", "queue": "compliance"}


def release_to_compliance(
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
    if role != HUMAN_RELEASER or not _text(actor):
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "actor_role": role or None,
            },
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "released": False}
    if record["designation"] == "R_AND_D" or record["queue"] == "rnd":
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "RND_SEGREGATED"},
        )
        return {
            "ok": False,
            "code": "RND_SEGREGATED",
            "queue": "rnd",
            "compliance_release": False,
        }
    if not record.get("staged"):
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "NOT_STAGED"},
        )
        return {"ok": False, "code": "NOT_STAGED"}
    if record["released"]:
        return {"ok": True, "duplicate": True, "queue": "compliance_release"}
    record["released"] = True
    record["released_by"] = _text(actor)
    record["state"] = "RELEASED_TO_COMPLIANCE_QUEUE"
    record["coa_released"] = False
    if accession_id_value not in journal["compliance_release_queue"]:
        journal["compliance_release_queue"].append(accession_id_value)
    _event(
        journal,
        "COMPLIANCE_RELEASE_QUEUED",
        {"accession_id": accession_id_value, "released_by": record["released_by"]},
    )
    return {
        "ok": True,
        "duplicate": False,
        "queue": "compliance_release",
        "coa_released": False,
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "accession_id": record["accession_id"],
        "row_id": record["row_id"],
        "package_id": record["package_id"],
        "sample_id": record["sample_id"],
        "designation": record["designation"],
        "queue": record["queue"],
        "state": record["state"],
        "staged": record["staged"],
        "released": record["released"],
        "released_by": record["released_by"],
        "coa_released": record["coa_released"],
        "source_pointers": deepcopy(record["source_pointers"]),
        "provenance_sha256": record["provenance_sha256"],
        "interface_state": record["interface_state"],
        "interface_live": record["interface_live"],
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = []
    rnd_blocked = []
    for acc_id, record in journal["accessions"].items():
        autonomous.append(
            release_to_compliance(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        )
        if record["designation"] == "R_AND_D":
            rnd_blocked.append(
                release_to_compliance(journal, acc_id, actor_role=HUMAN_RELEASER, actor="reviewer-1")
            )

    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["row_id"])
    holds = deepcopy(journal["holds"])
    hold_codes = sorted(item["code"] for item in holds)
    compliance_ids = [acc_id for acc_id in journal["compliance_queue"]]
    rnd_ids = [acc_id for acc_id in journal["rnd_queue"]]

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "accessioned": len(accessioned),
        "held": len(holds),
        "hold_codes": sorted(set(hold_codes)),
        "hold_code_counts": {
            code: sum(1 for item in holds if item["code"] == code) for code in HOLD_CODES
        },
        "compliance_queue": len(compliance_ids),
        "rnd_queue": len(rnd_ids),
        "compliance_release_queue": len(journal["compliance_release_queue"]),
        "rnd_in_compliance_release": sum(
            1
            for acc_id in journal["compliance_release_queue"]
            if journal["accessions"][acc_id]["designation"] == "R_AND_D"
        ),
        "accession_ids": [item["accession_id"] for item in accessioned],
        "released_coas": 0,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "rnd_release_effects": rnd_blocked,
        "accessions": [_public_record(item) for item in accessioned],
        "holds": holds,
        "compliance_ids": compliance_ids,
        "rnd_ids": rnd_ids,
        "interface_live": False,
        "interfaces": ADAPTER_MODE,
        "metrc_write": False,
        "state_write": False,
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


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


def _has_provenance(record: dict[str, Any]) -> bool:
    pointers = record.get("source_pointers") or {}
    if not isinstance(pointers, dict):
        return False
    for key in ("qbench", "metrc", "physical"):
        node = pointers.get(key) or {}
        if len(_text(node.get("id"))) < 1:
            return False
        if len(_text(node.get("sha256"))) != 64:
            return False
        if node.get("mode") != ADAPTER_MODE:
            return False
    return len(_text(record.get("provenance_sha256"))) == 64


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != FIXTURE_ROWS:
        failures.append("input_rows!=120")
    if result.get("accessioned") != EXPECTED_ACCESSION:
        failures.append("accessioned!=100")
    if result.get("held") != EXPECTED_HOLD:
        failures.append("held!=20")
    counts = result.get("hold_code_counts") or {}
    if counts.get("INVALID_OR_MISSING_LICENSE") != INVALID_LICENSE:
        failures.append("license_holds!=8")
    if counts.get("DUPLICATE_PACKAGE_OR_SAMPLE") != DUPLICATE_IDS:
        failures.append("duplicate_holds!=6")
    if counts.get("DESIGNATION_MISMATCH") != DESIGNATION_MISMATCH:
        failures.append("mismatch_holds!=6")
    if result.get("compliance_queue") != VALID_COMPLIANCE:
        failures.append("compliance_queue!=80")
    if result.get("rnd_queue") != VALID_RND:
        failures.append("rnd_queue!=20")
    if result.get("compliance_release_queue") != 0:
        failures.append("compliance_release_queue!=0")
    if result.get("rnd_in_compliance_release") != 0:
        failures.append("rnd_leaked_into_compliance_release")
    if len(set(result.get("accession_ids") or [])) != EXPECTED_ACCESSION:
        failures.append("accession_ids_not_unique")
    if result.get("released_coas") != 0:
        failures.append("released_coas!=0")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != ADAPTER_MODE:
        failures.append("interfaces")
    if result.get("metrc_write") is not False:
        failures.append("metrc_write")
    if result.get("state_write") is not False:
        failures.append("state_write")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    if not all(item.get("code") == "RND_SEGREGATED" for item in result.get("rnd_release_effects") or []):
        failures.append("rnd_not_segregated")
    if len(result.get("rnd_release_effects") or []) != VALID_RND:
        failures.append("rnd_release_effects!=20")
    for record in result.get("accessions") or []:
        if not _has_provenance(record):
            failures.append("accession_missing_provenance")
            break
        if record.get("designation") == "R_AND_D" and record.get("queue") != "rnd":
            failures.append("rnd_not_on_rnd_queue")
            break
        if record.get("designation") == "COMPLIANCE" and record.get("queue") != "compliance":
            failures.append("compliance_not_on_compliance_queue")
            break
    for record in result.get("holds") or []:
        if not _has_provenance(record):
            failures.append("hold_missing_provenance")
            break
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "accessioned": first.get("accessioned"),
        "held": first.get("held"),
        "hold_code_counts": first.get("hold_code_counts"),
        "compliance_queue": first.get("compliance_queue"),
        "rnd_queue": first.get("rnd_queue"),
        "compliance_release_queue": first.get("compliance_release_queue"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "replay_added_holds": replay.get("added_holds"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

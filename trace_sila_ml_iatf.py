#!/usr/bin/env python3
"""TRACE-SILA-ML-IATF-v0 — Sila Moses Lake IATF evidence rail.

Read-only MES/QMS/analytics export adapters. Raw-material-to-batch
genealogy. Exception ownership. IATF-ready evidence manifests.
Incumbents remain authoritative.

Demand: trace-sila-ml-iatf-lims-01
Buyer: Sila Moses Lake / Rosendo Alvarado
Fixture: SILA-ML-01

Four batches, 12 unique analytics records plus one duplicate.
B002 wrong unit, B003 synthetic OOS, B004 missing parent.
Output: 12 canonical results, one duplicate log, four dossiers.
B001=REVIEW_READY, B002=HOLD_UNIT_MISMATCH, B003=HOLD_SPEC_OOS,
B004=HOLD_GENEALOGY_GAP. Byte-identical replay.

AquaTrace HOLD / BUILD-AND-VERIFY. Interfaces stay simulated.
No writes, recipes, or real thresholds before buyer/vendor validation.
Named human disposition is mandatory. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "trace-sila-ml-iatf-lims-01"
SCHEMA = "commons-trace-sila-ml-iatf-lims/v1"
BUILD = "TRACE-SILA-ML-IATF-v0"
FIXTURE_ID = "SILA-ML-01"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
HUMAN_DISPOSITION = "HUMAN_DISPOSITION"

# Fixture-only method dictionary. Not a live QMS threshold.
METHODS: dict[str, dict[str, Any]] = {
    "PSD_D50": {
        "unit": "um",
        "lo": 8.0,
        "hi": 12.0,
        "owner": "QMS_METROLOGY",
        "threshold_source": "FIXTURE_ONLY",
    },
    "MOISTURE": {
        "unit": "wt_pct",
        "lo": 0.0,
        "hi": 0.50,
        "owner": "QMS_METROLOGY",
        "threshold_source": "FIXTURE_ONLY",
    },
    "IMPURITY_NA": {
        "unit": "ppm",
        "lo": 0.0,
        "hi": 50.0,
        "owner": "QUALITY_ENGINEER",
        "threshold_source": "FIXTURE_ONLY",
    },
}

HOLD_CODES = (
    "HOLD_UNIT_MISMATCH",
    "HOLD_SPEC_OOS",
    "HOLD_GENEALOGY_GAP",
)

HOLD_OWNERS = {
    "HOLD_UNIT_MISMATCH": "QMS_METROLOGY",
    "HOLD_SPEC_OOS": "QUALITY_ENGINEER",
    "HOLD_GENEALOGY_GAP": "MES_GENEALOGY",
}

BATCH_STATUS_ORDER = (
    "HOLD_GENEALOGY_GAP",
    "HOLD_UNIT_MISMATCH",
    "HOLD_SPEC_OOS",
    "REVIEW_READY",
)


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def result_identity(row: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "fixture_id": FIXTURE_ID,
            "result_id": _text(row.get("result_id")),
            "batch_id": _text(row.get("batch_id")),
            "method": _text(row.get("method")),
        }
    )


class ReadOnlyAdapter:
    """Simulated read-only export. Writes are denied and audited."""

    def __init__(self, name: str, payload: Any) -> None:
        self.name = name
        self.live = False
        self._payload = deepcopy(payload)
        self.write_attempts: list[dict[str, Any]] = []

    def export(self) -> Any:
        return deepcopy(self._payload)

    def write(self, action: str, payload: Any = None) -> dict[str, Any]:
        denial = {
            "ok": False,
            "code": "ADAPTER_WRITE_DENIED",
            "adapter": self.name,
            "action": _text(action) or "WRITE",
            "live": False,
            "incumbent_authoritative": True,
        }
        self.write_attempts.append(denial)
        return denial


def build_mes_batches() -> list[dict[str, Any]]:
    return [
        {
            "batch_id": "B001",
            "parent_lot": "RM-SILA-A",
            "site": "SILA-MOSES-LAKE-SYN",
            "product_family": "silicon_anode_synthetic",
        },
        {
            "batch_id": "B002",
            "parent_lot": "RM-SILA-B",
            "site": "SILA-MOSES-LAKE-SYN",
            "product_family": "silicon_anode_synthetic",
        },
        {
            "batch_id": "B003",
            "parent_lot": "RM-SILA-C",
            "site": "SILA-MOSES-LAKE-SYN",
            "product_family": "silicon_anode_synthetic",
        },
        {
            "batch_id": "B004",
            "parent_lot": "",
            "site": "SILA-MOSES-LAKE-SYN",
            "product_family": "silicon_anode_synthetic",
        },
    ]


def build_analytics_records() -> list[dict[str, Any]]:
    """SILA-ML-01: 12 unique analytics plus one duplicate of B001-A01."""
    unique = [
        {
            "result_id": "B001-A01",
            "batch_id": "B001",
            "method": "PSD_D50",
            "value": 10.0,
            "unit": "um",
            "instrument": "PSA-SYN-01",
        },
        {
            "result_id": "B001-A02",
            "batch_id": "B001",
            "method": "MOISTURE",
            "value": 0.20,
            "unit": "wt_pct",
            "instrument": "MOIST-SYN-01",
        },
        {
            "result_id": "B001-A03",
            "batch_id": "B001",
            "method": "IMPURITY_NA",
            "value": 12.0,
            "unit": "ppm",
            "instrument": "ICP-SYN-01",
        },
        {
            "result_id": "B002-A01",
            "batch_id": "B002",
            "method": "PSD_D50",
            "value": 10.1,
            "unit": "um",
            "instrument": "PSA-SYN-01",
        },
        {
            "result_id": "B002-A02",
            "batch_id": "B002",
            "method": "MOISTURE",
            "value": 0.18,
            "unit": "wt_pct",
            "instrument": "MOIST-SYN-01",
        },
        {
            "result_id": "B002-A03",
            "batch_id": "B002",
            "method": "IMPURITY_NA",
            "value": 15.0,
            "unit": "wt_pct",
            "instrument": "ICP-SYN-01",
        },
        {
            "result_id": "B003-A01",
            "batch_id": "B003",
            "method": "PSD_D50",
            "value": 10.2,
            "unit": "um",
            "instrument": "PSA-SYN-01",
        },
        {
            "result_id": "B003-A02",
            "batch_id": "B003",
            "method": "MOISTURE",
            "value": 0.22,
            "unit": "wt_pct",
            "instrument": "MOIST-SYN-01",
        },
        {
            "result_id": "B003-A03",
            "batch_id": "B003",
            "method": "IMPURITY_NA",
            "value": 88.0,
            "unit": "ppm",
            "instrument": "ICP-SYN-01",
        },
        {
            "result_id": "B004-A01",
            "batch_id": "B004",
            "method": "PSD_D50",
            "value": 9.8,
            "unit": "um",
            "instrument": "PSA-SYN-01",
        },
        {
            "result_id": "B004-A02",
            "batch_id": "B004",
            "method": "MOISTURE",
            "value": 0.19,
            "unit": "wt_pct",
            "instrument": "MOIST-SYN-01",
        },
        {
            "result_id": "B004-A03",
            "batch_id": "B004",
            "method": "IMPURITY_NA",
            "value": 11.0,
            "unit": "ppm",
            "instrument": "ICP-SYN-01",
        },
    ]
    duplicate = deepcopy(unique[0])
    duplicate["row_kind"] = "DUPLICATE"
    rows = unique + [duplicate]
    if len(unique) != 12:
        raise RuntimeError("SILA-ML-01 unique analytics must be 12, got %s" % len(unique))
    if len(rows) != 13:
        raise RuntimeError("SILA-ML-01 inbound analytics must be 13, got %s" % len(rows))
    return rows


def build_acceptance_fixture() -> dict[str, Any]:
    return {
        "fixture_id": FIXTURE_ID,
        "demand_id": DEMAND_ID,
        "batches": build_mes_batches(),
        "methods": deepcopy(METHODS),
        "analytics": build_analytics_records(),
        "threshold_source": "FIXTURE_ONLY",
        "synthetic": True,
        "de_identified": True,
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "fixture_id": FIXTURE_ID,
        "results": {},
        "duplicates": [],
        "exceptions": [],
        "dossiers": {},
        "events": [],
        "write_denials": [],
        "disposition": {},
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def classify_result(row: dict[str, Any], parent_lot: str) -> dict[str, Any]:
    method = _text(row.get("method"))
    unit = _text(row.get("unit"))
    value = _number(row.get("value"))
    spec = METHODS.get(method)
    holds: list[str] = []
    if not _text(parent_lot):
        holds.append("HOLD_GENEALOGY_GAP")
    if spec is None or unit != spec["unit"]:
        holds.append("HOLD_UNIT_MISMATCH")
    if spec is not None and value is not None:
        if value < float(spec["lo"]) or value > float(spec["hi"]):
            holds.append("HOLD_SPEC_OOS")
    elif spec is not None and value is None:
        holds.append("HOLD_SPEC_OOS")
    hold = next((code for code in BATCH_STATUS_ORDER if code in holds), None)
    return {
        "result_id": _text(row.get("result_id")),
        "batch_id": _text(row.get("batch_id")),
        "method": method,
        "value": value,
        "unit": unit,
        "expected_unit": None if spec is None else spec["unit"],
        "instrument": _text(row.get("instrument")),
        "parent_lot": _text(parent_lot) or None,
        "holds": holds,
        "hold": hold,
        "status": hold or "CANONICAL",
        "threshold_source": "FIXTURE_ONLY",
        "identity": result_identity(row),
    }


def batch_status(holds: list[str]) -> str:
    for code in BATCH_STATUS_ORDER:
        if code in holds:
            return code
    return "REVIEW_READY"


def ingest_result(
    journal: dict[str, Any],
    row: dict[str, Any],
    parent_lot: str,
    prior_identities: set[str] | None = None,
) -> dict[str, Any]:
    verdict = classify_result(row, parent_lot)
    identity = verdict["identity"]
    existing = journal["results"].get(identity)
    if existing is not None:
        already_known = identity in (prior_identities or set())
        dup = {
            "result_id": verdict["result_id"],
            "batch_id": verdict["batch_id"],
            "method": verdict["method"],
            "identity": identity,
            "code": "DUPLICATE_ANALYTICS",
        }
        fingerprint = sha256_hex(dup)
        seen = {sha256_hex(item) for item in journal["duplicates"]}
        if already_known or fingerprint in seen:
            _event(journal, "REPLAY_NOOP", {"identity": identity, "kind": "RESULT"})
            return {"kind": "REPLAY_NOOP", "identity": identity, "result_id": verdict["result_id"]}
        journal["duplicates"].append(dup)
        _event(journal, "DUPLICATE", dup)
        return {"kind": "DUPLICATE", "identity": identity, "result_id": verdict["result_id"]}

    record = {
        "result_id": verdict["result_id"],
        "batch_id": verdict["batch_id"],
        "method": verdict["method"],
        "value": verdict["value"],
        "unit": verdict["unit"],
        "expected_unit": verdict["expected_unit"],
        "instrument": verdict["instrument"],
        "parent_lot": verdict["parent_lot"],
        "hold": verdict["hold"],
        "status": verdict["status"],
        "threshold_source": "FIXTURE_ONLY",
        "identity": identity,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    journal["results"][identity] = record
    _event(
        journal,
        "CANONICAL_RESULT",
        {
            "result_id": record["result_id"],
            "batch_id": record["batch_id"],
            "status": record["status"],
        },
    )
    if record["hold"]:
        exception = {
            "batch_id": record["batch_id"],
            "result_id": record["result_id"],
            "code": record["hold"],
            "owner": HOLD_OWNERS[record["hold"]],
            "method": record["method"],
            "open": True,
        }
        journal["exceptions"].append(exception)
        _event(journal, "EXCEPTION", exception)
    return {"kind": "CANONICAL", "identity": identity, "result_id": record["result_id"]}


def rebuild_dossiers(journal: dict[str, Any], batches: list[dict[str, Any]]) -> None:
    by_batch: dict[str, list[dict[str, Any]]] = {}
    for record in journal["results"].values():
        by_batch.setdefault(record["batch_id"], []).append(record)
    dossiers = {}
    for batch in batches:
        batch_id = _text(batch.get("batch_id"))
        rows = sorted(by_batch.get(batch_id, []), key=lambda item: item["result_id"])
        holds = [item["hold"] for item in rows if item.get("hold")]
        status = batch_status(holds)
        exceptions = [
            item for item in journal["exceptions"] if item["batch_id"] == batch_id
        ]
        body = {
            "batch_id": batch_id,
            "parent_lot": _text(batch.get("parent_lot")) or None,
            "site": _text(batch.get("site")),
            "product_family": _text(batch.get("product_family")),
            "status": status,
            "result_ids": [item["result_id"] for item in rows],
            "result_count": len(rows),
            "exceptions": deepcopy(exceptions),
            "released": False,
            "released_by": None,
            "disposition_state": "HOLD" if status != "REVIEW_READY" else "REVIEW_READY",
            "incumbent_authoritative": True,
            "interface_live": False,
        }
        body["dossier_sha256"] = sha256_hex(
            {key: value for key, value in body.items() if key != "dossier_sha256"}
        )
        dossiers[batch_id] = body
    journal["dossiers"] = dossiers


def bind_adapters(fixture: dict[str, Any] | None = None) -> dict[str, ReadOnlyAdapter]:
    inbound = deepcopy(fixture if fixture is not None else build_acceptance_fixture())
    return {
        "mes": ReadOnlyAdapter("MES_EXPORT", inbound["batches"]),
        "qms": ReadOnlyAdapter("QMS_EXPORT", inbound["methods"]),
        "analytics": ReadOnlyAdapter("ANALYTICS_EXPORT", inbound["analytics"]),
    }


def ingest_fixture(
    journal: dict[str, Any],
    fixture: dict[str, Any] | None = None,
    adapters: dict[str, ReadOnlyAdapter] | None = None,
) -> list[dict[str, Any]]:
    inbound = deepcopy(fixture if fixture is not None else build_acceptance_fixture())
    bound = adapters or bind_adapters(inbound)
    batches = list(bound["mes"].export())
    analytics = list(bound["analytics"].export())
    parent_by_batch = {_text(item.get("batch_id")): _text(item.get("parent_lot")) for item in batches}
    prior_identities = set(journal["results"])
    effects = []
    for row in analytics:
        batch_id = _text(row.get("batch_id"))
        effects.append(
            ingest_result(
                journal,
                row,
                parent_by_batch.get(batch_id, ""),
                prior_identities,
            )
        )
    rebuild_dossiers(journal, batches)
    return effects


def attempt_adapter_writes(adapters: dict[str, ReadOnlyAdapter], journal: dict[str, Any]) -> list[dict[str, Any]]:
    denials = []
    for adapter in adapters.values():
        denial = adapter.write("PRODUCTION_MUTATION", {"demand_id": DEMAND_ID})
        denials.append(denial)
        journal["write_denials"].append(denial)
        _event(journal, "ADAPTER_WRITE_DENIED", denial)
    recipe = adapters["qms"].write("RECIPE_CHANGE", {"recipe": "FORBIDDEN"})
    denials.append(recipe)
    journal["write_denials"].append(recipe)
    return denials


def release_dossier(
    journal: dict[str, Any],
    batch_id: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    dossier = journal["dossiers"].get(batch_id)
    if dossier is None:
        return {"ok": False, "code": "UNKNOWN_BATCH"}
    role = _text(actor_role).upper()
    if role != HUMAN_DISPOSITION:
        _event(
            journal,
            "DISPOSITION_DENIED",
            {
                "batch_id": batch_id,
                "code": "AUTONOMOUS_DISPOSITION_DENIED",
                "actor_role": role or None,
            },
        )
        return {
            "ok": False,
            "code": "AUTONOMOUS_DISPOSITION_DENIED",
            "status": dossier["status"],
        }
    if dossier["status"] != "REVIEW_READY":
        _event(
            journal,
            "DISPOSITION_DENIED",
            {
                "batch_id": batch_id,
                "code": "HUMAN_DISPOSITION_REQUIRED",
                "status": dossier["status"],
            },
        )
        return {
            "ok": False,
            "code": "HUMAN_DISPOSITION_REQUIRED",
            "status": dossier["status"],
        }
    if dossier["released"]:
        return {"ok": True, "duplicate": True, "status": "RELEASED"}
    dossier["released"] = True
    dossier["released_by"] = _text(actor) or "human-disposition"
    dossier["disposition_state"] = "RELEASED"
    journal["disposition"][batch_id] = {
        "batch_id": batch_id,
        "released_by": dossier["released_by"],
        "role": HUMAN_DISPOSITION,
    }
    _event(
        journal,
        "RELEASED",
        {"batch_id": batch_id, "released_by": dossier["released_by"]},
    )
    return {"ok": True, "duplicate": False, "status": "RELEASED"}


def audit_export(journal: dict[str, Any]) -> dict[str, Any]:
    results = sorted(journal["results"].values(), key=lambda item: item["result_id"])
    dossiers = [journal["dossiers"][key] for key in sorted(journal["dossiers"])]
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "build": BUILD,
        "fixture_id": FIXTURE_ID,
        "truth_gate": TRUTH_GATE,
        "results": deepcopy(results),
        "duplicates": deepcopy(journal["duplicates"]),
        "exceptions": deepcopy(journal["exceptions"]),
        "dossiers": deepcopy(dossiers),
        "events": deepcopy(journal["events"]),
        "write_denials": deepcopy(journal["write_denials"]),
        "disposition": deepcopy(journal["disposition"]),
    }
    body["audit_sha256"] = sha256_hex(body)
    return body


def run_gate(fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    inbound = deepcopy(fixture if fixture is not None else build_acceptance_fixture())
    adapters = bind_adapters(inbound)
    journal = empty_journal()
    effects = ingest_fixture(journal, inbound, adapters)
    write_denials = attempt_adapter_writes(adapters, journal)
    autonomous = [
        release_dossier(journal, batch_id, actor_role="SYSTEM", actor="autonomous")
        for batch_id in sorted(journal["dossiers"])
    ]
    results = sorted(journal["results"].values(), key=lambda item: item["result_id"])
    dossiers = [journal["dossiers"][key] for key in sorted(journal["dossiers"])]
    statuses = {item["batch_id"]: item["status"] for item in dossiers}
    audit = audit_export(journal)
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "build": BUILD,
        "fixture_id": FIXTURE_ID,
        "truth_gate": TRUTH_GATE,
        "input_analytics": len(inbound["analytics"]),
        "unique_analytics": 12,
        "canonical_results": len(results),
        "duplicate_log": len(journal["duplicates"]),
        "dossier_count": len(dossiers),
        "statuses": statuses,
        "result_ids": [item["result_id"] for item in results],
        "duplicate_result_ids": [item["result_id"] for item in journal["duplicates"]],
        "exceptions": deepcopy(journal["exceptions"]),
        "exception_codes": sorted({item["code"] for item in journal["exceptions"]}),
        "exception_owners": sorted({item["owner"] for item in journal["exceptions"]}),
        "dossiers": deepcopy(dossiers),
        "results": deepcopy(results),
        "duplicates": deepcopy(journal["duplicates"]),
        "effects": effects,
        "autonomous_disposition_effects": autonomous,
        "write_denials": write_denials,
        "released_dossiers": 0,
        "interface_live": False,
        "interfaces": "SIMULATED_READONLY",
        "adapter_writes": False,
        "recipes_mutated": False,
        "real_thresholds": False,
        "threshold_source": "FIXTURE_ONLY",
        "incumbent_authoritative": True,
        "autonomous_certification": False,
        "autonomous_disposition": False,
        "human_disposition_mandatory": True,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "audit_sha256": audit["audit_sha256"],
        "dossier_hashes": {item["batch_id"]: item["dossier_sha256"] for item in dossiers},
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def replay_into(
    journal: dict[str, Any],
    fixture: dict[str, Any] | None = None,
    adapters: dict[str, ReadOnlyAdapter] | None = None,
) -> dict[str, Any]:
    before_results = set(journal["results"])
    before_dups = len(journal["duplicates"])
    effects = ingest_fixture(journal, fixture, adapters)
    added = set(journal["results"]) - before_results
    return {
        "added_results": sorted(added),
        "added_result_count": len(added),
        "added_duplicates": len(journal["duplicates"]) - before_dups,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "DUPLICATE"),
        "canonical_results": len(journal["results"]),
        "duplicate_count": len(journal["duplicates"]),
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("fixture_id") != FIXTURE_ID:
        failures.append("fixture_id")
    if result.get("input_analytics") != 13:
        failures.append("input_analytics!=13")
    if result.get("canonical_results") != 12:
        failures.append("canonical_results!=12")
    if result.get("duplicate_log") != 1:
        failures.append("duplicate_log!=1")
    if result.get("dossier_count") != 4:
        failures.append("dossier_count!=4")
    expected = {
        "B001": "REVIEW_READY",
        "B002": "HOLD_UNIT_MISMATCH",
        "B003": "HOLD_SPEC_OOS",
        "B004": "HOLD_GENEALOGY_GAP",
    }
    if result.get("statuses") != expected:
        failures.append("statuses")
    if result.get("duplicate_result_ids") != ["B001-A01"]:
        failures.append("duplicate_result_ids")
    if len(result.get("result_ids") or []) != 12:
        failures.append("result_ids")
    if len(set(result.get("result_ids") or [])) != 12:
        failures.append("result_ids_not_unique")
    if result.get("released_dossiers") != 0:
        failures.append("released_dossiers!=0")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED_READONLY":
        failures.append("interfaces")
    if result.get("adapter_writes") is not False:
        failures.append("adapter_writes")
    if result.get("recipes_mutated") is not False:
        failures.append("recipes_mutated")
    if result.get("real_thresholds") is not False:
        failures.append("real_thresholds")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_disposition") is not False:
        failures.append("autonomous_disposition")
    if result.get("human_disposition_mandatory") is not True:
        failures.append("human_disposition_mandatory")
    if result.get("incumbent_authoritative") is not True:
        failures.append("incumbent_authoritative")
    if not all(
        item.get("code") == "AUTONOMOUS_DISPOSITION_DENIED"
        for item in result.get("autonomous_disposition_effects") or []
    ):
        failures.append("autonomous_disposition_not_denied")
    if not all(item.get("code") == "ADAPTER_WRITE_DENIED" for item in result.get("write_denials") or []):
        failures.append("write_not_denied")
    if len(result.get("write_denials") or []) < 3:
        failures.append("write_denials_missing")
    if not result.get("audit_sha256") or len(result.get("audit_sha256") or "") != 64:
        failures.append("audit_sha256")
    if not result.get("manifest_sha256") or len(result.get("manifest_sha256") or "") != 64:
        failures.append("manifest_sha256")
    hashes = result.get("dossier_hashes") or {}
    if set(hashes) != {"B001", "B002", "B003", "B004"}:
        failures.append("dossier_hashes")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    adapters = bind_adapters()
    ingest_fixture(journal, None, adapters)
    replay = replay_into(journal, None, adapters)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if replay.get("added_result_count") != 0:
        failures.append("replay_added_results")
    if replay.get("added_duplicates") != 0:
        failures.append("replay_added_duplicates")
    if first.get("dossier_hashes") != second.get("dossier_hashes"):
        failures.append("dossier_hash_mismatch")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "audit_sha256": first.get("audit_sha256"),
        "canonical_results": first.get("canonical_results"),
        "duplicate_log": first.get("duplicate_log"),
        "dossier_count": first.get("dossier_count"),
        "statuses": first.get("statuses"),
        "released_dossiers": first.get("released_dossiers"),
        "replay_added_results": replay.get("added_result_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""ElevateBio BaseCamp Pittsburgh greenfield LIMS replication pack.

Demand: elevatebio-pittsburgh-replication-lims-01
Buyer: ElevateBio BaseCamp Pittsburgh / Katie Shannon

Port buyer-approved Waltham master data and interface contracts into a
site-isolated Pittsburgh tenant. QC/MSAT workflows, namespace isolation,
two-site governance, exact role matrix, named-human batch disposition.

400 synthetic two-site samples through signed Waltham/Pittsburgh fixtures.
Approved methods produce identical calculations/routing. Pittsburgh
identifiers stay isolated. Cross-site access is denied. Seeded
method/version and permission defects HOLD. Replay changes zero records.
Disposition requires a named human signature.

AquaTrace HOLD / BUILD-AND-VERIFY. MES/EBR/LIMS/monitoring/QMS stay
simulated/read-only. No production tenant change. No validation claim
until a buyer-approved golden round trip. No PHI. No outreach.
PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "elevatebio-pittsburgh-replication-lims-01"
SCHEMA = "commons-elevatebio-pittsburgh-replication-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "ElevateBio BaseCamp Pittsburgh / Katie Shannon"
SITES = ("WALTHAM", "PITTSBURGH")
WORKFLOWS = ("QC", "MSAT")
NAMESPACES = {
    "WALTHAM": "eb.waltham.lims",
    "PITTSBURGH": "eb.pittsburgh.lims",
}
SITE_PREFIX = {"WALTHAM": "WAL", "PITTSBURGH": "PIT"}
TENANTS = {
    "WALTHAM": "eb-wal-tenant-01",
    "PITTSBURGH": "eb-pit-tenant-01",
}
INTERFACES = ("MES", "EBR", "LIMS", "MONITORING", "QMS")
HUMAN_WAL = "wal-qa-human-01"
HUMAN_PIT = "pit-qa-human-01"
FIXTURE_SIGNERS = {
    "WALTHAM": "wal-master-signer-01",
    "PITTSBURGH": "pit-replica-signer-01",
}

# Buyer-approved Waltham master methods. Pittsburgh must compute identically.
APPROVED_METHODS: dict[str, dict[str, Any]] = {
    "QC_IDENTITY": {
        "version": 3,
        "workflow": "QC",
        "route": "QC_IDENTITY_PANEL",
        "factor": 1.0,
    },
    "QC_POTENCY": {
        "version": 2,
        "workflow": "QC",
        "route": "QC_POTENCY_PANEL",
        "factor": 1.25,
    },
    "QC_STERILITY": {
        "version": 1,
        "workflow": "QC",
        "route": "QC_STERILITY_PANEL",
        "factor": 1.0,
    },
    "MSAT_PROCESS": {
        "version": 4,
        "workflow": "MSAT",
        "route": "MSAT_PROCESS_PANEL",
        "factor": 0.8,
    },
    "MSAT_IN_PROCESS": {
        "version": 2,
        "workflow": "MSAT",
        "route": "MSAT_IPC_PANEL",
        "factor": 0.95,
    },
}
QC_METHODS = ("QC_IDENTITY", "QC_POTENCY", "QC_STERILITY")
MSAT_METHODS = ("MSAT_PROCESS", "MSAT_IN_PROCESS")

# Exact role matrix. Missing pairs are denied.
ROLE_MATRIX: dict[tuple[str, str, str], str] = {}
for _role, _site, _workflow, _perm in (
    ("WAL_QC", "WALTHAM", "QC", "ACCESS"),
    ("WAL_MSAT", "WALTHAM", "MSAT", "ACCESS"),
    ("WAL_QA", "WALTHAM", "QC", "DISPOSE"),
    ("WAL_QA", "WALTHAM", "MSAT", "DISPOSE"),
    ("PIT_QC", "PITTSBURGH", "QC", "ACCESS"),
    ("PIT_MSAT", "PITTSBURGH", "MSAT", "ACCESS"),
    ("PIT_QA", "PITTSBURGH", "QC", "DISPOSE"),
    ("PIT_QA", "PITTSBURGH", "MSAT", "DISPOSE"),
    ("TWO_SITE_GOV", "WALTHAM", "QC", "GOVERN"),
    ("TWO_SITE_GOV", "WALTHAM", "MSAT", "GOVERN"),
    ("TWO_SITE_GOV", "PITTSBURGH", "QC", "GOVERN"),
    ("TWO_SITE_GOV", "PITTSBURGH", "MSAT", "GOVERN"),
):
    ROLE_MATRIX[(_role, _site, _workflow)] = _perm

HOLD_CODES = ("HOLD_METHOD_VERSION", "HOLD_PERMISSION")
EXPECTED_HOLD_CODES = ["HOLD_METHOD_VERSION", "HOLD_PERMISSION"]
GOLDEN_AUDIT_SHA256 = "b9d13ff324911223d626b20372fcc94c01280bded27d66acd346519881d7b679"
GOLDEN_CALC_SHA256 = "30e5041178ffc58d42b15545865dd05076c5eb89441a9a12a721dfc27c428ca9"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def signed_interface_contracts() -> dict[str, dict[str, Any]]:
    """Waltham-approved interface contracts. Pittsburgh ports the same bodies."""
    contracts: dict[str, dict[str, Any]] = {}
    for name in INTERFACES:
        body = {
            "adapter": name,
            "demand_id": DEMAND_ID,
            "mode": "SIMULATED_READ_ONLY",
            "ops": ["export"],
            "writes": False,
            "source": "WALTHAM_MASTER",
        }
        contracts[name] = {
            "body": body,
            "sha256": sha256_hex(body),
            "live": False,
        }
    return contracts


INTERFACE_CONTRACTS = signed_interface_contracts()
GOLDEN_INTERFACE_SHA256 = sha256_hex(
    {name: INTERFACE_CONTRACTS[name]["sha256"] for name in INTERFACES}
)


def access_permission(role: str, site: str, workflow: str) -> str | None:
    return ROLE_MATRIX.get((_text(role).upper(), _text(site).upper(), _text(workflow).upper()))


def role_may(role: str, site: str, workflow: str, action: str) -> bool:
    perm = access_permission(role, site, workflow)
    if perm is None:
        return False
    if action == "ACCESS":
        return perm in {"ACCESS", "DISPOSE"}
    if action == "DISPOSE":
        return perm == "DISPOSE"
    if action == "GOVERN":
        return perm == "GOVERN"
    return False


def calculate(method: str, version: int, raw_value: float) -> dict[str, Any]:
    spec = APPROVED_METHODS[method]
    if int(version) != int(spec["version"]):
        return {"ok": False, "code": "HOLD_METHOD_VERSION"}
    value = round(float(raw_value) * float(spec["factor"]), 4)
    return {
        "ok": True,
        "method": method,
        "version": int(version),
        "raw_value": float(raw_value),
        "value": value,
        "route": spec["route"],
        "workflow": spec["workflow"],
    }


def sample_id(site: str, workflow: str, index: int) -> str:
    return f"SYN-{SITE_PREFIX[site]}-{workflow}-{index:03d}"


def batch_id(site: str, workflow: str, batch_index: int) -> str:
    return f"{SITE_PREFIX[site]}-{workflow}-B{batch_index:02d}"


def _analyst_role(site: str, workflow: str) -> str:
    return f"{SITE_PREFIX[site]}_{workflow}"


def _qa_role(site: str) -> str:
    return f"{SITE_PREFIX[site]}_QA"


def _human_for(site: str) -> str:
    return HUMAN_WAL if site == "WALTHAM" else HUMAN_PIT


def _method_for(workflow: str, index: int) -> str:
    pool = QC_METHODS if workflow == "QC" else MSAT_METHODS
    return pool[(index - 1) % len(pool)]


def _raw_for(index: int) -> float:
    return float(10 + (index % 10))


def _row(
    site: str,
    workflow: str,
    index: int,
    *,
    exception: str | None = None,
) -> dict[str, Any]:
    method = _method_for(workflow, index)
    spec = APPROVED_METHODS[method]
    version = spec["version"]
    accessor = _analyst_role(site, workflow)
    if exception == "METHOD_VERSION":
        version = spec["version"] + 1
    if exception == "PERMISSION":
        other = "PITTSBURGH" if site == "WALTHAM" else "WALTHAM"
        accessor = _analyst_role(other, workflow)
    return {
        "row_id": f"{SITE_PREFIX[site]}-{workflow}-{index:03d}",
        "site": site,
        "tenant": TENANTS[site],
        "namespace": NAMESPACES[site],
        "workflow": workflow,
        "sample_id": sample_id(site, workflow, index),
        "method": method,
        "method_version": version,
        "raw_value": _raw_for(index),
        "accessor_role": accessor,
        "exception_type": exception,
        "synthetic": True,
        "deidentified": True,
        "phi": False,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """400-row signed two-site fixture.

    Per site: 144 valid QC + 48 valid MSAT + 4 method/version + 4 permission.
    Waltham 200 + Pittsburgh 200. Seeded defects HOLD.
    """
    rows: list[dict[str, Any]] = []
    for site in SITES:
        for index in range(1, 145):
            rows.append(_row(site, "QC", index))
        for index in range(145, 149):
            rows.append(_row(site, "QC", index, exception="METHOD_VERSION"))
        for index in range(149, 153):
            rows.append(_row(site, "QC", index, exception="PERMISSION"))
        for index in range(1, 49):
            rows.append(_row(site, "MSAT", index))
    if len(rows) != 400:
        raise RuntimeError("acceptance fixture must be exactly 400 rows, got %s" % len(rows))
    by_site = {name: 0 for name in SITES}
    exceptions = {"METHOD_VERSION": 0, "PERMISSION": 0}
    for row in rows:
        by_site[row["site"]] += 1
        if row["exception_type"]:
            exceptions[row["exception_type"]] += 1
    if by_site != {"WALTHAM": 200, "PITTSBURGH": 200}:
        raise RuntimeError("site split must be 200/200, got %s" % by_site)
    if exceptions != {"METHOD_VERSION": 8, "PERMISSION": 8}:
        raise RuntimeError("exception split must be 8/8, got %s" % exceptions)
    return rows


def signed_site_fixture(site: str) -> dict[str, Any]:
    signer = FIXTURE_SIGNERS[site]
    body = {
        "demand_id": DEMAND_ID,
        "site": site,
        "tenant": TENANTS[site],
        "namespace": NAMESPACES[site],
        "methods": deepcopy(APPROVED_METHODS),
        "interfaces": {name: INTERFACE_CONTRACTS[name]["sha256"] for name in INTERFACES},
        "role_matrix": sorted(
            f"{role}|{site_name}|{workflow}|{perm}"
            for (role, site_name, workflow), perm in ROLE_MATRIX.items()
        ),
        "signed_by": signer,
        "signed": True,
    }
    return {
        **body,
        "sha256": sha256_hex(body),
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "tenants": {
            site: {
                "site": site,
                "tenant": TENANTS[site],
                "namespace": NAMESPACES[site],
                "accessions": {},
                "batches": {},
                "sample_index": {},
            }
            for site in SITES
        },
        "holds": [],
        "events": [],
        "signatures": [],
        "write_denials": [],
        "interface_live": False,
        "production_tenant_change": 0,
        "validation_claimed": False,
        "buyer_approved_golden_round_trip": False,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    prev = journal["events"][-1]["record_hash"] if journal["events"] else "GENESIS"
    body = {"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)}
    body["prev_hash"] = prev
    body["record_hash"] = sha256_hex(
        {"prev": prev, "body": {k: v for k, v in body.items() if k not in {"prev_hash", "record_hash"}}}
    )
    journal["events"].append(body)


def _sign(
    journal: dict[str, Any],
    *,
    kind: str,
    actor: str,
    meaning: str,
    target: str,
) -> dict[str, Any]:
    prev = journal["signatures"][-1]["record_hash"] if journal["signatures"] else "SIG-GENESIS"
    record = {
        "seq": len(journal["signatures"]) + 1,
        "kind": kind,
        "actor": actor,
        "meaning": meaning,
        "target": target,
        "named_human": True,
        "signed_at": "2026-08-31T12:00:00Z",
    }
    record["prev_hash"] = prev
    record["record_hash"] = sha256_hex(
        {"prev": prev, "body": {k: v for k, v in record.items() if k not in {"prev_hash", "record_hash"}}}
    )
    journal["signatures"].append(record)
    _event(journal, "SIGN", {"kind": kind, "actor": actor, "target": target, "record_hash": record["record_hash"]})
    return record


def bind_signed_fixtures(journal: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fixtures = {site: signed_site_fixture(site) for site in SITES}
    for site, fixture in fixtures.items():
        _sign(
            journal,
            kind="FIXTURE",
            actor=fixture["signed_by"],
            meaning="Signed %s fixture for two-site replication" % site,
            target=fixture["sha256"],
        )
    journal["fixtures"] = fixtures
    return fixtures


class ReadOnlyAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.live = False
        self.contract = deepcopy(INTERFACE_CONTRACTS[name])
        self.write_attempts: list[dict[str, Any]] = []

    def export(self) -> dict[str, Any]:
        return deepcopy(self.contract)

    def write(self, action: str, payload: Any = None) -> dict[str, Any]:
        denial = {
            "ok": False,
            "code": "ADAPTER_WRITE_DENIED",
            "adapter": self.name,
            "action": _text(action) or "WRITE",
            "live": False,
        }
        self.write_attempts.append(denial)
        return denial


def bind_adapters() -> dict[str, ReadOnlyAdapter]:
    return {name: ReadOnlyAdapter(name) for name in INTERFACES}


def attempt_adapter_writes(
    adapters: dict[str, ReadOnlyAdapter], journal: dict[str, Any]
) -> list[dict[str, Any]]:
    denials = []
    for name, adapter in adapters.items():
        denial = adapter.write("MUTATE_TENANT", {"tenant": TENANTS["PITTSBURGH"]})
        denials.append(denial)
        journal["write_denials"].append(denial)
        _event(journal, "ADAPTER_WRITE_DENIED", {"adapter": name, "code": denial["code"]})
    return denials


def normalize_intake(row: dict[str, Any]) -> dict[str, Any]:
    site = _text(row.get("site")).upper()
    workflow = _text(row.get("workflow")).upper()
    return {
        "row_id": _text(row.get("row_id")),
        "site": site,
        "tenant": _text(row.get("tenant")) or TENANTS.get(site, ""),
        "namespace": _text(row.get("namespace")) or NAMESPACES.get(site, ""),
        "workflow": workflow,
        "sample_id": _text(row.get("sample_id")),
        "method": _text(row.get("method")).upper(),
        "method_version": int(row.get("method_version") or 0),
        "raw_value": float(row.get("raw_value") or 0),
        "accessor_role": _text(row.get("accessor_role")).upper(),
        "exception_type": _text(row.get("exception_type")).upper() or None,
        "synthetic": True,
        "deidentified": True,
        "phi": False,
    }


def classify_intake(norm: dict[str, Any]) -> dict[str, Any]:
    if norm["site"] not in SITES:
        return {"ok": False, "code": "HOLD_PERMISSION"}
    if norm["namespace"] != NAMESPACES[norm["site"]]:
        return {"ok": False, "code": "HOLD_PERMISSION"}
    if not norm["sample_id"].startswith("SYN-%s-" % SITE_PREFIX[norm["site"]]):
        return {"ok": False, "code": "HOLD_PERMISSION"}
    if norm["method"] not in APPROVED_METHODS:
        return {"ok": False, "code": "HOLD_METHOD_VERSION"}
    spec = APPROVED_METHODS[norm["method"]]
    if spec["workflow"] != norm["workflow"]:
        return {"ok": False, "code": "HOLD_METHOD_VERSION"}
    if (
        norm["method_version"] != spec["version"]
        or norm["exception_type"] == "METHOD_VERSION"
    ):
        return {"ok": False, "code": "HOLD_METHOD_VERSION"}
    if not role_may(norm["accessor_role"], norm["site"], norm["workflow"], "ACCESS"):
        return {"ok": False, "code": "HOLD_PERMISSION"}
    if norm["exception_type"] == "PERMISSION":
        return {"ok": False, "code": "HOLD_PERMISSION"}
    return {"ok": True}


def _hold(journal: dict[str, Any], norm: dict[str, Any], code: str) -> dict[str, Any]:
    hold = {
        "row_id": norm["row_id"],
        "sample_id": norm["sample_id"],
        "site": norm["site"],
        "namespace": norm["namespace"],
        "workflow": norm["workflow"],
        "method": norm["method"],
        "method_version": norm["method_version"],
        "accessor_role": norm["accessor_role"],
        "code": code,
        "state": "HOLD",
    }
    already = next(
        (
            item
            for item in journal["holds"]
            if item.get("row_id") == norm["row_id"] and item.get("code") == code
        ),
        None,
    )
    if already is not None:
        return {"kind": "HOLD", "duplicate": True, **deepcopy(already)}
    journal["holds"].append(hold)
    _event(journal, "HOLD", hold)
    return {"kind": "HOLD", "duplicate": False, **hold}


def accession_key(norm: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "namespace": norm["namespace"],
            "sample_id": norm["sample_id"],
            "method": norm["method"],
            "method_version": norm["method_version"],
        }
    )


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_intake(row)
    tenant = journal["tenants"][norm["site"]]
    key = accession_key(norm)
    if key in tenant["accessions"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": key, "sample_id": norm["sample_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": key, "sample_id": norm["sample_id"]}
    verdict = classify_intake(norm)
    if not verdict["ok"]:
        return _hold(journal, norm, verdict["code"])
    calc = calculate(norm["method"], norm["method_version"], norm["raw_value"])
    if not calc["ok"]:
        return _hold(journal, norm, calc["code"])
    record = {
        "accession_id": key,
        "row_id": norm["row_id"],
        "site": norm["site"],
        "tenant": norm["tenant"],
        "namespace": norm["namespace"],
        "workflow": norm["workflow"],
        "sample_id": norm["sample_id"],
        "method": norm["method"],
        "method_version": norm["method_version"],
        "raw_value": norm["raw_value"],
        "value": calc["value"],
        "route": calc["route"],
        "accessor_role": norm["accessor_role"],
        "state": "ACCESSIONED",
        "disposed": False,
        "disposed_by": None,
        "interface_live": False,
        "phi": False,
    }
    tenant["accessions"][key] = record
    tenant["sample_index"][norm["sample_id"]] = key
    _event(
        journal,
        "ACCESSIONED",
        {
            "accession_id": key,
            "sample_id": norm["sample_id"],
            "site": norm["site"],
            "namespace": norm["namespace"],
            "route": calc["route"],
            "value": calc["value"],
        },
    )
    return {"kind": "ACCESSION", "accession_id": key, "sample_id": norm["sample_id"]}


def lookup_sample(journal: dict[str, Any], sample_id_value: str, role: str) -> dict[str, Any]:
    """Namespace isolation: a role may only see its own site identifiers."""
    for site in SITES:
        tenant = journal["tenants"][site]
        if sample_id_value in tenant["sample_index"]:
            record = tenant["accessions"][tenant["sample_index"][sample_id_value]]
            if not role_may(role, site, record["workflow"], "ACCESS"):
                _event(
                    journal,
                    "CROSS_SITE_DENIED",
                    {
                        "sample_id": sample_id_value,
                        "role": role,
                        "site": site,
                        "code": "CROSS_SITE_DENIED",
                    },
                )
                return {"ok": False, "code": "CROSS_SITE_DENIED"}
            return {"ok": True, "record": deepcopy(record)}
    return {"ok": False, "code": "UNKNOWN_SAMPLE"}


def assign_batches(journal: dict[str, Any]) -> list[dict[str, Any]]:
    assigned = []
    for site in SITES:
        tenant = journal["tenants"][site]
        by_workflow: dict[str, list[dict[str, Any]]] = {"QC": [], "MSAT": []}
        for item in sorted(tenant["accessions"].values(), key=lambda rec: rec["sample_id"]):
            by_workflow[item["workflow"]].append(item)
        for workflow, records in by_workflow.items():
            for offset in range(0, len(records), 24):
                chunk = records[offset : offset + 24]
                if not chunk:
                    continue
                batch_index = (offset // 24) + 1
                bid = batch_id(site, workflow, batch_index)
                batch = {
                    "batch_id": bid,
                    "site": site,
                    "namespace": NAMESPACES[site],
                    "workflow": workflow,
                    "sample_ids": [item["sample_id"] for item in chunk],
                    "accession_ids": [item["accession_id"] for item in chunk],
                    "disposed": False,
                    "disposed_by": None,
                    "state": "READY_FOR_HUMAN_DISPOSITION",
                }
                tenant["batches"][bid] = batch
                assigned.append(batch)
                _event(journal, "BATCH_READY", {"batch_id": bid, "site": site, "count": len(chunk)})
    return assigned


def dispose_batch(
    journal: dict[str, Any],
    batch_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    batch = None
    tenant = None
    for site in SITES:
        if batch_id_value in journal["tenants"][site]["batches"]:
            tenant = journal["tenants"][site]
            batch = tenant["batches"][batch_id_value]
            break
    if batch is None:
        return {"ok": False, "code": "UNKNOWN_BATCH"}
    role = _text(actor_role).upper()
    if role == "SYSTEM" or not _text(actor) or role != _qa_role(batch["site"]):
        _event(
            journal,
            "DISPOSITION_DENIED",
            {
                "batch_id": batch_id_value,
                "code": "AUTONOMOUS_DISPOSITION_DENIED" if role == "SYSTEM" or not _text(actor) else "HOLD_PERMISSION",
                "actor_role": role or None,
            },
        )
        return {
            "ok": False,
            "code": "AUTONOMOUS_DISPOSITION_DENIED" if role == "SYSTEM" or not _text(actor) else "HOLD_PERMISSION",
        }
    if not role_may(role, batch["site"], batch["workflow"], "DISPOSE"):
        _event(
            journal,
            "DISPOSITION_DENIED",
            {"batch_id": batch_id_value, "code": "HOLD_PERMISSION", "actor_role": role},
        )
        return {"ok": False, "code": "HOLD_PERMISSION"}
    if batch["disposed"]:
        return {"ok": True, "duplicate": True}
    batch["disposed"] = True
    batch["disposed_by"] = _text(actor)
    batch["state"] = "DISPOSED"
    for acc_id in batch["accession_ids"]:
        record = tenant["accessions"][acc_id]
        record["disposed"] = True
        record["disposed_by"] = batch["disposed_by"]
        record["state"] = "DISPOSED"
    _sign(
        journal,
        kind="BATCH_DISPOSITION",
        actor=batch["disposed_by"],
        meaning="Named-human batch disposition",
        target=batch_id_value,
    )
    _event(
        journal,
        "DISPOSED",
        {"batch_id": batch_id_value, "disposed_by": batch["disposed_by"], "site": batch["site"]},
    )
    return {"ok": True, "duplicate": False}


def attempt_autonomous_disposition(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for site in SITES:
        for bid in sorted(journal["tenants"][site]["batches"]):
            effects.append(dispose_batch(journal, bid, actor_role="SYSTEM", actor="autonomous"))
    return effects


def authorized_human_disposition(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for site in SITES:
        actor = _human_for(site)
        role = _qa_role(site)
        for bid in sorted(journal["tenants"][site]["batches"]):
            effects.append(dispose_batch(journal, bid, actor_role=role, actor=actor))
    return effects


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before_acc = sum(len(journal["tenants"][site]["accessions"]) for site in SITES)
    before_holds = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in inbound]
    after_acc = sum(len(journal["tenants"][site]["accessions"]) for site in SITES)
    return {
        "added_accession_count": after_acc - before_acc,
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": after_acc,
        "hold_count": len(journal["holds"]),
    }


def _all_accessions(journal: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for site in SITES:
        records.extend(journal["tenants"][site]["accessions"].values())
    return sorted(records, key=lambda item: item["sample_id"])


def _all_batches(journal: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for site in SITES:
        records.extend(journal["tenants"][site]["batches"].values())
    return sorted(records, key=lambda item: item["batch_id"])


def paired_calculations(journal: dict[str, Any]) -> list[dict[str, Any]]:
    """Same method/version/raw on both sites must match value and route."""
    wal = {
        (item["workflow"], item["method"], item["raw_value"]): item
        for item in journal["tenants"]["WALTHAM"]["accessions"].values()
    }
    pairs = []
    for pit in journal["tenants"]["PITTSBURGH"]["accessions"].values():
        key = (pit["workflow"], pit["method"], pit["raw_value"])
        wal_item = wal.get(key)
        if wal_item is None:
            continue
        pairs.append(
            {
                "method": pit["method"],
                "version": pit["method_version"],
                "raw_value": pit["raw_value"],
                "waltham_value": wal_item["value"],
                "pittsburgh_value": pit["value"],
                "waltham_route": wal_item["route"],
                "pittsburgh_route": pit["route"],
                "identical": wal_item["value"] == pit["value"] and wal_item["route"] == pit["route"],
            }
        )
    return pairs


def _audit_payload(
    journal: dict[str, Any],
    counts: dict[str, Any],
    adapters: dict[str, ReadOnlyAdapter],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "counts": counts,
        "holds": deepcopy(journal["holds"]),
        "accessions": [
            {
                "sample_id": item["sample_id"],
                "site": item["site"],
                "namespace": item["namespace"],
                "method": item["method"],
                "method_version": item["method_version"],
                "value": item["value"],
                "route": item["route"],
                "disposed": item["disposed"],
            }
            for item in _all_accessions(journal)
        ],
        "batches": [
            {
                "batch_id": item["batch_id"],
                "site": item["site"],
                "disposed": item["disposed"],
                "disposed_by": item["disposed_by"],
            }
            for item in _all_batches(journal)
        ],
        "signatures": deepcopy(journal["signatures"]),
        "events": deepcopy(journal["events"]),
        "interfaces": {name: adapters[name].contract["sha256"] for name in INTERFACES},
        "adapters": {name: "SIMULATED_READ_ONLY" for name in INTERFACES},
        "validation_claimed": False,
        "buyer_approved_golden_round_trip": False,
        "production_tenant_change": 0,
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    fixtures = bind_signed_fixtures(journal)
    adapters = bind_adapters()
    write_denials = attempt_adapter_writes(adapters, journal)
    effects = [ingest_row(journal, row) for row in inbound]
    assign_batches(journal)
    autonomous = attempt_autonomous_disposition(journal)
    human = authorized_human_disposition(journal)
    pairs = paired_calculations(journal)
    accessions = _all_accessions(journal)
    batches = _all_batches(journal)
    hold_codes = sorted(set(item["code"] for item in journal["holds"]))
    wal_ids = [item["sample_id"] for item in accessions if item["site"] == "WALTHAM"]
    pit_ids = [item["sample_id"] for item in accessions if item["site"] == "PITTSBURGH"]
    cross_denied = []
    if pit_ids:
        cross_denied.append(lookup_sample(journal, pit_ids[0], "WAL_QC"))
    if wal_ids:
        cross_denied.append(lookup_sample(journal, wal_ids[0], "PIT_QC"))
    gov_denied = []
    if wal_ids:
        gov_denied.append(lookup_sample(journal, wal_ids[0], "TWO_SITE_GOV"))
    counts = {
        "input_rows": len(inbound),
        "valid_completed": len(accessions),
        "hold": len(journal["holds"]),
        "waltham": sum(1 for item in inbound if item["site"] == "WALTHAM"),
        "pittsburgh": sum(1 for item in inbound if item["site"] == "PITTSBURGH"),
        "human_disposed_batches": sum(1 for item in batches if item["disposed"]),
        "autonomous_disposed": 0,
        "identical_pairs": sum(1 for item in pairs if item["identical"]),
        "interfaces": len(INTERFACES),
    }
    audit = _audit_payload(journal, counts, adapters)
    calc_digest = sha256_hex(
        [
            {
                "sample_id": item["sample_id"],
                "method": item["method"],
                "version": item["method_version"],
                "value": item["value"],
                "route": item["route"],
            }
            for item in accessions
        ]
    )
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": counts["input_rows"],
        "valid_completed": counts["valid_completed"],
        "hold": counts["hold"],
        "hold_codes": hold_codes,
        "hold_code_counts": {
            code: sum(1 for item in journal["holds"] if item["code"] == code) for code in hold_codes
        },
        "waltham": counts["waltham"],
        "pittsburgh": counts["pittsburgh"],
        "human_disposed_batches": counts["human_disposed_batches"],
        "autonomous_disposed": 0,
        "identical_pairs": counts["identical_pairs"],
        "pair_count": len(pairs),
        "pairs_all_identical": bool(pairs) and all(item["identical"] for item in pairs),
        "pittsburgh_ids_isolated": all(item.startswith("SYN-PIT-") for item in pit_ids)
        and not any(item.startswith("SYN-WAL-") for item in pit_ids),
        "waltham_ids_isolated": all(item.startswith("SYN-WAL-") for item in wal_ids)
        and not any(item.startswith("SYN-PIT-") for item in wal_ids),
        "namespaces": deepcopy(NAMESPACES),
        "tenants": deepcopy(TENANTS),
        "role_matrix": [
            {"role": role, "site": site, "workflow": workflow, "perm": perm}
            for (role, site, workflow), perm in sorted(ROLE_MATRIX.items())
        ],
        "fixtures": {
            site: {"signed_by": fixtures[site]["signed_by"], "sha256": fixtures[site]["sha256"]}
            for site in SITES
        },
        "interface_hashes": {name: INTERFACE_CONTRACTS[name]["sha256"] for name in INTERFACES},
        "interface_hash_bundle": GOLDEN_INTERFACE_SHA256,
        "accessions": accessions,
        "holds": deepcopy(journal["holds"]),
        "batches": batches,
        "pairs": pairs,
        "effects": effects,
        "autonomous_disposition_effects": autonomous,
        "human_disposition_effects": human,
        "cross_site_denials": cross_denied,
        "governor_sample_denials": gov_denied,
        "write_denials": write_denials,
        "signatures": deepcopy(journal["signatures"]),
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED_READ_ONLY",
        "production_tenant_change": 0,
        "validation_claimed": False,
        "buyer_approved_golden_round_trip": False,
        "autonomous_disposition": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "calc_sha256": calc_digest,
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
    }
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    expected = {
        "input_rows": 400,
        "valid_completed": 384,
        "hold": 16,
        "waltham": 200,
        "pittsburgh": 200,
        "human_disposed_batches": 16,
        "autonomous_disposed": 0,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            failures.append(f"{key}!={value} actual={result.get(key)}")
    if result.get("hold_codes") != EXPECTED_HOLD_CODES:
        failures.append("hold_codes")
    if result.get("hold_code_counts") != {"HOLD_METHOD_VERSION": 8, "HOLD_PERMISSION": 8}:
        failures.append("hold_code_counts")
    if result.get("pairs_all_identical") is not True:
        failures.append("pairs_not_identical")
    if result.get("pittsburgh_ids_isolated") is not True:
        failures.append("pittsburgh_ids_not_isolated")
    if result.get("waltham_ids_isolated") is not True:
        failures.append("waltham_ids_not_isolated")
    if result.get("interface_hash_bundle") != GOLDEN_INTERFACE_SHA256:
        failures.append("interface_hash_bundle")
    if result.get("interface_hashes") != {name: INTERFACE_CONTRACTS[name]["sha256"] for name in INTERFACES}:
        failures.append("interface_hashes")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("production_tenant_change") != 0:
        failures.append("production_tenant_change")
    if result.get("validation_claimed") is not False:
        failures.append("validation_claimed")
    if result.get("buyer_approved_golden_round_trip") is not False:
        failures.append("buyer_approved_golden_round_trip")
    if result.get("autonomous_disposition") is not False:
        failures.append("autonomous_disposition")
    if not all(item.get("code") == "AUTONOMOUS_DISPOSITION_DENIED" for item in result.get("autonomous_disposition_effects") or []):
        failures.append("autonomous_disposition_not_denied")
    if not all(item.get("ok") for item in result.get("human_disposition_effects") or []):
        failures.append("human_disposition_incomplete")
    if not all(item.get("code") == "CROSS_SITE_DENIED" for item in result.get("cross_site_denials") or []):
        failures.append("cross_site_not_denied")
    if not all(item.get("code") == "CROSS_SITE_DENIED" for item in result.get("governor_sample_denials") or []):
        failures.append("governor_saw_sample")
    if not all(item.get("code") == "ADAPTER_WRITE_DENIED" for item in result.get("write_denials") or []):
        failures.append("adapter_write_not_denied")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result.get("calc_sha256") != GOLDEN_CALC_SHA256:
        failures.append("calc_sha256")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "input_rows": 400,
        "valid_completed": 384,
        "hold": 16,
        "waltham": 200,
        "pittsburgh": 200,
        "human_disposed_batches": 16,
        "autonomous_disposed": 0,
        "identical_pairs": result.get("pair_count"),
        "interfaces": 5,
    }
    actual = {
        "input_rows": result.get("input_rows"),
        "valid_completed": result.get("valid_completed"),
        "hold": result.get("hold"),
        "waltham": result.get("waltham"),
        "pittsburgh": result.get("pittsburgh"),
        "human_disposed_batches": result.get("human_disposed_batches"),
        "autonomous_disposed": result.get("autonomous_disposed"),
        "identical_pairs": result.get("identical_pairs"),
        "interfaces": len(result.get("interface_hashes") or {}),
    }
    return {"expected": expected, "actual": actual, "match": expected == actual}


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    bind_signed_fixtures(journal)
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if first.get("calc_sha256") != second.get("calc_sha256"):
        failures.append("calc_replay_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "command": "python3 elevatebio_pittsburgh_replication.py",
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "hold_codes": first.get("hold_codes"),
        "hold_code_counts": first.get("hold_code_counts"),
        "audit_sha256": first.get("audit_sha256"),
        "calc_sha256": first.get("calc_sha256"),
        "interface_hash_bundle": first.get("interface_hash_bundle"),
        "interface_hashes": first.get("interface_hashes"),
        "fixtures": first.get("fixtures"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "truth_gate": TRUTH_GATE,
        "interfaces": "SIMULATED_READ_ONLY",
        "validation_claimed": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

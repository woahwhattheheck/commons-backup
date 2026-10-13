#!/usr/bin/env python3
"""OrganaBio multi-site donor-to-CoA federation (synthetic).

Demand: organabio-multisite-donor-coa-lims-01
Buyer pairing: OrganaBio / Christopher B. Goodman

Donor eligibility, collection, accession, aliquot lineage, PBMC
processing, cryopreservation, QC, inventory, shipment, and Excellos
legacy-ID reconciliation across five synthetic sites.

240 valid collections produce 1,200 aliquots (five vials each).
The seed also includes 24 consent/eligibility failures that never
accession and 40 donor-recall cases. Every valid aliquot has exactly
one immutable donor-to-vial lineage. Site namespaces never collide.
Replay is idempotent. No material disposition without a named human
quality release.

HOLD / BUILD-AND-VERIFY. Synthetic / de-identified only.
Site / LIMS / QMS / inventory / shipping adapters stay simulated
and read-only. No donors, clinical data, PHI, live movement,
outreach, or cash claim. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "organabio-multisite-donor-coa-lims-01"
SCHEMA = "commons-organabio-multisite-donor-coa-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "OrganaBio / Christopher B. Goodman"
HUMAN_RELEASER = "QA_RELEASER"
HUMAN_ACTOR = "qa-human-01"
ALIQUOTS_PER_COLLECTION = 5
VALID_COLLECTIONS = 240
EXPECTED_ALIQUOTS = 1200
EXPECTED_FAILURES = 24
EXPECTED_RECALLS = 40
SITES = ("MIA", "SDG", "IRV", "LAX", "OAK")
SITE_NAMES = {
    "MIA": "SYN-MIA-HQ",
    "SDG": "SYN-SDG-EXL",
    "IRV": "SYN-IRV-ISO7",
    "LAX": "SYN-LAX-ISO7",
    "OAK": "SYN-OAK-ISO7",
}
NAMESPACE = {code: f"OBA-{code}" for code in SITES}
LEGACY_SITE = "SDG"
LEGACY_PREFIX = "EXL"
FAILURE_CODES = (
    "BLOCK_CONSENT_MISSING",
    "BLOCK_CONSENT_WITHDRAWN",
    "BLOCK_ELIGIBILITY_INFECTIOUS",
    "BLOCK_ELIGIBILITY_TRAVEL",
)
EXPECTED_FAILURE_COUNTS = {
    "BLOCK_CONSENT_MISSING": 6,
    "BLOCK_CONSENT_WITHDRAWN": 6,
    "BLOCK_ELIGIBILITY_INFECTIOUS": 6,
    "BLOCK_ELIGIBILITY_TRAVEL": 6,
}
LINEAGE_STATES = (
    "COLLECTED",
    "ACCESSIONED",
    "ALIQUOTED",
    "PBMC_PROCESSED",
    "CRYOPRESERVED",
    "QC_RECORDED",
    "INVENTORY_RECORDED",
    "COA_ISSUED",
    "READY_FOR_HUMAN_RELEASE",
    "RELEASED",
)
FIXTURE_PATH = Path("revenue/organabio_multisite_donor_coa/fixture.json")
GOLDEN_COA_SHA256 = "3f3f9ab647c6d7e34cce48fc002c86150b3d83285b78de30e5ff25a0a845db01"
GOLDEN_LINEAGE_SHA256 = "ed446eb4bcea1c78d499c184d577672622e4846db556069054cbbad4b4f1986a"
GOLDEN_AUDIT_SHA256 = "1a5bfdccf4b5c59c8c40bbb5276d2915636e8c18a68f923f24c7cedb22eeeef3"


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


def site_namespace(site: str) -> str:
    return NAMESPACE[site]


def donor_id(site: str, index: int) -> str:
    return f"SYN-{site_namespace(site)}-DNR-{index:02d}"


def collection_id(site: str, index: int) -> str:
    return f"{site_namespace(site)}-COL-{index:02d}"


def accession_id(site: str, index: int) -> str:
    return f"{site_namespace(site)}-ACC-{index:02d}"


def aliquot_id(site: str, collection_index: int, vial: int) -> str:
    return f"{site_namespace(site)}-VIAL-{collection_index:02d}-{vial}"


def processing_lot(site: str, index: int) -> str:
    return f"{site_namespace(site)}-PBMC-{index:02d}"


def cryo_vial(site: str, collection_index: int, vial: int) -> str:
    return f"{site_namespace(site)}-CRYO-{collection_index:02d}-{vial}"


def legacy_id(index: int) -> str:
    return f"{LEGACY_PREFIX}-{index:04d}"


def failure_row_id(site: str, index: int) -> str:
    return f"{site_namespace(site)}-FAIL-{index:02d}"


def lineage_payload(
    *,
    donor: str,
    collection: str,
    accession: str,
    aliquot: str,
    site: str,
    vial: int,
    lot: str,
    cryo: str,
    legacy: str | None,
) -> dict[str, Any]:
    body = {
        "accession_id": accession,
        "aliquot_id": aliquot,
        "collection_id": collection,
        "cryo_vial_id": cryo,
        "demand_id": DEMAND_ID,
        "donor_id": donor,
        "legacy_id": legacy,
        "processing_lot": lot,
        "site": site,
        "vial_index": vial,
    }
    body["lineage_hash"] = sha256_hex(body)
    return body


def _valid_row(site: str, index: int) -> dict[str, Any]:
    return {
        "row_id": collection_id(site, index),
        "kind": "COLLECTION",
        "site": site,
        "site_name": SITE_NAMES[site],
        "namespace": site_namespace(site),
        "donor_id": donor_id(site, index),
        "collection_id": collection_id(site, index),
        "accession_id": accession_id(site, index),
        "legacy_id": legacy_id(index) if site == LEGACY_SITE else None,
        "recall": index <= 8,
        "consent": True,
        "eligible": True,
        "exception_code": None,
        "synthetic": True,
        "deidentified": True,
    }


def _failure_row(ordinal: int) -> dict[str, Any]:
    site = SITES[ordinal % 5]
    code = FAILURE_CODES[ordinal % 4]
    local = (ordinal // 5) + 1
    return {
        "row_id": failure_row_id(site, local),
        "kind": "FAILURE",
        "site": site,
        "site_name": SITE_NAMES[site],
        "namespace": site_namespace(site),
        "donor_id": f"SYN-{site_namespace(site)}-BLK-{local:02d}",
        "collection_id": None,
        "accession_id": None,
        "legacy_id": None,
        "recall": False,
        "consent": code not in {"BLOCK_CONSENT_MISSING", "BLOCK_CONSENT_WITHDRAWN"},
        "eligible": code not in {"BLOCK_ELIGIBILITY_INFECTIOUS", "BLOCK_ELIGIBILITY_TRAVEL"},
        "exception_code": code,
        "synthetic": True,
        "deidentified": True,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """Seed: 240 valid collections + 24 blocked attempts + 40 recall flags."""
    rows: list[dict[str, Any]] = []
    for site in SITES:
        for index in range(1, 49):
            rows.append(_valid_row(site, index))
    for ordinal in range(EXPECTED_FAILURES):
        rows.append(_failure_row(ordinal))
    valid = [row for row in rows if row["kind"] == "COLLECTION"]
    failures = [row for row in rows if row["kind"] == "FAILURE"]
    recalls = [row for row in valid if row["recall"]]
    if len(valid) != VALID_COLLECTIONS:
        raise RuntimeError("fixture must seed 240 valid collections, got %s" % len(valid))
    if len(failures) != EXPECTED_FAILURES:
        raise RuntimeError("fixture must seed 24 failures, got %s" % len(failures))
    if len(recalls) != EXPECTED_RECALLS:
        raise RuntimeError("fixture must flag 40 recall donors, got %s" % len(recalls))
    by_site = {code: 0 for code in SITES}
    for row in valid:
        by_site[row["site"]] += 1
    if any(count != 48 for count in by_site.values()):
        raise RuntimeError("each site must have 48 valid collections, got %s" % by_site)
    codes = {code: 0 for code in FAILURE_CODES}
    for row in failures:
        codes[row["exception_code"]] += 1
    if codes != dict(EXPECTED_FAILURE_COUNTS):
        raise RuntimeError("failure split must be 6/6/6/6, got %s" % codes)
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "collections": {},
        "aliquots": {},
        "lineages": {},
        "failures": [],
        "recalls": {},
        "legacy_map": {},
        "events": [],
        "interface_live": False,
        "production_writes": 0,
        "billing_writes": 0,
        "material_disposition": 0,
        "automatic_releases": 0,
        "live_movement": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    prev = journal["events"][-1]["record_hash"] if journal["events"] else "GENESIS"
    body = {"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)}
    body["prev_hash"] = prev
    body["record_hash"] = sha256_hex(
        {"prev": prev, "body": {k: v for k, v in body.items() if k not in {"prev_hash", "record_hash"}}}
    )
    journal["events"].append(body)


def normalize_intake(row: dict[str, Any]) -> dict[str, Any]:
    site = _text(row.get("site")).upper()
    kind = _text(row.get("kind")).upper() or "COLLECTION"
    code = _text(row.get("exception_code")).upper() or None
    return {
        "row_id": _text(row.get("row_id")),
        "kind": kind,
        "site": site,
        "site_name": _text(row.get("site_name")) or SITE_NAMES.get(site, ""),
        "namespace": _text(row.get("namespace")) or (site_namespace(site) if site in NAMESPACE else ""),
        "donor_id": _text(row.get("donor_id")),
        "collection_id": _text(row.get("collection_id")) or None,
        "accession_id": _text(row.get("accession_id")) or None,
        "legacy_id": _text(row.get("legacy_id")) or None,
        "recall": _flag(row.get("recall")),
        "consent": _flag(row.get("consent")) if "consent" in row else True,
        "eligible": _flag(row.get("eligible")) if "eligible" in row else True,
        "exception_code": code,
        "synthetic": _flag(row.get("synthetic")) if "synthetic" in row else True,
        "deidentified": _flag(row.get("deidentified")) if "deidentified" in row else True,
    }


def classify_intake(norm: dict[str, Any]) -> dict[str, Any]:
    if norm["site"] not in SITES:
        return {"ok": False, "code": "BLOCK_UNKNOWN_SITE"}
    if norm["kind"] == "FAILURE" or norm["exception_code"]:
        code = norm["exception_code"] or "BLOCK_CONSENT_MISSING"
        return {"ok": False, "code": code}
    if not norm["consent"]:
        return {"ok": False, "code": "BLOCK_CONSENT_MISSING"}
    if not norm["eligible"]:
        return {"ok": False, "code": "BLOCK_ELIGIBILITY_INFECTIOUS"}
    if not norm["donor_id"] or not norm["collection_id"] or not norm["accession_id"]:
        return {"ok": False, "code": "BLOCK_CONSENT_MISSING"}
    if not norm["namespace"] or not norm["collection_id"].startswith(norm["namespace"] + "-"):
        return {"ok": False, "code": "BLOCK_NAMESPACE"}
    return {"ok": True}


def _block(journal: dict[str, Any], norm: dict[str, Any], code: str) -> dict[str, Any]:
    hold = {
        "row_id": norm["row_id"],
        "donor_id": norm["donor_id"],
        "site": norm["site"],
        "namespace": norm["namespace"],
        "code": code,
        "state": "BLOCKED",
        "aliquots": 0,
        "lineage": None,
    }
    already = next((item for item in journal["failures"] if item["row_id"] == hold["row_id"]), None)
    if already is not None:
        return {"kind": "REPLAY_NOOP", "row_id": hold["row_id"], "code": code}
    journal["failures"].append(hold)
    _event(journal, "BLOCK", hold)
    return {"kind": "BLOCK", "duplicate": False, **hold}


def _freeze_lineage(journal: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    aliquot = payload["aliquot_id"]
    existing = journal["lineages"].get(aliquot)
    if existing is not None:
        if existing["lineage_hash"] != payload["lineage_hash"]:
            return {"ok": False, "code": "IMMUTABLE_LINEAGE"}
        return {"ok": True, "duplicate": True, "lineage_hash": existing["lineage_hash"]}
    journal["lineages"][aliquot] = deepcopy(payload)
    return {"ok": True, "duplicate": False, "lineage_hash": payload["lineage_hash"]}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_intake(row)
    verdict = classify_intake(norm)
    if not verdict["ok"]:
        return _block(journal, norm, verdict["code"])

    col_id = norm["collection_id"]
    if col_id in journal["collections"]:
        _event(journal, "REPLAY_NOOP", {"collection_id": col_id, "donor_id": norm["donor_id"]})
        return {"kind": "REPLAY_NOOP", "collection_id": col_id, "donor_id": norm["donor_id"]}

    index = int(col_id.rsplit("-", 1)[-1])
    collection = {
        "collection_id": col_id,
        "donor_id": norm["donor_id"],
        "accession_id": norm["accession_id"],
        "site": norm["site"],
        "site_name": norm["site_name"],
        "namespace": norm["namespace"],
        "legacy_id": norm["legacy_id"],
        "recall": norm["recall"],
        "state": "ACCESSIONED",
        "aliquot_ids": [],
        "released": False,
        "released_by": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "production_write": False,
        "material_disposition": False,
        "live_movement": False,
    }
    journal["collections"][col_id] = collection
    if norm["legacy_id"]:
        journal["legacy_map"][norm["legacy_id"]] = col_id
    if norm["recall"]:
        journal["recalls"][norm["donor_id"]] = {
            "donor_id": norm["donor_id"],
            "collection_id": col_id,
            "site": norm["site"],
            "aliquot_ids": [],
        }
    _event(
        journal,
        "ACCESSION",
        {
            "collection_id": col_id,
            "donor_id": norm["donor_id"],
            "site": norm["site"],
            "adapter": "SIMULATED_SITE_LIMS",
        },
    )

    lot = processing_lot(norm["site"], index)
    aliquot_ids: list[str] = []
    for vial in range(1, ALIQUOTS_PER_COLLECTION + 1):
        alq = aliquot_id(norm["site"], index, vial)
        cryo = cryo_vial(norm["site"], index, vial)
        lineage = lineage_payload(
            donor=norm["donor_id"],
            collection=col_id,
            accession=norm["accession_id"],
            aliquot=alq,
            site=norm["site"],
            vial=vial,
            lot=lot,
            cryo=cryo,
            legacy=norm["legacy_id"],
        )
        frozen = _freeze_lineage(journal, lineage)
        if not frozen["ok"]:
            return {"kind": "BLOCK", "code": frozen["code"], "aliquot_id": alq}
        record = {
            "aliquot_id": alq,
            "donor_id": norm["donor_id"],
            "collection_id": col_id,
            "accession_id": norm["accession_id"],
            "site": norm["site"],
            "namespace": norm["namespace"],
            "legacy_id": norm["legacy_id"],
            "vial_index": vial,
            "processing_lot": lot,
            "cryo_vial_id": cryo,
            "lineage_hash": lineage["lineage_hash"],
            "states_seen": list(LINEAGE_STATES[:3]),
            "state": "ALIQUOTED",
            "qc": None,
            "inventory": None,
            "coa": None,
            "released": False,
            "released_by": None,
            "disposed": False,
            "shipped": False,
            "interface_live": False,
        }
        journal["aliquots"][alq] = record
        aliquot_ids.append(alq)
    collection["aliquot_ids"] = aliquot_ids
    if norm["recall"]:
        journal["recalls"][norm["donor_id"]]["aliquot_ids"] = list(aliquot_ids)
    _event(journal, "ALIQUOT", {"collection_id": col_id, "aliquot_ids": aliquot_ids})
    return {"kind": "COLLECTION", "collection_id": col_id, "aliquot_ids": aliquot_ids}


def _advance(record: dict[str, Any], state: str) -> None:
    if state not in record["states_seen"]:
        record["states_seen"].append(state)
    record["state"] = state


def process_valid(journal: dict[str, Any]) -> None:
    for record in sorted(journal["aliquots"].values(), key=lambda item: item["aliquot_id"]):
        _advance(record, "PBMC_PROCESSED")
        _advance(record, "CRYOPRESERVED")
        qc = {
            "aliquot_id": record["aliquot_id"],
            "viability_pct": 92.0,
            "sterility": "PASS",
            "identity": "PBMC",
            "adapter": "SIMULATED_QC",
            "read_only": True,
        }
        qc["digest"] = sha256_hex(qc)
        record["qc"] = qc
        _advance(record, "QC_RECORDED")
        inventory = {
            "aliquot_id": record["aliquot_id"],
            "location": f"{record['namespace']}-VAPOR-01",
            "temp_c": -150.0,
            "adapter": "SIMULATED_INVENTORY",
            "disposition": "NONE",
        }
        record["inventory"] = inventory
        _advance(record, "INVENTORY_RECORDED")
        coa = {
            "aliquot_id": record["aliquot_id"],
            "donor_id": record["donor_id"],
            "collection_id": record["collection_id"],
            "site": record["site"],
            "lineage_hash": record["lineage_hash"],
            "qc_digest": qc["digest"],
            "legacy_id": record["legacy_id"],
            "adapter": "SIMULATED_COA",
        }
        coa["digest"] = sha256_hex(coa)
        record["coa"] = coa
        _advance(record, "COA_ISSUED")
        record["report_status"] = "READY_FOR_HUMAN_RELEASE"
        _advance(record, "READY_FOR_HUMAN_RELEASE")
        _event(
            journal,
            "COA",
            {"aliquot_id": record["aliquot_id"], "digest": coa["digest"], "adapter": "SIMULATED_COA"},
        )


def release_aliquot(
    journal: dict[str, Any],
    aliquot_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["aliquots"].get(aliquot_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ALIQUOT"}
    role = _text(actor_role).upper()
    if role != HUMAN_RELEASER:
        _event(
            journal,
            "RELEASE_DENIED",
            {"aliquot_id": aliquot_id_value, "code": "AUTONOMOUS_RELEASE_DENIED", "actor_role": role or None},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("report_status") != "READY_FOR_HUMAN_RELEASE" and not record["released"]:
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": record.get("report_status")}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = _text(actor) or HUMAN_ACTOR
    record["report_status"] = "RELEASED"
    _advance(record, "RELEASED")
    collection = journal["collections"][record["collection_id"]]
    if all(journal["aliquots"][alq]["released"] for alq in collection["aliquot_ids"]):
        collection["released"] = True
        collection["released_by"] = record["released_by"]
    _event(journal, "RELEASED", {"aliquot_id": aliquot_id_value, "released_by": record["released_by"]})
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_aliquot(journal, alq, actor_role="SYSTEM", actor="autonomous")
        for alq in sorted(journal["aliquots"])
    ]


def authorized_human_release(journal: dict[str, Any], actor: str = HUMAN_ACTOR) -> list[dict[str, Any]]:
    return [
        release_aliquot(journal, alq, actor_role=HUMAN_RELEASER, actor=actor)
        for alq in sorted(journal["aliquots"])
    ]


def dispose_material(
    journal: dict[str, Any],
    aliquot_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["aliquots"].get(aliquot_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ALIQUOT"}
    if not record["released"] or _text(actor_role).upper() != HUMAN_RELEASER:
        _event(
            journal,
            "DISPOSITION_DENIED",
            {
                "aliquot_id": aliquot_id_value,
                "code": "HUMAN_RELEASE_REQUIRED",
                "actor": actor,
                "released": record["released"],
            },
        )
        return {"ok": False, "code": "HUMAN_RELEASE_REQUIRED"}
    return {
        "ok": False,
        "code": "SIMULATED_ONLY_NO_LIVE_MOVEMENT",
        "interface_live": False,
        "live_movement": False,
    }


def recall_donor(journal: dict[str, Any], donor: str) -> dict[str, Any]:
    expected = journal["recalls"].get(donor)
    if expected is None:
        found = [item["aliquot_id"] for item in journal["aliquots"].values() if item["donor_id"] == donor]
        return {"ok": False, "code": "NOT_A_RECALL_DONOR", "aliquot_ids": found}
    ids = [
        item["aliquot_id"]
        for item in journal["aliquots"].values()
        if item["donor_id"] == donor
    ]
    return {
        "ok": True,
        "donor_id": donor,
        "aliquot_ids": sorted(ids),
        "expected": sorted(expected["aliquot_ids"]),
        "exact": sorted(ids) == sorted(expected["aliquot_ids"]),
    }


def recall_all(journal: dict[str, Any]) -> dict[str, Any]:
    expected = sorted(
        alq
        for item in journal["recalls"].values()
        for alq in item["aliquot_ids"]
    )
    actual = sorted(
        item["aliquot_id"]
        for item in journal["aliquots"].values()
        if item["donor_id"] in journal["recalls"]
    )
    extras = [alq for alq in actual if alq not in expected]
    missing = [alq for alq in expected if alq not in actual]
    return {
        "ok": extras == [] and missing == [] and actual == expected,
        "aliquot_ids": actual,
        "expected": expected,
        "extras": extras,
        "missing": missing,
        "recall_donors": sorted(journal["recalls"]),
        "recall_count": len(journal["recalls"]),
        "aliquot_count": len(actual),
    }


def mutate_lineage(journal: dict[str, Any], aliquot_id_value: str, donor_id_value: str) -> dict[str, Any]:
    existing = journal["lineages"].get(aliquot_id_value)
    if existing is None:
        return {"ok": False, "code": "UNKNOWN_ALIQUOT"}
    attempt = deepcopy(existing)
    attempt["donor_id"] = donor_id_value
    attempt.pop("lineage_hash", None)
    attempt["lineage_hash"] = sha256_hex(attempt)
    frozen = _freeze_lineage(journal, attempt)
    if frozen.get("ok") and not frozen.get("duplicate"):
        return {"ok": True, "code": "LINEAGE_REPLACED"}
    return {"ok": False, "code": "IMMUTABLE_LINEAGE", "lineage_hash": existing["lineage_hash"]}


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before_col = set(journal["collections"])
    before_alq = set(journal["aliquots"])
    before_fail = len(journal["failures"])
    effects = [ingest_row(journal, row) for row in inbound]
    return {
        "added_collections": sorted(set(journal["collections"]) - before_col),
        "added_collection_count": len(set(journal["collections"]) - before_col),
        "added_aliquots": len(set(journal["aliquots"]) - before_alq),
        "added_failures": len(journal["failures"]) - before_fail,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "collection_count": len(journal["collections"]),
        "aliquot_count": len(journal["aliquots"]),
        "failure_count": len(journal["failures"]),
    }


def namespaces_collide(journal: dict[str, Any]) -> list[str]:
    seen: dict[str, str] = {}
    collisions: list[str] = []
    tokens = []
    for collection in journal["collections"].values():
        tokens.extend(
            [
                (collection["collection_id"], collection["site"]),
                (collection["accession_id"], collection["site"]),
                (collection["donor_id"], collection["site"]),
            ]
        )
        if collection["legacy_id"]:
            tokens.append((collection["legacy_id"], collection["site"]))
    for aliquot in journal["aliquots"].values():
        tokens.append((aliquot["aliquot_id"], aliquot["site"]))
        tokens.append((aliquot["cryo_vial_id"], aliquot["site"]))
        tokens.append((aliquot["processing_lot"], aliquot["site"]))
    for failure in journal["failures"]:
        tokens.append((failure["row_id"], failure["site"]))
        tokens.append((failure["donor_id"], failure["site"]))
    for token, site in tokens:
        owner = seen.get(token)
        if owner is None:
            seen[token] = site
        elif owner != site:
            collisions.append(token)
        prefix = NAMESPACE.get(site)
        if prefix and not token.startswith(prefix) and not token.startswith(f"SYN-{prefix}") and not token.startswith(LEGACY_PREFIX + "-"):
            collisions.append(token)
        if token.startswith(LEGACY_PREFIX + "-") and site != LEGACY_SITE:
            collisions.append(token)
    return sorted(set(collisions))


def _coa_records(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(item["coa"])
        for item in sorted(journal["aliquots"].values(), key=lambda item: item["aliquot_id"])
        if item.get("coa")
    ]


def _lineage_records(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(journal["lineages"][alq])
        for alq in sorted(journal["lineages"])
    ]


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any], digests: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "counts": counts,
        "failures": deepcopy(journal["failures"]),
        "recalls": deepcopy(journal["recalls"]),
        "legacy_map": deepcopy(journal["legacy_map"]),
        "lineages": _lineage_records(journal),
        "coas": _coa_records(journal),
        "events": deepcopy(journal["events"]),
        "digests": digests,
        "adapters": {
            "site_lims": "SIMULATED_READ_ONLY",
            "qms": "SIMULATED_READ_ONLY",
            "inventory": "SIMULATED_READ_ONLY",
            "shipping": "SIMULATED_READ_ONLY",
            "excellos_legacy": "SIMULATED_RECONCILE",
            "material_disposition": "NOT_PERFORMED",
        },
    }


def run_federation(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    process_valid(journal)
    autonomous = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)
    recall = recall_all(journal)
    collisions = namespaces_collide(journal)

    collections = sorted(journal["collections"].values(), key=lambda item: item["collection_id"])
    aliquots = sorted(journal["aliquots"].values(), key=lambda item: item["aliquot_id"])
    failure_codes = sorted(item["code"] for item in journal["failures"])
    unique_failure_codes = sorted(set(failure_codes))
    site_counts = {code: 0 for code in SITES}
    for item in collections:
        site_counts[item["site"]] += 1
    lineage_hashes = [item["lineage_hash"] for item in aliquots]
    digests = {
        "coa_sha256": sha256_hex(_coa_records(journal)),
        "lineage_sha256": sha256_hex(_lineage_records(journal)),
    }
    counts = {
        "input_rows": len(inbound),
        "valid_collections": len(collections),
        "aliquots": len(aliquots),
        "failures": len(journal["failures"]),
        "recalls": len(journal["recalls"]),
        "human_released": sum(1 for item in aliquots if item["released"]),
        "autonomous_released": 0,
        "namespace_collisions": len(collisions),
        "recall_aliquots": recall["aliquot_count"],
        "legacy_reconciled": len(journal["legacy_map"]),
    }
    audit = _audit_payload(journal, counts, digests)
    audit_sha256 = sha256_hex(audit)
    one_lineage = all(
        len([h for h in lineage_hashes if h == item["lineage_hash"]]) == 1
        and journal["lineages"][item["aliquot_id"]]["lineage_hash"] == item["lineage_hash"]
        for item in aliquots
    )
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": counts["input_rows"],
        "valid_collections": counts["valid_collections"],
        "aliquots": counts["aliquots"],
        "failures": counts["failures"],
        "failure_codes": unique_failure_codes,
        "failure_code_counts": {
            code: sum(1 for item in journal["failures"] if item["code"] == code) for code in unique_failure_codes
        },
        "recalls": counts["recalls"],
        "recall_aliquots": counts["recall_aliquots"],
        "human_released": counts["human_released"],
        "autonomous_released": 0,
        "site_counts": site_counts,
        "sites": list(SITES),
        "namespace_collisions": collisions,
        "legacy_map": deepcopy(journal["legacy_map"]),
        "legacy_reconciled": counts["legacy_reconciled"],
        "one_lineage_per_aliquot": one_lineage,
        "recall": recall,
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "human_release_effects": human,
        "collections": collections,
        "aliquot_records": aliquots,
        "failure_records": deepcopy(journal["failures"]),
        "lineages": deepcopy(journal["lineages"]),
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "billing_writes": 0,
        "material_disposition": 0,
        "automatic_releases": 0,
        "live_movement": 0,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "coa_sha256": digests["coa_sha256"],
        "lineage_sha256": digests["lineage_sha256"],
        "audit": audit,
        "audit_sha256": audit_sha256,
    }
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    expected = {
        "valid_collections": VALID_COLLECTIONS,
        "aliquots": EXPECTED_ALIQUOTS,
        "failures": EXPECTED_FAILURES,
        "recalls": EXPECTED_RECALLS,
        "human_released": EXPECTED_ALIQUOTS,
        "autonomous_released": 0,
        "recall_aliquots": EXPECTED_RECALLS * ALIQUOTS_PER_COLLECTION,
        "legacy_reconciled": 48,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            failures.append(f"{key}!={value} actual={result.get(key)}")
    if result.get("site_counts") != {code: 48 for code in SITES}:
        failures.append("site_counts")
    if result.get("failure_code_counts") != dict(EXPECTED_FAILURE_COUNTS):
        failures.append("failure_code_counts")
    if result.get("namespace_collisions") != []:
        failures.append("namespace_collisions")
    if result.get("one_lineage_per_aliquot") is not True:
        failures.append("one_lineage_per_aliquot")
    if not (result.get("recall") or {}).get("ok"):
        failures.append("recall_not_exact")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("material_disposition") != 0:
        failures.append("material_disposition")
    if result.get("automatic_releases") != 0:
        failures.append("automatic_releases")
    if result.get("live_movement") != 0:
        failures.append("live_movement")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    if any(item.get("lineage") for item in result.get("failure_records") or []):
        failures.append("failure_grew_lineage")
    if result.get("coa_sha256") != GOLDEN_COA_SHA256:
        failures.append("coa_sha256")
    if result.get("lineage_sha256") != GOLDEN_LINEAGE_SHA256:
        failures.append("lineage_sha256")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "valid_collections": VALID_COLLECTIONS,
        "aliquots": EXPECTED_ALIQUOTS,
        "failures": EXPECTED_FAILURES,
        "recalls": EXPECTED_RECALLS,
        "human_released": EXPECTED_ALIQUOTS,
        "autonomous_released": 0,
        "recall_aliquots": EXPECTED_RECALLS * ALIQUOTS_PER_COLLECTION,
    }
    actual = {key: result.get(key) for key in expected}
    return {"expected": expected, "actual": actual, "match": expected == actual}


def fixture_document(result: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = build_acceptance_fixture()
    body = result if result is not None else run_federation(rows)
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "sites": [
            {
                "code": code,
                "name": SITE_NAMES[code],
                "namespace": site_namespace(code),
                "legacy_system": "EXCELLOS" if code == LEGACY_SITE else None,
            }
            for code in SITES
        ],
        "seed": rows,
        "expected": {
            "valid_collections": VALID_COLLECTIONS,
            "aliquots": EXPECTED_ALIQUOTS,
            "failures": EXPECTED_FAILURES,
            "recalls": EXPECTED_RECALLS,
            "recall_aliquots": EXPECTED_RECALLS * ALIQUOTS_PER_COLLECTION,
            "failure_code_counts": dict(EXPECTED_FAILURE_COUNTS),
            "legacy_reconciled": 48,
            "coa_sha256": body["coa_sha256"],
            "lineage_sha256": body["lineage_sha256"],
            "audit_sha256": body["audit_sha256"],
        },
        "adapters": {
            "site_lims": "SIMULATED_READ_ONLY",
            "qms": "SIMULATED_READ_ONLY",
            "inventory": "SIMULATED_READ_ONLY",
            "shipping": "SIMULATED_READ_ONLY",
        },
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "synthetic": True,
        "deidentified": True,
        "live_lims": False,
        "production_deployment": False,
    }


def write_fixture(path: Path | None = None, result: dict[str, Any] | None = None) -> Path:
    dest = path or FIXTURE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(fixture_document(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dest


def load_fixture(path: Path | None = None) -> dict[str, Any]:
    dest = path or FIXTURE_PATH
    return json.loads(dest.read_text(encoding="utf-8"))


def main() -> int:
    first = run_federation()
    second = run_federation()
    journal = empty_journal()
    seed = build_acceptance_fixture()
    for row in seed:
        ingest_row(journal, row)
    replay = replay_into(journal, seed)
    write_fixture(result=first)
    failures = pass_contract(first)
    if first["coa_sha256"] != second["coa_sha256"]:
        failures.append("coa_replay_mismatch")
    if first["lineage_sha256"] != second["lineage_sha256"]:
        failures.append("lineage_replay_mismatch")
    if first["audit_sha256"] != second["audit_sha256"]:
        failures.append("audit_replay_mismatch")
    if replay.get("added_collection_count") != 0:
        failures.append("replay_added_collections")
    if replay.get("added_aliquots") != 0:
        failures.append("replay_added_aliquots")
    if replay.get("added_failures") != 0:
        failures.append("replay_added_failures")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "command": "python3 organabio_multisite_donor_coa.py",
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "failure_codes": first.get("failure_codes"),
        "failure_code_counts": first.get("failure_code_counts"),
        "site_counts": first.get("site_counts"),
        "coa_sha256": first.get("coa_sha256"),
        "lineage_sha256": first.get("lineage_sha256"),
        "audit_sha256": first.get("audit_sha256"),
        "replay_added_collections": replay.get("added_collection_count"),
        "truth_gate": TRUTH_GATE,
        "interfaces": "SIMULATED",
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Wadsworth five-site consolidation namespace and migration-readiness LIMS.

Demand: wadsworth-five-site-consolidation-lims-01
Buyer: Leonard F. Peruski / NYSDOH Wadsworth Center

Cross-site master-data namespace and migration-readiness verifier for
accessions, samples, tests, results, reports, attachments, methods, and
facility custody. Five synthetic source sites map once onto a synthetic
Harriman Campus namespace. Adapters stay synthetic and read-only /
simulated-migration only.

Acceptance: 2,000 synthetic multi-site bundles — 1,700 valid, 100
duplicate namespace IDs, 80 method/version conflicts, 60 broken
references, 60 facility/custody mismatches. PASS only when exactly
1,700 are READY, 300 receive their predetermined HOLD, every valid
object maps once with originating-site/source hashes, orphans and
duplicates are zero, replay adds nothing, rollback restores baseline,
and release is named-human only.

HOLD / BUILD-AND-VERIFY. No public-health, GMP, regulatory, clinical,
or diagnostic decision. No outreach. PRE-SALE TRANSPORT: NONE.
cash_usd=0.

Official command:
    python3 wadsworth_five_site_consolidation_lims.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from typing import Any

DEMAND_ID = "wadsworth-five-site-consolidation-lims-01"
SCHEMA = "commons-wadsworth-five-site-consolidation-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Leonard F. Peruski / NYSDOH Wadsworth Center"
HUMAN_APPROVER = "SYN-WAD-RELEASER"
HUMAN_ROLE = "NAMED_HUMAN_RELEASER"
TARGET_SITE = "SYN-HARRIMAN-CAMPUS"

VALID_COUNT = 1700
DUPLICATE_COUNT = 100
METHOD_CONFLICT_COUNT = 80
BROKEN_REF_COUNT = 60
CUSTODY_MISMATCH_COUNT = 60
HOLD_COUNT = DUPLICATE_COUNT + METHOD_CONFLICT_COUNT + BROKEN_REF_COUNT + CUSTODY_MISMATCH_COUNT
INPUT_COUNT = VALID_COUNT + HOLD_COUNT
OBJECT_KINDS = (
    "accession",
    "sample",
    "test",
    "result",
    "report",
    "attachment",
    "method",
    "facility_custody",
)
OBJECTS_PER_BUNDLE = len(OBJECT_KINDS)
MAPPED_OBJECT_COUNT = VALID_COUNT * OBJECTS_PER_BUNDLE

HOLD_CODES = (
    "DUPLICATE_NAMESPACE_ID",
    "METHOD_VERSION_CONFLICT",
    "BROKEN_REFERENCE",
    "FACILITY_CUSTODY_MISMATCH",
)
HOLD_FAMILY_COUNTS = {
    "DUPLICATE_NAMESPACE_ID": DUPLICATE_COUNT,
    "METHOD_VERSION_CONFLICT": METHOD_CONFLICT_COUNT,
    "BROKEN_REFERENCE": BROKEN_REF_COUNT,
    "FACILITY_CUSTODY_MISMATCH": CUSTODY_MISMATCH_COUNT,
}

# Synthetic labels for the five Albany/Guilderland source sites that the
# public construction announcement is consolidating. Not live facility codes.
SITES = (
    "SYN-ALB-AXELROD",
    "SYN-ALB-BIGGS",
    "SYN-GLD-GRIFFIN",
    "SYN-ALB-EMPIRE",
    "SYN-GLD-CULTURE",
)

# Synthetic method catalog only. Versions are fixture bindings, not a lab menu.
METHOD_CATALOG: dict[str, dict[str, Any]] = {
    "SYN-WAD-SEQ-WGS": {"versions": ("1.0.0", "1.1.0"), "family": "sequence_metadata"},
    "SYN-WAD-CHEM-ICP": {"versions": ("3.2.0",), "family": "chemistry_metadata"},
    "SYN-WAD-MICRO-CULTURE": {"versions": ("2.0.0", "2.1.0"), "family": "culture_metadata"},
    "SYN-WAD-NUCLEIC-PCR": {"versions": ("4.0.0",), "family": "nucleic_run_metadata"},
    "SYN-WAD-ENV-WATER": {"versions": ("1.4.0", "1.5.0"), "family": "environmental_metadata"},
}
METHOD_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (method, version) for method, spec in METHOD_CATALOG.items() for version in spec["versions"]
)

AUTONOMOUS_NAMES = frozenset({"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE"})

GOLDEN_FIXTURE_SHA256 = "bccabef160e21d1fa4da52355819913765da44933f362b2842651158c9ffe198"
GOLDEN_CATALOG_SHA256 = "7d42d8242af9760f6cb96d2e3c53badc8e2f5431240127a86a82f28d6b83350b"
GOLDEN_MANIFEST_SHA256 = "687fc3e126ace5833254fceefa04b9a4a39dc5420e1b4558e80c29da2ab7f9c5"
GOLDEN_BASELINE_SHA256 = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"

EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "ready": VALID_COUNT,
    "holds": HOLD_COUNT,
    "hold_duplicate_namespace_id": DUPLICATE_COUNT,
    "hold_method_version_conflict": METHOD_CONFLICT_COUNT,
    "hold_broken_reference": BROKEN_REF_COUNT,
    "hold_facility_custody_mismatch": CUSTODY_MISMATCH_COUNT,
    "mapped": MAPPED_OBJECT_COUNT,
    "orphans": 0,
    "duplicates": 0,
    "replay_added_mappings": 0,
    "replay_added_objects": 0,
    "released": 0,
    "production_writes": 0,
}

OFFICIAL_BINARY = "python3 wadsworth_five_site_consolidation_lims.py"
OFFICIAL_TEST = "python3 test_wadsworth_five_site_consolidation_lims.py"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


CATALOG_SHA256 = sha256_hex(METHOD_CATALOG)


def _site(index: int) -> str:
    return SITES[(index - 1) % len(SITES)]


def _method_pair(index: int) -> tuple[str, str]:
    return METHOD_PAIRS[(index - 1) % len(METHOD_PAIRS)]


def _namespace_id(site: str, kind: str, index: int) -> str:
    return f"WAD:{site}:{kind}:{index:04d}"


def _object_by_kind(row: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for obj in row.get("objects") or []:
        if obj.get("kind") == kind:
            return obj
    return None


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "demand_id": DEMAND_ID,
        "bundle_id": row["bundle_id"],
        "originating_site": row["originating_site"],
        "method": row["method"],
        "method_version": row["method_version"],
        "namespace_ids": [obj["namespace_id"] for obj in row["objects"]],
        "object_kinds": [obj["kind"] for obj in row["objects"]],
        "refs": [obj.get("refs") for obj in row["objects"]],
    }


def _originating_site_payload(row: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_id": row["bundle_id"],
        "kind": obj["kind"],
        "namespace_id": obj["namespace_id"],
        "originating_site": row["originating_site"],
        "object_site": obj.get("originating_site"),
    }


def _result_payload(index: int, method: str, version: str) -> dict[str, Any]:
    # Raw instrument fields only. No Detected / Positive / organism / diagnosis.
    return {
        "cycle_index": index,
        "signal_units": (index % 97) + 3,
        "method": method,
        "method_version": version,
        "instrument": "SYN-WAD-ANALYZER",
    }


def _stamp_hashes(row: dict[str, Any]) -> dict[str, Any]:
    row["source"] = _source_payload(row)
    row["source_hash"] = sha256_hex(row["source"])
    for obj in row["objects"]:
        obj["originating_site_hash"] = sha256_hex(_originating_site_payload(row, obj))
        obj["source_hash"] = row["source_hash"]
    row["originating_site_hash"] = sha256_hex(
        {
            "bundle_id": row["bundle_id"],
            "originating_site": row["originating_site"],
            "namespace_ids": [obj["namespace_id"] for obj in row["objects"]],
        }
    )
    row["result_hash"] = sha256_hex(row["result"])
    return row


def _valid_bundle(index: int) -> dict[str, Any]:
    site = _site(index)
    method, version = _method_pair(index)
    objects = []
    ns = {kind: _namespace_id(site, kind, index) for kind in OBJECT_KINDS}
    objects.append(
        {
            "kind": "accession",
            "namespace_id": ns["accession"],
            "originating_site": site,
            "local_id": f"ACC-{index:04d}",
            "refs": {},
        }
    )
    objects.append(
        {
            "kind": "sample",
            "namespace_id": ns["sample"],
            "originating_site": site,
            "local_id": f"SMP-{index:04d}",
            "refs": {"accession": ns["accession"]},
        }
    )
    objects.append(
        {
            "kind": "test",
            "namespace_id": ns["test"],
            "originating_site": site,
            "local_id": f"TST-{index:04d}",
            "refs": {"sample": ns["sample"], "method": ns["method"]},
        }
    )
    objects.append(
        {
            "kind": "result",
            "namespace_id": ns["result"],
            "originating_site": site,
            "local_id": f"RST-{index:04d}",
            "refs": {"test": ns["test"]},
        }
    )
    objects.append(
        {
            "kind": "report",
            "namespace_id": ns["report"],
            "originating_site": site,
            "local_id": f"RPT-{index:04d}",
            "refs": {"result": ns["result"]},
        }
    )
    objects.append(
        {
            "kind": "attachment",
            "namespace_id": ns["attachment"],
            "originating_site": site,
            "local_id": f"ATT-{index:04d}",
            "refs": {"report": ns["report"]},
        }
    )
    objects.append(
        {
            "kind": "method",
            "namespace_id": ns["method"],
            "originating_site": site,
            "local_id": f"MTH-{index:04d}",
            "method": method,
            "method_version": version,
            "refs": {"test": ns["test"]},
        }
    )
    objects.append(
        {
            "kind": "facility_custody",
            "namespace_id": ns["facility_custody"],
            "originating_site": site,
            "facility": site,
            "local_id": f"CUS-{index:04d}",
            "refs": {"accession": ns["accession"], "sample": ns["sample"], "facility": site},
        }
    )
    row: dict[str, Any] = {
        "bundle_id": f"WAD-{index:04d}",
        "originating_site": site,
        "target_site": TARGET_SITE,
        "method": method,
        "method_version": version,
        "objects": objects,
        "result": _result_payload(index, method, version),
        "interpretation": None,
        "public_health_call": None,
        "diagnostic_call": None,
        "expected_state": "READY",
        "expected_hold": None,
    }
    return _stamp_hashes(row)


def _duplicate_bundle(slot: int) -> dict[str, Any]:
    source = _valid_bundle(slot + 1)
    row = deepcopy(source)
    row["bundle_id"] = f"WAD-DUP-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "DUPLICATE_NAMESPACE_ID"
    return _stamp_hashes(row)


def _method_conflict_bundle(slot: int) -> dict[str, Any]:
    index = VALID_COUNT + slot + 1
    row = _valid_bundle(index)
    row["bundle_id"] = f"WAD-MVC-{slot + 1:04d}"
    row["method_version"] = "99.0.0-CONFLICT"
    row["result"]["method_version"] = "99.0.0-CONFLICT"
    method_obj = _object_by_kind(row, "method")
    if method_obj is not None:
        method_obj["method_version"] = "99.0.0-CONFLICT"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "METHOD_VERSION_CONFLICT"
    return _stamp_hashes(row)


def _broken_ref_bundle(slot: int) -> dict[str, Any]:
    index = VALID_COUNT + METHOD_CONFLICT_COUNT + slot + 1
    row = _valid_bundle(index)
    row["bundle_id"] = f"WAD-BRK-{slot + 1:04d}"
    sample = _object_by_kind(row, "sample")
    if sample is not None:
        sample["refs"]["accession"] = "WAD:MISSING:accession:0000"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "BROKEN_REFERENCE"
    return _stamp_hashes(row)


def _custody_mismatch_bundle(slot: int) -> dict[str, Any]:
    index = VALID_COUNT + METHOD_CONFLICT_COUNT + BROKEN_REF_COUNT + slot + 1
    row = _valid_bundle(index)
    row["bundle_id"] = f"WAD-CUS-{slot + 1:04d}"
    wrong = SITES[(SITES.index(row["originating_site"]) + 1) % len(SITES)]
    custody = _object_by_kind(row, "facility_custody")
    if custody is not None:
        custody["facility"] = wrong
        custody["refs"]["facility"] = wrong
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "FACILITY_CUSTODY_MISMATCH"
    return _stamp_hashes(row)


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_valid_bundle(index) for index in range(1, VALID_COUNT + 1)]
    rows.extend(_duplicate_bundle(slot) for slot in range(DUPLICATE_COUNT))
    rows.extend(_method_conflict_bundle(slot) for slot in range(METHOD_CONFLICT_COUNT))
    rows.extend(_broken_ref_bundle(slot) for slot in range(BROKEN_REF_COUNT))
    rows.extend(_custody_mismatch_bundle(slot) for slot in range(CUSTODY_MISMATCH_COUNT))
    return rows


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    inbound = rows if rows is not None else build_acceptance_fixture()
    return sha256_hex(inbound)


def fixture_manifest() -> dict[str, Any]:
    rows = build_acceptance_fixture()
    return {
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "input_rows": len(rows),
        "ready": sum(1 for row in rows if row["expected_state"] == "READY"),
        "holds": sum(1 for row in rows if row["expected_state"] == "HOLD"),
        "hold_family_counts": {
            code: sum(1 for row in rows if row.get("expected_hold") == code) for code in HOLD_CODES
        },
        "sites": list(SITES),
        "target_site": TARGET_SITE,
        "object_kinds": list(OBJECT_KINDS),
        "fixture_sha256": fixture_sha256(rows),
        "catalog_sha256": CATALOG_SHA256,
    }


class SimulatedFiveSiteSourceAdapter:
    """Read-only synthetic source across the five consolidation sites. No writes."""

    def __init__(self, bundles: list[dict[str, Any]]):
        self._order = [row["bundle_id"] for row in bundles]
        self._bundles = {row["bundle_id"]: deepcopy(row) for row in bundles}
        self.writes = 0
        self.live = False
        self.mode = "READ_ONLY"

    def list_bundles(self) -> list[dict[str, Any]]:
        return [deepcopy(self._bundles[bundle_id]) for bundle_id in self._order]

    def get_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        row = self._bundles.get(bundle_id)
        return None if row is None else deepcopy(row)

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("five-site source adapter is read-only")


class SimulatedHarrimanNamespaceAdapter:
    """Simulated Harriman target namespace. Snapshot / apply / rollback only."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.live = False
        self.mode = "SIMULATED"
        self.production_writes = 0
        self._snapshots: dict[str, dict[str, dict[str, Any]]] = {}

    def snapshot(self) -> str:
        snap = deepcopy(self.objects)
        digest = sha256_hex(snap)
        self._snapshots[digest] = snap
        return digest

    def baseline_hash(self) -> str:
        return sha256_hex(self.objects)

    def put(self, target_id: str, obj: dict[str, Any]) -> None:
        self.objects[target_id] = deepcopy(obj)

    def get(self, target_id: str) -> dict[str, Any] | None:
        obj = self.objects.get(target_id)
        return None if obj is None else deepcopy(obj)

    def rollback(self, snap_hash: str) -> dict[str, Any]:
        if snap_hash not in self._snapshots:
            return {"ok": False, "code": "UNKNOWN_SNAPSHOT"}
        self.objects = deepcopy(self._snapshots[snap_hash])
        return {"ok": True, "baseline_hash": self.baseline_hash(), "object_count": len(self.objects)}


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "catalog_sha256": CATALOG_SHA256,
        "seen_namespace_ids": {},
        "ready": {},
        "holds": [],
        "mappings": {},
        "target_index": {},
        "events": [],
        "released": {},
        "interface_live": False,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "production_writes": 0,
        "public_health_interpretation": False,
        "autonomous_release": False,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def references_ok(row: dict[str, Any]) -> bool:
    by_kind = {obj.get("kind"): obj for obj in row.get("objects") or []}
    if set(by_kind) != set(OBJECT_KINDS):
        return False
    accession = _text(by_kind["accession"].get("namespace_id"))
    sample = _text(by_kind["sample"].get("namespace_id"))
    test = _text(by_kind["test"].get("namespace_id"))
    result = _text(by_kind["result"].get("namespace_id"))
    report = _text(by_kind["report"].get("namespace_id"))
    method = _text(by_kind["method"].get("namespace_id"))
    if by_kind["sample"].get("refs", {}).get("accession") != accession:
        return False
    if by_kind["test"].get("refs", {}).get("sample") != sample:
        return False
    if by_kind["test"].get("refs", {}).get("method") != method:
        return False
    if by_kind["result"].get("refs", {}).get("test") != test:
        return False
    if by_kind["report"].get("refs", {}).get("result") != result:
        return False
    if by_kind["attachment"].get("refs", {}).get("report") != report:
        return False
    if by_kind["method"].get("refs", {}).get("test") != test:
        return False
    if by_kind["facility_custody"].get("refs", {}).get("accession") != accession:
        return False
    if by_kind["facility_custody"].get("refs", {}).get("sample") != sample:
        return False
    return True


def method_version_ok(row: dict[str, Any]) -> bool:
    method = _text(row.get("method"))
    version = _text(row.get("method_version"))
    spec = METHOD_CATALOG.get(method)
    if spec is None:
        return False
    if version not in spec["versions"]:
        return False
    method_obj = _object_by_kind(row, "method")
    if method_obj is None:
        return False
    if _text(method_obj.get("method")) != method:
        return False
    if _text(method_obj.get("method_version")) != version:
        return False
    return True


def custody_ok(row: dict[str, Any]) -> bool:
    site = _text(row.get("originating_site"))
    if site not in SITES:
        return False
    custody = _object_by_kind(row, "facility_custody")
    if custody is None:
        return False
    if _text(custody.get("facility")) != site:
        return False
    if _text(custody.get("originating_site")) != site:
        return False
    if _text((custody.get("refs") or {}).get("facility")) != site:
        return False
    for obj in row.get("objects") or []:
        if _text(obj.get("originating_site")) != site:
            return False
    return True


def hashes_ok(row: dict[str, Any]) -> bool:
    expected_source = sha256_hex(_source_payload(row))
    if expected_source != _text(row.get("source_hash")):
        return False
    if sha256_hex(row.get("result")) != _text(row.get("result_hash")):
        return False
    expected_site = sha256_hex(
        {
            "bundle_id": row.get("bundle_id"),
            "originating_site": row.get("originating_site"),
            "namespace_ids": [obj.get("namespace_id") for obj in row.get("objects") or []],
        }
    )
    if expected_site != _text(row.get("originating_site_hash")):
        return False
    for obj in row.get("objects") or []:
        if sha256_hex(_originating_site_payload(row, obj)) != _text(obj.get("originating_site_hash")):
            return False
        if _text(obj.get("source_hash")) != expected_source:
            return False
    return True


def classify_bundle(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    namespace_ids = [_text(obj.get("namespace_id")) for obj in row.get("objects") or []]
    if not all(namespace_ids) or len(namespace_ids) != OBJECTS_PER_BUNDLE:
        return {"ok": False, "code": "DUPLICATE_NAMESPACE_ID"}
    if any(ns in journal["seen_namespace_ids"] for ns in namespace_ids):
        return {"ok": False, "code": "DUPLICATE_NAMESPACE_ID"}
    if len(set(namespace_ids)) != OBJECTS_PER_BUNDLE:
        return {"ok": False, "code": "DUPLICATE_NAMESPACE_ID"}
    if not method_version_ok(row):
        return {"ok": False, "code": "METHOD_VERSION_CONFLICT"}
    if not references_ok(row):
        return {"ok": False, "code": "BROKEN_REFERENCE"}
    if not custody_ok(row):
        return {"ok": False, "code": "FACILITY_CUSTODY_MISMATCH"}
    if not hashes_ok(row):
        return {"ok": False, "code": "BROKEN_REFERENCE"}
    return {"ok": True, "code": None}


def target_object_id(obj: dict[str, Any], record: dict[str, Any]) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "namespace_id": obj["namespace_id"],
            "kind": obj["kind"],
            "originating_site": record["originating_site"],
            "originating_site_hash": obj["originating_site_hash"],
            "source_hash": record["source_hash"],
        }
    )
    return f"WAD-HARRIMAN-{obj['kind']}-{digest[:12]}"


def ingest_bundle(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    bundle_id = _text(row.get("bundle_id"))
    existing = journal["ready"].get(bundle_id)
    if existing is not None:
        _event(journal, "REPLAY_NOOP", {"bundle_id": bundle_id})
        return {"kind": "REPLAY_NOOP", "bundle_id": bundle_id}

    verdict = classify_bundle(journal, row)
    if not verdict["ok"]:
        hold = {
            "bundle_id": bundle_id,
            "originating_site": _text(row.get("originating_site")) or None,
            "code": verdict["code"],
            "state": "HOLD",
            "mapped": False,
            "namespace_ids": [_text(obj.get("namespace_id")) for obj in row.get("objects") or []],
        }
        fingerprint = sha256_hex(hold)
        existing_prints = {sha256_hex(item) for item in journal["holds"]}
        if fingerprint not in existing_prints:
            journal["holds"].append(hold)
            _event(journal, "HOLD", hold)
        return {"kind": "HOLD", "duplicate": fingerprint in existing_prints, **hold}

    objects = deepcopy(row["objects"])
    record = {
        "bundle_id": bundle_id,
        "originating_site": _text(row["originating_site"]),
        "target_site": TARGET_SITE,
        "method": _text(row["method"]),
        "method_version": _text(row["method_version"]),
        "objects": objects,
        "result": deepcopy(row["result"]),
        "source": deepcopy(row["source"]),
        "source_hash": _text(row["source_hash"]),
        "originating_site_hash": _text(row["originating_site_hash"]),
        "result_hash": _text(row["result_hash"]),
        "state": "READY",
        "mapped": False,
        "released": False,
        "released_by": None,
        "interpretation": None,
        "public_health_call": None,
        "diagnostic_call": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    journal["ready"][bundle_id] = record
    for obj in objects:
        journal["seen_namespace_ids"][obj["namespace_id"]] = bundle_id
    _event(journal, "READY", {"bundle_id": bundle_id, "originating_site": record["originating_site"]})
    return {"kind": "READY", "bundle_id": bundle_id}


def migrate(journal: dict[str, Any], target: SimulatedHarrimanNamespaceAdapter) -> dict[str, Any]:
    added_mappings = 0
    added_objects = 0
    for bundle_id, record in journal["ready"].items():
        all_mapped = True
        for obj in record["objects"]:
            namespace_id = obj["namespace_id"]
            if namespace_id in journal["mappings"]:
                continue
            target_id = target_object_id(obj, record)
            if target_id in journal["target_index"]:
                _event(journal, "DUPLICATE_TARGET", {"bundle_id": bundle_id, "target_id": target_id})
                all_mapped = False
                continue
            payload = {
                "target_id": target_id,
                "namespace_id": namespace_id,
                "kind": obj["kind"],
                "originating_site": record["originating_site"],
                "originating_site_hash": obj["originating_site_hash"],
                "source_hash": record["source_hash"],
                "bundle_id": bundle_id,
                "released": False,
                "interface_state": "SIMULATED",
            }
            target.put(target_id, payload)
            journal["mappings"][namespace_id] = target_id
            journal["target_index"][target_id] = namespace_id
            obj["mapped"] = True
            obj["target_id"] = target_id
            added_mappings += 1
            added_objects += 1
            _event(journal, "MAP", {"namespace_id": namespace_id, "target_id": target_id, "kind": obj["kind"]})
        record["mapped"] = all_mapped and all(obj.get("mapped") for obj in record["objects"])
    return {
        "added_mappings": added_mappings,
        "added_objects": added_objects,
        "mapped": len(journal["mappings"]),
        "target_objects": len(target.objects),
    }


def mapping_integrity(
    journal: dict[str, Any], target: SimulatedHarrimanNamespaceAdapter
) -> dict[str, Any]:
    ready_ns = {
        obj["namespace_id"] for record in journal["ready"].values() for obj in record["objects"]
    }
    mapped_ns = set(journal["mappings"])
    target_ids = set(target.objects)
    mapped_targets = set(journal["mappings"].values())
    orphans = sorted(
        (ready_ns - mapped_ns) | (mapped_ns - ready_ns) | (target_ids - mapped_targets) | (mapped_targets - target_ids)
    )
    reverse: dict[str, list[str]] = {}
    for namespace_id, target_id in journal["mappings"].items():
        reverse.setdefault(target_id, []).append(namespace_id)
    duplicate_targets = [target_id for target_id, nss in reverse.items() if len(nss) > 1]
    duplicate_index = [
        ns for ns, target_id in journal["mappings"].items() if journal["target_index"].get(target_id) != ns
    ]
    hold_mapped = [item["bundle_id"] for item in journal["holds"] if item.get("mapped")]
    return {
        "orphans": orphans,
        "orphan_count": len(orphans),
        "duplicate_targets": duplicate_targets,
        "duplicate_index": duplicate_index,
        "duplicate_count": len(duplicate_targets) + len(duplicate_index),
        "hold_mapped": hold_mapped,
    }


def release_mapped(
    journal: dict[str, Any],
    target: SimulatedHarrimanNamespaceAdapter,
    bundle_id: str,
    *,
    named_approver: str,
) -> dict[str, Any]:
    record = journal["ready"].get(bundle_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_OBJECT"}
    name = _text(named_approver)
    if not name:
        _event(journal, "RELEASE_DENIED", {"bundle_id": bundle_id, "code": "MISSING_NAMED_APPROVAL"})
        return {"ok": False, "code": "MISSING_NAMED_APPROVAL"}
    if name.upper() in AUTONOMOUS_NAMES:
        _event(journal, "RELEASE_DENIED", {"bundle_id": bundle_id, "code": "AUTONOMOUS_RELEASE_DENIED"})
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released"):
        return {"ok": True, "duplicate": True}
    record["released"] = True
    record["released_by"] = name
    journal["released"][bundle_id] = name
    for obj in record["objects"]:
        target_id = obj.get("target_id")
        stored = target.objects.get(target_id) if target_id else None
        if stored is not None:
            stored["released"] = True
            stored["released_by"] = name
    _event(journal, "RELEASED", {"bundle_id": bundle_id, "released_by": name})
    return {"ok": True, "duplicate": False, "released_by": name}


def compact_ready(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_id": record["bundle_id"],
        "originating_site": record["originating_site"],
        "target_site": record["target_site"],
        "method": record["method"],
        "method_version": record["method_version"],
        "namespace_ids": [obj["namespace_id"] for obj in record["objects"]],
        "target_ids": [obj.get("target_id") for obj in record["objects"]],
        "kinds": [obj["kind"] for obj in record["objects"]],
        "originating_site_hash": record["originating_site_hash"],
        "source_hash": record["source_hash"],
        "object_originating_site_hashes": [obj["originating_site_hash"] for obj in record["objects"]],
        "mapped": record["mapped"],
        "released": record["released"],
        "interpretation": record["interpretation"],
        "public_health_call": record["public_health_call"],
        "diagnostic_call": record["diagnostic_call"],
        "interface_state": record["interface_state"],
        "interface_live": record["interface_live"],
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    source = SimulatedFiveSiteSourceAdapter(inbound)
    target = SimulatedHarrimanNamespaceAdapter()
    journal = empty_journal()
    baseline = target.snapshot()
    effects = [ingest_bundle(journal, row) for row in source.list_bundles()]
    first_migrate = migrate(journal, target)
    integrity = mapping_integrity(journal, target)
    replay_migrate = migrate(journal, target)
    replay_ingest = [ingest_bundle(journal, row) for row in inbound]
    autonomous = [
        release_mapped(journal, target, bundle_id, named_approver="SYSTEM")
        for bundle_id in list(journal["ready"])[:2]
    ]
    autonomous.append(release_mapped(journal, target, next(iter(journal["ready"])), named_approver=""))
    after_migrate_hash = target.baseline_hash()
    rollback = target.rollback(baseline)
    restored_hash = target.baseline_hash()

    ready = [compact_ready(item) for item in sorted(journal["ready"].values(), key=lambda item: item["bundle_id"])]
    hold_codes = [item["code"] for item in journal["holds"]]
    hold_code_counts = {code: hold_codes.count(code) for code in HOLD_CODES}
    site_counts = {site: 0 for site in SITES}
    for item in ready:
        site_counts[item["originating_site"]] = site_counts.get(item["originating_site"], 0) + 1

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "ready": len(ready),
        "holds": len(journal["holds"]),
        "hold_codes": sorted(hold_codes),
        "hold_code_counts": hold_code_counts,
        "mapped": len(journal["mappings"]),
        "target_objects": first_migrate["target_objects"],
        "orphans": integrity["orphan_count"],
        "orphan_ids": integrity["orphans"],
        "duplicates": integrity["duplicate_count"],
        "hold_mapped": integrity["hold_mapped"],
        "site_counts": site_counts,
        "ready_ids": [item["bundle_id"] for item in ready],
        "namespace_ids": sorted(journal["mappings"]),
        "target_ids": sorted(journal["target_index"]),
        "mappings": dict(sorted(journal["mappings"].items())),
        "replay_added_mappings": replay_migrate["added_mappings"],
        "replay_added_objects": replay_migrate["added_objects"],
        "replay_ingest_noops": sum(1 for item in replay_ingest if item.get("kind") == "REPLAY_NOOP"),
        "replay_ingest_holds_dup": sum(1 for item in replay_ingest if item.get("kind") == "HOLD" and item.get("duplicate")),
        "baseline_hash": baseline,
        "after_migrate_hash": after_migrate_hash,
        "rollback_ok": rollback.get("ok") is True,
        "restored_hash": restored_hash,
        "rollback_restored_baseline": restored_hash == baseline,
        "released": len(journal["released"]),
        "autonomous_release_effects": autonomous,
        "effects": [{"kind": item.get("kind"), "bundle_id": item.get("bundle_id"), "code": item.get("code")} for item in effects],
        "ready_records": ready,
        "hold_records": deepcopy(journal["holds"]),
        "catalog_sha256": CATALOG_SHA256,
        "fixture_sha256": fixture_sha256(inbound),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "source_writes": source.writes,
        "production_writes": target.production_writes,
        "public_health_interpretation": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "official_binary": OFFICIAL_BINARY,
        "official_test": OFFICIAL_TEST,
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != INPUT_COUNT:
        failures.append("input_rows!=2000")
    if result.get("ready") != VALID_COUNT:
        failures.append("ready!=1700")
    if result.get("holds") != HOLD_COUNT:
        failures.append("holds!=300")
    counts = result.get("hold_code_counts") or {}
    if counts.get("DUPLICATE_NAMESPACE_ID") != DUPLICATE_COUNT:
        failures.append("hold_duplicate_namespace_id")
    if counts.get("METHOD_VERSION_CONFLICT") != METHOD_CONFLICT_COUNT:
        failures.append("hold_method_version_conflict")
    if counts.get("BROKEN_REFERENCE") != BROKEN_REF_COUNT:
        failures.append("hold_broken_reference")
    if counts.get("FACILITY_CUSTODY_MISMATCH") != CUSTODY_MISMATCH_COUNT:
        failures.append("hold_facility_custody_mismatch")
    if result.get("mapped") != MAPPED_OBJECT_COUNT:
        failures.append("mapped!=13600")
    if result.get("target_objects") != MAPPED_OBJECT_COUNT:
        failures.append("target_objects!=13600")
    if result.get("orphans") != 0:
        failures.append("orphans")
    if result.get("duplicates") != 0:
        failures.append("duplicates")
    if result.get("hold_mapped"):
        failures.append("hold_mapped")
    if len(set(result.get("ready_ids") or [])) != VALID_COUNT:
        failures.append("ready_ids_not_unique")
    if len(set(result.get("namespace_ids") or [])) != MAPPED_OBJECT_COUNT:
        failures.append("namespace_ids_not_unique")
    if len(set(result.get("target_ids") or [])) != MAPPED_OBJECT_COUNT:
        failures.append("target_ids_not_unique")
    if result.get("replay_added_mappings") != 0:
        failures.append("replay_added_mappings")
    if result.get("replay_added_objects") != 0:
        failures.append("replay_added_objects")
    if result.get("rollback_restored_baseline") is not True:
        failures.append("rollback_baseline")
    if result.get("baseline_hash") != result.get("restored_hash"):
        failures.append("rollback_hash")
    if result.get("after_migrate_hash") == result.get("baseline_hash"):
        failures.append("migrate_did_not_change_store")
    if result.get("released") != 0:
        failures.append("released")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("shadowing") != "READ_ONLY":
        failures.append("shadowing")
    if result.get("source_writes") != 0:
        failures.append("source_writes")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("public_health_interpretation") is not False:
        failures.append("public_health_interpretation")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    autos = result.get("autonomous_release_effects") or []
    if not autos:
        failures.append("autonomous_release_effects_missing")
    elif not all(
        item.get("ok") is False and item.get("code") in {"AUTONOMOUS_RELEASE_DENIED", "MISSING_NAMED_APPROVAL"}
        for item in autos
    ):
        failures.append("autonomous_release_not_denied")
    site_counts = result.get("site_counts") or {}
    if set(site_counts) != set(SITES):
        failures.append("sites_missing")
    elif any(count <= 0 for count in site_counts.values()):
        failures.append("site_not_represented")
    elif sum(site_counts.values()) != VALID_COUNT:
        failures.append("site_counts_sum")
    for item in result.get("ready_records") or []:
        if item.get("interpretation") is not None or item.get("public_health_call") is not None:
            failures.append("public_health_field")
            break
        if item.get("diagnostic_call") is not None:
            failures.append("diagnostic_call")
            break
        if len(item.get("kinds") or []) != OBJECTS_PER_BUNDLE:
            failures.append("object_kinds")
            break
        if item.get("target_site") != TARGET_SITE:
            failures.append("target_site")
            break
    if result.get("fixture_sha256") != GOLDEN_FIXTURE_SHA256 and GOLDEN_FIXTURE_SHA256 != "pending":
        failures.append("fixture_sha256")
    if result.get("catalog_sha256") != GOLDEN_CATALOG_SHA256 and GOLDEN_CATALOG_SHA256 != "pending":
        failures.append("catalog_sha256")
    if result.get("manifest_sha256") != GOLDEN_MANIFEST_SHA256 and GOLDEN_MANIFEST_SHA256 != "pending":
        failures.append("manifest_sha256")
    if result.get("baseline_hash") != GOLDEN_BASELINE_SHA256 and GOLDEN_BASELINE_SHA256 != "pending":
        failures.append("baseline_sha256")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result.get("input_rows"),
        "ready": result.get("ready"),
        "holds": result.get("holds"),
        "hold_duplicate_namespace_id": (result.get("hold_code_counts") or {}).get("DUPLICATE_NAMESPACE_ID"),
        "hold_method_version_conflict": (result.get("hold_code_counts") or {}).get("METHOD_VERSION_CONFLICT"),
        "hold_broken_reference": (result.get("hold_code_counts") or {}).get("BROKEN_REFERENCE"),
        "hold_facility_custody_mismatch": (result.get("hold_code_counts") or {}).get("FACILITY_CUSTODY_MISMATCH"),
        "mapped": result.get("mapped"),
        "orphans": result.get("orphans"),
        "duplicates": result.get("duplicates"),
        "replay_added_mappings": result.get("replay_added_mappings"),
        "replay_added_objects": result.get("replay_added_objects"),
        "released": result.get("released"),
        "production_writes": result.get("production_writes"),
    }
    return {"expected": EXPECTED_COUNTS, "actual": actual, "match": actual == EXPECTED_COUNTS}


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    failures = pass_contract(result)
    counts = expected_actual(result)
    return {
        "ok": not failures,
        "failures": failures,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "counts": counts,
        "site_counts": result.get("site_counts"),
        "hold_code_counts": result.get("hold_code_counts"),
        "mapped": result.get("mapped"),
        "orphans": result.get("orphans"),
        "duplicates": result.get("duplicates"),
        "replay_added_mappings": result.get("replay_added_mappings"),
        "replay_added_objects": result.get("replay_added_objects"),
        "rollback_restored_baseline": result.get("rollback_restored_baseline"),
        "released": result.get("released"),
        "manifest_sha256": result.get("manifest_sha256"),
        "fixture_sha256": result.get("fixture_sha256"),
        "catalog_sha256": result.get("catalog_sha256"),
        "baseline_hash": result.get("baseline_hash"),
        "after_migrate_hash": result.get("after_migrate_hash"),
        "restored_hash": result.get("restored_hash"),
        "interfaces": result.get("interfaces"),
        "shadowing": result.get("shadowing"),
        "public_health_interpretation": result.get("public_health_interpretation"),
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "official_binary": OFFICIAL_BINARY,
        "official_test": OFFICIAL_TEST,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--print-goldens" in args:
        first = run_gate()
        sys.stdout.write(
            _canonical(
                {
                    "fixture_sha256": first["fixture_sha256"],
                    "catalog_sha256": first["catalog_sha256"],
                    "manifest_sha256": first["manifest_sha256"],
                    "baseline_hash": first["baseline_hash"],
                    "counts": expected_actual(first),
                    "hold_code_counts": first["hold_code_counts"],
                    "site_counts": first["site_counts"],
                }
            )
            + "\n"
        )
        return 0
    first = run_gate()
    second = run_gate()
    failures = pass_contract(first)
    if sha256_hex(cli_payload(first)) != sha256_hex(cli_payload(second)):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    report = cli_payload(first)
    report["failures"] = failures
    report["ok"] = not failures
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

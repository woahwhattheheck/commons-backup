#!/usr/bin/env python3
"""SLO CliniSys cutover evidence LIMS.

Demand: slo-cls-cutover-evidence-lims-01
Buyer: Glen M. Miller / San Luis Obispo County Public Health Laboratory

Requisition/portal accession + Panther Fusion method version +
result/report/source hash → deterministic incumbent-to-CLS migration
and rollback verifier.

Synthetic 1,000-bundle fixture: 850 READY, 150 predetermined HOLD
(50 duplicate IDs, 40 broken sample→test refs, 30 method/version
conflicts, 30 report/result hash mismatches). Every READY object maps
once. Replay creates nothing. Rollback restores the exact baseline.
No result/report release without a named approver. Adapters stay
read-only / simulated. No public-health interpretation.

HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "slo-cls-cutover-evidence-lims-01"
SCHEMA = "commons-slo-cls-cutover-evidence-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Glen M. Miller / San Luis Obispo County Public Health Laboratory"
HUMAN_APPROVER = "SYN-SLO-RELEASER"
HUMAN_ROLE = "NAMED_APPROVER"

VALID_COUNT = 850
DUPLICATE_COUNT = 50
BROKEN_REF_COUNT = 40
METHOD_CONFLICT_COUNT = 30
HASH_MISMATCH_COUNT = 30
HOLD_COUNT = DUPLICATE_COUNT + BROKEN_REF_COUNT + METHOD_CONFLICT_COUNT + HASH_MISMATCH_COUNT
INPUT_COUNT = VALID_COUNT + HOLD_COUNT

HOLD_CODES = (
    "DUPLICATE_ID",
    "BROKEN_SAMPLE_TEST_REF",
    "METHOD_VERSION_CONFLICT",
    "HASH_MISMATCH",
)

HOLD_FAMILY_COUNTS = {
    "DUPLICATE_ID": DUPLICATE_COUNT,
    "BROKEN_SAMPLE_TEST_REF": BROKEN_REF_COUNT,
    "METHOD_VERSION_CONFLICT": METHOD_CONFLICT_COUNT,
    "HASH_MISMATCH": HASH_MISMATCH_COUNT,
}

# Synthetic Panther Fusion catalog only. Not a clinical catalog.
PANTHER_FUSION_CATALOG: dict[str, dict[str, Any]] = {
    "PF-SARS-COV-2": {"versions": ("2.1.0", "2.2.0"), "assay": "sars_cov_2_fusion"},
    "PF-FLU-AB-RSV": {"versions": ("1.5.0", "1.6.0"), "assay": "flu_ab_rsv_fusion"},
    "PF-PARAFLU": {"versions": ("1.3.0",), "assay": "parainfluenza_fusion"},
    "PF-ADENO": {"versions": ("1.2.0",), "assay": "adenovirus_fusion"},
    "PF-CT-NG": {"versions": ("2.0.0", "2.1.0"), "assay": "ct_ng_fusion"},
}

METHOD_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (method, version)
    for method, spec in PANTHER_FUSION_CATALOG.items()
    for version in spec["versions"]
)

AUTONOMOUS_NAMES = frozenset({"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE"})

GOLDEN_FIXTURE_SHA256 = "52fd63d42b02502e0368052fb88b2b75d81044cf6b2ba3f088dbdca1bd61d7ea"
GOLDEN_CATALOG_SHA256 = "993f241f304028f2d1d03ade8b219506548d0d4a1227a8619623f18592db227c"
GOLDEN_MANIFEST_SHA256 = "62d2c21260162d4a8198f84e86f1b21f5dc9e5258ffa9116eced501e28a6b71e"
GOLDEN_BASELINE_SHA256 = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"

EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "ready": VALID_COUNT,
    "holds": HOLD_COUNT,
    "hold_duplicate_id": DUPLICATE_COUNT,
    "hold_broken_sample_test_ref": BROKEN_REF_COUNT,
    "hold_method_version_conflict": METHOD_CONFLICT_COUNT,
    "hold_hash_mismatch": HASH_MISMATCH_COUNT,
    "mapped": VALID_COUNT,
    "orphans": 0,
    "duplicates": 0,
    "replay_added_mappings": 0,
    "replay_added_objects": 0,
    "released_results": 0,
    "released_reports": 0,
    "production_writes": 0,
}


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


CATALOG_SHA256 = sha256_hex(PANTHER_FUSION_CATALOG)


def _method_pair(index: int) -> tuple[str, str]:
    return METHOD_PAIRS[index % len(METHOD_PAIRS)]


def _result_payload(index: int, method: str, version: str) -> dict[str, Any]:
    # Raw instrument fields only. No Detected / Not Detected / Positive / Negative.
    return {
        "cycle_index": index,
        "rf_units": (index % 97) + 3,
        "method": method,
        "method_version": version,
        "instrument": "SYN-PANTHER-FUSION",
    }


def _report_payload(accession_id: str, sample_id: str, test_id: str, result_hash: str) -> dict[str, Any]:
    return {
        "accession_id": accession_id,
        "sample_id": sample_id,
        "test_id": test_id,
        "result_hash": result_hash,
        "interpretation": None,
        "public_health_call": None,
    }


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "demand_id": DEMAND_ID,
        "legacy_id": row["legacy_id"],
        "channel": row["channel"],
        "accession_id": row["accession_id"],
        "requisition_id": row["requisition_id"],
        "sample_id": row["sample_id"],
        "test_id": row["test_id"],
        "sample_test_ref": row["sample_test_ref"],
        "method": row["method"],
        "method_version": row["method_version"],
    }


def _stamp_hashes(row: dict[str, Any]) -> dict[str, Any]:
    row["result_hash"] = sha256_hex(row["result"])
    row["report"] = _report_payload(
        row["accession_id"],
        row["sample_id"],
        row["test_id"],
        row["result_hash"],
    )
    row["report_hash"] = sha256_hex(row["report"])
    row["source"] = _source_payload(row)
    row["source_hash"] = sha256_hex(row["source"])
    return row


def _valid_bundle(index: int) -> dict[str, Any]:
    # index is 1-based for human IDs
    method, version = _method_pair(index - 1)
    channel = "REQUISITION" if index % 2 == 1 else "PORTAL"
    prefix = "REQ" if channel == "REQUISITION" else "PRT"
    row: dict[str, Any] = {
        "bundle_id": f"SLO-{index:04d}",
        "legacy_id": f"INC-{index:04d}",
        "channel": channel,
        "accession_id": f"ACC-{index:04d}",
        "requisition_id": f"{prefix}-{index:04d}",
        "sample_id": f"SMP-{index:04d}",
        "test_id": f"TST-{index:04d}",
        "sample_test_ref": f"SMP-{index:04d}->TST-{index:04d}",
        "method": method,
        "method_version": version,
        "result": _result_payload(index, method, version),
        "expected_state": "READY",
        "expected_hold": None,
    }
    return _stamp_hashes(row)


def _duplicate_bundle(slot: int) -> dict[str, Any]:
    source = _valid_bundle(slot + 1)
    row = deepcopy(source)
    row["bundle_id"] = f"SLO-D-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "DUPLICATE_ID"
    return row


def _broken_ref_bundle(slot: int) -> dict[str, Any]:
    index = VALID_COUNT + slot + 1
    row = _valid_bundle(index)
    row["bundle_id"] = f"SLO-B-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "BROKEN_SAMPLE_TEST_REF"
    if slot % 2 == 0:
        row["sample_test_ref"] = f"{row['sample_id']}->TST-MISSING"
    else:
        row["sample_test_ref"] = f"SMP-MISSING->{row['test_id']}"
    return _stamp_hashes(row)


def _method_conflict_bundle(slot: int) -> dict[str, Any]:
    index = VALID_COUNT + BROKEN_REF_COUNT + slot + 1
    row = _valid_bundle(index)
    row["bundle_id"] = f"SLO-M-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "METHOD_VERSION_CONFLICT"
    if slot % 2 == 0:
        row["method"] = "PF-UNKNOWN"
        row["method_version"] = "0.0.0"
    else:
        row["method_version"] = "9.9.9"
    row["result"] = _result_payload(index, row["method"], row["method_version"])
    return _stamp_hashes(row)


def _hash_mismatch_bundle(slot: int) -> dict[str, Any]:
    index = VALID_COUNT + BROKEN_REF_COUNT + METHOD_CONFLICT_COUNT + slot + 1
    row = _valid_bundle(index)
    row["bundle_id"] = f"SLO-H-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HASH_MISMATCH"
    if slot % 3 == 0:
        row["result_hash"] = "0" * 64
    elif slot % 3 == 1:
        row["report_hash"] = "1" * 64
    else:
        row["source_hash"] = "2" * 64
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_valid_bundle(i) for i in range(1, VALID_COUNT + 1)]
    rows.extend(_duplicate_bundle(i) for i in range(DUPLICATE_COUNT))
    rows.extend(_broken_ref_bundle(i) for i in range(BROKEN_REF_COUNT))
    rows.extend(_method_conflict_bundle(i) for i in range(METHOD_CONFLICT_COUNT))
    rows.extend(_hash_mismatch_bundle(i) for i in range(HASH_MISMATCH_COUNT))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s rows, got %s" % (INPUT_COUNT, len(rows)))
    ready = [row for row in rows if row["expected_state"] == "READY"]
    holds = [row for row in rows if row["expected_state"] == "HOLD"]
    if len(ready) != VALID_COUNT or len(holds) != HOLD_COUNT:
        raise RuntimeError("acceptance fixture split must be 850/150")
    codes = [row["expected_hold"] for row in holds]
    for code, count in HOLD_FAMILY_COUNTS.items():
        if codes.count(code) != count:
            raise RuntimeError("%s must appear exactly %s times" % (code, count))
    ids = [row["bundle_id"] for row in rows]
    if len(set(ids)) != INPUT_COUNT:
        raise RuntimeError("bundle_id values must be unique")
    return rows


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    return sha256_hex(rows if rows is not None else build_acceptance_fixture())


class SimulatedIncumbentAdapter:
    """Read-only shadow of the incumbent LIMS. No writes."""

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
        raise RuntimeError("incumbent adapter is read-only")


class SimulatedClsAdapter:
    """Simulated CliniSys target. Snapshot / apply / rollback only. Not live."""

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

    def put(self, cls_id: str, obj: dict[str, Any]) -> None:
        self.objects[cls_id] = deepcopy(obj)

    def get(self, cls_id: str) -> dict[str, Any] | None:
        obj = self.objects.get(cls_id)
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
        "seen_legacy_ids": {},
        "seen_accession_ids": {},
        "ready": {},
        "holds": [],
        "mappings": {},
        "cls_index": {},
        "events": [],
        "released_results": {},
        "released_reports": {},
        "interface_live": False,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "production_writes": 0,
        "public_health_interpretation": False,
        "autonomous_release": False,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def sample_test_ref_ok(row: dict[str, Any]) -> bool:
    sample_id = _text(row.get("sample_id"))
    test_id = _text(row.get("test_id"))
    ref = _text(row.get("sample_test_ref"))
    if not sample_id or not test_id or not ref:
        return False
    return ref == f"{sample_id}->{test_id}"


def method_version_ok(row: dict[str, Any]) -> bool:
    method = _text(row.get("method"))
    version = _text(row.get("method_version"))
    spec = PANTHER_FUSION_CATALOG.get(method)
    if spec is None:
        return False
    return version in spec["versions"]


def hashes_ok(row: dict[str, Any]) -> bool:
    if sha256_hex(row.get("result")) != _text(row.get("result_hash")):
        return False
    if sha256_hex(row.get("report")) != _text(row.get("report_hash")):
        return False
    if sha256_hex(row.get("source")) != _text(row.get("source_hash")):
        return False
    return True


def classify_bundle(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    legacy_id = _text(row.get("legacy_id"))
    accession_id = _text(row.get("accession_id"))
    if not legacy_id or not accession_id:
        return {"ok": False, "code": "DUPLICATE_ID"}
    if legacy_id in journal["seen_legacy_ids"] or accession_id in journal["seen_accession_ids"]:
        return {"ok": False, "code": "DUPLICATE_ID"}
    if not sample_test_ref_ok(row):
        return {"ok": False, "code": "BROKEN_SAMPLE_TEST_REF"}
    if not method_version_ok(row):
        return {"ok": False, "code": "METHOD_VERSION_CONFLICT"}
    if not hashes_ok(row):
        return {"ok": False, "code": "HASH_MISMATCH"}
    return {"ok": True, "code": None}


def cls_object_id(row: dict[str, Any]) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "accession_id": row["accession_id"],
            "method": row["method"],
            "method_version": row["method_version"],
            "result_hash": row["result_hash"],
            "report_hash": row["report_hash"],
            "source_hash": row["source_hash"],
        }
    )
    return "CLS-" + digest[:16]


def ingest_bundle(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    bundle_id = _text(row.get("bundle_id"))
    legacy_id = _text(row.get("legacy_id"))
    existing = journal["ready"].get(legacy_id)
    if existing is not None and existing.get("bundle_id") == bundle_id:
        _event(journal, "REPLAY_NOOP", {"legacy_id": legacy_id, "bundle_id": bundle_id})
        return {"kind": "REPLAY_NOOP", "legacy_id": legacy_id, "bundle_id": bundle_id}

    verdict = classify_bundle(journal, row)
    if not verdict["ok"]:
        hold = {
            "bundle_id": bundle_id,
            "legacy_id": _text(row.get("legacy_id")) or None,
            "accession_id": _text(row.get("accession_id")) or None,
            "code": verdict["code"],
            "state": "HOLD",
            "mapped": False,
        }
        fingerprint = sha256_hex(hold)
        existing = {sha256_hex(item) for item in journal["holds"]}
        if fingerprint not in existing:
            journal["holds"].append(hold)
            _event(journal, "HOLD", hold)
        return {"kind": "HOLD", "duplicate": fingerprint in existing, **hold}

    legacy_id = _text(row["legacy_id"])
    accession_id = _text(row["accession_id"])
    if legacy_id in journal["ready"]:
        _event(journal, "REPLAY_NOOP", {"legacy_id": legacy_id, "bundle_id": bundle_id})
        return {"kind": "REPLAY_NOOP", "legacy_id": legacy_id, "bundle_id": bundle_id}

    record = {
        "bundle_id": bundle_id,
        "legacy_id": legacy_id,
        "channel": _text(row["channel"]),
        "accession_id": accession_id,
        "requisition_id": _text(row["requisition_id"]),
        "sample_id": _text(row["sample_id"]),
        "test_id": _text(row["test_id"]),
        "sample_test_ref": _text(row["sample_test_ref"]),
        "method": _text(row["method"]),
        "method_version": _text(row["method_version"]),
        "result": deepcopy(row["result"]),
        "report": deepcopy(row["report"]),
        "source": deepcopy(row["source"]),
        "result_hash": _text(row["result_hash"]),
        "report_hash": _text(row["report_hash"]),
        "source_hash": _text(row["source_hash"]),
        "cls_id": cls_object_id(row),
        "state": "READY",
        "mapped": False,
        "released_result": False,
        "released_report": False,
        "released_by": None,
        "interpretation": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    journal["ready"][legacy_id] = record
    journal["seen_legacy_ids"][legacy_id] = bundle_id
    journal["seen_accession_ids"][accession_id] = bundle_id
    _event(journal, "READY", {"legacy_id": legacy_id, "accession_id": accession_id, "cls_id": record["cls_id"]})
    return {"kind": "READY", "legacy_id": legacy_id, "cls_id": record["cls_id"]}


def migrate(journal: dict[str, Any], cls_adapter: SimulatedClsAdapter) -> dict[str, Any]:
    added_mappings = 0
    added_objects = 0
    for legacy_id, record in journal["ready"].items():
        cls_id = record["cls_id"]
        existing = journal["mappings"].get(legacy_id)
        if existing is not None:
            continue
        if cls_id in journal["cls_index"]:
            _event(journal, "DUPLICATE_CLS", {"legacy_id": legacy_id, "cls_id": cls_id})
            continue
        obj = {
            "cls_id": cls_id,
            "incumbent_id": legacy_id,
            "accession_id": record["accession_id"],
            "channel": record["channel"],
            "method": record["method"],
            "method_version": record["method_version"],
            "result_hash": record["result_hash"],
            "report_hash": record["report_hash"],
            "source_hash": record["source_hash"],
            "released_result": False,
            "released_report": False,
            "interpretation": None,
            "interface_state": "SIMULATED",
        }
        cls_adapter.put(cls_id, obj)
        journal["mappings"][legacy_id] = cls_id
        journal["cls_index"][cls_id] = legacy_id
        record["mapped"] = True
        added_mappings += 1
        added_objects += 1
        _event(journal, "MAP", {"legacy_id": legacy_id, "cls_id": cls_id})
    return {
        "added_mappings": added_mappings,
        "added_objects": added_objects,
        "mapped": len(journal["mappings"]),
        "cls_objects": len(cls_adapter.objects),
    }


def mapping_integrity(journal: dict[str, Any], cls_adapter: SimulatedClsAdapter) -> dict[str, Any]:
    mapped_ready = set(journal["mappings"])
    ready_ids = set(journal["ready"])
    cls_ids = set(cls_adapter.objects)
    mapped_cls = set(journal["mappings"].values())
    orphans = sorted(
        (ready_ids - mapped_ready)
        | (mapped_ready - ready_ids)
        | (cls_ids - mapped_cls)
        | (mapped_cls - cls_ids)
    )
    duplicate_incumbent = [lid for lid, cls_id in journal["mappings"].items() if journal["cls_index"].get(cls_id) != lid]
    reverse: dict[str, list[str]] = {}
    for lid, cls_id in journal["mappings"].items():
        reverse.setdefault(cls_id, []).append(lid)
    duplicate_cls = [cls_id for cls_id, lids in reverse.items() if len(lids) > 1]
    hold_mapped = [item["bundle_id"] for item in journal["holds"] if item.get("mapped")]
    return {
        "orphans": orphans,
        "orphan_count": len(orphans),
        "duplicate_incumbent": duplicate_incumbent,
        "duplicate_cls": duplicate_cls,
        "duplicate_count": len(duplicate_incumbent) + len(duplicate_cls),
        "hold_mapped": hold_mapped,
    }


def release_result(
    journal: dict[str, Any],
    cls_adapter: SimulatedClsAdapter,
    legacy_id: str,
    *,
    named_approver: str,
) -> dict[str, Any]:
    record = journal["ready"].get(legacy_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_OBJECT"}
    name = _text(named_approver)
    if not name:
        _event(journal, "RELEASE_DENIED", {"legacy_id": legacy_id, "code": "MISSING_NAMED_APPROVAL", "kind": "result"})
        return {"ok": False, "code": "MISSING_NAMED_APPROVAL"}
    if name.upper() in AUTONOMOUS_NAMES:
        _event(journal, "RELEASE_DENIED", {"legacy_id": legacy_id, "code": "AUTONOMOUS_RELEASE_DENIED", "kind": "result"})
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released_result"):
        return {"ok": True, "duplicate": True, "kind": "result"}
    record["released_result"] = True
    record["released_by"] = name
    journal["released_results"][legacy_id] = name
    obj = cls_adapter.objects.get(record["cls_id"])
    if obj is not None:
        obj["released_result"] = True
        obj["released_by"] = name
    _event(journal, "RELEASED_RESULT", {"legacy_id": legacy_id, "released_by": name})
    return {"ok": True, "duplicate": False, "kind": "result", "released_by": name}


def release_report(
    journal: dict[str, Any],
    cls_adapter: SimulatedClsAdapter,
    legacy_id: str,
    *,
    named_approver: str,
) -> dict[str, Any]:
    record = journal["ready"].get(legacy_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_OBJECT"}
    name = _text(named_approver)
    if not name:
        _event(journal, "RELEASE_DENIED", {"legacy_id": legacy_id, "code": "MISSING_NAMED_APPROVAL", "kind": "report"})
        return {"ok": False, "code": "MISSING_NAMED_APPROVAL"}
    if name.upper() in AUTONOMOUS_NAMES:
        _event(journal, "RELEASE_DENIED", {"legacy_id": legacy_id, "code": "AUTONOMOUS_RELEASE_DENIED", "kind": "report"})
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if not record.get("released_result"):
        _event(journal, "RELEASE_DENIED", {"legacy_id": legacy_id, "code": "RESULT_NOT_RELEASED", "kind": "report"})
        return {"ok": False, "code": "RESULT_NOT_RELEASED"}
    if record.get("released_report"):
        return {"ok": True, "duplicate": True, "kind": "report"}
    record["released_report"] = True
    record["released_by"] = name
    journal["released_reports"][legacy_id] = name
    obj = cls_adapter.objects.get(record["cls_id"])
    if obj is not None:
        obj["released_report"] = True
        obj["released_by"] = name
    _event(journal, "RELEASED_REPORT", {"legacy_id": legacy_id, "released_by": name})
    return {"ok": True, "duplicate": False, "kind": "report", "released_by": name}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    incumbent = SimulatedIncumbentAdapter(inbound)
    cls_adapter = SimulatedClsAdapter()
    journal = empty_journal()
    baseline = cls_adapter.snapshot()
    effects = [ingest_bundle(journal, row) for row in incumbent.list_bundles()]
    first_migrate = migrate(journal, cls_adapter)
    integrity = mapping_integrity(journal, cls_adapter)
    replay_migrate = migrate(journal, cls_adapter)
    replay_ingest = [ingest_bundle(journal, row) for row in inbound]
    autonomous = []
    for legacy_id in list(journal["ready"]):
        autonomous.append(release_result(journal, cls_adapter, legacy_id, named_approver="SYSTEM"))
        autonomous.append(release_report(journal, cls_adapter, legacy_id, named_approver=""))
    after_migrate_hash = cls_adapter.baseline_hash()
    rollback = cls_adapter.rollback(baseline)
    restored_hash = cls_adapter.baseline_hash()

    ready = sorted(journal["ready"].values(), key=lambda item: item["legacy_id"])
    hold_codes = sorted(item["code"] for item in journal["holds"])
    hold_code_counts = {code: hold_codes.count(code) for code in HOLD_CODES}
    accession_channels = {
        "REQUISITION": sum(1 for item in ready if item["channel"] == "REQUISITION"),
        "PORTAL": sum(1 for item in ready if item["channel"] == "PORTAL"),
    }

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "ready": len(ready),
        "holds": len(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_code_counts": hold_code_counts,
        "mapped": len(journal["mappings"]),
        "cls_objects": first_migrate["cls_objects"],
        "orphans": integrity["orphan_count"],
        "orphan_ids": integrity["orphans"],
        "duplicates": integrity["duplicate_count"],
        "hold_mapped": integrity["hold_mapped"],
        "accession_channels": accession_channels,
        "ready_ids": [item["legacy_id"] for item in ready],
        "cls_ids": [item["cls_id"] for item in ready],
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
        "released_results": len(journal["released_results"]),
        "released_reports": len(journal["released_reports"]),
        "autonomous_release_effects": autonomous,
        "effects": effects,
        "ready_records": ready,
        "hold_records": deepcopy(journal["holds"]),
        "catalog_sha256": CATALOG_SHA256,
        "fixture_sha256": fixture_sha256(inbound),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "incumbent_writes": incumbent.writes,
        "production_writes": cls_adapter.production_writes,
        "public_health_interpretation": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != INPUT_COUNT:
        failures.append("input_rows!=1000")
    if result.get("ready") != VALID_COUNT:
        failures.append("ready!=850")
    if result.get("holds") != HOLD_COUNT:
        failures.append("holds!=150")
    counts = result.get("hold_code_counts") or {}
    if counts.get("DUPLICATE_ID") != DUPLICATE_COUNT:
        failures.append("hold_duplicate_id")
    if counts.get("BROKEN_SAMPLE_TEST_REF") != BROKEN_REF_COUNT:
        failures.append("hold_broken_sample_test_ref")
    if counts.get("METHOD_VERSION_CONFLICT") != METHOD_CONFLICT_COUNT:
        failures.append("hold_method_version_conflict")
    if counts.get("HASH_MISMATCH") != HASH_MISMATCH_COUNT:
        failures.append("hold_hash_mismatch")
    if result.get("mapped") != VALID_COUNT:
        failures.append("mapped!=850")
    if result.get("cls_objects") != VALID_COUNT:
        failures.append("cls_objects!=850")
    if result.get("orphans") != 0:
        failures.append("orphans")
    if result.get("duplicates") != 0:
        failures.append("duplicates")
    if result.get("hold_mapped"):
        failures.append("hold_mapped")
    if len(set(result.get("ready_ids") or [])) != VALID_COUNT:
        failures.append("ready_ids_not_unique")
    if len(set(result.get("cls_ids") or [])) != VALID_COUNT:
        failures.append("cls_ids_not_unique")
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
    if result.get("released_results") != 0:
        failures.append("released_results")
    if result.get("released_reports") != 0:
        failures.append("released_reports")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("shadowing") != "READ_ONLY":
        failures.append("shadowing")
    if result.get("incumbent_writes") != 0:
        failures.append("incumbent_writes")
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
        item.get("ok") is False
        and item.get("code") in {"AUTONOMOUS_RELEASE_DENIED", "MISSING_NAMED_APPROVAL"}
        for item in autos
    ):
        failures.append("autonomous_release_not_denied")
    for item in result.get("ready_records") or []:
        if item.get("interpretation") is not None:
            failures.append("interpretation_present")
            break
        if item.get("result", {}).get("call") or item.get("report", {}).get("public_health_call"):
            failures.append("public_health_call")
            break
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result.get("input_rows"),
        "ready": result.get("ready"),
        "holds": result.get("holds"),
        "hold_duplicate_id": (result.get("hold_code_counts") or {}).get("DUPLICATE_ID"),
        "hold_broken_sample_test_ref": (result.get("hold_code_counts") or {}).get("BROKEN_SAMPLE_TEST_REF"),
        "hold_method_version_conflict": (result.get("hold_code_counts") or {}).get("METHOD_VERSION_CONFLICT"),
        "hold_hash_mismatch": (result.get("hold_code_counts") or {}).get("HASH_MISMATCH"),
        "mapped": result.get("mapped"),
        "orphans": result.get("orphans"),
        "duplicates": result.get("duplicates"),
        "replay_added_mappings": result.get("replay_added_mappings"),
        "replay_added_objects": result.get("replay_added_objects"),
        "released_results": result.get("released_results"),
        "released_reports": result.get("released_reports"),
        "production_writes": result.get("production_writes"),
    }
    return {"expected": EXPECTED_COUNTS, "actual": actual, "match": actual == EXPECTED_COUNTS}


def main() -> int:
    first = run_gate()
    second = run_gate()
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "counts": counts,
        "manifest_sha256": first.get("manifest_sha256"),
        "fixture_sha256": first.get("fixture_sha256"),
        "catalog_sha256": first.get("catalog_sha256"),
        "baseline_hash": first.get("baseline_hash"),
        "after_migrate_hash": first.get("after_migrate_hash"),
        "restored_hash": first.get("restored_hash"),
        "ready": first.get("ready"),
        "holds": first.get("holds"),
        "hold_code_counts": first.get("hold_code_counts"),
        "mapped": first.get("mapped"),
        "orphans": first.get("orphans"),
        "duplicates": first.get("duplicates"),
        "replay_added_mappings": first.get("replay_added_mappings"),
        "released_results": first.get("released_results"),
        "released_reports": first.get("released_reports"),
        "rollback_restored_baseline": first.get("rollback_restored_baseline"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

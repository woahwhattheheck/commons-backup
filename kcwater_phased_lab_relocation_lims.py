#!/usr/bin/env python3
"""Synthetic KC Water phased-laboratory accession and result router.

Demand: kcwater-phased-lab-relocation-lims-01
Buyer: Jessica Jensen / KC Water Laboratory

This fixture-only engine routes de-identified synthetic drinking-water,
wastewater, and stormwater submissions across main, temporary, and
contingency sites. It has no live adapter, clinical use, production write,
or automatic report release.

Official acceptance:
    python test_kcwater_phased_lab_relocation_lims.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEMAND_ID = "kcwater-phased-lab-relocation-lims-01"
SCHEMA = "commons-kcwater-phased-lab-relocation-lims/v1"
BUYER = "Jessica Jensen / KC Water Laboratory"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
OFFICIAL_BINARY = "python kcwater_phased_lab_relocation_lims.py"
OFFICIAL_TEST = "python test_kcwater_phased_lab_relocation_lims.py"

INPUT_COUNT = 300
READY_COUNT = 240
DUPLICATE_CONTAINER_COUNT = 20
SITE_METHOD_SCOPE_MISMATCH_COUNT = 20
CUSTODY_TEMPERATURE_FAILURE_COUNT = 20
HOLD_COUNT = DUPLICATE_CONTAINER_COUNT + SITE_METHOD_SCOPE_MISMATCH_COUNT + CUSTODY_TEMPERATURE_FAILURE_COUNT
HOLD_CODES = ("HOLD_DUPLICATE_CONTAINER", "HOLD_SITE_METHOD_SCOPE_MISMATCH", "HOLD_CUSTODY_TEMPERATURE_FAILURE")
HOLD_COUNTS = {"HOLD_DUPLICATE_CONTAINER": DUPLICATE_CONTAINER_COUNT, "HOLD_SITE_METHOD_SCOPE_MISMATCH": SITE_METHOD_SCOPE_MISMATCH_COUNT, "HOLD_CUSTODY_TEMPERATURE_FAILURE": CUSTODY_TEMPERATURE_FAILURE_COUNT}

SITE_IDS = ("KCW-MAIN", "KCW-TEMP", "KCW-CONTINGENCY")
WATER_CLASSES = ("DRINKING", "WASTEWATER", "STORMWATER")
METHOD_CATALOG: dict[str, dict[str, str]] = {
    "DRINKING": {"method_id": "EPA-200.8", "method_version": "2026.1", "unit": "ug/L", "qualifier": "ACCEPTED"},
    "WASTEWATER": {"method_id": "SM-5220D", "method_version": "23rd-edition", "unit": "mg/L", "qualifier": "ACCEPTED"},
    "STORMWATER": {"method_id": "EPA-160.2", "method_version": "2026.1", "unit": "mg/L", "qualifier": "ESTIMATED"},
}
ROUTE_CATALOG: dict[str, dict[str, str | bool]] = {
    f"{site}-{water}-INSTRUMENT": {"route_id": f"KCW-ROUTE-{site.removeprefix('KCW-')}-{water}", "site_id": site, "instrument_id": f"{site}-{water}-INSTRUMENT", "water_class": water, **METHOD_CATALOG[water], "active": True}
    for site in SITE_IDS for water in WATER_CLASSES
}
RELEASE_DIRECTORY = {"SYN-NAMED-HUMAN-JESSICA-JENSEN-01": {"display_name": "Jessica Jensen (synthetic release authority)", "permissions": ("RELEASE_STAGED_REPORT",), "named_human": True}}
AUTOMATION_IDENTITIES = frozenset({"", "SYSTEM", "AUTO", "AUTOMATION", "BOT", "MACHINE"})


class InputError(ValueError):
    """Typed inbound-schema failure."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _receipt_goldens() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "revenue" / "kcwater_phased_lab_relocation_lims" / "receipt.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    return {key: str(value.get(key) or "pending") for key in ("fixture_sha256", "manifest_sha256", "audit_sha256")}


_GOLDENS = _receipt_goldens()
GOLDEN_FIXTURE_SHA256 = _GOLDENS["fixture_sha256"]
GOLDEN_MANIFEST_SHA256 = _GOLDENS["manifest_sha256"]
GOLDEN_AUDIT_SHA256 = _GOLDENS["audit_sha256"]


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object")
    return value


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InputError(f"{field} must be a string")
    clean = value.strip()
    if not allow_empty and not clean:
        raise InputError(f"{field} is required")
    return clean


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise InputError(f"{field} must be a boolean")
    return value


def _nonnegative_number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{field} must be a finite non-negative number")
    if not math.isfinite(float(value)) or value < 0:
        raise InputError(f"{field} must be a finite non-negative number")
    return value


def _timestamp(value: Any, field: str) -> str:
    text = _text(value, field)
    if not text.endswith("Z"):
        raise InputError(f"{field} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"{field} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise InputError(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _accession_id(submission_id: str) -> str:
    return "KCW-ACC-" + sha256_hex({"demand_id": DEMAND_ID, "submission_id": submission_id})[:14]


def _test_id(accession_id: str, route_id: str, method_id: str, method_version: str) -> str:
    return "KCW-TEST-" + sha256_hex({"demand_id": DEMAND_ID, "accession_id": accession_id, "route_id": route_id, "method_id": method_id, "method_version": method_version})[:14]


def _result_id(test_id: str, source_uri: str) -> str:
    return "KCW-RES-" + sha256_hex({"demand_id": DEMAND_ID, "test_id": test_id, "source_uri": source_uri})[:14]


def _report_id(result_id: str) -> str:
    return "KCW-RPT-" + sha256_hex({"demand_id": DEMAND_ID, "result_id": result_id})[:14]


def _source_uri(site_id: str, instrument_id: str, token: str) -> str:
    return f"synthetic://kcwater/{site_id}/{instrument_id}/run-{token}.json"


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("submission_id", "container_id", "sample_id", "site_id", "instrument_id", "water_class", "collected_at", "received_at", "custody_chain_intact", "custody_seal_id", "temperature_c", "container_volume_ml", "synthetic", "deidentified")}


def _method_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("site_id", "instrument_id", "water_class", "method_id", "method_version")}


def _result_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("sample_id", "site_id", "instrument_id", "method_id", "method_version", "raw_source_uri", "raw_source_revision", "result_value", "result_unit", "result_qualifier")}


def _matching_routes(row: dict[str, Any]) -> list[dict[str, str | bool]]:
    return [route for route in ROUTE_CATALOG.values() if route["active"] is True and route["site_id"] == row["site_id"] and route["instrument_id"] == row["instrument_id"] and route["water_class"] == row["water_class"] and route["method_id"] == row["method_id"] and route["method_version"] == row["method_version"]]


def _derived_hashes(row: dict[str, Any]) -> dict[str, str]:
    source_hash = sha256_hex(_source_payload(row))
    method_hash = sha256_hex(_method_payload(row))
    result_hash = sha256_hex(_result_payload(row))
    accession_id = _accession_id(row["submission_id"])
    routes = _matching_routes(row)
    route_id = str(routes[0]["route_id"]) if len(routes) == 1 else "UNROUTABLE"
    test_id = _test_id(accession_id, route_id, row["method_id"], row["method_version"])
    result_id = _result_id(test_id, row["raw_source_uri"])
    report_core = {"report_id": _report_id(result_id), "accession_id": accession_id, "test_id": test_id, "result_id": result_id, "site_id": row["site_id"], "instrument_id": row["instrument_id"], "source_sha256": source_hash, "method_sha256": method_hash, "result_sha256": result_hash, "value_sha256": sha256_hex({"value": row["result_value"]}), "unit_sha256": sha256_hex({"unit": row["result_unit"]}), "qualifier_sha256": sha256_hex({"qualifier": row["result_qualifier"]}), "status": "STAGED"}
    return {"source_sha256": source_hash, "method_sha256": method_hash, "result_sha256": result_hash, "value_sha256": report_core["value_sha256"], "unit_sha256": report_core["unit_sha256"], "qualifier_sha256": report_core["qualifier_sha256"], "report_sha256": sha256_hex(report_core)}


def _stamp_goldens(row: dict[str, Any]) -> dict[str, Any]:
    stamped = deepcopy(row)
    stamped["golden_hashes"] = _derived_hashes(stamped)
    return stamped


def _base_submission(index: int) -> dict[str, Any]:
    token = f"{index:04d}"
    water_class = WATER_CLASSES[(index - 1) % len(WATER_CLASSES)]
    site_id = SITE_IDS[((index - 1) // 80) % len(SITE_IDS)]
    method = METHOD_CATALOG[water_class]
    instrument_id = f"{site_id}-{water_class}-INSTRUMENT"
    return {"row_id": f"KCW-ROW-{token}", "submission_id": f"KCW-SUB-{token}", "container_id": f"KCW-CONT-{token}", "sample_id": f"KCW-SAMPLE-{token}", "site_id": site_id, "instrument_id": instrument_id, "water_class": water_class, "collected_at": "2026-09-01T08:00:00Z", "received_at": "2026-09-01T10:00:00Z", "custody_chain_intact": True, "custody_seal_id": f"KCW-SEAL-{token}", "temperature_c": 4.5, "container_volume_ml": 1000.0, "method_id": method["method_id"], "method_version": method["method_version"], "raw_source_uri": _source_uri(site_id, instrument_id, token), "raw_source_revision": "SYN-2026.09", "result_value": round(0.125 + index * 0.03125, 5), "result_unit": method["unit"], "result_qualifier": method["qualifier"], "synthetic": True, "deidentified": True, "expected_state": "READY", "expected_hold": None}


def _duplicate_container_submission(slot: int) -> dict[str, Any]:
    row = _base_submission(READY_COUNT + slot)
    row["container_id"] = f"KCW-CONT-{slot:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HOLD_DUPLICATE_CONTAINER"
    return _stamp_goldens(row)


def _site_method_scope_mismatch_submission(slot: int) -> dict[str, Any]:
    index = READY_COUNT + DUPLICATE_CONTAINER_COUNT + slot
    row = _base_submission(index)
    alternative = WATER_CLASSES[(WATER_CLASSES.index(row["water_class"]) + 1) % len(WATER_CLASSES)]
    row["method_id"] = METHOD_CATALOG[alternative]["method_id"]
    row["method_version"] = METHOD_CATALOG[alternative]["method_version"]
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HOLD_SITE_METHOD_SCOPE_MISMATCH"
    return _stamp_goldens(row)


def _custody_temperature_failure_submission(slot: int) -> dict[str, Any]:
    index = READY_COUNT + DUPLICATE_CONTAINER_COUNT + SITE_METHOD_SCOPE_MISMATCH_COUNT + slot
    row = _base_submission(index)
    if slot <= CUSTODY_TEMPERATURE_FAILURE_COUNT // 2:
        row["custody_chain_intact"] = False
    else:
        row["temperature_c"] = 18.0
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HOLD_CUSTODY_TEMPERATURE_FAILURE"
    return _stamp_goldens(row)


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_stamp_goldens(_base_submission(index)) for index in range(1, 241)]
    rows.extend(_duplicate_container_submission(slot) for slot in range(1, 21))
    rows.extend(_site_method_scope_mismatch_submission(slot) for slot in range(1, 21))
    rows.extend(_custody_temperature_failure_submission(slot) for slot in range(1, 21))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("fixture cardinality drift")
    return rows


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    return sha256_hex(rows if rows is not None else build_acceptance_fixture())


class SyntheticReadOnlySubmissionAdapter:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = deepcopy(rows)
        self.mode = "SYNTHETIC_READ_ONLY"
        self.live = False
        self.writes = 0

    def list_submissions(self) -> list[dict[str, Any]]:
        return deepcopy(self._rows)

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("synthetic source adapter is read-only")


def empty_journal() -> dict[str, Any]:
    return {"schema": SCHEMA, "demand_id": DEMAND_ID, "buyer": BUYER, "processed_rows": {}, "container_index": {}, "accessions": {}, "tests": {}, "results": {}, "reports": {}, "holds": [], "events": [], "interface_live": False, "interfaces": "SYNTHETIC_READ_ONLY", "production_writes": 0, "automatic_releases": 0}


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def _commit(journal: dict[str, Any], candidate: dict[str, Any]) -> None:
    journal.clear()
    journal.update(candidate)


def normalize_submission(row: dict[str, Any]) -> dict[str, Any]:
    source = _mapping(row, "row")
    golden = _mapping(source.get("golden_hashes"), "golden_hashes")
    return {"row_id": _text(source.get("row_id"), "row_id"), "submission_id": _text(source.get("submission_id"), "submission_id"), "container_id": _text(source.get("container_id"), "container_id"), "sample_id": _text(source.get("sample_id"), "sample_id"), "site_id": _text(source.get("site_id"), "site_id"), "instrument_id": _text(source.get("instrument_id"), "instrument_id"), "water_class": _text(source.get("water_class"), "water_class").upper(), "collected_at": _timestamp(source.get("collected_at"), "collected_at"), "received_at": _timestamp(source.get("received_at"), "received_at"), "custody_chain_intact": _bool(source.get("custody_chain_intact"), "custody_chain_intact"), "custody_seal_id": _text(source.get("custody_seal_id"), "custody_seal_id"), "temperature_c": _nonnegative_number(source.get("temperature_c"), "temperature_c"), "container_volume_ml": _nonnegative_number(source.get("container_volume_ml"), "container_volume_ml"), "method_id": _text(source.get("method_id"), "method_id"), "method_version": _text(source.get("method_version"), "method_version"), "raw_source_uri": _text(source.get("raw_source_uri"), "raw_source_uri"), "raw_source_revision": _text(source.get("raw_source_revision"), "raw_source_revision"), "result_value": _nonnegative_number(source.get("result_value"), "result_value"), "result_unit": _text(source.get("result_unit"), "result_unit"), "result_qualifier": _text(source.get("result_qualifier"), "result_qualifier").upper(), "synthetic": _bool(source.get("synthetic"), "synthetic"), "deidentified": _bool(source.get("deidentified"), "deidentified"), "golden_hashes": {key: _text(golden.get(key), f"golden_hashes.{key}") for key in ("source_sha256", "method_sha256", "result_sha256", "value_sha256", "unit_sha256", "qualifier_sha256", "report_sha256")}}


def classify_submission(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    if not row["synthetic"] or not row["deidentified"]:
        return {"ok": False, "code": "HOLD_TRUTH_BOUNDARY"}
    routes = _matching_routes(row)
    if len(routes) != 1:
        return {"ok": False, "code": "HOLD_SITE_METHOD_SCOPE_MISMATCH"}
    if _parse_timestamp(row["received_at"]) < _parse_timestamp(row["collected_at"]):
        return {"ok": False, "code": "HOLD_CUSTODY_TEMPERATURE_FAILURE"}
    if not row["custody_chain_intact"] or not 0 <= row["temperature_c"] <= 10 or row["container_volume_ml"] <= 0:
        return {"ok": False, "code": "HOLD_CUSTODY_TEMPERATURE_FAILURE"}
    if row["container_id"] in journal["container_index"]:
        return {"ok": False, "code": "HOLD_DUPLICATE_CONTAINER"}
    method = METHOD_CATALOG.get(row["water_class"])
    if method is None or row["method_id"] != method["method_id"] or row["method_version"] != method["method_version"] or row["result_unit"] != method["unit"] or row["result_qualifier"] != method["qualifier"]:
        return {"ok": False, "code": "HOLD_SITE_METHOD_SCOPE_MISMATCH"}
    if row["raw_source_uri"] != _source_uri(row["site_id"], row["instrument_id"], row["submission_id"].removeprefix("KCW-SUB-")):
        return {"ok": False, "code": "HOLD_CROSS_SITE_RESULT"}
    if row["golden_hashes"] != _derived_hashes(row):
        return {"ok": False, "code": "HOLD_GOLDEN_HASH_MISMATCH"}
    return {"ok": True, "code": None, "route": routes[0]}


def ingest_submission(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    try:
        norm = normalize_submission(row)
    except (InputError, KeyError, TypeError, ValueError) as exc:
        return {"kind": "REJECT", "ok": False, "code": "REJECT_INVALID_INPUT", "row_id": row.get("row_id", "").strip() if isinstance(row, dict) and isinstance(row.get("row_id"), str) else "", "detail": str(exc)}
    row_id = norm["row_id"]
    payload_sha256 = sha256_hex(norm)
    prior = journal["processed_rows"].get(row_id)
    if prior is not None:
        if prior["payload_sha256"] != payload_sha256:
            return {"kind": "REPLAY_CONFLICT", "ok": False, "code": "REPLAY_PAYLOAD_DIGEST_CONFLICT", "row_id": row_id}
        return {"kind": "REPLAY_NOOP", "ok": True, "row_id": row_id, "prior_kind": prior["kind"]}
    candidate = deepcopy(journal)
    verdict = classify_submission(candidate, norm)
    if not verdict["ok"]:
        hold = {"row_id": row_id, "submission_id": norm["submission_id"], "container_id": norm["container_id"], "code": verdict["code"], "state": "HOLD", "accessions_created": 0, "tests_created": 0, "results_created": 0, "reports_staged": 0, "reports_released": 0}
        candidate["holds"].append(hold)
        candidate["processed_rows"][row_id] = {"kind": "HOLD", "code": verdict["code"], "payload_sha256": payload_sha256}
        _event(candidate, "HOLD", hold)
        _commit(journal, candidate)
        return {"kind": "HOLD", "ok": False, **deepcopy(hold)}
    route = verdict["route"]
    accession_id = _accession_id(norm["submission_id"])
    test_id = _test_id(accession_id, str(route["route_id"]), norm["method_id"], norm["method_version"])
    result_id = _result_id(test_id, norm["raw_source_uri"])
    report_id = _report_id(result_id)
    if any(identifier in collection for identifier, collection in ((accession_id, candidate["accessions"]), (test_id, candidate["tests"]), (result_id, candidate["results"]), (report_id, candidate["reports"]))):
        return {"kind": "REJECT", "ok": False, "code": "REJECT_DERIVED_IDENTIFIER_COLLISION", "row_id": row_id}
    hashes = _derived_hashes(norm)
    accession = {"accession_id": accession_id, "submission_id": norm["submission_id"], "container_id": norm["container_id"], "sample_id": norm["sample_id"], "site_id": norm["site_id"], "source_sha256": hashes["source_sha256"], "state": "ACCESSIONED"}
    test = {"test_id": test_id, "accession_id": accession_id, "route_id": route["route_id"], "site_id": norm["site_id"], "instrument_id": norm["instrument_id"], "water_class": norm["water_class"], "method_id": norm["method_id"], "method_version": norm["method_version"], "method_sha256": hashes["method_sha256"], "state": "COMPLETE_PENDING_REVIEW"}
    result = {"result_id": result_id, "test_id": test_id, "accession_id": accession_id, "site_id": norm["site_id"], "instrument_id": norm["instrument_id"], "source_uri": norm["raw_source_uri"], "source_revision": norm["raw_source_revision"], "value": norm["result_value"], "unit": norm["result_unit"], "qualifier": norm["result_qualifier"], "source_sha256": hashes["source_sha256"], "method_sha256": hashes["method_sha256"], "result_sha256": hashes["result_sha256"], "value_sha256": hashes["value_sha256"], "unit_sha256": hashes["unit_sha256"], "qualifier_sha256": hashes["qualifier_sha256"]}
    report = {"report_id": report_id, "accession_id": accession_id, "test_id": test_id, "result_id": result_id, "site_id": norm["site_id"], "instrument_id": norm["instrument_id"], "source_sha256": hashes["source_sha256"], "method_sha256": hashes["method_sha256"], "result_sha256": hashes["result_sha256"], "value_sha256": hashes["value_sha256"], "unit_sha256": hashes["unit_sha256"], "qualifier_sha256": hashes["qualifier_sha256"], "report_sha256": hashes["report_sha256"], "status": "STAGED", "released": False, "released_by": None}
    candidate["accessions"][accession_id] = accession
    candidate["tests"][test_id] = test
    candidate["results"][result_id] = result
    candidate["reports"][report_id] = report
    candidate["container_index"][norm["container_id"]] = {"row_id": row_id, "accession_id": accession_id}
    candidate["processed_rows"][row_id] = {"kind": "READY", "payload_sha256": payload_sha256, "accession_id": accession_id, "test_id": test_id, "result_id": result_id, "report_id": report_id}
    _event(candidate, "REPORT_STAGED", {"row_id": row_id, "accession_id": accession_id, "test_id": test_id, "result_id": result_id, "report_id": report_id, "route_id": route["route_id"]})
    _commit(journal, candidate)
    return {"kind": "READY", "ok": True, "row_id": row_id, "accession_id": accession_id, "test_id": test_id, "result_id": result_id, "report_id": report_id, "route_id": route["route_id"]}


def release_report(journal: dict[str, Any], report_id: str, *, reviewer_id: str) -> dict[str, Any]:
    if not isinstance(report_id, str) or not isinstance(reviewer_id, str):
        return {"ok": False, "code": "RELEASE_INVALID_INPUT"}
    report_id, reviewer_id = report_id.strip(), reviewer_id.strip()
    report = journal["reports"].get(report_id)
    if report is None:
        return {"ok": False, "code": "UNKNOWN_REPORT"}
    if reviewer_id.upper() in AUTOMATION_IDENTITIES:
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    reviewer = RELEASE_DIRECTORY.get(reviewer_id)
    if reviewer is None or reviewer.get("named_human") is not True or "RELEASE_STAGED_REPORT" not in reviewer.get("permissions", ()) or not reviewer.get("display_name"):
        return {"ok": False, "code": "UNAUTHORIZED_REVIEWER"}
    if report["released"]:
        return {"ok": True, "duplicate": True, "status": "RELEASED", "released_by": deepcopy(report["released_by"])}
    candidate = deepcopy(journal)
    target = candidate["reports"][report_id]
    target["released"] = True
    target["released_by"] = {"reviewer_id": reviewer_id, "display_name": reviewer["display_name"]}
    target["status"] = "RELEASED"
    _event(candidate, "RELEASED", {"report_id": report_id, "reviewer_id": reviewer_id, "display_name": reviewer["display_name"]})
    _commit(journal, candidate)
    return {"ok": True, "duplicate": False, "status": "RELEASED", "released_by": deepcopy(target["released_by"])}


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, int]:
    before = {key: len(journal[key]) for key in ("accessions", "tests", "results", "reports", "holds")}
    effects = [ingest_submission(journal, row) for row in deepcopy(rows)]
    return {"added_accessions": len(journal["accessions"]) - before["accessions"], "added_tests": len(journal["tests"]) - before["tests"], "added_results": len(journal["results"]) - before["results"], "added_reports": len(journal["reports"]) - before["reports"], "added_holds": len(journal["holds"]) - before["holds"], "replay_noops": sum(item.get("kind") == "REPLAY_NOOP" for item in effects), "replay_conflicts": sum(item.get("kind") == "REPLAY_CONFLICT" for item in effects)}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    source = SyntheticReadOnlySubmissionAdapter(inbound)
    journal = empty_journal()
    effects = [ingest_submission(journal, row) for row in source.list_submissions()]
    autonomous_release_effects = [release_report(journal, report_id, reviewer_id="SYSTEM") for report_id in sorted(journal["reports"])[:3]]
    replay = replay_into(journal, inbound)
    accessions = sorted(deepcopy(list(journal["accessions"].values())), key=lambda item: item["accession_id"])
    tests = sorted(deepcopy(list(journal["tests"].values())), key=lambda item: item["test_id"])
    results = sorted(deepcopy(list(journal["results"].values())), key=lambda item: item["result_id"])
    reports = sorted(deepcopy(list(journal["reports"].values())), key=lambda item: item["report_id"])
    holds = sorted(deepcopy(journal["holds"]), key=lambda item: item["row_id"])
    hold_counts = {code: sum(item["code"] == code for item in holds) for code in HOLD_CODES}
    route_counts = {site_id: sum(item["site_id"] == site_id for item in tests) for site_id in SITE_IDS}
    report_by_result = {item["result_id"]: item for item in reports}
    accession_by_id = {item["accession_id"]: item for item in accessions}
    hash_match_counts = {"source": sum(result["source_sha256"] == accession_by_id[result["accession_id"]]["source_sha256"] for result in results), "value": sum(item["value_sha256"] == sha256_hex({"value": item["value"]}) for item in results), "unit": sum(item["unit_sha256"] == sha256_hex({"unit": item["unit"]}) for item in results), "qualifier": sum(item["qualifier_sha256"] == sha256_hex({"qualifier": item["qualifier"]}) for item in results), "report": sum(item["report_sha256"] == report_by_result[item["result_id"]]["report_sha256"] for item in reports)}
    manifest = {"demand_id": DEMAND_ID, "accession_ids": [item["accession_id"] for item in accessions], "test_ids": [item["test_id"] for item in tests], "result_ids": [item["result_id"] for item in results], "reports": [{"report_id": item["report_id"], "report_sha256": item["report_sha256"], "status": item["status"]} for item in reports], "holds": [(item["row_id"], item["submission_id"], item["code"]) for item in holds]}
    return {"schema": SCHEMA, "demand_id": DEMAND_ID, "buyer": BUYER, "truth_gate": TRUTH_GATE, "input_rows": len(inbound), "ready": len(accessions), "holds": len(holds), "accessions": len(accessions), "tests": len(tests), "results": len(results), "reports_staged": sum(item["status"] == "STAGED" for item in reports), "reports_released": sum(item["released"] for item in reports), "hold_counts": hold_counts, "route_counts": route_counts, "active_route_count": len(ROUTE_CATALOG), "hash_match_counts": hash_match_counts, "fixture_sha256": fixture_sha256(inbound), "manifest_sha256": sha256_hex(manifest), "accession_records": accessions, "test_records": tests, "result_records": results, "report_records": reports, "hold_records": holds, "effects": effects, "autonomous_release_effects": autonomous_release_effects, "replay": replay, "audit_sha256": sha256_hex({"events": journal["events"], "manifest": manifest, "replay": replay, "truth_gate": TRUTH_GATE}), "interface_live": False, "interfaces": "SYNTHETIC_READ_ONLY", "source_writes": source.writes, "production_writes": 0, "automatic_releases": journal["automatic_releases"], "autonomous_release": False, "pre_sale_transport": "NONE", "cash_usd": 0, "official_binary": OFFICIAL_BINARY, "official_test": OFFICIAL_TEST}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    checks = {"input_rows": result.get("input_rows") == INPUT_COUNT, "ready": result.get("ready") == READY_COUNT, "holds": result.get("holds") == HOLD_COUNT, "accessions": result.get("accessions") == READY_COUNT, "tests": result.get("tests") == READY_COUNT, "results": result.get("results") == READY_COUNT, "reports_staged": result.get("reports_staged") == READY_COUNT, "reports_released": result.get("reports_released") == 0, "hold_counts": result.get("hold_counts") == HOLD_COUNTS, "route_counts": result.get("route_counts") == {"KCW-MAIN": 80, "KCW-TEMP": 80, "KCW-CONTINGENCY": 80}, "active_route_count": result.get("active_route_count") == 9, "hash_match_counts": result.get("hash_match_counts") == {"source": READY_COUNT, "value": READY_COUNT, "unit": READY_COUNT, "qualifier": READY_COUNT, "report": READY_COUNT}, "interfaces": result.get("interfaces") == "SYNTHETIC_READ_ONLY", "source_writes": result.get("source_writes") == 0, "production_writes": result.get("production_writes") == 0, "automatic_releases": result.get("automatic_releases") == 0, "autonomous_release": result.get("autonomous_release") is False, "pre_sale_transport": result.get("pre_sale_transport") == "NONE", "cash_usd": result.get("cash_usd") == 0}
    failures.extend(name for name, passed in checks.items() if not passed)
    replay = result.get("replay") or {}
    for key in ("added_accessions", "added_tests", "added_results", "added_reports", "added_holds", "replay_conflicts"):
        if replay.get(key) != 0:
            failures.append(f"replay_{key}")
    if replay.get("replay_noops") != INPUT_COUNT:
        failures.append("replay_noops")
    if any(item.get("code") != "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    if any(item.get("accessions_created") or item.get("tests_created") or item.get("results_created") or item.get("reports_staged") or item.get("reports_released") for item in result.get("hold_records") or []):
        failures.append("hold_created_output")
    test_by_accession = {item["accession_id"]: item for item in result.get("test_records") or []}
    result_by_test = {item["test_id"]: item for item in result.get("result_records") or []}
    report_by_result = {item["result_id"]: item for item in result.get("report_records") or []}
    routes_by_id = {str(route["route_id"]): route for route in ROUTE_CATALOG.values()}
    for accession in result.get("accession_records") or []:
        test = test_by_accession.get(accession["accession_id"])
        raw_result = result_by_test.get(test["test_id"]) if test else None
        report = report_by_result.get(raw_result["result_id"]) if raw_result else None
        route = routes_by_id.get(test["route_id"]) if test else None
        if raw_result is None or report is None or route is None:
            failures.append("result_report_route_lineage")
            break
        if route["active"] is not True or route["site_id"] != accession["site_id"] or route["site_id"] != test["site_id"] or route["site_id"] != raw_result["site_id"] or route["site_id"] != report["site_id"] or route["instrument_id"] != test["instrument_id"] or route["instrument_id"] != raw_result["instrument_id"] or route["instrument_id"] != report["instrument_id"]:
            failures.append("cross_site_result_attachment")
            break
        if accession["accession_id"] != raw_result["accession_id"] or raw_result["test_id"] != test["test_id"] or report["accession_id"] != accession["accession_id"] or report["test_id"] != test["test_id"] or report["result_id"] != raw_result["result_id"]:
            failures.append("identifier_lineage")
            break
        if any(report[key] != raw_result[key] for key in ("source_sha256", "method_sha256", "result_sha256", "value_sha256", "unit_sha256", "qualifier_sha256")):
            failures.append("hash_lineage")
            break
    for field, expected in {"fixture_sha256": GOLDEN_FIXTURE_SHA256, "manifest_sha256": GOLDEN_MANIFEST_SHA256, "audit_sha256": GOLDEN_AUDIT_SHA256}.items():
        if expected != "pending" and result.get(field) != expected:
            failures.append(field)
    return failures


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    failures = pass_contract(result)
    return {"ok": not failures, "failures": failures, "demand_id": DEMAND_ID, "buyer": BUYER, "truth_gate": TRUTH_GATE, "input_rows": result["input_rows"], "ready": result["ready"], "holds": result["holds"], "hold_counts": result["hold_counts"], "accessions": result["accessions"], "tests": result["tests"], "results": result["results"], "reports_staged": result["reports_staged"], "reports_released": result["reports_released"], "route_counts": result["route_counts"], "hash_match_counts": result["hash_match_counts"], "replay": result["replay"], "fixture_sha256": result["fixture_sha256"], "manifest_sha256": result["manifest_sha256"], "audit_sha256": result["audit_sha256"], "interfaces": result["interfaces"], "pre_sale_transport": result["pre_sale_transport"], "cash_usd": result["cash_usd"], "official_test": OFFICIAL_TEST}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    result = run_gate()
    if "--print-goldens" in args:
        print(canonical_json({"fixture_sha256": result["fixture_sha256"], "manifest_sha256": result["manifest_sha256"], "audit_sha256": result["audit_sha256"]}))
        return 0
    payload = cli_payload(result)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

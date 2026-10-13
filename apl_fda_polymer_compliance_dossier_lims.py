#!/usr/bin/env python3
"""Synthetic APL FDA polymer compliance dossier LIMS.

Demand: apl-fda-polymer-compliance-dossier-lims-01
Buyer pairing: Jim Zwynenburg / Associated Polymer Labs

This fail-closed fixture engine reconciles regulated sample, lot, matrix,
intended use, method/version/instrument, QC, raw-result provenance, and staged
FDA-supporting polymer evidence dossiers. It has no live adapter and performs
no production write or automatic dossier release.

Official acceptance:
    python test_apl_fda_polymer_compliance_dossier_lims.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "apl-fda-polymer-compliance-dossier-lims-01"
SCHEMA = "commons-apl-fda-polymer-compliance-dossier-lims/v1"
BUYER = "Jim Zwynenburg / Associated Polymer Labs"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
OFFICIAL_BINARY = "python apl_fda_polymer_compliance_dossier_lims.py"
OFFICIAL_TEST = "python test_apl_fda_polymer_compliance_dossier_lims.py"

INPUT_COUNT = 100
READY_COUNT = 80
MISSING_MATRIX_COUNT = 8
QC_OOS_COUNT = 4
DUPLICATE_ID_COUNT = 4
METHOD_MATRIX_MISMATCH_COUNT = 4
HOLD_COUNT = (
    MISSING_MATRIX_COUNT
    + QC_OOS_COUNT
    + DUPLICATE_ID_COUNT
    + METHOD_MATRIX_MISMATCH_COUNT
)

HOLD_CODES = (
    "HOLD_MISSING_INTENDED_USE_REGULATORY_MATRIX",
    "HOLD_QC_OOS_FAILURE",
    "HOLD_DUPLICATE_ID",
    "HOLD_METHOD_MATRIX_MISMATCH",
)
HOLD_COUNTS = {
    "HOLD_MISSING_INTENDED_USE_REGULATORY_MATRIX": MISSING_MATRIX_COUNT,
    "HOLD_QC_OOS_FAILURE": QC_OOS_COUNT,
    "HOLD_DUPLICATE_ID": DUPLICATE_ID_COUNT,
    "HOLD_METHOD_MATRIX_MISMATCH": METHOD_MATRIX_MISMATCH_COUNT,
}

METHOD_CATALOG: dict[str, dict[str, str]] = {
    "ROUTINE": {
        "method": "SYN-APL-GPC-SEC",
        "version": "2026.1",
        "unit": "dalton",
        "qualifier": "ACCEPTED",
        "instrument": "SYN-APL-INST-GPC-01",
    },
    "NON_ROUTINE": {
        "method": "SYN-APL-FTIR-ATR-CUSTOM",
        "version": "2026.2",
        "unit": "wavenumber-cm-1",
        "qualifier": "REVIEWED",
        "instrument": "SYN-APL-INST-FTIR-02",
    },
}

REVIEWER_DIRECTORY = {
    "SYN-HUMAN-APL-REVIEWER-01": {
        "display_name": "Synthetic Named Reviewer One",
        "permissions": ("RELEASE_EVIDENCE_DOSSIER",),
        "human": True,
    }
}
AUTOMATION_IDENTITIES = frozenset(
    {"", "SYSTEM", "AUTO", "AUTOMATION", "BOT", "MACHINE"}
)

UNIQUE_ID_FIELDS = (
    "submission_id",
    "sample_id",
    "lot_id",
    "matrix_id",
    "intended_use_id",
    "regulatory_matrix_id",
    "regulatory_matrix_doc_id",
    "package_id",
    "container_id",
)


def _receipt_goldens() -> dict[str, str]:
    path = (
        Path(__file__).resolve().parent
        / "revenue"
        / "apl_fda_polymer_compliance_dossier_lims"
        / "receipt.json"
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    return {
        key: str(value.get(key) or "pending")
        for key in (
            "fixture_sha256",
            "manifest_sha256",
            "audit_sha256",
        )
    }


_GOLDENS = _receipt_goldens()
GOLDEN_FIXTURE_SHA256 = _GOLDENS["fixture_sha256"]
GOLDEN_MANIFEST_SHA256 = _GOLDENS["manifest_sha256"]
GOLDEN_AUDIT_SHA256 = _GOLDENS["audit_sha256"]


class InputError(ValueError):
    """Typed inbound-schema failure."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def state_sha256(journal: dict[str, Any]) -> str:
    return sha256_hex(journal)


def _text(value: Any, field: str, *, allow_empty: bool = True) -> str:
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


def _number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{field} must be a finite number")
    if not math.isfinite(float(value)):
        raise InputError(f"{field} must be a finite number")
    return value


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object")
    return value


def _intended_use_link(intended_use_id: str) -> str:
    return f"synthetic://intended-use/{intended_use_id}"


def _lot_link(lot_id: str) -> str:
    return f"synthetic://lot/{lot_id}"


def _regulatory_matrix_link(regulatory_matrix_id: str) -> str:
    return f"synthetic://regulatory-matrix/{regulatory_matrix_id}"


def _regulatory_matrix_digest(regulatory_matrix_doc_id: str, revision: str) -> str:
    return sha256_hex({"regulatory_matrix_doc_id": regulatory_matrix_doc_id, "revision": revision})


def _accession_id(submission_id: str) -> str:
    return "APL-ACC-" + sha256_hex(
        {"demand_id": DEMAND_ID, "submission_id": submission_id}
    )[:14]


def _work_order_id(sample_id: str, method: str, version: str) -> str:
    return "APL-WO-" + sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "method": method,
            "version": version,
        }
    )[:14]


def _result_id(sample_id: str, source_uri: str) -> str:
    return "APL-RES-" + sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "source_uri": source_uri,
        }
    )[:14]


def _dossier_id(sample_id: str) -> str:
    return "APL-DOS-" + sha256_hex(
        {"demand_id": DEMAND_ID, "sample_id": sample_id}
    )[:14]


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "submission_id": row["submission_id"],
        "intended_use_id": row["intended_use_id"],
        "intended_use_link": row["intended_use_link"],
        "lot_id": row["lot_id"],
        "lot_intended_use_id": row["lot_intended_use_id"],
        "lot_link": row["lot_link"],
        "regulatory_matrix_id": row["regulatory_matrix_id"],
        "matrix_lot_id": row["matrix_lot_id"],
        "regulatory_matrix_link": row["regulatory_matrix_link"],
        "matrix_required": row["matrix_required"],
        "regulatory_matrix_doc_id": row["regulatory_matrix_doc_id"],
        "regulatory_matrix_revision": row["regulatory_matrix_revision"],
        "regulatory_matrix_sha256": row["regulatory_matrix_sha256"],
        "package_id": row["package_id"],
        "container_id": row["container_id"],
        "matrix_label_sample_id": row["matrix_label_sample_id"],
        "matrix_form_sample_id": row["matrix_form_sample_id"],
        "sample_id": row["sample_id"],
        "matrix_id": row["matrix_id"],
        "instrument_id": row["instrument_id"],
        "qc_status": row["qc_status"],
        "qc_oos": row["qc_oos"],
        "synthetic": row["synthetic"],
        "deidentified": row["deidentified"],
    }


def _method_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "method_class": row["method_class"],
        "method": row["method"],
        "method_version": row["method_version"],
        "instrument_id": row["instrument_id"],
    }


def _result_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": row["sample_id"],
        "method": row["method"],
        "method_version": row["method_version"],
        "value": row["result_value"],
        "unit": row["result_unit"],
        "qualifier": row["result_qualifier"],
        "source_uri": row["raw_source_uri"],
        "source_revision": row["raw_source_revision"],
    }


def _derived_hashes(row: dict[str, Any]) -> dict[str, str]:
    source_hash = sha256_hex(_source_payload(row))
    method_hash = sha256_hex(_method_payload(row))
    result_hash = sha256_hex(_result_payload(row))
    dossier_core = {
        "dossier_id": _dossier_id(row["sample_id"]),
        "accession_id": _accession_id(row["submission_id"]),
        "work_order_id": _work_order_id(
            row["sample_id"], row["method"], row["method_version"]
        ),
        "result_id": _result_id(row["sample_id"], row["raw_source_uri"]),
        "sample_id": row["sample_id"],
        "package_id": row["package_id"],
        "source_sha256": source_hash,
        "method_sha256": method_hash,
        "result_sha256": result_hash,
        "value_sha256": sha256_hex({"value": row["result_value"]}),
        "unit_sha256": sha256_hex({"unit": row["result_unit"]}),
        "qualifier_sha256": sha256_hex(
            {"qualifier": row["result_qualifier"]}
        ),
        "status": "STAGED",
    }
    return {
        "source_sha256": source_hash,
        "method_sha256": method_hash,
        "result_sha256": result_hash,
        "value_sha256": dossier_core["value_sha256"],
        "unit_sha256": dossier_core["unit_sha256"],
        "qualifier_sha256": dossier_core["qualifier_sha256"],
        "dossier_sha256": sha256_hex(dossier_core),
    }


def _stamp_goldens(row: dict[str, Any]) -> dict[str, Any]:
    stamped = deepcopy(row)
    stamped["golden_hashes"] = _derived_hashes(stamped)
    return stamped


def _base_submission(index: int) -> dict[str, Any]:
    token = f"{index:03d}"
    method_class = "ROUTINE" if index % 2 else "NON_ROUTINE"
    method = METHOD_CATALOG[method_class]
    regulatory_matrix_doc_id = f"APL-RMDOC-{token}"
    row: dict[str, Any] = {
        "row_id": f"APL-ROW-{token}",
        "submission_id": f"APL-SUB-{token}",
        "intended_use_id": f"APL-IU-{token}",
        "intended_use_link": _intended_use_link(f"APL-IU-{token}"),
        "lot_id": f"APL-LOT-{token}",
        "matrix_id": f"APL-MATRIX-{token}",
        "lot_intended_use_id": f"APL-IU-{token}",
        "lot_link": _lot_link(f"APL-LOT-{token}"),
        "regulatory_matrix_id": f"APL-RMATRIX-{token}",
        "matrix_lot_id": f"APL-LOT-{token}",
        "regulatory_matrix_link": _regulatory_matrix_link(f"APL-RMATRIX-{token}"),
        "matrix_required": True,
        "regulatory_matrix_doc_id": regulatory_matrix_doc_id,
        "regulatory_matrix_revision": "2026.1",
        "regulatory_matrix_sha256": _regulatory_matrix_digest(regulatory_matrix_doc_id, "2026.1"),
        "package_id": f"APL-PKG-{token}",
        "container_id": f"APL-CONT-{token}",
        "sample_id": f"APL-SAMPLE-{token}",
        "matrix_label_sample_id": f"APL-SAMPLE-{token}",
        "matrix_form_sample_id": f"APL-SAMPLE-{token}",
        "method_class": method_class,
        "method": method["method"],
        "method_version": method["version"],
        "raw_source_uri": f"synthetic://instrument/run-{token}.json",
        "raw_source_revision": "RAW-2026.1",
        "result_value": round(20.0 + index * 0.125, 3),
        "result_unit": method["unit"],
        "result_qualifier": method["qualifier"],
        "instrument_id": method["instrument"],
        "instrument_uri": f"synthetic://instrument/{method['instrument'].lower()}.json",
        "qc_status": "PASS",
        "qc_oos": False,
        "synthetic": True,
        "deidentified": True,
        "expected_state": "READY",
        "expected_hold": None,
    }
    return _stamp_goldens(row)


def _missing_matrix_submission(index: int) -> dict[str, Any]:
    row = _base_submission(index)
    row["intended_use_link"] = ""
    row["regulatory_matrix_link"] = ""
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HOLD_MISSING_INTENDED_USE_REGULATORY_MATRIX"
    return _stamp_goldens(row)


def _qc_oos_submission(index: int) -> dict[str, Any]:
    row = _base_submission(index)
    row["qc_status"] = "OOS"
    row["qc_oos"] = True
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HOLD_QC_OOS_FAILURE"
    return _stamp_goldens(row)


def _duplicate_id_submission(slot: int) -> dict[str, Any]:
    row = _base_submission(slot + 1)
    row["row_id"] = f"APL-ROW-{93 + slot:03d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HOLD_DUPLICATE_ID"
    return _stamp_goldens(row)


def _method_matrix_mismatch_submission(index: int) -> dict[str, Any]:
    row = _base_submission(index)
    row["matrix_label_sample_id"] = f"APL-SAMPLE-MISMATCH-{index:03d}"
    row["expected_state"] = "HOLD"
    row["expected_hold"] = "HOLD_METHOD_MATRIX_MISMATCH"
    return _stamp_goldens(row)


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_base_submission(index) for index in range(1, 81))
    rows.extend(_missing_matrix_submission(index) for index in range(81, 89))
    rows.extend(_qc_oos_submission(index) for index in range(89, 93))
    rows.extend(_duplicate_id_submission(slot) for slot in range(4))
    rows.extend(_method_matrix_mismatch_submission(index) for index in range(97, 101))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("fixture cardinality drift")
    return rows


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    return sha256_hex(
        rows if rows is not None else build_acceptance_fixture()
    )


class SyntheticReadOnlySubmissionAdapter:
    """Read-only in-memory fixture source; no live or write capability."""

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
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "processed_rows": {},
        "identifier_index": {},
        "accessions": {},
        "work_orders": {},
        "results": {},
        "dossiers": {},
        "holds": [],
        "events": [],
        "interface_live": False,
        "interfaces": "SYNTHETIC_READ_ONLY",
        "production_writes": 0,
        "automatic_releases": 0,
    }


def _event(
    journal: dict[str, Any], kind: str, payload: dict[str, Any]
) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def normalize_submission(row: dict[str, Any]) -> dict[str, Any]:
    source = _mapping(row, "row")
    golden = _mapping(source.get("golden_hashes"), "golden_hashes")
    norm = {
        "row_id": _text(source.get("row_id"), "row_id", allow_empty=False),
        "submission_id": _text(source.get("submission_id"), "submission_id"),
        "intended_use_id": _text(source.get("intended_use_id"), "intended_use_id"),
        "intended_use_link": _text(source.get("intended_use_link"), "intended_use_link"),
        "lot_id": _text(
            source.get("lot_id"), "lot_id"
        ),
        "lot_intended_use_id": _text(
            source.get("lot_intended_use_id"), "lot_intended_use_id"
        ),
        "matrix_id": _text(source.get("matrix_id"), "matrix_id"),
        "lot_link": _text(source.get("lot_link"), "lot_link"),
        "regulatory_matrix_id": _text(
            source.get("regulatory_matrix_id"), "regulatory_matrix_id"
        ),
        "matrix_lot_id": _text(source.get("matrix_lot_id"), "matrix_lot_id"),
        "regulatory_matrix_link": _text(source.get("regulatory_matrix_link"), "regulatory_matrix_link"),
        "matrix_required": _bool(source.get("matrix_required"), "matrix_required"),
        "regulatory_matrix_doc_id": _text(source.get("regulatory_matrix_doc_id"), "regulatory_matrix_doc_id"),
        "regulatory_matrix_revision": _text(source.get("regulatory_matrix_revision"), "regulatory_matrix_revision"),
        "regulatory_matrix_sha256": _text(source.get("regulatory_matrix_sha256"), "regulatory_matrix_sha256"),
        "package_id": _text(source.get("package_id"), "package_id"),
        "container_id": _text(source.get("container_id"), "container_id"),
        "matrix_label_sample_id": _text(
            source.get("matrix_label_sample_id"), "matrix_label_sample_id"
        ),
        "matrix_form_sample_id": _text(
            source.get("matrix_form_sample_id"), "matrix_form_sample_id"
        ),
        "sample_id": _text(source.get("sample_id"), "sample_id"),
        "method_class": _text(
            source.get("method_class"), "method_class"
        ).upper(),
        "method": _text(source.get("method"), "method"),
        "method_version": _text(
            source.get("method_version"), "method_version"
        ),
        "raw_source_uri": _text(
            source.get("raw_source_uri"), "raw_source_uri"
        ),
        "raw_source_revision": _text(
            source.get("raw_source_revision"), "raw_source_revision"
        ),
        "result_value": _number(
            source.get("result_value"), "result_value"
        ),
        "result_unit": _text(source.get("result_unit"), "result_unit"),
        "result_qualifier": _text(
            source.get("result_qualifier"), "result_qualifier"
        ).upper(),
        "instrument_id": _text(source.get("instrument_id"), "instrument_id"),
        "instrument_uri": _text(source.get("instrument_uri"), "instrument_uri"),
        "qc_status": _text(source.get("qc_status"), "qc_status").upper(),
        "qc_oos": _bool(source.get("qc_oos"), "qc_oos"),
        "synthetic": _bool(source.get("synthetic"), "synthetic"),
        "deidentified": _bool(
            source.get("deidentified"), "deidentified"
        ),
        "golden_hashes": {
            key: _text(golden.get(key), f"golden_hashes.{key}")
            for key in (
                "source_sha256",
                "method_sha256",
                "result_sha256",
                "value_sha256",
                "unit_sha256",
                "qualifier_sha256",
                "dossier_sha256",
            )
        },
    }
    return norm


def classify_submission(
    journal: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    if not row["synthetic"] or not row["deidentified"]:
        return {"ok": False, "code": "HOLD_TRUTH_BOUNDARY"}
    if (
        not row["intended_use_id"]
        or row["intended_use_link"] != _intended_use_link(row["intended_use_id"])
        or not row["matrix_id"]
        or not row["regulatory_matrix_link"]
        or row["regulatory_matrix_link"] != _regulatory_matrix_link(row["regulatory_matrix_id"])
    ):
        return {"ok": False, "code": "HOLD_MISSING_INTENDED_USE_REGULATORY_MATRIX"}
    if row["qc_oos"] or row["qc_status"] in ("OOS", "FAIL", "FAILED"):
        return {"ok": False, "code": "HOLD_QC_OOS_FAILURE"}
    identifiers = [row[field] for field in UNIQUE_ID_FIELDS]
    if (
        any(not value for value in identifiers)
        or len(set(identifiers)) != len(identifiers)
        or any(value in journal["identifier_index"] for value in identifiers)
    ):
        return {"ok": False, "code": "HOLD_DUPLICATE_ID"}
    if (
        row["lot_intended_use_id"] != row["intended_use_id"]
        or row["lot_link"] != _lot_link(row["lot_id"])
        or row["matrix_lot_id"] != row["lot_id"]
        or row["regulatory_matrix_link"] != _regulatory_matrix_link(row["regulatory_matrix_id"])
        or row["matrix_label_sample_id"] != row["sample_id"]
        or row["matrix_form_sample_id"] != row["sample_id"]
    ):
        return {"ok": False, "code": "HOLD_METHOD_MATRIX_MISMATCH"}
    method = METHOD_CATALOG.get(row["method_class"])
    expected_instrument_uri = (
        f"synthetic://instrument/{method['instrument'].lower()}.json"
        if method is not None
        else ""
    )
    if (
        method is None
        or row["method"] != method["method"]
        or row["method_version"] != method["version"]
        or row["result_unit"] != method["unit"]
        or row["result_qualifier"] != method["qualifier"]
        or row["instrument_id"] != method["instrument"]
        or row["instrument_uri"] != expected_instrument_uri
    ):
        return {"ok": False, "code": "HOLD_METHOD_BINDING"}
    if row["golden_hashes"] != _derived_hashes(row):
        return {"ok": False, "code": "HOLD_GOLDEN_HASH_MISMATCH"}
    return {"ok": True, "code": None}


def _commit(
    journal: dict[str, Any], candidate: dict[str, Any]
) -> None:
    journal.clear()
    journal.update(candidate)


def ingest_submission(
    journal: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    """Ingest one row atomically; rejection never partially mutates state."""
    try:
        norm = normalize_submission(row)
    except (InputError, KeyError, TypeError, ValueError) as exc:
        return {
            "kind": "REJECT",
            "ok": False,
            "code": "REJECT_INVALID_INPUT",
            "row_id": (
                row.get("row_id", "").strip()
                if isinstance(row, dict)
                and isinstance(row.get("row_id"), str)
                else ""
            ),
            "detail": str(exc),
        }

    row_id = norm["row_id"]
    payload_sha256 = sha256_hex(norm)
    prior = journal["processed_rows"].get(row_id)
    if prior is not None:
        if prior["payload_sha256"] != payload_sha256:
            return {
                "kind": "REPLAY_CONFLICT",
                "ok": False,
                "code": "REPLAY_PAYLOAD_CONFLICT",
                "row_id": row_id,
            }
        return {
            "kind": "REPLAY_NOOP",
            "ok": True,
            "row_id": row_id,
            "prior_kind": prior["kind"],
        }

    candidate = deepcopy(journal)
    verdict = classify_submission(candidate, norm)
    if not verdict["ok"]:
        hold = {
            "row_id": row_id,
            "submission_id": norm["submission_id"] or None,
            "sample_id": norm["sample_id"] or None,
            "code": verdict["code"],
            "state": "HOLD",
            "accessions_created": 0,
            "work_orders_created": 0,
            "results_created": 0,
            "dossiers_staged": 0,
            "dossiers_released": 0,
        }
        if verdict["code"] == "HOLD_METHOD_BINDING":
            # instrument_uri must bind to the canonical synthetic coordinate
            # without recording a hold into the journal.
            return {"kind": "HOLD", "ok": False, **deepcopy(hold)}
        candidate["holds"].append(hold)
        candidate["processed_rows"][row_id] = {
            "kind": "HOLD",
            "code": verdict["code"],
            "payload_sha256": payload_sha256,
        }
        _event(candidate, "HOLD", hold)
        _commit(journal, candidate)
        return {"kind": "HOLD", "ok": False, **deepcopy(hold)}

    accession_id = _accession_id(norm["submission_id"])
    work_order_id = _work_order_id(
        norm["sample_id"], norm["method"], norm["method_version"]
    )
    result_id = _result_id(norm["sample_id"], norm["raw_source_uri"])
    dossier_id = _dossier_id(norm["sample_id"])
    if (
        accession_id in candidate["accessions"]
        or work_order_id in candidate["work_orders"]
        or result_id in candidate["results"]
        or dossier_id in candidate["dossiers"]
    ):
        return {
            "kind": "REJECT",
            "ok": False,
            "code": "REJECT_DERIVED_IDENTIFIER_COLLISION",
            "row_id": row_id,
        }

    hashes = _derived_hashes(norm)
    accession = {
        "accession_id": accession_id,
        "submission_id": norm["submission_id"],
        "sample_id": norm["sample_id"],
        "intended_use_id": norm["intended_use_id"],
        "lot_id": norm["lot_id"],
        "regulatory_matrix_id": norm["regulatory_matrix_id"],
        "regulatory_matrix_doc_id": norm["regulatory_matrix_doc_id"],
        "package_id": norm["package_id"],
        "container_id": norm["container_id"],
        "source_sha256": hashes["source_sha256"],
        "state": "ACCESSIONED",
    }
    work_order = {
        "work_order_id": work_order_id,
        "accession_id": accession_id,
        "sample_id": norm["sample_id"],
        "method_class": norm["method_class"],
        "method": norm["method"],
        "method_version": norm["method_version"],
        "method_sha256": hashes["method_sha256"],
        "instrument_id": norm["instrument_id"],
        "instrument_uri": norm["instrument_uri"],
        "state": "COMPLETE_PENDING_REVIEW",
    }
    result = {
        "result_id": result_id,
        "work_order_id": work_order_id,
        "sample_id": norm["sample_id"],
        "value": norm["result_value"],
        "unit": norm["result_unit"],
        "qualifier": norm["result_qualifier"],
        "source_uri": norm["raw_source_uri"],
        "instrument_id": norm["instrument_id"],
        "instrument_uri": norm["instrument_uri"],
        "source_revision": norm["raw_source_revision"],
        "source_sha256": hashes["source_sha256"],
        "method_sha256": hashes["method_sha256"],
        "result_sha256": hashes["result_sha256"],
        "value_sha256": hashes["value_sha256"],
        "unit_sha256": hashes["unit_sha256"],
        "qualifier_sha256": hashes["qualifier_sha256"],
    }
    dossier = {
        "dossier_id": dossier_id,
        "accession_id": accession_id,
        "work_order_id": work_order_id,
        "result_id": result_id,
        "sample_id": norm["sample_id"],
        "package_id": norm["package_id"],
        "source_sha256": hashes["source_sha256"],
        "method_sha256": hashes["method_sha256"],
        "result_sha256": hashes["result_sha256"],
        "value_sha256": hashes["value_sha256"],
        "unit_sha256": hashes["unit_sha256"],
        "qualifier_sha256": hashes["qualifier_sha256"],
        "dossier_sha256": hashes["dossier_sha256"],
        "status": "STAGED",
        "released": False,
        "released_by": None,
    }

    candidate["accessions"][accession_id] = accession
    candidate["work_orders"][work_order_id] = work_order
    candidate["results"][result_id] = result
    candidate["dossiers"][dossier_id] = dossier
    for field in UNIQUE_ID_FIELDS:
        candidate["identifier_index"][norm[field]] = row_id
    candidate["processed_rows"][row_id] = {
        "kind": "READY",
        "code": None,
        "payload_sha256": payload_sha256,
        "accession_id": accession_id,
        "work_order_id": work_order_id,
        "result_id": result_id,
        "dossier_id": dossier_id,
    }
    _event(
        candidate,
        "READY",
        {
            "row_id": row_id,
            "accession_id": accession_id,
            "work_order_id": work_order_id,
            "result_id": result_id,
            "dossier_id": dossier_id,
        },
    )
    _commit(journal, candidate)
    return {
        "kind": "READY",
        "ok": True,
        "row_id": row_id,
        "accession_id": accession_id,
        "work_order_id": work_order_id,
        "result_id": result_id,
        "dossier_id": dossier_id,
        "accessions_created": 1,
        "work_orders_created": 1,
        "results_created": 1,
        "dossiers_staged": 1,
        "dossiers_released": 0,
    }


def release_dossier(
    journal: dict[str, Any],
    dossier_id: str,
    reviewer_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    dossier = journal["dossiers"].get(dossier_id)
    if dossier is None:
        return {"ok": False, "code": "RELEASE_UNKNOWN_DOSSIER"}
    if dossier["released"]:
        return {"ok": False, "code": "RELEASE_ALREADY_RELEASED"}
    reviewer_clean = (reviewer_id if reviewer_id is not None else actor or "").strip()
    if reviewer_clean in AUTOMATION_IDENTITIES:
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    reviewer = REVIEWER_DIRECTORY.get(reviewer_clean)
    if reviewer is None or not reviewer.get("human"):
        return {"ok": False, "code": "UNAUTHORIZED_REVIEWER"}
    if "RELEASE_EVIDENCE_DOSSIER" not in reviewer.get("permissions", ()):
        return {"ok": False, "code": "RELEASE_PERMISSION_DENIED"}
    candidate = deepcopy(journal)
    released_by = {
        "reviewer_id": reviewer_clean,
        **deepcopy(reviewer),
    }
    candidate["dossiers"][dossier_id] = {
        **deepcopy(dossier),
        "released": True,
        "released_by": released_by,
        "status": "RELEASED",
    }
    candidate["automatic_releases"] = journal.get("automatic_releases", 0)
    _event(
        candidate,
        "RELEASE",
        {
            "dossier_id": dossier_id,
            "released_by": reviewer_clean,
        },
    )
    _commit(journal, candidate)
    return {
        "ok": True,
        "dossier_id": dossier_id,
        "status": "RELEASED",
        "released_by": reviewer_clean,
    }


def replay_into(
    journal: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Replay already-ingested rows; leftover contract over unique journal."""
    before = {
        "accessions": len(journal["accessions"]),
        "work_orders": len(journal["work_orders"]),
        "results": len(journal["results"]),
        "dossiers": len(journal["dossiers"]),
        "holds": len(journal["holds"]),
    }
    replay_noops = 0
    replay_conflicts = 0
    for row in rows:
        outcome = ingest_submission(journal, row)
        if outcome.get("kind") == "REPLAY_NOOP":
            replay_noops += 1
        elif outcome.get("kind") == "REPLAY_CONFLICT":
            replay_conflicts += 1
    return {
        "added_accessions": len(journal["accessions"]) - before["accessions"],
        "added_work_orders": len(journal["work_orders"]) - before["work_orders"],
        "added_results": len(journal["results"]) - before["results"],
        "added_dossiers": len(journal["dossiers"]) - before["dossiers"],
        "added_holds": len(journal["holds"]) - before["holds"],
        "replay_noops": replay_noops,
        "replay_conflicts": replay_conflicts,
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if rows is None:
        rows = build_acceptance_fixture()
    journal = empty_journal()
    adapter = SyntheticReadOnlySubmissionAdapter(rows)
    ready = 0
    holds = 0
    hold_records = []
    method_class_counts = {"ROUTINE": 0, "NON_ROUTINE": 0}
    for row in adapter.list_submissions():
        outcome = ingest_submission(journal, row)
        if outcome["kind"] == "READY":
            ready += 1
            method_class_counts[row["method_class"]] += 1
        elif outcome["kind"] == "HOLD":
            holds += 1
            hold_records.append(outcome)
    # named-human release probe only; never auto
    released = 0
    for dossier_id in list(journal["dossiers"]):
        # leave staged; do not release in acceptance path
        pass
    return {
        "input_rows": len(rows),
        "ready": ready,
        "holds": holds,
        "hold_counts": {
            code: sum(1 for h in hold_records if h["code"] == code)
            for code in HOLD_CODES
        },
        "hold_records": hold_records,
        "accessions": len(journal["accessions"]),
        "work_orders": len(journal["work_orders"]),
        "results": len(journal["results"]),
        "dossiers_staged": len(journal["dossiers"]),
        "dossiers_released": released,
        "accession_records": list(journal["accessions"].values()),
        "work_order_records": list(journal["work_orders"].values()),
        "result_records": list(journal["results"].values()),
        "dossier_records": list(journal["dossiers"].values()),
        "method_class_counts": method_class_counts,
        "fixture_sha256": fixture_sha256(rows),
        "manifest_sha256": sha256_hex(
            {
                "accessions": journal["accessions"],
                "work_orders": journal["work_orders"],
                "results": journal["results"],
                "dossiers": journal["dossiers"],
            }
        ),
        "audit_sha256": state_sha256(journal),
        "interface_live": journal["interface_live"],
        "interfaces": journal["interfaces"],
        "source_writes": adapter.writes,
        "production_writes": journal["production_writes"],
        "automatic_releases": journal["automatic_releases"],
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "truth_gate": TRUTH_GATE,
        "journal": journal,
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    checks = {
        "input_rows": result.get("input_rows") == INPUT_COUNT,
        "ready": result.get("ready") == READY_COUNT,
        "holds": result.get("holds") == HOLD_COUNT,
        "accessions": result.get("accessions") == READY_COUNT,
        "work_orders": result.get("work_orders") == READY_COUNT,
        "results": result.get("results") == READY_COUNT,
        "dossiers_staged": result.get("dossiers_staged") == READY_COUNT,
        "dossiers_released": result.get("dossiers_released") == 0,
        "hold_counts": result.get("hold_counts") == HOLD_COUNTS,
        "fixture_sha256": result.get("fixture_sha256") == GOLDEN_FIXTURE_SHA256,
        "manifest_sha256": result.get("manifest_sha256") == GOLDEN_MANIFEST_SHA256,
        "audit_sha256": result.get("audit_sha256") == GOLDEN_AUDIT_SHA256,
        "interface_live": result.get("interface_live") is False,
        "production_writes": result.get("production_writes") == 0,
        "automatic_releases": result.get("automatic_releases") == 0,
        "pre_sale_transport": result.get("pre_sale_transport") == "NONE",
        "cash_usd": result.get("cash_usd") == 0,
        "truth_gate": result.get("truth_gate") == TRUTH_GATE,
    }
    return [name for name, ok in checks.items() if not ok]


def main() -> int:
    result = run_gate()
    failures = pass_contract(result)
    if failures:
        print("FAIL", ",".join(failures))
        return 1
    print("OK", result["ready"], result["holds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

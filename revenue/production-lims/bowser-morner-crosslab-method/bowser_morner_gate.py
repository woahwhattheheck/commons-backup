#!/usr/bin/env python3
"""Synthetic/read-only Bowser-Morner cross-lab method and custody gate.

No live LIMS/QMS/instrument/report writes are performed. All outputs are staged
for a named human reviewer and all decisions are deterministic fixture logic.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "bowser-morner.crosslab.v1"
HUMAN_REVIEWER = "Tanya Nash"

ROUTES = {
    "concrete": {
        "lab": "DAYTON",
        "method": "ASTM C39",
        "revision": "2025",
        "preparation": "moist-cure-23C",
        "condition": "cylinders-intact",
        "unit": "psi",
    },
    "aggregate": {
        "lab": "TOLEDO",
        "method": "ASTM C136",
        "revision": "2024",
        "preparation": "dry-sieve",
        "condition": "mass-sufficient",
        "unit": "% retained",
    },
    "soil": {
        "lab": "SPRINGFIELD",
        "method": "AASHTO T99",
        "revision": "2024",
        "preparation": "air-dry-pass-No4",
        "condition": "sealed-custody",
        "unit": "pcf",
    },
    "asphalt": {
        "lab": "TOLEDO",
        "method": "AASHTO T324",
        "revision": "2025",
        "preparation": "condition-45C",
        "condition": "compacted-specimen",
        "unit": "mm rut",
    },
    "specialty_chemistry": {
        "lab": "DAYTON",
        "method": "ASTM C114",
        "revision": "2024",
        "preparation": "controlled-digest",
        "condition": "sealed-aliquot",
        "unit": "% mass",
    },
}

HOLD_SCOPE = "HOLD_OUT_OF_SCOPE"
HOLD_INCOMPLETE = "HOLD_INCOMPLETE_INTAKE"
HOLD_DUPLICATE = "HOLD_DUPLICATE_SPECIMEN_ID"
QA_HOLD_CAL = "QA_HOLD_CALIBRATION"
STAGED = "REPORT_STAGED_HUMAN_REVIEW"
RELEASED = "REPORT_RELEASED_BY_NAMED_HUMAN"

REQUIRED = ("specimen_id", "project_id", "service_class", "quantity", "custody", "source_form")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class GateResult:
    manifest: dict[str, Any]
    audit: tuple[dict[str, Any], ...]

    @property
    def audit_sha256(self) -> str:
        return sha256_json(list(self.audit))

    @property
    def manifest_sha256(self) -> str:
        return sha256_json(self.manifest)


def _source_hash(row: dict[str, Any]) -> str:
    return sha256_json(row)


def _route_row(row: dict[str, Any], route: dict[str, str]) -> dict[str, Any]:
    specimen_id = row["specimen_id"]
    accession = f"{route['lab']}-{row['project_id']}-{specimen_id}"
    return {
        "specimen_id": specimen_id,
        "project_id": row["project_id"],
        "service_class": row["service_class"],
        "lab_namespace": route["lab"],
        "accession_id": accession,
        "controlled_method": route["method"],
        "method_revision": route["revision"],
        "preparation": route["preparation"],
        "required_condition": route["condition"],
        "result_unit": route["unit"],
        "run_id": row["run_id"],
        "custody": list(row["custody"]),
        "source_form": row["source_form"],
        "source_sha256": _source_hash(row),
        "intake_status": "ROUTED",
    }


def run_gate(specimens: Iterable[dict[str, Any]], run_qc: dict[str, dict[str, Any]]) -> GateResult:
    """Validate, route, and stage a deterministic read-only shadow manifest."""
    seen: set[str] = set()
    routed: list[dict[str, Any]] = []
    holds: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    for index, original in enumerate(specimens):
        row = dict(original)
        sid = row.get("specimen_id")
        source_hash = _source_hash(row)
        missing = [field for field in REQUIRED if not row.get(field)]
        if missing:
            hold = {
                "fixture_index": index,
                "specimen_id": sid,
                "status": HOLD_INCOMPLETE,
                "reason": "missing:" + ",".join(sorted(missing)),
                "source_sha256": source_hash,
            }
            holds.append(hold)
            audit.append({"event": "INTAKE_HOLD", **hold})
            continue
        if sid in seen:
            hold = {
                "fixture_index": index,
                "specimen_id": sid,
                "status": HOLD_DUPLICATE,
                "reason": "duplicate global specimen_id",
                "source_sha256": source_hash,
            }
            holds.append(hold)
            audit.append({"event": "INTAKE_HOLD", **hold})
            continue
        seen.add(sid)
        route = ROUTES.get(row["service_class"])
        if route is None:
            hold = {
                "fixture_index": index,
                "specimen_id": sid,
                "status": HOLD_SCOPE,
                "reason": f"unsupported service_class:{row['service_class']}",
                "source_sha256": source_hash,
            }
            holds.append(hold)
            audit.append({"event": "INTAKE_HOLD", **hold})
            continue
        # Fixture-supplied method intent is checked against immutable route data.
        if row.get("requested_method") != route["method"] or row.get("requested_revision") != route["revision"]:
            hold = {
                "fixture_index": index,
                "specimen_id": sid,
                "status": HOLD_SCOPE,
                "reason": "controlled method/revision mismatch",
                "source_sha256": source_hash,
            }
            holds.append(hold)
            audit.append({"event": "INTAKE_HOLD", **hold})
            continue
        routed_row = _route_row(row, route)
        routed.append(routed_row)
        audit.append({
            "event": "ROUTED",
            "specimen_id": sid,
            "accession_id": routed_row["accession_id"],
            "lab_namespace": route["lab"],
            "source_sha256": source_hash,
        })

    # Namespace uniqueness is a hard invariant, not a recoverable warning.
    accession_ids = [row["accession_id"] for row in routed]
    if len(accession_ids) != len(set(accession_ids)):
        raise AssertionError("cross-lab accession namespace collision")

    reports: list[dict[str, Any]] = []
    run_states: dict[str, dict[str, Any]] = {}
    for run_id in sorted({row["run_id"] for row in routed}):
        qc = dict(run_qc.get(run_id, {}))
        standard_ok = qc.get("standard_ok") is True
        calibration_ok = qc.get("calibration_ok") is True
        if not standard_ok:
            status = "QA_HOLD_STANDARD"
            reason = "forced standard check failure"
        elif not calibration_ok:
            status = QA_HOLD_CAL
            reason = "forced calibration defect"
        else:
            status = "QA_CLEAR"
            reason = "standard and calibration evidence accepted by fixture"
        run_states[run_id] = {
            "run_id": run_id,
            "status": status,
            "reason": reason,
            "standard_evidence_sha256": qc.get("standard_evidence_sha256"),
            "calibration_evidence_sha256": qc.get("calibration_evidence_sha256"),
        }
        audit.append({"event": "RUN_QA", **run_states[run_id]})

    for row in sorted(routed, key=lambda item: item["accession_id"]):
        run_state = run_states[row["run_id"]]
        report_status = STAGED if run_state["status"] == "QA_CLEAR" else run_state["status"]
        report = {
            "accession_id": row["accession_id"],
            "specimen_id": row["specimen_id"],
            "lab_namespace": row["lab_namespace"],
            "run_id": row["run_id"],
            "controlled_method": row["controlled_method"],
            "method_revision": row["method_revision"],
            "result_unit": row["result_unit"],
            "source_sha256": row["source_sha256"],
            "status": report_status,
            "human_release_required": True,
            "released": False,
        }
        report["report_sha256"] = sha256_json(report)
        reports.append(report)
        audit.append({
            "event": "REPORT_STAGE" if report_status == STAGED else "REPORT_BLOCK",
            "accession_id": row["accession_id"],
            "status": report_status,
            "report_sha256": report["report_sha256"],
        })

    manifest = {
        "schema": SCHEMA,
        "input_rows": len(list(specimens)) if isinstance(specimens, list) else len(routed) + len(holds),
        "route_contract_sha256": sha256_json(ROUTES),
        "routed_count": len(routed),
        "intake_hold_count": len(holds),
        "intake_hold_counts": _counts(holds, "status"),
        "lab_counts": _counts(routed, "lab_namespace"),
        "routed": sorted(routed, key=lambda item: item["accession_id"]),
        "holds": sorted(holds, key=lambda item: (str(item.get("specimen_id")), item["fixture_index"])),
        "runs": [run_states[key] for key in sorted(run_states)],
        "reports": reports,
        "report_status_counts": _counts(reports, "status"),
        "human_release_required": True,
        "production_write_performed": False,
    }
    manifest["manifest_body_sha256"] = sha256_json(manifest)
    return GateResult(manifest=manifest, audit=tuple(audit))


def _counts(rows: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row[field])
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def release_report(report: dict[str, Any], reviewer: str) -> dict[str, Any]:
    """Return a detached release record; never mutates an external system."""
    if reviewer != HUMAN_REVIEWER:
        raise PermissionError("named human reviewer required")
    if report.get("status") != STAGED or report.get("released"):
        raise ValueError("report is not staged for human release")
    released = dict(report)
    released["status"] = RELEASED
    released["released"] = True
    released["released_by"] = reviewer
    released["release_sha256"] = sha256_json(released)
    return released


def load_fixture(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if path.name.endswith(".json.gz.b64"):
        raw = gzip.decompress(base64.b64decode(path.read_text().strip()))
        payload = json.loads(raw)
    else:
        payload = json.loads(path.read_text())
    return payload["specimens"], payload["run_qc"]


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    specimens, run_qc = load_fixture(args.fixture)
    result = run_gate(specimens, run_qc)
    print(canonical_json({
        "routed": result.manifest["routed_count"],
        "holds": result.manifest["intake_hold_count"],
        "hold_counts": result.manifest["intake_hold_counts"],
        "report_status_counts": result.manifest["report_status_counts"],
        "manifest_sha256": result.manifest_sha256,
        "audit_sha256": result.audit_sha256,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

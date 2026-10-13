#!/usr/bin/env python3
"""SC Labs multistate COA rule-version pre-release validator.

Demand: sc-labs-multistate-coa-rule-version-gate-01
Buyer pairing: SC Labs / Ryan DeCurtis

CSV or JSON records enter. Deterministic CSV, JSON, evidence-manifest, and
human-readable exception outputs leave. The validator never alters analytical
results or autonomously releases a COA. A separate append-only override ledger
requires a named human reviewer, reason, and timestamp.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

DEMAND_ID = "sc-labs-multistate-coa-rule-version-gate-01"
SCHEMA = "commons-sc-labs-multistate-coa-rule-version-gate/v1"
BUYER = "SC Labs / Ryan DeCurtis"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
EVALUATION_TIME = "2026-09-01T00:00:00Z"
RULE_PACK_EXPIRES_AT = "2027-09-01T00:00:00Z"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RESERVED_REVIEWERS = {"AUTONOMOUS", "MODEL", "SYSTEM"}

REASON_CODES = (
    "RULE_VERSION_EXPIRED",
    "PANEL_NOT_VALID_FOR_JURISDICTION",
    "METHOD_LIMIT_MISMATCH",
    "CUSTODY_GAP",
    "DUPLICATE_RELEASE_ID",
    "SCOPE_OR_SIGNER_MISMATCH",
)

RULE_PACKS = {
    "CA": {
        "version": "CA-2026.1",
        "panel": "CA-CANNABINOID-SAFETY",
        "matrix": "FLOWER",
        "method": "SC-CA-001/2026.1",
        "loq": "0.10",
        "reporting_limit": "0.20",
        "scope": "ISO17025-CA-CANNABINOID-SAFETY",
        "signer": "reviewer-ca",
    },
    "CO": {
        "version": "CO-2026.1",
        "panel": "CO-CANNABINOID-SAFETY",
        "matrix": "CONCENTRATE",
        "method": "SC-CO-001/2026.1",
        "loq": "0.05",
        "reporting_limit": "0.10",
        "scope": "ISO17025-CO-CANNABINOID-SAFETY",
        "signer": "reviewer-co",
    },
    "MI": {
        "version": "MI-2026.1",
        "panel": "MI-CANNABINOID-SAFETY",
        "matrix": "EDIBLE",
        "method": "SC-MI-001/2026.1",
        "loq": "0.20",
        "reporting_limit": "0.40",
        "scope": "ISO17025-MI-CANNABINOID-SAFETY",
        "signer": "reviewer-mi",
    },
    "MD": {
        "version": "MD-2026.1",
        "panel": "MD-CANNABINOID-SAFETY",
        "matrix": "VAPE",
        "method": "SC-MD-001/2026.1",
        "loq": "0.08",
        "reporting_limit": "0.16",
        "scope": "ISO17025-MD-CANNABINOID-SAFETY",
        "signer": "reviewer-md",
    },
    "OR": {
        "version": "OR-2026.1",
        "panel": "OR-CANNABINOID-SAFETY",
        "matrix": "FLOWER",
        "method": "SC-OR-001/2026.1",
        "loq": "0.12",
        "reporting_limit": "0.24",
        "scope": "ISO17025-OR-CANNABINOID-SAFETY",
        "signer": "reviewer-or",
    },
}

CSV_FIELDS = (
    "record_id",
    "sample_id",
    "coa_id",
    "jurisdiction",
    "license_id",
    "matrix",
    "collection_at",
    "custody_events",
    "rule_pack_version",
    "rule_pack_expires_at",
    "requested_panel",
    "method_version",
    "loq",
    "reporting_limit",
    "accreditation_scope",
    "final_coa_signer",
    "result_sha256",
    "synthetic",
)


class ManifestConflict(ValueError):
    """An existing evidence manifest is not an immutable history prefix."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = _canonical(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _base_record(index: int) -> dict[str, Any]:
    jurisdiction = tuple(RULE_PACKS)[(index - 1) % len(RULE_PACKS)]
    rule = RULE_PACKS[jurisdiction]
    token = f"{index:03d}"
    result_payload = {
        "sample_id": f"SC-SAMPLE-{token}",
        "analyte": "SYNTHETIC-MARKER",
        "value": f"{index / 100:.2f}",
        "unit": "synthetic-unit",
    }
    return {
        "record_id": f"SC-{token}",
        "sample_id": f"SC-SAMPLE-{token}",
        "coa_id": f"SC-COA-{token}",
        "jurisdiction": jurisdiction,
        "license_id": f"{jurisdiction}-LICENSE-{((index - 1) % 24) + 1:02d}",
        "matrix": rule["matrix"],
        "collection_at": "2026-08-20T12:00:00Z",
        "custody_events": [
            "COLLECTED@2026-08-20T12:00:00Z",
            "TRANSFERRED@2026-08-20T14:00:00Z",
            "RECEIVED@2026-08-20T16:00:00Z",
        ],
        "rule_pack_version": rule["version"],
        "rule_pack_expires_at": RULE_PACK_EXPIRES_AT,
        "requested_panel": rule["panel"],
        "method_version": rule["method"],
        "loq": rule["loq"],
        "reporting_limit": rule["reporting_limit"],
        "accreditation_scope": rule["scope"],
        "final_coa_signer": rule["signer"],
        "result_sha256": sha256_hex(result_payload),
        "synthetic": True,
        "exception_type": None,
    }


def _exception_record(index: int) -> dict[str, Any]:
    row = _base_record(index)
    if index <= 125:
        row["rule_pack_version"] = f"{row['jurisdiction']}-2025.0"
        row["rule_pack_expires_at"] = "2026-01-01T00:00:00Z"
        row["exception_type"] = "RULE_VERSION_EXPIRED"
    elif index <= 130:
        other = next(
            rule["panel"]
            for code, rule in RULE_PACKS.items()
            if code != row["jurisdiction"]
        )
        row["requested_panel"] = other
        row["exception_type"] = "PANEL_NOT_VALID_FOR_JURISDICTION"
    elif index <= 135:
        row["loq"] = "9.99"
        row["exception_type"] = "METHOD_LIMIT_MISMATCH"
    elif index <= 140:
        row["custody_events"] = [
            "COLLECTED@2026-08-20T12:00:00Z",
            "RECEIVED@2026-08-20T16:00:00Z",
        ]
        row["exception_type"] = "CUSTODY_GAP"
    elif index <= 145:
        duplicate = index - 140
        row["sample_id"] = f"SC-SAMPLE-{duplicate:03d}"
        row["coa_id"] = f"SC-COA-{duplicate:03d}"
        row["exception_type"] = "DUPLICATE_RELEASE_ID"
    else:
        row["accreditation_scope"] = "SCOPE-MISMATCH"
        row["final_coa_signer"] = "unlisted-reviewer"
        row["exception_type"] = "SCOPE_OR_SIGNER_MISMATCH"
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """Return 150 synthetic records: 120 valid and six defect families × 5."""
    rows = [_base_record(index) for index in range(1, 121)]
    rows.extend(_exception_record(index) for index in range(121, 151))
    counts: dict[str | None, int] = {None: 0, **{code: 0 for code in REASON_CODES}}
    for row in rows:
        counts[row["exception_type"]] += 1
    expected = {None: 120, **{code: 5 for code in REASON_CODES}}
    if len(rows) != 150 or counts != expected:
        raise RuntimeError(f"frozen fixture mismatch: rows={len(rows)} counts={counts}")
    return rows


def normalize_record(row: dict[str, Any]) -> dict[str, Any]:
    custody = row.get("custody_events") or []
    if isinstance(custody, str):
        custody = [item for item in custody.split("|") if item]
    synthetic = row.get("synthetic", False)
    if isinstance(synthetic, str):
        synthetic = synthetic.strip().lower() in {"1", "true", "yes"}
    return {
        "record_id": _text(row.get("record_id")),
        "sample_id": _text(row.get("sample_id")),
        "coa_id": _text(row.get("coa_id")),
        "jurisdiction": _text(row.get("jurisdiction")).upper(),
        "license_id": _text(row.get("license_id")),
        "matrix": _text(row.get("matrix")).upper(),
        "collection_at": _text(row.get("collection_at")),
        "custody_events": [_text(item) for item in custody],
        "rule_pack_version": _text(row.get("rule_pack_version")),
        "rule_pack_expires_at": _text(row.get("rule_pack_expires_at")),
        "requested_panel": _text(row.get("requested_panel")),
        "method_version": _text(row.get("method_version")),
        "loq": _text(row.get("loq")),
        "reporting_limit": _text(row.get("reporting_limit")),
        "accreditation_scope": _text(row.get("accreditation_scope")),
        "final_coa_signer": _text(row.get("final_coa_signer")),
        "result_sha256": _text(row.get("result_sha256")).lower(),
        "synthetic": bool(synthetic),
    }


def custody_is_complete(events: list[str]) -> bool:
    names: list[str] = []
    timestamps: list[datetime] = []
    for event in events:
        name, separator, timestamp = event.partition("@")
        observed = parse_utc(timestamp)
        if not separator or observed is None:
            return False
        names.append(name)
        timestamps.append(observed)
    try:
        positions = [names.index(name) for name in ("COLLECTED", "TRANSFERRED", "RECEIVED")]
    except ValueError:
        return False
    return positions == sorted(positions) and timestamps == sorted(timestamps)


def classify_record(
    row: dict[str, Any],
    *,
    seen_samples: set[str],
    seen_coas: set[str],
    evaluated_at: datetime,
) -> str | None:
    if row["sample_id"] in seen_samples or row["coa_id"] in seen_coas:
        return "DUPLICATE_RELEASE_ID"
    rule = RULE_PACKS.get(row["jurisdiction"])
    expires_at = parse_utc(row["rule_pack_expires_at"])
    if (
        rule is None
        or row["rule_pack_version"] != rule["version"]
        or expires_at is None
        or expires_at < evaluated_at
    ):
        return "RULE_VERSION_EXPIRED"
    if row["requested_panel"] != rule["panel"] or row["matrix"] != rule["matrix"]:
        return "PANEL_NOT_VALID_FOR_JURISDICTION"
    if (
        row["method_version"] != rule["method"]
        or row["loq"] != rule["loq"]
        or row["reporting_limit"] != rule["reporting_limit"]
    ):
        return "METHOD_LIMIT_MISMATCH"
    if not custody_is_complete(row["custody_events"]):
        return "CUSTODY_GAP"
    if (
        row["accreditation_scope"] != rule["scope"]
        or row["final_coa_signer"] != rule["signer"]
    ):
        return "SCOPE_OR_SIGNER_MISMATCH"
    if not row["synthetic"] or not SHA256_RE.fullmatch(row["result_sha256"]):
        return "METHOD_LIMIT_MISMATCH"
    return None


def validate_records(
    records: Iterable[dict[str, Any]], *, evaluation_time: str = EVALUATION_TIME
) -> dict[str, Any]:
    """Validate records in order and produce deterministic evidence outputs."""
    evaluated_at = parse_utc(evaluation_time)
    if evaluated_at is None:
        raise ValueError("evaluation_time must be ISO-8601 UTC ending in Z")
    seen_samples: set[str] = set()
    seen_coas: set[str] = set()
    decisions: list[dict[str, Any]] = []
    evidence_manifest: list[dict[str, Any]] = []
    for seq, source in enumerate(records, start=1):
        row = normalize_record(source)
        normalized_sha = sha256_hex(row)
        # A row may arrive from CSV or JSON, so its stable source identity is the
        # canonical normalized row. Whole-file byte hashes are recorded by the
        # artifact writer for transport-level provenance.
        source_sha = normalized_sha
        reason = classify_record(
            row,
            seen_samples=seen_samples,
            seen_coas=seen_coas,
            evaluated_at=evaluated_at,
        )
        decision = {
            "record_id": row["record_id"],
            "sample_id": row["sample_id"],
            "coa_id": row["coa_id"],
            "jurisdiction": row["jurisdiction"],
            "status": "HOLD" if reason else "RELEASEABLE",
            "reason_code": reason or "",
            "source_sha256": source_sha,
            "normalized_sha256": normalized_sha,
            "result_sha256": row["result_sha256"],
            "autonomous_release": False,
        }
        decisions.append(decision)
        evidence_manifest.append(
            {
                "seq": seq,
                "record_id": row["record_id"],
                "status": decision["status"],
                "reason_code": decision["reason_code"],
                "source_sha256": source_sha,
                "normalized_sha256": normalized_sha,
                "result_sha256": row["result_sha256"],
                "previous_entry_sha256": (
                    sha256_hex(evidence_manifest[-1]) if evidence_manifest else ""
                ),
            }
        )
        seen_samples.add(row["sample_id"])
        seen_coas.add(row["coa_id"])

    hold_counts = {code: 0 for code in REASON_CODES}
    jurisdiction_counts = {code: 0 for code in RULE_PACKS}
    for decision in decisions:
        if decision["reason_code"]:
            hold_counts[decision["reason_code"]] += 1
        else:
            jurisdiction_counts[decision["jurisdiction"]] += 1
    releaseable = sum(item["status"] == "RELEASEABLE" for item in decisions)
    held = len(decisions) - releaseable
    manifest_sha = sha256_hex(evidence_manifest)
    result = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "evaluated_at": evaluation_time,
        "input_records": len(decisions),
        "releaseable": releaseable,
        "held": held,
        "hold_counts": hold_counts,
        "jurisdiction_releaseable": jurisdiction_counts,
        "decisions": decisions,
        "evidence_manifest": evidence_manifest,
        "evidence_manifest_sha256": manifest_sha,
        "exception_report": exception_report_text(decisions),
        "override_history": [],
        "autonomous_releases": 0,
        "result_alterations": 0,
        "source_mutations": 0,
        "interface_live": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    result["audit_sha256"] = sha256_hex(
        {
            "schema": SCHEMA,
            "decisions": decisions,
            "evidence_manifest_sha256": manifest_sha,
            "exception_report": result["exception_report"],
        }
    )
    return result


def append_override(
    history: list[dict[str, Any]],
    decision: dict[str, Any],
    *,
    reviewer: str,
    reason: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Return a new append-only override ledger without mutating prior history."""
    if decision.get("status") != "HOLD":
        raise ValueError("override applies only to HOLD decisions")
    reviewer = _text(reviewer)
    reason = _text(reason)
    timestamp = _text(timestamp)
    if not reviewer or reviewer.upper() in RESERVED_REVIEWERS:
        raise ValueError("named human reviewer metadata is missing")
    if not reason or parse_utc(timestamp) is None:
        raise ValueError("override reason and UTC timestamp are missing")
    previous_hash = sha256_hex(history[-1]) if history else ""
    entry = {
        "seq": len(history) + 1,
        "record_id": decision["record_id"],
        "sample_id": decision["sample_id"],
        "coa_id": decision["coa_id"],
        "original_reason_code": decision["reason_code"],
        "reviewer": reviewer,
        "reason": reason,
        "timestamp": timestamp,
        "previous_entry_sha256": previous_hash,
    }
    entry["entry_sha256"] = sha256_hex(entry)
    return [*deepcopy(history), entry]


def record_human_release(
    decision: dict[str, Any],
    *,
    reviewer: str,
    timestamp: str,
    override_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record a human decision; validation output itself remains unchanged."""
    reviewer = _text(reviewer)
    timestamp = _text(timestamp)
    if (
        not reviewer
        or reviewer.upper() in RESERVED_REVIEWERS
        or parse_utc(timestamp) is None
    ):
        return {"ok": False, "code": "NAMED_HUMAN_REQUIRED"}
    if decision.get("status") == "HOLD":
        matching = [
            entry
            for entry in override_history or []
            if entry.get("record_id") == decision.get("record_id")
        ]
        if not matching:
            return {"ok": False, "code": "HOLD_REQUIRES_RECORDED_OVERRIDE"}
    receipt = {
        "record_id": decision["record_id"],
        "sample_id": decision["sample_id"],
        "coa_id": decision["coa_id"],
        "reviewer": reviewer,
        "timestamp": timestamp,
        "validation_status": decision["status"],
        "released_by_named_human": True,
    }
    receipt["receipt_sha256"] = sha256_hex(receipt)
    return {"ok": True, "code": "HUMAN_RELEASE_RECORDED", "receipt": receipt}


def records_to_csv(records: Iterable[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for source in records:
        row = normalize_record(source)
        writer.writerow(
            {
                **{field: row[field] for field in CSV_FIELDS if field != "custody_events"},
                "custody_events": "|".join(row["custody_events"]),
                "synthetic": "true" if row["synthetic"] else "false",
            }
        )
    return buffer.getvalue()


def records_from_csv(text: str) -> list[dict[str, Any]]:
    return [normalize_record(dict(row)) for row in csv.DictReader(io.StringIO(text))]


def records_to_json(records: Iterable[dict[str, Any]]) -> str:
    return _canonical([normalize_record(row) for row in records]) + "\n"


def records_from_json(text: str) -> list[dict[str, Any]]:
    value = json.loads(text)
    if not isinstance(value, list):
        raise ValueError("input JSON must be an array")
    return [normalize_record(row) for row in value]


def decisions_to_csv(decisions: Iterable[dict[str, Any]]) -> str:
    fields = (
        "record_id",
        "sample_id",
        "coa_id",
        "jurisdiction",
        "status",
        "reason_code",
        "source_sha256",
        "normalized_sha256",
        "result_sha256",
        "autonomous_release",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for decision in decisions:
        writer.writerow(decision)
    return buffer.getvalue()


def exception_report_text(decisions: Iterable[dict[str, Any]]) -> str:
    held = [item for item in decisions if item["status"] == "HOLD"]
    lines = [
        f"SC Labs multistate COA gate — {len(held)} HOLD",
        "Validation overlay only. Named-human disposition required.",
        "",
    ]
    lines.extend(
        f"{item['record_id']} | {item['sample_id']} | {item['coa_id']} | {item['reason_code']}"
        for item in held
    )
    return "\n".join(lines) + "\n"


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    checks = {
        "input_records": result.get("input_records") == 150,
        "releaseable": result.get("releaseable") == 120,
        "held": result.get("held") == 30,
        "hold_counts": result.get("hold_counts")
        == {code: 5 for code in REASON_CODES},
        "manifest_rows": len(result.get("evidence_manifest") or []) == 150,
        "decisions": len(result.get("decisions") or []) == 150,
        "autonomous_releases": result.get("autonomous_releases") == 0,
        "result_alterations": result.get("result_alterations") == 0,
        "source_mutations": result.get("source_mutations") == 0,
        "interface_live": result.get("interface_live") is False,
    }
    failures.extend(name for name, ok in checks.items() if not ok)
    if any(
        item["status"] == "RELEASEABLE" and item["reason_code"]
        for item in result.get("decisions") or []
    ):
        failures.append("defective_releaseable")
    if any(
        item["autonomous_release"] for item in result.get("decisions") or []
    ):
        failures.append("autonomous_release")
    if len(result.get("evidence_manifest_sha256") or "") != 64:
        failures.append("manifest_sha256")
    if len(result.get("audit_sha256") or "") != 64:
        failures.append("audit_sha256")
    return failures


def write_artifacts(
    directory: Path,
    records: list[dict[str, Any]],
    *,
    evaluation_time: str = EVALUATION_TIME,
) -> dict[str, Any]:
    result = validate_records(records, evaluation_time=evaluation_time)
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "fixture.csv": records_to_csv(records),
        "fixture.json": records_to_json(records),
        "decisions.csv": decisions_to_csv(result["decisions"]),
        "decisions.json": _canonical(result["decisions"]) + "\n",
        "evidence-manifest.json": _canonical(result["evidence_manifest"]) + "\n",
        "exception-report.txt": result["exception_report"],
    }
    manifest_path = directory / "evidence-manifest.json"
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestConflict("existing evidence manifest is unreadable") from exc
        requested_manifest = result["evidence_manifest"]
        if (
            not isinstance(existing_manifest, list)
            or existing_manifest != requested_manifest[: len(existing_manifest)]
        ):
            raise ManifestConflict(
                "existing evidence manifest is not an immutable history prefix"
            )
    for name, body in artifacts.items():
        (directory / name).write_text(body, encoding="utf-8", newline="")
    return {
        "written": sorted(artifacts),
        "output_sha256": {
            name: sha256_hex(body) for name, body in sorted(artifacts.items())
        },
        "evidence_manifest_sha256": result["evidence_manifest_sha256"],
        "audit_sha256": result["audit_sha256"],
    }


def _load_input(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".csv":
        return records_from_csv(text)
    if path.suffix.lower() == ".json":
        return records_from_json(text)
    raise ValueError("input must be .csv or .json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="normalized/redacted CSV or JSON")
    parser.add_argument("--write-artifacts", type=Path, help="output directory")
    parser.add_argument("--evaluation-time", default=EVALUATION_TIME)
    args = parser.parse_args(argv)
    records = _load_input(args.input) if args.input else build_acceptance_fixture()
    result = validate_records(records, evaluation_time=args.evaluation_time)
    failures = pass_contract(result) if not args.input else []
    written = (
        write_artifacts(
            args.write_artifacts,
            records,
            evaluation_time=args.evaluation_time,
        )
        if args.write_artifacts
        else None
    )
    summary = {
        "ok": not failures,
        "failures": failures,
        "command": "python3 sc_labs_multistate_coa_gate.py",
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "input_records": result["input_records"],
        "releaseable": result["releaseable"],
        "held": result["held"],
        "hold_counts": result["hold_counts"],
        "evidence_manifest_sha256": result["evidence_manifest_sha256"],
        "audit_sha256": result["audit_sha256"],
        "written": written,
        "truth_gate": TRUTH_GATE,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

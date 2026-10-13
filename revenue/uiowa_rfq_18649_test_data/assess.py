#!/usr/bin/env python3
"""Metadata-only test-data assessment. No network access or fixture execution.

All evidence is supplied by the assessor; references are opaque, never opened.
This tool reports consistency and evidence limitations, not institutional findings.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import sys
from typing import Any

SCHEMA_VERSION = 1
CONTEXTS = {"synthetic-demo", "assessment-metadata"}


class InputError(ValueError):
    """An input record is malformed or internally impossible."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise InputError(message)


def text(value: Any, where: str, nullable: bool = False) -> None:
    require((nullable and value is None) or
            (isinstance(value, str) and bool(value.strip())),
            f"{where}: expected a nonempty string" + (" or null" if nullable else ""))


def fields(value: Any, keys: str, where: str) -> None:
    require(isinstance(value, dict), f"{where}: expected an object")
    expected = set(keys.split())
    require(set(value) == expected,
            f"{where}: missing={sorted(expected - set(value))}; unknown={sorted(set(value) - expected)}")


def sequence(value: Any, where: str) -> None:
    require(isinstance(value, list), f"{where}: expected an array")


def instant(value: Any, where: str = "timestamp") -> datetime:
    text(value, where)
    require("T" in value, f"{where}: expected ISO 8601 date-time with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, f"{where}: timezone is required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{where}: invalid timestamp {value!r}") from exc


def unique(values: list[Any], where: str) -> None:
    require(len(values) == len(set(values)), f"{where}: duplicate values")


def validate(catalog: dict[str, Any]) -> None:
    fields(catalog, "schema_version context contracts fixtures", "catalog")
    require(type(catalog["schema_version"]) is int and catalog["schema_version"] == SCHEMA_VERSION,
            "catalog.schema_version: expected integer 1")
    text(catalog["context"], "catalog.context")
    require(catalog["context"] in CONTEXTS, "catalog.context: unsupported context")
    contracts: dict[str, Any] = {}
    sequence(catalog["contracts"], "contracts")
    require(bool(catalog["contracts"]), "contracts: at least one contract is required")
    for c in catalog["contracts"]:
        fields(c, "id group version required_cases", "contract")
        for key in ("id", "group", "version"):
            text(c[key], f"contract.{key}")
        require(c["id"] not in contracts, f"contract: duplicate id {c['id']}")
        sequence(c["required_cases"], "contract.required_cases")
        require(bool(c["required_cases"]), "contract.required_cases: cannot be empty")
        for case in c["required_cases"]:
            text(case, "contract.required_case")
        unique(c["required_cases"], "contract.required_cases")
        contracts[c["id"]] = c
    sequence(catalog["fixtures"], "fixtures")
    fixture_ids: set[str] = set()
    for f in catalog["fixtures"]:
        fields(f, "id contract_id contract_version fixture_version origin state owner maintenance_hours refresh_interval_days recipe_ref created_at cleanup_due_at refreshes cleanups cases", "fixture")
        for key in ("id", "contract_id", "origin", "state"):
            text(f[key], f"fixture.{key}")
        for key in ("contract_version", "fixture_version", "owner", "recipe_ref"):
            text(f[key], f"fixture.{key}", nullable=True)
        require(f["id"] not in fixture_ids, f"fixture: duplicate id {f['id']}")
        fixture_ids.add(f["id"])
        require(f["contract_id"] in contracts, f"{f['id']}: unknown contract_id")
        require(f["origin"] in {"synthetic", "production-derived", "unknown"}, f"{f['id']}: invalid origin")
        require(f["state"] in {"active", "retired"}, f"{f['id']}: invalid state")
        if catalog["context"] == "synthetic-demo":
            require(f["origin"] == "synthetic", f"{f['id']}: a synthetic demo may contain only synthetic fixtures")
        hours = f["maintenance_hours"]
        require(hours is None or (type(hours) in (int, float) and (type(hours) is int or math.isfinite(hours)) and hours >= 0),
                f"{f['id']}.maintenance_hours: expected finite nonnegative number or null")
        interval = f["refresh_interval_days"]
        require(interval is None or (type(interval) is int and interval > 0),
                f"{f['id']}.refresh_interval_days: expected positive integer or null")
        created = instant(f["created_at"], f"{f['id']}.created_at")
        if f["cleanup_due_at"] is not None:
            require(instant(f["cleanup_due_at"]) >= created, f"{f['id']}: cleanup is due before creation")
        for event_type in ("refreshes", "cleanups"):
            _events(f[event_type], created, f"{f['id']}.{event_type}", versioned=event_type == "refreshes")
        sequence(f["cases"], f"{f['id']}.cases")
        case_ids: list[str] = []
        for case in f["cases"]:
            fields(case, "id input_class expected_behavior runs", f"{f['id']}.case")
            for key in ("id", "input_class", "expected_behavior"):
                text(case[key], f"{f['id']}.case.{key}")
            case_ids.append(case["id"])
            require(case["id"] in contracts[f["contract_id"]]["required_cases"],
                    f"{f['id']}: undeclared contract case {case['id']}")
            _events(case["runs"], created, f"{f['id']}.{case['id']}.runs", versioned=True)
        unique(case_ids, f"{f['id']}.cases")


def _events(events: Any, created: datetime, where: str, versioned: bool) -> None:
    sequence(events, where)
    times: list[datetime] = []
    keys = "at outcome evidence_ref" + (" fixture_version contract_version" if versioned else "")
    for e in events:
        fields(e, keys, where)
        when = instant(e["at"], f"{where}.at")
        require(when >= created, f"{where}: event precedes fixture creation")
        times.append(when)
        text(e["outcome"], f"{where}.outcome")
        require(e["outcome"] in {"succeeded", "failed"}, f"{where}: invalid outcome")
        text(e["evidence_ref"], f"{where}.evidence_ref", nullable=True)
        if versioned:
            for key in ("fixture_version", "contract_version"):
                text(e[key], f"{where}.{key}")
    unique(times, where + ".at (ambiguous event ordering)")


def _latest(events: list[dict[str, Any]], as_of: datetime) -> dict[str, Any] | None:
    eligible = [e for e in events if instant(e["at"]) <= as_of]
    return max(eligible, key=lambda e: instant(e["at"])) if eligible else None


def _backed(event: dict[str, Any] | None) -> bool:
    return bool(event and event["evidence_ref"])


def assess(catalog: dict[str, Any], as_of: str) -> dict[str, Any]:
    validate(catalog)
    clock = instant(as_of, "as_of")
    limitations: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    contracts = {c["id"]: c for c in catalog["contracts"]}

    def note(f: dict[str, Any], code: str, status: str, consequence: str,
             improvement: str, evidence: list[str] | None = None, case_id: str | None = None) -> None:
        limitations.append({"fixture_id": f["id"], "contract_id": f["contract_id"],
                            "case_id": case_id, "code": code, "evidence_state": status,
                            "consequence": consequence, "next_action": improvement,
                            "owner": f["owner"], "estimated_maintenance_hours": f["maintenance_hours"],
                            "evidence_refs": evidence or []})

    for f in sorted(catalog["fixtures"], key=lambda x: x["id"]):
        c = contracts[f["contract_id"]]
        eligible = True
        if instant(f["created_at"]) > clock:
            eligible = False
            note(f, "NOT_YET_CREATED", "UNKNOWN", "Fixture was not present at the assessment cutoff.",
                 "Reconcile the cutoff or obtain an earlier fixture record.")
        if f["state"] == "retired":
            eligible = False
            note(f, "RETIRED_FIXTURE", "RECORDED", "Retired inventory does not establish current coverage.",
                 "Link an active replacement or accept the documented testing limitation.")
        for key, code, action in (("owner", "OWNER_UNKNOWN", "Assign an accountable team role for refresh and cleanup."),
                                  ("maintenance_hours", "EFFORT_UNKNOWN", "Estimate refresh, review and cleanup effort before prioritizing."),
                                  ("recipe_ref", "RECIPE_UNKNOWN", "Capture a repeatable fixture-generation and refresh recipe.")):
            if f[key] is None:
                note(f, code, "UNKNOWN", "Maintenance planning lacks " + key + ".", action)
        if f["origin"] != "synthetic":
            note(f, "ORIGIN_REVIEW", "UNKNOWN" if f["origin"] == "unknown" else "RECORDED",
                 "Provenance needs a separate data-handling review; this tool inspects metadata only.",
                 "Confirm classification, minimization and permitted use without supplying record values.")
        version_ok = f["fixture_version"] is not None and f["contract_version"] == c["version"]
        if not version_ok:
            eligible = False
            note(f, "VERSION_ALIGNMENT", "UNKNOWN" if f["contract_version"] is None or f["fixture_version"] is None else "CONTRADICTED",
                 "Fixture metadata does not match the declared current interface.",
                 "Version the fixture and reconcile its interface contract before relying on its runs.")
        refresh = _latest(f["refreshes"], clock)
        refresh_ok = bool(refresh and refresh["outcome"] == "succeeded" and _backed(refresh)
                          and refresh["fixture_version"] == f["fixture_version"]
                          and refresh["contract_version"] == c["version"])
        if not refresh_ok:
            eligible = False
            note(f, "REFRESH_NOT_DEMONSTRATED", "RECORDED" if _backed(refresh) else "UNKNOWN",
                 "A current repeatable refresh has not been demonstrated by the supplied latest record.",
                 "Capture a successful, version-aligned refresh receipt; a recipe alone is not a rehearsal.",
                 [refresh["evidence_ref"]] if _backed(refresh) else [])
        interval = f["refresh_interval_days"]
        if interval is None:
            eligible = False
            note(f, "REFRESH_CADENCE_UNKNOWN", "UNKNOWN", "There is no declared freshness horizon.",
                 "Agree a service-appropriate refresh interval and interface-change trigger.")
        elif refresh_ok and (clock - instant(refresh["at"])).total_seconds() > interval * 86400:
            eligible = False
            note(f, "REFRESH_OVERDUE", "RECORDED", "The latest refresh is older than the supplied refresh interval.",
                 "Refresh and rerun affected cases, or record a revised service-specific interval.", [refresh["evidence_ref"]])
        cleanup = _latest(f["cleanups"], clock)
        # Completion changes the fixture generation; a later failed or unbacked
        # attempt cannot undo it. Keep latest-attempt diagnostics above, while
        # comparing the last demonstrated cleanup and recreation independently.
        completed_cleanup = _latest([e for e in f["cleanups"]
                                     if e["outcome"] == "succeeded" and _backed(e)], clock)
        completed_refresh = _latest([e for e in f["refreshes"]
                                     if e["outcome"] == "succeeded" and _backed(e)], clock)
        cleaned = bool(completed_cleanup and
                       (not completed_refresh or
                        instant(completed_cleanup["at"]) >= instant(completed_refresh["at"])))
        if cleaned and f["state"] == "active":
            eligible = False
            note(f, "ACTIVE_AFTER_CLEANUP", "CONTRADICTED", "An active fixture is recorded as cleaned without a later refresh.",
                 "Reconcile inventory state or provide a later successful recreation receipt.", [completed_cleanup["evidence_ref"]])
        if f["cleanup_due_at"] is None:
            note(f, "CLEANUP_HORIZON_UNKNOWN", "UNKNOWN", "Cleanup or retained-fixture review timing is unspecified.",
                 "Set a proportionate cleanup/review horizon and accountable owner.")
        elif instant(f["cleanup_due_at"]) < clock and not cleaned:
            note(f, "CLEANUP_NOT_DEMONSTRATED", "RECORDED" if _backed(cleanup) else "UNKNOWN",
                 "The supplied cleanup due time has passed without a successful cleanup receipt.",
                 "Demonstrate cleanup or document the retention/review decision and next due time.",
                 [cleanup["evidence_ref"]] if _backed(cleanup) else [])
        observed = []
        for case in sorted(f["cases"], key=lambda x: x["id"]):
            run = _latest(case["runs"], clock)
            valid_run = bool(run and _backed(run) and run["fixture_version"] == f["fixture_version"]
                             and run["contract_version"] == c["version"] and refresh_ok
                             and instant(run["at"]) > instant(refresh["at"]))
            if eligible and valid_run:
                status = "supported" if run["outcome"] == "succeeded" else "failure_recorded"
            else:
                status = "unknown"
            refs = [run["evidence_ref"]] if _backed(run) else []
            if status != "supported":
                note(f, "CASE_FAILURE_RECORDED" if status == "failure_recorded" else "CASE_EVIDENCE_LIMITED",
                     "RECORDED" if status == "failure_recorded" else "UNKNOWN",
                     "Latest supplied case run failed; this does not identify a production defect." if status == "failure_recorded"
                     else "Declared case lacks usable, current, post-refresh run evidence.",
                     "Investigate the failed case and capture the resolution and rerun." if status == "failure_recorded"
                     else "Capture a version-aligned run after the demonstrated refresh and before the cutoff.", refs, case["id"])
            observed.append({"id": case["id"], "status": status, "evidence_refs": refs,
                             "latest_run_at": run["at"] if run else None,
                             "latest_run_outcome": run["outcome"] if run else None,
                             "latest_run_fixture_version": run["fixture_version"] if run else None,
                             "latest_run_contract_version": run["contract_version"] if run else None})
        results.append({"fixture_id": f["id"], "contract_id": f["contract_id"], "current_evidence_eligible": eligible,
                        "cases": observed, "latest_refresh_at": refresh["at"] if refresh else None,
                        "latest_cleanup_at": cleanup["at"] if cleanup else None,
                        "excluded_future_events": sum(instant(e["at"]) > clock
                            for events in [f["refreshes"], f["cleanups"]] + [case["runs"] for case in f["cases"]]
                            for e in events)})
    coverage = []
    for c in sorted(catalog["contracts"], key=lambda x: x["id"]):
        for case_id in sorted(c["required_cases"]):
            matches = [(r["fixture_id"], case) for r in results if r["contract_id"] == c["id"]
                       for case in r["cases"] if case["id"] == case_id]
            coverage.append({"contract_id": c["id"], "group": c["group"], "case_id": case_id,
                             "declared_by": [fid for fid, _ in matches],
                             "supported_by": [fid for fid, case in matches if case["status"] == "supported"],
                             "failure_recorded_by": [fid for fid, case in matches if case["status"] == "failure_recorded"],
                             "unknown_by": [fid for fid, case in matches if case["status"] == "unknown"]})
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return {"schema_version": SCHEMA_VERSION, "work_order": "UIOWA-047", "context": catalog["context"],
            "as_of": clock.isoformat(), "catalog_sha256": hashlib.sha256(canonical).hexdigest(),
            "scope_notice": "Supplied metadata only. Synthetic examples are fictional. Evidence references are not independently verified. No institutional finding, compliance verdict or release authorization.",
            "summary": {"fixtures": len(results), "required_cases": len(coverage),
                        "cases_with_supported_evidence": sum(bool(r["supported_by"]) for r in coverage),
                        "cases_without_specification": sum(not r["declared_by"] for r in coverage),
                        "cases_with_recorded_failure": sum(bool(r["failure_recorded_by"]) for r in coverage),
                        "limitations_by_code": dict(sorted(Counter(n["code"] for n in limitations).items()))},
            "coverage": coverage, "fixtures": results, "limitations": limitations}


def markdown(report: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        raw = "UNKNOWN" if value is None else ", ".join(value) if isinstance(value, list) else str(value)
        return html.escape(raw, quote=True).replace("|", "&#124;").replace("\r", " ").replace("\n", " ").replace("`", "&#96;").replace("[", "&#91;").replace("]", "&#93;")
    lines = ["# Test-data readiness evidence", "", report["scope_notice"], "",
             f"Context: {cell(report['context'])}; cutoff: {cell(report['as_of'])}",
             f"Canonical catalog SHA-256: `{report['catalog_sha256']}`", "",
             "Counts are coverage descriptors, not a maturity or release-readiness score.", "",
             "| Contract | Group | Boundary case | Declared | Supported | Recorded failure | Unknown |",
             "|---|---|---|---|---|---|---|"]
    for row in report["coverage"]:
        lines.append("| " + " | ".join(cell(row[k]) for k in ("contract_id", "group", "case_id", "declared_by", "supported_by", "failure_recorded_by", "unknown_by")) + " |")
    lines += ["", "## Limitations and maintenance actions", "",
              "| Fixture / case | Code / evidence state | Testing consequence | Next action | Owner | Estimated hours | Evidence refs |",
              "|---|---|---|---|---|---|---|"]
    for n in report["limitations"]:
        values = [n["fixture_id"] + (" / " + n["case_id"] if n["case_id"] else ""),
                  n["code"] + " / " + n["evidence_state"], n["consequence"], n["next_action"], n["owner"],
                  n["estimated_maintenance_hours"], n["evidence_refs"]]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", "A missing specification is a sampling/design gap, not proof the behavior is untested everywhere.",
              "Failures on one fixture remain visible even when another fixture supplies passing evidence.", ""]
    return "\n".join(lines)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in out, f"JSON: duplicate key {key!r}")
        out[key] = value
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--as-of", required=True, help="ISO 8601 timestamp with timezone; explicit for reproducibility")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.resolve() == args.catalog.resolve():
            raise InputError("Output must not overwrite the input catalog")
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"), object_pairs_hook=_object)
        report = assess(catalog, args.as_of)
        rendered = markdown(report) if args.format == "markdown" else json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (InputError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"test-data assessment: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline test-data readiness assessor for UIOWA-047.

Consumes a synthetic or exported JSON catalog and reports evidence-backed readiness
signals. The evaluator never contacts external systems and never converts missing
evidence into a defect: missing inputs are reported as UNKNOWN.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

EVIDENCED = "EVIDENCED"
OBSERVED_GAP = "OBSERVED_GAP"
UNKNOWN = "UNKNOWN"

VALID_STATES = {EVIDENCED, OBSERVED_GAP, UNKNOWN}


def _date(value: Any) -> date | None:
    # Catalog dates are calendar dates, not timestamps or arbitrary prefixes.
    if (not isinstance(value, str) or len(value) != 10
            or value[4] != "-" or value[7] != "-"):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _case_set(value: Any) -> set[str] | None:
    """Keep absent/invalid evidence distinct from an explicitly empty inventory.

    Case identities are exact nonblank strings. Do not coerce mapping keys,
    string characters, numbers or nested values into evidence, or normalize
    distinct identifiers. Duplicates describe the same case, not extra coverage.
    """
    if not isinstance(value, list):
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return set(value)


def _days_between(start: date, end: date) -> int:
    return (end - start).days


def _check(check_id: str, state: str, detail: str, follow_up: str = "") -> Dict[str, str]:
    if state not in VALID_STATES:
        raise ValueError(f"invalid state: {state}")
    return {
        "check_id": check_id,
        "state": state,
        "detail": detail,
        "follow_up": follow_up,
    }


def evaluate_dataset(dataset: Dict[str, Any], as_of: date) -> Dict[str, Any]:
    """Evaluate one catalog entry without inferring facts from absent evidence."""
    result = {
        "dataset_id": dataset.get("dataset_id") or "UNNAMED",
        "service": dataset.get("service") or "UNKNOWN",
        "purpose": dataset.get("purpose") or "",
        "checks": [],
    }
    checks: List[Dict[str, str]] = result["checks"]

    owner = str(dataset.get("owner_role") or "").strip()
    checks.append(
        _check(
            "ownership",
            EVIDENCED if owner else UNKNOWN,
            f"Owner role recorded: {owner}" if owner else "No owner role supplied.",
            "" if owner else "Identify the role accountable for fixture refresh and retirement.",
        )
    )

    refreshed = _date(dataset.get("last_refreshed"))
    cadence = dataset.get("refresh_cadence_days")
    if refreshed is None:
        checks.append(
            _check(
                "refresh_freshness",
                UNKNOWN,
                "No reliable last_refreshed date supplied.",
                "Locate refresh history or record that refresh timing is not currently evidenced.",
            )
        )
    elif refreshed > as_of:
        checks.append(
            _check(
                "refresh_freshness",
                UNKNOWN,
                f"Last refresh {refreshed.isoformat()} is after assessment date "
                f"{as_of.isoformat()}; it does not evidence refresh as of that date.",
                "Locate refresh evidence on or before the assessment date, or correct "
                "the catalog chronology from its source records.",
            )
        )
    elif isinstance(cadence, bool) or not isinstance(cadence, int) or cadence <= 0:
        checks.append(
            _check(
                "refresh_freshness",
                UNKNOWN,
                f"Last refresh is {refreshed.isoformat()}, but no valid cadence is supplied.",
                "Define an evidence-backed refresh trigger or cadence appropriate to the fixture.",
            )
        )
    else:
        age = _days_between(refreshed, as_of)
        stale = age > cadence
        checks.append(
            _check(
                "refresh_freshness",
                OBSERVED_GAP if stale else EVIDENCED,
                f"Fixture age is {age} days against a {cadence}-day cadence.",
                "Review whether stale data still represents current interfaces and boundary behavior."
                if stale
                else "",
            )
        )

    fixture_version = str(dataset.get("fixture_interface_version") or "").strip()
    current_version = str(dataset.get("current_interface_version") or "").strip()
    if not fixture_version or not current_version:
        checks.append(
            _check(
                "interface_alignment",
                UNKNOWN,
                "Fixture and current interface versions are not both evidenced.",
                "Record the fixture contract/schema version and the current interface version.",
            )
        )
    elif fixture_version != current_version:
        checks.append(
            _check(
                "interface_alignment",
                OBSERVED_GAP,
                f"Fixture targets {fixture_version}; current interface is {current_version}.",
                "Review the interface delta and update or explicitly justify the fixture version.",
            )
        )
    else:
        checks.append(
            _check(
                "interface_alignment",
                EVIDENCED,
                f"Fixture and current interface both identify {current_version}.",
            )
        )

    required = _case_set(dataset.get("required_boundary_cases"))
    covered = _case_set(dataset.get("covered_boundary_cases"))
    if not required:
        checks.append(
            _check(
                "representativeness",
                UNKNOWN,
                "No valid nonempty required boundary-case list is documented.",
                "Define the required boundaries as a nonempty list of nonblank string "
                "case identities; invalid or absent entries do not establish an expectation.",
            )
        )
    elif covered is None:
        checks.append(
            _check(
                "representativeness",
                UNKNOWN,
                "No valid covered boundary-case inventory is supplied.",
                "Record covered cases as a list of nonblank string identities. Use an "
                "empty list only when the supplied inventory explicitly records no covered cases.",
            )
        )
    else:
        missing = sorted(required - covered)
        if missing:
            checks.append(
                _check(
                    "representativeness",
                    OBSERVED_GAP,
                    "Missing boundary cases: " + ", ".join(missing),
                    "Add or intentionally waive each missing case with service-owner rationale.",
                )
            )
        else:
            checks.append(
                _check(
                    "representativeness",
                    EVIDENCED,
                    f"All {len(required)} documented boundary cases are represented.",
                )
            )

    # Only explicit booleans declare whether cleanup applies. Absence is not False.
    cleanup_required = dataset.get("cleanup_required")
    cleanup_verified = (
        _date(dataset.get("cleanup_last_verified")) if cleanup_required is True else None
    )
    if cleanup_required is False:
        checks.append(
            _check(
                "cleanup",
                EVIDENCED,
                "Catalog marks cleanup as not required for this fixture.",
            )
        )
    elif cleanup_required is not True:
        checks.append(
            _check(
                "cleanup",
                UNKNOWN,
                "No reliable boolean cleanup_required declaration supplied.",
                "Record whether cleanup is required; an omitted declaration does not "
                "establish that cleanup is unnecessary.",
            )
        )
    elif cleanup_verified is None:
        checks.append(
            _check(
                "cleanup",
                UNKNOWN,
                "Cleanup is required but no verification date is supplied.",
                "Demonstrate cleanup/retirement behavior or record why evidence is unavailable.",
            )
        )
    elif cleanup_verified > as_of:
        checks.append(
            _check(
                "cleanup",
                UNKNOWN,
                f"Cleanup verification {cleanup_verified.isoformat()} is after assessment "
                f"date {as_of.isoformat()}; it does not evidence cleanup as of that date.",
                "Locate verification on or before the assessment date, or correct the "
                "catalog chronology from its source records.",
            )
        )
    else:
        checks.append(
            _check(
                "cleanup",
                EVIDENCED,
                f"Cleanup verification recorded on {cleanup_verified.isoformat()}.",
            )
        )

    retention = dataset.get("retention_days")
    if retention is None:
        checks.append(
            _check(
                "retention",
                UNKNOWN,
                "No retention duration is supplied.",
                "Record the fixture retention/retirement rule and its owner.",
            )
        )
    elif isinstance(retention, bool) or not isinstance(retention, int) or retention < 0:
        checks.append(
            _check(
                "retention",
                OBSERVED_GAP,
                f"Invalid retention_days value: {retention!r}.",
                "Correct the catalog entry and document the intended retention rule.",
            )
        )
    else:
        checks.append(
            _check(
                "retention",
                EVIDENCED,
                f"Retention rule recorded as {retention} days.",
            )
        )

    origin = str(dataset.get("data_origin") or "").strip().lower()
    handling = str(dataset.get("handling_reference") or "").strip()
    if not origin:
        checks.append(
            _check(
                "data_origin",
                UNKNOWN,
                "Data origin is not supplied.",
                "Record whether the fixture is synthetic, generated, masked, or production-derived.",
            )
        )
    elif origin == "synthetic":
        checks.append(
            _check("data_origin", EVIDENCED, "Fixture is explicitly marked synthetic.")
        )
    elif handling:
        checks.append(
            _check(
                "data_origin",
                EVIDENCED,
                f"Fixture origin is {origin}; a handling reference is recorded.",
            )
        )
    else:
        checks.append(
            _check(
                "data_origin",
                UNKNOWN,
                f"Fixture origin is {origin}, but no handling reference is supplied.",
                "Locate the applicable handling/minimization/cleanup evidence before drawing conclusions.",
            )
        )

    counts = Counter(c["state"] for c in checks)
    result["summary"] = {
        EVIDENCED: counts[EVIDENCED],
        OBSERVED_GAP: counts[OBSERVED_GAP],
        UNKNOWN: counts[UNKNOWN],
    }
    return result


def evaluate_catalog(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    as_of = _date(payload.get("as_of"))
    if as_of is None:
        raise ValueError("catalog requires ISO date field 'as_of'")
    datasets = payload.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("catalog requires a 'datasets' array")
    for index, dataset in enumerate(datasets):
        if not isinstance(dataset, dict):
            raise ValueError(f"datasets[{index}] must be a JSON object")
    results = [evaluate_dataset(d, as_of) for d in datasets]
    aggregate = Counter()
    for result in results:
        aggregate.update(result["summary"])
    return {
        "assessment": "UIOWA-047 test-data readiness",
        "as_of": as_of.isoformat(),
        "input_label": payload.get("label") or "",
        "dataset_count": len(results),
        "state_definitions": {
            EVIDENCED: "The supplied record contains evidence for this check.",
            OBSERVED_GAP: "Supplied evidence shows a mismatch against the catalog's own documented expectation.",
            UNKNOWN: "The supplied record is insufficient; no defect is inferred.",
        },
        "summary": {
            EVIDENCED: aggregate[EVIDENCED],
            OBSERVED_GAP: aggregate[OBSERVED_GAP],
            UNKNOWN: aggregate[UNKNOWN],
        },
        "datasets": results,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Test-data readiness assessment",
        "",
        f"- Assessment date: {report['as_of']}",
        f"- Catalog: {report.get('input_label') or 'unlabeled'}",
        f"- Datasets: {report['dataset_count']}",
        f"- Evidenced checks: {report['summary'][EVIDENCED]}",
        f"- Observed gaps: {report['summary'][OBSERVED_GAP]}",
        f"- Unknowns: {report['summary'][UNKNOWN]}",
        "",
        "> OBSERVED_GAP means the supplied catalog conflicts with its own documented expectation. "
        "UNKNOWN means evidence is missing or insufficient; it is not converted into a defect.",
        "",
        "| Service | Dataset | Check | State | Detail | Follow-up |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for dataset in report["datasets"]:
        for check in dataset["checks"]:
            vals = [
                dataset["service"],
                dataset["dataset_id"],
                check["check_id"],
                check["state"],
                check["detail"],
                check["follow_up"],
            ]
            vals = [str(v).replace("|", "\\|").replace("\n", " ") for v in vals]
            lines.append("| " + " | ".join(vals) + " |")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This report evaluates only the supplied catalog. It does not inspect University systems, "
            "prove data quality, establish compliance, or infer maturity from absent evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    return payload


def _check_output_target(output: Path, catalog: Path) -> None:
    """Reject catalog aliases and ambiguous destinations before any replacement."""
    if output.is_symlink():
        raise ValueError("output must not be a symbolic link; choose a regular report path")
    if output.resolve() == catalog.resolve():
        raise ValueError("output must not replace the source catalog")
    try:
        if output.samefile(catalog):
            raise ValueError("output must not alias the source catalog")
    except FileNotFoundError:
        pass  # A new, distinct report path is supported.
    if output.exists() and not output.is_file():
        raise ValueError("output must name a regular report file")


def _write_report(output: Path, rendered: str, catalog: Path) -> None:
    """Stage beside the destination; preserve input/prior report until replacement.

    Replacement of a distinct ordinary report remains supported. This is a
    per-file operation, not a multi-file transaction or power-loss durability
    guarantee. Concurrent external path mutation is outside this CLI contract.
    """
    _check_output_target(output, catalog)
    fd, name = tempfile.mkstemp(prefix=".uiowa047-", suffix=".tmp", dir=output.parent)
    staging = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            fd = -1  # The stream now owns the descriptor, including on failure.
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        _check_output_target(output, catalog)
        if output.exists():
            os.chmod(staging, stat.S_IMODE(output.stat().st_mode))
        os.replace(staging, output)
    finally:
        if fd >= 0:
            os.close(fd)
        staging.unlink(missing_ok=True)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="JSON catalog to evaluate")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = evaluate_catalog(load_json(args.catalog))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    else:
        rendered = render_markdown(report)

    if args.output:
        try:
            _write_report(args.output, rendered, args.catalog)
        except (OSError, ValueError) as exc:
            parser.error(f"cannot write report: {exc}")
    else:
        print(rendered, end="" if rendered.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

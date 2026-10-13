#!/usr/bin/env python3
"""Offline DORA five-metric calculator for UIOWA-064 synthetic assessment use.

Service-scoped and descriptive only. No peer percentiles, maturity scores,
compliance verdicts, or individual productivity ratings are produced.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import stat
import tempfile
import statistics
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class DataError(ValueError):
    pass


@dataclass(frozen=True)
class Deployment:
    deployment_id: str
    service: str
    commit_at: datetime | None
    deployed_at: datetime
    intervention_required: bool | None
    recovered_at: datetime | None
    unplanned_rework: bool | None
    notes: str


def _parse_time(value: str, field: str, deployment_id: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DataError(
            f"{deployment_id}: {field} must be an ISO-8601 timestamp with offset"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DataError(f"{deployment_id}: {field} must include a UTC offset")
    return _utc_datetime(parsed, field, deployment_id)


def _parse_bool(value: str, field: str, deployment_id: str) -> bool | None:
    value = value.strip().lower()
    if not value:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise DataError(f"{deployment_id}: {field} must be true, false, or blank")


def _utc_datetime(value: datetime, field: str, record: str) -> datetime:
    """Normalize both CSV and programmatic timestamps before elapsed arithmetic."""
    if not isinstance(value, datetime):
        raise DataError(f"{record}: {field} must be a datetime")
    try:
        has_offset = value.tzinfo is not None and value.utcoffset() is not None
    except (ValueError, OverflowError, TypeError) as exc:
        raise DataError(f"{record}: {field} must include a valid UTC offset") from exc
    if not has_offset:
        raise DataError(f"{record}: {field} must include a UTC offset")
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError) as exc:
        raise DataError(f"{record}: {field} cannot be represented in UTC") from exc


def _normalize_deployment(deployment: Deployment) -> Deployment:
    """Apply one data contract to CSV rows and adapters calling calculate()."""
    if not isinstance(deployment, Deployment):
        raise DataError("each deployment must be a Deployment instance")
    for field in ("deployment_id", "service"):
        value = getattr(deployment, field)
        if not isinstance(value, str) or not value.strip():
            raise DataError(f"deployment: {field} is required and must be text")
    record = deployment.deployment_id.strip()
    for field in ("intervention_required", "unplanned_rework"):
        value = getattr(deployment, field)
        if value is not None and type(value) is not bool:
            raise DataError(f"{record}: {field} must be bool or None")
    if not isinstance(deployment.notes, str):
        raise DataError(f"{record}: notes must be text")
    deployed = _utc_datetime(deployment.deployed_at, "deployed_at", record)
    committed = (
        _utc_datetime(deployment.commit_at, "commit_at", record)
        if deployment.commit_at is not None else None
    )
    recovered = (
        _utc_datetime(deployment.recovered_at, "recovered_at", record)
        if deployment.recovered_at is not None else None
    )
    if committed is not None and committed > deployed:
        raise DataError(f"{record}: commit_at occurs after deployed_at")
    if recovered is not None and recovered < deployed:
        raise DataError(f"{record}: recovered_at occurs before deployed_at")
    if deployment.intervention_required is False and recovered is not None:
        raise DataError(f"{record}: recovered_at supplied while intervention_required=false")
    return replace(
        deployment, deployment_id=record, service=deployment.service.strip(),
        commit_at=committed, deployed_at=deployed, recovered_at=recovered,
    )


def load_deployments(path: Path) -> list[Deployment]:
    required = {
        "deployment_id", "service", "commit_at", "deployed_at",
        "intervention_required", "recovered_at", "unplanned_rework", "notes",
    }
    deployments: list[Deployment] = []
    seen: set[str] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        headers = reader.fieldnames or []
        if any(not name.strip() for name in headers):
            raise DataError("CSV column names must not be blank")
        if len(headers) != len(set(headers)):
            raise DataError("duplicate CSV column names")
        missing = required - set(headers)
        if missing:
            raise DataError(f"missing CSV columns: {sorted(missing)}")

        for row_num, row in enumerate(reader, start=2):
            # Explicit blanks are unknown data; absent/extra cells are malformed rows.
            if None in row:
                raise DataError(f"row {row_num}: more values than CSV column names")
            absent = sorted(name for name, value in row.items() if value is None)
            if absent:
                raise DataError(f"row {row_num}: missing CSV cells: {absent}")
            deployment_id = row["deployment_id"].strip()
            if not deployment_id:
                raise DataError(f"row {row_num}: deployment_id is required")
            if deployment_id in seen:
                raise DataError(f"duplicate deployment_id: {deployment_id}")
            seen.add(deployment_id)

            service = row["service"].strip()
            if not service:
                raise DataError(f"{deployment_id}: service is required")

            deployed_at = _parse_time(row["deployed_at"], "deployed_at", deployment_id)
            if deployed_at is None:
                raise DataError(f"{deployment_id}: deployed_at is required")
            commit_at = _parse_time(row["commit_at"], "commit_at", deployment_id)
            recovered_at = _parse_time(row["recovered_at"], "recovered_at", deployment_id)
            intervention = _parse_bool(
                row["intervention_required"], "intervention_required", deployment_id
            )
            rework = _parse_bool(
                row["unplanned_rework"], "unplanned_rework", deployment_id
            )

            deployments.append(
                _normalize_deployment(Deployment(
                    deployment_id=deployment_id,
                    service=service,
                    commit_at=commit_at,
                    deployed_at=deployed_at,
                    intervention_required=intervention,
                    recovered_at=recovered_at,
                    unplanned_rework=rework,
                    notes=row["notes"].strip(),
                ))
            )
    return deployments


def _hours(delta) -> float:
    return delta.total_seconds() / 3600.0


def _coverage(*, eligible: int, used: int, missing: int) -> dict:
    if eligible == 0:
        status = "NOT_OBSERVED"
    elif missing:
        status = "PARTIAL"
    else:
        status = "COMPLETE"
    return {"status": status, "eligible": eligible, "used": used, "missing": missing}


def _recovery_coverage(*, eligible: int, used: int, missing: int,
                       eligibility_unknown: int) -> dict:
    # Keep unknown failure classification OUT of the known-failure denominator.
    coverage = _coverage(eligible=eligible, used=used, missing=missing)
    coverage["eligibility_unknown"] = eligibility_unknown
    if eligibility_unknown:
        coverage["status"] = "PARTIAL"
    return coverage


def _median_mean(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    return round(statistics.median(values), 3), round(statistics.fmean(values), 3)


def _rate_bounds(positive: int, unknown: int, total: int) -> dict:
    """Logical full-cohort bounds, not imputed rates or confidence intervals."""
    return {
        "lower": round(positive / total, 6),
        "upper": round((positive + unknown) / total, 6),
        "population": total,
        "unknown_classifications": unknown,
        "kind": "MISSING_CLASSIFICATION_BOUNDS_NOT_CONFIDENCE_INTERVAL",
    }


def calculate(
    deployments: Iterable[Deployment],
    *,
    window_start: datetime,
    window_end: datetime,
    service: str | None = None,
    recovery_observed_through: datetime | None = None,
) -> dict:
    window_start = _utc_datetime(window_start, "window_start", "arguments")
    window_end = _utc_datetime(window_end, "window_end", "arguments")
    if window_start >= window_end:
        raise DataError("window_start must be before window_end")
    if service is not None:
        if not isinstance(service, str) or not service.strip():
            raise DataError("service must be nonblank text")
        service = service.strip()
    if recovery_observed_through is not None:
        recovery_observed_through = _utc_datetime(
            recovery_observed_through, "recovery_observed_through", "arguments"
        )
        if recovery_observed_through < window_end:
            raise DataError("recovery_observed_through must be at or after window_end")

    rows: list[Deployment] = []
    seen: set[str] = set()
    for deployment in deployments:
        d = _normalize_deployment(deployment)
        if d.deployment_id in seen:
            raise DataError(f"duplicate deployment_id: {d.deployment_id}")
        seen.add(d.deployment_id)
        if window_start <= d.deployed_at < window_end:
            rows.append(d)
    services = sorted({d.service for d in rows})
    if service is not None:
        rows = [d for d in rows if d.service == service]
    elif len(services) > 1:
        raise DataError(
            "multiple services are present in the window; pass --service so metrics remain service-scoped"
        )
    if not rows:
        raise DataError("no deployments match the selected service/window")

    rows.sort(key=lambda d: (d.deployed_at, d.deployment_id))
    selected_service = rows[0].service

    lead_values = [
        _hours(d.deployed_at - d.commit_at) for d in rows if d.commit_at is not None
    ]
    lead_missing = sum(d.commit_at is None for d in rows)
    lead_median, lead_mean = _median_mean(lead_values)

    intervals = [
        _hours(rows[i].deployed_at - rows[i - 1].deployed_at)
        for i in range(1, len(rows))
    ]
    median_interval = round(statistics.median(intervals), 3) if intervals else None
    window_days = (window_end - window_start).total_seconds() / 86400.0
    per_day = len(rows) / window_days
    per_week = per_day * 7.0

    failed_known = [d for d in rows if d.intervention_required is not None]
    failed_missing = len(rows) - len(failed_known)
    failed = [d for d in failed_known if d.intervention_required is True]
    missing_recovery = [d for d in failed if d.recovered_at is None]
    after_cutoff = [
        d for d in failed
        if d.recovered_at is not None
        and recovery_observed_through is not None
        and d.recovered_at > recovery_observed_through
    ]
    observed_recovery = [
        d for d in failed
        if d.recovered_at is not None
        and (recovery_observed_through is None
             or d.recovered_at <= recovery_observed_through)
    ]
    recovery_values = [
        _hours(d.recovered_at - d.deployed_at) for d in observed_recovery
    ]
    recovery_missing = len(missing_recovery) + len(after_cutoff)
    recovery_median, recovery_mean = _median_mean(recovery_values)

    rework_known = [d for d in rows if d.unplanned_rework is not None]
    rework_missing = len(rows) - len(rework_known)
    rework_count = sum(d.unplanned_rework is True for d in rework_known)

    cfr_rate = (len(failed) / len(failed_known)) if failed_known else None
    rework_rate = (rework_count / len(rework_known)) if rework_known else None

    return {
        "scope": {
            "service": selected_service,
            "window_start": window_start.isoformat().replace("+00:00", "Z"),
            "window_end_exclusive": window_end.isoformat().replace("+00:00", "Z"),
            "deployment_count": len(rows),
            "recovery_observed_through": (
                recovery_observed_through.isoformat().replace("+00:00", "Z")
                if recovery_observed_through is not None else None
            ),
            "recovery_follow_up_mode": (
                "EXPLICIT_RECOVERY_CUTOFF" if recovery_observed_through is not None
                else "ALL_SUPPLIED_RECORDS_RETROSPECTIVE"
            ),
        },
        "metrics": {
            "change_lead_time": {
                "unit": "hours",
                "median": lead_median,
                "mean": lead_mean,
                "coverage": _coverage(
                    eligible=len(rows), used=len(lead_values), missing=lead_missing
                ),
            },
            "deployment_frequency": {
                "deployment_count": len(rows),
                "window_days": round(window_days, 3),
                "deployments_per_day": round(per_day, 6),
                "deployments_per_week": round(per_week, 6),
                "median_interdeployment_hours": median_interval,
                "coverage": _coverage(eligible=len(rows), used=len(rows), missing=0),
            },
            "failed_deployment_recovery_time": {
                "unit": "hours",
                "median": recovery_median,
                "mean": recovery_mean,
                "coverage": _recovery_coverage(
                    eligible=len(failed),
                    used=len(recovery_values),
                    missing=recovery_missing,
                    eligibility_unknown=failed_missing,
                ),
                "evidence": {
                    "observed_recovery_ids": [d.deployment_id for d in observed_recovery],
                    "missing_recovery_timestamp_ids": [d.deployment_id for d in missing_recovery],
                    "recovered_after_cutoff_ids": [d.deployment_id for d in after_cutoff],
                    "unknown_failure_classification_ids": [
                        d.deployment_id for d in rows if d.intervention_required is None
                    ],
                    "known_non_failure_count": len(failed_known) - len(failed),
                },
            },
            "change_fail_rate": {
                "failed_deployments": len(failed),
                "denominator_basis": "KNOWN_CLASSIFICATION_ONLY",
                "full_cohort_rate_bounds": _rate_bounds(len(failed), failed_missing, len(rows)),
                "known_deployments": len(failed_known),
                "rate": round(cfr_rate, 6) if cfr_rate is not None else None,
                "percent": round(cfr_rate * 100, 3) if cfr_rate is not None else None,
                "coverage": _coverage(
                    eligible=len(rows), used=len(failed_known), missing=failed_missing
                ),
            },
            "deployment_rework_rate": {
                "unplanned_rework_deployments": rework_count,
                "denominator_basis": "KNOWN_CLASSIFICATION_ONLY",
                "full_cohort_rate_bounds": _rate_bounds(rework_count, rework_missing, len(rows)),
                "known_deployments": len(rework_known),
                "rate": round(rework_rate, 6) if rework_rate is not None else None,
                "percent": round(rework_rate * 100, 3) if rework_rate is not None else None,
                "coverage": _coverage(
                    eligible=len(rows), used=len(rework_known), missing=rework_missing,
                ),
            },
        },
        "interpretation_boundary": {
            "service_scoped": True,
            "peer_percentile": False,
            "individual_productivity_rating": False,
            "maturity_score": False,
            "partial_metrics_must_be_labeled": True,
            "recovery_statistics_are_observed_case_only": True,
            "classification_as_of_verified": False,
            "source_export_completeness_verified": False,
        },
    }


def _required_time(value: str, field: str) -> datetime:
    parsed = _parse_time(value, field, "arguments")
    if parsed is None:
        raise DataError(f"{field} is required")
    return parsed


def _write_report(payload: str, output: Path, source: Path) -> None:
    """Publish a complete UTF-8 report without truncating its source or old output.

    The CLI operates in an operator-controlled directory. Atomic replacement
    protects an existing report against write/flush/replace failure; it is not
    a claim of crash durability or protection against hostile directory swaps.
    """
    source_stat = source.stat()

    def check_destination() -> None:
        if not os.path.samestat(source_stat, source.stat()):
            raise DataError("input file identity changed during report publication")
        try:
            destination = output.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(destination.st_mode):
            raise DataError("output must not be a symbolic link")
        if not stat.S_ISREG(destination.st_mode):
            raise DataError("output must be a regular file or a new path")
        if os.path.samestat(source_stat, destination):
            raise DataError("output must not overwrite the input CSV or its hardlink")

    check_destination()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            prefix=".uiowa64-report-", suffix=".tmp", dir=output.parent,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Recheck after writing, before making the complete report visible.
        check_destination()
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--service")
    parser.add_argument(
        "--recovery-observed-through",
        help="Inclusive recovery timestamp cutoff; must be at or after window end. "
             "Omit to use all supplied recovery records retrospectively.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        report = calculate(
            load_deployments(args.csv_path),
            window_start=_required_time(args.window_start, "window_start"),
            window_end=_required_time(args.window_end, "window_end"),
            service=args.service,
            recovery_observed_through=(
                _required_time(args.recovery_observed_through, "recovery_observed_through")
                if args.recovery_observed_through is not None else None
            ),
        )
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            _write_report(payload, args.output, args.csv_path)
        else:
            sys.stdout.write(payload)
    except (DataError, OSError, UnicodeError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

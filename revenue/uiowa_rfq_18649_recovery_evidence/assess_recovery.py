#!/usr/bin/env python3
"""Offline backup/recovery evidence assessor for UIOWA-068.

Consumes synthetic or engagement-supplied metadata. It does not touch backup
systems, restore data, or claim that backup completion proves recoverability.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class DataError(ValueError):
    pass


def _time(value, field, service_id):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise DataError(f"{service_id}: {field} must be an ISO-8601 string or null")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DataError(f"{service_id}: {field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DataError(f"{service_id}: {field} must include an offset")
    return parsed.astimezone(timezone.utc)


def _nonnegative_int(value, field, service_id):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DataError(f"{service_id}: {field} must be a nonnegative integer")
    return value


def _minutes(later, earlier):
    return round((later - earlier).total_seconds() / 60.0, 3)


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("services"), list):
        raise DataError("root must be an object with services[]")
    return data


def assess_service(service):
    if not isinstance(service, dict):
        raise DataError("each service must be an object")
    sid = service.get("service_id")
    if not isinstance(sid, str) or not sid:
        raise DataError("service_id is required")
    name = service.get("name")
    function = service.get("business_function")
    if not isinstance(name, str) or not name or not isinstance(function, str) or not function:
        raise DataError(f"{sid}: name and business_function are required")

    target_rpo = _nonnegative_int(
        service.get("target_rpo_minutes"), "target_rpo_minutes", sid
    )
    target_rto = _nonnegative_int(
        service.get("target_rto_minutes"), "target_rto_minutes", sid
    )
    dependencies = service.get("dependencies", [])
    if not isinstance(dependencies, list) or any(
        not isinstance(x, str) or not x for x in dependencies
    ):
        raise DataError(f"{sid}: dependencies must be a list of service IDs")

    backup = service.get("backup")
    if backup is None:
        backup_status = "UNKNOWN"
        backup_evidence = None
        last_success = None
    elif isinstance(backup, dict):
        backup_evidence = backup.get("evidence_id")
        last_success = _time(
            backup.get("last_successful_at"), "backup.last_successful_at", sid
        )
        backup_status = (
            "EVIDENCED"
            if isinstance(backup_evidence, str)
            and backup_evidence
            and last_success is not None
            else "PARTIAL"
        )
    else:
        raise DataError(f"{sid}: backup must be an object or null")

    ex = service.get("exercise")
    result = {
        "service_id": sid,
        "name": name,
        "business_function": function,
        "dependencies": dependencies,
        "target_rpo_minutes": target_rpo,
        "target_rto_minutes": target_rto,
        "backup_status": backup_status,
        "backup_evidence_id": backup_evidence,
        "last_successful_backup_at": (
            last_success.isoformat().replace("+00:00", "Z") if last_success else None
        ),
        "restoration_status": "NOT_DEMONSTRATED",
        "exercise_id": None,
        "observed_rpo_minutes": None,
        "rpo_result": "UNKNOWN",
        "observed_rto_minutes": None,
        "rto_result": "UNKNOWN",
        "dependency_verification": (
            "NOT_APPLICABLE" if not dependencies else "UNKNOWN"
        ),
        "business_verification": "NOT_EVIDENCED",
        "gaps": [],
    }

    if ex is None:
        result["gaps"].append("No restoration exercise evidence supplied.")
        if backup_status == "EVIDENCED":
            result["gaps"].append(
                "Successful backup evidence does not demonstrate restoration."
            )
        return result
    if not isinstance(ex, dict):
        raise DataError(f"{sid}: exercise must be an object or null")

    exercise_id = ex.get("exercise_id")
    if not isinstance(exercise_id, str) or not exercise_id:
        raise DataError(f"{sid}: exercise.exercise_id is required")
    result["exercise_id"] = exercise_id

    disruption = _time(ex.get("disruption_at"), "exercise.disruption_at", sid)
    restored_as_of = _time(
        ex.get("restored_data_as_of"), "exercise.restored_data_as_of", sid
    )
    restore_completed = _time(
        ex.get("restore_completed_at"), "exercise.restore_completed_at", sid
    )
    business_verified = _time(
        ex.get("business_verified_at"), "exercise.business_verified_at", sid
    )
    verification_evidence = ex.get("business_verification_evidence_id")

    if disruption is None:
        result["gaps"].append("Exercise disruption/reference time is missing.")
    if restored_as_of is None:
        result["gaps"].append("Restored data point-in-time is missing.")
    if restore_completed is None:
        result["gaps"].append("Restore completion time is missing.")
    if (
        business_verified is None
        or not isinstance(verification_evidence, str)
        or not verification_evidence
    ):
        result["gaps"].append("Business-function verification evidence is incomplete.")
    else:
        result["business_verification"] = "EVIDENCED"

    for field, dt in (
        ("restored_data_as_of", restored_as_of),
        ("restore_completed_at", restore_completed),
        ("business_verified_at", business_verified),
    ):
        if (
            disruption is not None
            and dt is not None
            and dt < disruption
            and field != "restored_data_as_of"
        ):
            raise DataError(f"{sid}: {field} occurs before disruption_at")

    if disruption is not None and restored_as_of is not None:
        if restored_as_of > disruption:
            raise DataError(f"{sid}: restored_data_as_of occurs after disruption_at")
        rpo = _minutes(disruption, restored_as_of)
        result["observed_rpo_minutes"] = rpo
        result["rpo_result"] = (
            "MEETS_TARGET" if rpo <= target_rpo else "EXCEEDS_TARGET"
        )

    dep_results = ex.get("dependency_results", [])
    if not isinstance(dep_results, list):
        raise DataError(f"{sid}: exercise.dependency_results must be a list")
    by_id = {}
    for dep in dep_results:
        if not isinstance(dep, dict) or not isinstance(dep.get("dependency_id"), str):
            raise DataError(f"{sid}: invalid dependency result")
        did = dep["dependency_id"]
        if did in by_id:
            raise DataError(f"{sid}: duplicate dependency result {did}")
        by_id[did] = dep

    if dependencies:
        missing = []
        late = []
        for did in dependencies:
            dep = by_id.get(did)
            if not dep:
                missing.append(did)
                continue
            verified_at = _time(
                dep.get("verified_at"), f"dependency[{did}].verified_at", sid
            )
            evidence_id = dep.get("evidence_id")
            if (
                verified_at is None
                or not isinstance(evidence_id, str)
                or not evidence_id
            ):
                missing.append(did)
                continue
            if business_verified is not None and verified_at > business_verified:
                late.append(did)

        if missing:
            result["dependency_verification"] = "PARTIAL"
            result["gaps"].append(
                "Missing dependency verification: " + ", ".join(sorted(missing))
            )
        elif late:
            result["dependency_verification"] = "INCONSISTENT"
            result["gaps"].append(
                "Dependency verified after business-function verification: "
                + ", ".join(sorted(late))
            )
        else:
            result["dependency_verification"] = "EVIDENCED"

    if disruption is not None and business_verified is not None:
        rto = _minutes(business_verified, disruption)
        result["observed_rto_minutes"] = rto
        result["rto_result"] = (
            "MEETS_TARGET" if rto <= target_rto else "EXCEEDS_TARGET"
        )

    complete_evidence = (
        disruption is not None
        and restored_as_of is not None
        and restore_completed is not None
        and result["business_verification"] == "EVIDENCED"
        and result["dependency_verification"] in {"EVIDENCED", "NOT_APPLICABLE"}
    )
    result["restoration_status"] = (
        "DEMONSTRATED" if complete_evidence else "PARTIAL"
    )
    return result


def assess(data):
    seen = set()
    results = []
    for service in data["services"]:
        sid = service.get("service_id") if isinstance(service, dict) else None
        if sid in seen:
            raise DataError(f"duplicate service_id: {sid}")
        seen.add(sid)
        results.append(assess_service(service))

    known = set(seen)
    for result in results:
        unknown = sorted(set(result["dependencies"]) - known)
        if unknown:
            result["gaps"].append(
                "Dependency service records absent from assessment packet: "
                + ", ".join(unknown)
            )

    return {
        "assessment_id": data.get("assessment_id"),
        "synthetic": bool(data.get("synthetic", False)),
        "services": results,
        "summary": {
            "service_count": len(results),
            "backup_evidenced": sum(
                r["backup_status"] == "EVIDENCED" for r in results
            ),
            "restoration_demonstrated": sum(
                r["restoration_status"] == "DEMONSTRATED" for r in results
            ),
            "restoration_partial": sum(
                r["restoration_status"] == "PARTIAL" for r in results
            ),
            "restoration_not_demonstrated": sum(
                r["restoration_status"] == "NOT_DEMONSTRATED" for r in results
            ),
            "rpo_meets_target": sum(
                r["rpo_result"] == "MEETS_TARGET" for r in results
            ),
            "rto_meets_target": sum(
                r["rto_result"] == "MEETS_TARGET" for r in results
            ),
        },
        "interpretation_boundary": {
            "backup_completion_is_restoration_proof": False,
            "missing_evidence_is_failure": False,
            "live_restore_performed": False,
            "university_finding": False,
        },
    }


def write_csv(report, path: Path):
    fields = [
        "service_id", "name", "business_function", "target_rpo_minutes",
        "observed_rpo_minutes", "rpo_result", "target_rto_minutes",
        "observed_rto_minutes", "rto_result", "backup_status",
        "restoration_status", "dependency_verification",
        "business_verification", "exercise_id", "gaps",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report["services"]:
            out = {k: row.get(k) for k in fields}
            out["gaps"] = " | ".join(row["gaps"])
            writer.writerow(out)


def write_markdown(report, path: Path):
    lines = [
        "# Synthetic recovery evidence assessment",
        "",
        f"Assessment: `{report.get('assessment_id')}`",
        "",
        "| Service | Backup | Restoration | RPO | RTO | Dependencies | Business verification |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report["services"]:
        lines.append(
            f"| {r['name']} | {r['backup_status']} | {r['restoration_status']} | "
            f"{r['rpo_result']} | {r['rto_result']} | {r['dependency_verification']} | "
            f"{r['business_verification']} |"
        )
    lines += ["", "## Evidence gaps", ""]
    for r in report["services"]:
        lines.append(f"### {r['name']}")
        if r["gaps"]:
            lines.extend(f"- {gap}" for gap in r["gaps"])
        else:
            lines.append(
                "- No structural evidence gaps in the supplied synthetic exercise record."
            )
        lines.append("")
    lines += [
        "## Interpretation boundary",
        "",
        "- Backup completion is not treated as restoration proof.",
        "- Missing evidence remains unknown; it is not converted into a failed control.",
        "- No live backup or restoration action was performed.",
        "- This synthetic output is not a University finding.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("input_json", type=Path)
    p.add_argument("--json-output", type=Path)
    p.add_argument("--csv-output", type=Path)
    p.add_argument("--markdown-output", type=Path)
    args = p.parse_args(argv)
    try:
        report = assess(load(args.input_json))
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.json_output:
            args.json_output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        if args.csv_output:
            write_csv(report, args.csv_output)
        if args.markdown_output:
            write_markdown(report, args.markdown_output)
    except (DataError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

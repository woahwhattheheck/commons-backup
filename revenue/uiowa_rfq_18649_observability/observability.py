#!/usr/bin/env python3
"""Offline evidence assessor for UIOWA-065 service observability and objectives.

This tool evaluates supplied synthetic or engagement evidence. It never contacts
monitoring systems and never treats missing evidence as a negative observation.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VALID_KINDS = {"ratio", "latency", "count", "duration"}
VALID_STATUSES = {"SUPPORTED", "PARTIAL", "UNKNOWN"}


@dataclass(frozen=True)
class Finding:
    service_id: str
    objective_id: str
    status: str
    user_visible: bool | None
    issues: tuple[str, ...]
    questions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "objective_id": self.objective_id,
            "status": self.status,
            "user_visible": self.user_visible,
            "issues": list(self.issues),
            "questions": list(self.questions),
        }


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _list_of_strings(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ValueError(f"{field} must be a list of strings")
    return [v.strip() for v in value if v.strip()]


# Measurement periods are explicit instants; relative windows remain descriptive.
_PERIOD_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text or null")
    return value.strip() or None


def _finite_number(value: Any, field: str) -> int | float:
    # bool subclasses int; finite floats must be checked before comparisons.
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise ValueError(f"{field} must be a finite number, not a Boolean")
    return value


def _period(value: Any, field: str) -> datetime | None:
    text = _optional_text(value, field)
    if text is None:
        return None
    if _PERIOD_RE.fullmatch(text) is None:
        raise ValueError(f"{field} must be an ISO timestamp with explicit timezone")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid calendar timestamp") from exc


def _target_complete(target: Any, kind: str) -> bool:
    if not isinstance(target, dict):
        raise ValueError("target must be an object or null")
    operator = _optional_text(target.get("operator"), "target.operator")
    if operator is not None and operator not in {"<", "<=", ">", ">=", "=="}:
        raise ValueError("target.operator is unsupported")
    keys = [key for key in ("value", "value_ms", "value_seconds") if key in target]
    if len(keys) > 1:
        raise ValueError("target must specify only one scalar value and unit")
    if keys:
        key = keys[0]
        number = _finite_number(target[key], f"target.{key}")
        if number < 0:
            raise ValueError("target values must be nonnegative")
        if kind == "ratio" and (key != "value" or number > 1):
            raise ValueError("ratio target.value must lie between zero and one")
        if kind == "count" and (key != "value" or int(number) != number):
            raise ValueError("count target.value must be a whole number")
    if "percentile" in target:
        percentile = _finite_number(target["percentile"], "target.percentile")
        if kind != "latency" or not 0 < percentile <= 100:
            raise ValueError("target.percentile must lie in (0, 100] for latency")
    return operator is not None and len(keys) == 1


def assess_objective(service: dict[str, Any], objective: dict[str, Any]) -> Finding:
    if not isinstance(service, dict) or not isinstance(objective, dict):
        raise ValueError("service and objective must be objects")
    service_id = _required_text(service.get("service_id"), "service_id")
    objective_id = _required_text(objective.get("objective_id"), "objective_id")
    _required_text(objective.get("objective"), "objective")
    _required_text(objective.get("window"), "window")

    indicator = objective.get("indicator")
    if not isinstance(indicator, dict):
        raise ValueError(f"{objective_id}: indicator must be an object")

    kind = _required_text(indicator.get("kind"), "indicator.kind")
    if kind not in VALID_KINDS:
        raise ValueError(f"{objective_id}: unsupported indicator kind {kind!r}")

    issues: list[str] = []
    questions: list[str] = []

    user_visible = indicator.get("user_visible")
    if user_visible is not None and type(user_visible) is not bool:
        raise ValueError(f"{objective_id}: indicator.user_visible must be Boolean or null")
    if user_visible is None:
        issues.append("indicator_user_visibility_unknown")
        questions.append("Is this indicator tied to a user-visible journey, infrastructure, or an unresolved scope?")
    elif user_visible is False:
        issues.append("indicator_not_user_visible")
        questions.append(
            "What user-visible behavior does this indicator represent, or what additional indicator is needed?"
        )

    target = objective.get("target")
    if target is None:
        issues.append("target_missing")
        questions.append("What explicit objective target applies to this indicator and window?")
    elif not _target_complete(target, kind):
        issues.append("target_incomplete")
        questions.append("What operator and scalar target, with an unambiguous unit, apply to this window?")

    evidence = objective.get("measurement_evidence")
    if evidence is not None and not isinstance(evidence, dict):
        raise ValueError(f"{objective_id}: measurement_evidence must be an object or null")
    if evidence is None:
        issues.append("measurement_evidence_missing")
        questions.append("What retained evidence shows how this indicator is measured over the stated window?")
        evidence = {}

    if not _optional_text(evidence.get("source_ref"), "measurement_evidence.source_ref"):
        issues.append("measurement_source_missing")
    start = _period(evidence.get("period_start"), "measurement_evidence.period_start")
    end = _period(evidence.get("period_end"), "measurement_evidence.period_end")
    if start is None or end is None:
        issues.append("measurement_period_missing")
        questions.append("What exact measurement period supports the current interpretation?")
    elif start >= end:
        issues.append("measurement_period_invalid")
        questions.append("What non-empty, ordered measurement interval applies to the supplied evidence?")
    if not _optional_text(evidence.get("definition_ref"), "measurement_evidence.definition_ref"):
        issues.append("indicator_definition_missing")
        questions.append("Where is the calculation or event definition retained?")

    if kind == "ratio":
        numerator = evidence.get("numerator")
        denominator = evidence.get("denominator")
        if numerator is not None:
            _finite_number(numerator, f"{objective_id}: numerator")
        if denominator is not None:
            _finite_number(denominator, f"{objective_id}: denominator")
        if numerator is None or denominator is None:
            issues.append("ratio_components_missing")
            questions.append("What numerator and denominator define the reported ratio?")
        elif denominator <= 0:
            issues.append("invalid_denominator")
            questions.append("Why is the denominator zero or negative for this measurement window?")
        elif numerator < 0 or numerator > denominator:
            issues.append("invalid_ratio_counts")
            questions.append("Do the supplied numerator and denominator use the same population and window?")

    dependencies = objective.get("dependencies")
    if dependencies is None:
        issues.append("dependency_visibility_unknown")
        questions.append("Which upstream or downstream dependencies can affect this user-visible behavior?")
    elif not isinstance(dependencies, list):
        raise ValueError(f"{objective_id}: dependencies must be a list")
    else:
        for dep in dependencies:
            if not isinstance(dep, dict):
                raise ValueError(f"{objective_id}: each dependency must be an object")
            if not _optional_text(dep.get("name"), "dependency.name"):
                issues.append("dependency_name_missing")
            visibility = _optional_text(dep.get("visibility"), "dependency.visibility")
            if visibility not in {"visible", "partial", "unknown"}:
                issues.append("dependency_visibility_invalid")
            elif visibility == "unknown":
                issues.append("dependency_visibility_unknown")
            elif visibility == "partial":
                issues.append("dependency_visibility_partial")

    diagnostic_context = _list_of_strings(
        objective.get("diagnostic_context"), f"{objective_id}.diagnostic_context"
    )
    if not diagnostic_context:
        issues.append("diagnostic_context_missing")
        questions.append(
            "What retained context lets responders connect an objective breach to a useful investigation?"
        )

    decisions = objective.get("decision_evidence")
    if decisions is None:
        issues.append("decision_use_unknown")
        questions.append(
            "What review, prioritization, release, capacity, or remediation decision has used this evidence?"
        )
    elif not isinstance(decisions, list):
        raise ValueError(f"{objective_id}: decision_evidence must be a list")
    elif not decisions:
        issues.append("decision_use_not_evidenced")
        questions.append(
            "Is the objective reviewed in an operational or planning decision, and where is that decision retained?"
        )
    else:
        for decision in decisions:
            if not isinstance(decision, dict):
                raise ValueError(f"{objective_id}: each decision_evidence entry must be an object")
            decision_ref = _optional_text(decision.get("decision_ref"), "decision.decision_ref")
            outcome = _optional_text(decision.get("outcome"), "decision.outcome")
            if not decision_ref or not outcome:
                issues.append("decision_evidence_incomplete")

    if not evidence:
        status = "UNKNOWN"
    else:
        material = {
            "measurement_evidence_missing",
            "measurement_source_missing",
            "measurement_period_missing",
            "measurement_period_invalid",
            "indicator_definition_missing",
            "ratio_components_missing",
            "invalid_denominator",
            "invalid_ratio_counts",
        }
        status = "PARTIAL" if material.intersection(issues) else "SUPPORTED"

    return Finding(
        service_id=service_id,
        objective_id=objective_id,
        status=status,
        user_visible=user_visible,
        issues=tuple(sorted(set(issues))),
        questions=tuple(dict.fromkeys(questions)),
    )


def assess_packet(packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("packet must be an object")
    if "schema" in packet and packet["schema"] != "uiowa-065-observability-evidence-v1":
        raise ValueError("unsupported evidence schema")
    if "synthetic" in packet and type(packet["synthetic"]) is not bool:
        raise ValueError("synthetic must be Boolean when supplied")
    services = packet.get("services")
    if not isinstance(services, list) or not services:
        raise ValueError("services must be a non-empty list")

    findings: list[dict[str, Any]] = []
    service_ids: set[str] = set()
    for service in services:
        if not isinstance(service, dict):
            raise ValueError("each service must be an object")
        service_id = _required_text(service.get("service_id"), "service_id")
        if service_id in service_ids:
            raise ValueError(f"duplicate service_id {service_id!r}")
        service_ids.add(service_id)
        _required_text(service.get("service_name"), "service_name")
        objectives = service.get("objectives")
        if not isinstance(objectives, list) or not objectives:
            raise ValueError(f"{service['service_id']}: objectives must be a non-empty list")
        objective_ids: set[str] = set()
        for objective in objectives:
            finding = assess_objective(service, objective)
            if finding.objective_id in objective_ids:
                raise ValueError(f"{service_id}: duplicate objective_id {finding.objective_id!r}")
            objective_ids.add(finding.objective_id)
            findings.append(finding.as_dict())

    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    for finding in findings:
        counts[finding["status"]] += 1

    return {
        "schema": "uiowa-065-observability-assessment-v1",
        "scope": "supplied evidence only; no live telemetry queried",
        "finding_count": len(findings),
        "status_counts": counts,
        "findings": findings,
    }


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number {value}")


def load_packet(path: Path) -> dict[str, Any]:
    """Read one strict UTF-8/JSON packet; source is never rewritten."""
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_json_object, parse_constant=_reject_constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="JSON evidence packet")
    parser.add_argument("--out", type=Path, help="create a new JSON result; never overwrite")
    args = parser.parse_args(argv)

    try:
        result = assess_packet(load_packet(args.packet))
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.out:
            # Exclusive creation also refuses existing source aliases and symlinks.
            # A newly created partial file can remain on I/O failure; no success is reported.
            with args.out.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
        else:
            print(rendered, end="")
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"observability: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

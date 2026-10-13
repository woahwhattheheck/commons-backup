#!/usr/bin/env python3
"""Offline recovery-evidence assessment; never operates a deployment system."""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "uiowa-recovery/v1"
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}\Z")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
PHASES = ("failure", "detected", "decision", "start", "complete")
MODES = {"executed_rehearsal", "production_observation", "tabletop"}
STRATEGIES = {"rollback", "forward_repair", "undecided"}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def obj(value: Any, keys: str, where: str) -> None:
    require(isinstance(value, dict) and set(value) == set(keys.split()),
            f"{where}: expected exactly these fields: {keys}")


def text(value: Any, where: str, nullable: bool = False) -> None:
    require((nullable and value is None) or
            (isinstance(value, str) and bool(value.strip()) and len(value) <= 4000),
            f"{where}: expected nonempty text" + (" or null" if nullable else ""))


def identifier(value: Any, where: str) -> None:
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None,
            f"{where}: invalid identifier")


def choice(value: Any, values: set[str], where: str) -> None:
    require(isinstance(value, str) and value in values, f"{where}: expected one of {sorted(values)}")


def stamp(value: Any, where: str, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    require(isinstance(value, str) and TIMESTAMP.fullmatch(value) is not None,
            f"{where}: expected timezone-aware ISO timestamp")
    if not value.endswith("Z"):
        require(int(value[-5:-3]) <= 23 and int(value[-2:]) <= 59, f"{where}: invalid UTC offset")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{where}: invalid timestamp") from exc


def array(value: Any, where: str) -> None:
    require(isinstance(value, list), f"{where}: expected array")


def refs(value: Any, where: str) -> None:
    array(value, where)
    for ref in value:
        identifier(ref, where)
    require(len(set(value)) == len(value), f"{where}: duplicate evidence reference")


def validate(packet: Any) -> None:
    obj(packet, "schema synthetic as_of max_exercise_age_days evidence scenarios", "packet")
    require(packet["schema"] == SCHEMA, "packet: unsupported schema")
    require(type(packet["synthetic"]) is bool, "synthetic: expected boolean")
    stamp(packet["as_of"], "as_of")
    age = packet["max_exercise_age_days"]
    require(type(age) is int and 1 <= age <= 36500, "max_exercise_age_days: expected integer 1..36500")
    array(packet["scenarios"], "scenarios")
    array(packet["evidence"], "evidence")
    require(0 < len(packet["scenarios"]) <= 1000, "scenarios: expected 1..1000 records")
    require(len(packet["evidence"]) <= 20000, "evidence: too many records")
    scenario_ids, attempt_ids, evidence_ids = set(), set(), set()
    for s in packet["scenarios"]:
        obj(s, "id group title change_kind procedure_refs decision target_minutes attempts", "scenario")
        identifier(s["id"], "scenario.id")
        require(s["id"] not in scenario_ids, "duplicate scenario id")
        scenario_ids.add(s["id"])
        choice(s["group"], {"ESS", "RIS", "IAM"}, "scenario.group")
        text(s["title"], "scenario.title")
        choice(s["change_kind"], {"configuration", "application", "data_migration"}, "change_kind")
        refs(s["procedure_refs"], "procedure_refs")
        target = s["target_minutes"]
        require(target is None or (type(target) in (int, float) and target > 0
                                   and (type(target) is int or math.isfinite(target))),
                "target_minutes: expected finite positive number or null")
        d = s["decision"]
        obj(d, "strategy rollback_compatible owner_role rationale evidence_refs", "decision")
        choice(d["strategy"], STRATEGIES, "decision.strategy")
        require(d["rollback_compatible"] is None or type(d["rollback_compatible"]) is bool,
                "rollback_compatible: expected boolean or null")
        text(d["owner_role"], "decision.owner_role", True)
        text(d["rationale"], "decision.rationale", True)
        refs(d["evidence_refs"], "decision.evidence_refs")
        array(s["attempts"], "attempts")
        for a in s["attempts"]:
            obj(a, "id mode strategy environment times evidence_refs verification", "attempt")
            identifier(a["id"], "attempt.id")
            require(a["id"] not in attempt_ids, "duplicate attempt id")
            attempt_ids.add(a["id"])
            choice(a["mode"], MODES, "attempt.mode")
            choice(a["strategy"], STRATEGIES - {"undecided"}, "attempt.strategy")
            text(a["environment"], "attempt.environment")
            obj(a["times"], " ".join(PHASES), "attempt.times")
            for phase in PHASES:
                stamp(a["times"][phase], f"times.{phase}", True)
            refs(a["evidence_refs"], "attempt.evidence_refs")
            array(a["verification"], "verification")
            for check in a["verification"]:
                obj(check, "aspect result at evidence_refs", "verification")
                choice(check["aspect"], {"service", "data"}, "verification.aspect")
                choice(check["result"], {"pass", "fail", "unknown"}, "verification.result")
                stamp(check["at"], "verification.at", True)
                refs(check["evidence_refs"], "verification.evidence_refs")
    for e in packet["evidence"]:
        obj(e, "id scenario_id kind available recorded_at summary", "evidence")
        identifier(e["id"], "evidence.id")
        require(e["id"] not in evidence_ids, "duplicate evidence id")
        evidence_ids.add(e["id"])
        require(isinstance(e["scenario_id"], str) and e["scenario_id"] in scenario_ids,
                "evidence: unknown scenario_id")
        choice(e["kind"], {"procedure", "decision", "execution", "verification"}, "evidence.kind")
        require(type(e["available"]) is bool, "evidence.available: expected boolean")
        stamp(e["recorded_at"], "evidence.recorded_at")
        text(e["summary"], "evidence.summary")


def assess(packet: dict) -> dict:
    validate(packet)
    as_of = stamp(packet["as_of"], "as_of")
    ledger = {e["id"]: e for e in packet["evidence"]}
    reports = []
    for scenario in sorted(packet["scenarios"], key=lambda s: s["id"]):
        sid = scenario["id"]
        issues: set[str] = set()

        def linked(references, kind, notes, not_before=None):
            valid = bool(references)
            if not references:
                notes.add(f"missing_{kind}_evidence")
            for ref in references:
                e = ledger.get(ref)
                if e is None:
                    notes.add(f"unresolved_reference:{ref}")
                    valid = False
                    continue
                when = stamp(e["recorded_at"], "evidence.recorded_at")
                if e["scenario_id"] != sid or e["kind"] != kind:
                    notes.add(f"wrong_scope_or_kind:{ref}")
                    valid = False
                if not e["available"]:
                    notes.add(f"unavailable_evidence:{ref}")
                    valid = False
                if when > as_of or (not_before is not None and when < not_before):
                    notes.add(f"evidence_time_mismatch:{ref}")
                    valid = False
            return valid

        procedure = linked(scenario["procedure_refs"], "procedure", issues)
        decision = scenario["decision"]
        decision_ok = linked(decision["evidence_refs"], "decision", issues)
        if not decision["owner_role"] or not decision["rationale"] or decision["strategy"] == "undecided":
            issues.add("decision_incomplete")
            decision_ok = False
        if decision["strategy"] == "rollback" and decision["rollback_compatible"] is not True:
            issues.add("rollback_incompatible" if decision["rollback_compatible"] is False
                       else "rollback_compatibility_unknown")
            decision_ok = False
        attempts = []
        execution_order = []
        for attempt in sorted(scenario["attempts"], key=lambda a: a["id"]):
            notes: set[str] = set()
            times = {p: stamp(attempt["times"][p], p, True) for p in PHASES}
            known = [times[p] for p in PHASES if times[p] is not None]
            chronology = known == sorted(known) and all(t <= as_of for t in known)
            if not chronology:
                notes.add("invalid_execution_chronology")
            if len(known) < len(PHASES):
                notes.add("missing_timestamps")
            executed = attempt["mode"] != "tabletop"
            execution = linked(attempt["evidence_refs"], "execution", notes, times["complete"])
            if attempt["strategy"] != decision["strategy"]:
                notes.add("strategy_differs_from_current_decision")
            required = {"service"} | {c["aspect"] for c in attempt["verification"]}
            if scenario["change_kind"] == "data_migration":
                required.add("data")
            results, verified_times = {}, []
            for aspect in sorted(required):
                checks = [c for c in attempt["verification"] if c["aspect"] == aspect]
                status = "unknown"
                if not checks or any(c["at"] is None for c in checks):
                    notes.add(f"missing_or_undated_verification:{aspect}")
                else:
                    latest_time = max(stamp(c["at"], "at") for c in checks)
                    latest = [c for c in checks if stamp(c["at"], "at") == latest_time]
                    observations = {c["result"] for c in latest}
                    usable = [linked(c["evidence_refs"], "verification", notes, latest_time) for c in latest]
                    if len(observations) != 1:
                        notes.add(f"conflicting_verification:{aspect}")
                    elif times["complete"] is None or latest_time < times["complete"] or latest_time > as_of:
                        notes.add(f"verification_time_mismatch:{aspect}")
                    elif all(usable):
                        status = latest[0]["result"]
                        if status == "pass":
                            verified_times.append(latest_time)
                results[aspect] = status
                if status != "pass":
                    notes.add(f"verification_not_passed:{aspect}")
            supported = (executed and execution and chronology and len(known) == len(PHASES)
                         and all(value == "pass" for value in results.values())
                         and attempt["strategy"] == decision["strategy"])
            age_days = None
            if times["complete"] is not None and times["complete"] <= as_of:
                age_actual = (as_of - times["complete"]).total_seconds() / 86400
                age_days = round(age_actual, 6)
                if age_actual > packet["max_exercise_age_days"]:
                    notes.add("exercise_older_than_declared_window")
                    supported = False

            def minutes(start, end):
                if not chronology or start is None or end is None or end < start:
                    return None
                return round((end - start).total_seconds() / 60, 6)

            verification_complete = max(verified_times) if supported else None
            elapsed = minutes(times["failure"], verification_complete)
            elapsed_actual = ((verification_complete - times["failure"]).total_seconds() / 60
                              if verification_complete is not None else None)
            target = scenario["target_minutes"]
            target_result = ("not_set" if target is None else "unknown" if elapsed is None
                             else "met" if elapsed_actual <= target else "missed")
            result = {
                "id": attempt["id"], "mode": attempt["mode"], "strategy": attempt["strategy"],
                "demonstration": ("discussion_only" if not executed else "evidence_supported" if supported else "unverified"),
                "verification": results, "age_days": age_days,
                "minutes": {"detect": minutes(times["failure"], times["detected"]),
                            "decide_after_detection": minutes(times["detected"], times["decision"]),
                            "execute": minutes(times["start"], times["complete"]),
                            "failure_to_completion": minutes(times["failure"], times["complete"]),
                            "failure_to_verified_recovery": elapsed},
                "target_result": target_result, "issues": sorted(notes),
            }
            attempts.append(result)
            if executed:
                execution_order.append((times["failure"], result))
        latest_id = None
        if not execution_order:
            state = "discussion_only" if attempts else "documented_only" if procedure else "unknown"
            issues.add("no_executed_recovery_record")
        elif any(when is None for when, _ in execution_order):
            state = "gaps_in_supplied_records"
            issues.add("latest_execution_order_unknown")
        else:
            latest_when = max(when for when, _ in execution_order)
            latest_attempts = [r for when, r in execution_order if when == latest_when]
            if len(latest_attempts) != 1:
                state = "gaps_in_supplied_records"
                issues.add("ambiguous_latest_execution")
            else:
                latest = latest_attempts[0]
                latest_id = latest["id"]
                state = ("evidence_supported" if procedure and decision_ok and
                         latest["demonstration"] == "evidence_supported" else "gaps_in_supplied_records")
                if latest["demonstration"] != "evidence_supported":
                    issues.add("latest_execution_not_verified")
        if scenario["target_minutes"] is None:
            issues.add("recovery_target_not_supplied")
        reports.append({"id": sid, "group": scenario["group"], "title": scenario["title"],
                        "change_kind": scenario["change_kind"], "state": state,
                        "procedure_supported": procedure, "decision_supported": decision_ok,
                        "selected_strategy": decision["strategy"], "target_minutes": scenario["target_minutes"],
                        "latest_execution_id": latest_id, "issues": sorted(issues), "attempts": attempts})
    return {"schema": "uiowa-recovery-report/v1", "synthetic": packet["synthetic"], "as_of": packet["as_of"],
            "interpretation": "Supplied-record consistency only; not independent proof, a readiness certification, or deployment authorization.",
            "max_exercise_age_days": packet["max_exercise_age_days"],
            "counts": {"scenarios": len(reports), "evidence_supported": sum(r["state"] == "evidence_supported" for r in reports)},
            "scenarios": reports}


def markdown(report: dict) -> str:
    def clean(value):
        return html.escape(str(value)).replace("|", "\\|").replace("`", "\\`").replace("\n", " ").replace("\r", " ")
    lines = ["# Recovery evidence assessment", "", "**SYNTHETIC EXERCISE — NOT UNIVERSITY FINDINGS**" if report["synthetic"]
             else "**SUPPLIED RECORDS — SOURCE AUTHENTICITY NOT VERIFIED**", "", report["interpretation"],
             f"As of: {clean(report['as_of'])}. Declared exercise window: {report['max_exercise_age_days']} days.", ""]
    for s in report["scenarios"]:
        lines.extend([f"## {clean(s['id'])}: {clean(s['title'])}", "",
                      f"Group: {s['group']}. State: **{s['state']}**. Strategy: {s['selected_strategy']}.",
                      f"Latest executed attempt: {clean(s['latest_execution_id'])}. Draft target: {clean(s['target_minutes'])} minutes.", "",
                      "| Attempt | Mode | Demonstration | Service | Data | Failure to verified recovery (min) | Target |",
                      "| --- | --- | --- | --- | --- | --- | --- |"])
        for a in s["attempts"]:
            elapsed = a["minutes"]["failure_to_verified_recovery"]
            lines.append(f"| {clean(a['id'])} | {a['mode']} | {a['demonstration']} | {a['verification'].get('service', 'unknown')} | "
                         f"{a['verification'].get('data', 'not_required')} | {elapsed if elapsed is not None else 'unknown'} | {a['target_result']} |")
        notes = [(s["id"], note) for note in s["issues"]]
        notes += [(a["id"], note) for a in s["attempts"] for note in a["issues"]]
        lines.extend(["", "### Evidence follow-up", ""])
        lines.extend(f"- {clean(owner)}: {clean(note)}" for owner, note in notes)
        if not notes:
            lines.append("No consistency gaps detected in the supplied records. Inspect original evidence before drawing an assessment conclusion.")
        lines.append("")
    return "\n".join(lines)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-gaps", action="store_true", help="return 1 if a scenario lacks supported evidence")
    args = parser.parse_args(argv)
    temporary = None
    try:
        with args.input.open("rb") as source:
            raw = source.read(2 * 1024 * 1024 + 1)
        require(len(raw) <= 2 * 1024 * 1024, "input exceeds 2 MiB")
        packet = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=invalid_constant)
        report = assess(packet)
        rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n" if args.format == "json" else markdown(report) + "\n"
        if args.output:
            require(args.output.resolve() != args.input.resolve() and
                    not (args.output.exists() and os.path.samefile(args.input, args.output)),
                    "output must not overwrite input")
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=args.output.parent,
                                             prefix=".recovery-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(rendered)
            os.replace(temporary, args.output)
            temporary = None
        else:
            sys.stdout.write(rendered)
        return 1 if args.fail_on_gaps and report["counts"]["evidence_supported"] < report["counts"]["scenarios"] else 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"recovery: {exc}", file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())

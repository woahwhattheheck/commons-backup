"""Offline retry-aware recovery timing, not a recovery-readiness decision.

All records are caller-supplied. No network, application execution or deployment.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

SCHEMA = "uiowa-recovery-attempts/v1"
LIMIT = 2 * 1024 * 1024
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
LIMITATION = ("Caller-supplied record consistency and elapsed-time arithmetic only. "
              "No authenticity, recovery readiness, University finding, DORA benchmark, "
              "or authorization for a live action is established.")


class InputError(ValueError):
    """Malformed input, distinct from missing or contradictory evidence."""


def stamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise InputError("timestamp needs seconds and an explicit UTC offset")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise InputError("invalid calendar timestamp") from exc


def obj(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise InputError(label + ": fields do not match the documented contract")


def ident(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise InputError("invalid identifier")


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise InputError("expected nonblank text, at most 4000 characters")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise InputError("control character in text")


def choice(value, values):
    if not isinstance(value, str) or value not in values.split():
        raise InputError("invalid enum value")


def rows(value, label, maximum=1000):
    if not isinstance(value, list) or len(value) > maximum:
        raise InputError(label + ": expected bounded list")


def unique(values):
    if len(values) != len(set(values)):
        raise InputError("duplicate identifier or reference")


def refs(value):
    rows(value, "references")
    for item in value:
        ident(item)
    unique(value)


def validate(packet):
    obj(packet, "schema_version packet_id synthetic as_of evidence incidents", "packet")
    if packet["schema_version"] != SCHEMA or type(packet["synthetic"]) is not bool:
        raise InputError("wrong schema version or synthetic flag")
    ident(packet["packet_id"])
    if stamp(packet["as_of"]) is None:
        raise InputError("as_of cannot be null")
    rows(packet["evidence"], "evidence")
    for e in packet["evidence"]:
        obj(e, "id incident_id attempt_id kind observed_at locator excerpt", "evidence")
        ident(e["id"])
        ident(e["incident_id"])
        if e["attempt_id"] is not None:
            ident(e["attempt_id"])
        choice(e["kind"], "record procedure statement")
        if stamp(e["observed_at"]) is None:
            raise InputError("evidence observation time cannot be null")
        text(e["locator"])
        text(e["excerpt"])
    unique([e["id"] for e in packet["evidence"]])
    rows(packet["incidents"], "incidents", 100)
    for incident in packet["incidents"]:
        obj(incident, "id group service release_id context change_type detected_at detection_refs history_complete target_minutes attempts", "incident")
        for key in ("id", "release_id"):
            ident(incident[key])
        text(incident["service"])
        choice(incident["group"], "ESS RIS IAM")
        choice(incident["context"], "exercise production_event tabletop")
        choice(incident["change_type"], "configuration data_migration")
        stamp(incident["detected_at"])
        refs(incident["detection_refs"])
        if incident["history_complete"] is not None and type(incident["history_complete"]) is not bool:
            raise InputError("history_complete must be true, false, or null")
        target = incident["target_minutes"]
        if target is not None and (type(target) not in (int, float) or (type(target) is float and not math.isfinite(target)) or not 0 < target <= 525600):
            raise InputError("target_minutes must be null or finite number in (0, 525600]")
        rows(incident["attempts"], "attempts", 100)
        for attempt in incident["attempts"]:
            obj(attempt, "id strategy started_at finished_at outcome record_refs checks", "attempt")
            ident(attempt["id"])
            choice(attempt["strategy"], "rollback forward_repair")
            choice(attempt["outcome"], "completed failed unknown")
            stamp(attempt["started_at"])
            stamp(attempt["finished_at"])
            refs(attempt["record_refs"])
            rows(attempt["checks"], "checks", 100)
            for check in attempt["checks"]:
                obj(check, "id scope observed_at result evidence_refs", "check")
                ident(check["id"])
                ident(check["scope"])
                choice(check["result"], "passed failed unknown")
                stamp(check["observed_at"])
                refs(check["evidence_refs"])
            unique([c["id"] for c in attempt["checks"]])
        unique([a["id"] for a in incident["attempts"]])
    unique([i["id"] for i in packet["incidents"]])


def loads(content):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise InputError("duplicate JSON key: " + key)
            value[key] = item
        return value

    def constant(value):
        raise InputError("nonfinite JSON constant: " + value)

    if len(content.encode("utf-8")) > LIMIT:
        raise InputError("input exceeds 2 MiB")
    try:
        packet = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        raise InputError(str(exc)) from exc
    validate(packet)
    return packet


def elapsed(start, end):
    return None if start is None or end is None or end < start else (end - start).total_seconds() / 60


def replay(packet):
    """Preserve the incident clock across serial attempts; never infer a missing start."""
    validate(packet)
    as_of = stamp(packet["as_of"])
    evidence = {e["id"]: e for e in packet["evidence"]}
    result = []
    for incident in packet["incidents"]:
        diagnostics, attempts = [], []
        detection = stamp(incident["detected_at"])

        def note(code, attempt_id=None, evidence_id=None):
            item = {"code": code, "attempt_id": attempt_id, "evidence_id": evidence_id}
            if item not in diagnostics:
                diagnostics.append(item)

        def supported(references, aid):
            ok = bool(references)
            if not references:
                note("MISSING_RECORD", aid)
            for ref in references:
                e = evidence.get(ref)
                code = ("MISSING_REFERENCE" if e is None else
                        "NON_RECORD_REFERENCE" if e["kind"] != "record" else
                        "CROSS_INCIDENT_REFERENCE" if e["incident_id"] != incident["id"] else
                        "CROSS_ATTEMPT_REFERENCE" if e["attempt_id"] != aid else
                        "FUTURE_RECORD" if stamp(e["observed_at"]) > as_of else None)
                if code:
                    note(code, aid, ref)
                    ok = False
            return ok

        complete = incident["history_complete"] is True
        if not complete:
            note("HISTORY_INCOMPLETE_OR_UNKNOWN")
        detection_ok = supported(incident["detection_refs"], None)
        if detection is None:
            note("MISSING_DETECTION_TIME")
        elif detection > as_of:
            note("FUTURE_DETECTION_TIME")
            detection_ok = False
        chain_ok = complete and detection_ok and detection is not None
        previous_finish = detection
        scopes = {"technical_health", "business_behavior"}
        if incident["change_type"] == "data_migration":
            scopes.add("data_integrity")
        for attempt in incident["attempts"]:
            aid = attempt["id"]
            start, finish = stamp(attempt["started_at"]), stamp(attempt["finished_at"])
            timing_ok = start is not None and finish is not None
            if not timing_ok:
                note("INCOMPLETE_ATTEMPT_TIMING", aid)
            elif start > finish or finish > as_of or (previous_finish is not None and start < previous_finish):
                note("REVERSED_OVERLAPPING_OR_FUTURE_ATTEMPT", aid)
                timing_ok = False
            record_ok = supported(attempt["record_refs"], aid)
            chain_ok = chain_ok and timing_ok and record_ok
            previous_finish = finish
            required = scopes | {c["scope"] for c in attempt["checks"]}
            scope_states, endpoints = {}, []
            for scope in sorted(required):
                checks = [c for c in attempt["checks"] if c["scope"] == scope]
                invalid = not checks
                if not checks:
                    note("MISSING_VERIFICATION_SCOPE:" + scope, aid)
                dated = []
                for c in checks:
                    when = stamp(c["observed_at"])
                    if when is None or finish is None or when < finish or when > as_of:
                        note("INVALID_VERIFICATION_TIME:" + c["id"], aid)
                        invalid = True
                    else:
                        dated.append((when, c))
                if dated:
                    latest = max(t for t, _ in dated)
                    last = [c for t, c in dated if t == latest]
                    outcomes = {c["result"] for c in last}
                    # Every final record must support its declared outcome; ties cannot be selected conveniently.
                    support = [supported(c["evidence_refs"], aid) for c in last]
                    passed = outcomes == {"passed"} and all(support) and not invalid
                    state = "passed" if passed else "not_established"
                    if len(outcomes) > 1:
                        note("CONFLICTING_FINAL_CHECKS:" + scope, aid)
                    elif outcomes != {"passed"}:
                        note("FINAL_CHECK_NOT_PASSED:" + scope, aid)
                    if passed:
                        endpoints.append(latest)
                else:
                    state = "not_established"
                scope_states[scope] = state
            verified = max(endpoints) if endpoints and all(v == "passed" for v in scope_states.values()) else None
            if attempt["outcome"] != "completed" or not timing_ok or not record_ok:
                verified = None
            attempts.append({"id": aid, "strategy": attempt["strategy"], "outcome": attempt["outcome"],
                             "execution_minutes": elapsed(start, finish) if timing_ok and record_ok else None,
                             "verification": scope_states,
                             "verified_at": verified.isoformat() if verified else None,
                             "attempt_to_verified_minutes": elapsed(start, verified)})
        final = attempts[-1] if attempts else None
        end = stamp(final["verified_at"]) if final else None
        measured = chain_ok and end is not None and incident["context"] != "tabletop"
        total = elapsed(detection, end) if measured else None
        if total is None:
            status = "TABLETOP_TIMING_ONLY" if incident["context"] == "tabletop" else "TIMING_NOT_ESTABLISHED"
        else:
            status = "SUPPLIED_RECORDS_SUPPORT_ELAPSED_TIME"
        target = incident["target_minutes"]
        comparison = ("not_defined" if target is None else "not_measured" if total is None else
                      "within_target" if total <= target else "exceeded_target")
        result.append({"id": incident["id"], "group": incident["group"], "service": incident["service"],
                       "release_id": incident["release_id"], "context": incident["context"], "status": status,
                       "detected_at": incident["detected_at"], "verified_at": end.isoformat() if end and measured else None,
                       "incident_detection_to_verified_minutes": total,
                       "target_minutes": target, "target_comparison": comparison,
                       "attempts": attempts, "diagnostics": diagnostics})
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {"schema_version": "uiowa-recovery-attempt-report/v1", "packet_id": packet["packet_id"],
            "synthetic": packet["synthetic"], "as_of": packet["as_of"], "limitation": LIMITATION,
            "input_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "incidents": result,
            "evidence": deepcopy(packet["evidence"])}


def render(report):
    def literal(value):
        value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for char in "\\|`*_[]":
            value = value.replace(char, "\\" + char)
        return value.replace("\r", " ").replace("\n", " ")

    label = "SYNTHETIC REHEARSAL" if report["synthetic"] else "SUPPLIED RECORDS — NOT INDEPENDENTLY VERIFIED"
    lines = ["# Recovery-attempt timing", "", label, "", report["limitation"], "",
             "Elapsed time starts at the supplied original detection, includes failed attempts and waits,",
             "and ends at the final required recorded verification. Null means unknown, not zero.", "",
             "| Incident | Context | Detection to verified (min) | Target | Comparison |",
             "|---|---|---:|---:|---|"]
    for item in report["incidents"]:
        values = [item["id"], item["context"], item["incident_detection_to_verified_minutes"], item["target_minutes"], item["target_comparison"]]
        lines.append("| " + " | ".join("UNKNOWN" if v is None else literal(v) for v in values) + " |")
    for item in report["incidents"]:
        lines += ["", "## " + literal(item["id"]), "", literal(item["status"])]
        for a in item["attempts"]:
            lines.append("- " + literal(a))
        for d in item["diagnostics"]:
            lines.append("- " + literal(d))
    lines += ["", "## Supplied evidence locators", ""]
    for e in report["evidence"]:
        lines.append("- " + literal(e["id"]) + ": " + literal(e["locator"]) + " — " + literal(e["excerpt"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", help="Create a new file; existing files are never replaced")
    args = parser.parse_args(argv)
    try:
        with Path(args.packet).open("rb") as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise InputError("input exceeds 2 MiB")
        report = replay(loads(raw.decode("utf-8")))
        content = render(report) if args.format == "markdown" else json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            with Path(args.output).open("x", encoding="utf-8") as stream:
                stream.write(content)
        else:
            sys.stdout.write(content)
        return 0
    except (InputError, OSError, UnicodeError) as exc:
        print("recovery-attempts: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

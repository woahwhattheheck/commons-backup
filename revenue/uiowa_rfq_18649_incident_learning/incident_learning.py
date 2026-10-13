"""Read the original UIOWA-067 draft format without upgrading references to proof.

Reconciles ZZ-Sol's retained examples with ZZ-HELIODORE-67's evidence-linked kit.
The original command is restored; the original input is preserved, never rewritten.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .contract import moment, require, text
except ImportError:
    from contract import moment, require, text

LEGACY_SCHEMA = "uiowa-067-incident-learning-evidence-v1"


def optional_time(value, label, cutoff):
    if value is None or value == "":
        return None
    stamp = moment(value)
    require(stamp <= cutoff, label + " is later than evaluated_at")
    return stamp


def optional_reference(value, label):
    require(value is None or text(value), label + " must be nonempty text or null")
    return value


def assess_packet(packet: dict) -> dict:
    require(isinstance(packet, dict) and packet.get("schema") == LEGACY_SCHEMA, "unsupported legacy schema")
    require(type(packet.get("synthetic")) is bool, "synthetic must be a boolean")
    cutoff = moment(packet.get("evaluated_at"))
    records = packet.get("incidents")
    require(isinstance(records, list) and bool(records), "incidents must be a nonempty list")
    incident_ids, action_ids, results = set(), set(), []
    for record in records:
        require(isinstance(record, dict), "incident must be an object")
        iid = record.get("incident_id")
        require(text(iid) and iid not in incident_ids, "missing or duplicate incident_id")
        incident_ids.add(iid)
        require(text(record.get("service")), "service required")
        detected = optional_time(record.get("detected_at"), iid + ".detected_at", cutoff)
        restored = optional_time(record.get("restored_at"), iid + ".restored_at", cutoff)
        require(not detected or not restored or detected <= restored, "restoration precedes detection")
        timeline = record.get("timeline", [])
        require(isinstance(timeline, list), "timeline must be a list")
        prior = None
        for event in timeline:
            require(isinstance(event, dict) and text(event.get("event")), "timeline event needs text")
            stamp = optional_time(event.get("at"), "timeline event", cutoff)
            require(stamp is not None, "timeline event needs a timestamp")
            require(prior is None or prior <= stamp, "timeline is not chronologically ordered")
            prior = stamp
        postmortem = record.get("postmortem", {})
        require(isinstance(postmortem, dict), "postmortem must be an object")
        if "narrative" in postmortem:
            require(text(postmortem["narrative"]), "narrative must be nonempty text")
        for field in ("contributing_conditions", "evidence_refs", "lessons"):
            values = postmortem.get(field, [])
            require(isinstance(values, list) and all(text(v) for v in values), field + " must be a text list")
        actions = record.get("corrective_actions")
        require(isinstance(actions, list), "corrective_actions must be a list")
        output_actions = []
        for action in actions:
            require(isinstance(action, dict), "action must be an object")
            aid = action.get("action_id")
            require(text(aid) and aid not in action_ids, "missing or duplicate action_id")
            action_ids.add(aid)
            require(text(action.get("description")), "action description required")
            owner = action.get("owner_role")
            require(owner is None or text(owner), "owner_role must be text or null")
            due_raw = action.get("due_at")
            due = None if due_raw in (None, "") else moment(due_raw)
            completed = optional_time(action.get("completed_at"), aid + ".completed_at", cutoff)
            completion_ref = optional_reference(action.get("completion_evidence_ref"), "completion_evidence_ref")
            effect_ref = optional_reference(action.get("effectiveness_evidence_ref"), "effectiveness_evidence_ref")
            changed = action.get("changed_approach")
            require(changed is None or isinstance(changed, dict), "changed_approach must be an object or null")
            issues = []
            if owner is None:
                issues.append("owner_role_unknown")
            if due is None:
                issues.append("due_time_unknown")
            if completed:
                state = "COMPLETION_REFERENCED" if completion_ref else "COMPLETION_UNVERIFIED"
                if changed is not None:
                    issues.append("completion_and_replacement_both_recorded")
            elif changed is not None:
                valid = all(text(changed.get(k)) for k in ("decision_ref", "rationale", "replacement_action"))
                state = "CHANGE_REFERENCED" if valid else "CHANGE_UNVERIFIED"
            elif due is None:
                state = "UNKNOWN"
            else:
                state = "OVERDUE" if due < cutoff else "OPEN"
            if effect_ref and not completed:
                issues.append("effectiveness_reference_without_recorded_completion")
            output_actions.append({"action_id": aid, "record_state": state,
                "completion_reference_present": bool(completion_ref),
                "effectiveness_reference_present": bool(effect_ref),
                "implementation_verification": "NOT_ESTABLISHED_FROM_REFERENCE_ONLY_FORMAT",
                "effectiveness_verification": "NOT_ESTABLISHED_FROM_REFERENCE_ONLY_FORMAT",
                "questions": ["Open the cited implementation and later verification records; confirm their scope and dates."],
                "issues": issues, "supplied_record": action})
        results.append({"incident_id": iid, "service": record["service"],
            "timeline_state": "DESCRIBED" if timeline else "UNKNOWN",
            "reported_detection_to_restoration_minutes":
                round((restored - detected).total_seconds() / 60, 3) if detected and restored else None,
            "measured_restoration_minutes": None,
            "learning_evidence": "REFERENCE_ONLY_REVIEW_REQUIRED",
            "actions": output_actions, "supplied_record": record})
    return {"schema": "uiowa-067-legacy-observations/v2", "synthetic": packet["synthetic"],
        "evaluated_at": packet["evaluated_at"], "incidents": results,
        "limits": ["Preserves the original draft's records and identifiers. References are not resolved source artifacts.",
                   "No supplied field identifies group membership, independent verification, exposure or comparable measurement windows.",
                   "Recorded timestamps support a reported interval only, not an independently measured recovery claim.",
                   "Use fixture.py and report.py for the richer evidence-linked packet; do not silently infer the missing fields."]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.out and args.out.resolve() == args.packet.resolve():
            raise ValueError("output must not overwrite the input packet")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, "duplicate JSON key: " + key)
                result[key] = value
            return result
        data = json.loads(args.packet.read_text(encoding="utf-8"), object_pairs_hook=unique)
        output = json.dumps(assess_packet(data), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.out:
            # Refuse replacement of any existing file, including unrelated work.
            with args.out.open("x", encoding="utf-8") as destination:
                destination.write(output)
        else:
            sys.stdout.write(output)
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        print("Invalid legacy packet or output: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

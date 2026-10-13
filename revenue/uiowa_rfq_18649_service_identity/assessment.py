#!/usr/bin/env python3
"""Offline, metadata-only service-identity practice assessment (UIOWA-054).

No network, credential processing, access mutation, or compliance decisions.
Python 3.10+; standard library only. Dates describe supplied records, not reality.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "service-identity-inventory/v1"
REPORT_SCHEMA = "service-identity-assessment/v1"
MAX_BYTES = 2_000_000
MAX_ROWS = 5_000
ASPECTS = {"ownership", "purpose", "privilege", "renewal", "continuity", "transition", "dependency", "retirement"}
KINDS = {"record", "demonstration", "interview", "procedure"}
STATES = {"observed", "reported", "documented", "unknown", "stale", "contradictory", "follow_up", "not_applicable"}


class InputError(ValueError):
    """Invalid metadata; messages deliberately do not echo supplied values."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def fields(value: Any, expected: set[str], where: str) -> None:
    require(isinstance(value, dict), f"{where}: expected object")
    require(set(value) == expected, f"{where}: missing or unexpected fields; use the documented metadata contract")


def text(value: Any, where: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 500, f"{where}: expected nonempty metadata text, at most 500 characters")
    require(all(ord(c) >= 32 and ord(c) != 127 for c in value), f"{where}: control characters are not permitted")


def ident(value: Any, where: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value) is not None, f"{where}: invalid metadata identifier")


def day(value: Any, where: str, nullable: bool = False) -> date | None:
    if nullable and value is None:
        return None
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, f"{where}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InputError(f"{where}: invalid calendar date") from None


def rows(value: Any, where: str) -> list[dict[str, Any]]:
    require(isinstance(value, list) and len(value) <= MAX_ROWS, f"{where}: expected a list of at most {MAX_ROWS} rows")
    seen: set[str] = set()
    for row in value:
        require(isinstance(row, dict), f"{where}: expected object rows")
        ident(row.get("id"), f"{where}.id")
        require(row["id"] not in seen, f"{where}: duplicate identifier")
        seen.add(row["id"])
    return value


def refs(value: Any, known: set[str], where: str) -> None:
    require(isinstance(value, list) and len(value) <= MAX_ROWS, f"{where}: expected identifier list")
    for item in value:
        ident(item, where)
    require(len(value) == len(set(value)), f"{where}: duplicate reference")
    require(set(value) <= known, f"{where}: unresolved reference")


def validate(data: Any) -> dict[str, Any]:
    fields(data, {"schema", "as_of", "evidence_max_age_days", "owners", "services", "identities", "evidence"}, "inventory")
    require(data["schema"] == SCHEMA, "inventory: unsupported schema")
    as_of = day(data["as_of"], "as_of")
    age = data["evidence_max_age_days"]
    require(type(age) is int and 1 <= age <= 3650, "evidence_max_age_days: expected integer from 1 to 3650")
    owners = rows(data["owners"], "owners")
    services = rows(data["services"], "services")
    identities = rows(data["identities"], "identities")
    evidence = rows(data["evidence"], "evidence")
    owner_ids, service_ids, identity_ids = ({r["id"] for r in group} for group in (owners, services, identities))
    for owner in owners:
        fields(owner, {"id", "role", "status", "departure_on"}, "owner")
        text(owner["role"], "owner.role")
        require(owner["status"] in ("active", "departed"), "owner: invalid status")
        departed = day(owner["departure_on"], "owner.departure_on", True)
        require((owner["status"] == "departed" and departed is not None and departed <= as_of) or (owner["status"] == "active" and departed is None), "owner: status and departure date disagree")
    for service in services:
        fields(service, {"id", "group", "criticality", "depends_on"}, "service")
        require(service["group"] in ("ESS", "RIS", "IAM"), "service: invalid group")
        require(service["criticality"] in ("low", "medium", "high"), "service: invalid criticality")
        refs(service["depends_on"], service_ids, "service.depends_on")
        require(service["id"] not in service["depends_on"], "service: direct self-dependency")
    identity_fields = {"id", "status", "purpose", "privilege_rationale", "owner_id", "continuity_owner_id", "consumer_ids", "consumer_inventory_complete", "review_due_on", "expires_on", "owner_transition"}
    for identity in identities:
        fields(identity, identity_fields, "identity")
        require(identity["status"] in ("active", "retiring", "retired"), "identity: invalid status")
        text(identity["purpose"], "identity.purpose", True)
        text(identity["privilege_rationale"], "identity.privilege_rationale", True)
        for key in ("owner_id", "continuity_owner_id"):
            ident(identity[key], f"identity.{key}", True)
            require(identity[key] is None or identity[key] in owner_ids, f"identity.{key}: unresolved reference")
        refs(identity["consumer_ids"], service_ids, "identity.consumer_ids")
        complete = identity["consumer_inventory_complete"]
        require(complete is None or type(complete) is bool, "consumer_inventory_complete: expected boolean or null")
        day(identity["review_due_on"], "identity.review_due_on", True)
        day(identity["expires_on"], "identity.expires_on", True)
        transition = identity["owner_transition"]
        if transition is not None:
            fields(transition, {"from_owner_id", "to_owner_id", "effective_on"}, "transition")
            for key in ("from_owner_id", "to_owner_id"):
                ident(transition[key], f"transition.{key}")
                require(transition[key] in owner_ids, "transition: unresolved owner")
            require(transition["from_owner_id"] != transition["to_owner_id"], "transition: owners must differ")
            require(day(transition["effective_on"], "transition.effective_on") <= as_of, "transition: future effective change is not an observed owner change")
    for item in evidence:
        fields(item, {"id", "identity_id", "aspect", "kind", "result", "observed_on", "owner_id", "reference"}, "evidence")
        ident(item["identity_id"], "evidence.identity_id")
        require(item["identity_id"] in identity_ids, "evidence: unresolved identity")
        require(isinstance(item["aspect"], str) and item["aspect"] in ASPECTS, "evidence: invalid aspect")
        require(isinstance(item["kind"], str) and item["kind"] in KINDS, "evidence: invalid kind")
        require(item["result"] in ("supports", "contradicts", "unknown"), "evidence: invalid result")
        require(day(item["observed_on"], "evidence.observed_on") <= as_of, "evidence: future observations are not evidence")
        ident(item["owner_id"], "evidence.owner_id", True)
        require(item["owner_id"] is None or item["owner_id"] in owner_ids, "evidence: unresolved owner")
        text(item["reference"], "evidence.reference")
    return data


def load(path: Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, "JSON: duplicate object key")
            result[key] = value
        return result
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "input exceeds two-million-byte metadata limit")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(InputError("JSON: non-finite number")))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise InputError("input must be valid UTF-8 JSON without excessive nesting") from None
    return validate(data)


def normalized(data: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(data)
    for key in ("owners", "services", "identities", "evidence"):
        value[key].sort(key=lambda row: row["id"])
    for service in value["services"]:
        service["depends_on"].sort()
    for identity in value["identities"]:
        identity["consumer_ids"].sort()
    return value


def canonical(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def impact(consumer_ids: list[str], services: dict[str, dict[str, Any]]) -> list[str]:
    """Reverse dependency closure; cycles are valid metadata and terminate."""
    reverse: dict[str, set[str]] = {key: set() for key in services}
    for key, service in services.items():
        for dependency in service["depends_on"]:
            reverse[dependency].add(key)
    found: set[str] = set()
    pending = list(consumer_ids)
    while pending:
        current = pending.pop()
        if current not in found:
            found.add(current)
            pending.extend(reverse[current] - found)
    return sorted(found)


def assess(data: dict[str, Any]) -> dict[str, Any]:
    data = normalized(validate(data))
    as_of = day(data["as_of"], "as_of")
    cutoff = as_of - timedelta(days=min(data["evidence_max_age_days"], (as_of - date.min).days))
    owners = {row["id"]: row for row in data["owners"]}
    services = {row["id"]: row for row in data["services"]}
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in data["evidence"]:
        indexed.setdefault((row["identity_id"], row["aspect"]), []).append(row)
    results: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for item in data["identities"]:
        controls: dict[str, dict[str, Any]] = {}
        transition = item["owner_transition"]
        changed_on = day(transition["effective_on"], "effective_on") if transition else date.min
        owner = owners.get(item["owner_id"])
        backup = owners.get(item["continuity_owner_id"])
        affected = impact(item["consumer_ids"], services)

        def control(aspect: str, owner_id: str | None = None, demonstrated: bool = False) -> dict[str, Any]:
            observations = indexed.get((item["id"], aspect), [])
            eligible = [e for e in observations if (owner_id is None or e["owner_id"] == owner_id)]
            lower = max(cutoff, changed_on) if aspect in {"ownership", "transition", "continuity"} else cutoff
            fresh = [e for e in eligible if day(e["observed_on"], "observed_on") >= lower]
            # Contradictions never silently expire; the inventory curator must reconcile them.
            if any(e["result"] == "contradicts" for e in observations):
                state, reason = "contradictory", "Conflicting supplied records require explicit reconciliation."
            else:
                positive = [e for e in fresh if e["result"] == "supports"]
                direct = {"demonstration"} if demonstrated else {"record", "demonstration"}
                if any(e["kind"] in direct for e in positive):
                    state, reason = "observed", "Supported by applicable supplied records; authenticity is not independently verified."
                elif any(e["kind"] in {"record", "interview"} for e in positive):
                    state, reason = "reported", ("Reported or recorded, but no applicable demonstration supports continuity." if demonstrated else "An interview report is not a direct practice record.")
                elif any(e["kind"] == "procedure" for e in positive):
                    state, reason = "documented", "A written procedure is not evidence that the practice occurred."
                elif eligible and not fresh:
                    state, reason = "stale", "Evidence predates the freshness window or effective ownership change."
                else:
                    state, reason = "unknown", "No applicable supporting evidence was supplied."
            return {"state": state, "reason": reason, "evidence_ids": [e["id"] for e in observations], "applicable_evidence_ids": [e["id"] for e in fresh]}

        def set_control(aspect: str, state: str, reason: str) -> None:
            current = controls.setdefault(aspect, control(aspect))
            if current["state"] != "contradictory":
                current.update(state=state, reason=reason)

        controls["ownership"] = control("ownership", item["owner_id"])
        if owner is None:
            set_control("ownership", "unknown", "No accountable owner is identified in the supplied inventory.")
        elif owner["status"] != "active":
            set_control("ownership", "follow_up", "The listed accountable owner is recorded as departed.")
        for aspect, key in (("purpose", "purpose"), ("privilege", "privilege_rationale")):
            controls[aspect] = control(aspect)
            if item[key] is None:
                set_control(aspect, "unknown", "Required rationale metadata is absent; do not infer it from the identity name.")
        controls["transition"] = control("transition", transition["to_owner_id"] if transition else None)
        if transition is None:
            set_control("transition", "not_applicable", "No ownership change is recorded in this inventory; this is not a complete history claim.")
        elif transition["to_owner_id"] != item["owner_id"]:
            set_control("transition", "contradictory", "The transition destination and current accountable owner disagree.")
        controls["continuity"] = control("continuity", item["continuity_owner_id"], True)
        if backup is None:
            set_control("continuity", "unknown", "No continuity role is identified.")
        elif backup["status"] != "active" or backup["id"] == item["owner_id"]:
            set_control("continuity", "follow_up", "Continuity requires a distinct, active role and evidence of a usable handoff.")
        controls["renewal"] = control("renewal")
        review = day(item["review_due_on"], "review_due_on", True)
        expires = day(item["expires_on"], "expires_on", True)
        if review is None:
            set_control("renewal", "unknown", "No review due date is supplied; confirm the applicable lifecycle rule.")
        elif review < as_of and item["status"] != "retired":
            set_control("renewal", "follow_up", "The supplied review due date has passed; this does not prove access is inappropriate.")
        if expires is not None and expires < as_of and item["status"] != "retired":
            set_control("renewal", "contradictory", "Recorded active/retiring status conflicts with the elapsed expiry date; confirm actual state.")
        controls["dependency"] = control("dependency")
        if item["consumer_inventory_complete"] is not True:
            set_control("dependency", "unknown", "Consumer inventory is incomplete or its coverage is unknown; an empty list is not clearance.")
        controls["retirement"] = control("retirement")
        if item["status"] == "active":
            set_control("retirement", "not_applicable", "No retirement is currently recorded; this does not authorize indefinite retention.")
        elif item["consumer_ids"]:
            set_control("retirement", "contradictory" if item["status"] == "retired" else "follow_up", "Declared consumers remain; reconcile dependencies before treating retirement as supported.")
        elif controls["dependency"]["state"] != "observed":
            set_control("retirement", "unknown", "Dependency removal and inventory coverage are not supported by applicable records.")

        for aspect, result in sorted(controls.items()):
            if result["state"] in {"observed", "not_applicable"}:
                continue
            role = owner["role"] if owner and owner["status"] == "active" else "Service portfolio owner"
            next_step = {
                "ownership": "Confirm an accountable organizational role and link current acceptance evidence.",
                "purpose": "Record service purpose and reconcile it with a representative usage record.",
                "privilege": "Record why the supplied privilege scope is needed; review with service and identity specialists.",
                "transition": "Reconcile current ownership and obtain receiving-role acceptance after the effective change.",
                "continuity": "Rehearse the metadata/runbook handoff with the continuity role; retain the result without credential values.",
                "renewal": "Confirm review/expiry interpretation and record the human renewal or retirement decision.",
                "dependency": "Reconcile shared consumers with service owners and record inventory coverage and removals.",
                "retirement": "Review remaining consumers and decommission evidence; this report performs no retirement."
            }[aspect]
            actions.append({"id": f"{item['id']}:{aspect}", "identity_id": item["id"], "aspect": aspect,
                            "state": result["state"], "priority": "high" if result["state"] in {"contradictory", "follow_up"} else "normal",
                            "accountable_role": role, "effort": "medium" if aspect in {"continuity", "dependency", "retirement"} else "small",
                            "depends_on": affected if aspect in {"dependency", "continuity", "retirement", "renewal"} else [], "next_step": next_step})
        results.append({"identity_id": item["id"], "declared_status": item["status"], "owner_id": item["owner_id"],
                        "continuity_owner_id": item["continuity_owner_id"], "direct_consumers": sorted(item["consumer_ids"]),
                        "potentially_affected_services": affected, "affected_groups": sorted({services[s]["group"] for s in affected}),
                        "shared_direct_dependency": len(item["consumer_ids"]) > 1,
                        "expiry_days_remaining": (expires - as_of).days if expires else None,
                        "controls": dict(sorted(controls.items()))})
    counts = Counter(control["state"] for result in results for control in result["controls"].values())
    return {"schema": REPORT_SCHEMA, "as_of": data["as_of"], "input_sha256": hashlib.sha256(canonical(data).encode()).hexdigest(),
            "scope": "Supplied metadata only; synthetic examples are not University findings. Potential impact is a declared dependency closure, not measured runtime exposure.",
            "access_changes_authorized": False, "compliance_verdict": None,
            "summary": {"identities": len(results), "services": len(services), "evidence_records": len(data["evidence"]),
                        "control_states": {state: counts[state] for state in sorted(STATES)}},
            "identities": results, "actions": sorted(actions, key=lambda a: (a["priority"] != "high", a["id"]))}


def markdown(report: dict[str, Any]) -> str:
    def safe(value: Any) -> str:
        return html.escape(str(value), quote=True).replace("|", "&#124;").replace("`", "&#96;").replace("\n", " ").replace("\r", " ")
    lines = ["# Service-identity practice assessment", "", f"As of: {report['as_of']}", "", report["scope"], "",
             "**Review instrument only. No access change, retirement, compliance certification or customer finding is authorized.**", "",
             f"Normalized input SHA-256: `{report['input_sha256']}`", "",
             "| Identity | Control | Evidence state | Reason | Evidence IDs |", "|---|---|---|---|---|"]
    for identity in report["identities"]:
        for aspect, control in identity["controls"].items():
            lines.append("| " + " | ".join(safe(v) for v in (identity["identity_id"], aspect, control["state"], control["reason"], ", ".join(control["evidence_ids"]) or "None supplied")) + " |")
    lines += ["", "## Declared dependency impact", "", "Direction: if A depends on B, an identity consumed by B may affect A. Cycles are traversed once.", ""]
    for identity in report["identities"]:
        lines.append(f"- **{safe(identity['identity_id'])}**: {safe(', '.join(identity['potentially_affected_services']) or 'No declared consumers; coverage must still be checked')}.")
    lines += ["", "## Follow-up work", "", "Effort bands are planning placeholders: small = one-role record review; medium = coordinated evidence collection or rehearsal. Estimate actual hours with the team.", "", "| Identity / aspect | Priority | Role | Effort | Dependency coordination | Next step |", "|---|---|---|---|---|---|"]
    for action in report["actions"]:
        lines.append("| " + " | ".join(safe(v) for v in (action["id"], action["priority"], action["accountable_role"], action["effort"], ", ".join(action["depends_on"]) or "None specified", action["next_step"])) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="Create a new report file; never overwrite an existing file")
    args = parser.parse_args(argv)
    try:
        report = assess(load(args.inventory))
        rendered = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n" if args.format == "json" else markdown(report)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (InputError, OSError) as error:
        # OSError strings can contain sensitive local paths; keep those out of logs.
        sys.stderr.write(f"Invalid inventory: {error}\n" if isinstance(error, InputError) else "Input/output failed; check file access and choose a new output path.\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

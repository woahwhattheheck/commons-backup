#!/usr/bin/env python3
"""Validate and render UIOWA-050 development-to-operations handoff packets.

No third-party dependencies. A successful validation means the packet is
structurally reviewable; it does not mean the change is approved or production-ready.
"""

from __future__ import annotations

import argparse
import html
import math
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ALLOWED_CHANGE_TYPES = {"planned_release", "urgent_maintenance"}
ALLOWED_GROUPS = {"ESS", "RIS", "IAM"}
READINESS_STATES = {"complete", "pending", "deferred_with_owner"}
DOC_STATES = {"updated", "reviewed_no_change", "pending", "deferred_with_owner"}
OPEN_SEVERITIES = {"blocking", "non_blocking"}

REQUIRED_TOP = (
    "metadata",
    "user_facing_behavior",
    "known_limitations",
    "requirements",
    "acceptance_evidence",
    "support_readiness",
    "documentation_updates",
    "operational_needs",
    "rollback_and_recovery",
    "open_items",
)

REQUIRED_METADATA = (
    "packet_version",
    "change_id",
    "change_type",
    "service",
    "group",
    "summary",
    "requested_behavior",
    "implementation_owner_role",
    "support_owner_role",
    "release_trigger",
    "synthetic",
)


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _id_map(items: Any, prefix: str, findings: list[Finding]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        findings.append(Finding("ERROR", "EXPECTED_LIST", prefix, "Expected a list."))
        return result

    for index, item in enumerate(items):
        path = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            findings.append(Finding("ERROR", "EXPECTED_OBJECT", path, "Expected an object."))
            continue
        item_id = item.get("id")
        if not _present(item_id):
            findings.append(Finding("ERROR", "MISSING_ID", path, "Item must have a non-empty id."))
            continue
        item_id = str(item_id)
        if item_id in result:
            findings.append(Finding("ERROR", "DUPLICATE_ID", path, f"Duplicate id: {item_id}"))
            continue
        result[item_id] = item
    return result


def _require_fields(
    obj: Any,
    fields: Iterable[str],
    path: str,
    findings: list[Finding],
    level: str = "ERROR",
) -> None:
    if not isinstance(obj, dict):
        findings.append(Finding("ERROR", "EXPECTED_OBJECT", path, "Expected an object."))
        return
    for field in fields:
        if not _present(obj.get(field)):
            findings.append(
                Finding(level, "MISSING_FIELD", f"{path}.{field}", "Required information is missing.")
            )



def _shape_findings(packet: dict[str, Any]) -> list[Finding]:
    """Check types before enum membership, ID lookup, or iteration.

    Missing/null information is left to the existing gap rules, except for
    containers and the required Boolean synthetic flag. Do not coerce IDs,
    string booleans, or malformed references into apparently valid records.
    """
    findings: list[Finding] = []
    text_fields = {
        "metadata": tuple(f for f in REQUIRED_METADATA if f != "synthetic") + ("urgency_reason",),
        "user_facing_behavior": ("before", "after", "communications"),
        "rollback_and_recovery": ("rollback_trigger", "rollback_method", "data_recovery_notes", "owner_role"),
        "known_limitations": ("id", "description", "affected_scope", "owner_role", "follow_up_trigger", "mitigation"),
        "requirements": ("id", "statement", "acceptance_criteria"),
        "acceptance_evidence": ("id", "kind", "locator", "result", "notes"),
        "support_readiness": ("id", "item", "owner_role", "status", "locator", "follow_up_trigger"),
        "operational_needs": ("id", "kind", "need", "owner_role", "status", "verification", "follow_up_trigger"),
        "documentation_updates": ("document", "owner_role", "status", "locator", "follow_up_trigger"),
        "open_items": ("id", "severity", "question", "owner_role", "resolution_trigger"),
    }
    objects = {"metadata", "user_facing_behavior", "rollback_and_recovery"}
    for section in REQUIRED_TOP:
        value = packet[section]
        if section in objects:
            if not isinstance(value, dict):
                findings.append(Finding("ERROR", "EXPECTED_OBJECT", section, "Expected an object."))
                continue
            rows = [(section, value)]
        else:
            if not isinstance(value, list):
                findings.append(Finding("ERROR", "EXPECTED_LIST", section, "Expected a list."))
                continue
            rows = [(f"{section}[{i}]", item) for i, item in enumerate(value)]
        for path, item in rows:
            if not isinstance(item, dict):
                findings.append(Finding("ERROR", "EXPECTED_OBJECT", path, "Expected an object."))
                continue
            for field in text_fields[section]:
                if field in item and item[field] is not None and not isinstance(item[field], str):
                    findings.append(Finding("ERROR", "EXPECTED_STRING", f"{path}.{field}", "Expected text, not a coerced value."))
            if section == "metadata" and "synthetic" in item and type(item["synthetic"]) is not bool:
                findings.append(Finding("ERROR", "EXPECTED_BOOLEAN", f"{path}.synthetic", "Expected JSON true or false."))
            if section == "requirements":
                for field in ("acceptance_evidence", "support_readiness"):
                    refs = item.get(field)
                    if refs is None:
                        continue  # Missing linkage remains an evidence gap.
                    if not isinstance(refs, list):
                        findings.append(Finding("ERROR", "EXPECTED_LIST", f"{path}.{field}", "Expected an array of reference IDs."))
                        continue
                    for index, ref in enumerate(refs):
                        if not isinstance(ref, str) or not ref.strip():
                            findings.append(Finding("ERROR", "INVALID_REFERENCE_ID", f"{path}.{field}[{index}]", "Reference IDs must be non-empty strings."))
            if section == "user_facing_behavior":
                users = item.get("affected_users")
                if users is not None and not (isinstance(users, str) or
                        isinstance(users, list) and all(isinstance(user, str) and user.strip() for user in users)):
                    findings.append(Finding("ERROR", "INVALID_AFFECTED_USERS", f"{path}.affected_users", "Expected text or a list of non-empty persona descriptions."))
    return findings


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _cell(value: Any) -> str:
    """Keep a supplied value in one readable Markdown table cell."""
    text = "not recorded" if value is None else str(value)
    return (html.escape(text, quote=False).replace("\\", "\\\\")
            .replace("|", "\\|").replace("\r\n", "\n").replace("\r", "\n")
            .replace("\n", "<br>"))


def _reference_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return "not recorded" if value is None else f"invalid reference list: {value}"


def validate(packet: Any) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(packet, dict):
        return [Finding("ERROR", "EXPECTED_OBJECT", "$", "Packet root must be an object.")]

    for key in REQUIRED_TOP:
        if key not in packet:
            findings.append(Finding("ERROR", "MISSING_SECTION", key, "Required section is absent."))

    if any(f.code == "MISSING_SECTION" for f in findings):
        return findings

    findings.extend(_shape_findings(packet))
    if findings:
        return findings

    metadata = packet.get("metadata")
    _require_fields(metadata, REQUIRED_METADATA, "metadata", findings)

    if isinstance(metadata, dict):
        change_type = metadata.get("change_type")
        if _present(change_type) and change_type not in ALLOWED_CHANGE_TYPES:
            findings.append(
                Finding("ERROR", "INVALID_CHANGE_TYPE", "metadata.change_type",
                        f"Expected one of {sorted(ALLOWED_CHANGE_TYPES)}.")
            )
        group = metadata.get("group")
        if _present(group) and group not in ALLOWED_GROUPS:
            findings.append(
                Finding("ERROR", "INVALID_GROUP", "metadata.group",
                        f"Expected one of {sorted(ALLOWED_GROUPS)}.")
            )
        if change_type == "urgent_maintenance" and not _present(metadata.get("urgency_reason")):
            findings.append(
                Finding("GAP", "URGENCY_REASON_MISSING", "metadata.urgency_reason",
                        "Urgent maintenance should state why normal release preparation was bypassed or compressed.")
            )
        if metadata.get("synthetic") is True:
            findings.append(
                Finding("INFO", "SYNTHETIC_PACKET", "metadata.synthetic",
                        "Packet is explicitly marked synthetic.")
            )

    behavior = packet.get("user_facing_behavior")
    _require_fields(
        behavior,
        ("before", "after", "affected_users", "communications"),
        "user_facing_behavior",
        findings,
        level="GAP",
    )

    limitations = packet.get("known_limitations")
    if not isinstance(limitations, list):
        findings.append(Finding("ERROR", "EXPECTED_LIST", "known_limitations", "Expected a list."))
    elif not limitations:
        findings.append(
            Finding("GAP", "LIMITATIONS_UNSTATED", "known_limitations",
                    "State known limitations or add an explicit none-known entry.")
        )
    else:
        for i, item in enumerate(limitations):
            _require_fields(
                item,
                ("id", "description", "affected_scope", "owner_role", "follow_up_trigger"),
                f"known_limitations[{i}]",
                findings,
                level="GAP",
            )

    evidence = _id_map(packet.get("acceptance_evidence"), "acceptance_evidence", findings)
    support = _id_map(packet.get("support_readiness"), "support_readiness", findings)
    operations = _id_map(packet.get("operational_needs"), "operational_needs", findings)
    for shared_id in sorted(set(support) & set(operations)):
        findings.append(Finding("ERROR", "AMBIGUOUS_READINESS_ID", "support_readiness/operational_needs",
                                f"Readiness ID names both support and operational records: {shared_id}"))

    for item_id, item in evidence.items():
        _require_fields(
            item,
            ("kind", "locator", "result", "notes"),
            f"acceptance_evidence[{item_id}]",
            findings,
            level="GAP",
        )

    for item_id, item in support.items():
        path = f"support_readiness[{item_id}]"
        _require_fields(item, ("item", "owner_role", "status"), path, findings, level="GAP")
        status = item.get("status")
        if _present(status) and status not in READINESS_STATES:
            findings.append(
                Finding("ERROR", "INVALID_STATUS", f"{path}.status",
                        f"Expected one of {sorted(READINESS_STATES)}.")
            )
        if status in {"pending", "deferred_with_owner"}:
            findings.append(Finding("WARNING", "SUPPORT_FOLLOWUP_OPEN", path,
                                    "Support work remains explicitly open; a locator is not completion."))
            if not _present(item.get("follow_up_trigger")):
                findings.append(Finding("GAP", "FOLLOWUP_TRIGGER_MISSING", path,
                                        "Incomplete support item needs a follow-up trigger, even when a locator exists."))
        elif status == "complete" and not _present(item.get("locator")):
            findings.append(Finding("GAP", "SUPPORT_LOCATOR_MISSING", path,
                                    "Reported completion has no support evidence locator."))

    for item_id, item in operations.items():
        path = f"operational_needs[{item_id}]"
        _require_fields(item, ("kind", "need", "owner_role", "status"), path, findings, level="GAP")
        status = item.get("status")
        if _present(status) and status not in READINESS_STATES:
            findings.append(
                Finding("ERROR", "INVALID_STATUS", f"{path}.status",
                        f"Expected one of {sorted(READINESS_STATES)}.")
            )
        if status in {"pending", "deferred_with_owner"}:
            findings.append(Finding("WARNING", "OPERATIONAL_FOLLOWUP_OPEN", path,
                                    "Operational work remains explicitly open; verification text is not completion."))
            if not _present(item.get("follow_up_trigger")):
                findings.append(Finding("GAP", "FOLLOWUP_TRIGGER_MISSING", path,
                                        "Incomplete operational item needs a follow-up trigger."))
        elif status == "complete" and not _present(item.get("verification")):
            findings.append(Finding("GAP", "OPERATION_VERIFICATION_MISSING", path,
                                    "Reported completion has no operational verification detail."))

    requirements = packet.get("requirements")
    requirement_ids: set[str] = set()
    if not isinstance(requirements, list):
        findings.append(Finding("ERROR", "EXPECTED_LIST", "requirements", "Expected a list."))
    elif not requirements:
        findings.append(Finding("ERROR", "NO_REQUIREMENTS", "requirements", "At least one requirement is required."))
    else:
        for index, requirement in enumerate(requirements):
            path = f"requirements[{index}]"
            if not isinstance(requirement, dict):
                findings.append(Finding("ERROR", "EXPECTED_OBJECT", path, "Expected an object."))
                continue
            _require_fields(
                requirement,
                ("id", "statement", "acceptance_criteria"),
                path,
                findings,
            )
            rid = requirement.get("id")
            if _present(rid):
                rid = str(rid)
                if rid in requirement_ids:
                    findings.append(Finding("ERROR", "DUPLICATE_ID", path, f"Duplicate requirement id: {rid}"))
                requirement_ids.add(rid)

            evidence_refs = requirement.get("acceptance_evidence", [])
            readiness_refs = requirement.get("support_readiness", [])
            if not isinstance(evidence_refs, list) or not evidence_refs:
                findings.append(
                    Finding("GAP", "REQUIREMENT_EVIDENCE_MISSING", path,
                            "Requirement has no acceptance-evidence reference.")
                )
                evidence_refs = []
            if not isinstance(readiness_refs, list) or not readiness_refs:
                findings.append(
                    Finding("GAP", "REQUIREMENT_HANDOFF_MISSING", path,
                            "Requirement has no support/operational readiness reference.")
                )
                readiness_refs = []

            for ref in evidence_refs:
                if ref not in evidence:
                    findings.append(
                        Finding("ERROR", "BROKEN_EVIDENCE_REFERENCE", path,
                                f"Acceptance evidence reference does not resolve: {ref}")
                    )
            readiness_universe = set(support) | set(operations)
            for ref in readiness_refs:
                if ref not in readiness_universe:
                    findings.append(
                        Finding("ERROR", "BROKEN_READINESS_REFERENCE", path,
                                f"Support/operational readiness reference does not resolve: {ref}")
                    )

    docs = packet.get("documentation_updates")
    if not isinstance(docs, list):
        findings.append(Finding("ERROR", "EXPECTED_LIST", "documentation_updates", "Expected a list."))
    elif not docs:
        findings.append(
            Finding("GAP", "DOCUMENTATION_UNSTATED", "documentation_updates",
                    "Document updates/review status must be explicit.")
        )
    else:
        for index, doc in enumerate(docs):
            path = f"documentation_updates[{index}]"
            _require_fields(doc, ("document", "owner_role", "status"), path, findings, level="GAP")
            if isinstance(doc, dict):
                status = doc.get("status")
                if _present(status) and status not in DOC_STATES:
                    findings.append(
                        Finding("ERROR", "INVALID_DOC_STATUS", f"{path}.status",
                                f"Expected one of {sorted(DOC_STATES)}.")
                    )
                if status in {"pending", "deferred_with_owner"}:
                    findings.append(
                        Finding("WARNING", "DOCUMENTATION_FOLLOWUP_OPEN", path,
                                "Documentation work remains explicitly open.")
                    )
                    if not _present(doc.get("follow_up_trigger")):
                        findings.append(
                            Finding("GAP", "FOLLOWUP_TRIGGER_MISSING", path,
                                    "Pending/deferred documentation needs a follow-up trigger.")
                        )
                elif status in {"updated", "reviewed_no_change"} and not _present(doc.get("locator")):
                    findings.append(
                        Finding("GAP", "DOCUMENT_LOCATOR_MISSING", path,
                                "Completed/reviewed documentation should retain a locator.")
                    )

    rollback = packet.get("rollback_and_recovery")
    _require_fields(
        rollback,
        ("rollback_trigger", "rollback_method", "data_recovery_notes", "owner_role"),
        "rollback_and_recovery",
        findings,
        level="GAP",
    )

    open_items = packet.get("open_items")
    if not isinstance(open_items, list):
        findings.append(Finding("ERROR", "EXPECTED_LIST", "open_items", "Expected a list."))
    else:
        for index, item in enumerate(open_items):
            path = f"open_items[{index}]"
            _require_fields(
                item,
                ("id", "severity", "question", "owner_role", "resolution_trigger"),
                path,
                findings,
                level="GAP",
            )
            if isinstance(item, dict):
                severity = item.get("severity")
                if _present(severity) and severity not in OPEN_SEVERITIES:
                    findings.append(
                        Finding("ERROR", "INVALID_OPEN_SEVERITY", f"{path}.severity",
                                f"Expected one of {sorted(OPEN_SEVERITIES)}.")
                    )
                if severity == "blocking":
                    findings.append(
                        Finding("WARNING", "BLOCKING_OPEN_ITEM", path,
                                "Packet explicitly records a blocking unresolved item.")
                    )
                elif severity == "non_blocking":
                    findings.append(
                        Finding("WARNING", "NON_BLOCKING_OPEN_ITEM", path,
                                "Packet explicitly records a non-blocking unresolved item.")
                    )

    return findings


def assessment_state(findings: list[Finding]) -> str:
    if any(f.level == "ERROR" for f in findings):
        return "UNRELIABLE_PACKET"
    if any(f.level in {"GAP", "WARNING"} for f in findings):
        return "REVIEWABLE_WITH_FOLLOWUP"
    return "REVIEWABLE_NO_RECORDED_GAPS"


def render(packet: Any, findings: list[Finding]) -> str:
    # Re-evaluate the packet so stale caller findings cannot conceal its errors.
    findings = list(dict.fromkeys([*validate(packet), *findings]))
    packet = _mapping(packet)
    metadata = _mapping(packet.get("metadata"))
    state = assessment_state(findings)

    out = [
        f"# Handoff review — {metadata.get('change_id', 'unknown')}",
        "",
        f"- **Assessment state:** {state}",
        "- **Important:** this state describes packet completeness only; it is not release approval.",
        f"- **Change type:** {metadata.get('change_type', 'unknown')}",
        f"- **Service:** {metadata.get('service', 'unknown')}",
        f"- **Group:** {metadata.get('group', 'unknown')}",
        f"- **Summary:** {metadata.get('summary', 'unknown')}",
        "",
        "## Packet context",
        "",
        f"- **Packet version:** {_cell(metadata.get('packet_version'))}",
        f"- **Synthetic declaration:** {_cell(json.dumps(metadata['synthetic']) if type(metadata.get('synthetic')) is bool else metadata.get('synthetic'))}",
        f"- **Implementation owner role:** {_cell(metadata.get('implementation_owner_role'))}",
        f"- **Support owner role:** {_cell(metadata.get('support_owner_role'))}",
        f"- **Release trigger:** {_cell(metadata.get('release_trigger'))}",
        f"- **Urgency reason:** {_cell(metadata.get('urgency_reason'))}",
        "",
        "## Requested behavior",
        "",
        str(metadata.get("requested_behavior", "")),
        "",
        "## User-facing behavior",
        "",
        f"- **Before:** {_mapping(packet.get('user_facing_behavior')).get('before', '')}",
        f"- **After:** {_mapping(packet.get('user_facing_behavior')).get('after', '')}",
        f"- **Affected users:** {_cell(_mapping(packet.get('user_facing_behavior')).get('affected_users'))}",
        f"- **Communications:** {_cell(_mapping(packet.get('user_facing_behavior')).get('communications'))}",
        "",
        "## Requirement traceability",
        "",
        "| Requirement | Statement | Acceptance criteria | Evidence | Support / operations |",
        "| --- | --- | --- | --- | --- |",
    ]

    for requirement in _objects(packet.get("requirements")):
        out.append(
            "| {rid} | {statement} | {criteria} | {evidence} | {ready} |".format(
                rid=_cell(requirement.get("id")),
                statement=_cell(requirement.get("statement")),
                criteria=_cell(requirement.get("acceptance_criteria")),
                evidence=_cell(_reference_text(requirement.get("acceptance_evidence"))),
                ready=_cell(_reference_text(requirement.get("support_readiness"))),
            )
        )

    out.extend(["", "## Acceptance evidence", "",
                "| ID | Kind | Locator | Recorded result | Notes |",
                "| --- | --- | --- | --- | --- |"])
    for item in _objects(packet.get("acceptance_evidence")):
        out.append("| " + " | ".join(_cell(item.get(key)) for key in
                                     ("id", "kind", "locator", "result", "notes")) + " |")
    out.extend(["", "## Support and operational readiness", "",
                "| ID | Scope | Kind | Item / need | Owner role | Recorded status | Evidence / verification | Follow-up trigger |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for section, label, description, evidence_field in (
            ("support_readiness", "support", "item", "locator"),
            ("operational_needs", "operations", "need", "verification")):
        for item in _objects(packet.get(section)):
            values = (item.get("id"), label, item.get("kind") if section == "operational_needs" else "support item",
                      item.get(description), item.get("owner_role"),
                      item.get("status"), item.get(evidence_field), item.get("follow_up_trigger"))
            out.append("| " + " | ".join(_cell(value) for value in values) + " |")

    out.extend(["", "## Known limitations", ""])
    for item in _objects(packet.get("known_limitations")):
        out.append(
            f"- **{item.get('id', '?')}** — {item.get('description', '')} "
            f"(scope: {item.get('affected_scope', '')}; owner: {item.get('owner_role', '')}; "
            f"follow-up: {item.get('follow_up_trigger', '')}; mitigation: {_cell(item.get('mitigation'))})"
        )

    out.extend(["", "## Documentation", "",
                "| Document | Owner role | Recorded status | Locator | Follow-up trigger |",
                "| --- | --- | --- | --- | --- |"])
    for item in _objects(packet.get("documentation_updates")):
        out.append("| " + " | ".join(_cell(item.get(key)) for key in
                                     ("document", "owner_role", "status", "locator", "follow_up_trigger")) + " |")

    # Recovery is required assessment input and must also reach the operator.
    # An owner mentioned elsewhere is not a substitute for this section.
    recovery = _mapping(packet.get("rollback_and_recovery"))
    out.extend(["", "## Rollback and recovery", ""])
    for key, label in (("rollback_trigger", "Rollback trigger"),
                       ("rollback_method", "Rollback method"),
                       ("data_recovery_notes", "Data recovery notes"),
                       ("owner_role", "Recovery owner role")):
        out.append(f"- **{label}:** {_cell(recovery.get(key))}")

    out.extend(["", "## Open items", ""])
    open_items = _objects(packet.get("open_items"))
    if open_items:
        for item in open_items:
            out.append(
                f"- **{item.get('severity', 'unknown')} / {item.get('id', '?')}** — "
                f"{item.get('question', '')} (owner: {item.get('owner_role', '')}; "
                f"resolution trigger: {item.get('resolution_trigger', '')})"
            )
    else:
        out.append("- No open items recorded in the packet.")

    out.extend(["", "## Validation findings", ""])
    if findings:
        for finding in findings:
            out.append(
                f"- **{finding.level} {finding.code}** at `{finding.path}`: {finding.message}"
            )
    else:
        out.append("- No validator findings.")

    out.append("")
    return "\n".join(out)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"Non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number is outside the finite numeric range")
    return number


def load_packet(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant, parse_float=_finite_float)
    if not isinstance(value, dict):
        raise ValueError("Packet root must be a JSON object")
    return value


def command_validate(path: str, json_output: bool) -> int:
    packet = load_packet(path)
    findings = validate(packet)
    state = assessment_state(findings)
    if json_output:
        print(json.dumps(
            {"assessment_state": state, "findings": [f.as_dict() for f in findings]},
            indent=2,
            sort_keys=True,
        ))
    else:
        print(f"assessment_state={state}")
        for finding in findings:
            print(f"{finding.level}: {finding.code}: {finding.path}: {finding.message}")
    return 2 if any(f.level == "ERROR" for f in findings) else 0


def _publish_new_report(output: str, rendered: str) -> None:
    """Publish a complete UTF-8 report without replacing any existing path.

    Stage in the destination directory, close the completed file, then use an
    exclusive hard-link creation as the commit point. Existing reports, input
    aliases, symlinks and a competing writer's output cannot be overwritten.
    A filesystem without hard-link support raises an ordinary output error;
    there is deliberately no non-atomic or overwriting fallback.

    This is no-clobber publication, not a power-loss durability guarantee.
    """
    payload = rendered.encode("utf-8")
    requested = Path(output)
    parent = requested.parent.resolve(strict=True)
    destination = parent / requested.name
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=parent, prefix=".handoff-report-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Do not replace this with os.replace or an exists()/write_text pair:
        # neither preserves an existing destination under a competing writer.
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def command_render(path: str, output: str | None, *, no_clobber: bool = False) -> int:
    packet = load_packet(path)
    findings = validate(packet)
    rendered = render(packet, findings)
    if output:
        if no_clobber:
            _publish_new_report(output, rendered)
        else:
            Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 2 if any(f.level == "ERROR" for f in findings) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a handoff JSON packet")
    validate_parser.add_argument("path")
    validate_parser.add_argument("--json", action="store_true", dest="json_output")

    render_parser = subparsers.add_parser("render", help="Render a handoff JSON packet as Markdown")
    render_parser.add_argument("path")
    render_parser.add_argument("-o", "--output")
    render_parser.add_argument("--no-clobber", action="store_true",
                               help="Publish a complete new report without replacing an existing output path")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            return command_validate(args.path, args.json_output)
        if args.command == "render":
            return command_render(args.path, args.output, no_clobber=args.no_clobber)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        finding = Finding("ERROR", "INPUT_OR_OUTPUT_ERROR", "$", str(exc))
        if args.command == "validate" and args.json_output:
            print(json.dumps({"assessment_state": "UNRELIABLE_PACKET",
                              "findings": [finding.as_dict()]}, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {finding.code}: {finding.message}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    sys.exit(main())

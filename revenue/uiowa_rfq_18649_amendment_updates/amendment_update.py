#!/usr/bin/env python3
"""UIOWA-140 local amendment-to-proposal propagation checker.

Consumes normalized saved/public requirement manifests and a proposal-state JSON.
Only declared structured value changes are eligible for automatic propagation.
Textual/ambiguous changes stop as REVIEW_REQUIRED.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


class DataError(ValueError):
    pass


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _req_map(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("requirements"), list):
        raise DataError("manifest must contain requirements[]")
    out = {}
    for req in doc["requirements"]:
        if not isinstance(req, dict) or not isinstance(req.get("requirement_id"), str):
            raise DataError("every requirement needs requirement_id")
        rid = req["requirement_id"]
        if rid in out:
            raise DataError(f"duplicate requirement_id: {rid}")
        if not isinstance(req.get("source_ref"), str) or not req["source_ref"]:
            raise DataError(f"{rid}: source_ref required")
        out[rid] = req
    return out


def compare(old_doc, new_doc):
    old = _req_map(old_doc)
    new = _req_map(new_doc)
    deltas = []
    for rid in sorted(set(old) | set(new)):
        if rid not in old:
            deltas.append({
                "requirement_id": rid,
                "status": "ADDED",
                "old": None,
                "new": new[rid],
                "auto_update": False,
                "reason": "new requirement requires interpretation",
            })
            continue
        if rid not in new:
            deltas.append({
                "requirement_id": rid,
                "status": "REMOVED",
                "old": old[rid],
                "new": None,
                "auto_update": False,
                "reason": "removed requirement requires interpretation",
            })
            continue

        before = old[rid]
        after = new[rid]
        same = (
            before.get("value") == after.get("value")
            and before.get("text") == after.get("text")
        )
        if same:
            deltas.append({
                "requirement_id": rid,
                "status": "UNCHANGED",
                "old": before,
                "new": after,
                "auto_update": False,
                "reason": "content unchanged; retain binding",
            })
            continue

        structured = (
            before.get("change_type") == after.get("change_type") == "structured_value"
            and before.get("value") is not None
            and after.get("value") is not None
            and before.get("data_type") == after.get("data_type")
        )
        if structured:
            status = "STRUCTURED_CHANGE"
            auto_update = True
            reason = "declared structured value changed with stable semantic type"
        else:
            status = "REVIEW_REQUIRED"
            auto_update = False
            reason = (
                "wording/semantics changed without a safe structured replacement contract"
            )

        deltas.append({
            "requirement_id": rid,
            "status": status,
            "old": before,
            "new": after,
            "auto_update": auto_update,
            "reason": reason,
        })
    return deltas


def apply(deltas, proposal):
    if not isinstance(proposal, dict) or not isinstance(proposal.get("fields"), dict):
        raise DataError("proposal must contain fields{}")
    fields = proposal["fields"]
    actions = []

    for delta in deltas:
        rid = delta["requirement_id"]
        new = delta.get("new")
        old = delta.get("old")
        affects = (new or old or {}).get("affects", [])
        if not isinstance(affects, list):
            raise DataError(f"{rid}: affects must be a list")

        if delta["status"] == "UNCHANGED":
            for field_id in affects:
                field = fields.get(field_id)
                if not isinstance(field, dict):
                    continue
                actions.append({
                    "requirement_id": rid,
                    "field_id": field_id,
                    "action": "RETAIN",
                    "before": field.get("value"),
                    "after": field.get("value"),
                    "source_ref": field.get("source_ref"),
                })
            continue

        if delta["status"] != "STRUCTURED_CHANGE":
            for field_id in affects:
                field = fields.get(field_id)
                actions.append({
                    "requirement_id": rid,
                    "field_id": field_id,
                    "action": "REVIEW_REQUIRED",
                    "before": field.get("value") if isinstance(field, dict) else None,
                    "after": None,
                    "source_ref": (new or old).get("source_ref"),
                })
            continue

        old_value = old["value"]
        new_value = new["value"]
        for field_id in affects:
            field = fields.get(field_id)
            if not isinstance(field, dict):
                actions.append({
                    "requirement_id": rid,
                    "field_id": field_id,
                    "action": "MISSING_FIELD",
                    "before": None,
                    "after": None,
                    "source_ref": new["source_ref"],
                })
                continue

            current = field.get("value")
            if current == new_value:
                action = "ALREADY_CURRENT"
                after_value = current
            elif current == old_value:
                action = "UPDATED"
                after_value = new_value
                field["value"] = new_value
                field["source_requirement_id"] = rid
                field["source_ref"] = new["source_ref"]
            else:
                action = "CONFLICT"
                after_value = current

            actions.append({
                "requirement_id": rid,
                "field_id": field_id,
                "action": action,
                "before": current,
                "after": after_value,
                "source_ref": new["source_ref"],
            })
    return proposal, actions


def build_report(old_doc, new_doc, proposal):
    deltas = compare(old_doc, new_doc)
    updated, actions = apply(deltas, proposal)
    return {
        "old_version": old_doc.get("version_id"),
        "new_version": new_doc.get("version_id"),
        "deltas": deltas,
        "actions": actions,
        "updated_proposal": updated,
        "summary": {
            "unchanged": sum(d["status"] == "UNCHANGED" for d in deltas),
            "structured_changes": sum(
                d["status"] == "STRUCTURED_CHANGE" for d in deltas
            ),
            "review_required": sum(
                d["status"] in {"REVIEW_REQUIRED", "ADDED", "REMOVED"}
                for d in deltas
            ),
            "updated_fields": sum(a["action"] == "UPDATED" for a in actions),
            "conflicts": sum(a["action"] == "CONFLICT" for a in actions),
        },
    }


def write_csv(report, path):
    columns = [
        "requirement_id", "status", "auto_update", "old_value", "new_value",
        "source_ref", "affected_fields", "reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for delta in report["deltas"]:
            old = delta.get("old")
            new = delta.get("new")
            source_ref = (new or old or {}).get("source_ref")
            affects = (new or old or {}).get("affects", [])
            writer.writerow({
                "requirement_id": delta["requirement_id"],
                "status": delta["status"],
                "auto_update": str(delta["auto_update"]).lower(),
                "old_value": None if old is None else old.get("value"),
                "new_value": None if new is None else new.get("value"),
                "source_ref": source_ref,
                "affected_fields": " | ".join(affects),
                "reason": delta["reason"],
            })


def write_markdown(report, path):
    summary = report["summary"]
    lines = [
        "# Requirement delta report",
        "",
        f"Old version: `{report['old_version']}`  ",
        f"New version: `{report['new_version']}`",
        "",
        (
            f"Summary: {summary['structured_changes']} structured change(s), "
            f"{summary['unchanged']} unchanged, "
            f"{summary['review_required']} review-required delta(s), "
            f"{summary['updated_fields']} field update(s), "
            f"{summary['conflicts']} conflict(s)."
        ),
        "",
        "| Requirement | Status | Old | New | Auto |",
        "|---|---|---|---|---|",
    ]
    for delta in report["deltas"]:
        old = delta.get("old")
        new = delta.get("new")
        lines.append(
            f"| {delta['requirement_id']} | {delta['status']} | "
            f"{'' if old is None else old.get('value', '')} | "
            f"{'' if new is None else new.get('value', '')} | "
            f"{delta['auto_update']} |"
        )

    lines += [
        "",
        "## Proposal-field actions",
        "",
        "| Requirement | Field | Action | Before | After |",
        "|---|---|---|---|---|",
    ]
    for action in report["actions"]:
        lines.append(
            f"| {action['requirement_id']} | {action['field_id']} | "
            f"{action['action']} | "
            f"{'' if action['before'] is None else action['before']} | "
            f"{'' if action['after'] is None else action['after']} |"
        )

    lines += [
        "",
        "`REVIEW_REQUIRED`, `CONFLICT`, and `MISSING_FIELD` actions are never auto-rewritten.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("old_manifest", type=Path)
    parser.add_argument("new_manifest", type=Path)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)

    try:
        report = build_report(
            load_json(args.old_manifest),
            load_json(args.new_manifest),
            load_json(args.proposal),
        )
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

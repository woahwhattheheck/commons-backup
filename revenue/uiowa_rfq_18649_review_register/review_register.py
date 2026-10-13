#!/usr/bin/env python3
"""Offline, non-authoritative consolidated review register for RFQ 18649.

No network calls, compiler replacement, scheduling, or report-authority promotion.
Python 3.10+; standard library only. See README.md for the schema and limitations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "uiowa-rfq18649-review-register/v1"
OUTPUT_SCHEMA = "uiowa-rfq18649-review-response-draft/v1"
HANDOFF_SCHEMA = "uiowa-rfq18649-analyst-handoff-draft/v1"
MAX_BYTES = 4 * 1024 * 1024
GROUPS = {"ESS", "RIS", "IAM"}
DIMENSIONS = {"software_development", "security", "deployment", "ai_readiness"}
KINDS = {"WORDING", "EVIDENCE_CHANGE", "QUESTION"}
DISPOSITIONS = {"UNREVIEWED", "NEEDS_EVIDENCE", "DISCUSS_WITH_PRIME", "TECHNICAL_DRAFT_NOTE"}
AUTHORITY = {
    "buyer_approved": False, "prime_approved": False,
    "current_evidence_review_authority": False,
    "submission_authorized": False, "signature_authorized": False,
    "invoice_or_payment_authorized": False, "recognized_revenue": False,
}
TRANSITIONS = {
    "OPEN": {"ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED"},
    "ACCEPTED": {"RESOLVED", "UNRESOLVED", "DEFERRED"},
    "UNRESOLVED": {"ACCEPTED", "REJECTED", "DEFERRED"},
    "DEFERRED": {"OPEN", "ACCEPTED", "REJECTED", "UNRESOLVED"},
    "REJECTED": {"OPEN"}, "RESOLVED": {"OPEN"},
}


class ValidationError(ValueError):
    """A deterministic, location-bearing input diagnosis."""


def fail(path: str, message: str) -> None:
    raise ValidationError(f"{path}: {message}")


def shape(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(path, "expected an object")
    missing, extra = keys - value.keys(), value.keys() - keys
    if missing or extra:
        fail(path, f"missing fields={sorted(missing)}; unknown fields={sorted(extra)}")
    return value


def string(value: Any, path: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        fail(path, "expected a nonempty string" if not empty else "expected a string")
    if len(value) > 100_000:
        fail(path, "string exceeds 100,000 characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        fail(path, "unpaired Unicode surrogate")
    return value


def identifier(value: Any, path: str) -> str:
    value = string(value, path)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}", value):
        fail(path, "expected a stable ASCII identifier of at most 120 characters")
    return value


def digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        fail(path, "expected a lowercase SHA-256 hex digest")
    return value


def array(value: Any, path: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or len(value) > 20_000:
        fail(path, "expected an array of at most 20,000 items")
    if nonempty and not value:
        fail(path, "expected at least one item")
    return value


def refs(value: Any, known: dict[str, Any], path: str) -> list[str]:
    values = array(value, path)
    for i, item in enumerate(values):
        identifier(item, f"{path}[{i}]")
        if item not in known:
            fail(path, f"unresolved reference {item!r}")
    if len(set(values)) != len(values):
        fail(path, "duplicate reference")
    return values


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_load(path: Path) -> dict[str, Any]:
    # Bound the actual read, not only a pre-read stat that can become stale.
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        fail(str(path), "input exceeds 4 MiB")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                fail(str(path), f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        fail(str(path), f"non-finite JSON constant {value}")

    def floating(value: str) -> Any:
        # This v1 schema has no floating-point fields. Reject overflow and all
        # floats rather than silently converting a receipt or event sequence.
        fail(str(path), "floating-point numbers are not part of this schema")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant, parse_float=floating)
    except ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        fail(str(path), f"invalid UTF-8 JSON ({type(exc).__name__})")
    if not isinstance(value, dict):
        fail(str(path), "expected a top-level object")
    return value


def cell(value: Any, path: str) -> tuple[str, str]:
    shape(value, {"group", "dimension"}, path)
    if (not isinstance(value["group"], str) or not isinstance(value["dimension"], str)
            or value["group"] not in GROUPS or value["dimension"] not in DIMENSIONS):
        fail(path, "unknown assessment cell")
    return value["group"], value["dimension"]


def instant(value: Any, path: str) -> datetime:
    value = string(value, path)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        fail(path, "expected an RFC 3339 timestamp with seconds and timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(path, "invalid timestamp")
    if parsed.utcoffset() is None:
        fail(path, "timestamp requires a timezone")
    return parsed


def finding_fingerprint(finding: dict[str, Any]) -> bytes:
    """Reference order is not a substantive evidence revision."""
    return canonical({**finding, "evidence_refs": sorted(finding["evidence_refs"])})


def compile_cycle(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate lineage and produce a deterministic response-to-comments draft.

    Hashes bind claimed records; they do NOT authenticate the compiler, an analyst,
    source files, or an institutional finding. No original input is mutated.
    """
    shape(packet, {"schema", "synthetic", "evidence", "reports", "comments"}, "packet")
    if packet["schema"] != SCHEMA:
        fail("packet.schema", f"expected {SCHEMA}")
    if type(packet["synthetic"]) is not bool:
        fail("packet.synthetic", "expected a boolean")

    evidence: dict[str, Any] = {}
    for i, record in enumerate(array(packet["evidence"], "evidence")):
        path = f"evidence[{i}]"
        shape(record, {"id", "label", "source_locator", "sha256"}, path)
        rid = identifier(record["id"], path + ".id")
        if rid in evidence:
            fail(path, f"duplicate evidence ID {rid}")
        string(record["label"], path + ".label")
        string(record["source_locator"], path + ".source_locator")
        digest(record["sha256"], path + ".sha256")
        evidence[rid] = record

    reports: dict[str, Any] = {}
    findings: dict[str, dict[str, Any]] = {}
    first_cells: dict[str, tuple[str, str]] = {}
    previous: str | None = None
    for i, report in enumerate(array(packet["reports"], "reports", nonempty=True)):
        path = f"reports[{i}]"
        shape(report, {"version", "receipt_sha256", "supersedes", "findings"}, path)
        version = identifier(report["version"], path + ".version")
        if version in reports:
            fail(path, f"duplicate report version {version}")
        if report["supersedes"] != previous:
            fail(path, "reports must form an explicit ordered, linear supersedes chain")
        digest(report["receipt_sha256"], path + ".receipt_sha256")
        by_id: dict[str, Any] = {}
        for j, finding in enumerate(array(report["findings"], path + ".findings")):
            fp = f"{path}.findings[{j}]"
            shape(finding, {"id", "cell", "statement", "evidence_refs"}, fp)
            fid = identifier(finding["id"], fp + ".id")
            if fid in by_id:
                fail(fp, f"duplicate finding ID {fid}")
            fc = cell(finding["cell"], fp + ".cell")
            if fid in first_cells and first_cells[fid] != fc:
                fail(fp, "a stable finding ID cannot move to a different assessment cell")
            first_cells[fid] = fc
            string(finding["statement"], fp + ".statement")
            refs(finding["evidence_refs"], evidence, fp + ".evidence_refs")
            by_id[fid] = finding
        reports[version], findings[version], previous = report, by_id, version

    versions = list(reports)
    rank = {version: i for i, version in enumerate(versions)}
    target = versions[-1]
    rows: list[dict[str, Any]] = []
    comment_ids: set[str] = set()
    for i, comment in enumerate(array(packet["comments"], "comments")):
        path = f"comments[{i}]"
        shape(comment, {"id", "reviewer", "report_version", "finding_id", "kind",
                        "comment", "proposed_edit", "events"}, path)
        cid = identifier(comment["id"], path + ".id")
        if cid in comment_ids:
            fail(path, f"duplicate comment ID {cid}")
        comment_ids.add(cid)
        string(comment["reviewer"], path + ".reviewer")
        string(comment["comment"], path + ".comment")
        string(comment["proposed_edit"], path + ".proposed_edit", empty=True)
        source = identifier(comment["report_version"], path + ".report_version")
        fid = identifier(comment["finding_id"], path + ".finding_id")
        if source not in reports or fid not in findings[source]:
            fail(path, "original report/finding reference does not resolve")
        if not isinstance(comment["kind"], str) or comment["kind"] not in KINDS:
            fail(path + ".kind", f"expected one of {sorted(KINDS)}")
        original = findings[source][fid]
        events = array(comment["events"], path + ".events", nonempty=True)
        old_state: str | None = None
        old_at: datetime | None = None
        resolution: str | None = None
        highest_resolution_rank = rank[source]
        delta: dict[str, list[str]] = {"added": [], "removed": []}
        for j, event in enumerate(events):
            ep = f"{path}.events[{j}]"
            shape(event, {"sequence", "at", "actor", "state", "rationale", "resulting_report_version"}, ep)
            if type(event["sequence"]) is not int or event["sequence"] != j + 1:
                fail(ep, "event sequence must be consecutive integers starting at 1")
            timestamp = instant(event["at"], ep + ".at")
            if old_at is not None and timestamp < old_at:
                fail(ep, "event timestamps move backwards")
            old_at = timestamp
            string(event["actor"], ep + ".actor")
            string(event["rationale"], ep + ".rationale")
            state = event["state"]
            if not isinstance(state, str) or state not in TRANSITIONS:
                fail(ep, "unknown review state")
            if old_state is None:
                if state != "OPEN":
                    fail(ep, "first event must be OPEN")
            elif state not in TRANSITIONS[old_state]:
                fail(ep, f"invalid transition {old_state} -> {state}")
            resulting = event["resulting_report_version"]
            if state != "RESOLVED":
                if resulting is not None:
                    fail(ep, "only RESOLVED events bind a resulting report version")
            else:
                identifier(resulting, ep + ".resulting_report_version")
                if resulting not in reports or rank[resulting] < rank[source]:
                    fail(ep, "resulting report must be the original version or a descendant")
                if rank[resulting] < highest_resolution_rank:
                    fail(ep, "resulting report revision moves backwards across review cycles")
                highest_resolution_rank = rank[resulting]
                if fid not in findings[resulting]:
                    fail(ep, "resulting finding reference does not resolve")
                revised = findings[resulting][fid]
                added = sorted(set(revised["evidence_refs"]) - set(original["evidence_refs"]))
                removed = sorted(set(original["evidence_refs"]) - set(revised["evidence_refs"]))
                changed_statement = revised["statement"] != original["statement"]
                if comment["kind"] == "WORDING" and (added or removed):
                    fail(ep, "evidence changed under a WORDING-only resolution; reclassify the comment")
                if comment["kind"] == "WORDING" and not changed_statement:
                    fail(ep, "WORDING resolution requires an actual statement edit")
                if comment["kind"] == "EVIDENCE_CHANGE" and not (added or removed):
                    fail(ep, "EVIDENCE_CHANGE resolution requires an explicit evidence version change")
                if comment["kind"] != "QUESTION" and rank[resulting] == rank[source]:
                    fail(ep, "an applied edit requires a later report version")
                resolution, delta = resulting, {"added": added, "removed": removed}
            if state == "OPEN":
                resolution, delta = None, {"added": [], "removed": []}
            old_state = state

        current = findings[target].get(fid)
        resolved_finding = findings[resolution][fid] if resolution else None
        stale = old_state == "RESOLVED" and (
            current is None or finding_fingerprint(current) != finding_fingerprint(resolved_finding))
        rows.append({
            "comment_id": cid, "reviewer": comment["reviewer"], "kind": comment["kind"],
            "finding_id": fid, "cell": original["cell"], "comment": comment["comment"],
            "proposed_edit": comment["proposed_edit"], "status": old_state,
            "original_report_version": source,
            "original_report_receipt_sha256": reports[source]["receipt_sha256"],
            "original_statement": original["statement"],
            "original_evidence": [evidence[eid] for eid in sorted(original["evidence_refs"])],
            "resulting_report_version": resolution,
            "resulting_report_receipt_sha256": reports[resolution]["receipt_sha256"] if resolution else None,
            "resulting_statement": resolved_finding["statement"] if resolved_finding else None,
            "evidence_delta": delta,
            "resulting_evidence": [evidence[eid] for eid in sorted(resolved_finding["evidence_refs"])] if resolved_finding else [],
            "target_finding_present": current is not None,
            "stale_resolution": stale,
            "needs_follow_up": old_state not in {"RESOLVED", "REJECTED"} or stale,
            "latest_rationale": events[-1]["rationale"], "events": events,
        })

    rows.sort(key=lambda row: row["comment_id"])
    output = {
        "schema": OUTPUT_SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE",
        "synthetic": packet["synthetic"], "source_packet_sha256": sha(packet),
        "target_report_version": target,
        "target_report_receipt_sha256": reports[target]["receipt_sha256"],
        "summary": {"comment_count": len(rows),
                    "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
                    "follow_up_comment_ids": [r["comment_id"] for r in rows if r["needs_follow_up"]],
                    "stale_resolution_comment_ids": [r["comment_id"] for r in rows if r["stale_resolution"]]},
        "comments": rows, "authority": dict(AUTHORITY),
        "limits": ["Recorded analyst decisions are not authenticated or institutional approval.",
                   "Receipt fields are claimed bindings; no parent-compiler verification is performed.",
                   "Evidence hashes are manifest metadata; this tool does not read or authenticate source files.",
                   "No maturity score, compliance conclusion, invoice, payment, or scheduling action is generated."],
    }
    output["receipt_sha256"] = sha(output)
    # Exported nested records must not retain mutable aliases into the input.
    return json.loads(canonical(output))


def handoff_intake(handoff: dict[str, Any], reviewer: str) -> dict[str, Any]:
    """Convert existing workbench notes to review INTAKE, never resolved findings."""
    shape(handoff, {"schema", "status", "report_receipt_sha256", "report_mode", "aggregate_state",
                    "synthetic_demo", "cell_notes", "authority"}, "handoff")
    if handoff["schema"] != HANDOFF_SCHEMA or handoff["status"] != "DRAFT_NON_AUTHORITATIVE":
        fail("handoff", "expected the existing v1 draft handoff")
    if handoff["report_mode"] != "UNTRUSTED_INSPECTION":
        fail("handoff.report_mode", "expected UNTRUSTED_INSPECTION")
    digest(handoff["report_receipt_sha256"], "handoff.report_receipt_sha256")
    string(handoff["aggregate_state"], "handoff.aggregate_state")
    if type(handoff["synthetic_demo"]) is not bool:
        fail("handoff.synthetic_demo", "expected a boolean")
    shape(handoff["authority"], set(AUTHORITY), "handoff.authority")
    if any(value is not False for value in handoff["authority"].values()):
        fail("handoff.authority", "draft handoff authority values must be literal false")
    string(reviewer, "reviewer")
    notes = array(handoff["cell_notes"], "handoff.cell_notes")
    seen: set[tuple[str, str]] = set()
    comments = []
    for i, note in enumerate(notes):
        path = f"handoff.cell_notes[{i}]"
        shape(note, {"group", "dimension", "compiler_status", "disposition", "analyst_note"}, path)
        key = cell({k: note[k] for k in ("group", "dimension")}, path)
        if key in seen:
            fail(path, "duplicate assessment cell")
        seen.add(key)
        string(note["compiler_status"], path + ".compiler_status")
        string(note["analyst_note"], path + ".analyst_note", empty=True)
        if not isinstance(note["disposition"], str) or note["disposition"] not in DISPOSITIONS:
            fail(path, "unknown workbench disposition")
        if note["analyst_note"].strip() or note["disposition"] != "UNREVIEWED":
            comments.append({"intake_id": "INTAKE-" + sha({"receipt": handoff["report_receipt_sha256"],
                "reviewer": reviewer, "synthetic_demo": handoff["synthetic_demo"], "note": note})[:24], "reviewer": reviewer,
                "cell": {"group": key[0], "dimension": key[1]},
                "compiler_status": note["compiler_status"], "disposition": note["disposition"],
                "analyst_note": note["analyst_note"], "status": "OPEN_INTAKE_NOT_A_FINDING",
                "finding_id": None, "kind": None})
    if seen != {(g, d) for g in GROUPS for d in DIMENSIONS}:
        fail("handoff.cell_notes", "expected all 12 distinct assessment cells")
    return {"schema": "uiowa-rfq18649-review-intake-draft/v1", "status": "DRAFT_NON_AUTHORITATIVE",
            "synthetic_demo": handoff["synthetic_demo"],
            "report_receipt_sha256": handoff["report_receipt_sha256"],
            "source_handoff_sha256": sha(handoff),
            "comments": sorted(comments, key=lambda c: c["intake_id"]), "authority": dict(AUTHORITY),
            "next_step": "A reviewer must bind intake to a real finding ID and classify it; no automatic resolution."}


def csv_text(report: dict[str, Any]) -> str:
    fields = ["comment_id", "reviewer", "kind", "finding_id", "status", "original_report_version",
              "resulting_report_version", "stale_resolution", "needs_follow_up", "comment", "proposed_edit", "latest_rationale"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in report["comments"]:
        safe = {}
        for key in fields:
            value = "" if row[key] is None else str(row[key])
            if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return output.getvalue()


def md(value: Any) -> str:
    value = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", value).replace("\n", "<br>").replace("\r", "")


def markdown(report: dict[str, Any]) -> str:
    label = "SYNTHETIC REHEARSAL" if report["synthetic"] else "PRIVATE INPUT — NOT APPROVED FOR PUBLICATION"
    lines = ["# Consolidated response to review comments", "", f"**{label} · DRAFT NON-AUTHORITATIVE**", "",
             f"Target report: `{report['target_report_version']}`", "",
             f"Claimed report receipt: `{report['target_report_receipt_sha256']}`", "",
             f"Review-register receipt: `{report['receipt_sha256']}`", "",
             f"Comments: {report['summary']['comment_count']}; follow-ups: {len(report['summary']['follow_up_comment_ids'])}.", "",
             "Recorded resolutions are analyst dispositions, not buyer acceptance or source authentication.", ""]
    for row in report["comments"]:
        lines += [f"## {row['comment_id']} — {row['status']}", "",
                  f"Finding `{row['finding_id']}` · {md(row['kind'])} · reviewer: {md(row['reviewer'])}", "",
                  f"**Original comment:** {md(row['comment'])}", "",
                  f"**Proposed edit:** {md(row['proposed_edit']) or 'None recorded'}", "",
                  f"**Original statement:** {md(row['original_statement'])}", "",
                  f"**Resulting statement:** {md(row['resulting_statement']) if row['resulting_statement'] else 'No applied resolution'}", "",
                  f"**Latest rationale:** {md(row['latest_rationale'])}", "",
                  f"**Version chain:** {row['original_report_version']} → {row['resulting_report_version'] or 'unresolved'}; target {report['target_report_version']}", "",
                  f"**Follow-up needed:** {row['needs_follow_up']}; **stale resolution:** {row['stale_resolution']}", "",
                  f"**Evidence added:** {md(', '.join(row['evidence_delta']['added'])) or 'None'}; **removed:** {md(', '.join(row['evidence_delta']['removed'])) or 'None'}", "",
                  "### Recorded decision history", ""]
        for event in row["events"]:
            lines += [f"{event['sequence']}. {md(event['at'])} · {event['state']} · {md(event['actor'])}: {md(event['rationale'])}"]
        lines += ["", "### Source locators", ""]
        records = {r["id"]: r for r in row["original_evidence"] + row["resulting_evidence"]}
        for rid in sorted(records):
            record = records[rid]
            lines += [f"- `{rid}` — {md(record['label'])}; {md(record['source_locator'])}; SHA-256 `{record['sha256']}`"]
        lines += [""]
    lines += ["## Interpretation limits", ""] + [f"- {x}" for x in report["limits"]] + [""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile", help="Write a new response-to-comments directory")
    compile_parser.add_argument("packet", type=Path)
    compile_parser.add_argument("--out", type=Path, required=True)
    intake_parser = commands.add_parser("handoff-intake", help="Convert existing workbench draft notes to unclassified intake")
    intake_parser.add_argument("handoff", type=Path)
    intake_parser.add_argument("--reviewer", required=True)
    intake_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            report = compile_cycle(strict_load(args.packet))
            # Refuse overwrite so prior exports and private originals stay intact.
            args.out.mkdir(parents=False, exist_ok=False)
            files = {"response.json": json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                     "response.csv": csv_text(report), "response.md": markdown(report)}
            for name, content in files.items():
                with (args.out / name).open("x", encoding="utf-8", newline="") as target:
                    target.write(content)
            manifest = {"schema": "uiowa-rfq18649-review-export-manifest/v1",
                        "status": "DRAFT_NON_AUTHORITATIVE", "review_receipt_sha256": report["receipt_sha256"],
                        "files": {name: hashlib.sha256((args.out / name).read_bytes()).hexdigest() for name in sorted(files)}}
            (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report["summary"], sort_keys=True))
        else:
            intake = handoff_intake(strict_load(args.handoff), args.reviewer)
            with args.out.open("x", encoding="utf-8") as target:
                json.dump(intake, target, indent=2, ensure_ascii=False, allow_nan=False)
                target.write("\n")
            print(f"Wrote {len(intake['comments'])} draft intake records; no findings resolved.")
        return 0
    except (ValidationError, OSError, TypeError, RecursionError) as exc:
        print(f"review_register: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

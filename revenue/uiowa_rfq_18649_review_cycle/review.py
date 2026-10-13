"""Receipt-bound draft review and deterministic original/revised delivery bundles."""
from __future__ import annotations
import argparse
from copy import deepcopy
import csv
import hashlib
import html
import io
import json
from pathlib import Path
import re
import sys

if __package__:
    from .parent_adapter import verify_inspection
else:
    from parent_adapter import verify_inspection

DOC_SCHEMA = "uiowa-rfq18649-review-document/v1"
CYCLE_SCHEMA = "uiowa-rfq18649-review-cycle/v1"
STATUS = "DRAFT_NON_AUTHORITATIVE"
AUTHORITY = {k: False for k in (
    "buyer_approved", "prime_approved", "current_evidence_review_authority",
    "submission_authorized", "signature_authorized", "invoice_or_payment_authorized", "recognized_revenue",
)}
KINDS = {"factual", "evidence", "wording", "interpretation", "priority"}
DECISIONS = {"ACCEPT", "REJECT", "UNRESOLVED", "DEFER", "OPEN"}
PHASES = {"0-90", "90-180", "180+", "UNPLACED"}
FIELDS = {"findings": {"title", "statement", "source_ids"},
          "recommendations": {"title", "priority", "phase", "rationale"}}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def exact(obj, keys: set, where: str) -> None:
    require(type(obj) is dict and set(obj) == keys, f"{where}: incorrect fields")


def text(value, where: str, *, empty=False) -> None:
    require(type(value) is str and (empty or bool(value.strip())) and len(value) <= 12000,
            f"{where}: expected bounded text")
    # Inspect paired CRLF as a line break without changing the retained text.
    # Bare CR and every other previously forbidden control remain invalid.
    require(not any(ord(c) < 32 and c not in "\n\t" for c in value.replace("\r\n", "\n")),
            f"{where}: control character")


def ident(value, where: str) -> None:
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", value) is not None,
            f"{where}: invalid identifier")


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def load(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    require(path.stat().st_size <= 2 * 1024 * 1024, "input exceeds 2 MiB")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non-finite JSON")))


def indexed(rows, where: str) -> dict:
    require(type(rows) is list and len(rows) <= 1000, f"{where}: expected bounded array")
    result = {}
    for row in rows:
        require(type(row) is dict, f"{where}: row must be object")
        ident(row.get("id"), where)
        require(row["id"] not in result, f"{where}: duplicate id {row['id']}")
        result[row["id"]] = row
    return result


def validate_document(doc: dict, report: dict) -> None:
    exact(doc, {"schema", "status", "synthetic", "version", "parent_version", "report_receipt_sha256",
                "authority", "findings", "recommendations", "applied_cycles", "unresolved"}, "document")
    require(doc["schema"] == DOC_SCHEMA and doc["status"] == STATUS, "document must be draft review schema")
    require(type(doc["synthetic"]) is bool, "synthetic must be boolean")
    require(doc["authority"] == AUTHORITY and all(v is False for v in doc["authority"].values()), "authority must remain false")
    ident(doc["version"], "document.version")
    if doc["parent_version"] is not None:
        ident(doc["parent_version"], "parent_version")
    require(doc["report_receipt_sha256"] == report["receipt_sha256"], "document/report receipt mismatch")
    require(type(doc["applied_cycles"]) is list and len(doc["applied_cycles"]) == len(set(doc["applied_cycles"])), "duplicate or invalid cycle history")
    for item in doc["applied_cycles"]:
        ident(item, "applied_cycle")
    require(type(doc["unresolved"]) is list, "unresolved must be array")
    for item in doc["unresolved"]:
        exact(item, {"cycle_id", "comment_id", "target_id", "comment", "decision", "rationale", "owner_role"}, "unresolved")
        for key in ("cycle_id", "comment_id", "target_id"):
            ident(item[key], key)
        require(item["decision"] in {"OPEN", "DEFER", "UNRESOLVED"}, "invalid unresolved disposition")
        for key in ("comment", "rationale", "owner_role"):
            text(item[key], key)
    sources = {s["source_id"]: s for s in report["evidence_authority"]["sources"]}
    cells = {(c["group"], c["dimension"]) for c in report["assessment_matrix"]}
    findings = indexed(doc["findings"], "findings")
    for row in findings.values():
        exact(row, {"id", "group", "dimension", "title", "statement", "source_ids"}, "finding")
        require((row["group"], row["dimension"]) in cells, "finding uses unknown native compiler cell")
        for field in ("title", "statement"):
            text(row[field], field)
        require(type(row["source_ids"]) is list and len(row["source_ids"]) == len(set(row["source_ids"])), "invalid source_ids")
        for sid in row["source_ids"]:
            require(sid in sources, f"missing source: {sid}")
            require((sources[sid]["group"], sources[sid]["dimension"]) == (row["group"], row["dimension"]), "cross-cell source transplant")
    for row in indexed(doc["recommendations"], "recommendations").values():
        exact(row, {"id", "title", "finding_ids", "priority", "phase", "rationale"}, "recommendation")
        for key in ("title", "rationale"):
            text(row[key], key)
        require(row["priority"] in {"HIGH", "MEDIUM", "LOW", "UNRANKED"} and row["phase"] in PHASES, "invalid priority/phase")
        require(type(row["finding_ids"]) is list and bool(row["finding_ids"]) and len(row["finding_ids"]) == len(set(row["finding_ids"])), "invalid finding_ids")
        require(all(fid in findings for fid in row["finding_ids"]), "broken recommendation finding reference")


def source_changes(old: dict, new: dict) -> list:
    before = {s["source_id"]: s for s in old["evidence_authority"]["sources"]}
    after = {s["source_id"]: s for s in new["evidence_authority"]["sources"]}
    changes = []
    for sid in sorted(set(before) | set(after)):
        a, b = before.get(sid), after.get(sid)
        # Generation-only rebinding is not mislabeled as substantive evidence change.
        fields = [k for k in sorted(set(a or {}) | set(b or {}))
                  if k != "authority_generation" and (a or {}).get(k) != (b or {}).get(k)]
        if fields:
            changes.append({"source_id": sid, "kind": "added" if a is None else "removed" if b is None else "revised",
                            "fields": fields, "before": a, "after": b})
    return changes


def apply_cycle(original_report: dict, revised_report: dict, document: dict, cycle: dict) -> tuple[dict, dict]:
    verify_inspection(original_report)
    verify_inspection(revised_report)
    require(original_report["candidate"]["engagement"] == revised_report["candidate"]["engagement"], "cross-engagement review")
    require(original_report["evaluated_at"] <= revised_report["evaluated_at"], "backdated revised inspection")
    validate_document(document, original_report)
    exact(cycle, {"schema", "id", "base_document_sha256", "base_report_receipt_sha256", "target_report_receipt_sha256",
                  "new_version", "comments"}, "cycle")
    require(cycle["schema"] == CYCLE_SCHEMA, "cycle schema mismatch")
    ident(cycle["id"], "cycle.id")
    ident(cycle["new_version"], "new_version")
    require(cycle["id"] not in document["applied_cycles"], "cycle already applied")
    require(cycle["new_version"] != document["version"], "revision must have a new version")
    require(cycle["base_document_sha256"] == digest(document), "stale base document")
    require(cycle["base_report_receipt_sha256"] == original_report["receipt_sha256"] and
            cycle["target_report_receipt_sha256"] == revised_report["receipt_sha256"], "cycle/report receipt mismatch")
    comments = indexed(cycle["comments"], "comments")
    result = deepcopy(document)
    original_tables = {t: indexed(document[t], t) for t in FIELDS}
    result_tables = {t: indexed(result[t], t) for t in FIELDS}
    sources = {s["source_id"]: s for s in revised_report["evidence_authority"]["sources"]}
    mutations, touched, responses = [], set(), []
    for cid, row in sorted(comments.items()):
        exact(row, {"id", "kind", "target_type", "target_id", "comment", "proposed_changes",
                    "source_ids", "decision", "rationale", "owner_role"}, "comment")
        require(row["kind"] in KINDS and row["decision"] in DECISIONS, "unknown kind/decision")
        table, target = row["target_type"], row["target_id"]
        require(table in FIELDS and target in original_tables[table], "unknown review target")
        for k in ("comment", "rationale", "owner_role"):
            text(row[k], k)
        require(type(row["source_ids"]) is list and len(row["source_ids"]) == len(set(row["source_ids"])), "invalid comment sources")
        require(all(s in sources for s in row["source_ids"]), "comment cites missing revised source")
        if table == "findings":
            target_row = original_tables[table][target]
            require(all((sources[s]["group"], sources[s]["dimension"]) ==
                        (target_row["group"], target_row["dimension"]) for s in row["source_ids"]),
                    "comment cites evidence from a different cell")
        changes = row["proposed_changes"]
        require(type(changes) is list and len(changes) <= 8, "invalid change list")
        require(row["decision"] != "ACCEPT" or bool(changes), "accepted comment must describe an actual change")
        if row["decision"] == "ACCEPT" and row["kind"] in {"factual", "evidence"}:
            require(bool(row["source_ids"]), "substantive correction requires source references")
        for patch in changes:
            exact(patch, {"field", "before", "after"}, "change")
            field = patch["field"]
            require(field in FIELDS[table], "protected or unknown change field")
            require(patch["before"] == original_tables[table][target][field], "stale field precondition")
            require(patch["before"] != patch["after"], "no-op change")
            if row["kind"] == "wording":
                require(field == "title", "wording changes may change titles only; conclusions require substantive review")
            if row["kind"] == "priority":
                require(table == "recommendations" and field in {"priority", "phase", "rationale"}, "priority change outside roadmap fields")
            if field == "source_ids":
                require(row["kind"] == "evidence", "only evidence review may change evidence links")
            if row["decision"] == "ACCEPT":
                key = (table, target, field)
                require(key not in touched, "conflicting accepted changes to one field")
                touched.add(key)
                result_tables[table][target][field] = deepcopy(patch["after"])
                mutations.append({"comment_id": cid, "target_type": table, "target_id": target, **deepcopy(patch)})
        if row["decision"] in {"OPEN", "DEFER", "UNRESOLVED"}:
            result["unresolved"].append({"cycle_id": cycle["id"], "comment_id": cid, "target_id": target,
                                         **{k: row[k] for k in ("comment", "decision", "rationale", "owner_role")}})
        responses.append(deepcopy(row))
    result["parent_version"] = document["version"]
    result["version"] = cycle["new_version"]
    result["report_receipt_sha256"] = revised_report["receipt_sha256"]
    result["applied_cycles"].append(cycle["id"])
    validate_document(result, revised_report)
    deltas = source_changes(original_report, revised_report)
    # Changed source content cannot silently carry an unchanged conclusion forward.
    reassessment = []
    changed_ids = {d["source_id"] for d in deltas if d["kind"] != "added"}
    for f in document["findings"]:
        affected = sorted(set(f["source_ids"]) & changed_ids)
        if affected and not any(c["target_type"] == "findings" and c["target_id"] == f["id"]
                                and c["kind"] in {"factual", "evidence", "interpretation"} and c["decision"] == "ACCEPT"
                                and set(affected).issubset(c["source_ids"])
                                and any(p["field"] in {"statement", "source_ids"} for p in c["proposed_changes"])
                                for c in responses):
            reassessment.append({"finding_id": f["id"], "source_ids": affected, "status": "REASSESSMENT_REQUIRED"})
    old_cells = {(c["group"], c["dimension"]): c for c in original_report["assessment_matrix"]}
    cell_changes = [{"group": c["group"], "dimension": c["dimension"],
                     "before_status": old_cells[(c["group"], c["dimension"])]["status"], "after_status": c["status"]}
                    for c in revised_report["assessment_matrix"]
                    if old_cells[(c["group"], c["dimension"])]["status"] != c["status"]]
    audit = {"status": STATUS, "cycle_id": cycle["id"], "base_document_sha256": digest(document),
             "revised_document_sha256": digest(result), "changes": mutations, "source_changes": deltas,
             "compiler_status_changes": cell_changes, "reassessment_required": reassessment,
             "unresolved_count": len(result["unresolved"]), "responses": responses, "authority": deepcopy(AUTHORITY)}
    return result, audit


def handoff_comments(report: dict, handoff: dict) -> list:
    verify_inspection(report)
    exact(handoff, {"schema", "status", "report_receipt_sha256", "report_mode", "aggregate_state",
                    "synthetic_demo", "cell_notes", "authority"}, "workbench handoff")
    require(handoff["schema"] == "uiowa-rfq18649-analyst-handoff-draft/v1" and handoff["status"] == STATUS, "unsupported handoff")
    require(handoff["synthetic_demo"] is False, "UI demo is not compiler output")
    require(handoff["authority"] == AUTHORITY and all(v is False for v in handoff["authority"].values()), "handoff authority drift")
    require(handoff["report_receipt_sha256"] == report["receipt_sha256"] and handoff["report_mode"] == report["mode"]
            and handoff["aggregate_state"] == report["aggregate_state"], "handoff/report mismatch")
    cells = {(c["group"], c["dimension"]): c for c in report["assessment_matrix"]}
    require(type(handoff["cell_notes"]) is list and len(handoff["cell_notes"]) == len(cells), "handoff requires all native cells")
    seen, output = set(), []
    for note in handoff["cell_notes"]:
        exact(note, {"group", "dimension", "compiler_status", "disposition", "analyst_note"}, "cell note")
        key = (note["group"], note["dimension"])
        require(key in cells and key not in seen, "duplicate or unknown handoff cell")
        seen.add(key)
        require(note["compiler_status"] == cells[key]["status"], "handoff compiler status drift")
        text(note["analyst_note"], "analyst_note", empty=True)
        text(note["disposition"], "disposition")
        if note["analyst_note"].strip() or note["disposition"] != "UNREVIEWED":
            output.append({"group": key[0], "dimension": key[1], "comment": note["analyst_note"],
                           "workbench_disposition": note["disposition"], "decision": "OPEN",
                           "report_receipt_sha256": report["receipt_sha256"]})
    return output


def md(value) -> str:
    return html.escape(str(value)).replace("|", "&#124;").replace("\r\n", "\n").replace("\n", "<br>")


def render_document(doc: dict, report: dict) -> str:
    lines = ["# Draft assessment review", "", f"**{STATUS} — {'SYNTHETIC FICTION; NOT UNIVERSITY FINDINGS' if doc['synthetic'] else 'LOCAL DRAFT; HUMAN REVIEW REQUIRED'}**", "",
             f"Version: {md(doc['version'])}; compiler receipt: `{report['receipt_sha256']}`.",
             "No approval, submission, payment or maturity authority is conferred by review decisions.", "", "## Findings"]
    sources = {s["source_id"]: s for s in report["evidence_authority"]["sources"]}
    for f in doc["findings"]:
        lines += ["", f"### {md(f['id'])}: {md(f['title'])}", f"{md(f['group'])} / {md(f['dimension'])}", md(f["statement"])]
        if not f["source_ids"]:
            lines.append("Evidence: UNKNOWN / no linked source supplied.")
        for sid in f["source_ids"]:
            s = sources[sid]
            lines.append(f"Source {md(sid)} — {md(s['source_ref'])}; content SHA-256 `{s['source_content_sha256']}`.")
    lines += ["", "## Recommendation and roadmap view", "", "| ID | Action | Findings | Priority | Relative phase | Rationale |", "|---|---|---|---|---|---|"]
    for r in doc["recommendations"]:
        lines.append("| " + " | ".join(md(r[k]) for k in ("id", "title", "finding_ids", "priority", "phase", "rationale")) + " |")
    lines += ["", "Relative phases are proposed planning choices, not appointments or committed availability.", "", "## Unresolved review"]
    for u in doc["unresolved"]:
        lines.append(f"- {md(u['comment_id'])} / {md(u['decision'])}: {md(u['comment'])} — {md(u['rationale'])}; proposed follow-up role: {md(u['owner_role'])}.")
    if not doc["unresolved"]:
        lines.append("No unresolved comments have been recorded in this version; this is not an approval.")
    return "\n".join(lines) + "\n"


def build_bundle(old: dict, new: dict, doc: dict, cycle: dict) -> dict[str, bytes]:
    revised, audit = apply_cycle(old, new, doc, cycle)
    output = {"original-report.json": canonical(old), "revised-report.json": canonical(new),
              "original-draft.json": canonical(doc), "revised-draft.json": canonical(revised),
              "comments.json": canonical(cycle), "audit.json": canonical(audit),
              "original-draft.md": render_document(doc, old).encode(), "revised-draft.md": (render_document(revised, new) + "\n## Evidence requiring reassessment\n" +
                                   md(audit["reassessment_required"]) + "\n").encode()}
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["comment_id", "kind", "target", "decision", "response", "proposed_owner_role"])
    response_lines = ["# Response to consolidated comments", "", f"{STATUS}. Synthetic status: {doc['synthetic']}.", ""]
    for c in audit["responses"]:
        # Display CSV only; exact original strings stay in comments.json/audit.json.
        values = [c["id"], c["kind"], c["target_id"], c["decision"], c["rationale"], c["owner_role"]]
        writer.writerow(["'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for v in values])
        response_lines += [f"## {md(c['id'])} — {md(c['decision'])}", md(c["comment"]), md(c["rationale"]),
                           f"Target: {md(c['target_id'])}; kind: {md(c['kind'])}; sources: {md(c['source_ids'])}.", ""]
    response_lines += ["## Reassessment queue", md(audit["reassessment_required"]), "",
                       "## Exact changes", "```json", json.dumps({k: audit[k] for k in ("changes", "source_changes", "compiler_status_changes")}, indent=2, ensure_ascii=False, sort_keys=True), "```", ""]
    output["responses.csv"] = buf.getvalue().encode()
    output["responses.md"] = "\n".join(response_lines).encode()
    manifest = {"schema": "uiowa-rfq18649-review-bundle/v1", "status": STATUS, "synthetic": doc["synthetic"],
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(output.items())}}
    output["manifest.json"] = canonical(manifest)
    return output


def write_bundle(path: Path, output: dict[str, bytes]) -> None:
    # Local operator output only; never overwrite an existing version or publish remotely.
    path.mkdir(parents=False, exist_ok=False)
    for name, data in output.items():
        with (path / name).open("xb") as handle:
            handle.write(data)


def verify_bundle(path: Path) -> None:
    rebuilt = build_bundle(*(load(path / n) for n in ("original-report.json", "revised-report.json", "original-draft.json", "comments.json")))
    require({p.name for p in path.iterdir()} == set(rebuilt), "bundle file set differs from regenerated output")
    for name, data in rebuilt.items():
        require((path / name).read_bytes() == data, f"bundle regeneration mismatch: {name}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    apply = sub.add_parser("apply")
    for key in ("original_report", "revised_report", "draft", "comments", "output"):
        apply.add_argument(key, type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    capture = sub.add_parser("capture-handoff")
    capture.add_argument("report", type=Path)
    capture.add_argument("handoff", type=Path)
    capture.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "apply":
            output = build_bundle(*(load(p) for p in (args.original_report, args.revised_report, args.draft, args.comments)))
            write_bundle(args.output, output)
            print(f"DRAFT bundle: {args.output}; {len(output)} files")
        elif args.command == "verify":
            verify_bundle(args.bundle)
            print("REGENERATED_EXACTLY; integrity only, not approval")
        else:
            captured = canonical(handoff_comments(load(args.report), load(args.handoff)))
            with args.output.open("xb") as handle:
                handle.write(captured)
            print("OPEN review capture; no decision inferred")
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

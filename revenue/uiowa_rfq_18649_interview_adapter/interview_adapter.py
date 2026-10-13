#!/usr/bin/env python3
"""UIOWA-034 -- interview notes to evidence records.

The completion condition is that a synthetic session imports into assessment
records **without turning a participant's statement into a verified
observation**. That is not a disclaimer, it is the whole design: an interview
produces testimony, and testimony is not observation. So every note gets an
explicit evidentiary status and the adapter will not promote one.

    STATED        someone said it. Testimony, attributed to a ROLE.
    ILLUSTRATED   statement plus a specific example -- still the participant's
                  own account of what happened.
    CORROBORATED  statement plus a named artifact that resolves in the source
                  register. Only this status may support a finding.
    DISPUTED      two participants conflict. BOTH notes are retained, neither is
                  promoted, and the adapter does not adjudicate.

The last one matters most. A disagreement is the most informative thing an
interview produces and the easiest to lose: resolve it and you have invented a
finding; drop it and you have hidden one. Where one side carries an artifact and
the other does not, the record says so and names the artifact to adjudicate
against -- that is a pointer for a human, not a verdict.

No field anywhere carries an individual's name. Participants are roles, and the
loader rejects a record that carries a personal-name or contact key at all.

Python 3 standard library only. No network.
"""

import argparse
import csv
import json
import hashlib
import math
from pathlib import Path
import tempfile
import os
import sys
import unicodedata

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"

STATED, ILLUSTRATED, CORROBORATED, DISPUTED = (
    "STATED", "ILLUSTRATED", "CORROBORATED", "DISPUTED")

# Keys that would attach a person to a record. The schema has no place for them
# and a file carrying one is refused rather than stripped: silently dropping a
# name leaves the operator believing it was accepted.
FORBIDDEN_KEYS = {"name", "participant_name", "person", "full_name", "email",
                  "employee_id", "netid", "username"}

# Narrow on purpose. A lint that flags ordinary prose gets switched off.
VAGUE_EXAMPLE_PHRASES = (
    "we generally", "generally keep", "we usually", "usually do", "as a rule",
    "most of the time", "we always try", "typically we", "we tend to",
)

RECORD_COLUMNS = [
    "record_id", "session_id", "group", "assessment_area", "question_id",
    "participant_id", "role", "status", "supports_finding", "basis",
    "stated_practice", "concrete_example", "corroborating_artifact",
    "artifact_locator", "disputed_with", "follow_up",
]


def norm(text):
    return unicodedata.normalize("NFC", text) if isinstance(text, str) else text


def fold(text):
    return " ".join(norm(str(text or "")).casefold().split())


def diag(severity, code, note_id, field, message):
    return {"severity": severity, "code": code, "note_id": note_id,
            "field": field, "message": message}


class LoadError(ValueError):
    pass


def _reject_personal_keys(node, path="$"):
    """Refuse a personal identifier anywhere in the tree, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                raise LoadError(f"{path}: object keys must be strings")
            if key.lower() in FORBIDDEN_KEYS:
                raise LoadError(
                    f"{path}.{key}: this schema records ROLES, not individuals. "
                    "Remove the field; it is refused rather than stripped so the "
                    "operator cannot believe a name was accepted.")
            _reject_personal_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_personal_keys(value, f"{path}[{index}]")


def _text(value, path, optional=False):
    if optional and value is None:
        return
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise LoadError(f"{path}: expected {'text or null' if optional else 'nonempty text'}")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise LoadError(f"{path}: text is not valid Unicode") from exc


def _finite(node):
    if isinstance(node, float) and not math.isfinite(node):
        raise LoadError("non-finite numeric value")
    if isinstance(node, dict):
        for value in node.values():
            _finite(value)
    elif isinstance(node, list):
        for value in node:
            _finite(value)


def _indexed_rows(payload, field, identity):
    rows = payload.get(field)
    if not isinstance(rows, list):
        raise LoadError(f"{field}: expected a list of objects")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise LoadError(f"{field}: expected an object for every row")
        value = row.get(identity)
        _text(value, f"{field}.{identity}")
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise LoadError(f"{field}.{identity}: whitespace/control character in identifier")
        canonical = norm(value)
        if canonical in seen:
            raise LoadError(f"{field}.{identity}: duplicate identifier {value!r}")
        seen.add(canonical)
    return rows


def _validate_capture(session, register):
    # The API enforces the same capture contract as the file loader. An identity
    # collision must be rejected before any dict comprehension loses an account.
    for label, payload in (("session", session), ("register", register)):
        if not isinstance(payload, dict):
            raise LoadError(f"{label}: expected an object")
        _reject_personal_keys(payload, label)
        _finite(payload)
    for key in ("session_id", "fiction_notice", "group"):
        _text(session.get(key), f"session.{key}")
    _text(session.get("session_source_id"), "session.session_source_id", optional=True)
    participants = _indexed_rows(session, "participants", "participant_id")
    questions = _indexed_rows(session, "questions", "question_id")
    notes = _indexed_rows(session, "notes", "note_id")
    sources = _indexed_rows(register, "sources", "source_id")
    for source in sources:
        for key in ("kind", "locator", "label", "as_of"):
            _text(source.get(key), f"source.{key}", optional=True)
    for participant in participants:
        _text(participant.get("role"), "participant.role")
        _text(participant.get("group"), "participant.group", optional=True)
    for question in questions:
        for key in ("assessment_area", "text"):
            _text(question.get(key), f"question.{key}")
    for note in notes:
        for key in ("participant_id", "question_id", "stated_practice"):
            _text(note.get(key), f"{note['note_id']}.{key}")
        for key in ("concrete_example", "corroborating_artifact", "disagrees_with", "follow_up"):
            _text(note.get(key), f"{note['note_id']}.{key}", optional=True)
        if note.get("disagrees_with") == note["note_id"]:
            raise LoadError(f"{note['note_id']}: a self-disagreement is not a second account")


def _load_snapshot(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise LoadError(f"duplicate JSON member: {key!r}")
            result[key] = value
        return result

    def constant(value):
        raise LoadError(f"non-finite JSON value: {value}")

    # One bounded read supplies both the parsed input and the receipt digest.
    with open(path, "rb") as handle:
        raw = handle.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise LoadError("input exceeds the 4 MiB capture limit")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                             parse_constant=constant)
        _finite(payload)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LoadError(f"invalid capture JSON: {exc}") from exc
    _reject_personal_keys(payload, os.path.basename(path))
    return payload, {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def load_json(path):
    return _load_snapshot(path)[0]


def adapt(session, register):
    _validate_capture(session, register)
    sources = {s["source_id"]: s for s in register["sources"]}
    participants = {p["participant_id"]: p for p in session["participants"]}
    questions = {q["question_id"]: q for q in session["questions"]}
    notes = {n["note_id"]: n for n in session["notes"]}
    session_source = session.get("session_source_id")

    diagnostics = []

    # Disagreement is symmetric whether or not both sides wrote it down. A note
    # that is contradicted and does not know it must still be marked, or the
    # unaware side would export as settled evidence.
    disputed_with = {}
    for note in session["notes"]:
        target = note.get("disagrees_with")
        if not target:
            continue
        if target not in notes:
            diagnostics.append(diag(
                ERROR, "DISAGREEMENT_TARGET_MISSING", note["note_id"], "disagrees_with",
                f"note {target!r} is not in this session; a disagreement whose other "
                "side is absent cannot be reviewed"))
            disputed_with.setdefault(note["note_id"], set()).add(target)
            continue
        disputed_with.setdefault(note["note_id"], set()).add(target)
        disputed_with.setdefault(target, set()).add(note["note_id"])
        if notes[target].get("disagrees_with") != note["note_id"]:
            diagnostics.append(diag(
                INFO, "DISAGREEMENT_MADE_MUTUAL", target, "disagrees_with",
                f"{note['note_id']} contradicts this note; marking both DISPUTED so "
                "the unaware side does not export as settled"))

    records = []
    for note in sorted(session["notes"], key=lambda n: n["note_id"]):
        note_id = note["note_id"]
        participant = participants.get(note["participant_id"])
        if participant is None:
            diagnostics.append(diag(
                ERROR, "UNKNOWN_PARTICIPANT", note_id, "participant_id",
                f"{note['participant_id']!r} is not in this session's participant list"))
            continue
        question = questions.get(note["question_id"])
        if question is None:
            diagnostics.append(diag(
                ERROR, "UNKNOWN_QUESTION", note_id, "question_id",
                f"{note['question_id']!r} is not in this session's question list"))
            continue

        artifact = note.get("corroborating_artifact")
        artifact_locator = None
        corroborated = False
        if artifact:
            source = sources.get(artifact)
            if source is None:
                diagnostics.append(diag(
                    ERROR, "ARTIFACT_NOT_IN_REGISTER", note_id, "corroborating_artifact",
                    f"{artifact!r} does not resolve in the source register; the note is "
                    "kept as testimony and is NOT corroborated"))
            elif artifact == session_source or fold(source.get("kind")) in {"interview", "interview_statement", "testimony"}:
                # Citing the interview as corroboration of the interview.
                diagnostics.append(diag(
                    ERROR, "SELF_CORROBORATION", note_id, "corroborating_artifact",
                    f"{artifact!r} is an interview record, so it cannot corroborate "
                    "interview testimony; corroboration needs a record the practice "
                    "produced, not a record of someone describing it"))
                artifact_locator = source.get("locator")
            elif (fold(source.get("kind")) not in {"document", "system_export"}
                  or not isinstance(source.get("locator"), str)
                  or not source["locator"].strip()):
                diagnostics.append(diag(
                    ERROR, "ARTIFACT_METADATA_INCOMPLETE", note_id, "corroborating_artifact",
                    f"{artifact!r} needs a supported document/system_export kind and a "
                    "nonempty locator; a registered name alone is not corroboration"))
            else:
                corroborated = True
                artifact_locator = source.get("locator")

        example = note.get("concrete_example")
        specific_example = bool(example)
        if example and any(p in fold(example) for p in VAGUE_EXAMPLE_PHRASES):
            specific_example = False
            diagnostics.append(diag(
                WARNING, "VAGUE_EXAMPLE", note_id, "concrete_example",
                "the example describes a habit rather than an instance, so it does "
                "not raise the note above STATED"))

        if note_id in disputed_with:
            status = DISPUTED
            others = ", ".join(sorted(disputed_with[note_id]))
            absent = sorted(target for target in disputed_with[note_id] if target not in notes)
            if absent:
                basis = (f"disagreement names absent account(s) {', '.join(absent)}; "
                         "counterpart must be supplied before review. This account is "
                         "retained; the adapter does not decide")
            elif corroborated:
                basis = (f"contradicted by {others}; this side carries artifact "
                         f"{artifact}. Adjudicate against that artifact — the adapter "
                         "does not decide")
            else:
                basis = (f"contradicted by {others}; no artifact on this side. Both "
                         "notes are retained and neither is promoted")
        elif corroborated:
            status = CORROBORATED
            basis = f"statement plus artifact {artifact} resolving to {artifact_locator}"
        elif specific_example:
            status = ILLUSTRATED
            basis = ("statement plus a specific example, still the participant's own "
                     "account; no artifact supplied")
        else:
            status = STATED
            basis = "testimony only; no artifact and no specific example supplied"

        records.append({
            "record_id": f"EV-{session['session_id']}-{note_id}",
            "session_id": session["session_id"],
            "group": participant.get("group") or session.get("group"),
            "assessment_area": question["assessment_area"],
            "question_id": note["question_id"],
            "participant_id": note["participant_id"],
            "role": participant["role"],
            "status": status,
            # The single load-bearing field. Only CORROBORATED is ever True.
            "supports_finding": status == CORROBORATED,
            "basis": basis,
            "stated_practice": norm(note.get("stated_practice")),
            "concrete_example": norm(example),
            "corroborating_artifact": artifact if corroborated else None,
            "artifact_locator": artifact_locator if corroborated else None,
            "disputed_with": ";".join(sorted(disputed_with.get(note_id, []))) or None,
            "follow_up": norm(note.get("follow_up")),
        })

    coverage = []
    for question in session["questions"]:
        answered = {r["participant_id"] for r in records
                    if r["question_id"] == question["question_id"]}
        missing = sorted(set(participants) - answered)
        coverage.append({
            "question_id": question["question_id"],
            "assessment_area": question["assessment_area"],
            "answered_by": sorted(answered),
            "not_covered_by": missing,
        })
        for participant_id in missing:
            # Absence of an answer is absence of evidence. It is never a gap.
            diagnostics.append(diag(
                INFO, "NOT_COVERED", question["question_id"], participant_id,
                f"{participants[participant_id]['role']} did not answer this question; "
                "recorded as not covered, which is not a finding about the practice"))

    return records, diagnostics, coverage


# ------------------------------------------------------------------ writing --

def csv_cell(value):
    if value is None:
        return "\\N"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = norm(str(value))
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("'", "\t", "\r", "\n")):
        text = "'" + text
    if text.startswith("\\"):
        text = "\\" + text
    return text


def md_cell(value):
    if value is None:
        return "—"
    text = norm(str(value)).replace("\\", "\\\\").replace("|", "\\|")
    return text.replace("\r\n", " ⏎ ").replace("\n", " ⏎ ").replace("\r", " ⏎ ")


def write_records_csv(path, records):
    with open(path, "x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(RECORD_COLUMNS)
        for record in records:
            writer.writerow([csv_cell(record.get(name)) for name in RECORD_COLUMNS])


def write_report(path, session, records, diagnostics, coverage):
    by_question = {}
    for record in records:
        by_question.setdefault(record["question_id"], []).append(record)
    questions = {q["question_id"]: q for q in session["questions"]}
    counts = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    with open(path, "x", encoding="utf-8") as fh:
        w = fh.write
        w(f"# Interview session {session['session_id']} — imported evidence records\n\n")
        w(f"**{session['fiction_notice']}**\n\n")
        w(f"{len(session['participants'])} participants, {len(session['questions'])} "
          f"questions, {len(records)} records.\n\n")
        w("| Status | Count | May support a finding |\n|---|---|---|\n")
        for status in (CORROBORATED, DISPUTED, ILLUSTRATED, STATED):
            w(f"| `{status}` | {counts.get(status, 0)} | "
              f"{'yes' if status == CORROBORATED else '**no**'} |\n")
        w("\nA participant's statement is testimony. Only a statement backed by a "
          "record the practice itself produced is marked as able to support a "
          "finding, and a contradicted statement is not promoted even when one side "
          "carries an artifact.\n\n")
        w("**Interpretation limit.** CORROBORATED means a declared document or "
          "system-export reference resolves in the supplied register. The adapter "
          "does not open it, authenticate it, or establish that its content supports "
          "the statement. `supports_finding` is eligibility for assessor review, "
          "not a verified finding.\n\n")

        for question_id in sorted(by_question):
            question = questions[question_id]
            w(f"## {question_id} — {question['text']}\n\n")
            w(f"*Assessment area: {question['assessment_area']}*\n\n")
            for record in sorted(by_question[question_id], key=lambda r: r["record_id"]):
                w(f"### {record['record_id']} · {record['role']} · `{record['status']}`\n\n")
                w(f"> {md_cell(record['stated_practice'])}\n\n")
                if record["concrete_example"]:
                    w(f"**Example given.** {md_cell(record['concrete_example'])}\n\n")
                w(f"**Basis.** {md_cell(record['basis'])}\n\n")
                if record["corroborating_artifact"]:
                    w(f"**Artifact.** `{record['corroborating_artifact']}` → "
                      f"`{record['artifact_locator']}`\n\n")
                if record["disputed_with"]:
                    present = {r["record_id"] for r in records}
                    unresolved = any(f"EV-{session['session_id']}-{other}" not in present
                                     for other in record["disputed_with"].split(";"))
                    retention = ("counterpart not imported; see the basis and capture review"
                                 if unresolved else "both notes retained")
                    w(f"**Contradicted by.** `{md_cell(record['disputed_with'])}` — "
                      f"{retention}; not adjudicated here.\n\n")
                if record["follow_up"]:
                    w(f"**Follow-up.** {md_cell(record['follow_up'])}\n\n")

        w("## Coverage\n\n")
        w("| Question | Area | Answered by | Not covered by |\n|---|---|---|---|\n")
        for item in coverage:
            w(f"| {item['question_id']} | {item['assessment_area']} | "
              f"{', '.join(item['answered_by']) or '—'} | "
              f"{', '.join(item['not_covered_by']) or '—'} |\n")
        w("\nA question a participant did not answer is recorded as not covered. "
          "That is absence of evidence about the practice, not evidence of a gap in "
          "it.\n\n")

        w("## Diagnostics\n\n")
        if not diagnostics:
            w("None.\n")
            return
        w("| Severity | Code | Note | Field | Message |\n|---|---|---|---|---|\n")
        for item in diagnostics:
            w(f"| {item['severity']} | `{item['code']}` | `{item['note_id']}` | "
              f"`{item['field']}` | {md_cell(item['message'])} |\n")


def _empty_output(out_dir):
    path = Path(out_dir).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise LoadError("output path and ancestors must not be symlinks")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise LoadError("output must be new or an empty directory; prior evidence is preserved")
    return path


def build(session_path, register_path, out_dir):
    session, session_binding = _load_snapshot(session_path)
    register, register_binding = _load_snapshot(register_path)
    records, diagnostics, coverage = adapt(session, register)
    output = _empty_output(out_dir)
    imported = {r["record_id"] for r in records}
    review = {
        "schema": "uiowa.interview-capture-review.v1",
        "fiction_notice": session["fiction_notice"],
        "state": "REVIEW_REQUIRED" if any(d["severity"] == ERROR for d in diagnostics) else "CAPTURE_IMPORTED",
        "inputs": {"session": session_binding, "register": register_binding},
        "input_notes": len(session["notes"]), "imported_records": len(records),
        "unimported_notes": [n for n in session["notes"]
                             if f"EV-{session['session_id']}-{n['note_id']}" not in imported],
        "captured_artifact_references": {n["note_id"]: n.get("corroborating_artifact")
                                         for n in session["notes"]},
        "source_authenticity_established": False, "finding_verified": False,
    }
    # Render entirely before publishing. A failure in JSON/CSV/Markdown rendering
    # cannot damage an earlier bundle or create a misleading partial destination.
    with tempfile.TemporaryDirectory(prefix="uiowa034-render-") as staging:
        stage = Path(staging)
        payload = {"session_id": session["session_id"],
                   "fiction_notice": session["fiction_notice"],
                   "records": records, "diagnostics": diagnostics, "coverage": coverage}
        (stage / "evidence_records.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        write_records_csv(stage / "evidence_records.csv", records)
        write_report(stage / "session_report.md", session, records, diagnostics, coverage)
        files = {p.name: p.read_bytes() for p in sorted(stage.iterdir())}
    review["outputs"] = {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                         for name, raw in files.items()}
    review_bytes = (json.dumps(review, ensure_ascii=False, sort_keys=True, indent=2,
                              allow_nan=False) + "\n").encode("utf-8")
    _empty_output(output)  # freshness at publication, not just at planning
    output.mkdir(parents=True, exist_ok=True)
    for name, raw in [*files.items(), ("capture_review.json", review_bytes)]:
        with (output / name).open("xb") as handle:
            handle.write(raw)
    # The complete receipt is written last. An I/O interruption leaves partial
    # artifacts but never overwrites a prior one; use a fresh private directory.
    return records, diagnostics, coverage


def main(argv=None):
    root = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["import", "check"])
    parser.add_argument("--session", default=os.path.join(root, "data", "session.json"))
    parser.add_argument("--register",
                        default=os.path.join(root, "data", "source_register.json"))
    parser.add_argument("--out", required=True, help="new or empty output directory; never overwrite")
    args = parser.parse_args(argv)

    try:
        records, diagnostics, coverage = build(args.session, args.register, args.out)
    except (LoadError, OSError, UnicodeError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    counts = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    errors = [d for d in diagnostics if d["severity"] == ERROR]
    print(f"records={len(records)} "
          + " ".join(f"{k}={counts.get(k, 0)}"
                     for k in (CORROBORATED, DISPUTED, ILLUSTRATED, STATED))
          + f" supports_finding={sum(1 for r in records if r['supports_finding'])}"
          + f" errors={len(errors)}")
    for item in diagnostics:
        if item["severity"] != INFO:
            print(f"  {item['severity']:<7} {item['code']:<28} {item['note_id']:<6} "
                  f"{item['field']}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

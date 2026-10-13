#!/usr/bin/env python3
"""Offline declared-reuse journal and portable handoff for ReuseLedger."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import types

# Replay must not add a __pycache__ directory to the exact bundle inventory.
sys.dont_write_bytecode = True

# Load the unchanged core from these bytes, independently of an earlier import
# or timestamp-based bytecode cache. Keep the source generation for the receipt.
_WORKFLOW_PATH = Path(__file__).resolve()
_CORE_PATH = _WORKFLOW_PATH.with_name("reuseledger.py")
_WORKFLOW_SOURCE = _WORKFLOW_PATH.read_bytes()
_CORE_SOURCE = _CORE_PATH.read_bytes()
core = types.ModuleType("reuseledger_workflow_core")
core.__file__ = str(_CORE_PATH)
exec(compile(_CORE_SOURCE, str(_CORE_PATH), "exec"), core.__dict__)

EVENT_SCHEMA = "nci-reuseledger-event/v1"
JOURNAL_SCHEMA = "nci-reuseledger-journal/v1"
REPORT_SCHEMA = "nci-reuseledger-reuse-report/v1"
BUNDLE_SCHEMA = "nci-reuseledger-bundle/v1"
EVENT_KEYS = {"schema", "id", "state", "recorded_on", "occurred_on", "purpose",
              "downstream", "upstream_ids", "credit_refs"}
JOURNAL_KEYS = {"schema", "project", "manifest_file_sha256", "manifest_semantic_sha256",
                "entries", "semantic_sha256"}
BUNDLE_NAMES = {"manifest.json", "packet.json", "journal.json", "reuse_report.json",
                "reuse_report.md", "reuseledger.py", "reuse_workflow.py", "RECEIPT.json"}
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class WorkflowError(ValueError):
    """Input or handoff does not satisfy the declared-reuse contract."""


def exact(value, keys, where):
    if type(value) is not dict or set(value) != keys:
        raise WorkflowError(f"{where}: expected exactly {', '.join(sorted(keys))}")


def text(value, where, limit=1000):
    if type(value) is not str or not value.strip() or len(value.strip()) > limit:
        raise WorkflowError(f"{where}: expected nonempty text of at most {limit} characters")
    return value.strip()


def identifier(value, where):
    value = text(value, where)
    if not core.PID.fullmatch(value):
        raise WorkflowError(f"{where}: expected HTTP(S), DOI or URN identifier")
    return value


def date(value, where):
    if type(value) is not str or not DATE.fullmatch(value):
        raise WorkflowError(f"{where}: expected YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise WorkflowError(f"{where}: invalid calendar date") from exc
    return value


def strict_json(raw):
    if type(raw) is not bytes:
        raise WorkflowError("JSON input must be bytes")
    def reject_constant(value):
        raise WorkflowError(f"non-finite JSON value: {value}")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=core.strict_object,
                          parse_constant=reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise WorkflowError(f"invalid JSON: {exc}") from exc


def dump(value):
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                           allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise WorkflowError(f"cannot encode JSON: {exc}") from exc


def canonical(value):
    try:
        return core.canon(value)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise WorkflowError(f"cannot canonicalize JSON: {exc}") from exc


def manifest_context(manifest, raw):
    parsed = strict_json(raw)
    if canonical(parsed) != canonical(manifest):
        raise WorkflowError("manifest object does not match supplied raw JSON")
    try:
        normalized = core.normalize(parsed)
    except (core.LedgerError, RecursionError, TypeError, ValueError) as exc:
        raise WorkflowError(f"manifest: {exc}") from exc
    return normalized, {row["id"]: row for row in normalized["outputs"]}


def ids(value, where, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= 1000:
        raise WorkflowError(f"{where}: expected {minimum}..1000 identifiers")
    normalized = [identifier(item, f"{where}[{i}]") for i, item in enumerate(value)]
    if len(set(normalized)) != len(normalized):
        raise WorkflowError(f"{where}: duplicate identifiers")
    return sorted(normalized)


def normalize_event(event, outputs):
    exact(event, EVENT_KEYS, "event")
    if event["schema"] != EVENT_SCHEMA:
        raise WorkflowError("event.schema mismatch")
    state = event["state"]
    if type(state) is not str or state not in {"planned", "reported"}:
        raise WorkflowError("event.state: expected planned or reported")
    recorded = date(event["recorded_on"], "event.recorded_on")
    occurred = event["occurred_on"]
    if state == "planned":
        if occurred is not None:
            raise WorkflowError("planned event requires occurred_on=null")
    else:
        occurred = date(occurred, "event.occurred_on")
        if occurred > recorded:
            raise WorkflowError("reported occurred_on must not follow recorded_on")
    exact(event["downstream"], {"id", "version"}, "event.downstream")
    downstream = event["downstream"]
    upstream = ids(event["upstream_ids"], "event.upstream_ids", 1)
    for oid in upstream:
        if oid not in outputs:
            raise WorkflowError(f"unknown upstream output: {oid}")
    return {
        "schema": EVENT_SCHEMA, "id": identifier(event["id"], "event.id"),
        "state": state, "recorded_on": recorded, "occurred_on": occurred,
        "purpose": text(event["purpose"], "event.purpose", 4000),
        "downstream": {"id": identifier(downstream["id"], "event.downstream.id"),
                       "version": None if downstream["version"] is None else
                       text(downstream["version"], "event.downstream.version", 500)},
        "upstream_ids": upstream,
        "credit_refs": None if event["credit_refs"] is None else
                       ids(event["credit_refs"], "event.credit_refs"),
    }


def seal(value, key):
    result = dict(value)
    result[key] = core.sha(canonical(value))
    return result


def empty_journal(normalized, raw):
    return {"schema": JOURNAL_SCHEMA, "project": normalized["project"],
            "manifest_file_sha256": core.sha(raw),
            "manifest_semantic_sha256": core.sha(canonical(normalized)), "entries": []}


def make_entry(event, entries, outputs):
    if len(entries) >= 10000:
        raise WorkflowError("journal permits at most 10000 records")
    event = normalize_event(event, outputs)
    if any(entry["event"]["id"] == event["id"] for entry in entries):
        raise WorkflowError("duplicate event id")
    if entries and event["recorded_on"] < entries[-1]["event"]["recorded_on"]:
        raise WorkflowError("recorded_on must be nondecreasing")
    bindings = [{"output_id": oid,
                 "output_metadata_sha256": core.sha(canonical(outputs[oid])),
                 "declared_fixity": outputs[oid]["fixity"]} for oid in event["upstream_ids"]]
    return seal({"sequence": len(entries) + 1, "event": event,
                 "upstream_bindings": bindings,
                 "previous_entry_sha256": entries[-1]["entry_sha256"] if entries else None},
                "entry_sha256")


def init_journal(manifest, raw_bytes):
    normalized, _ = manifest_context(manifest, raw_bytes)
    return seal(empty_journal(normalized, raw_bytes), "semantic_sha256")


def validate_journal(manifest, raw_bytes, journal):
    normalized, outputs = manifest_context(manifest, raw_bytes)
    exact(journal, JOURNAL_KEYS, "journal")
    entries = journal["entries"]
    if type(entries) is not list or len(entries) > 10000:
        raise WorkflowError("journal.entries: expected 0..10000 entries")
    expected = empty_journal(normalized, raw_bytes)
    for entry in entries:
        exact(entry, {"sequence", "event", "upstream_bindings", "previous_entry_sha256",
                      "entry_sha256"}, "journal entry")
        derived = make_entry(entry["event"], expected["entries"], outputs)
        if canonical(entry) != canonical(derived):
            raise WorkflowError("journal entry derivation mismatch")
        expected["entries"].append(derived)
    expected = seal(expected, "semantic_sha256")
    if canonical(journal) != canonical(expected):
        raise WorkflowError("journal manifest binding or semantic digest mismatch")
    return expected


def record_event(manifest, raw_bytes, journal, event):
    result = validate_journal(manifest, raw_bytes, journal)
    _, outputs = manifest_context(manifest, raw_bytes)
    result.pop("semantic_sha256")
    result["entries"].append(make_entry(event, result["entries"], outputs))
    return seal(result, "semantic_sha256")


def reuse_report(journal):
    records = [{**entry["event"], "sequence": entry["sequence"],
                "upstream_bindings": entry["upstream_bindings"]} for entry in journal["entries"]]
    return {"schema": REPORT_SCHEMA, "project": journal["project"],
            "manifest_file_sha256": journal["manifest_file_sha256"],
            "journal_semantic_sha256": journal["semantic_sha256"],
            "basis": "DECLARED_RECORDS_ONLY",
            "summary": {
                "total_records": len(records),
                "planned_records": sum(r["state"] == "planned" for r in records),
                "reported_records": sum(r["state"] == "reported" for r in records),
                "credit_unknown_records": sum(r["credit_refs"] is None for r in records),
                "no_credit_refs_records": sum(r["credit_refs"] == [] for r in records),
                "declared_credit_refs_records": sum(bool(r["credit_refs"]) for r in records),
            }, "records": records}


def md(value):
    # Display supplied metadata as text; do not allow it to create report structure.
    value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = value.replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", value)


def report_markdown(report):
    lines = ["# ReuseLedger declared-reuse handoff", "", md(report["project"]), "",
             "Basis: DECLARED_RECORDS_ONLY. Counts describe records, not independent reuse or impact.", ""]
    lines += [f"- {key.replace('_', ' ')}: {value}" for key, value in report["summary"].items()]
    if not report["records"]:
        lines += ["", "No declared reuse records."]
    for record in report["records"]:
        credit = record["credit_refs"]
        lines += ["", f"## Record {record['sequence']}", "",
                  f"- ID: {md(record['id'])}", f"- State: {record['state']}",
                  f"- Recorded on: {record['recorded_on']}",
                  f"- Occurred on: {record['occurred_on'] or 'not applicable (planned)'}",
                  f"- Purpose: {md(record['purpose'])}",
                  f"- Downstream: {md(record['downstream']['id'])}",
                  f"- Downstream version: {md(record['downstream']['version']) if record['downstream']['version'] is not None else 'UNKNOWN'}",
                  "- Credit: " + ("UNKNOWN" if credit is None else "NONE SUPPLIED" if not credit else
                                   "DECLARED REFERENCES: " + ", ".join(md(ref) for ref in credit))]
        for binding in record["upstream_bindings"]:
            fixity = binding["declared_fixity"]
            lines += [f"- Upstream: {md(binding['output_id'])}",
                      f"  - Output metadata SHA-256: {binding['output_metadata_sha256']}",
                      "  - Declared content fixity: " + ("UNKNOWN" if fixity is None else
                          f"{fixity['sha256']} / {fixity['bytes']} bytes (not content-verified)")]
    lines += ["", f"Manifest bytes SHA-256: {report['manifest_file_sha256']}",
              f"Journal semantic SHA-256: {report['journal_semantic_sha256']}", "",
              "These are supplied declarations. Identifiers are not fetched; content, real-world reuse, credit, rights and consent are not independently verified.",
              "Hashes establish consistency with supplied inputs, not authenticity. No scientific or clinical conclusion is made.", ""]
    return "\n".join(lines).encode("utf-8")


def build_files(manifest, raw_bytes, journal):
    journal = validate_journal(manifest, raw_bytes, journal)
    report = reuse_report(journal)
    try:
        if (_WORKFLOW_PATH.read_bytes() != _WORKFLOW_SOURCE or
                _CORE_PATH.read_bytes() != _CORE_SOURCE):
            raise WorkflowError("source files changed after startup; start a fresh process")
        packet = core.compile_packet(strict_json(raw_bytes), core.sha(raw_bytes))
        files = {"manifest.json": raw_bytes, "packet.json": dump(packet),
                 "journal.json": dump(journal), "reuse_report.json": dump(report),
                 "reuse_report.md": report_markdown(report),
                 "reuseledger.py": _CORE_SOURCE,
                 "reuse_workflow.py": _WORKFLOW_SOURCE}
    except (core.LedgerError, OSError, RecursionError) as exc:
        raise WorkflowError(str(exc)) from exc
    receipt = {"schema": BUNDLE_SCHEMA,
               "manifest_file_sha256": core.sha(raw_bytes),
               "journal_semantic_sha256": journal["semantic_sha256"],
               "files": [{"filename": name, "sha256": core.sha(raw), "bytes": len(raw)}
                         for name, raw in sorted(files.items())]}
    files["RECEIPT.json"] = dump(receipt)
    return files


def verify_bundle(directory):
    directory = Path(directory)
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise WorkflowError("bundle must be a regular directory")
        items = list(directory.iterdir())
        if {item.name for item in items} != BUNDLE_NAMES:
            raise WorkflowError("bundle file inventory mismatch")
        if any(item.is_symlink() or not item.is_file() for item in items):
            raise WorkflowError("bundle requires eight regular files")
        actual = {item.name: item.read_bytes() for item in items}
        manifest = strict_json(actual["manifest.json"])
        journal = strict_json(actual["journal.json"])
        expected = build_files(manifest, actual["manifest.json"], journal)
        for name, raw in expected.items():
            if raw != actual[name]:
                raise WorkflowError(f"bundle derivation mismatch: {name}")
        return strict_json(expected["reuse_report.json"])
    except OSError as exc:
        raise WorkflowError(f"bundle I/O: {exc}") from exc


def write_new(path, raw):
    try:
        with Path(path).open("xb") as stream:
            stream.write(raw)
    except OSError as exc:
        raise WorkflowError(f"cannot create new output {path}: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "record", "bundle"):
        command = sub.add_parser(name)
        command.add_argument("manifest", type=Path)
        if name != "init":
            command.add_argument("journal", type=Path)
        if name == "record":
            command.add_argument("event", type=Path)
        command.add_argument("--out", type=Path, required=True)
    sub.add_parser("verify").add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            report = verify_bundle(args.directory)
            print("VALID: declared-record bundle;", report["summary"]["total_records"], "records")
            return 0
        raw = args.manifest.read_bytes()
        manifest = strict_json(raw)
        if args.command == "init":
            write_new(args.out, dump(init_journal(manifest, raw)))
        else:
            journal = strict_json(args.journal.read_bytes())
            if args.command == "record":
                event = strict_json(args.event.read_bytes())
                write_new(args.out, dump(record_event(manifest, raw, journal, event)))
            else:
                files = build_files(manifest, raw, journal)
                args.out.mkdir()
                for name in sorted(set(files) - {"RECEIPT.json"}) + ["RECEIPT.json"]:
                    write_new(args.out / name, files[name])
        print("CREATED:", args.out)
        return 0
    except (WorkflowError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

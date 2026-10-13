"""Proposed offline transport journal around the unchanged SMART synthetic shadow.

No endpoint is contacted and no authoritative mutation is performed. DISPATCH
starts a logical attempt; NOT_SENT is explicit fixture evidence that nothing was
sent, not an inference from a timeout or HTTP response. All time is logical.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tempfile
import types
import uuid
from pathlib import Path

SCHEMA = "wayne-smart-offline-transcript/v1"
REPORT_SCHEMA = "wayne-smart-offline-acceptance/v1"
MAX_BYTES = 1024 * 1024
MAX_EVENTS = 256
DEFAULT_PROFILE = {"profile_id": "PROPOSED_OFFLINE_V1", "max_attempts": 3,
                   "backoff_base_ms": 100, "backoff_cap_ms": 1000}
CORE_HASHES = {
    "wayne_smart_reconcile.py": "13cc35d9baa99d9d2d84462b6993fb92ed13ae61dbc8d869b7c1e7a3ea55072d",
    "fixtures/wayne_150_states.json": "0313d184be3de873291c456313dbd74440de10c88d95a205b21101cad5e44d14",
    "fixtures/manifest.json": "00751ebcf51d22b3a584923b300c2ea101c0c03d6fda68b404902fb15a94a5ed",
}


class LabError(ValueError):
    """Invalid input, changed baseline, or inconsistent simulated receipt."""


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise LabError("Value must be finite, acyclic JSON data.") from exc


def digest(value):
    try:
        return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    except UnicodeError as exc:
        raise LabError("Text must contain valid Unicode scalar values.") from exc


def _keys(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise LabError(f"{label} has missing or unexpected fields.")


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise LabError(f"{label} must be an integer from {low} to {high}.")


def _identifier(value, label):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", value):
        raise LabError(f"{label} must be a bounded ASCII identifier.")


def strict_json_bytes(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise LabError("Transcript must be UTF-8 JSON bytes of at most 1 MiB.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise LabError("Duplicate JSON property.")
            result[key] = value
        return result
    def invalid_constant(value):
        raise LabError(f"Non-finite JSON constant: {value}")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=invalid_constant)
        digest(result)
        return result
    except LabError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise LabError("Invalid UTF-8 JSON document.") from exc


def load_baseline(core_dir=None):
    """Execute captured, SHA-pinned original bytes with captured fixture files.

    The three consumed files are copied once into an ephemeral directory. The
    temporary module is uniquely named and removed; sys.path is never changed.
    Existing core source, records, manifest and truth labels are not modified.
    """
    source = Path(core_dir) if core_dir is not None else Path(__file__).resolve().parent.parent / "wayne-smart-api"
    captured = {}
    bindings = []
    for name, expected in CORE_HASHES.items():
        try:
            raw = (source / name).read_bytes()
        except OSError as exc:
            raise LabError(f"Baseline file unavailable: {name}") from exc
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise LabError(f"Baseline source binding changed: {name}")
        captured[name] = raw
        bindings.append({"path": f"revenue/wayne-smart-api/{name}", "bytes": len(raw),
                         "sha256": actual, "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()})
    with tempfile.TemporaryDirectory(prefix="wayne-shadow-captured-") as temp:
        root = Path(temp)
        for name, raw in captured.items():
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        name = "_wayne_captured_" + uuid.uuid4().hex
        module = types.ModuleType(name)
        module.__file__ = str(root / "wayne_smart_reconcile.py")
        sys.modules[name] = module
        try:
            exec(compile(captured["wayne_smart_reconcile.py"], module.__file__, "exec"), module.__dict__)
            records, manifest = module.load_fixture()
            baseline = module.run_default()
        except Exception as exc:
            raise LabError(f"Unchanged baseline execution failed: {exc}") from exc
        finally:
            sys.modules.pop(name, None)
    return {"records": records, "manifest": manifest, "baseline": baseline,
            "source_bindings": bindings}


def request_sha256(record):
    """Logical mutation identity excludes observational record/source identifiers."""
    return digest({key: record[key] for key in
                   ("mutation_key", "commit_id", "ledger_account", "expected_cents")})


def validate_transcript(document):
    # Canonical roundtrip also rejects Python-only objects, cycles and lone surrogates.
    encoded = canonical(document).encode("utf-8", errors="strict")
    if len(encoded) > MAX_BYTES:
        raise LabError("Transcript exceeds 1 MiB.")
    document = strict_json_bytes(encoded)
    _keys(document, ("schema", "synthetic_only", "profile", "events"), "Transcript")
    if document["schema"] != SCHEMA or document["synthetic_only"] is not True:
        raise LabError("Only the synthetic offline transcript schema is accepted.")
    profile = document["profile"]
    _keys(profile, DEFAULT_PROFILE, "Profile")
    if profile["profile_id"] != "PROPOSED_OFFLINE_V1":
        raise LabError("Unknown proposed profile.")
    _integer(profile["max_attempts"], 1, 8, "max_attempts")
    _integer(profile["backoff_base_ms"], 1, 10000, "backoff_base_ms")
    _integer(profile["backoff_cap_ms"], profile["backoff_base_ms"], 60000, "backoff_cap_ms")
    events = document["events"]
    if type(events) is not list or not 1 <= len(events) <= MAX_EVENTS:
        raise LabError("Transcript must contain 1 to 256 ordered events.")
    seen = set()
    previous = -1
    for event in events:
        if type(event) is not dict or type(event.get("type")) is not str:
            raise LabError("Event must be an object with a type.")
        kind = event["type"]
        extra = {"SUBMIT": ("record_id", "payload_sha256"), "DISPATCH": (),
                 "NOT_SENT": ("dispatch_event_id",), "ACK_LOST": ("dispatch_event_id",),
                 "OBSERVE": ("record_id", "payload_sha256", "commit_id", "observation", "posted_cents", "evidence_id")}
        if kind not in extra:
            raise LabError("Unknown event type.")
        _keys(event, ("event_id", "at_ms", "type", "key") + extra[kind], "Event")
        _identifier(event["event_id"], "event_id")
        _identifier(event["key"], "key")
        if not event["key"].startswith("SYNTH-"):
            raise LabError("Keys must have the SYNTH- prefix.")
        if event["event_id"] in seen:
            raise LabError("Duplicate event_id; replay the complete transcript instead.")
        seen.add(event["event_id"])
        _integer(event["at_ms"], 0, 10**12, "at_ms")
        if event["at_ms"] < previous:
            raise LabError("Logical event time must be nondecreasing.")
        previous = event["at_ms"]
        if kind in ("NOT_SENT", "ACK_LOST"):
            _identifier(event["dispatch_event_id"], "dispatch_event_id")
        if kind in ("SUBMIT", "OBSERVE"):
            _identifier(event["record_id"], "record_id")
            if type(event["payload_sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", event["payload_sha256"]):
                raise LabError("payload_sha256 must be a lowercase SHA-256 digest.")
        if kind == "OBSERVE":
            _identifier(event["commit_id"], "commit_id")
            _identifier(event["evidence_id"], "evidence_id")
            if not event["evidence_id"].startswith("SYNTH-"):
                raise LabError("Evidence IDs must have the SYNTH- prefix.")
            if event["observation"] not in ("COMMITTED", "NOT_COMMITTED", "UNKNOWN"):
                raise LabError("Unknown observation.")
            if event["observation"] == "COMMITTED":
                _integer(event["posted_cents"], -(10**15), 10**15, "posted_cents")
            elif event["posted_cents"] is not None:
                raise LabError("Uncommitted/unknown observations must not claim posted cents.")
    return document


def run_transcript(document, core_dir=None):
    try:
        document = validate_transcript(document)
    except UnicodeError as exc:
        raise LabError("Text must contain valid Unicode scalar values.") from exc
    source = load_baseline(core_dir)
    records = {row["record_id"]: row for row in source["records"]}
    profile = document["profile"]
    journal, mutation_owners, observations, trace = {}, {}, {}, []
    for event in document["events"]:
        kind, key, now = event["type"], event["key"], event["at_ms"]
        entry = journal.get(key)
        before = entry["state"] if entry else "ABSENT"
        result = "HOLD_INVALID_TRANSITION"
        if kind == "SUBMIT":
            record = records.get(event["record_id"])
            if record is None:
                raise LabError("SUBMIT references a record outside the frozen baseline.")
            expected = request_sha256(record)
            if event["payload_sha256"] != expected:
                result = "HOLD_PAYLOAD_MISMATCH"
            elif entry:
                result = "DUPLICATE_NOOP" if entry["payload_sha256"] == expected else "HOLD_KEY_PAYLOAD_CONFLICT"
            elif record["mutation_key"] in mutation_owners:
                result = "HOLD_MUTATION_KEY_CONFLICT"
            else:
                state = "READY" if record["truth_status"] == "RECONCILED" else "HOLD_BASELINE_STATUS"
                entry = {"key": key, "record_id": record["record_id"], "mutation_key": record["mutation_key"],
                         "payload_sha256": expected, "commit_id": record["commit_id"],
                         "expected_cents": record["expected_cents"], "source_uri": record["source_uri"],
                         "baseline_status": record["truth_status"], "state": state, "attempts": 0,
                         "active_dispatch_event_id": None,
                         "retry_at_ms": None, "posted_cents": None, "variance_cents": 0,
                         "accepted_observations": 0}
                journal[key] = entry
                mutation_owners[record["mutation_key"]] = key
                result = state
        elif entry and kind == "DISPATCH":
            if entry["state"] == "READY" or (entry["state"] == "RETRY_WAIT" and now >= entry["retry_at_ms"]):
                if entry["attempts"] >= profile["max_attempts"]:
                    entry["state"] = result = "HOLD_RETRY_EXHAUSTED"
                else:
                    entry["attempts"] += 1
                    entry["active_dispatch_event_id"] = event["event_id"]
                    entry["retry_at_ms"] = None
                    entry["state"] = result = "IN_FLIGHT"
            elif entry["state"] == "RETRY_WAIT":
                result = "RETRY_NOT_DUE"
            elif entry["state"] == "COMMITTED":
                result = "DUPLICATE_NOOP"
            elif entry["state"] == "HOLD_UNKNOWN_COMMIT":
                result = "HOLD_UNKNOWN_COMMIT"
        elif entry and kind in ("NOT_SENT", "ACK_LOST") and entry["state"] == "IN_FLIGHT":
            if event["dispatch_event_id"] != entry["active_dispatch_event_id"]:
                result = "HOLD_STALE_ATTEMPT"
            elif kind == "ACK_LOST":
                entry["state"] = result = "HOLD_UNKNOWN_COMMIT"
            elif entry["attempts"] >= profile["max_attempts"]:
                entry["state"] = result = "HOLD_RETRY_EXHAUSTED"
            else:
                delay = min(profile["backoff_cap_ms"], profile["backoff_base_ms"] * 2 ** (entry["attempts"] - 1))
                entry["retry_at_ms"] = now + delay
                entry["state"] = result = "RETRY_WAIT"
        elif entry and kind == "OBSERVE":
            evidence = {field: event[field] for field in ("key", "record_id", "payload_sha256", "commit_id", "observation", "posted_cents")}
            prior = observations.get(event["evidence_id"])
            if any(event[field] != entry[field] for field in ("record_id", "payload_sha256", "commit_id")):
                result = "HOLD_OBSERVATION_BINDING"
            elif prior is not None:
                result = "DUPLICATE_NOOP" if prior == evidence else "HOLD_EVIDENCE_CONFLICT"
            elif entry["state"] not in ("IN_FLIGHT", "HOLD_UNKNOWN_COMMIT"):
                result = "HOLD_INVALID_TRANSITION"
            else:
                observations[event["evidence_id"]] = evidence
                if event["observation"] == "UNKNOWN":
                    entry["state"] = result = "HOLD_UNKNOWN_COMMIT"
                elif event["observation"] == "NOT_COMMITTED":
                    entry["state"] = result = "HOLD_NOT_COMMITTED_REVIEW"
                else:
                    entry["posted_cents"] = event["posted_cents"]
                    entry["variance_cents"] = event["posted_cents"] - entry["expected_cents"]
                    entry["state"] = result = "HOLD_LEDGER_VARIANCE" if entry["variance_cents"] else "COMMITTED"
                    if not entry["variance_cents"]:
                        entry["accepted_observations"] = 1
        trace.append({"event": copy.deepcopy(event), "state_before": before, "result": result,
                      "state_after": entry["state"] if entry else "ABSENT",
                      "attempts": entry["attempts"] if entry else 0,
                      "retry_at_ms": entry["retry_at_ms"] if entry else None,
                      "active_dispatch_event_id": entry["active_dispatch_event_id"] if entry else None,
                      "variance_cents": entry["variance_cents"] if entry else None})
    operations = list(journal.values())
    holds = [item["event"]["event_id"] for item in trace if item["result"].startswith("HOLD_")]
    unresolved = [item["key"] for item in operations if item["state"] != "COMMITTED"]
    report = {"schema": REPORT_SCHEMA, "status": "PROPOSED_SYNTHETIC_ACCEPTANCE_ONLY",
              "synthetic_only": True, "profile": profile, "transcript_sha256": digest(document),
              "source_bindings": source["source_bindings"], "baseline": source["baseline"],
              "baseline_expanded_records_sha256": source["manifest"]["expanded_records_sha256"],
              "operations": operations, "events": trace,
              "summary": {"operations": len(operations), "events": len(trace),
                          "logical_attempts": sum(item["attempts"] for item in operations),
                          "accepted_commit_observations": sum(item["accepted_observations"] for item in operations),
                          "observed_variance_cents": sum(item["variance_cents"] for item in operations),
                          "nonzero_variance_operations": sum(item["variance_cents"] != 0 for item in operations),
                          "hold_event_ids": holds, "unresolved_keys": unresolved,
                          "disposition": "HOLD_REVIEW_REQUIRED" if holds or unresolved else "SIMULATION_RECONCILED"},
              "authority": {"buyer_approved": False, "production_ready": False,
                            "endpoint_contacted": False, "authoritative_writes": 0,
                            "submission_authorized": False, "payment_authorized": False},
              "limitations": ["Proposed offline contract; actual SMART endpoints, idempotency and commit-query semantics are unavailable.",
                              "NOT_SENT is injected evidence of no send; a timeout never establishes it.",
                              "After uncertain commit only a matching injected observation can resolve state; this lab never blindly resends.",
                              "Receipt digests bind reproducible synthetic content; they are not signatures or customer approval."]}
    report["receipt_sha256"] = digest({"domain": REPORT_SCHEMA, "report": report})
    return report


def verify_report(report, document, core_dir=None):
    expected = run_transcript(document, core_dir)
    if type(report) is not dict or canonical(report) != canonical(expected):
        raise LabError("Report does not match replay of the source-bound transcript.")
    return True


def render_markdown(report):
    """Readable projection retains every event/operation, including holds."""
    def cell(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace("|", "&#124;").replace("\n", " ")
    lines = ["# Wayne SMART proposed offline acceptance", "", report["status"], "",
             f"Receipt: `{report['receipt_sha256']}`", f"Transcript: `{report['transcript_sha256']}`", "",
             "No endpoints contacted; no authoritative writes, buyer approval or payment authority.", "",
             "## Unchanged original baseline", "", "```json", json.dumps(report["baseline"], sort_keys=True, indent=2), "```", "",
             "## Source bindings", "", "| Source | SHA-256 |", "| --- | --- |"]
    lines += [f"| {cell(row['path'])} | `{row['sha256']}` |" for row in report["source_bindings"]]
    lines += ["", "## Proposed profile and summary", "", "```json", json.dumps({"profile": report["profile"], "summary": report["summary"]}, sort_keys=True, indent=2), "```", "",
              "## Operations", "", "| Key | Record | State | Attempts | Expected cents | Observed cents | Signed variance |", "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for row in report["operations"]:
        lines.append("| " + " | ".join(cell(row[k]) for k in ("key", "record_id", "state", "attempts", "expected_cents", "posted_cents", "variance_cents")) + " |")
    lines += ["", "## Every event in input order", "", "| Event | Time ms | Key | Type | Dispatch reference | Evidence | Reported cents | Result | State after | Attempts | Retry due ms | Signed variance |", "| --- | ---: | --- | --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: |"]
    for row in report["events"]:
        event = row["event"]
        values = [event["event_id"], event["at_ms"], event["key"], event["type"], event.get("dispatch_event_id", "—"), event.get("evidence_id", "—"), event.get("posted_cents", "—"), row["result"], row["state_after"], row["attempts"], row["retry_at_ms"], row["variance_cents"]]
        lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += ["", "## Exact event claims", "",
              "These supplied claims include observation type, record, request digest, commit and dispatch references; a visible claim is not an accepted fact.",
              "", "```json", json.dumps([row["event"] for row in report["events"]], sort_keys=True, indent=2), "```", ""]
    lines += ["", "## Limitations", ""] + ["- " + item for item in report["limitations"]] + [""]
    return "\n".join(lines)


def write_bundle(document, output_dir, core_dir=None):
    """Prepare all contents before creating a new directory; never overwrite."""
    report = run_transcript(document, core_dir)
    members = {"transcript.json": json.dumps(validate_transcript(document), sort_keys=True, indent=2) + "\n",
               "report.json": json.dumps(report, sort_keys=True, indent=2) + "\n",
               "report.md": render_markdown(report)}
    destination = Path(output_dir)
    try:
        destination.mkdir(parents=False, exist_ok=False)
        for name, text in members.items():
            with (destination / name).open("x", encoding="utf-8", newline="\n") as output:
                output.write(text)
    except OSError as exc:
        raise LabError("Output must be a new writable directory; interruption may leave a partial new directory.") from exc
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path, help="Replay and compare an existing report JSON")
    args = parser.parse_args(argv)
    if (args.out is None) == (args.verify is None):
        parser.error("Choose exactly one of --out or --verify.")
    try:
        raw = args.transcript.read_bytes()
        document = strict_json_bytes(raw)
        if args.verify:
            verify_report(strict_json_bytes(args.verify.read_bytes()), document)
            print("OFFLINE_REPLAY_VERIFIED")
        else:
            report = write_bundle(document, args.out)
            print(json.dumps({"receipt_sha256": report["receipt_sha256"], "disposition": report["summary"]["disposition"]}, sort_keys=True))
        return 0
    except (LabError, OSError) as exc:
        print(f"Offline acceptance refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

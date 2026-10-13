"""Deterministic synthetic operator rehearsal; no endpoint or payment activity."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import acceptance_lab as lab


def scenarios():
    records = lab.load_baseline()["records"]
    first, second, alias = records[0], records[1], records[120]
    def submit(record=first, key="SYNTH-A", **overrides):
        return {"type": "SUBMIT", "key": key, "record_id": record["record_id"],
                "payload_sha256": lab.request_sha256(record), **overrides}
    def dispatch(key="SYNTH-A", at_ms=0):
        return {"type": "DISPATCH", "key": key, "at_ms": at_ms}
    def outcome(kind, dispatch_id="e2", at_ms=0):
        return {"type": kind, "key": "SYNTH-A", "dispatch_event_id": dispatch_id, "at_ms": at_ms}
    def observe(record=first, key="SYNTH-A", evidence="SYNTH-OBS1", observation="COMMITTED", at_ms=0, **overrides):
        return {"type": "OBSERVE", "key": key, "record_id": record["record_id"],
                "payload_sha256": lab.request_sha256(record), "commit_id": record["commit_id"],
                "evidence_id": evidence, "observation": observation, "at_ms": at_ms,
                "posted_cents": record["expected_cents"] if observation == "COMMITTED" else None, **overrides}
    cases = []
    def add(name, events, results, states, attempts, accepted=0, variance=0, nonzero=0, profile=None):
        # Expectations below are authored separately from runtime decisions.
        # Input order is retained when logical timestamps are equal.
        fixed = [{"event_id": f"e{i}", "at_ms": 0, **event} for i, event in enumerate(events, 1)]
        cases.append({"name": name, "transcript": {"schema": lab.SCHEMA, "synthetic_only": True,
                      "profile": dict(profile or lab.DEFAULT_PROFILE), "events": fixed},
                      "expected": {"results": results, "states": states, "logical_attempts": attempts,
                                   "accepted_commit_observations": accepted, "observed_variance_cents": variance,
                                   "nonzero_variance_operations": nonzero}})
    add("ordinary-confirmed", [submit(), dispatch(), observe()],
        ["READY", "IN_FLIGHT", "COMMITTED"], ["COMMITTED"], 1, 1)
    add("before-dispatch-retry", [submit(), dispatch(), outcome("NOT_SENT"), dispatch(at_ms=99),
        dispatch(at_ms=100), outcome("NOT_SENT", "e5", 100), dispatch(at_ms=300), observe(at_ms=300)],
        ["READY", "IN_FLIGHT", "RETRY_WAIT", "RETRY_NOT_DUE", "IN_FLIGHT", "RETRY_WAIT", "IN_FLIGHT", "COMMITTED"], ["COMMITTED"], 3, 1)
    add("retry-budget-exhausted", [submit(), dispatch(), outcome("NOT_SENT"), dispatch(at_ms=100),
        outcome("NOT_SENT", "e4", 100), dispatch(at_ms=300), outcome("NOT_SENT", "e6", 300)],
        ["READY", "IN_FLIGHT", "RETRY_WAIT", "IN_FLIGHT", "RETRY_WAIT", "IN_FLIGHT", "HOLD_RETRY_EXHAUSTED"], ["HOLD_RETRY_EXHAUSTED"], 3)
    add("capped-logical-backoff", [submit(), dispatch(), outcome("NOT_SENT"), dispatch(at_ms=100),
        outcome("NOT_SENT", "e4", 100), dispatch(at_ms=250), outcome("NOT_SENT", "e6", 250), dispatch(at_ms=400), observe(at_ms=400)],
        ["READY", "IN_FLIGHT", "RETRY_WAIT", "IN_FLIGHT", "RETRY_WAIT", "IN_FLIGHT", "RETRY_WAIT", "IN_FLIGHT", "COMMITTED"], ["COMMITTED"], 4, 1,
        profile={**lab.DEFAULT_PROFILE, "max_attempts": 4, "backoff_cap_ms": 150})
    add("duplicate-alias-and-observation", [submit(), submit(alias), dispatch(), observe(), observe(), dispatch()],
        ["READY", "DUPLICATE_NOOP", "IN_FLIGHT", "COMMITTED", "DUPLICATE_NOOP", "DUPLICATE_NOOP"], ["COMMITTED"], 1, 1)
    add("lost-acknowledgement-no-resend", [submit(), dispatch(), outcome("ACK_LOST"), dispatch(at_ms=100)],
        ["READY", "IN_FLIGHT", "HOLD_UNKNOWN_COMMIT", "HOLD_UNKNOWN_COMMIT"], ["HOLD_UNKNOWN_COMMIT"], 1)
    add("lost-acknowledgement-resolved", [submit(), dispatch(), outcome("ACK_LOST"), observe()],
        ["READY", "IN_FLIGHT", "HOLD_UNKNOWN_COMMIT", "COMMITTED"], ["COMMITTED"], 1, 1)
    add("explicit-not-committed-review", [submit(), dispatch(), outcome("ACK_LOST"), observe(observation="NOT_COMMITTED"), dispatch()],
        ["READY", "IN_FLIGHT", "HOLD_UNKNOWN_COMMIT", "HOLD_NOT_COMMITTED_REVIEW", "HOLD_INVALID_TRANSITION"], ["HOLD_NOT_COMMITTED_REVIEW"], 1)
    add("same-key-changed-payload", [submit(), submit(second)],
        ["READY", "HOLD_KEY_PAYLOAD_CONFLICT"], ["READY"], 0)
    add("wrong-payload-digest", [submit(payload_sha256="0" * 64)], ["HOLD_PAYLOAD_MISMATCH"], [], 0)
    add("competing-key-same-mutation", [submit(), submit(alias, "SYNTH-B")],
        ["READY", "HOLD_MUTATION_KEY_CONFLICT"], ["READY"], 0)
    add("wrong-commit-observation", [submit(), dispatch(), observe(commit_id="SMART-COMMIT-0002")],
        ["READY", "IN_FLIGHT", "HOLD_OBSERVATION_BINDING"], ["IN_FLIGHT"], 1)
    add("conflicting-evidence-id", [submit(), dispatch(), observe(), observe(posted_cents=100138)],
        ["READY", "IN_FLIGHT", "COMMITTED", "HOLD_EVIDENCE_CONFLICT"], ["COMMITTED"], 1, 1)
    add("opposing-cent-variances", [submit(), submit(second, "SYNTH-B"), dispatch(), dispatch("SYNTH-B"),
        observe(posted_cents=100138), observe(second, "SYNTH-B", "SYNTH-OBS2", posted_cents=100273)],
        ["READY", "READY", "IN_FLIGHT", "IN_FLIGHT", "HOLD_LEDGER_VARIANCE", "HOLD_LEDGER_VARIANCE"],
        ["HOLD_LEDGER_VARIANCE", "HOLD_LEDGER_VARIANCE"], 2, 0, 0, 2)
    add("baseline-unknown-never-upgraded", [submit(records[130]), dispatch(), observe(records[130])],
        ["HOLD_BASELINE_STATUS", "HOLD_INVALID_TRANSITION", "HOLD_INVALID_TRANSITION"], ["HOLD_BASELINE_STATUS"], 0)
    add("baseline-unauthorized-never-upgraded", [submit(records[140]), dispatch(), observe(records[140])],
        ["HOLD_BASELINE_STATUS", "HOLD_INVALID_TRANSITION", "HOLD_INVALID_TRANSITION"], ["HOLD_BASELINE_STATUS"], 0)
    add("stale-attempt-outcome", [submit(), dispatch(), outcome("NOT_SENT"), dispatch(at_ms=100),
        outcome("NOT_SENT", "e2", 100), outcome("ACK_LOST", "e2", 100), observe(at_ms=100)],
        ["READY", "IN_FLIGHT", "RETRY_WAIT", "IN_FLIGHT", "HOLD_STALE_ATTEMPT", "HOLD_STALE_ATTEMPT", "COMMITTED"], ["COMMITTED"], 2, 1)
    add("explicit-unknown-observation", [submit(), dispatch(), observe(observation="UNKNOWN"), dispatch()],
        ["READY", "IN_FLIGHT", "HOLD_UNKNOWN_COMMIT", "HOLD_UNKNOWN_COMMIT"], ["HOLD_UNKNOWN_COMMIT"], 1)
    return cases


def check_expected(report, expected):
    actual = {"results": [row["result"] for row in report["events"]],
              "states": [row["state"] for row in report["operations"]],
              **{key: report["summary"][key] for key in ("logical_attempts", "accepted_commit_observations", "observed_variance_cents", "nonzero_variance_operations")}}
    if actual != expected:
        raise lab.LabError(f"Independent scenario expectation mismatch: {actual!r} != {expected!r}")


def run_rehearsal(output_dir):
    cases = scenarios()
    prepared = []
    for case in cases:
        report = lab.run_transcript(case["transcript"])
        check_expected(report, case["expected"])
        lab.verify_report(report, case["transcript"])
        prepared.append((case, report))
    base = lab.load_baseline()
    summary = {"schema": "wayne-smart-offline-rehearsal/v1", "synthetic_only": True,
               "status": "LOCAL_SYNTHETIC_EXPECTATIONS_MATCHED", "baseline": base["baseline"],
               "scenario_count": len(cases), "scenario_results": [
                   {"name": case["name"], "expected": case["expected"], "expectations_matched": True,
                    "receipt_sha256": report["receipt_sha256"], "summary": report["summary"]}
                   for case, report in prepared],
               "limitations": "18 proposed scenarios are separate from the original150-state truth set. Neither count establishes code coverage, actual SMART capabilities, deployment or buyer acceptance."}
    summary["receipt_sha256"] = lab.digest(summary)
    lines = ["# Synthetic Wayne SMART operator rehearsal", "", summary["status"], "",
             f"Rehearsal receipt: `{summary['receipt_sha256']}`", "",
             "The unchanged original 150-state baseline and 18 new proposed scenarios were checked separately.",
             "This is synthetic local execution, not buyer acceptance or measured code coverage.", "",
             "| Scenario | Expected outcomes matched | Current states | Attempts | Accepted commit observations | Variance sum | Nonzero variance operations | Review disposition |", "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for case, report in prepared:
        s = report["summary"]
        states = ", ".join(row["state"] for row in report["operations"]) or "No operation accepted"
        lines.append(f"| [{case['name']}]({case['name']}/report.md) | Yes | {states} | {s['logical_attempts']} | {s['accepted_commit_observations']} | {s['observed_variance_cents']} | {s['nonzero_variance_operations']} | {s['disposition']} |")
    lines += ["", "Matching an expected HOLD is a successful synthetic contract check; it is not permission to dispatch.",
              "A resolved COMMITTED operation retains historical HOLD event IDs and the review disposition until a human evaluates the history. The lab never erases that history.",
              "The opposing-cent case records +1 and −1 cent individually: zero net variance still leaves two held operations.",
              "", "## Original baseline result", "", "```json", json.dumps(base["baseline"], sort_keys=True, indent=2), "```", "",
              "All150 expanded baseline records are retained in baseline_records.json with their original truth labels. Every case directory retains transcript.json, report.json and report.md.", ""]
    destination = Path(output_dir)
    try:
        destination.mkdir(parents=False, exist_ok=False)
        for case, report in prepared:
            folder = destination / case["name"]
            folder.mkdir()
            values = {"transcript.json": case["transcript"], "report.json": report}
            for name, value in values.items():
                with (folder / name).open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
            with (folder / "report.md").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(lab.render_markdown(report))
        for name, value in (("summary.json", summary), ("baseline_records.json", base["records"])):
            with (destination / name).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        with (destination / "summary.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines))
    except OSError as exc:
        raise lab.LabError("Rehearsal output must be a new writable directory; interruption may leave partial new output.") from exc
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(args.out)
        print(json.dumps({"scenario_count": result["scenario_count"], "receipt_sha256": result["receipt_sha256"], "status": result["status"]}, sort_keys=True))
        return 0
    except (lab.LabError, OSError) as exc:
        print(f"Offline rehearsal refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

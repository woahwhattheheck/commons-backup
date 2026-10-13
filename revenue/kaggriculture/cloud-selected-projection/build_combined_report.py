#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize all selected-projection suites from saved, source-bound output.

This reads existing files, never imports policy code or reruns a test/game.
Missing or inconsistent evidence produces an explicit unsuccessful report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path

ROOT = "revenue/kaggriculture/"
LAB = ROOT + "cloud-execution-lab/"
MARKET = ROOT + "cloud-selected-market-checks/"
PROJECTION = ROOT + "cloud-selected-projection/"
# key, log, test source, optional JSON report, JSON count field
SUITES = (
    ("original", "original-seller-tests.log", LAB + "test_selected_action_sell.py", None, None),
    ("projection", "projection-tests.log", PROJECTION + "test_projection.py", "projection-results.json", "tests_run"),
    ("market", "market-tests.log", MARKET + "check_market_contracts.py", "market-results.json", "test_methods"),
    ("loader", "loader-tests.log", MARKET + "test_engine_binding.py", "loader-results.json", "test_methods"),
    ("empty_lot", "empty-lot-tests.log", MARKET + "test_empty_lot.py", None, None),
    ("joined_wrapper", "joined-wrapper-tests.log", LAB + "test_ordered_selected_sell.py", None, None),
)
FUNDED_JOIN = ("funded_join", "funded-join-tests.log", ROOT + "cloud-composition-cases/cypress/test_funded_join.py", "funded-join-results.json", "test_methods")
LEDGER_SCHEDULE = ("ledger_schedule", "ledger-schedule-tests.log", MARKET + "test_ledger_schedule.py", "ledger-schedule-results.json", "test_methods")
CANCELLATION = ("deadline_cancellation", "deadline-cancellation-tests.log", ROOT + "cloud-economic-stress/cancellation/test_deadline_cancellation.py", "deadline-cancellation.json", "tests_run")
CALLER_HANDLER = ("caller_handler", "caller-handler-tests.log", ROOT + "cloud-economic-stress/test_caller_handler.py", "caller-handler-results.json", "tests_run")
RUNTIME_REGRESSIONS = (
    ("capture_binding", "capture-binding-tests.log", ROOT + "cloud-market-game-theory/adaptive/test_capture_binding.py", "capture-binding-results.json", "run"),
    ("score_schedule", "score-schedule-tests.log", LAB + "test_score_schedule.py", None, None),
    ("workflow_bindings", "workflow-bindings-tests.log", ROOT + "cloud-composition-cases/cover/test_regression_bindings.py", None, None),
)
STRESS = ROOT + "cloud-economic-stress/"
STRESS_RUNNER = (
    ("stress_runner_boundary", "stress-runner-boundary-tests.log", STRESS + "test_runner_guard_join.py", "stress-runner-boundary.json", "tests_run"),
    ("stress_runner_existing", "stress-runner-existing-tests.log", STRESS + "test_runner.py", None, None),
    ("stress_runner_reporter", "stress-runner-reporter-tests.log", PROJECTION + "test_stress_runner_report.py", None, None),
)
QUEUE_COPY = (
    ("queue_copy", "queue-copy-tests.log", MARKET + "test_queue_copy.py", "queue-copy-results.json", "methods"),
    ("queue_copy_reporter", "queue-copy-reporter-tests.log", PROJECTION + "test_queue_copy_report.py", None, None),
)
ADAPTIVE = ROOT + "cloud-market-game-theory/adaptive/"
ADAPTIVE_CONTEXT = (
    ("adaptive_context", "adaptive-context-tests.log", ADAPTIVE + "context_cases/test_market_context.py", "adaptive-context-results.json", "tests"),
    ("lazy_offers", "lazy-offers-tests.log", ADAPTIVE + "test_lazy_offers.py", None, None),
    ("adaptive_context_reporter", "adaptive-context-reporter-tests.log", PROJECTION + "test_adaptive_context_report.py", None, None),
)
ADAPTIVE_SOURCES = {
    "runtime": ADAPTIVE + "runtime.py", "core": LAB + "selected_sell_core.py",
    "recourse": ADAPTIVE + "recourse.py", "selector": ROOT + "cloud-market-game-theory/selector.py",
    "continuation": ROOT + "cloud-plan-continuation/continuation.py",
    "engine": LAB + "reference/engine/kaggriculture.py",
}
REPORTER = ("reporter", "reporter-tests.log", PROJECTION + "test_combined_report.py", None, None)
SUMMARY = re.compile(r"^Ran ([0-9]+) tests? in .+\n\s*\n(OK(?: \([^\n]*\))?|FAILED(?: \([^\n]*\))?)\s*$", re.M)
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def parse_unittest(text: str) -> dict:
    """Accept one complete unittest summary, including trailing JSON output."""
    summaries = list(SUMMARY.finditer(text))
    runs = re.findall(r"^Ran [0-9]+ tests? in ", text, re.M)
    if len(summaries) != 1 or len(runs) != 1:
        raise ValueError("expected exactly one completed unittest summary")
    match = summaries[0]
    trailer = text[match.end():].strip()
    if trailer:
        try:
            trailing_report = json.loads(trailer)
        except ValueError as exc:
            raise ValueError("unexpected output after unittest completion") from exc
        if not isinstance(trailing_report, dict):
            raise ValueError("expected optional trailing JSON object")
    count = int(match.group(1))
    status = match.group(2)
    flags = dict((k, int(v)) for k, v in re.findall(r"([a-zA-Z ]+)=([0-9]+)", status))
    # Expected failures and skips are not counted as passing methods.
    successful = status == "OK" and count > 0
    return {"tests": count, "successful": successful, "summary": status,
            "failures": flags.get("failures", 0), "errors": flags.get("errors", 0),
            "skipped": flags.get("skipped", 0)}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _check_source_context(snapshot: dict, problems: list) -> None:
    """Check optional workflow context without relabeling legacy snapshots.

    The event commit is the executed checkout; PR head/base are provenance,
    not substitutes for the synthetic merge commit. Extra fields are retained.
    These checks align declarations, not independently attest execution.
    """
    if "source_context" not in snapshot:
        return
    context = snapshot["source_context"]
    if not isinstance(context, dict):
        problems.append("source context: expected an object")
        return
    event = context.get("event")
    if not isinstance(event, str) or not event.strip():
        problems.append("source context: missing/invalid event")
    event_sha = context.get("event_sha")
    if (not isinstance(event_sha, str)
            or re.fullmatch(r"[0-9a-f]{40}", event_sha) is None
            or event_sha != snapshot.get("checkout")):
        problems.append("source context: event_sha does not match executed checkout")
    semantics = context.get("checkout_semantics")
    if semantics not in ("pull_request_merge", "event_commit"):
        problems.append("source context: unsupported checkout_semantics")
    for key in ("pull_request_head", "pull_request_base"):
        value = context.get(key)
        if semantics == "pull_request_merge":
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
                problems.append("source context: missing/invalid " + key)
        elif value is not None:
            problems.append("source context: unexpected " + key + " for event_commit")


def _atomic_write_text(output: Path, text: str) -> None:
    """Publish complete UTF-8 bytes; preserve an old file on pre-replace failure.

    Resolve an existing symlink as write_text did. Stage on the same filesystem,
    retain existing permissions, and replace only after flush/fsync succeeds.
    A hard kill may leave a temporary sibling; it cannot expose a partial target.
    This is atomic visibility, not a claim of power-loss directory durability.
    """
    output = output.resolve()
    try:
        mode = stat.S_IMODE(output.stat().st_mode)
    except FileNotFoundError:
        mode = None
    temporary = output.with_name("." + output.name + "." + uuid.uuid4().hex + ".tmp")
    # O_EXCL avoids collisions; 0666 lets the OS apply the caller's umask,
    # matching write_text for a newly created output without changing umask.
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        try:
            stream = os.fdopen(fd, "w", encoding="utf-8", newline="")
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        with stream:
            if stream.write(text) != len(text):
                raise OSError("short report write")
            stream.flush()
            if mode is not None:
                os.chmod(temporary, mode)
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        try:
            temporary.unlink()
        except OSError:
            # Cleanup must not replace the original write/replace exception.
            pass


def build_report(directory: Path, *, include_reporter: bool = False, include_funded_join: bool = False, include_runtime_regressions: bool = False, include_cancellation: bool = False, include_caller_handler: bool = False, include_ledger_schedule: bool = False, include_stress_runner: bool = False, include_queue_copy: bool = False, include_adaptive_context: bool = False) -> dict:
    """Bind all named suite results to their one declared source snapshot."""
    directory = Path(directory)
    problems, digests = [], {}

    def read(name, *, as_json=False):
        try:
            data = (directory / name).read_bytes()
            digests[name] = hashlib.sha256(data).hexdigest()
            text = data.decode("utf-8")
            if not as_json:
                return text
            value = json.loads(text, object_pairs_hook=_pairs)
            if not isinstance(value, dict):
                raise ValueError("expected a JSON object")
            return value
        except (OSError, UnicodeError, ValueError) as exc:
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
            return None

    snapshot = read("SOURCE-SNAPSHOT.json", as_json=True) or {}
    _check_source_context(snapshot, problems)
    files = snapshot.get("files")
    if not isinstance(files, dict):
        problems.append("source snapshot: missing files mapping")
        files = {}
    for field, pattern in (("checkout", r"[0-9a-f]{40}"), ("run_id", r"[1-9][0-9]*"), ("attempt", r"[1-9][0-9]*")):
        if not re.fullmatch(pattern, str(snapshot.get(field, ""))):
            problems.append("source snapshot: invalid " + field)

    def source(path):
        row = files.get(path)
        value = row.get("sha256") if isinstance(row, dict) else None
        if not isinstance(value, str) or SHA256.fullmatch(value) is None:
            problems.append("source snapshot: missing/invalid SHA256 for " + path)
            return None
        return value

    def bind(label, observed, expected):
        if expected is None or not isinstance(observed, str) or observed != expected:
            problems.append("source mismatch: " + label)

    suites, reports = {}, {}
    declarations = (SUITES + ((FUNDED_JOIN,) if include_funded_join else ())
                    + (RUNTIME_REGRESSIONS if include_runtime_regressions else ())
                    + ((CANCELLATION,) if include_cancellation else ())
                    + ((CALLER_HANDLER,) if include_caller_handler else ())
                    + ((LEDGER_SCHEDULE,) if include_ledger_schedule else ())
                    + ((REPORTER,) if include_reporter else ())
                    + (STRESS_RUNNER if include_stress_runner else ())
                    + (QUEUE_COPY if include_queue_copy else ())
                    + (ADAPTIVE_CONTEXT if include_adaptive_context else ()))
    for key, log, test_path, report_file, count_key in declarations:
        entry = {"tests": None, "successful": False, "test_source_sha256": source(test_path), "log": log}
        text = read(log)
        if text is not None:
            try:
                entry.update(parse_unittest(text))
            except ValueError as exc:
                problems.append(f"{log}: {exc}")
        if not entry["successful"]:
            problems.append(key + ": no complete unskipped passing suite")
        if report_file:
            report = read(report_file, as_json=True)
            reports[key] = report or {}
            if report is not None:
                summary = report.get("tests", {}) if key == "capture_binding" else report
                if not isinstance(summary, dict):
                    summary = {}
                value = summary.get(count_key)
                if type(value) is not int or value != entry["tests"]:
                    problems.append(key + ": JSON/log test counts differ")
                if key in ("deadline_cancellation", "caller_handler", "stress_runner_boundary", "adaptive_context"):
                    for field in ("failures", "errors", "skipped"):
                        if not isinstance(summary.get(field), list) or summary[field]:
                            problems.append(key + ": nonempty or missing JSON " + field + " array")
                else:
                    if any(type(summary.get(k)) is not int or summary[k] != 0 for k in ("failures", "errors")):
                        problems.append(key + ": nonzero or missing JSON failures/errors")
                    success_field = "passed" if key == "queue_copy" else "success" if key == "capture_binding" else "successful"
                    if key != "projection" and summary.get(success_field) is not True:
                        problems.append(key + ": JSON result is not successful")
        suites[key] = entry

    seller = source(LAB + "selected_action_sell.py")
    projected, market, loader = (reports.get(k, {}) for k in ("projection", "market", "loader"))
    bind("projection seller", projected.get("seller_sha256"), seller)
    bind("projection implementation", projected.get("projection_sha256"), source(PROJECTION + "projection.py"))
    market_sources = market.get("sources") or {}
    if not isinstance(market_sources, dict):
        market_sources = {}
    for name in ("selected_action_sell.py", "selected_sell_core.py", "mechanics.py", "reference/decision/decision.py"):
        bind("market " + name, market_sources.get(name), source(LAB + name))
    engine = {name: source(LAB + "reference/engine/" + name)
              for name in ("kaggriculture.py", "kaggriculture.json", "utils.py")}
    same_engine = all(engine.values()) and projected.get("engine_sha256") == engine and market.get("engine_sha256") == engine
    if not same_engine:
        problems.append("engine hashes do not match both JSON reports and source snapshot")
    loader_sources = loader.get("source_sha256") or {}
    if not isinstance(loader_sources, dict):
        loader_sources = {}
    for name, path in (("checker", MARKET + "check_market_contracts.py"),
                       ("evaluator", LAB + "reference/evaluator/evaluate.py"),
                       ("loader", LAB + "reference/evaluator/loader.py")):
        bind("loader " + name, loader_sources.get(name), source(path))
    joined = source(LAB + "ordered_selected_sell.py")
    funded = reports.get("funded_join", {})
    if include_funded_join:
        funded_sources = funded.get("sources")
        if not isinstance(funded_sources, dict) or not funded_sources:
            problems.append("funded join: missing source bindings")
            funded_sources = {}
        for name, row in funded_sources.items():
            digest = row.get("sha256") if isinstance(row, dict) else None
            bind("funded join " + name, digest, source(ROOT + name))
        required = (FUNDED_JOIN[2], LAB + "integrated_selected.py",
                    LAB + "selected_action_sell.py", LAB + "reference/engine/kaggriculture.py")
        for path in required:
            if path[len(ROOT):] not in funded_sources:
                problems.append("funded join: missing binding for " + path)
        for field, origin in (("workflow_run", "run_id"), ("workflow_attempt", "attempt")):
            if str(funded.get(field)) != str(snapshot.get(origin)):
                problems.append("funded join: mismatched " + field)

    if include_runtime_regressions:
        capture = reports.get("capture_binding", {})
        bind("capture runtime", capture.get("runtime_sha256"),
             source(ROOT + "cloud-market-game-theory/adaptive/runtime.py"))
        bind("capture optimizer", capture.get("optimizer_sha256"),
             source(LAB + "selected_sell_core.py"))
        source(".github/workflows/titan-selected-projection.yml")

    ledger = reports.get("ledger_schedule", {})
    if include_ledger_schedule:
        bindings = ledger.get("sources_sha256")
        if not isinstance(bindings, dict):
            bindings = {}
        for name in ("selected_action_sell.py", "selected_sell_core.py", "mechanics.py", "reference/decision/decision.py"):
            bind("ledger " + name, bindings.get(name), source(LAB + name))
        if ledger.get("engine_sha256") != engine:
            problems.append("ledger: engine hashes do not match source snapshot")
        if type(ledger.get("skipped")) is not int or ledger["skipped"] != 0:
            problems.append("ledger: nonzero or missing skipped count")
        counts = ledger.get("counts")
        if not isinstance(counts, dict) or any(type(n) is not int or n < 0 for n in counts.values()):
            problems.append("ledger: invalid case-count mapping")

    cancelled = reports.get("deadline_cancellation", {})
    if include_cancellation:
        bind("cancellation adapter", cancelled.get("adapter_sha256"),
             source(ROOT + "cloud-economic-stress/deadline_adapter.py"))
        partition = [cancelled.get(field) for field in
                     ("new_regression_methods", "unchanged_upstream_guard_methods")]
        if (any(type(n) is not int or n < 0 for n in partition)
                or sum(partition) != cancelled.get("tests_run")):
            problems.append("cancellation: method partition does not match tests_run")

    caller = reports.get("caller_handler", {})
    caller_measurements = caller.get("measurements")
    if include_caller_handler:
        bind("caller handler adapter", caller.get("adapter_sha256"),
             source(ROOT + "cloud-economic-stress/deadline_adapter.py"))
        bind("caller handler test", caller.get("test_sha256"), source(CALLER_HANDLER[2]))
        if type(caller.get("games")) is not int or caller["games"] != 0:
            problems.append("caller handler: expected zero games")
        if not isinstance(caller_measurements, list) or not caller_measurements:
            problems.append("caller handler: missing measurement array")
        else:
            for index, row in enumerate(caller_measurements):
                if not isinstance(row, dict):
                    problems.append(f"caller handler: invalid measurement {index}")
                    continue
                diagnostics = row.get("diagnostics")
                if row.get("handler_preserved") is not True:
                    problems.append(f"caller handler: replacement not preserved in measurement {index}")
                if not isinstance(diagnostics, dict) or diagnostics.get("status") != "deadline_fallback":
                    problems.append(f"caller handler: invalid fallback diagnostics in measurement {index}")

    stress = reports.get("stress_runner_boundary", {})
    if include_stress_runner:
        for field, path in (("runner_sha256", STRESS + "runner.py"),
                            ("adapter_sha256", STRESS + "deadline_adapter.py"),
                            ("test_sha256", STRESS_RUNNER[0][2])):
            bind("stress runner " + field, stress.get(field), source(path))
        # The hosted command runs boundary-only fixtures. Do not import a local
        # actual-state run or its three extra methods into this receipt.
        if stress.get("actual_source") is not False:
            problems.append("stress runner: expected boundary-only actual_source=false")
        if type(stress.get("full_games")) is not int or stress["full_games"] != 0:
            problems.append("stress runner: expected zero full_games")
        if stress.get("new_game_seeds") != []:
            problems.append("stress runner: expected empty new_game_seeds array")

    queue = reports.get("queue_copy", {})
    if include_queue_copy:
        bind("queue copy seller", queue.get("source_sha256"), seller)
        if queue.get("schema") != "titan.queue-copy.final.v1":
            problems.append("queue copy: unsupported or missing report schema")
        for field in ("new_games", "engine_transitions"):
            if type(queue.get(field)) is not int or queue[field] != 0:
                problems.append("queue copy: expected zero " + field)
        counts = queue.get("counts")
        expected_counts = ("queue_comparisons", "replacement_comparisons",
                           "complete_transform_comparisons", "feasibility_comparisons")
        if (not isinstance(counts, dict)
                or any(type(counts.get(k)) is not int or counts[k] < 0 for k in expected_counts)):
            problems.append("queue copy: invalid comparison-count mapping")
        inner_log = queue.get("log")
        try:
            if not isinstance(inner_log, str):
                raise ValueError("missing text")
            inner = parse_unittest(inner_log)
            if not inner["successful"] or inner["tests"] != suites["queue_copy"]["tests"]:
                raise ValueError("embedded log does not match completed passing outer log")
        except ValueError as exc:
            problems.append("queue copy: " + str(exc))

    context = reports.get("adaptive_context", {})
    context_transitions = 0
    context_bindings = {}
    if include_adaptive_context:
        if type(context.get("schema")) is not int or context["schema"] != 1:
            problems.append("adaptive context: unsupported or missing report schema")
        bindings = context.get("sources")
        if not isinstance(bindings, dict):
            bindings = {}
        for name, path in ADAPTIVE_SOURCES.items():
            row = bindings.get(name)
            observed = row.get("sha256") if isinstance(row, dict) else None
            expected = source(path)
            bind("adaptive context " + name, observed, expected)
            context_bindings[name] = expected
        # Both suites import these actual support files. Their checked-out
        # identities are part of the same snapshot, not a borrowed old closure.
        for path in (LAB + "selected_action_sell.py", LAB + "mechanics.py",
                     LAB + "reference/decision/decision.py",
                     ROOT + "cloud-observed-fills/observed_fills.py"):
            context_bindings[path] = source(path)
        evidence = context.get("evidence")
        if not isinstance(evidence, list):
            problems.append("adaptive context: missing evidence array")
            evidence = []
        official = [row for row in evidence if isinstance(row, dict)
                    and row.get("kind") == "official_interpreter"]
        if not official:
            problems.append("adaptive context: no official interpreter evidence")
        for row in official:
            transitions = row.get("transitions")
            if (not isinstance(transitions, list) or not transitions
                    or any(not isinstance(t, dict) for t in transitions)):
                problems.append("adaptive context: invalid interpreter transitions")
            else:
                context_transitions += len(transitions)

    observed_total = sum(s["tests"] for s in suites.values() if s["tests"] is not None)
    counts_complete = all(s["tests"] is not None for s in suites.values())
    result = {"schema": "titan.selected-projection.combined.v2",
              "checkout": snapshot.get("checkout"), "run_id": snapshot.get("run_id"),
              "attempt": snapshot.get("attempt"), "python": snapshot.get("python"),
              "seller_sha256": seller, "joined_wrapper_sha256": joined,
              "engine_sha256": engine, "same_engine": bool(same_engine),
              "suites": suites, "suite_count": len(suites),
              "observed_tests": observed_total,
              "total_tests": observed_total if counts_complete else None,
              "complete": counts_complete and not problems,
              "successful": not problems,
              "projection_cases": projected.get("differential_cases"),
              "projection_transitions": projected.get("interpreter_transitions"),
              "market_cases": market.get("official_market_cases"),
              "loader_market_cases": loader.get("official_market_cases"),
              "input_sha256": digests, "problems": problems, "full_games": 0,
              "scope": "saved focused-suite outputs; source alignment is not independent execution attestation"}
    if "source_context" in snapshot:
        result["source_context"] = snapshot["source_context"]
    for key, entry in suites.items():
        result[key + "_tests"] = entry["tests"]
    first_three = [result[k + "_tests"] for k in ("original", "projection", "market")]
    result["legacy_three_suite_tests"] = sum(first_three) if all(v is not None for v in first_three) else None
    if include_funded_join:
        result["funded_join_transitions"] = funded.get("official_transitions")
        result["funded_join_full_games"] = funded.get("full_games")
    if include_cancellation:
        result["cancellation_new_regression_methods"] = cancelled.get("new_regression_methods")
        result["cancellation_retained_guard_methods"] = cancelled.get("unchanged_upstream_guard_methods")
        result["cancellation_adapter_sha256"] = cancelled.get("adapter_sha256")
    if include_caller_handler:
        result["caller_handler_binding"] = {
            "adapter_sha256": caller.get("adapter_sha256"),
            "test_sha256": caller.get("test_sha256"),
            "games": caller.get("games")}
        result["caller_handler_measurements"] = (
            len(caller_measurements) if isinstance(caller_measurements, list) else None)
    if include_ledger_schedule:
        result["ledger_schedule_case_counts"] = ledger.get("counts")
        result["ledger_reported_reference_method_sha256"] = ledger.get("reference_method_sha256")
    if include_stress_runner:
        result["stress_runner_binding"] = {
            field: stress.get(field) for field in
            ("runner_sha256", "adapter_sha256", "test_sha256", "actual_source", "full_games", "new_game_seeds")}
    if include_queue_copy:
        result["queue_copy_binding"] = {
            field: queue.get(field) for field in
            ("schema", "source_sha256", "new_games", "engine_transitions")}
        result["queue_copy_case_counts"] = queue.get("counts")
    if include_adaptive_context:
        result["adaptive_context_binding"] = context_bindings
        result["adaptive_context_interpreter_transitions"] = context_transitions
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-reporter-tests", action="store_true")
    parser.add_argument("--include-funded-join", action="store_true")
    parser.add_argument("--include-runtime-regressions", action="store_true")
    parser.add_argument("--include-cancellation", action="store_true")
    parser.add_argument("--include-caller-handler", action="store_true")
    parser.add_argument("--include-ledger-schedule", action="store_true")
    parser.add_argument("--include-stress-runner", action="store_true")
    parser.add_argument("--include-queue-copy", action="store_true")
    parser.add_argument("--include-adaptive-context", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(args.directory, include_reporter=args.include_reporter_tests,
                          include_funded_join=args.include_funded_join,
                          include_runtime_regressions=args.include_runtime_regressions,
                          include_cancellation=args.include_cancellation,
                          include_caller_handler=args.include_caller_handler,
                          include_ledger_schedule=args.include_ledger_schedule,
                          include_stress_runner=args.include_stress_runner,
                          include_queue_copy=args.include_queue_copy,
                          include_adaptive_context=args.include_adaptive_context)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        _atomic_write_text(args.output, text)
    else:
        print(text, end="")
    return 0 if report["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

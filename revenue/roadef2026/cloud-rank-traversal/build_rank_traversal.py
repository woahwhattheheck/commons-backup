#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a separate scheduler-only draft from exact e801 integration source."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

BASE_SHA256 = "e8014d78f40df5546d80f0ff6f1c6bc3a97944a526d7c347eb0dcdbe77728e46"
PRISM_COMMIT = "73a805e290cee36981917ac09e7ce2133f35afd7"
RANK_BAND_COMMIT = "4b1dcaa793f9b54f13c287d766e6094f2faf4ac8"
TRACE_COMMIT = "3f1ee2866f21cb73988de5a82863b7f818aeb333"

SELECTION_OLD = '''            int position = 0;
            for (int i = 1; i < static_cast<int>(loads.size()); ++i)
                if (loads[i] > loads[position]) position = i;
'''
SELECTION_NEW = '''            int position = 0;
            if (rankTraversal) {
                if (rankCursor == 0) {
                    coordinateOrder.resize(loads.size());
                    std::iota(coordinateOrder.begin(), coordinateOrder.end(), 0);
                    std::partial_sort(coordinateOrder.begin(), coordinateOrder.begin() + rankLimit,
                                      coordinateOrder.end(), [&](int a, int b) {
                        return loads[a] != loads[b] ? loads[a] > loads[b] : a < b;
                    });
                }
                position = coordinateOrder[rankCursor];
            } else {
                for (int i = 1; i < static_cast<int>(loads.size()); ++i)
                    if (loads[i] > loads[position]) position = i;
            }
'''
STOP_OLD = '''            // No state change means the deterministic exhaustive pass would
            // repeat the same proposals. Preserve that measured stopping point.
            if (accepted == acceptedBefore) break;
'''
STOP_NEW = r'''            // A no-accept result exhausts this configured pass, not all routes.
            if (!rankTraversal) {
                if (accepted == acceptedBefore) break;
                continue;
            }
            const auto& completed = records.back();
            std::cerr << "FLEET_POLISH {\"event\":\"rank_pass\",\"pass\":" << pass
                      << ",\"selected_rank\":" << completed.selectedRank
                      << ",\"coordinate\":" << position << ",\"outcome\":\""
                      << completed.passOutcome << "\",\"attempted\":"
                      << (completed.attemptsAfter - completed.attemptsBefore)
                      << ",\"accepted\":" << (completed.acceptedAfter - completed.acceptedBefore)
                      << "}\n";
            if (finished()) {
                schedulerStop = interrupted ? "signal" : "deadline";
                break;
            }
            if (accepted != acceptedBefore) {
                rankCursor = 0;
            } else if (++rankCursor >= rankLimit) {
                schedulerStop = "configured_sweep_exhaustion";
                break;
            }
'''
SCHEDULER_END = r'''        if (rankTraversal) {
            if (interrupted) schedulerStop = "signal";
            else if (elapsed() >= seconds) schedulerStop = "deadline";
            std::cerr << "FLEET_POLISH {\"event\":\"rank_stop\",\"reason\":\""
                      << schedulerStop << "\",\"passes\":" << records.size()
                      << ",\"pass_limit\":" << passLimit << ",\"rank_limit\":" << rankLimit
                      << ",\"last_selected_rank\":"
                      << (records.empty() ? 0 : records.back().selectedRank) << "}\n";
        }
'''


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("expected one source region: " + repr(old[:120]))
    return text.replace(old, new, 1)


def between(text: str, start: str, end: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("unexpected preservation boundary")
    return text.split(start, 1)[1].split(end, 1)[0]


def transform(source: bytes) -> tuple[bytes, dict]:
    if sha256(source) != BASE_SHA256:
        raise ValueError("source differs from exact e801 natural-exhaustion integration")
    original = source.decode("utf-8")
    old_notice = (
        "    // PRISM rankOne() body reused verbatim from commons PR10430,\n"
        "    // merged 73a805e290cee36981917ac09e7ce2133f35afd7 (cloud-a-rank1).\n"
        "    // Natural-exhaustion dispatch below is a separate opt-in integration.\n"
    )
    new_notice = (
        "    // PRISM proposal body retained from commons PR10430,\n"
        "    // merged 73a805e290cee36981917ac09e7ce2133f35afd7 (cloud-a-rank1).\n"
        "    // Scheduler idea: PR10451 / TRACE; PRISM owns the proposal mechanism.\n"
        "    // PR10451 merge: 4b1dcaa793f9b54f13c287d766e6094f2faf4ac8.\n"
        "    // This separate opt-in uses a finite sweep, not rank-band cycling.\n"
        "    // The e801 natural-exhaustion guard and allowance remain unchanged.\n"
    )
    text = replace_once(original, old_notice, new_notice)
    text = replace_once(text, "    // Opt-in hard-case pass: exhaust the current rank-one coordinate before\n",
                        "    // Opt-in bounded proposals at the selected load coordinate before\n")
    controls = '        const char* reportPath = std::getenv("FLEET_RANK1_REPORT");\n'
    text = replace_once(text, controls, controls + '''        bool rankTraversal = setting("FLEET_POLISH_RANK_TRAVERSAL", 0) != 0;
        int rankLimit = std::min<int>(static_cast<int>(loads.size()), passLimit);
        int rankCursor = 0;
        std::vector<int> coordinateOrder;
        const char* schedulerStop = "pass_budget";
''')
    text = replace_once(text, "            std::vector<std::pair<int, double>> top;\n",
                        "            std::vector<std::pair<int, double>> top;\n"
                        "            int selectedRank = 1;\n"
                        '            const char* passOutcome = "configured_pass_exhaustion";\n')
    text = replace_once(text, SELECTION_OLD, SELECTION_NEW)
    accounting = "            record.acceptedAfter = accepted;\n"
    text = replace_once(text, accounting, accounting + '''            if (rankTraversal) {
                record.selectedRank = rankCursor + 1;
                record.passOutcome = accepted != acceptedBefore ? "accepted_move"
                    : interrupted ? "signal" : elapsed() >= seconds ? "deadline"
                    : "configured_pass_exhaustion";
            }
''')
    text = replace_once(text, STOP_OLD, STOP_NEW)
    boundary = "        writeSolution();\n        statistics();\n        if (reportPath) {\n"
    text = replace_once(text, boundary, SCHEDULER_END + boundary)
    report_start = '                out << "{\\"pass\\":" << r.pass << ",\\"t\\":" << r.t\n'
    text = replace_once(text, report_start, r'''                out << "{\"pass\":" << r.pass;
                if (rankTraversal) {
                    out << ",\"selected_rank\":" << r.selectedRank
                        << ",\"outcome\":\"" << r.passOutcome << "\"";
                }
                out << ",\"t\":" << r.t
''')
    report_end = '''            out << "],\\"attempted\\":" << attempted << ",\\"accepted\\":" << accepted
                << ",\\"elapsed\\":" << elapsed() << "}\\n";
'''
    text = replace_once(text, report_end, r'''            out << "],\"attempted\":" << attempted << ",\"accepted\":" << accepted
                << ",\"elapsed\":" << elapsed();
            if (rankTraversal) {
                out << ",\"rank_traversal\":true,\"rank_limit\":" << rankLimit
                    << ",\"stop_reason\":\"" << schedulerStop << "\"";
            }
            out << "}\n";
''')
    proposal_start = "            int t = position / m, edge = position % m;\n"
    proposal_end = "            record.after = loads[t * m + edge];\n"
    before = between(original, proposal_start, proposal_end)
    after = between(text, proposal_start, proposal_end)
    if before != after:
        raise ValueError("PRISM proposal, constraint dispatch or ejection body drifted")
    outside_start = "    void polishAfterExhaustion(bool naturallyExhausted) {\n"
    if original.split(outside_start, 1)[1] != text.split(outside_start, 1)[1]:
        raise ValueError("natural exhaustion, ordinary run or main dispatch drifted")
    prefix_end = "    // PRISM "
    if original.split(prefix_end, 1)[0] != text.split(prefix_end, 1)[0]:
        raise ValueError("solver kernel, clock, constraints or writer drifted")
    result = text.encode("utf-8")
    receipt = {
        "schema": "roadef.rank-traversal.draft-source.v1",
        "status": "draft; no build, runtime trial, publication, promotion or submission",
        "base": {"bytes": len(source), "sha256": sha256(source)},
        "output": {"bytes": len(result), "sha256": sha256(result)},
        "sources": {
            "prism_pr": 10430, "prism_merge": PRISM_COMMIT,
            "rank_band_pr": 10451, "rank_band_merge": RANK_BAND_COMMIT,
            "trace_merge": TRACE_COMMIT,
            "trace_header": "revenue/roadef2026/cloud-critical-bands/critical_bands.hpp",
            "trace_header_git_blob": "5826c0a11480cf471316a002c45e3a4f3f9e259b",
            "scope": "TRACE/rank-band scheduler guidance around PRISM proposals; separate finite sweep",
        },
        "proposal_region": {"bytes": len(before.encode()), "sha256": sha256(before.encode()),
                            "unchanged": True},
        "solver_kernel_and_writer_unchanged": True,
        "ordinary_run_guard_clock_and_main_unchanged": True,
        "enable": ["FLEET_POLISH_AFTER_EXHAUSTION=1", "FLEET_POLISH_RANK_TRAVERSAL=1"],
        "shared_pass_limit": {"default": 16, "maximum": 128},
        "rank_limit": "min(load coordinate count, pass limit)",
    }
    return result, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    paths = [path for path in (args.output, args.patch, args.receipt) if path is not None]
    if len({path.resolve() for path in paths}) != len(paths) or any(path.exists() for path in paths):
        parser.error("outputs must be distinct fresh files")
    if any(path.resolve() == args.source.resolve() for path in paths):
        parser.error("output must not replace the input")
    source = args.source.read_bytes()
    try:
        changed, receipt = transform(source)
    except (ValueError, UnicodeDecodeError) as error:
        parser.error(str(error))
    patch = "".join(difflib.unified_diff(source.decode().splitlines(keepends=True),
                                       changed.decode().splitlines(keepends=True),
                                       fromfile="a/main.cpp", tofile="b/main.cpp")).encode()
    receipt["patch"] = {"bytes": len(patch), "sha256": sha256(patch)}
    for path, body in ((args.output, changed), (args.patch, patch),
                       (args.receipt, (json.dumps(receipt, indent=2) + "\n").encode())):
        if path is not None:
            with path.open("xb") as stream:
                stream.write(body)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Insert an opt-in rank-one diversion pass into the frozen fleet candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

METHOD_ANCHOR = "\n    void run() {\n"
MAIN_OLD = "    try { Solver solver(argv[1], argv[2], argv[3], argv[4]); solver.run(); }\n"
MAIN_NEW = (
    "    try { Solver solver(argv[1], argv[2], argv[3], argv[4]); "
    "if (setting(\"FLEET_RANK1\", 0) != 0) solver.rankOne(); else solver.run(); }\n"
)
MARKER = "void rankOne()"

METHOD = r'''
    // Opt-in hard-case pass: exhaust the current rank-one coordinate before
    // returning to the ordinary search. All proposed routes still enter through
    // move()/moveTogether(), so exact ECMP, segment limits, transition budgets,
    // and the full sorted six-decimal acceptance rule remain authoritative.
    void rankOne() {
        int passLimit = static_cast<int>(std::min(128.0, setting("FLEET_RANK1_PASSES", 16)));
        int demandLimitSetting = static_cast<int>(std::min(256.0, setting("FLEET_RANK1_DEMANDS", 32)));
        int pairNodeLimit = static_cast<int>(std::min(96.0, setting("FLEET_RANK1_PAIR_NODES", 24)));
        const char* reportPath = std::getenv("FLEET_RANK1_REPORT");
        struct PassRecord {
            int pass, t, edge, from, to, contributors;
            double before, after;
            long long attemptsBefore, attemptsAfter, acceptedBefore, acceptedAfter;
            bool ejection;
            std::vector<std::pair<int, double>> top;
        };
        std::vector<PassRecord> records;
        auto appendWindow = [](std::vector<std::pair<int, int>>& windows, int left, int right) {
            std::pair<int, int> item{left, right};
            if (std::find(windows.begin(), windows.end(), item) == windows.end()) windows.push_back(item);
        };
        for (int pass = 0; pass < passLimit && !finished(); ++pass) {
            int position = 0;
            for (int i = 1; i < static_cast<int>(loads.size()); ++i)
                if (loads[i] > loads[position]) position = i;
            int t = position / m, edge = position % m;
            double before = loads[position];
            auto contributing = contributors(t, edge);
            PassRecord record{pass, t, edge, nodeIds[edges[edge].from], nodeIds[edges[edge].to],
                              static_cast<int>(contributing.size()), before, before,
                              attempted, attempted, accepted, accepted, false, {}};
            for (int i = 0; i < std::min<int>(32, contributing.size()); ++i)
                record.top.emplace_back(contributing[i].second, contributing[i].first);
            long long acceptedBefore = accepted;
            int demandLimit = std::min<int>(demandLimitSetting, contributing.size());
            for (int j = 0; j < demandLimit && accepted == acceptedBefore && !finished(); ++j) {
                int d = contributing[j].second;
                Route original = routes[d * h + t];
                std::vector<std::pair<int, int>> windows;
                appendWindow(windows, t, t);
                if (h > 1) {
                    for (int radius : {1, 2, 3})
                        appendWindow(windows, std::max(0, t - radius), std::min(h - 1, t + radius));
                    appendWindow(windows, 0, t);
                    appendWindow(windows, t, h - 1);
                }
                appendWindow(windows, 0, h - 1);

                auto tryPath = [&](const Route& path) {
                    for (auto [left, right] : windows) {
                        if (finished()) return false;
                        if (move(d, left, right, path)) return true;
                    }
                    return false;
                };

                if (tryPath({})) break;
                for (std::size_t k = 0; k < original.size() && accepted == acceptedBefore && !finished(); ++k) {
                    Route path = original;
                    path.erase(path.begin() + static_cast<std::ptrdiff_t>(k));
                    if (tryPath(path)) break;
                }
                if (accepted != acceptedBefore || finished()) break;

                // This ranks every node when FLEET_WAYPOINT_LIMIT is unset, but
                // unlike run() it does not truncate the returned candidate list.
                auto candidates = waypointCandidates(d, t, edge);
                for (int w : candidates) {
                    if (finished() || accepted != acceptedBefore) break;
                    if (tryPath({w})) break;
                    for (std::size_t k = 0; k < original.size() && accepted == acceptedBefore; ++k) {
                        Route path = original;
                        path[k] = w;
                        if (tryPath(path)) break;
                    }
                    if (accepted != acceptedBefore) break;
                    if (original.size() + 1 < static_cast<std::size_t>(maxSegments)) {
                        for (std::size_t k = 0; k <= original.size() && accepted == acceptedBefore; ++k) {
                            Route path = original;
                            path.insert(path.begin() + static_cast<std::ptrdiff_t>(k), w);
                            if (tryPath(path)) break;
                        }
                    }
                }
                if (accepted != acceptedBefore || finished() || maxSegments < 3) break;

                int pairLimit = std::min<int>(pairNodeLimit, candidates.size());
                for (int a = 0; a < pairLimit && accepted == acceptedBefore && !finished(); ++a) {
                    for (int b = 0; b < pairLimit && accepted == acceptedBefore && !finished(); ++b) {
                        if (a == b) continue;
                        if (tryPath({candidates[a], candidates[b]})) break;
                    }
                }
            }
            if (accepted == acceptedBefore && !finished()) {
                record.ejection = eject(t, edge, contributing, true);
            }
            record.after = loads[t * m + edge];
            record.attemptsAfter = attempted;
            record.acceptedAfter = accepted;
            records.push_back(std::move(record));
            writeSolution();
            // No state change means the deterministic exhaustive pass would
            // repeat the same proposals. Preserve that measured stopping point.
            if (accepted == acceptedBefore) break;
        }
        writeSolution();
        statistics();
        if (reportPath) {
            std::string temporary = std::string(reportPath) + ".tmp";
            std::ofstream out(temporary);
            if (!out) throw std::runtime_error("Cannot write " + temporary);
            out.precision(17);
            out << "{\"schema\":\"roadef.rank-one-diversion.v1\",\"passes\":[";
            for (std::size_t i = 0; i < records.size(); ++i) {
                if (i) out << ',';
                const auto& r = records[i];
                out << "{\"pass\":" << r.pass << ",\"t\":" << r.t
                    << ",\"edge\":" << r.edge << ",\"from\":" << r.from
                    << ",\"to\":" << r.to << ",\"before\":" << r.before
                    << ",\"after\":" << r.after << ",\"contributors\":" << r.contributors
                    << ",\"attempts\":" << (r.attemptsAfter - r.attemptsBefore)
                    << ",\"accepted\":" << (r.acceptedAfter - r.acceptedBefore)
                    << ",\"ejection\":" << (r.ejection ? "true" : "false")
                    << ",\"top_contributors\":[";
                for (std::size_t j = 0; j < r.top.size(); ++j) {
                    if (j) out << ',';
                    out << "{\"d\":" << r.top[j].first << ",\"load\":" << r.top[j].second << '}';
                }
                out << "]}";
            }
            out << "],\"attempted\":" << attempted << ",\"accepted\":" << accepted
                << ",\"elapsed\":" << elapsed() << "}\n";
            out.close();
            if (!out) throw std::runtime_error("Failed writing " + temporary);
            std::filesystem::rename(temporary, reportPath);
        }
        std::cerr << "Rank-one pass completed " << accepted << " improving moves / "
                  << attempted << " attempts; MLU " << *std::max_element(loads.begin(), loads.end())
                  << "; elapsed " << elapsed() << "s\n";
    }
'''


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def transform(text: str) -> str:
    if MARKER in text:
        raise ValueError("rank-one method is already present")
    if text.count(METHOD_ANCHOR) != 1:
        raise ValueError("expected exactly one run() insertion anchor")
    if text.count(MAIN_OLD) != 1:
        raise ValueError("expected exactly one main dispatch anchor")
    changed = text.replace(METHOD_ANCHOR, "\n" + METHOD + METHOD_ANCHOR, 1)
    return changed.replace(MAIN_OLD, MAIN_NEW, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    if args.expected_sha256 and sha256(source) != args.expected_sha256:
        parser.error("source SHA256 differs")
    if args.output.exists():
        parser.error("output already exists")
    changed = transform(source.decode("utf-8")).encode("utf-8")
    args.output.write_bytes(changed)
    receipt = {
        "schema": "roadef.rank-one-builder.v1",
        "source": {"bytes": len(source), "sha256": sha256(source)},
        "output": {"bytes": len(changed), "sha256": sha256(changed)},
        "method_marker": MARKER,
        "normal_dispatch_preserved": "else solver.run();" in changed.decode("utf-8"),
    }
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

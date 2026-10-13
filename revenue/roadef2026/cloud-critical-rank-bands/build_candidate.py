#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the opt-in critical-rank-band ROADEF candidate from exact fleet source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BASE_SHA256 = "322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1"
OUTPUT_SHA256 = "f3c76d2aa60525cde061bcb10b95c504b09d13a54cf2a442cd0dcae6975057c9"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one exact source region, found {count}")
    return text.replace(old, new)


def transform(text: str) -> str:
    setting = '''static double setting(const char* name, double fallback) {
    const char* text = std::getenv(name);
    if (!text) return fallback;
    char* end = nullptr;
    double value = std::strtod(text, &end);
    if (end == text || *end || !std::isfinite(value) || value < 0)
        throw std::runtime_error(std::string("Invalid setting ") + name);
    return value;
}
'''
    text = replace_once(text, setting, setting + '''static int positiveIntegerSetting(const char* name, int fallback, int maximum) {
    double value = setting(name, fallback);
    if (value < 1 || value > maximum || std::floor(value) != value)
        throw std::runtime_error(std::string("Invalid positive integer setting ") + name);
    return static_cast<int>(value);
}

struct CriticalRankChoice {
    int sortedPrefix;
    int rank;
    int band;
};

// Visit the top 32 coordinates first. Each uninterrupted plateau then opens
// one disjoint power-of-two rank band. Once the configured limit is exhausted,
// keep cycling the deepest band rather than silently returning to the top.
static CriticalRankChoice selectCriticalRank(int stalled, int available, int maxRanks) {
    if (stalled < 0 || available <= 0 || maxRanks <= 0)
        throw std::runtime_error("Invalid critical-rank selection input");
    int limit = std::min(available, maxRanks);
    int start = 0, end = std::min(32, limit), remaining = stalled, band = 0;
    while (end < limit && remaining >= end - start) {
        remaining -= end - start;
        start = end;
        end = std::min(limit, end * 2);
        ++band;
    }
    int width = end - start;
    return {end, start + remaining % width, band};
}
''', "rank selector")

    text = replace_once(text, '''    bool jointEnabled = setting("FLEET_JOINT", 1) != 0;
    bool directedEnabled = setting("FLEET_DIRECTED", 1) != 0;
    int scanLimit = static_cast<int>(setting("FLEET_WAYPOINT_LIMIT", 0));
''', '''    bool jointEnabled = setting("FLEET_JOINT", 1) != 0;
    bool directedEnabled = setting("FLEET_DIRECTED", 1) != 0;
    int scanLimit = static_cast<int>(setting("FLEET_WAYPOINT_LIMIT", 0));
    int criticalRankLimit = positiveIntegerSetting("FLEET_CRITICAL_RANK_LIMIT", 32, 1000000);
    int criticalStallLimit = positiveIntegerSetting("FLEET_CRITICAL_STALL_LIMIT", 64, 1000000);
    std::vector<long long> criticalBandVisits = std::vector<long long>(32, 0);
    std::vector<long long> criticalBandAccepts = std::vector<long long>(32, 0);
    int criticalMaxRankVisited = -1;
    int criticalMaxBandVisited = 0;
    int roundsCompleted = 0;
    std::string stopReason = "round_limit";
''', "runtime controls")

    text = replace_once(text, '''            << ",\\"ranked_candidates\\":" << rankedCandidates
            << ",\\"accepted\\":" << accepted << ",\\"initial_mlu\\":" << initialMlu
            << ",\\"final_mlu\\":" << *std::max_element(loads.begin(), loads.end())
            << ",\\"budget_used\\":[";
''', '''            << ",\\"ranked_candidates\\":" << rankedCandidates
            << ",\\"accepted\\":" << accepted << ",\\"initial_mlu\\":" << initialMlu
            << ",\\"final_mlu\\":" << *std::max_element(loads.begin(), loads.end())
            << ",\\"critical_rank_limit\\":" << criticalRankLimit
            << ",\\"critical_stall_limit\\":" << criticalStallLimit
            << ",\\"critical_max_rank_visited\\":" << criticalMaxRankVisited
            << ",\\"rounds_completed\\":" << roundsCompleted
            << ",\\"stop_reason\\":\\"" << stopReason << "\\""
            << ",\\"critical_band_visits\\":[";
        for (int i = 0; i <= criticalMaxBandVisited; ++i) {
            if (i) out << ',';
            out << criticalBandVisits.at(i);
        }
        out << "],\\"critical_band_accepts\\":[";
        for (int i = 0; i <= criticalMaxBandVisited; ++i) {
            if (i) out << ',';
            out << criticalBandAccepts.at(i);
        }
        out << "],\\"budget_used\\":[";
''', "statistics")

    text = replace_once(text, '''        for (int round = 0; round < maxRounds && !finished(); ++round) {
            if (elapsed() > seconds * 0.65 || stalled >= 12) adaptive = true;
            std::vector<int> critical(loads.size());
            std::iota(critical.begin(), critical.end(), 0);
            int count = std::min<int>(32, static_cast<int>(critical.size()));
            std::partial_sort(critical.begin(), critical.begin() + count, critical.end(),
                [&](int a, int b) { return loads[a] != loads[b] ? loads[a] > loads[b] : a < b; });
            int position = critical[stalled % count], t = position / m, e = position % m;
            auto contributing = contributors(t, e);
            long long oldAccepted = accepted;
''', '''        for (int round = 0; round < maxRounds && !finished(); ++round) {
            roundsCompleted = round + 1;
            if (elapsed() > seconds * 0.65 || stalled >= 12) adaptive = true;
            std::vector<int> critical(loads.size());
            std::iota(critical.begin(), critical.end(), 0);
            CriticalRankChoice choice = selectCriticalRank(
                stalled, static_cast<int>(critical.size()), criticalRankLimit);
            std::partial_sort(critical.begin(), critical.begin() + choice.sortedPrefix, critical.end(),
                [&](int a, int b) { return loads[a] != loads[b] ? loads[a] > loads[b] : a < b; });
            int position = critical[choice.rank], t = position / m, e = position % m;
            criticalMaxRankVisited = std::max(criticalMaxRankVisited, choice.rank);
            criticalMaxBandVisited = std::max(criticalMaxBandVisited, choice.band);
            criticalBandVisits.at(choice.band) += 1;
            auto contributing = contributors(t, e);
            long long oldAccepted = accepted;
''', "critical coordinate selection")

    text = replace_once(text, '''            if (accepted > oldAccepted) stalled = 0; else ++stalled;
            if (adaptive && stalled >= 64) break;
        }
        writeSolution();
''', '''            if (accepted > oldAccepted) {
                criticalBandAccepts.at(choice.band) += accepted - oldAccepted;
                stalled = 0;
            } else {
                ++stalled;
            }
            if (adaptive && stalled >= criticalStallLimit) {
                stopReason = "stall_limit";
                break;
            }
        }
        if (interrupted) stopReason = "signal";
        else if (elapsed() >= seconds) stopReason = "time_limit";
        else if (stopReason != "stall_limit") stopReason = "round_limit";
        writeSolution();
''', "plateau accounting")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    if sha256(source) != BASE_SHA256:
        raise SystemExit("source is not exact fleet 2885d176 main.cpp")
    candidate = transform(source.decode("utf-8")).encode("utf-8")
    if sha256(candidate) != OUTPUT_SHA256:
        raise SystemExit("transformed source identity differs from recorded candidate")
    if args.output.exists():
        raise SystemExit("output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    print(json.dumps({"source_sha256": BASE_SHA256, "output_sha256": OUTPUT_SHA256,
                      "output_bytes": len(candidate), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

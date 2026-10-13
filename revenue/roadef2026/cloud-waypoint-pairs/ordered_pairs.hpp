// SPDX-License-Identifier: MIT
// CEDAR: bounded, deterministic ordered waypoint-pair enumeration.
#pragma once
#include <algorithm>
#include <cstddef>
#include <vector>

namespace cedar_pairs {
struct Result {
    bool accepted = false;
    bool exhausted = true;
    std::size_t tested = 0;
    std::size_t eligible = 0;
};

// The caller supplies the ranking and the exact route/budget/objective test.
// Width limits the input neighborhood, not the validity of an accepted move.
// A false exhausted flag reports an incomplete scan of that chosen neighborhood.
template<class Stop, class TryPair>
Result visit(const std::vector<int>& ranked, int source, int destination,
             std::size_t width, std::size_t max_pairs, Stop stop, TryPair try_pair) {
    std::vector<int> pool;
    pool.reserve(std::min(width, ranked.size()));
    for (int node : ranked) {
        if (pool.size() == width) break;
        if (node == source || node == destination || node < 0) continue;
        if (std::find(pool.begin(), pool.end(), node) == pool.end()) pool.push_back(node);
    }
    Result out;
    out.eligible = pool.size();
    for (int first : pool) for (int second : pool) {
        if (first == second) continue;
        if (out.tested == max_pairs || stop()) {
            out.exhausted = false;
            return out;
        }
        ++out.tested;
        if (try_pair(first, second)) {
            out.accepted = true;
            out.exhausted = false;
            return out;
        }
    }
    return out;
}
} // namespace cedar_pairs

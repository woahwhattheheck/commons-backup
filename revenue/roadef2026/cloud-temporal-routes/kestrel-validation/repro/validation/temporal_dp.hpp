// SPDX-License-Identifier: MIT
// Exact finite-pool temporal routing DP. Original implementation, ASTRA-KESTREL.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <iterator>
#include <stdexcept>
#include <utility>
#include <vector>

namespace kestrel {
using Score = std::vector<std::int64_t>;
struct Option { bool available = false; Score descending_loads; };
enum class Status { complete, infeasible, cancelled, too_large };
struct Result {
    Status status = Status::infeasible;
    std::vector<int> route_indices;
    Score descending_loads;
    std::size_t transitions_examined = 0;
};

// Each row contains the full link-load vector at that time, sorted descending.
// All times use the same finite route pool. allowed[t] is the transition budget
// left after the unchanged demands, with the old target-demand cost refunded.
// This is an exact optimum over this supplied pool, NOT over all possible paths.
// Adding the same multiset preserves sorted lexicographic order, so for each
// final route only the best feasible predecessor label must be retained.
inline Result optimize(const std::vector<std::vector<Option>>& rows,
                       const std::vector<std::vector<int>>& transition,
                       const std::vector<int>& allowed,
                       const std::function<bool()>& stopped = [] { return false; },
                       std::size_t max_cells = 2000000) {
    Result result;
    if (stopped()) { result.status = Status::cancelled; return result; }
    if (rows.empty() || rows.front().empty())
        throw std::invalid_argument("Need a nonempty horizon and route pool");
    const std::size_t times = rows.size(), count = rows.front().size();
    if (allowed.size() != times || transition.size() != count)
        throw std::invalid_argument("Transition dimensions differ");
    for (const auto& costs : transition) {
        if (costs.size() != count)
            throw std::invalid_argument("Transition matrix must be square");
        for (int cost : costs) if (cost < 0)
            throw std::invalid_argument("Negative transition cost");
    }
    for (std::size_t t = 1; t < times; ++t) if (allowed[t] < 0)
        throw std::invalid_argument("Negative residual budget");
    std::size_t width = 0;
    bool have_width = false;
    for (const auto& row : rows) {
        if (row.size() != count) throw std::invalid_argument("Ragged route pool");
        for (const auto& option : row) {
            if (stopped()) { result.status = Status::cancelled; return result; }
            if (!option.available) continue;
            const auto& score = option.descending_loads;
            if (!have_width) { width = score.size(); have_width = true; }
            if (score.size() != width ||
                !std::is_sorted(score.begin(), score.end(), std::greater<std::int64_t>()) ||
                (!score.empty() && score.back() < 0))
                throw std::invalid_argument("Scores require equal-width sorted nonnegative loads");
        }
    }
    if (!have_width) return result;
    // Check products without overflowing size_t. Also bound backpointer cells.
    if (count > max_cells / times ||
        (width && times * count > max_cells / width)) {
        result.status = Status::too_large; return result;
    }
    struct Label { bool feasible = false; Score loads; };
    std::vector<Label> previous(count), current(count);
    std::vector<std::vector<int>> parent(times, std::vector<int>(count, -1));
    for (std::size_t k = 0; k < count; ++k) if (rows[0][k].available)
        previous[k] = {true, rows[0][k].descending_loads};
    for (std::size_t t = 1; t < times; ++t) {
        for (std::size_t k = 0; k < count; ++k) {
            current[k] = Label{};
            if (!rows[t][k].available) continue;
            int best = -1;
            for (std::size_t p = 0; p < count; ++p) {
                if (stopped()) { result.status = Status::cancelled; return result; }
                ++result.transitions_examined;
                if (!previous[p].feasible || transition[p][k] > allowed[t]) continue;
                if (best < 0 || previous[p].loads < previous[best].loads)
                    best = static_cast<int>(p);
            }
            if (best < 0) continue;
            current[k].feasible = true;
            parent[t][k] = best;
            const auto& prefix = previous[best].loads;
            const auto& addition = rows[t][k].descending_loads;
            auto& merged = current[k].loads;
            merged.reserve(prefix.size() + addition.size());
            std::merge(prefix.begin(), prefix.end(), addition.begin(), addition.end(),
                       std::back_inserter(merged), std::greater<std::int64_t>());
            if (stopped()) { result.status = Status::cancelled; return result; }
        }
        previous.swap(current);
    }
    int best = -1;
    for (std::size_t k = 0; k < count; ++k)
        if (previous[k].feasible && (best < 0 || previous[k].loads < previous[best].loads))
            best = static_cast<int>(k);
    if (best < 0) return result;
    if (stopped()) { result.status = Status::cancelled; return result; }
    std::vector<int> chosen(times);
    int k = best;
    for (std::size_t t = times; t-- > 0;) { chosen[t] = k; k = parent[t][k]; }
    result.route_indices = std::move(chosen);
    result.descending_loads = std::move(previous[best].loads);
    result.status = Status::complete;
    return result;
}
} // namespace kestrel

// SPDX-License-Identifier: MIT
// Exact lexicographic route-menu optimization across bounded time layers.
#pragma once
#include <algorithm>
#include <cstddef>
#include <functional>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace dock_temporal {
using Objective = std::vector<long long>;
struct Option {
    bool reachable = true;
    Objective cost; // All edge saturations at this slot, descending, six-decimal integers.
};
struct Result {
    bool complete = false;
    bool feasible = false;
    std::vector<int> choices;
    Objective objective;
    std::size_t transitions_examined = 0;
};

// Unchanged loads cancel in multiset lex order. More generally, if X < Y,
// sorted(X union Z) < sorted(Y union Z). Thus for the same terminal option,
// only the best feasible prefix must be retained; adding that option's cost
// cannot reverse the prefix order. No sum/peak surrogate is used.
//
// transition_cost(t, previous, current) is a nonnegative integer. budgets[t]
// is the residual budget with all OTHER demands fixed; budgets[0] is ignored.
// Cancellation returns incomplete, never a partial schedule to execute.
// Valid inputs and callback behavior are a caller contract; malformed matrices
// and negative transition costs are rejected before they can choose a route.
template<class Distance, class Cancel>
Result solve(const std::vector<std::vector<Option>>& layers,
             const std::vector<int>& budgets, Distance transition_cost, Cancel cancel) {
    Result result;
    const std::size_t h = layers.size();
    if (h == 0 || budgets.size() != h) throw std::invalid_argument("invalid temporal horizon");
    std::size_t width = 0;
    bool have_width = false;
    for (std::size_t t = 0; t < h; ++t) {
        if (cancel()) return result;
        if (layers[t].empty()) throw std::invalid_argument("empty route menu");
        if (t && budgets[t] < 0) throw std::invalid_argument("negative residual budget");
        for (const auto& option : layers[t]) {
            if (!option.reachable) continue;
            if (!have_width) { width = option.cost.size(); have_width = true; }
            if (option.cost.size() != width ||
                !std::is_sorted(option.cost.begin(), option.cost.end(), std::greater<long long>()))
                throw std::invalid_argument("unaligned or unsorted objective");
            if (!option.cost.empty() && option.cost.back() < 0)
                throw std::invalid_argument("negative load coordinate");
        }
    }
    if (have_width && h > std::numeric_limits<std::size_t>::max() / std::max<std::size_t>(width, 1))
        throw std::length_error("temporal objective size overflow");
    std::vector<Objective> previous(layers[0].size());
    std::vector<bool> previous_ok(layers[0].size(), false);
    std::vector<std::vector<int>> parents(h);
    parents[0].assign(layers[0].size(), -1);
    for (std::size_t k = 0; k < layers[0].size(); ++k) {
        if (cancel()) return result;
        if (layers[0][k].reachable) {
            previous[k] = layers[0][k].cost;
            previous_ok[k] = true;
        }
    }
    // Start with the landed ranked path. Each completed layer supplies enough
    // transition-scan evidence to choose the next layer without extra callback
    // probes. Direct layers can switch back when their actual feasible-prefix
    // comparison work amortizes ranking again.
    bool prefer_ranked = true;
    std::size_t ranked_pressure_streak = 0;
    for (std::size_t t = 1; t < h; ++t) {
        // Adding the SAME current option preserves the lexicographic order of
        // predecessor prefixes. Ranked and direct scans therefore choose the
        // same parent; stable ordering preserves V1's lowest-index tie-break.
        std::vector<int> predecessor_order;
        predecessor_order.reserve(previous.size());
        for (std::size_t j = 0; j < previous.size(); ++j)
            if (previous_ok[j]) predecessor_order.push_back(static_cast<int>(j));
        std::size_t reachable_count = 0;
        for (const auto& option : layers[t])
            reachable_count += option.reachable ? 1U : 0U;
        // Sorting cannot amortize with one destination. Tiny predecessor menus
        // retain PR10363's exact ranked behavior and its established 3-to-1 case.
        const bool ranked = predecessor_order.size() <= 3 ? true
            : reachable_count <= 1 ? false : prefer_ranked;
        if (ranked) {
            std::stable_sort(predecessor_order.begin(), predecessor_order.end(),
                [&](int a, int b) { return previous[static_cast<std::size_t>(a)] <
                                          previous[static_cast<std::size_t>(b)]; });
        }

        std::vector<Objective> current(layers[t].size());
        std::vector<bool> current_ok(layers[t].size(), false);
        parents[t].assign(layers[t].size(), -1);
        const std::size_t transitions_before_layer = result.transitions_examined;
        std::size_t direct_comparisons = 0;
        for (std::size_t k = 0; k < layers[t].size(); ++k) {
            if (cancel()) return result;
            if (!layers[t][k].reachable) continue;
            int best = -1;
            if (ranked) {
                // Keep the landed ranked hot path byte-structurally simple:
                // the first feasible predecessor is already optimal.
                for (int candidate : predecessor_order) {
                    if (cancel()) return result;
                    const std::size_t j = static_cast<std::size_t>(candidate);
                    int used = transition_cost(t, j, k);
                    ++result.transitions_examined;
                    if (used < 0) throw std::invalid_argument("negative transition cost");
                    if (used > budgets[t]) continue;
                    best = candidate;
                    break;
                }
            } else {
                for (int candidate : predecessor_order) {
                    if (cancel()) return result;
                    const std::size_t j = static_cast<std::size_t>(candidate);
                    int used = transition_cost(t, j, k);
                    ++result.transitions_examined;
                    if (used < 0) throw std::invalid_argument("negative transition cost");
                    if (used > budgets[t]) continue;
                    if (best >= 0) ++direct_comparisons;
                    if (best < 0 || previous[j] < previous[static_cast<std::size_t>(best)])
                        best = candidate;
                }
            }
            if (best < 0) continue;
            const auto& prefix = previous[static_cast<std::size_t>(best)];
            const auto& local = layers[t][k].cost;
            current[k].reserve(prefix.size() + local.size());
            std::merge(prefix.begin(), prefix.end(), local.begin(), local.end(),
                       std::back_inserter(current[k]), std::greater<long long>());
            parents[t][k] = best;
            current_ok[k] = true;
        }

        if (predecessor_order.size() > 3 && reachable_count > 1) {
            if (ranked) {
                // A ranked layer that still scans at least a quarter of every
                // predecessor for long objectives has little callback saving
                // left to offset sorting. Fall back on the next layer. This
                // observation is free: it uses calls the ranked solve made.
                const long double full_scan =
                    static_cast<long double>(predecessor_order.size()) *
                    static_cast<long double>(reachable_count);
                std::size_t prefix_width = 0;
                if (!predecessor_order.empty())
                    prefix_width = previous[static_cast<std::size_t>(predecessor_order.front())].size();
                const std::size_t layer_transitions =
                    result.transitions_examined - transitions_before_layer;
                const bool high_scan_pressure = prefix_width >= 32 &&
                    static_cast<long double>(layer_transitions) * 4.0L >= full_scan;
                if (high_scan_pressure) {
                    if (ranked_pressure_streak < 2) ++ranked_pressure_streak;
                } else {
                    ranked_pressure_streak = 0;
                }
                // One irregular layer is common in the retained public models;
                // require persistence before abandoning the ranked path.
                prefer_ranked = ranked_pressure_streak < 2;
            } else {
                // On a direct layer, the exact number of feasible-prefix vector
                // comparisons is known. Rank the next layer only when those
                // comparisons can pay even a conservative insertion-sort bound.
                const long double conservative_sort =
                    static_cast<long double>(predecessor_order.size()) *
                    static_cast<long double>(predecessor_order.size() - 1) / 2.0L;
                prefer_ranked = static_cast<long double>(direct_comparisons) >= conservative_sort;
                if (prefer_ranked) ranked_pressure_streak = 0;
            }
        }
        previous.swap(current); previous_ok.swap(current_ok);
    }
    if (cancel()) return result;
    int best = -1;
    for (std::size_t k = 0; k < previous.size(); ++k)
        if (previous_ok[k] && (best < 0 || previous[k] < previous[static_cast<std::size_t>(best)]))
            best = static_cast<int>(k);
    result.complete = true;
    if (best < 0) return result;
    result.feasible = true;
    result.objective = std::move(previous[static_cast<std::size_t>(best)]);
    result.choices.resize(h);
    for (std::size_t t = h; t-- > 0;) {
        result.choices[t] = best;
        best = parents[t][static_cast<std::size_t>(best)];
    }
    return result;
}
} // namespace dock_temporal

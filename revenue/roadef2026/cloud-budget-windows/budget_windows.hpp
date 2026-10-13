// SPDX-License-Identifier: MIT
// Budget-feasible asymmetric time-window proposals. ASTRA-RELAY-COOLDOWN.
#pragma once
#include <algorithm>
#include <cstdlib>
#include <stdexcept>
#include <tuple>
#include <utility>
#include <vector>

namespace budget_windows {
// A constant replacement has zero internal transition cost. Only its two
// boundary transitions can consume additional budget. Scan each side once;
// pair the nearest feasible boundaries in increasing interval length.
template<class LeftFeasible, class RightFeasible>
std::vector<std::pair<int, int>> nearest(int horizon, int focus, int count,
                                        LeftFeasible left_ok, RightFeasible right_ok) {
    if (horizon < 1 || focus < 0 || focus >= horizon || count < 0)
        throw std::invalid_argument("invalid window dimensions");
    std::vector<int> left, right;
    for (int t = focus; t >= 0 && static_cast<int>(left.size()) < count; --t)
        if (left_ok(t)) left.push_back(t);
    for (int t = focus; t < horizon && static_cast<int>(right.size()) < count; ++t)
        if (right_ok(t)) right.push_back(t);
    std::vector<std::pair<int, int>> result;
    for (int l : left) for (int r : right) result.emplace_back(l, r);
    std::sort(result.begin(), result.end(), [focus](auto a, auto b) {
        return std::tuple{a.second-a.first, std::abs(focus-a.first-(a.second-focus)), a.first}
             < std::tuple{b.second-b.first, std::abs(focus-b.first-(b.second-focus)), b.first};
    });
    return result;
}
} // namespace budget_windows

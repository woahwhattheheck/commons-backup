// SPDX-License-Identifier: MIT
// Exact-flow-equivalent waypoint removal. No primary objective is approximated.
#pragma once
#include <algorithm>
#include <cstddef>
#include <optional>
#include <stdexcept>
#include <utility>
#include <vector>

namespace budget_release {
struct Counters {
    std::size_t proposals = 0, flow_checks = 0, budget_rejected = 0;
    std::size_t flow_rejected = 0;
    bool stopped = false;
};

template<class Route> struct Proposal {
    int demand, left, right;
    Route next;
    std::vector<int> used_after;
};

// Routes and cached normalized unit flows use demand-major, time-minor order.
// flow_for(d,t,next,out) and distance(d,a,b) are the EXISTING solver functions.
// stop() is cooperative; a late callback return is never committed here.
// A maximal constant run is shortened by one waypoint only. Every boundary
// must consume no more budget, and at least one boundary must consume less.
// Thus repeated accepted calls cannot cycle (the waypoint count also falls).
template<class Route, class Flow, class FlowFor, class Distance, class Stop>
std::optional<Proposal<Route>> find_release(
    const std::vector<Route>& routes, const std::vector<Flow>& flows,
    int horizon, const std::vector<int>& used,
    FlowFor flow_for, Distance distance, Stop stop,
    Counters& counts, std::size_t max_proposals = 4096) {
    if (horizon < 1 || used.size() != static_cast<std::size_t>(horizon) ||
        routes.size() != flows.size() || routes.size() % horizon != 0)
        throw std::invalid_argument("budget release: inconsistent dimensions");
    if (std::any_of(used.begin(), used.end(), [](int x) { return x < 0; }))
        throw std::invalid_argument("budget release: negative transition usage");
    std::size_t inspected = 0;
    const int demands = static_cast<int>(routes.size() / horizon);
    for (int d = 0; d < demands; ++d) {
        const int base = d * horizon;
        for (int left = 0; left < horizon;) {
            if (stop()) { counts.stopped = true; return std::nullopt; }
            int right = left;
            const Route& old = routes[base + left];
            while (right + 1 < horizon && routes[base + right + 1] == old) ++right;
            for (std::size_t k = 0; k < old.size(); ++k) {
                if (inspected >= max_proposals || stop()) {
                    counts.stopped = true; return std::nullopt;
                }
                ++inspected; ++counts.proposals;
                Route next = old;
                next.erase(next.begin() + k);
                std::vector<int> after = used;
                if (left > 0) after[left] +=
                    distance(d, routes[base + left - 1], next) -
                    distance(d, routes[base + left - 1], old);
                if (right + 1 < horizon) after[right + 1] +=
                    distance(d, next, routes[base + right + 1]) -
                    distance(d, old, routes[base + right + 1]);
                bool strict = false, worse = false;
                for (int t = 1; t < horizon; ++t) {
                    strict |= after[t] < used[t];
                    worse |= after[t] > used[t] || after[t] < 0;
                }
                if (worse || !strict) { ++counts.budget_rejected; continue; }
                bool same = true;
                for (int t = left; t <= right; ++t) {
                    if (stop()) { counts.stopped = true; return std::nullopt; }
                    Flow projected;
                    ++counts.flow_checks;
                    if (!flow_for(d, t, next, projected) || projected != flows[base + t]) {
                        same = false; break;
                    }
                    if (stop()) { counts.stopped = true; return std::nullopt; }
                }
                if (!same) { ++counts.flow_rejected; continue; }
                if (stop()) { counts.stopped = true; return std::nullopt; }
                return Proposal<Route>{d, left, right, std::move(next), std::move(after)};
            }
            left = right + 1;
        }
    }
    return std::nullopt;
}
} // namespace budget_release

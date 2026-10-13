// SPDX-License-Identifier: MIT
// Test-only consumer of the unmodified fleet mechanics and DATE operator.
#include "fleet_visible.cpp"
#include "budget_release.hpp"
#include <cstring>

static void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

int main(int argc, char** argv) {
    if (argc != 7) {
        std::cerr << "usage: witness net tm scenario incumbent output original|release|release-only|no-release|zero-work|cancel|late-cancel\n";
        return 2;
    }
    try {
        setenv("CLOUD_INITIAL_SOLUTION", argv[4], 1);
        Solver s(argv[1], argv[2], argv[3], argv[5]);
        const std::string mode = argv[6];
        if (mode == "no-release" || mode == "zero-work" || mode == "cancel" || mode == "late-cancel") {
            const auto routes = s.routes;
            const auto flows = s.routed;
            const auto loads = s.loads;
            const auto used = s.used;
            bool stopped = mode == "cancel";
            budget_release::Counters counts;
            auto proposal = budget_release::find_release(
                s.routes, s.routed, s.h, s.used,
                [&](int d, int t, const Route& r, Sparse& f) {
                    bool ok = s.routeFlow(d, t, r, f);
                    if (mode == "late-cancel") stopped = true;
                    return ok;
                },
                [&](int d, const Route& a, const Route& b) { return s.distance(d, a, b); },
                [&] { return stopped; }, counts, mode == "zero-work" ? 0 : 64);
            require(!proposal, "negative control returned a release");
            require(s.routes == routes && s.routed == flows && s.loads == loads && s.used == used,
                    "negative control changed input");
            if (mode == "zero-work" || mode == "cancel")
                require(counts.flow_checks == 0 && counts.stopped, "unexpected cancelled work");
            if (mode == "late-cancel") require(counts.flow_checks == 1 && counts.stopped,
                                               "late callback not discarded");
            std::cerr << "NEGATIVE " << mode << " proposals=" << counts.proposals
                      << " flow_checks=" << counts.flow_checks << " unchanged=true\n";
            s.writeSolution(); s.statistics(); return 0;
        }
        if (mode != "original" && mode != "release" && mode != "release-only")
            throw std::runtime_error("unknown test mode");
        if (mode != "original") {
            const auto original_routes = s.routes;
            const auto original_flows = s.routed;
            const auto original_loads = s.loads;
            const auto original_used = s.used;
            // The profitable main-demand detour is blocked by unrelated budget.
            require(!s.move(1, 1, 1, Route{6}), "pre-release improvement should be blocked");
            require(s.routes == original_routes && s.loads == original_loads && s.used == original_used,
                    "rejected move mutated the incumbent");
            budget_release::Counters counts;
            auto proposal = budget_release::find_release(
                s.routes, s.routed, s.h, s.used,
                [&](int d, int t, const Route& r, Sparse& f) { return s.routeFlow(d, t, r, f); },
                [&](int d, const Route& a, const Route& b) { return s.distance(d, a, b); },
                [] { return false; }, counts, 64);
            require(proposal.has_value(), "missing exact-flow budget release");
            require(s.routes == original_routes && s.routed == original_flows &&
                    s.loads == original_loads && s.used == original_used,
                    "proposal finder mutated its inputs");
            require(proposal->demand == 0 && proposal->left == 1 && proposal->right == 1 &&
                    proposal->next.empty(), "unexpected release witness");
            require(proposal->used_after == std::vector<int>({0, 0}), "budget not released");
            // Test-only application of the returned proposal. No search/acceptance
            // implementation is introduced: the operator belongs to DATE.
            for (int t = proposal->left; t <= proposal->right; ++t) {
                Sparse actual;
                require(s.routeFlow(proposal->demand, t, proposal->next, actual), "unreachable release");
                require(actual == s.routed[proposal->demand * s.h + t], "flow differs after release");
                s.routes[proposal->demand * s.h + t] = proposal->next;
            }
            s.used = proposal->used_after;
            require(std::memcmp(s.loads.data(), original_loads.data(), s.loads.size()*sizeof(double)) == 0,
                    "neutral application changed load bits");
            // Independently recalculate aggregate boundary cost from every route.
            for (int t = 1; t < s.h; ++t) {
                int actual = 0;
                for (int d = 0; d < static_cast<int>(s.demands.size()); ++d)
                    actual += s.distance(d, s.routes[d*s.h+t-1], s.routes[d*s.h+t]);
                require(actual == s.used[t] && actual <= s.budget[t], "recomputed budget mismatch");
            }
            std::cerr << "NEUTRAL proposal d=0 interval=[1,1] before_budget=3 after_budget=0"
                      << " exact_flow=true load_bits_unchanged=true proposals=" << counts.proposals << '\n';
        }
        if (mode == "release-only") { s.writeSolution(); s.statistics(); }
        else s.run();
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}

// SPDX-License-Identifier: MIT
#include "temporal_dp.hpp"
#include <algorithm>
#include <cassert>
#include <iostream>
#include <random>
#include <vector>
#ifdef NDEBUG
#error "Compile the test without NDEBUG; its assertions must execute."
#endif
using namespace dock_temporal;

struct ReferenceResult {
    bool feasible = false;
    std::vector<int> choices;
    Objective objective;
    std::size_t transitions_examined = 0;
};

template<class Distance>
ReferenceResult solve_v1(const std::vector<std::vector<Option>>& layers,
                         const std::vector<int>& budgets, Distance distance) {
    const std::size_t h = layers.size();
    std::vector<Objective> previous(layers[0].size());
    std::vector<bool> previous_ok(layers[0].size(), false);
    std::vector<std::vector<int>> parents(h);
    parents[0].assign(layers[0].size(), -1);
    for (std::size_t k = 0; k < layers[0].size(); ++k) {
        if (layers[0][k].reachable) {
            previous[k] = layers[0][k].cost;
            previous_ok[k] = true;
        }
    }
    ReferenceResult result;
    for (std::size_t t = 1; t < h; ++t) {
        std::vector<Objective> current(layers[t].size());
        std::vector<bool> current_ok(layers[t].size(), false);
        parents[t].assign(layers[t].size(), -1);
        for (std::size_t k = 0; k < layers[t].size(); ++k) {
            if (!layers[t][k].reachable) continue;
            int best = -1;
            for (std::size_t j = 0; j < previous.size(); ++j) {
                if (!previous_ok[j]) continue;
                ++result.transitions_examined;
                if (distance(t, j, k) > budgets[t]) continue;
                if (best < 0 || previous[j] < previous[static_cast<std::size_t>(best)])
                    best = static_cast<int>(j);
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
        previous.swap(current);
        previous_ok.swap(current_ok);
    }
    int best = -1;
    for (std::size_t k = 0; k < previous.size(); ++k)
        if (previous_ok[k] && (best < 0 || previous[k] < previous[static_cast<std::size_t>(best)]))
            best = static_cast<int>(k);
    if (best < 0) return result;
    result.feasible = true;
    result.objective = previous[static_cast<std::size_t>(best)];
    result.choices.resize(h);
    for (std::size_t t = h; t-- > 0;) {
        result.choices[t] = best;
        best = parents[t][static_cast<std::size_t>(best)];
    }
    return result;
}

int main() {
    std::vector<std::vector<Option>> discriminator{
        {{true,{9}}, {true,{1}}, {true,{5}}},
        {{true,{7}}}
    };
    std::vector<int> discriminator_budget{0,0};
    auto distance = [](std::size_t, std::size_t from, std::size_t) {
        return from == 1 ? 0 : 1;
    };
    auto old = solve_v1(discriminator, discriminator_budget, distance);
    auto ranked = solve(discriminator, discriminator_budget, distance, []{ return false; });
    assert(old.feasible && ranked.complete && ranked.feasible);
    assert(old.choices == ranked.choices && ranked.choices == std::vector<int>({1,0}));
    assert(old.objective == ranked.objective);
    assert(old.transitions_examined == 3 && ranked.transitions_examined == 1);

    std::vector<std::vector<Option>> tied{
        {{true,{4,2}}, {true,{4,2}}, {true,{7,1}}},
        {{true,{3,1}}}
    };
    auto tied_distance = [](std::size_t, std::size_t from, std::size_t) {
        return from < 2 ? 0 : 1;
    };
    auto old_tied = solve_v1(tied, {0,0}, tied_distance);
    auto ranked_tied = solve(tied, {0,0}, tied_distance, []{ return false; });
    assert(old_tied.choices == ranked_tied.choices);
    assert(ranked_tied.choices == std::vector<int>({0,0}));

    std::mt19937 rng(20260908);
    std::size_t models = 0, saved = 0, improved_models = 0;
    for (int trial = 0; trial < 20000; ++trial) {
        const int h = 1 + rng()%6, k = 1 + rng()%6, width = rng()%5;
        std::vector<std::vector<Option>> layers(h, std::vector<Option>(k));
        std::vector<int> budgets(h);
        std::vector<std::vector<std::vector<int>>> costs(h,
            std::vector<std::vector<int>>(k, std::vector<int>(k)));
        for (int t=0; t<h; ++t) {
            budgets[t] = rng()%7;
            for (int a=0; a<k; ++a) {
                layers[t][a].reachable = (rng()%5)!=0;
                for (int e=0; e<width; ++e) layers[t][a].cost.push_back(rng()%23);
                std::sort(layers[t][a].cost.begin(), layers[t][a].cost.end(), std::greater<long long>());
                for (int b=0; b<k; ++b) costs[t][a][b] = rng()%8;
            }
        }
        auto cost = [&](std::size_t t, std::size_t a, std::size_t b) {
            return costs[t][a][b];
        };
        auto before = solve_v1(layers, budgets, cost);
        auto after = solve(layers, budgets, cost, []{ return false; });
        assert(after.complete);
        assert(before.feasible == after.feasible);
        if (before.feasible) {
            assert(before.objective == after.objective);
            assert(before.choices == after.choices);
        }
        assert(after.transitions_examined <= before.transitions_examined);
        saved += before.transitions_examined - after.transitions_examined;
        if (after.transitions_examined < before.transitions_examined) ++improved_models;
        ++models;
    }
    assert(saved > 0 && improved_models > 0);
    std::cout << "{\"models\":" << models
              << ",\"models_with_fewer_transition_checks\":" << improved_models
              << ",\"transition_checks_saved\":" << saved
              << ",\"discriminator\":\"3_to_1\",\"status\":\"PASS\"}\n";
}

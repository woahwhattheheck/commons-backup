// SPDX-License-Identifier: MIT
#include "temporal_dp.hpp"
#include <cassert>
#include <iostream>
#include <random>
#include <functional>
#include <climits>
#ifdef NDEBUG
#error "Compile the test without NDEBUG; its assertions must execute."
#endif
using namespace dock_temporal;

int main() {
    std::mt19937 rng(20260908);
    std::size_t checked = 0;
    // Deterministic exhaustive oracle: all complete paths, not another DP.
    for (int trial = 0; trial < 5000; ++trial) {
        int h = 1 + rng()%6, k = 1 + rng()%4, width = rng()%5;
        std::vector<std::vector<Option>> layers(h, std::vector<Option>(k));
        std::vector<int> budget(h);
        std::vector<std::vector<std::vector<int>>> distance(h,
             std::vector<std::vector<int>>(k, std::vector<int>(k)));
        for (int t=0;t<h;++t) {
            budget[t]=rng()%7;
            for (int a=0;a<k;++a) {
                layers[t][a].reachable = (rng()%5)!=0;
                for (int e=0;e<width;++e) layers[t][a].cost.push_back(rng()%23);
                std::sort(layers[t][a].cost.begin(),layers[t][a].cost.end(),std::greater<long long>());
                for (int b=0;b<k;++b) distance[t][a][b]=rng()%8;
            }
        }
        bool any=false; Objective exact; std::vector<int> path(h);
        std::function<void(int,Objective)> enumerate = [&](int t,Objective values) {
            if (t==h) {
                ++checked;
                std::sort(values.begin(),values.end(),std::greater<long long>());
                if (!any || values<exact) exact=values;
                any=true; return;
            }
            for (int a=0;a<k;++a) {
                if (!layers[t][a].reachable || (t && distance[t][path[t-1]][a]>budget[t])) continue;
                path[t]=a;
                auto next=values;
                next.insert(next.end(),layers[t][a].cost.begin(),layers[t][a].cost.end());
                enumerate(t+1,std::move(next));
            }
        };
        enumerate(0,{});
        auto got=solve(layers,budget,[&](std::size_t t,std::size_t a,std::size_t b){return distance[t][a][b];},[]{return false;});
        assert(got.complete && got.feasible==any);
        if (any) {
            assert(got.objective==exact && got.choices.size()==static_cast<std::size_t>(h));
            Objective replay;
            for(int t=0;t<h;++t) {
                int a=got.choices[t]; assert(layers[t][a].reachable);
                if(t) assert(distance[t][got.choices[t-1]][a]<=budget[t]);
                replay.insert(replay.end(),layers[t][a].cost.begin(),layers[t][a].cost.end());
            }
            std::sort(replay.begin(),replay.end(),std::greater<long long>());
            assert(replay==exact);
        }
    }
    // Equal peak, unequal later coordinates: total or peak is not the objective.
    std::vector<std::vector<Option>> x{{{true,{10,9,0}},{true,{10,8,8}}}};
    auto lex=solve(x,{0},[](auto,auto,auto){return 0;},[]{return false;});
    assert(lex.choices==std::vector<int>{1});
    auto cancelled=solve(x,{0},[](auto,auto,auto){return 0;},[]{return true;});
    assert(!cancelled.complete && !cancelled.feasible && cancelled.choices.empty());
    std::vector<std::vector<Option>> narrow{{{true,{4}}},{{true,{3}}}};
    auto impossible=solve(narrow,{0,0},[](auto,auto,auto){return 1;},[]{return false;});
    assert(impossible.complete && !impossible.feasible);
    // Different layer menu lengths and near-limit integer coordinates.
    auto jagged=solve({{{true,{LLONG_MAX,4}},{true,{LLONG_MAX,3}}},
                      {{true,{8,2}}},{{false,{}},{true,{7,1}},{true,{6,5}}}},
                     {0,1,1},[](auto,auto,auto){return 1;},[]{return false;});
    assert(jagged.complete && jagged.feasible && jagged.choices==std::vector<int>({1,0,2}));
    int checks=0;
    auto lateCancel=solve(narrow,{0,0},[&](auto,auto,auto){++checks;return 0;},[&]{return checks>0;});
    assert(!lateCancel.complete && !lateCancel.feasible && lateCancel.choices.empty());
    int errors=0;
    try { solve({}, {}, [](auto,auto,auto){return 0;},[]{return false;}); } catch(const std::invalid_argument&){++errors;}
    try { solve(narrow,{0,-1},[](auto,auto,auto){return 0;},[]{return false;}); } catch(const std::invalid_argument&){++errors;}
    try { solve(narrow,{0,0},[](auto,auto,auto){return -1;},[]{return false;}); } catch(const std::invalid_argument&){++errors;}
    try { solve({{{true,{1,2}}}},{0},[](auto,auto,auto){return 0;},[]{return false;}); } catch(const std::invalid_argument&){++errors;}
    assert(errors==4);
    std::cout << "{\"generated_models\":5000,\"exhaustive_feasible_paths\":"<<checked<<",\"focused_cases\":9,\"status\":\"PASS\"}\n";
}

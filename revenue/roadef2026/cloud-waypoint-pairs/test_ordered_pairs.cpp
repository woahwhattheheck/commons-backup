// SPDX-License-Identifier: MIT
#include "ordered_pairs.hpp"
#include <cassert>
#include <iostream>
#include <random>
#include <set>
#include <utility>

int main() {
    std::mt19937 rng(20260908);
    std::size_t cases = 0, comparisons = 0;
    for (int test = 0; test < 1000; ++test) {
        std::vector<int> raw;
        for (int i = 0; i < int(rng()%45); ++i) raw.push_back(int(rng()%18)-2);
        const int s=int(rng()%16), t=int(rng()%16);
        const std::size_t width=rng()%20;
        std::vector<int> pool;
        for (int n : raw) {
            if (pool.size() == width) break;
            if (n >= 0 && n != s && n != t && std::find(pool.begin(), pool.end(), n)==pool.end()) pool.push_back(n);
        }
        std::vector<std::pair<int,int>> expected;
        for(int a:pool)for(int b:pool)if(a!=b)expected.emplace_back(a,b);
        for (std::size_t cap : {std::size_t(0), std::size_t(1), std::size_t(7), std::size_t(1000)}) {
            std::vector<std::pair<int,int>> got;
            auto out=cedar_pairs::visit(raw,s,t,width,cap,[]{return false;},[&](int a,int b){got.emplace_back(a,b);return false;});
            auto end=std::min(cap,expected.size());
            assert((got==std::vector<std::pair<int,int>>(expected.begin(),expected.begin()+end)));
            assert(out.tested==end && out.eligible==pool.size() && !out.accepted);
            assert(out.exhausted == (end==expected.size()));
            comparisons+=end; ++cases;
        }
        std::vector<std::pair<int,int>> got;
        auto stopped=cedar_pairs::visit(raw,s,t,width,1000,[]{return true;},[&](int a,int b){got.emplace_back(a,b);return false;});
        assert(got.empty() && !stopped.accepted);
        if(!expected.empty())assert(!stopped.exhausted);
        ++cases;
        if (!expected.empty()) {
            auto target=expected[rng()%expected.size()];
            auto out=cedar_pairs::visit(raw,s,t,width,1000,[]{return false;},[&](int a,int b){return std::pair{a,b}==target;});
            assert(out.accepted && !out.exhausted);
            assert(out.tested == std::size_t(std::find(expected.begin(),expected.end(),target)-expected.begin()+1));
            ++cases;
        }
    }
    // Ordering is essential: reverse and forward pairs both remain eligible.
    std::vector<std::pair<int,int>> got;
    cedar_pairs::visit({4,3,4,2,0,1},0,1,3,100,[]{return false;},[&](int a,int b){got.emplace_back(a,b);return false;});
    assert((got==std::vector<std::pair<int,int>>{{4,3},{4,2},{3,4},{3,2},{2,4},{2,3}}));
    std::cout << "{\"passed\":true,\"property_cases\":"<<cases+1<<",\"ordered_pair_comparisons\":"<<comparisons+6<<"}\n";
}

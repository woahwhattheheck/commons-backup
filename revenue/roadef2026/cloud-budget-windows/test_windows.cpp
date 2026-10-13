// SPDX-License-Identifier: MIT
#include "budget_windows.hpp"
#include <cassert>
#include <iostream>
#include <random>
#include <set>
#include <vector>
using Route = std::vector<int>;
int distance(const Route& a, const Route& b) {
    auto segments=[](const Route& r){
        std::set<std::pair<int,int>> s;int last=0;
        for(int v:r){s.emplace(last,v);last=v;}s.emplace(last,9);return s;
    };
    auto x=segments(a), y=segments(b);int common=0;
    for(auto v:x)common+=y.count(v);
    return static_cast<int>(x.size()+y.size())-2*common;
}
int main() {
    std::mt19937 rng(20260908);
    std::vector<Route> options{{},{1},{2},{3},{1,2},{3,1},{2,4}};
    long long checked=0;
    for(int trial=0;trial<4000;trial++) {
        int h=1+rng()%9,focus=rng()%h;
        std::vector<Route> current(h);
        for(auto& r:current)r=options[rng()%options.size()];
        const auto& next=options[rng()%options.size()];
        std::vector<int> used(h),budget(h);
        for(int t=1;t<h;t++) {
            used[t]=rng()%11+distance(current[t-1],current[t]);
            budget[t]=used[t]+rng()%5;
        }
        auto left=[&](int l){return l==0 || used[l]-distance(current[l-1],current[l])+distance(current[l-1],next)<=budget[l];};
        auto right=[&](int r){return r==h-1 || used[r+1]-distance(current[r],current[r+1])+distance(next,current[r+1])<=budget[r+1];};
        auto actual=budget_windows::nearest(h,focus,h,left,right);
        std::set<std::pair<int,int>> expected;
        for(int l=0;l<=focus;l++)for(int r=focus;r<h;r++) {
            auto proposed=current;
            for(int t=l;t<=r;t++)proposed[t]=next;
            bool ok=true;
            for(int t=1;t<h;t++)
                ok &= used[t]-distance(current[t-1],current[t])+distance(proposed[t-1],proposed[t])<=budget[t];
            if(ok)expected.emplace(l,r);
            checked++;
        }
        assert((std::set<std::pair<int,int>>(actual.begin(),actual.end())==expected));
        auto limited=budget_windows::nearest(h,focus,4,left,right);
        assert(limited.size()<=16);
        for(auto interval:limited)assert(expected.count(interval));
        for(size_t i=1;i<limited.size();i++)
            assert(limited[i-1].second-limited[i-1].first<=limited[i].second-limited[i].first);
        assert(budget_windows::nearest(h,focus,0,left,right).empty());
    }
    auto yes=[](int){return true;};
    for(auto [h,t,k]:std::vector<std::tuple<int,int,int>>{{0,0,1},{4,-1,1},{4,4,1},{4,0,-1}}){
        bool rejected=false;try{budget_windows::nearest(h,t,k,yes,yes);}catch(const std::invalid_argument&){rejected=true;}assert(rejected);
    }
    auto long_window=budget_windows::nearest(17,4,1,[](int t){return t==4||t==0;},[](int t){return t==12||t==16;});
    assert((long_window==std::vector<std::pair<int,int>>{{4,12}}));
    std::cout << "PASS 4000 boundary models; " << checked << " exhaustive interval comparisons; bounded/order/dimension controls\n";
}

// SPDX-License-Identifier: MIT
#include "budget_release.hpp"
#include <cassert>
#include <iostream>
#include <random>
#include <set>
using Route = std::vector<int>;
using Flow = std::vector<std::pair<int,double>>;
static int distance(int, const Route& a, const Route& b) {
    auto segments=[](const Route& p){
        std::set<std::pair<int,int>> s; int last=0;
        for(int v:p){s.emplace(last,v);last=v;} s.emplace(last,9); return s;
    };
    auto x=segments(a),y=segments(b); int result=0;
    for(auto e:x)result+=!y.count(e);
    for(auto e:y)result+=!x.count(e);
    return result;
}
static std::vector<int> usage(const std::vector<Route>& r,int h){
    std::vector<int> u(h);
    for(std::size_t d=0;d<r.size()/h;++d)for(int t=1;t<h;++t)
        u[t]+=distance(d,r[d*h+t-1],r[d*h+t]);
    return u;
}
static Flow f(int d,int t,const Route& r){
    // Explicit manufactured flow families, not official graph evidence.
    // All routes using only nodes 1/2 are flow equivalent; 3 changes one edge.
    int tag=std::find(r.begin(),r.end(),3)!=r.end();
    return {{0,0.5},{1,0.25+0.125*tag+0.0625*(t%2)+0.03125*d}};
}
static auto run(const std::vector<Route>& r,int h,budget_release::Counters& c,
                std::size_t cap=4096){
    std::vector<Flow> flows;
    for(std::size_t i=0;i<r.size();++i)flows.push_back(f(i/h,i%h,r[i]));
    return budget_release::find_release(r,flows,h,usage(r,h),
        [](int d,int t,const Route& p,Flow& out){out=f(d,t,p);return true;},
        distance,[]{return false;},c,cap);
}
static bool oracle_exists(const std::vector<Route>& r,int h){
    auto before=usage(r,h);
    for(std::size_t d=0;d<r.size()/h;++d) for(int l=0;l<h;){
        int end=l;while(end+1<h && r[d*h+end+1]==r[d*h+l])++end;
        for(std::size_t k=0;k<r[d*h+l].size();++k){
            auto next=r; Route p=r[d*h+l];p.erase(p.begin()+k);
            bool same=true;
            for(int t=l;t<=end;++t){same&=f(d,t,p)==f(d,t,r[d*h+t]);next[d*h+t]=p;}
            auto after=usage(next,h);bool strict=false,worse=false;
            for(int t=1;t<h;++t){strict|=after[t]<before[t];worse|=after[t]>before[t];}
            if(same&&strict&&!worse)return true;
        } l=end+1;
    }return false;
}
int main(){
    int specific=0;
    {
        std::vector<Route> r{{},{1},{}}; auto before=r;
        budget_release::Counters c;auto p=run(r,3,c);
        assert(p && p->left==1 && p->right==1 && p->next.empty());
        assert((p->used_after==std::vector<int>{0,0,0}));assert(r==before);++specific;
    }
    {
        budget_release::Counters c;auto p=run({{1},{1},{1}},3,c);
        assert(!p);++specific; // no strict transition savings
    }
    {
        budget_release::Counters c;assert(!run({{},{3},{}},3,c));
        assert(c.flow_rejected==1);++specific;
    }
    {
        budget_release::Counters c;auto p=run({{1,2},{1,2},{2}},3,c);
        assert(p && p->left==0 && p->right==1 && p->next==Route{2});++specific;
    }
    {
        budget_release::Counters c;assert(!run({{1}},1,c));++specific;
        budget_release::Counters c2;assert(!run({},1,c2));++specific;
        budget_release::Counters c3;assert(!run({{},{1},{}},3,c3,0));
        assert(c3.stopped && c3.proposals==0);++specific;
    }
    {
        std::vector<Route> r{{},{1},{}};std::vector<Flow> fs(3,{{0,1}});
        bool late=false; budget_release::Counters c;
        auto p=budget_release::find_release(r,fs,3,usage(r,3),
            [&](int,int,const Route&,Flow& out){out={{0,1}};late=true;return true;},
            distance,[&]{return late;},c);
        assert(!p&&c.stopped);++specific;
        budget_release::Counters c2;
        assert(!budget_release::find_release(r,fs,3,usage(r,3),
            [](int,int,const Route&,Flow&){return false;},distance,[]{return false;},c2));++specific;
        budget_release::Counters c3;
        assert(!budget_release::find_release(r,fs,3,usage(r,3),
            [](int,int,const Route&,Flow& out){out={{0,1.0+1e-14}};return true;},distance,[]{return false;},c3));++specific;
    }
    {
        bool threw=false;budget_release::Counters c;
        try {std::vector<Route> r;std::vector<Flow> fs;
            budget_release::find_release(r,fs,0,{},[](int,int,const Route&,Flow&){return true;},distance,[]{return false;},c);
        }catch(const std::invalid_argument&){threw=true;} assert(threw);++specific;
    }
    std::mt19937 rng(20260908);std::vector<Route> menu{{},{1},{2},{3},{1,2},{1,3},{2,1},{2,3},{3,1},{3,2}};
    int found=0,accepted=0;
    for(int sample=0;sample<5000;++sample){
        int h=1+rng()%7,nd=1+rng()%3;std::vector<Route> r(h*nd);
        for(auto& p:r)p=menu[rng()%menu.size()];
        const auto original=r;
        budget_release::Counters c;auto p=run(r,h,c);
        assert(bool(p)==oracle_exists(r,h));assert(r==original);
        if(p){++found;auto before=usage(r,h);auto beforeflows=std::vector<Flow>{};
            for(int t=p->left;t<=p->right;++t){
                assert(f(p->demand,t,r[p->demand*h+t])==f(p->demand,t,p->next));
                r[p->demand*h+t]=p->next;
            }
            assert(usage(r,h)==p->used_after);bool strict=false;
            for(int t=1;t<h;++t){assert(p->used_after[t]<=before[t]);strict|=p->used_after[t]<before[t];}
            assert(strict);++accepted;
        }
    }
    std::cout<<"{\"specific_cases\":"<<specific<<",\"exhaustive_proposal_models\":5000,\"accepted_invariant_checks\":"<<accepted<<",\"matches\":5000}\n";
}

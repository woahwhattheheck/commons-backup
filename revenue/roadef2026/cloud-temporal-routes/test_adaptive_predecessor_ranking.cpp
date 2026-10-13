// SPDX-License-Identifier: MIT
#include "temporal_dp.hpp"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <iostream>
#include <random>
#include <vector>
#ifdef NDEBUG
#error "Compile without NDEBUG"
#endif
using namespace dock_temporal;

struct Ref {
    bool feasible=false;
    std::vector<int> choices;
    Objective objective;
    std::size_t transitions=0;
};

template<class Distance>
Ref direct(const std::vector<std::vector<Option>>& layers,
           const std::vector<int>& budgets, Distance distance) {
    const std::size_t h=layers.size();
    std::vector<Objective> previous(layers[0].size());
    std::vector<bool> previous_ok(layers[0].size(),false);
    std::vector<std::vector<int>> parent(h);
    parent[0].assign(layers[0].size(),-1);
    for(std::size_t k=0;k<layers[0].size();++k) if(layers[0][k].reachable){
        previous[k]=layers[0][k].cost; previous_ok[k]=true;
    }
    Ref out;
    for(std::size_t t=1;t<h;++t){
        std::vector<Objective> current(layers[t].size());
        std::vector<bool> current_ok(layers[t].size(),false);
        parent[t].assign(layers[t].size(),-1);
        for(std::size_t k=0;k<layers[t].size();++k){
            if(!layers[t][k].reachable)continue;
            int best=-1;
            for(std::size_t j=0;j<previous.size();++j){
                if(!previous_ok[j])continue;
                ++out.transitions;
                const int used=distance(t,j,k);
                if(used<0)throw std::invalid_argument("negative transition cost");
                if(used>budgets[t])continue;
                if(best<0||previous[j]<previous[static_cast<std::size_t>(best)])best=static_cast<int>(j);
            }
            if(best<0)continue;
            const auto& a=previous[static_cast<std::size_t>(best)];
            const auto& b=layers[t][k].cost;
            current[k].reserve(a.size()+b.size());
            std::merge(a.begin(),a.end(),b.begin(),b.end(),std::back_inserter(current[k]),std::greater<long long>());
            current_ok[k]=true; parent[t][k]=best;
        }
        previous.swap(current); previous_ok.swap(current_ok);
    }
    int best=-1;
    for(std::size_t k=0;k<previous.size();++k)
        if(previous_ok[k]&&(best<0||previous[k]<previous[static_cast<std::size_t>(best)]))best=static_cast<int>(k);
    if(best<0)return out;
    out.feasible=true; out.objective=previous[static_cast<std::size_t>(best)]; out.choices.resize(h);
    for(std::size_t t=h;t-->0;){out.choices[t]=best;best=parent[t][static_cast<std::size_t>(best)];}
    return out;
}

std::vector<std::vector<Option>> layers(int h,int k,int width) {
    std::vector<std::vector<Option>> x(h,std::vector<Option>(k));
    for(int t=0;t<h;++t)for(int r=0;r<k;++r){
        x[t][r].reachable=true;
        for(int e=0;e<width;++e)x[t][r].cost.push_back(1000000-t*100-r*3-e);
    }
    return x;
}

int main(){
    const int H=6,K=12,W=64;
    auto dense_layers=layers(H,K,W);
    std::vector<int> budget(H,0);
    auto dense=[](std::size_t,std::size_t,std::size_t){return 0;};
    auto dense_ref=direct(dense_layers,budget,dense);
    auto dense_got=solve(dense_layers,budget,dense,[]{return false;});
    assert(dense_got.complete&&dense_got.feasible);
    assert(dense_got.choices==dense_ref.choices&&dense_got.objective==dense_ref.objective);
    assert(dense_got.transitions_examined<dense_ref.transitions);

    auto diagonal=[](std::size_t,std::size_t a,std::size_t b){return a==b?0:1;};
    auto sparse_ref=direct(dense_layers,budget,diagonal);
    auto sparse_got=solve(dense_layers,budget,diagonal,[]{return false;});
    assert(sparse_got.complete&&sparse_got.feasible);
    assert(sparse_got.choices==sparse_ref.choices&&sparse_got.objective==sparse_ref.objective);
    // Two consecutive high-pressure ranked layers are required before the
    // remaining three sparse layers switch to direct scanning.
    assert(sparse_got.transitions_examined==588);
    assert(sparse_got.transitions_examined<sparse_ref.transitions);

    auto one_destination=layers(2,K,W);
    one_destination[1].resize(1);
    auto only_last=[](std::size_t,std::size_t a,std::size_t){return a==11?0:1;};
    auto single_ref=direct(one_destination,{0,0},only_last);
    auto single_got=solve(one_destination,{0,0},only_last,[]{return false;});
    assert(single_got.choices==single_ref.choices&&single_got.objective==single_ref.objective);
    assert(single_got.transitions_examined==single_ref.transitions&&single_ref.transitions==12);

    // Stable ties remain lowest-index in both adaptive paths.
    auto ties=layers(3,8,4);
    for(auto& layer:ties)for(auto& option:layer)option.cost={8,4,2,1};
    auto tied=solve(ties,{0,0,0},diagonal,[]{return false;});
    assert(tied.complete&&tied.feasible&&tied.choices==std::vector<int>({0,0,0}));

    // Negative costs are still rejected on the sampled direct path.
    bool negative=false;
    try { (void)solve(dense_layers,budget,[](std::size_t,std::size_t,std::size_t){return -1;},[]{return false;}); }
    catch(const std::invalid_argument&){negative=true;}
    assert(negative);

    // Cooperative cancellation during a direct sparse scan returns no partial route.
    std::size_t calls=0;
    auto cancelled=solve(dense_layers,budget,[&](std::size_t,std::size_t a,std::size_t b){++calls;return a==b?0:1;},[&]{return calls>=17;});
    assert(!cancelled.complete&&!cancelled.feasible&&cancelled.choices.empty());

    // Broad exact parity including jagged current menus and atypical first probes.
    std::mt19937 rng(2026090817);
    std::size_t models=0,direct_models=0,ranked_models=0;
    for(int trial=0;trial<40000;++trial){
        int h=1+rng()%7, k0=1+rng()%10, width=rng()%8;
        std::vector<std::vector<Option>> x; x.reserve(h);
        std::vector<int> budgets(h);
        std::vector<std::vector<std::vector<int>>> costs(h);
        for(int t=0;t<h;++t){
            int kt=1+rng()%10;
            if(t==0)kt=k0;
            x.emplace_back(kt);
            budgets[t]=rng()%8;
            if(t){
                costs[t].assign(x[t-1].size(),std::vector<int>(kt));
                for(auto& row:costs[t])for(auto& value:row)value=rng()%10;
            }
            for(int k=0;k<kt;++k){
                x[t][k].reachable=(rng()%6)!=0;
                for(int e=0;e<width;++e)x[t][k].cost.push_back(rng()%1000);
                std::sort(x[t][k].cost.begin(),x[t][k].cost.end(),std::greater<long long>());
            }
        }
        auto cost=[&](std::size_t t,std::size_t a,std::size_t b){return costs[t][a][b];};
        auto ref=direct(x,budgets,cost);
        auto got=solve(x,budgets,cost,[]{return false;});
        assert(got.complete&&got.feasible==ref.feasible);
        if(ref.feasible){assert(got.choices==ref.choices);assert(got.objective==ref.objective);}
        assert(got.transitions_examined<=ref.transitions);
        if(got.transitions_examined==ref.transitions)++direct_models;else ++ranked_models;
        ++models;
    }
    assert(direct_models>0&&ranked_models>0);
    std::cout<<"{\"status\":\"PASS\",\"models\":"<<models
             <<",\"direct_or_equal_models\":"<<direct_models
             <<",\"ranked_models\":"<<ranked_models
             <<",\"dense_transitions\":"<<dense_got.transitions_examined
             <<",\"dense_v1\":"<<dense_ref.transitions
             <<",\"sparse_transitions\":"<<sparse_got.transitions_examined
             <<"}\n";
}

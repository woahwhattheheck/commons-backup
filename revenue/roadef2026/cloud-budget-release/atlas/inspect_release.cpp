// SPDX-License-Identifier: MIT
// Test-only translation unit. The runner exposes Solver fields and renames main
// in an exact temporary source copy; no production method bodies are changed.
#include "budget_release.hpp"
#include "fleet_exposed.cpp"
#include <cstring>

static void check(bool condition,const char* message) {
    if (!condition) throw std::runtime_error(message);
}
static std::vector<int> recompute_budget(Solver& s) {
    std::vector<int> used(s.h,0);
    for(int t=1;t<s.h;++t) for(int d=0;d<static_cast<int>(s.demands.size());++d)
        used[t]+=s.distance(d,s.routes[d*s.h+t-1],s.routes[d*s.h+t]);
    return used;
}
static void invariant(Solver& s,const std::vector<double>& original,
                      const std::vector<Sparse>& original_flows) {
    check(s.used==recompute_budget(s),"transition totals differ from recomputed full schedule");
    check(s.routed==original_flows,"cached exact flow mutated");
    check(s.loads==original,"cached loads mutated");
    std::vector<double> rebuilt(s.loads.size(),0);
    for(int d=0;d<static_cast<int>(s.demands.size());++d) for(int t=0;t<s.h;++t) {
        Sparse now;check(s.routeFlow(d,t,s.routes[d*s.h+t],now),"unreachable returned route");
        check(now==original_flows[d*s.h+t],"returned route changes exact ECMP flow");
        for(auto [e,ratio]:now) rebuilt[t*s.m+e]+=s.demands[d].volume[t]*ratio;
    }
    check(rebuilt.size()==original.size() && std::memcmp(rebuilt.data(),original.data(),
          original.size()*sizeof(double))==0,"recomputed complete load bytes differ");
}
int main(int argc,char** argv) {
    try {
        if(argc!=8) throw std::runtime_error("net tm scenario incumbent output mode limit");
        setenv("CLOUD_INITIAL_SOLUTION",argv[4],1);
        Solver solver(argv[1],argv[2],argv[3],argv[5]);
        const std::string mode=argv[6]; const auto limit=std::stoul(argv[7]);
        const auto start_routes=solver.routes;const auto start_used=solver.used;
        const auto start_flows=solver.routed;const auto start_loads=solver.loads;
        bool deadline=mode=="pre_stop",exception_seen=false;
        int callbacks=0,committed=0;std::int64_t released=0;
        budget_release::Counters counts;
        while(true) {
            const auto before_routes=solver.routes;const auto before_used=solver.used;
            std::optional<budget_release::Proposal<Route>> proposal;
            try {
                proposal=budget_release::find_release(solver.routes,solver.routed,solver.h,solver.used,
                  [&](int d,int t,const Route& next,Sparse& result) {
                    ++callbacks;const bool good=solver.routeFlow(d,t,next,result);
                    if(mode=="post_callback_stop") deadline=true;
                    if(mode=="callback_exception") throw std::runtime_error("callback-marker");
                    if(mode=="unreachable") return false;
                    if(mode=="near_flow" && !result.empty()) result.front().second+=1e-13;
                    return good;
                  },
                  [&](int d,const Route& a,const Route& b){return solver.distance(d,a,b);},
                  [&]{return deadline;},counts,limit);
            } catch(const std::runtime_error& e) {
                if(mode!="callback_exception" || std::string(e.what())!="callback-marker") throw;
                exception_seen=true;
            }
            check(before_routes==solver.routes && before_used==solver.used && solver.routed==start_flows
                  && solver.loads==start_loads,"proposal callback mutated supplied state");
            if(!proposal)break;
            check(!deadline,"proposal returned after callback deadline");
            check(proposal->left>=0 && proposal->right<solver.h,"proposal interval bounds");
            bool strict=false;
            for(int t=0;t<solver.h;++t) {
                check(proposal->used_after[t]<=solver.used[t],"a transition cost increased");
                strict|=proposal->used_after[t]<solver.used[t];
                released+=solver.used[t]-proposal->used_after[t];
            }
            check(strict,"budget did not strictly improve");
            for(int t=proposal->left;t<=proposal->right;++t)
                solver.routes[proposal->demand*solver.h+t]=proposal->next;
            solver.used=proposal->used_after;
            invariant(solver,start_loads,start_flows);
            if(++committed>1000) throw std::runtime_error("neutral descent did not terminate");
        }
        invariant(solver,start_loads,start_flows);
        if(mode!="normal")check(start_routes==solver.routes && start_used==solver.used,"control changed state");
        if(mode=="callback_exception")check(exception_seen,"callback exception not reached");
        if(mode=="post_callback_stop")check(callbacks==1 && counts.stopped,"late stop not observed");
        solver.writeSolution();solver.statistics();
        std::cout<<"{\"successful\":true,\"committed\":"<<committed<<",\"released\":"<<released
                 <<",\"flow_callbacks\":"<<callbacks<<",\"proposals\":"<<counts.proposals
                 <<",\"stopped\":"<<(counts.stopped?"true":"false")
                 <<",\"exception_seen\":"<<(exception_seen?"true":"false")<<"}\n";
    } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}

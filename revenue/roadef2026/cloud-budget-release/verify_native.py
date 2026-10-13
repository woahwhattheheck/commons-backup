#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native exact-fleet regression; generated instances are NOT public benchmarks.

Consumes existing fleet source and RapidJSON. Builds original, derived, and a
read-access-only test view; no solver method is replaced in the test view.
All subprocess commands, inputs, outputs and identities are retained.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from build_candidate import derive, git_blob, SOURCE_BLOB

HARNESS = r'''
#include "probe_source.cpp"
#include <cstring>
static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
static int independent_distance(int source, int target, const Route& a, const Route& b) {
    auto segments = [&](const Route& path) {
        std::vector<std::pair<int,int>> out;
        int previous = source;
        for (int next : path) { out.emplace_back(previous,next); previous=next; }
        out.emplace_back(previous,target);
        std::sort(out.begin(),out.end());
        out.erase(std::unique(out.begin(),out.end()),out.end());
        return out;
    };
    auto x=segments(a), y=segments(b);
    std::vector<std::pair<int,int>> difference;
    std::set_symmetric_difference(x.begin(),x.end(),y.begin(),y.end(),
                                 std::back_inserter(difference));
    return int(difference.size());
}
int main(int argc,char**argv) {
    if(argc!=6) return 2;
    try {
        Solver solver(argv[1],argv[2],argv[3],argv[4]);
        auto initialLoads=solver.loads;
        auto initialFlows=solver.routed;
        auto initialRoutes=solver.routes;
        auto initialUsed=solver.used;
        const std::string mode=argv[5];
        if(mode=="interrupted") interrupted=1;
        if(mode=="expired") solver.seconds=0;
        std::size_t checked=0;
        int accepted=0;
        for(;;) {
            auto previous=solver.used;
            std::size_t previousWaypoints=0;
            for(const auto& r:solver.routes) previousWaypoints+=r.size();
            if(!solver.releaseBudget()) break;
            require(++accepted<10000,"neutral pass failed to terminate");
            require(solver.loads.size()==initialLoads.size() &&
                std::memcmp(solver.loads.data(),initialLoads.data(),initialLoads.size()*sizeof(double))==0,
                "stored loads changed");
            require(solver.routed==initialFlows,"cached routed flows changed");
            bool strict=false;
            for(int t=1;t<solver.h;++t) {
                int total=0;
                for(int d=0;d<int(solver.demands.size());++d)
                    total+=independent_distance(solver.demands[d].from,solver.demands[d].to,
                        solver.routes[d*solver.h+t-1],solver.routes[d*solver.h+t]);
                require(total==solver.used[t],"independent full transition accounting differs");
                require(total<=previous[t] && total<=solver.budget[t],"transition use increased");
                strict|=total<previous[t];
            }
            require(strict,"neutral pass did not release any budget");
            std::size_t waypoints=0;
            for(const auto& r:solver.routes) waypoints+=r.size();
            require(waypoints<previousWaypoints,"waypoint measure did not decrease");
            for(int d=0;d<int(solver.demands.size());++d) for(int t=0;t<solver.h;++t) {
                Sparse flow;
                require(solver.routeFlow(d,t,solver.routes[d*solver.h+t],flow),"new route unreachable");
                require(flow==initialFlows[d*solver.h+t],"exact native ECMP differs");
                ++checked;
            }
        }
        if(mode!="normal") require(solver.routes==initialRoutes && solver.used==initialUsed,
                                   "stopped/disabled consumer changed routes");
        solver.writeSolution();
        std::cout << "{\"accepted\":" << accepted << ",\"checked_native_flows\":" << checked
                  << ",\"initial_cost\":" << std::accumulate(initialUsed.begin(),initialUsed.end(),0)
                  << ",\"final_cost\":" << std::accumulate(solver.used.begin(),solver.used.end(),0)
                  << ",\"proposals\":" << solver.budgetReleaseProposals
                  << ",\"flow_callbacks\":" << solver.budgetReleaseFlowChecks << "}\n";
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
    return 0;
}
'''

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n",encoding="utf-8")

def segment_set(demand, route):
    chain=[demand['s'],*route,demand['t']]
    return set(zip(chain,chain[1:]))

def instance(n, edges, routes, volumes, *, interventions=(), budgets=None):
    h=len(routes[0]); demands=[dict(s=0,t=n-1,v=list(v)) for v in volumes]
    network={'nodes':[{'id':i} for i in range(n)],'links':[
        dict(id=i,**{'from':a,'to':b,'metric':w,'capacity':c})
        for i,(a,b,w,c) in enumerate(edges)]}
    costs=[0]+[sum(len(segment_set(d,rs[t-1])^segment_set(d,rs[t]))
                    for d,rs in zip(demands,routes)) for t in range(1,h)]
    scenario={'max_segments':8,'interventions':list(interventions),
              'budget':[{'t':t,'value':costs[t] if budgets is None else budgets[t]}
                        for t in range(1,h)]}
    initial={'srpaths':[{'d':d,'t':t,'w':r} for d,rs in enumerate(routes)
                        for t,r in enumerate(rs) if r]}
    return network,{'num_time_slots':h,'demands':demands},scenario,initial

def barrier():
    values=instance(6,[(0,1,1,100),(1,2,1,100),(3,5,1,1),(3,4,1,2),(4,5,1,2)],
                    [[[],[1],[]],[[],[],[]]],[[1,1,1],[5,10,5]],
                    interventions=[{'t':t,'links':[3]} for t in (0,2)])
    net,tm,sc,initial=values
    tm['demands'][0].update(s=0,t=2);tm['demands'][1].update(s=3,t=5)
    sc['budget']=[{'t':1,'value':3},{'t':2,'value':3}]
    return values

def run(source, vendor, output, cxx):
    output.mkdir(parents=True,exist_ok=False)
    raw=source.read_bytes();generated=derive(raw)
    header=Path(__file__).with_name('budget_release.hpp')
    (output/'baseline.cpp').write_bytes(raw)
    (output/'candidate.cpp').write_bytes(generated)
    (output/'budget_release.hpp').write_bytes(header.read_bytes())
    # Expose fields only in this probe; no method, predicate or kernel is rewritten.
    view=generated.decode().replace('class Solver {','class Solver {\npublic:',1)
    view=view.replace('int main(int argc, char** argv)', 'int source_main(int argc, char** argv)',1)
    (output/'probe_source.cpp').write_text(view)
    (output/'probe.cpp').write_text(HARNESS)
    commands=[]
    def execute(cmd,label,env=None,timeout=30):
        started=time.monotonic()
        result=subprocess.run([str(x) for x in cmd],env=env,capture_output=True,timeout=timeout)
        (output/(label+'.stdout')).write_bytes(result.stdout)
        (output/(label+'.stderr')).write_bytes(result.stderr)
        commands.append({'label':label,'argv':[str(x) for x in cmd],'returncode':result.returncode,
                         'wall_seconds':time.monotonic()-started})
        if result.returncode: raise RuntimeError(f"{label} failed: {result.stderr.decode(errors='replace')}")
        return result
    version=execute([cxx,'--version'],'compiler-version').stdout.decode().splitlines()[0]
    for name in ('baseline','candidate','probe'):
        execute([cxx,'-std=c++20','-O2','-DNDEBUG','-I',vendor,output/(name+'.cpp'),'-o',output/name],
                'build-'+name,timeout=45)
    env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','CLOUD_'))}
    env.update(SEDGE_SECONDS='30',SEDGE_MAX_ROUNDS='0')
    def prepare(label,values):
        p=output/label;p.mkdir()
        for name,value in zip(('network','traffic','scenario','initial'),values):write(p/(name+'.json'),value)
        return p
    cases=[('unique-chain-middle',instance(3,[(0,1,1,10),(1,2,1,10)],[[[],[1],[]]],[[1,1,1]]),1),
           ('full-run-no-budget-release',instance(3,[(0,1,1,10),(1,2,1,10)],[[[1],[1],[1]]],[[1,1,1]]),0),
           ('ecmp-split-not-equivalent',instance(4,[(0,1,1,10),(1,3,1,10),(0,2,1,10),(2,3,1,10)],
                                                [[[],[1],[]]],[[2,2,2]]),0),
           ('every-maintenance-layer',instance(4,[(0,1,1,10),(1,3,1,10),(0,2,1,10),(2,3,1,10)],
                        [[[],[1],[1],[]]],[[2,2,2,2]],interventions=[{'t':1,'links':[2]}]),0),
           ('zero-traffic-still-exact-flow',instance(4,[(0,1,1,10),(1,3,1,10),(0,2,1,10),(2,3,1,10)],
                                                   [[[],[1],[]]],[[0,0,0]]),0)]
    rng=random.Random(260908)
    for k in range(30):
        n=rng.randrange(4,10);h=rng.randrange(3,8);ds=rng.randrange(1,4)
        edges=[(i,i+1,1,rng.randrange(3,20)) for i in range(n-1)]+[(n-1,0,n+1,10)]
        routes=[[sorted(rng.sample(range(1,n-1),rng.randrange(min(4,n-2)+1))) for _ in range(h)] for _ in range(ds)]
        cases.append((f'generated-chain-{k:02d}',instance(n,edges,routes,[[rng.randrange(1,20) for _ in range(h)] for _ in range(ds)]),None))
    checks=[]
    for label,values,expected in cases:
        p=prepare(label,values)
        local={**env,'CLOUD_INITIAL_SOLUTION':str(p/'initial.json')}
        result=execute([output/'probe',*[p/(x+'.json') for x in ('network','traffic','scenario')],p/'out.json','normal'],label,env=local)
        item=json.loads(result.stdout)
        if expected is not None and item['accepted']!=expected:raise AssertionError((label,item,expected))
        checks.append({'case':label,**item})
    p=output/'unique-chain-middle'
    for mode in ('interrupted','expired','disabled','proposal-cap'):
        local={**env,'CLOUD_INITIAL_SOLUTION':str(p/'initial.json')}
        if mode=='disabled':local['FLEET_BUDGET_RELEASE']='0'
        if mode=='proposal-cap':local['FLEET_BUDGET_RELEASE_LIMIT']='0'
        result=execute([output/'probe',*[p/(x+'.json') for x in ('network','traffic','scenario')],p/(mode+'.json'),mode],mode,env=local)
        item=json.loads(result.stdout)
        if item['accepted']!=0:raise AssertionError(mode)
        checks.append({'case':mode,**item})
    p=prepare('barrier',barrier());records={}
    for label,binary,enabled,rounds in [('baseline','baseline',0,64),('disabled','candidate',0,64),('neutral-only','candidate',1,0),('enabled','candidate',1,64)]:
        local={**env,'CLOUD_INITIAL_SOLUTION':str(p/'initial.json'),'SEDGE_MAX_ROUNDS':str(rounds),
               'SEDGE_STATS':str(p/(label+'-stats.json')),'FLEET_BUDGET_RELEASE':str(enabled)}
        execute([output/binary,*[p/(x+'.json') for x in ('network','traffic','scenario')],p/(label+'.json')], 'barrier-'+label,env=local)
        records[label]={'solution':json.loads((p/(label+'.json')).read_text()),
                        'stats':json.loads((p/(label+'-stats.json')).read_text())}
    old=records['baseline']['stats'];disabled=records['disabled']['stats']
    if any(disabled[k]!=v for k,v in old.items() if k!='seconds'):raise AssertionError('disabled stats differ')
    if records['baseline']['solution']!=records['disabled']['solution']:raise AssertionError('disabled solution differs')
    neutral=records['neutral-only']['stats'];enabled=records['enabled']['stats']
    if neutral['loads']!=old['loads'] or neutral['budget_used']!=[0,0,0] or neutral['accepted']!=0:raise AssertionError('neutral result')
    if (old['final_mlu'],enabled['final_mlu'],enabled['budget_used'])!=(10,5,[0,3,3]):raise AssertionError('barrier improvement')
    # Identical acceptance body is a build-time compatibility check, not a claim of identical search.
    section=lambda s:s[s.index('    bool moveTogether('):s.index('\n    bool move(',s.index('    bool moveTogether('))]
    if section(raw.decode())!=section(generated.decode()):raise AssertionError('strict acceptance changed')
    report={'schema':'date.budget-release-native.v1','compiler':version,
        'source_blob':git_blob(raw),'source_sha256':hashlib.sha256(raw).hexdigest(),
        'generated_sha256':hashlib.sha256(generated).hexdigest(),'header_sha256':digest(header),
        'binary_sha256':{k:digest(output/k) for k in ('baseline','candidate','probe')},
        'native_cases':checks,'native_case_count':len(checks),
        'accepted_neutral_moves':sum(x['accepted'] for x in checks),
        'rechecked_native_flows':sum(x['checked_native_flows'] for x in checks),
        'barrier':records,'strict_acceptance_unchanged':True,'commands':commands,
        'limits':['Generated native instances, not public-B benchmark or official-checker evidence.',
                  'Exact ECMP equality is conservative; equivalent floating sums with different rounding can be rejected.',
                  'No universal quality or runtime improvement is established by this discriminator.']}
    write(output/'RESULTS.json',report)
    print(json.dumps({k:report[k] for k in ('native_case_count','accepted_neutral_moves','rechecked_native_flows','generated_sha256')},indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','vendor','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cxx',default='g++');a=p.parse_args()
    run(a.source.resolve(),a.vendor.resolve(),a.output.resolve(),a.cxx)

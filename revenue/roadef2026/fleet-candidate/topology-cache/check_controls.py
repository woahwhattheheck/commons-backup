#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Negative cache-identity controls, eviction replay, and fixed-round native timing.

Run after check_topology_cache.py. No network or official benchmark is used.
"""
from __future__ import annotations
import argparse,hashlib,json,statistics,subprocess
from pathlib import Path
import check_topology_cache as check


def compile_probe(text,probe,vendor,root):
    root.mkdir(parents=True,exist_ok=True)
    text=text.replace('class Solver {','class Solver {\npublic:',1).replace('int main(int argc, char** argv)','int solver_cli(int argc, char** argv)',1)
    cpp=root/'probe-source.cpp';cpp.write_text(text+'\n'+probe)
    result=subprocess.run(['g++','-std=c++20','-O3','-DNDEBUG','-I',str(vendor),str(cpp),'-o',str(root/'probe')],text=True,capture_output=True)
    (root/'build.log').write_text(result.stdout+result.stderr);result.check_returncode()
    return root/'probe'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,default=Path(__file__).resolve().parents[1]/'main.cpp')
    parser.add_argument('--vendor',type=Path,required=True)
    parser.add_argument('--checks',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    candidate=args.candidate.read_text();reference=args.reference.read_text()
    probe=Path(__file__).with_name('probe.cpp').read_text()
    paths=[args.checks/'case-2'/(part+'.json') for part in ('net','tm','scenario')]
    original,_=check.invoke(args.checks/'reference/probe',paths,out/'reference.json',0,'dump')
    good,_=check.invoke(args.checks/'candidate/probe',paths,out/'candidate.json',0,'dump')
    body,summary=good.rsplit('summary ',1);assert body==original.rsplit('summary ',1)[0]
    mutations={
      'count-not-mask':candidate.replace('offline[t] == offline[prior]', 'std::count(offline[t].begin(), offline[t].end(), true) == std::count(offline[prior].begin(), offline[prior].end(), true)'),
      'first-word-only':candidate.replace('offline[t] == offline[prior]', 'std::equal(offline[t].begin(), offline[t].begin() + std::min(m, 64), offline[prior].begin())'),
      'segment-time-not-topology':candidate.replace('(static_cast<std::uint64_t>(topologySlot[t]) * n + source)', '(static_cast<std::uint64_t>(t) * n + source)'),
    }
    negative=[]
    for name,source in mutations.items():
        assert source!=candidate
        binary=compile_probe(source,probe,args.vendor,out/name)
        text,_=check.invoke(binary,paths,out/name/'result.json',0,'dump')
        wrong_body,wrong_summary=text.rsplit('summary ',1)
        actual=list(map(int,wrong_summary.split())); expected=list(map(int,summary.split()))
        if name=='segment-time-not-topology':
            assert wrong_body==body and actual[3]>expected[3]
            detection='segment-cache count differs despite equal flows'
        else:
            assert wrong_body!=body and actual[5]>0
            detection='exact flow differs and distinct maintenance states alias'
        negative.append({'name':name,'detected':True,'detection':detection,'summary':actual,'source_sha256':hashlib.sha256(source.encode()).hexdigest()})
    # Force eviction independently of the production 300000-entry limit.
    evict=probe.replace('const auto& flow = solver.segment(t, a, b);','if ((t * solver.n * solver.n + a * solver.n + b) % 17 == 0) solver.cache.clear();\n                const auto& flow = solver.segment(t, a, b);')
    evictions=[]
    for tag,text in [('reference',reference),('candidate',candidate)]:
        binary=compile_probe(text,evict,args.vendor,out/('evict-'+tag))
        result,_=check.invoke(binary,paths,out/('evict-'+tag)/'result.json',0,'dump')
        result_body,result_summary=result.rsplit('summary ',1)
        assert result_body==body
        evictions.append({'arm':tag,'exact_queries':1728,'interval_queries':17,'matches_uninterrupted':True,'summary':list(map(int,result_summary.split()))})
    performance=[]
    for label,groups in [('repeated',3),('unique',24)]:
        paths,unique,_=check.fixture(out/('solver-'+label),987,40,24,groups)
        samples={'reference':[],'candidate':[]};final={}
        for i in range(7):
            order=('reference','candidate') if i%2==0 else ('candidate','reference')
            for tag in order:
                target=out/('solver-'+label)/(tag+f'-{i}.json')
                _,elapsed=check.invoke(args.checks/tag/'solver',paths,target,12)
                samples[tag].append(elapsed);final[tag]=(target.read_bytes(),check.stats(target))
            assert final['reference']==final['candidate']
        performance.append({'label':label,'nodes':40,'slots':24,'topologies':unique,'rounds':12,'samples_seconds':samples,'median_seconds':{k:statistics.median(v) for k,v in samples.items()},'solution_sha256':hashlib.sha256(final['candidate'][0]).hexdigest(),'equal_complete_state':True,'stats':final['candidate'][1]})
    report={'schema':'kestrel.topology-cache-controls.v1','reference_sha256':check.digest(args.reference),'candidate_sha256':check.digest(args.candidate),'negative_controls':negative,'eviction':evictions,'solver_performance':performance,'scope':'Generated complete compiled-solver runs; not official benchmark or qualification-score evidence'}
    (out/'RESULTS.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({**report,'solver_performance':[{k:v for k,v in x.items() if k!='stats'} for x in performance]},indent=2))

if __name__=='__main__':main()

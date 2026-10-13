#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check saved generated solutions with the unchanged official ROADEF checker.

The native stress fixtures omit schema-only 'directed' metadata and emit empty
intervention rows (including at zero). A separate checker copy supplies directed
metadata, removes empty no-op rows and consistently relabels graph identifiers
to contiguous indices. This is a separate isomorphic checker input, not the raw
noncontiguous-label native fixture. Original stress inputs/results stay untouched.
The disconnected sentinel fixture remains a native test, not an official case.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checker',type=Path,required=True)
    p.add_argument('--checks',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[]
    for seed in [1,2,3,5,*range(6,12)]:
        source=a.checks/f'case-{seed}';target=a.output/f'case-{seed}';target.mkdir(exist_ok=True)
        network=json.loads((source/'net.json').read_text());network['directed']=True
        node_map={node['id']:i for i,node in enumerate(network['nodes'])}
        edge_map={edge['id']:i for i,edge in enumerate(network['links'])}
        for node in network['nodes']:node['id']=node_map[node['id']]
        for edge in network['links']:
            edge['id']=edge_map[edge['id']];edge['from']=node_map[edge['from']];edge['to']=node_map[edge['to']]
        traffic=json.loads((source/'tm.json').read_text())
        for demand in traffic['demands']:
            demand['s']=node_map[demand['s']];demand['t']=node_map[demand['t']]
        scenario=json.loads((source/'scenario.json').read_text())
        scenario['interventions']=[{'t':row['t'],'links':[edge_map[e] for e in row['links']]} for row in scenario['interventions'] if row['links']]
        net=target/'net.json';scn=target/'scenario.json';tm=target/'tm.json'
        tm.write_text(json.dumps(traffic,sort_keys=True)+'\n')
        net.write_text(json.dumps(network,sort_keys=True)+'\n');scn.write_text(json.dumps(scenario,sort_keys=True)+'\n')
        reference=source/'reference-r8.json';candidate=source/'candidate-r8.json'
        assert reference.read_bytes()==candidate.read_bytes()
        reports=[]
        for tag,solution in [('reference',reference),('candidate',candidate)]:
            converted=json.loads(solution.read_text())
            for row in converted['srpaths']:row['w']=[node_map[w] for w in row['w']]
            converted_path=target/(tag+'-solution.json');converted_path.write_text(json.dumps(converted,sort_keys=True)+'\n')
            cmd=[str(a.checker.resolve()),'--net',str(net.resolve()),'--tm',str(tm.resolve()),'--scenario',str(scn.resolve()),'--srpaths',str(converted_path.resolve()),'--max-decimal-places','6']
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
            (target/(tag+'.json')).write_text(result.stdout);(target/(tag+'.stderr')).write_text(result.stderr)
            result.check_returncode();report=json.loads(result.stdout);assert report['valid'] is True
            reports.append(report)
        assert reports[0]==reports[1]
        rows.append({'seed':seed,'valid':True,'official_report_equal':True,'solution_sha256':digest(candidate),'checker_report_sha256':digest(target/'candidate.json'),'checker_network_sha256':digest(net),'checker_scenario_sha256':digest(scn),'original_network_sha256':digest(source/'net.json'),'original_scenario_sha256':digest(source/'scenario.json')})
    report={'schema':'kestrel.topology-cache-official.v1','checker_sha256':digest(a.checker),'checks':rows,'scope':'20 checker invocations on 10 generated graph pairs; no official public-B benchmark, submission or competitive-score claim','native_disconnected_seed':4}
    (a.output/'RESULTS.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

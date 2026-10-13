#!/usr/bin/env python3
"""Run fixed-work source variants on constructed, checker-validated networks.

No official benchmark instances, qualification artifacts or network access.
All raw input, solver/checker output and process results are retained.
"""
from pathlib import Path
import argparse, hashlib, itertools, json, os, subprocess, time


def fixture(k, slots, segments, budget, maintenance=False, noncontiguous=False, ties=False):
    n=2*k+3; a,b,c=2*k,2*k+1,2*k+2
    ids=[1000+17*i if noncontiguous else i for i in range(n)]
    links=[]
    def pair(u,v,metric,capacity):
        out=[]
        for x,y in [(u,v),(v,u)]:
            eid=5000+11*len(links) if noncontiguous else len(links)
            links.append({'id':eid,'from':ids[x],'to':ids[y], 'metric':metric,'capacity':capacity})
            out.append(eid)
        return out
    for i in range(k): pair(i,a,1,100)
    for j in range(k): pair(b,k+j,1,100)
    core=pair(a,b,1,10); pair(a,c,2,20); pair(c,b,2,20)
    net={'directed':True,'multigraph':False,'nodes':[{'id':i,'name':f'n{i}'} for i in ids],'links':links}
    tm={'num_time_slots':slots,'demands':[{'s':ids[i],'t':ids[k+j],
        'v':[1 if ties else (10+(3*i+5*j+7*t)%9)/10 for t in range(slots)]}
        for i in range(k) for j in range(k)]}
    scenario={'max_segments':segments,'budget':[{'t':t,'value':budget} for t in range(1,slots)],
              'interventions':[{'t':1,'links':core}] if maintenance else []}
    return net,tm,scenario


def run(command, env, directory, name):
    begin=time.perf_counter()
    result=subprocess.run([str(x) for x in command],env=env,cwd=directory,capture_output=True,timeout=90)
    seconds=time.perf_counter()-begin
    (directory/(name+'.stdout')).write_bytes(result.stdout)
    (directory/(name+'.stderr')).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(f'{name} exit{result.returncode}: {result.stderr.decode(errors="replace")[:300]}')
    return {'command':[str(x) for x in command],'exit':result.returncode,'seconds':seconds}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--checker',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    binaries={n:getattr(args,n).resolve() for n in ('original','candidate','checker')}
    report={'status':'FAIL','binary_sha256':{n:hashlib.sha256(path.read_bytes()).hexdigest() for n,path in binaries.items()},'pairs':[]}
    configs=[('small',4,1,2,0,False,False,False),('medium',8,3,2,16,False,False,False),
             ('large',12,2,4,32,False,False,False),('maintenance',8,3,3,4,True,False,False),
             ('ties',8,2,2,0,False,False,True),('noncontiguous',8,2,2,14,False,True,False)]
    try:
        for name,*parameters in configs:
            d=out/name;d.mkdir()
            for suffix,data in zip(('net','tm','scenario'),fixture(*parameters)):
                (d/(suffix+'.json')).write_text(json.dumps(data)+'\n')
            for directed,joint in itertools.product((0,1),repeat=2):
                config=d/f'd{directed}-j{joint}';config.mkdir()
                incumbent=None
                for mode in ('cold','resume'):
                    cell=config/mode;cell.mkdir();observed={};checks={};stats={};receipts={}
                    for variant in ('original','candidate'):
                        env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','CLOUD_INITIAL_'))}
                        env.update(SEDGE_SECONDS='600',SEDGE_MAX_ROUNDS='12',FLEET_DIRECTED=str(directed),FLEET_JOINT=str(joint),FLEET_WAYPOINT_LIMIT='0')
                        solution=cell/(variant+'.solution.json');stat=cell/(variant+'.stats.json');env['SEDGE_STATS']=str(stat)
                        if incumbent:env['CLOUD_INITIAL_SOLUTION']=str(incumbent)
                        command=[binaries[variant],d/'net.json',d/'tm.json',d/'scenario.json',solution]
                        receipts[variant]=run(command,env,cell,variant)
                        observed[variant]=solution.read_bytes();stats[variant]=json.loads(stat.read_text());stats[variant].pop('seconds')
                        checks[variant]={}
                        for places in (6,12):
                            ck=run([binaries['checker'],'--net',d/'net.json','--tm',d/'tm.json','--scenario',d/'scenario.json','--srpaths',solution,'--max-decimal-places',str(places)],env,cell,f'{variant}-checker{places}')
                            parsed=json.loads((cell/f'{variant}-checker{places}.stdout').read_text())
                            if parsed.get('valid') is not True:raise AssertionError(f'{name} invalid official result: {parsed}')
                            checks[variant][places]=parsed
                    assert observed['original']==observed['candidate'],str(cell)+' solution mismatch'
                    assert stats['original']==stats['candidate'],str(cell)+' search-state mismatch'
                    assert checks['original']==checks['candidate'],str(cell)+' checker result mismatch'
                    report['pairs'].append({'fixture':name,'directed':directed,'joint':joint,'mode':mode,
                        'identical_solution':True,'identical_stats_except_seconds':True,'identical_checker_reports':True,
                        'solution_sha256':hashlib.sha256(observed['original']).hexdigest(),
                        'original_seconds':receipts['original']['seconds'],'candidate_seconds':receipts['candidate']['seconds'],
                        'attempted':stats['original']['attempted'],'accepted':stats['original']['accepted'],
                        'joint_attempted':stats['original']['joint_attempted']})
                    (cell/'commands.json').write_text(json.dumps(receipts,indent=2)+'\n')
                    if mode=='cold':incumbent=cell/'original.solution.json'
            print(name,'8 original/candidate pairs validated',flush=True)
        report.update(status='PASS',pair_count=len(report['pairs']),solver_invocations=2*len(report['pairs']),checker_invocations=4*len(report['pairs']))
        print(json.dumps({k:v for k,v in report.items() if k!='pairs'}))
    finally:
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()

# SPDX-License-Identifier: Apache-2.0
"""Source-bound exact work-route search composition; never edits production in place."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

SOURCE_BLOB = 'edbc423023479dbe2e78131495334384a87b607f'
TRANSFORM_BEFORE_SHA256 = '6dd30b4a21df7ac818048937e6e446dcbe0b3251c036e2bb560af01cb745e776'
TRANSFORM_AFTER_SHA256 = 'c70e6a90fc01f14b8ee61f8056666c358862070aca45aeff0dac4966a6b5a6c9'
OLD = '''                choices=[]
                for order in permutations(range(len(groups))):
                    q=origin;trial=[]
                    for index in order:
                        pos,acts=groups[index];trial+=path(q,pos)+acts;q=pos
                    trial+=path(q,goal)
                    if len(trial)<=length:choices.append(trial)
                if choices:
                    trial=min(choices,key=lambda a:sum(x[0] in MOVES for x in a));trial+= [['PASS']]*(length-len(trial))
'''
NEW = '''                trial=_minimum_work_trial(origin,goal,groups,length)
                if trial is not None:
                    trial+= [['PASS']]*(length-len(trial))
'''
GUARD = "            if self.pathing and 1<=len(groups)<=6 and len({p for p,_ in groups})==len(groups):\n"
HELPER = '''def _minimum_work_trial(origin, goal, groups, length):
    """Exact native permutation winner, constructing only the winning action list.

    Every site keeps all its work actions in their original order. Native path
    length is Manhattan distance, and the work length is constant across orders.
    Therefore minimizing travel also minimizes total length. The tuple order is
    the original itertools.permutations tie-break, not a new planner policy.
    """
    n=len(groups)
    if not 1<=n<=6:
        raise ValueError('work-route search requires one through six sites')
    sites=[entry[0] for entry in groups]
    start=[distance(origin,p) for p in sites]
    finish=[distance(p,goal) for p in sites]
    edges=[[distance(a,b) for b in sites] for a in sites]
    if n<=3:
        # Tiny tours are cheaper to enumerate as scalar costs than DP states.
        cost,order=min((start[o[0]]+sum(edges[a][b] for a,b in zip(o,o[1:]))
                        +finish[o[-1]],o) for o in permutations(range(n)))
    else:
        # Held-Karp: at most 192 states for the native six-site bound. A state
        # retains the lexicographically earliest minimum-cost prefix. Future
        # costs depend only on visited sites and last site, so this tie is safe.
        states={(1<<i,i):(start[i],(i,)) for i in range(n)}
        full=(1<<n)-1
        for mask in range(1,full+1):
            for last in range(n):
                prior=states.get((mask,last))
                if prior is None:
                    continue
                for nxt in range(n):
                    if mask & (1<<nxt):
                        continue
                    key=(mask|(1<<nxt),nxt)
                    proposal=(prior[0]+edges[last][nxt],prior[1]+(nxt,))
                    incumbent=states.get(key)
                    if incumbent is None or proposal<incumbent:
                        states[key]=proposal
        cost,order=min((states[(full,i)][0]+finish[i],states[(full,i)][1])
                       for i in range(n))
    if cost+sum(len(acts) for _,acts in groups)>length:
        return None
    q=origin;trial=[]
    for index in order:
        pos,acts=groups[index]
        trial+=path(q,pos)+acts;q=pos
    trial+=path(q,goal)
    return trial

'''
# Whole primitive text is pinned, not only a name or advertised parent hash.
PINS = {
    'path': "def path(a,b):\n    return [[('EAST' if b[0]>a[0] else 'WEST')]]*abs(b[0]-a[0])+[[('SOUTH' if b[1]>a[1] else 'NORTH')]]*abs(b[1]-a[1])",
    'distance': 'def distance(a,b):return abs(a[0]-b[0])+abs(a[1]-b[1])',
    'MOVES': "MOVES={'NORTH':(0,-1),'SOUTH':(0,1),'EAST':(1,0),'WEST':(-1,0)}",
    'WORK': "WORK={'WATER','CARE','FEED','HARVEST','COLLECT_FERTILIZER'}",
}

def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def compose(source: str) -> str:
    """Preserve all bytes outside the authenticated search block/helper insertion.

    Reject primitive drift, mixed applications and ambiguous replacement sites.
    Other methods/peer changes are retained; transform-method drift requires review.
    """
    tree=ast.parse(source)
    for name, expected in PINS.items():
        nodes=[node for node in tree.body if
               isinstance(node,ast.FunctionDef) and node.name==name or
               isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)]
        if len(nodes)!=1 or ast.get_source_segment(source,nodes[0])!=expected:
            raise ValueError('native work-route dependency drift: '+name)
    imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='itertools']
    if len(imports)!=1 or ast.get_source_segment(source,imports[0])!='from itertools import permutations':
        raise ValueError('native permutations dependency drift')
    spatial=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SpatialTempo']
    if len(spatial)!=1:
        raise ValueError('ambiguous or missing SpatialTempo')
    transforms=[n for n in spatial[0].body if isinstance(n,ast.FunctionDef) and n.name=='transform']
    if len(transforms)!=1:
        raise ValueError('ambiguous or missing SpatialTempo.transform')
    method=ast.get_source_segment(source,transforms[0])
    method_hash=hashlib.sha256(method.encode('utf-8')).hexdigest()
    helpers=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_minimum_work_trial']
    if helpers:
        if method_hash==TRANSFORM_AFTER_SHA256 and len(helpers)==1 and source.count(HELPER)==1 and source.count(NEW)==1 and OLD not in source and GUARD+NEW in source and NEW in method:
            return source
        raise ValueError('partial or changed work-route composition')
    if method_hash!=TRANSFORM_BEFORE_SHA256 or source.count(OLD)!=1 or source.count(GUARD+OLD)!=1 or OLD not in method or NEW in source:
        raise ValueError('native work-route caller drift')
    output=source.replace(OLD,NEW,1)
    anchor='class SpatialTempo:'
    if output.count(anchor)!=1:
        raise ValueError('ambiguous helper insertion')
    output=output.replace(anchor,HELPER+anchor,1)
    ast.parse(output)
    return output


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.source.resolve()==args.output.resolve():
        parser.error('output must be a separate scratch file')
    data=args.source.read_bytes()
    result=compose(data.decode('utf-8')).encode('utf-8')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(result)
    print(json.dumps({'input_blob':blob(data),'output_blob':blob(result),
                      'output_sha256':hashlib.sha256(result).hexdigest()},sort_keys=True))

if __name__=='__main__':
    main()

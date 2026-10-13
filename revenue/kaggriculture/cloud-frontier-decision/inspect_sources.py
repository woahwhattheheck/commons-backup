"""Static source decoding only. Does not import agents or run any game."""
import ast
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zlib

HERE = Path(__file__).resolve().parent
VENDOR = HERE.parent / 'cloud-frontier-policy/next-panel/vendor'


def inspect():
    upstream = json.loads((VENDOR.parent/'UPSTREAM.json').read_text())
    for path in ('vendor/arlene.py', 'vendor/apex/source/tape.inc',
                 'vendor/apex/main.py', 'vendor/apex/source/policy.cpp',
                 'vendor/apex/source/include/six_day_budget_guard.hpp'):
        assert hashlib.sha256((VENDOR.parent/path).read_bytes()).hexdigest() == upstream['files'][path]['sha256']
    tree = ast.parse((VENDOR/'arlene.py').read_text())
    blob = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id=='_BLOB' for t in n.targets))
    data = json.loads(zlib.decompress(base64.b64decode(blob)))
    routes = {data['main']: data['full']}
    for t in data['tails']:
        routes[t['h']] = routes[t['parent']][:t['at']] + t['suffix']
    report = {'source_main': '52b71bf15433cf6831e4373d4fd84fb9ffcbcf05',
              'meaning': 'Requested actions in source data, NOT successful work or causal cash attribution.', 'routes': {}}
    ops = ['PASS','NORTH','SOUTH','EAST','WEST','PICKUP','DROP','PLACE','PLANT','WATER',
           'HARVEST','FERTILIZE','DIG','BUILD_COOP','BUILD_PASTURE','FEED','COLLECT_FERTILIZER','CARE']
    for name, route in routes.items():
        service = Counter(a[0] for turn in route for a in [turn.get('farmer',['PASS']),*turn.get('hands',[])] if a)
        hires = Counter(i//24 for i,t in enumerate(route) for o in t.get('market',[]) if o[0]=='HIRE')
        report['routes']['arlene:'+name] = {'turns':len(route),'hires_by_day':dict(hires),
            'service':{k:service[k] for k in ['HARVEST','WATER','FEED','CARE','FERTILIZE']}}
    index = 0
    for block in re.findall(r'\{([^{}]+)\}', (VENDOR/'apex/source/tape.inc').read_text()):
        rows = re.findall(r'"([0-9 ]+)"', block)
        if not rows: continue
        service, hires = Counter(), Counter()
        for step,row in enumerate(rows):
            v = list(map(int,row.split())); units, orders = v[:2]
            assert len(v) == 2 + 3*(units+orders)
            for j in range(units): service[ops[v[2+3*j]]] += 1
            for j in range(orders):
                if v[2+3*units+3*j] == 1: hires[step//24] += 1
        report['routes']['apex:'+str(index)] = {'turns':len(rows),'hires_by_day':dict(hires),
            'service':{k:service[k] for k in ['HARVEST','WATER','FEED','CARE','FERTILIZE']}}
        index += 1
    return report


if __name__ == '__main__': print(json.dumps(inspect(), indent=2))

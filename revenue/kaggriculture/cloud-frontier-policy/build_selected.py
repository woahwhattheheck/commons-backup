"""Build selected sales-only derivative; exact parent plus attributed helpers."""
import ast
import hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
HELPERS = {'_get', '_seat', '_farm', '_shed_access', '_projected_shed', '_shape',
           '_market_price', '_is_sell', '_impact_score', '_demand_per_day',
           '_order_score', '_v17_pickup_reserve', '_copy_action'}
CONSTANTS = {'_MARKET_PARAMS', '_SHOP_PRODUCTS', '_PRICE_FLOOR', '_DEMAND_ALPHA'}
PINS = {'igor_multiroute.py': '8ac34abce129cf5c9456776c90edf7d2233b3a280bbdcf7622628825ef3669a0',
        'kaito_v43.py': '69f06a802b62aa08f28705dab5728eb924bb6a7c23ffe0164f65b104cc3dadf3'}


def build():
    parents = {name: (HERE/'vendor'/name).read_bytes() for name in PINS}
    for name, data in parents.items():
        if hashlib.sha256(data).hexdigest() != PINS[name]:
            raise ValueError('Pinned source mismatch: '+name)
    igor = parents['igor_multiroute.py'].decode()
    tree = ast.parse(igor)
    extracts = []
    for node in tree.body:
        if (isinstance(node, ast.FunctionDef) and node.name in HELPERS or
            isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTANTS for t in node.targets)):
            extracts.append(ast.get_source_segment(igor, node))
    helpers = '\n\n'.join(extracts).encode()
    source = (b'# Apache-2.0. Kaito Fukami policy, Igor Zharov helpers, LARK sale overlay. See NOTICE.md.\n'
              + parents['kaito_v43.py']
              + b'\n\n# BEGIN EXACT IGOR HELPER EXTRACTS\nimport copy\nimport math\n'
              + helpers + b'\n\n# BEGIN LARK ADDITIONS\n' + (HERE/'sales.py').read_bytes())
    compile(source, 'candidate.py', 'exec')
    (HERE/'candidate.py').write_bytes(source)
    entrypoint = (HERE/'entrypoint.py').read_bytes()
    (HERE/'main.py').write_bytes(source + entrypoint)
    print(hashlib.sha256(source).hexdigest(), len(source))


if __name__ == '__main__':
    build()

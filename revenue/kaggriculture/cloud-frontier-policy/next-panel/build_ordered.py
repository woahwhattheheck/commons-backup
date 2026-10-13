from pathlib import Path
import hashlib
p=Path(__file__).resolve().parent;s=(p/'vendor/arlene.py').read_text();assert hashlib.sha256(s.encode()).hexdigest()=='1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4'
a=s.index('        # ---- projected shed:');b=s.index('        # ---- room_guard:',a)
s=s[:a]+'''        # LARK modification: exact ordered PICKUP/DROP/PLACE shed transfers.
        proj, carried_after_transfers = _ordered_shed_projection(
            shed, invs, positions, acts, tiles, SHED_CAP)

'''+s[b:]
s=s.replace('carried = sum(max(0, int(n)) for inv in invs for n in inv.values())','carried = sum(max(0, int(n)) for inv in carried_after_transfers for n in inv.values())')
s=s.replace('shed_total = sum(max(0, int(n)) for n in shed.values())','shed_total = sum(max(0, int(n)) for n in proj.values())')
s=s.replace('int(shed.get(it, 0))','int(proj.get(it, 0))')
s+='\n'+(p/'ordered_shed.py').read_text()+'''\n_ORDERED_SHED_PARENT = agent

def lark_ordered_shed_entrypoint(observation):
    return _ORDERED_SHED_PARENT(observation)
'''
(p/'ordered-shed-main.py').write_text(s)
template=Path('next-panel-runtime/arlene-adapter.py').read_text();template=template.replace(str((p/'vendor/arlene.py').resolve()),str((p/'ordered-shed-main.py').resolve()));Path('next-panel-runtime/ordered-shed-adapter.py').write_text(template)
print(hashlib.sha256(s.encode()).hexdigest())

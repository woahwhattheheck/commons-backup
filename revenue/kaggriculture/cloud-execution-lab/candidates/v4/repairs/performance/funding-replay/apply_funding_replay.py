# SPDX-License-Identifier: Apache-2.0
"""Pure, fail-closed source composition for native FrozenSelected funding replay.

Four named function spans change; one private disposal helper is added.
Unrelated peer source is preserved.
The original and fully applied function sets are accepted; mixed or changed
spans fail before any output write. There is no activation or archive builder.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

BEFORE = {'_stressed_sale_receipt': '01c7fb5871b94e63ba87824bc87fed49402597c76824c960798b0e90314320ea',
 '_market_prefix_state': '84a587cf167b9db2e7696c5adcf9f9636d1c2c516f79dbe634c0834e3b50f425',
 'fund_same_turn_acquisition': '2cb97c04c171cd72e57cb2487e6500f5f3dcf10a3cb0ec2cb6c5f6410e359751',
 'funded_minimum_now': 'faa06a1f64161cdb2e1bdc734d0db365d20c3cc31808893d49c9744f8e2aa3df'}
AFTER = {'funded_minimum_now': '42038b5f59bba0f7ceeb296aa75c4e291e27e77eb2ab46ded0eaa52835bae12e',
 'fund_same_turn_acquisition': '117f150d54bd6bae75133bf6b415fdc0b12c1dc56327563965200d3499166167',
 '_market_prefix_state': '03f904a410a8f2c60a0b710e1230a358f05a510a73e61d8c61d56db06e09f71e',
 '_stressed_sale_receipt': '4771f6dcfe9864ad4ed891bedba909443a0a43116481e858c1b71dfe527d3b17'}
PATCHES = {'_stressed_sale_receipt': [('                            rival_quantity):',
                             '                            rival_quantity, _models=None):'),
                            ('    '
                             "model=MarketPath(item,int(inventory),market.get('params'),shops,config,now,now)",
                             '    # Models live for exactly one funding search, never across observations.\n'
                             '    # Snapshot native scalar price parameters on every call: a rival callback\n'
                             '    # may edit them, so identity-only keys would reuse stale rounded quotes.\n'
                             "    params=market.get('params')\n"
                             '    signature=None\n'
                             '    if _models is not None:\n'
                             '        table=params or m.MARKET_PARAMS\n'
                             '        spec=table.get(item) if type(table) is dict else None\n'
                             '        if (type(spec) is dict and all(type(k) is str for k in spec)\n'
                             '                and all(type(v) in (int,float,str,bool,type(None))\n'
                             '                        for v in spec.values())):\n'
                             '            signature=tuple(spec.items())\n'
                             '    cached=(_models.get(item) if _models is not None\n'
                             '            and signature is not None else None)\n'
                             '    owned=_models is None or signature is None\n'
                             '    if cached is not None and cached[0]==signature:\n'
                             '        model=cached[1]\n'
                             '    else:\n'
                             '        if cached is not None:\n'
                             '            del _models[item]\n'
                             '            _dispose_funding_model(cached[1])\n'
                             '        model=MarketPath(item,int(inventory),params,shops,config,now,now)\n'
                             '        if _models is not None and signature is not None:\n'
                             '            _models[item]=(signature,model)'),
                            ('    cases={}\n'
                             '    for name,r,alignment in (\n'
                             "            ('no_rival',0,'paired'),\n"
                             "            ('observed_paired',rival,'paired'),\n"
                             "            ('observed_before',rival,'before')):\n"
                             '        cases[name]=model.joint(int(inventory),quantity,r,alignment)\n'
                             '    name,(cash,_other,ending)=min(\n'
                             '        cases.items(),key=lambda '
                             'entry:(int(entry[1][0]),-int(entry[1][2]),entry[0]))\n'
                             '    return int(cash),int(ending),name\n',
                             '    try:\n'
                             '        cases={}\n'
                             '        for name,r,alignment in (\n'
                             "                ('no_rival',0,'paired'),\n"
                             "                ('observed_paired',rival,'paired'),\n"
                             "                ('observed_before',rival,'before')):\n"
                             '            cases[name]=model.joint(int(inventory),quantity,r,alignment)\n'
                             '        name,(cash,_other,ending)=min(\n'
                             '            cases.items(),key=lambda '
                             'entry:(int(entry[1][0]),-int(entry[1][2]),entry[0]))\n'
                             '        return int(cash),int(ending),name\n'
                             '    finally:\n'
                             '        if owned:\n'
                             '            _dispose_funding_model(model)\n')],
 '_market_prefix_state': [('                         rival_quantity, stop):',
                           '                         rival_quantity, stop, _models=None):'),
                          ('                item,sold,inventory[item],market,shops,config,now,rival)',
                           '                '
                           'item,sold,inventory[item],market,shops,config,now,rival,_models)')],
 'fund_same_turn_acquisition': [('    baseline=_market_prefix_state(\n',
                                 '    models={}\n    baseline=_market_prefix_state(\n'),
                                ('        '
                                 'original,farm,private,market,shops,config,now,rival_quantity,len(original)-1)',
                                 '        '
                                 'original,farm,private,market,shops,config,now,rival_quantity,len(original)-1,models)'),
                                ('                '
                                 'candidate,farm,private,market,shops,config,now,rival_quantity,target)',
                                 '                '
                                 'candidate,farm,private,market,shops,config,now,rival_quantity,target,models)')],
 'funded_minimum_now': [('            traces = [\n'
                         '                _funding_trace(obs, config, farm, private, route, now, '
                         'prefix_end,\n'
                         '                               candidate_market, stress_units=0),\n'
                         '                _funding_trace(obs, config, farm, private, route, now, '
                         'prefix_end,\n'
                         '                               candidate_market, stress_units=stress_units),\n'
                         '            ]',
                         '            nominal = _funding_trace(\n'
                         '                obs, config, farm, private, route, now, prefix_end,\n'
                         '                candidate_market, stress_units=0)\n'
                         '            # The prior rival draw changes only raw BUY_PRODUCT item inventories.\n'
                         '            # With no such executed-prefix row (or zero draw), both simulations\n'
                         '            # are identical. Keep the two-entry certificate, not a weaker gate.\n'
                         '            has_draw = bool(stress_units) and any(\n'
                         "                o and len(o)>2 and o[0]=='BUY_PRODUCT'\n"
                         '                for t in range(now, prefix_end+1)\n'
                         '                for o in (candidate_market if t==now else\n'
                         "                          (route[t].get('market', []) if t<len(route) else "
                         '[]))[:max_orders])\n'
                         '            stressed = (_funding_trace(\n'
                         '                obs, config, farm, private, route, now, prefix_end,\n'
                         '                candidate_market, stress_units=stress_units) if has_draw else '
                         'nominal)\n'
                         '            traces = [nominal, stressed]')]}
ADDED = 'def _dispose_funding_model(model):\n    """Dispose only an owned private model after its last receipt use.\n\n    CACHELIFE protocol: clearing entries alone leaves bound-method owner cycles.\n    Never call this at the end of a receipt that borrowed a search-pool model.\n    """\n    model.quote.cache_clear()\n    model.single.cache_clear()\n    model.joint.cache_clear()\n    del model.single, model.joint\n\n\n'
FINALIZER = '    finally:\n        for _signature, model in models.values():\n            _dispose_funding_model(model)\n        models.clear()\n'

def _spans(source: str) -> dict[str, tuple[int, int]]:
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in result:
                raise ValueError("duplicate top-level function: " + node.name)
            result[node.name] = (offsets[node.lineno - 1], offsets[node.end_lineno])
    return result


def apply(source: str) -> str:
    """Return the composed source or raise ValueError without partial output."""
    spans = _spans(source)
    observed = {}
    for name in BEFORE:
        if name not in spans:
            raise ValueError("missing required function: " + name)
        start, end = spans[name]
        observed[name] = hashlib.sha256(source[start:end].encode()).hexdigest()
    if observed == AFTER:
        helper = spans.get('_dispose_funding_model')
        expected_helper = ADDED.rstrip() + '\n'
        if helper is None or source[helper[0]:helper[1]] != expected_helper:
            raise ValueError("missing or changed funding disposal helper")
        return source
    if '_dispose_funding_model' in spans:
        raise ValueError("funding disposal helper already exists without its composed callers")
    if observed != BEFORE:
        changed = [name for name in BEFORE if observed[name] != BEFORE[name]]
        raise ValueError("funding source changed; rebase explicitly: " + ", ".join(changed))
    result = source
    for name in sorted(PATCHES, key=lambda n: spans[n][0], reverse=True):
        start, end = spans[name]
        part = source[start:end]
        for before, after in PATCHES[name]:
            if part.count(before) != 1:
                raise ValueError("non-unique patch anchor: " + name)
            part = part.replace(before, after, 1)
        if name == 'fund_same_turn_acquisition':
            if part.count('    models={}\n') != 1:
                raise ValueError("non-unique funding owner anchor")
            head, tail = part.split('    models={}\n')
            part = (head + '    models={}\n    try:\n'
                    + ''.join('    ' + line if line.strip() else line
                              for line in tail.splitlines(keepends=True))
                    + FINALIZER)
        if hashlib.sha256(part.encode()).hexdigest() != AFTER[name]:
            raise ValueError("unexpected output function: " + name)
        result = result[:start] + part + result[end:]
    position = _spans(result)['_stressed_sale_receipt'][0]
    result = result[:position] + ADDED + result[position:]
    compile(result, "funding_replay_composed", "exec")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("write a separate composition output, not the source")
    result = apply(args.source.read_bytes().decode("utf-8"))
    # Parsing, all pins and composition checks finish before opening output.
    args.output.write_bytes(result.encode("utf-8"))
    print(hashlib.sha256(result.encode()).hexdigest())


if __name__ == "__main__":
    main()

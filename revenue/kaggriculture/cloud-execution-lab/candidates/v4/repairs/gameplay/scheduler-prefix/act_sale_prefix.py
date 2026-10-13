# SPDX-License-Identifier: Apache-2.0
"""Compose the nonterminal SELL-prefix repair into the existing scheduler source.

This is a source-only repair, not a new policy, runtime, feature key or release.
It does not run the legacy V4 materializer or modify the production package.
The exact act-method pin deliberately rejects unknown/partially patched inputs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

ACT_BEFORE_SHA256 = "847427a1a68349f2efb280cac44ea1fddd098e2af9848d2a3800e00654016c5f"
ACT_AFTER_SHA256 = "b6c61101c399b6a7afbb62ef8034ae8d5befe6306a70b0ad4ec620abacf42fdb"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
HELPERS = '''# V4-SCHEDULER-SALE-PREFIX: raw positions, not valid-order compaction.
def _v4_sale_market_limit(config):
    return max(1, int(config.get('maxMarketOrdersPerTurn', 10)))


def _v4_sale_market_prefix(raw, config):
    # Match the official market's list normalization and minimum-one cap.
    return raw[:_v4_sale_market_limit(config)] if isinstance(raw, list) else []


'''

# All replacements are scoped to SellScheduler.act, never other methods.
REPLACEMENTS = (
    ("        for o in base['market']:\n",
     "        for o in _v4_sale_market_prefix(base.get('market', []), config):\n"),
    ("                for order in route[t].get('market',[]) if t<len(route) else []:\n",
     "                for order in _v4_sale_market_prefix(route[t].get('market', []) if t<len(route) else [], config):\n"),
    ("                    orders=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n"
     "                    if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):\n",
     "                    raw_orders=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n"
     "                    orders=_v4_sale_market_prefix(raw_orders, config)\n"
     "                    if len(orders)>=_v4_sale_market_limit(config):\n"),
    ("        for raw in out['market']:\n"
     "            o=list(raw)\n",
     "        for slot, raw in enumerate(out['market']):\n"
     "            if slot>=_v4_sale_market_limit(config):\n"
     "                market.append(raw)  # Engine-inert suffix stays opaque.\n"
     "                continue\n"
     "            o=list(raw)\n"),
    ("            if q>0 and len(market)<int(config.get('maxMarketOrdersPerTurn',10)):\n",
     "            if q>0 and len(market)<_v4_sale_market_limit(config):\n"),
    ("            sold=sum(o[2] for o in out['market'] if o and o[0]=='SELL' and o[1]==item)\n",
     "            sold=sum(o[2] for o in _v4_sale_market_prefix(out['market'], config) if o and o[0]=='SELL' and o[1]==item)\n"),
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _method(source: str):
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SellScheduler']
    if len(classes) != 1 or classes[0].decorator_list:
        raise ValueError('expected one undecorated top-level SellScheduler')
    methods = [n for n in classes[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'act']
    if len(methods) != 1 or type(methods[0]) is not ast.FunctionDef or methods[0].decorator_list:
        raise ValueError('expected one undecorated synchronous SellScheduler.act')
    method = methods[0]
    lines = source.splitlines(keepends=True)
    text = ''.join(lines[method.lineno - 1:method.end_lineno])
    return tree, classes[0], method, lines, text


def rewrite_source(source: str) -> tuple[str, dict]:
    """Return a checked source postimage, preserving all unrelated bytes.

    No filesystem writes or source execution occur here. Unknown inputs, stale
    anchors, helper collisions and partial application raise ValueError.
    """
    if not isinstance(source, str):
        raise TypeError('source must be UTF-8 text')
    tree, cls, method, lines, before = _method(source)
    digest = sha256(before)
    helper_names = {'_v4_sale_market_limit', '_v4_sale_market_prefix'}
    helpers = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name in helper_names]
    if digest == ACT_AFTER_SHA256:
        if source.count(HELPERS) != 1 or len(helpers) != 2:
            raise ValueError('patched method has missing or altered helpers')
        return source, {'changed': False, 'source_sha256': sha256(source),
                        'act_sha256': digest, 'engine_blob': ENGINE_BLOB}
    if digest != ACT_BEFORE_SHA256:
        raise ValueError('unknown SellScheduler.act preimage: ' + digest)
    # Reject any occurrence: assignment aliases and nested helper definitions
    # must not silently capture the names introduced by this transform.
    if helpers or any(name in source for name in helper_names):
        raise ValueError('repair helper name collision')
    after = before
    for old, new in REPLACEMENTS:
        if after.count(old) != 1:
            raise ValueError('expected exactly one act anchor: ' + old.strip())
        after = after.replace(old, new, 1)
    if sha256(after) != ACT_AFTER_SHA256:
        raise ValueError('postimage digest mismatch')
    # Compute both modifications against the original line coordinates.
    output = (''.join(lines[:cls.lineno - 1]) + HELPERS
              + ''.join(lines[cls.lineno - 1:method.lineno - 1]) + after
              + ''.join(lines[method.end_lineno:]))
    compile(output, '<scheduler-sale-prefix>', 'exec')
    if _method(output)[-1] != after:
        raise ValueError('postimage structural mismatch')
    return output, {
        'changed': True,
        'source_before_sha256': sha256(source),
        'source_after_sha256': sha256(output),
        'act_before_sha256': digest,
        'act_after_sha256': sha256(after),
        'replacement_count': len(REPLACEMENTS),
        'engine_blob': ENGINE_BLOB,
        'scope': 'nonterminal SellScheduler.act sale-prefix consumers only',
        'production_activation': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('output must differ from source; in-place production edits are not supported')
    output, receipt = rewrite_source(args.source.read_bytes().decode('utf-8'))
    # Never overwrite a peer's postimage or an existing production file.
    with args.output.open('x', encoding='utf-8', newline='') as handle:
        handle.write(output)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

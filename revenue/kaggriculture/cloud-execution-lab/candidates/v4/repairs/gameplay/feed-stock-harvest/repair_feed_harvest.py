# SPDX-License-Identifier: Apache-2.0
"""Conservative native feed-certificate repair; no runtime or file writes.

Only the authenticated _feed_window function is replaced. Other source bytes,
including concurrently composed FERT-prefix repairs, are preserved verbatim.
"""
from __future__ import annotations

import ast
import hashlib

ORIGINAL_FUNCTION_SHA256 = 'c77803fb4ee1f9113c2a6105a103db2ef8332d1bf02c07549329debc6efc1956'
REPAIRED_FUNCTION_SHA256 = 'b5b9d01c7d14a5ba3844bad1b48acd866ff29b7ab47944f831038a3638afa4fb'
REASON = 'protected_feed_has_uncredited_wheat_harvest'

EDITS = (
    ('    fertilizer_requests = 0\n',
     '    fertilizer_requests = 0\n    wheat_harvests = []\n'),
    ('                tile = animals.get(pos)\n',
     '                tile = animals.get(pos)\n'
     "                if op == 'HARVEST':\n"
     '                    observed_tile = farm[\'tiles\'][pos[1]][pos[0]]\n'
     '                    if (isinstance(observed_tile, dict)\n'
     "                            and observed_tile.get('kind') == 'PLANT'\n"
     "                            and observed_tile.get('crop') == 'WHEAT'\n"
     "                            and step // 24 - _whole(observed_tile['planted_day'])\n"
     "                            >= _whole(mechanics.CROPS['WHEAT']['first_yield_day'])):\n"
     '                        wheat_harvests.append((actor, step))\n'),
    ('        if not deficit:continue\n',
     '        if not deficit:continue\n'
     "        last_feed = max(f['step'] for f in feeds if f['actor'] == actor)\n"
     '        # Uncredited harvested grain can satisfy a feed instead of the\n'
     '        # retained shed grain. The latter can then return at EOD and\n'
     '        # displace another producer\'s goods; do not certify its use.\n'
     '        if any(a == actor and t < last_feed for a, t in wheat_harvests):\n'
     "            raise ValueError('protected_feed_has_uncredited_wheat_harvest')\n"),
)


def function_span(source: str) -> tuple[int, int, str]:
    """Return character offsets and complete function bytes, including newline."""
    if not isinstance(source, str):
        raise TypeError('source must be UTF-8 decoded text')
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == '_feed_window']
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise ValueError('expected exactly one undecorated _feed_window')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    stop = sum(map(len, lines[:node.end_lineno]))
    return start, stop, source[start:stop]


def repair_source(source: str) -> str:
    """Fail closed on target drift; idempotently preserve every unrelated byte."""
    start, stop, function = function_span(source)
    digest = hashlib.sha256(function.encode('utf-8')).hexdigest()
    if digest == REPAIRED_FUNCTION_SHA256:
        return source
    if digest != ORIGINAL_FUNCTION_SHA256:
        raise ValueError('unrecognized _feed_window source: ' + digest)
    repaired = function
    for before, after in EDITS:
        if repaired.count(before) != 1:
            raise ValueError('nonunique feed repair anchor')
        repaired = repaired.replace(before, after, 1)
    if hashlib.sha256(repaired.encode('utf-8')).hexdigest() != REPAIRED_FUNCTION_SHA256:
        raise ValueError('feed repair postimage mismatch')
    result = source[:start] + repaired + source[stop:]
    compile(result, '<feed-harvest-repair>', 'exec')
    return result

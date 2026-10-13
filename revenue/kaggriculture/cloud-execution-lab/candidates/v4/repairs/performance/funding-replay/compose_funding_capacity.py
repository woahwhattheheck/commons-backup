# SPDX-License-Identifier: Apache-2.0
"""Compose physical-capacity and raw-slot funding-boundary custody into V4.

TOWNPATH, UNITFLOW and FUNDING-PERF may compose first. Only two authenticated top-level
function spans change; this is not a runtime builder or policy switch.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

BEFORE = {'_funding_trace': {'88d315a8e16a7a3f1aa2e88d65e53bad827ce2cee4b7fbef65fe4d192cdfdff6',
                    'af20f71e59ebb9abea7a90a914f4f727e65d2bd7c958727e521e3e29447c2527',
                    'c6b789fa8b28ce020a2b2d803b31e76cdd6505b41815f2a49ebe90bbc5058088',
                    'd9ca4d0737b5ab3344c0df588014a83a5c634464327fdd175b8ec862c2d7beb9'},
 'funded_minimum_now': {'42038b5f59bba0f7ceeb296aa75c4e291e27e77eb2ab46ded0eaa52835bae12e',
                        'faa06a1f64161cdb2e1bdc734d0db365d20c3cc31808893d49c9744f8e2aa3df'}}
AFTER = {'_funding_trace': {'2adf10d26fd7a0d3445783e5fb64e540361eecdfd0702e1edc2b777034aaf1e4',
                    '61b78c43f796c10a943b72ca84a458720219e3cc732903df27f18c6c2545906b',
                    '74ef800fe10fbec67e1771644de3a3ba2b43f7fbb07e93b6597e7689858f17a9',
                    'db252cac77861df9c946340affbd9ebeaf9de34d286a77e68c218d31dae3d6b0'},
 'funded_minimum_now': {'c9c50457890e1acb161c97e56804021bbe697005fccf226667a027a88557b0a9',
                        'e65489a58f7f59afb16a730be45d369aab7391f3acc5e9661304703e0c6b1477'}}


def spans(source: str) -> dict[str, tuple[int, int]]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in result:
                raise ValueError('duplicate top-level function: ' + node.name)
            result[node.name] = offsets[node.lineno - 1], offsets[node.end_lineno]
    return result


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError('missing or ambiguous composition anchor')
    return text.replace(before, after, 1)


def patch_trace(part: str) -> str:
    # The pressure/capacity upper bounds in other consumers intentionally keep
    # their oversized sheds. This trace promises acquisition fills, not bounds.
    part = once(part, '24, 10**6)', '24, cap)')
    part = once(part, '    executed_sales = []\n',
                '    executed_sales = []\n    sale_receipts = []\n')
    part = once(part,
                '                    executed_sales.append((t, item, executed, cash))',
                '                    executed_sales.append((t, item, executed, cash))\n'
                '                    sale_receipts.append((t, index, item, executed, cash))')
    part = once(part, "            'executed_sales': executed_sales}",
                "            'executed_sales': executed_sales, 'sale_receipts': sale_receipts}")
    return part


def patch_minimum(part: str) -> str:
    part = once(part, "        certificate['funding_turn'] = funding_turn\n",
                "        certificate['funding_turn'] = funding_turn\n"
                "        # The stop event belongs to a raw slot, not just a day. A smaller\n"
                "        # current sale must not destroy the deposit which funds that event.\n"
                "        boundary = next((r for r in scout['sale_receipts'] if r[4] > 0), None)\n"
                "        trace_end = boundary[0] if boundary is not None else prefix_end\n"
                "        certificate['funding_boundary'] = boundary\n")
    anchor = "        required = {key: units for key, units in reference['acquisitions'] if units > 0}\n"
    part = once(part, anchor, anchor +
                "        if boundary is not None:\n"
                "            # Buys before the first filled SELL on its own turn still\n"
                "            # need inherited funding; a later row cannot pre-fund them.\n"
                "            required = {key: units for key, units in scout['acquisitions']\n"
                "                        if units > 0 and key[:2] < boundary[:2]}\n")
    part = once(part, '        if not required:\n',
                '        if not required and boundary is None:\n')
    head, tail = part.split('        for quantity in range(baseline + 1):\n')
    # This also preserves PERF's stress deduplication while extending its raw
    # BUY_PRODUCT scan to every newly inspected boundary-turn row.
    tail = tail.replace('prefix_end', 'trace_end')
    part = head + '        for quantity in range(baseline + 1):\n' + tail
    part = once(part, '            for trace in traces:\n',
                '            for trace in traces:\n'
                '                if boundary is not None:\n'
                "                    receipt = next((r for r in trace['sale_receipts']\n"
                '                                    if r[:3] == boundary[:3]), None)\n'
                '                    if (receipt is None or receipt[3] < boundary[3]\n'
                '                            or receipt[4] < boundary[4]):\n'
                '                        safe = False\n'
                '                        break\n')
    return part


def apply(source: str) -> str:
    positions = spans(source)
    if not all(name in positions for name in BEFORE):
        raise ValueError('missing funding functions')
    observed = {name: digest(source[slice(*positions[name])]) for name in BEFORE}
    if AFTER and all(observed[name] in AFTER[name] for name in BEFORE):
        return source
    if not all(observed[name] in BEFORE[name] for name in BEFORE):
        raise ValueError('changed or partially applied funding source; rebase explicitly')
    patches = {'_funding_trace': patch_trace, 'funded_minimum_now': patch_minimum}
    result = source
    for name in sorted(BEFORE, key=lambda n: positions[n][0], reverse=True):
        start, end = positions[name]
        part = patches[name](source[start:end])
        if AFTER and digest(part) not in AFTER[name]:
            raise ValueError('unexpected funding postimage: ' + name)
        result = result[:start] + part + result[end:]
    compile(result, 'captrace_composed', 'exec')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('write a separate source output, never the input')
    result = apply(args.source.read_bytes().decode('utf-8'))
    # Do not overwrite any existing output or open it before all input checks.
    with args.output.open('xb') as stream:
        stream.write(result.encode('utf-8'))
    print(digest(result))


if __name__ == '__main__':
    main()

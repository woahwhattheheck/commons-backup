# SPDX-License-Identifier: Apache-2.0
"""Compose an action-equivalent MarketPath.score acceleration, not a policy.

Only the exact score method is replaced; independent scheduler-prefix and
_single/_joint repairs are retained. The original implementation remains the
fallback for values outside the native integer-lot domain. No runtime is edited
unless the caller explicitly writes the returned source to its staging path.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

REFERENCE_SHA256 = frozenset({
    'ca4a363dbd3dbd99f25951add7955d09b417c9610ead8ae966785eda26117e1c',
    '4fea05b3c9ea8025455caf9b1a8d8ae032308a3f772d87043bee96dedab3a30e',
})

SCORE = '''    def score(self, plan, quantity, rival, alignment, terminal=False):
        # Short horizons do not amortize event construction; retain the fast
        # incumbent loop there. Native optimizer dates are integer callbacks.
        if self.end - self.now < 4:
            return self._score_eventpath_reference(plan, quantity, rival, alignment, terminal)
        # Sparse integer-lot evaluation; preserve the exact reference fallback.
        if (type(quantity) is not int or quantity < 0 or
                type(self.inventory) is not int or
                type(plan) not in (tuple, list, dict)):
            return self._score_eventpath_reference(plan, quantity, rival, alignment, terminal)
        orders = dict(plan)
        rivals = dict(rival) if isinstance(rival, tuple) else {self.now: rival}
        events = orders.keys() | rivals.keys()
        if any(type(t) is not int for t in events):
            return self._score_eventpath_reference(plan, quantity, rival, alignment, terminal)
        now, end = self.now, self.end
        context = (self.item, now, end, tuple(self.shops),
                   self.config.get('townShopSellInterval', 4),
                   self.config.get('townCenterSellInterval', 24))
        if getattr(self, '_eventpath_context', None) != context:
            if (type(now) is not int or type(end) is not int or
                    not 0 <= end - now <= 4095):
                return self._score_eventpath_reference(plan, quantity, rival, alignment, terminal)
            prefix = {}; total = 0
            for step in range(now, end + 1):
                prefix[step] = total
                total += absorption(self.item, step, self.shops, self.config)
            self._eventpath_prefix = prefix
            self._eventpath_total = total
            self._eventpath_context = context
        prefix = self._eventpath_prefix
        inv = self.inventory
        own_cash = other_cash = sold = consumed = 0
        for step in sorted(events):
            if step < now or step > end:
                continue
            q = orders.get(step, 0); r = rivals.get(step, 0)
            if type(q) is not int or type(r) is not int or r < 0:
                return self._score_eventpath_reference(plan, quantity, rival, alignment, terminal)
            used = prefix[step]
            inv -= used - consumed; consumed = used
            q = min(quantity - sold, max(0, q))
            a, b, inv = self.joint(inv, q, r, alignment)
            own_cash += a; other_cash += b; sold += q
        inv -= self._eventpath_total - consumed
        remaining = quantity - sold
        carry = 0.0
        if remaining and not terminal:
            carry = float(self.single(inv, remaining)[0])
        return own_cash + carry - other_cash, own_cash, other_cash, remaining
'''


def _score_node(source: str):
    tree = ast.parse(source)
    absorbers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'absorption']
    lines = source.splitlines(keepends=True)
    if len(absorbers) != 1 or absorbers[0].decorator_list:
        raise ValueError('expected the verified undecorated absorption function')
    absorber = ''.join(lines[absorbers[0].lineno - 1:absorbers[0].end_lineno])
    if hashlib.sha256(absorber.encode()).hexdigest() != 'f4a824e421361ccb978f5ffdaa8d73b344d2624e4c05574ae876ffff141694bd':
        raise ValueError('absorption source drifted')
    owners = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MarketPath']
    if len(owners) != 1:
        raise ValueError('expected exactly one MarketPath class')
    methods = [n for n in owners[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    scores = [n for n in methods if n.name == 'score']
    if len(scores) != 1 or scores[0].decorator_list:
        raise ValueError('expected exactly one MarketPath.score method')
    return scores[0], methods


def compose(source: str) -> str:
    """Replace one exact method; refuse drift, retain every unrelated byte."""
    node, methods = _score_node(source)
    lines = source.splitlines(keepends=True)
    old = ''.join(lines[node.lineno - 1:node.end_lineno])
    if old == SCORE:
        fallback = [m for m in methods if m.name == '_score_eventpath_reference']
        if len(fallback) != 1 or fallback[0].decorator_list:
            raise ValueError('composed score has no unique reference method')
        reference = ''.join(lines[fallback[0].lineno - 1:fallback[0].end_lineno])
        reference = reference.replace('def _score_eventpath_reference(', 'def score(', 1)
        if hashlib.sha256(reference.encode()).hexdigest() not in REFERENCE_SHA256:
            raise ValueError('composed reference method drifted')
        return source
    if hashlib.sha256(old.encode()).hexdigest() not in REFERENCE_SHA256:
        raise ValueError('MarketPath.score does not match the verified current method')
    if any(m.name == '_score_eventpath_reference' for m in methods):
        raise ValueError('reference method already exists without the verified score')
    fallback = old.replace('def score(', 'def _score_eventpath_reference(', 1)
    result = ''.join(lines[:node.lineno - 1]) + SCORE + '\n' + fallback + ''.join(lines[node.end_lineno:])
    compile(result, '<composed scheduler>', 'exec')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('use a separate staging output; this command does not edit the source in place')
    try:
        candidate = compose(args.source.read_bytes().decode('utf-8'))
        with args.output.open('x', encoding='utf-8') as handle:
            handle.write(candidate)
    except (OSError, ValueError, SyntaxError) as exc:
        parser.exit(2, f'{exc}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

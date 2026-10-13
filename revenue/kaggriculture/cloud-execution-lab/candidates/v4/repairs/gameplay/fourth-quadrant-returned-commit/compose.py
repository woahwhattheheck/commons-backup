# SPDX-License-Identifier: Apache-2.0
"""Source-pinned FourthQuadrant returned-commit/acquisition repair.

Offline only: writes a new scratch module, never production or an existing file.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

PREIMAGE = '57ffe172a5a5ebf5b57132319731aa367b9dc7f5'

CHECK = '''    def _returned_commit_matches(self, selected, returned):
        """Authenticate the complete unit vector and raw executable market prefix.

        Extra hand PLANT rows can block real actors in the engine. Empty market
        slots consume the order cap, so never filter before taking this prefix.
        This is a conservative receipt check, not an economic-equivalence claim.
        """
        if not isinstance(selected, dict) or not isinstance(returned, dict):
            return False
        try:
            cap = max(1, int(self.configuration.get('maxMarketOrdersPerTurn', 10)))
        except (TypeError, ValueError, OverflowError):
            return False
        for key, default in (('farmer', ['PASS']), ('hands', []), ('market', [])):
            if not isinstance(selected.get(key, default), list) or not isinstance(returned.get(key, default), list):
                return False
        return (returned.get('farmer', ['PASS']) == selected.get('farmer', ['PASS'])
                and returned.get('hands', []) == selected.get('hands', [])
                and returned.get('market', [])[:cap] == selected.get('market', [])[:cap])

'''

FINISH = '''    def finish(self, observation, returned_action):
        # Consume tentative state even when a finalizer rejects or malforms it.
        pending, selected = self.pending, self.selected
        self.pending = None; self.selected = None
        if pending is None or selected is None:
            return
        try:
            now = int(observation['step'])
        except (KeyError, TypeError, ValueError, OverflowError):
            return
        if (pending['start'] == now
                and self._returned_commit_matches(selected, returned_action)):
            self.plan = pending; self.generation += 1
            self.events.append({'step': now, 'kind': 'bundle_admitted',
                'crop': self.plan['crop'], 'tiles': self.plan['tiles'],
                'workers': self.plan['workers'], 'reserved_cash': self.plan['cost']})
'''

LAND_CHECK = '''        # A returned BUY_LAND is an intent, not evidence of a filled purchase.
        # Inspect the next public observation before any optional continuation,
        # including days without a worker_days entry. Successful hires alone do
        # not prove that the preceding, more expensive land order filled.
        proposal = self.pending or self.plan
        if proposal is not None:
            try:
                bundle = variant['bundle']
                if now > int(bundle['land']['step']):
                    if bundle['target_quadrant'] not in farm.get('unlocked_quadrants', []):
                        return False
                    if any(farm['tiles'][y][x] == 'LOCKED' for x, y in proposal['tiles']):
                        return False
            except (KeyError, TypeError, ValueError, IndexError, OverflowError):
                return False
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def compose(source: bytes) -> bytes:
    """Accept only the exact native donor; any peer drift is an explicit error."""
    if git_blob(source) != PREIMAGE:
        raise ValueError('fourth_quadrant.py source drift: expected ' + PREIMAGE)
    text = source.decode('utf-8')
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FourthQuadrant']
    if len(classes) != 1:
        raise ValueError('expected exactly one FourthQuadrant')
    methods = {n.name: n for n in classes[0].body if isinstance(n, ast.FunctionDef)}
    finish = methods['finish']
    lines = text.splitlines(keepends=True)
    lines[finish.lineno - 1:finish.end_lineno] = [CHECK + FINISH]
    text = ''.join(lines)
    physical = methods['_physical_match']
    # The exact whole-file pin authenticates this unique method-local anchor.
    anchor = "        farm = obs['farms'][int(obs['player'])]\n"
    start = sum(len(line) for line in source.decode('utf-8').splitlines(keepends=True)[:physical.lineno - 1])
    at = text.index(anchor, start) + len(anchor)
    text = text[:at] + LAND_CHECK + text[at:]
    ast.parse(text)
    compile(text, '<fourth-quadrant-landreturn>', 'exec')
    return text.encode('utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        result = compose(args.source.read_bytes())
        # Exclusive creation also refuses same path, symlinks and existing files.
        with args.output.open('xb') as out:
            out.write(result)
    except (OSError, ValueError, SyntaxError) as exc:
        parser.exit(2, f'{exc}\n')
    print(git_blob(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

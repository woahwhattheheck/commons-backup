# SPDX-License-Identifier: Apache-2.0
"""Compose demand-loaded history into the existing native TITAN join.

This is a source-only, fail-closed performance repair. It does not change a
feature flag, deadline, production archive, or any other V4 component.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

BASE_GIT_BLOB = 'f878320d293dbf08fda24dc66f1805702a6c763c'
EAGER = '''        self.m=dependency('terminal_mechanics')
        bridge=dependency('selected_action_history')
        fills=dependency('observed_fills');flow=dependency('flow')
        scenario=dependency('scenario_adapter')
        self.bridge=bridge.SelectedActionHistory(ledger=fills.ObservedFillLedger(),
            history=flow.FlowHistory(period=period), interval_type=flow.FlowInterval,
            infer=scenario.infer_rival_flow, mechanics=self.m)
'''
LAZY = '''        # Publish mechanics and the complete per-agent bridge together. Most
        # in-season calls have no pending receipt; they need no history imports.
        self._history_components=None
        self._history_period=period
'''
METHODS = '''    def _ensure_history(self):
        if self._history_components is None:
            dependency=self.dependency
            mechanics=dependency('terminal_mechanics')
            bridge=dependency('selected_action_history')
            fills=dependency('observed_fills');flow=dependency('flow')
            scenario=dependency('scenario_adapter')
            completed=bridge.SelectedActionHistory(ledger=fills.ObservedFillLedger(),
                history=flow.FlowHistory(period=self._history_period),
                interval_type=flow.FlowInterval, infer=scenario.infer_rival_flow,
                mechanics=mechanics)
            # Cancellation before this assignment leaves no partial bridge.
            # Stateless dependencies retain the existing path-keyed load cache.
            self._history_components=(mechanics,completed)
        return self._history_components

    @property
    def m(self):
        return self._ensure_history()[0]

    @m.setter
    def m(self, value):
        self._history_components=(value,self._ensure_history()[1])

    @property
    def bridge(self):
        return self._ensure_history()[1]

    @bridge.setter
    def bridge(self, value):
        self._history_components=(self._ensure_history()[0],value)

'''
TERMINAL = '    def _initialize_terminal(self):\n'
TERMINAL_LAZY = TERMINAL + '        self._ensure_history()  # Opt-in terminal mode keeps eager validation.\n'
OLD_OBSERVE = '''        self.pending=None
        self.bridge.record(before,cfg,final,post_unit_shed=post['private']['shed'],
                           post_unit_inventories=post['private']['inventories'])
        self.diagnostics['observed_fills']=self.bridge.observe(obs)
        self.fill_result=deepcopy(self.bridge.ledger.last_result)
'''
NEW_OBSERVE = '''        # Resolve before consuming pending: interrupted first-use construction
        # must leave the original public transition available for a retry.
        bridge=self.bridge
        self.pending=None
        bridge.record(before,cfg,final,post_unit_shed=post['private']['shed'],
                      post_unit_inventories=post['private']['inventories'])
        self.diagnostics['observed_fills']=bridge.observe(obs)
        self.fill_result=deepcopy(bridge.ledger.last_result)
'''


def compose(source: str) -> str:
    """Preserve all unrelated bytes; reject ambiguous, drifted or partial ports."""
    ast.parse(source)
    if LAZY in source:
        if (source.count(LAZY) == 1 and source.count(METHODS) == 1
                and source.count(TERMINAL_LAZY) == 1
                and source.count(NEW_OBSERVE) == 1 and EAGER not in source
                and OLD_OBSERVE not in source):
            return source
        raise ValueError('partial or changed lazy-history composition')
    if any(source.count(block) != 1 for block in (EAGER, TERMINAL, OLD_OBSERVE)):
        raise ValueError('native history source changed; rebase the repair explicitly')
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == 'TerminalHistoryJoin']
    if len(classes) != 1 or any(getattr(n, 'name', '') in
            {'_ensure_history', 'm', 'bridge'} for n in classes[0].body):
        raise ValueError('unexpected history class or pre-existing lazy API')
    result = source.replace(EAGER, LAZY, 1).replace(
        TERMINAL, METHODS + TERMINAL_LAZY, 1).replace(OLD_OBSERVE, NEW_OBSERVE, 1)
    ast.parse(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('use a separate output file; never overwrite the input')
    output = compose(args.source.read_text())
    args.output.write_text(output)
    print(hashlib.sha256(output.encode()).hexdigest())


if __name__ == '__main__':
    main()

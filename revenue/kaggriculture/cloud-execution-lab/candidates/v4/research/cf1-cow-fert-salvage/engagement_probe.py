# SPDX-License-Identifier: Apache-2.0
"""Read-only CF1 engagement evidence; the existing donor alone decides admission.

This is offline research instrumentation, not a production wrapper. The probe
traces the donor's actual return line instead of reimplementing its guards.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

DONOR_BLOB = 'ef6ab6e795375cf84c5dc7d0bcd43f979bbd0af8'


def blob_hash(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class EngagementProbe:
    """Load authenticated CF1 bytes and inspect copies of final parent actions."""

    def __init__(self, donor: Path):
        self.path = Path(donor).resolve()
        raw = self.path.read_bytes()
        if blob_hash(raw) != DONOR_BLOB:
            raise ValueError('CF1 donor source changed; re-review the evidence contract')
        self.source_sha256 = hashlib.sha256(raw).hexdigest()
        spec = importlib.util.spec_from_file_location('_cf1_engagement_donor', self.path)
        if spec is None or spec.loader is None:
            raise ValueError('Cannot load CF1 donor')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.function = self.module.apply_cow_fert_salvage
        self.reasons = self._return_guards(raw.decode())

    @staticmethod
    def _return_guards(source: str) -> dict[int, str]:
        root = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'apply_cow_fert_salvage')
        reasons: dict[int, str] = {}

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.guards: list[str] = []

            def visit_If(self, node):
                self.guards.append(ast.unparse(node.test))
                for child in node.body:
                    self.visit(child)
                self.guards.pop()
                self.guards.append('else: ' + ast.unparse(node.test))
                for child in node.orelse:
                    self.visit(child)
                self.guards.pop()

            def visit_Return(self, node):
                reasons[node.lineno] = self.guards[-1] if self.guards else 'admitted'

        Visitor().visit(root)
        return reasons

    def inspect(self, observation: dict, configuration: dict, action: dict) -> dict:
        """Never apply the hypothetical action or modify caller-owned objects."""
        if not all(isinstance(x, dict) for x in (observation, configuration, action)):
            raise TypeError('Observation, configuration and action must be mappings')
        supplied = digest([observation, configuration, action])
        obs, cfg, working = copy.deepcopy((observation, configuration, action))
        before = digest([obs, cfg, working])
        counters = self.module.telemetry.copy()
        previous_trace = sys.gettrace()
        returns: list[int] = []
        code = self.function.__code__

        def trace(frame, event, arg):
            if frame.f_code is code:
                if event == 'return':
                    returns.append(frame.f_lineno)
                return trace
            return None

        try:
            disabled = self.function(working, obs, cfg, enabled=False)
            if disabled is not working:
                raise RuntimeError('CF1 OFF no longer preserves parent identity')
            sys.settrace(trace)
            proposed = self.function(working, obs, cfg, enabled=True)
        finally:
            sys.settrace(previous_trace)
            # Donor telemetry counts hypothetical proposals; never leak it as
            # actual recovered fertilizer or change another consumer's counters.
            self.module.telemetry.clear()
            self.module.telemetry.update(counters)
        if digest([obs, cfg, working]) != before or digest([observation, configuration, action]) != supplied:
            raise RuntimeError('CF1 mutated an observation, configuration or parent action')
        if len(returns) != 1 or returns[0] not in self.reasons:
            raise RuntimeError('Missing or unrecognized donor-return evidence')
        admitted = proposed is not working
        if admitted != (proposed != working):
            raise RuntimeError('CF1 result identity/value contract disagrees')
        line = returns[0]
        result = {
            'step': observation.get('step'), 'seat': observation.get('player'),
            'would_activate': admitted, 'donor_return_line': line,
            'donor_guard': self.reasons[line], 'off_identity': True,
            'input_unchanged': True, 'input_sha256': supplied,
            'parent_action_sha256': digest(action),
            'donor_blob': DONOR_BLOB, 'completed_service': False,
        }
        if admitted:
            result['hypothetical_action'] = proposed
        return result


def summarize(rows: list[dict], *, expected_last_step: int = 718) -> dict:
    """Do not turn missing, duplicate or out-of-order callbacks into zero evidence."""
    from collections import Counter
    if type(expected_last_step) is not int or expected_last_step < 0:
        raise ValueError('expected_last_step must be a nonnegative integer')
    if not rows:
        return {'complete': False, 'callbacks': 0, 'would_activate': 0,
                'verdict': 'INCOMPLETE', 'skip_return_lines': {}}
    seats = {r.get('seat') for r in rows}
    steps = [r.get('step') for r in rows]
    valid_flags = all(type(r.get('would_activate')) is bool
                      and r.get('off_identity') is True
                      and r.get('input_unchanged') is True for r in rows)
    complete = (len(seats) == 1 and all(type(r.get('seat')) is int and r['seat'] in (0, 1) for r in rows)
                and all(type(s) is int for s in steps)
                and steps == list(range(expected_last_step + 1)) and valid_flags)
    activations = sum(r.get('would_activate') is True for r in rows)
    counts = Counter(str(r.get('donor_return_line')) for r in rows if r.get('would_activate') is False)
    return {
        'complete': complete, 'callbacks': len(rows), 'would_activate': activations,
        'off_identity_checks': sum(r.get('off_identity') is True for r in rows),
        'input_unchanged_checks': sum(r.get('input_unchanged') is True for r in rows),
        'eligible_eod_callbacks': sum(type(s) is int and 0 <= s <= 695 and s % 24 == 23 for s in steps),
        'skip_return_lines': dict(sorted(counts.items())),
        'verdict': ('INCOMPLETE' if not complete else
                    'ENGAGED_REQUIRES_PAIRED_ECONOMICS' if activations else 'ZERO_ON_THIS_PANEL_ONLY'),
    }

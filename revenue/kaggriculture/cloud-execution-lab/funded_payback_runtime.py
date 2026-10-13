# SPDX-License-Identifier: Apache-2.0
"""Canonical-route adapter for ECON's attributed payback admission.

The official engine treats recognized zero-quantity market rows as no-ops while
retaining their queue slots. Historical Arlene routes contain those placeholders.
ECON deliberately rejects malformed inputs, so this adapter translates only that
known engine no-op shape to PASS for prospective evaluation. The executed route
and the peer-owned ECON implementation remain unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import math
import time


_POST_ADMISSION_SECONDS = 0.30


_QUANTITY_ORDERS = frozenset(
    ('BUY_SEED', 'BUY_PRODUCT', 'BUY_ANIMAL', 'SELL')
)


def _engine_noop(order):
    if not isinstance(order, list) or len(order) < 3 or order[0] not in _QUANTITY_ORDERS:
        return False
    try:
        return int(order[2]) <= 0
    except (TypeError, ValueError):
        return False


def _evaluation_row(row):
    market = row.get('market', [])
    if not isinstance(market, list):
        return row
    result = None
    for slot, order in enumerate(market):
        if not _engine_noop(order):
            continue
        if result is None:
            result = deepcopy(row)
        result['market'][slot] = ['PASS']
    return row if result is None else result


def _evaluation_route(route):
    """Translate engine no-ops without rebuilding clean canonical routes."""
    result = None
    for index, row in enumerate(route):
        evaluation = _evaluation_row(row)
        if evaluation is row:
            continue
        if result is None:
            result = list(route)
        result[index] = evaluation
    if result is not None:
        return result
    # Historical callers receive a list for arbitrary Sequence inputs. Preserve
    # that contract while keeping the overwhelmingly common canonical list hot
    # path allocation-free when no translation is needed.
    return route if isinstance(route, list) else list(route)


def _evaluation_routes(routes):
    """Translate only changed routes; preserve the canonical plain-dict hot path."""
    result = None
    for key, route in routes.items():
        evaluation = _evaluation_route(route)
        if evaluation is route:
            continue
        if result is None:
            result = dict(routes)
        result[key] = evaluation
    if result is not None:
        return result
    # The previous mapping comprehension always materialized arbitrary Mapping
    # inputs as a plain dict. Preserve that contract outside the canonical dict.
    return routes if type(routes) is dict else dict(routes)


def make_admission(base_class):
    """Bind the adapter to the exact packaged ECON class without forking it."""
    class RuntimeFundedPaybackAdmission(base_class):
        _action_deadline = None

        def begin_action(self, deadline):
            deadline = float(deadline)
            if not math.isfinite(deadline):
                raise ValueError('action deadline must be finite')
            self._action_deadline = deadline

        @staticmethod
        def _candidate(base, variant, now):
            candidate, inferred = base_class._candidate(base, variant, now)
            candidate = _evaluation_route(candidate)
            bundle = variant.get('bundle', {})
            rejoin = bundle.get('rejoin_step', inferred) if isinstance(bundle, dict) else inferred
            if isinstance(rejoin, bool) or not isinstance(rejoin, int):
                raise ValueError('proposal rejoin step must be an integer')
            if not now < rejoin <= len(candidate) or rejoin < inferred:
                raise ValueError('proposal rejoin step lies outside its physical route tail')
            return candidate, rejoin

        def __call__(self, mechanics, observation, configuration, routes, proposals):
            evaluation_routes = _evaluation_routes(routes)
            configured_seconds = self.seconds
            action_deadline = self._action_deadline
            try:
                if action_deadline is not None:
                    self.seconds = min(
                        configured_seconds,
                        max(0.0, action_deadline-time.monotonic()-_POST_ADMISSION_SECONDS))
                return super().__call__(mechanics, observation, configuration,
                                        evaluation_routes, proposals)
            finally:
                self.seconds = configured_seconds
                self._action_deadline = None

    RuntimeFundedPaybackAdmission.__name__ = 'RuntimeFundedPaybackAdmission'
    RuntimeFundedPaybackAdmission.__qualname__ = 'RuntimeFundedPaybackAdmission'
    return RuntimeFundedPaybackAdmission

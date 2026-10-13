# SPDX-License-Identifier: Apache-2.0
"""Optional binding to an injected certificate consumer, not another checker."""
from copy import deepcopy
from collections.abc import Mapping


class CheckedProvider:
    """Keep provider output and checker facts distinct; use one per actor.

    The checker is TRIAD's check_certificate(rows, result) or a compatible
    callable. It alone checks the certificate. This binding calls both inputs
    once and returns a detached unchanged result only when valid, completed,
    and positive_optimum are all exactly True. Other outcomes return None to
    the existing selector's complete-fallback/no-draw path.
    """
    def __init__(self, provider, checker):
        if not callable(provider) or not callable(checker):
            raise TypeError('provider and checker must be callable')
        self.provider, self.checker = provider, checker
        self.calls = 0
        self.last_check = None

    def __call__(self, rows):
        self.calls += 1
        self.last_check = None
        try:
            frozen_rows = tuple(tuple(row) for row in rows)
            result = deepcopy(self.provider(frozen_rows))
            verdict = self.checker(frozen_rows, deepcopy(result))
            if not isinstance(verdict, Mapping):
                self.last_check = {'valid': False, 'reason': 'checker_result_unavailable'}
                return None
            self.last_check = deepcopy(dict(verdict))
            if all(verdict.get(k) is True for k in ('valid', 'completed', 'positive_optimum')):
                return result
            return None
        except Exception:
            self.last_check = {'valid': False, 'reason': 'provider_or_checker_unavailable'}
            return None


def checked_provider(provider, checker):
    """Return a callable binding with the checker verdict at .last_check."""
    return CheckedProvider(provider, checker)

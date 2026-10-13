"""Opt-in scientific thread limits at actor launch, without changing evaluator code.

Install on one independently loaded evaluator module in a per-game driver.
Only explicitly selected worker specifications receive the six limits. The
original sanitized environment, protocol, timers, arguments and cleanup remain.
No parent environment or credentials are copied into a worker.
"""
from __future__ import annotations
from collections.abc import Iterable, Mapping
from types import ModuleType
from typing import Any

THREAD_LIMITS: dict[str, str] = {
    'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
    'MKL_NUM_THREADS': '1', 'BLIS_NUM_THREADS': '1',
    'NUMEXPR_NUM_THREADS': '1', 'VECLIB_MAXIMUM_THREADS': '1',
}

class ScientificEnvironment:
    """Local subprocess facade; does not monkey-patch the subprocess module."""
    def __init__(self, original: Any, allowed_specs: Iterable[str]):
        self._original = original
        self.allowed_specs = frozenset(allowed_specs)
        if not self.allowed_specs or any(not isinstance(x, str) or not x for x in self.allowed_specs):
            raise ValueError('At least one exact nonempty worker specification is required')
        self.launches: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)

    def Popen(self, args: Any, *positional: Any, **kwargs: Any) -> Any:
        selected = False
        spec = None
        if isinstance(args, (list, tuple)) and '--worker' in args:
            index = args.index('--worker')
            if index + 1 < len(args):
                spec = args[index + 1]
                selected = spec in self.allowed_specs
        if selected:
            environment = kwargs.get('env')
            if not isinstance(environment, Mapping):
                raise ValueError('Selected actor must already provide a sanitized environment')
            kwargs = dict(kwargs)
            kwargs['env'] = {**environment, **THREAD_LIMITS}
        process = self._original.Popen(args, *positional, **kwargs)
        self.launches.append({'worker_spec': spec, 'limits_applied': selected,
                              'pid': getattr(process, 'pid', None),
                              'thread_limits': dict(THREAD_LIMITS) if selected else {}})
        return process

def install(evaluator: ModuleType, allowed_specs: Iterable[str]) -> ScientificEnvironment:
    """Return launch evidence; callers keep the evaluator source hash unchanged."""
    if isinstance(evaluator.subprocess, ScientificEnvironment):
        raise ValueError('Scientific environment is already installed on this evaluator')
    proxy = ScientificEnvironment(evaluator.subprocess, allowed_specs)
    evaluator.subprocess = proxy
    return proxy

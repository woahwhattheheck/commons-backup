# SPDX-License-Identifier: Apache-2.0
"""Opt-in native sale-window experiment wiring; not a sale policy.

The existing main._new_instance constructs the only producer/runtime. A market-
only callback runs inside native finalization, after final pressure and before
receipt owners commit. The outer observer never changes the returned action.
Source custody and economic acceptance belong to the paired runner, not here.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
from types import MethodType
from typing import Callable

MAIN_SHA256 = 'c4c22d0f2b1071cadf6a9f74effccc8cb20ea9f4d10ca1cf9f1fe57351709dc1'
FINALIZER_SHA256 = 'f9b82a6c2574822a9db31aef4fd91d85950af75fd1d656a153bac53788f57f37'
SAFE_PRODUCTS = frozenset(('WOOL', 'MILK', 'STRAWBERRY', 'MELON'))


def digest(value) -> str:
    """Canonical JSON identity, not a claim about transport-byte formatting."""
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method_sha(path: Path, cls: str, name: str) -> str:
    text = path.read_text()
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == cls)
    method = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == name)
    span = ''.join(text.splitlines(keepends=True)[method.lineno - 1:method.end_lineno])
    return hashlib.sha256(span.encode()).hexdigest()


def verify_native(module) -> dict:
    """Pin main and the receipt-bearing finalizer, leaving unrelated methods alone."""
    root = Path(module.__file__).resolve().parent
    main_path, runtime_path = root / 'main.py', root / 'titan_runtime.py'
    if Path(module.__file__).resolve() != main_path:
        raise ValueError('Expected the native main.py, not a replacement entrypoint')
    actual = {'main_sha256': _sha(main_path),
              'finalizer_sha256': _method_sha(runtime_path, 'TitanAgent', '_finish_production')}
    if actual['main_sha256'] != MAIN_SHA256 or actual['finalizer_sha256'] != FINALIZER_SHA256:
        raise ValueError('Native source binding changed; revalidate this seam before use')
    if getattr(module, '_INSTANCE', None) is not None:
        raise ValueError('Bind before the first native action, not during an episode')
    return actual


def _target(row, products) -> bool:
    return (isinstance(row, list) and len(row) == 3 and row[0] == 'SELL'
            and row[1] in products and type(row[2]) is int and row[2] >= 0)


def validate_market_only(original: dict, proposed: dict, cfg: dict, products) -> None:
    """Preserve units, funding prefix, other goods, raw slots and clipped suffix.

    This is an action-shape/ownership gate, NOT a profit or physical-fill gate.
    Requested quantities can exceed stock exactly as normal native SELL rows do.
    """
    if not isinstance(proposed, dict) or not isinstance(original, dict):
        raise ValueError('Callback must return an action dictionary')
    if {k: v for k, v in original.items() if k != 'market'} != {
            k: v for k, v in proposed.items() if k != 'market'}:
        raise ValueError('Non-market action fields changed')
    before, after = original.get('market', []), proposed.get('market', [])
    if not isinstance(before, list) or not isinstance(after, list):
        raise ValueError('Market must remain a raw list')
    cap = cfg.get('maxMarketOrdersPerTurn', 10)
    if type(cap) is not int:
        raise ValueError('Invalid raw market cap')
    cap = max(1, cap)  # Official interpreter floors the live queue cap at one.
    if len(after) < len(before) or len(after) > max(len(before), cap):
        raise ValueError('Do not remove raw slots or append beyond the live cap')
    if before[cap:] != after[cap:]:
        raise ValueError('Clipped raw suffix changed')
    # Even a malformed/unknown economic row remains an immovable boundary.
    barrier = max((i for i, row in enumerate(before[:cap]) if row and
                   (not isinstance(row, list) or row[0] != 'SELL')), default=-1)
    if before[:barrier + 1] != after[:barrier + 1]:
        raise ValueError('Inherited economic/funding prefix changed')
    for index in range(barrier + 1, min(len(after), cap)):
        old = before[index] if index < len(before) else []
        new = after[index]
        if new == old:
            continue
        if old != [] and not _target(old, products):
            raise ValueError('Non-target raw row changed')
        if new != [] and not _target(new, products):
            raise ValueError('Only nonnegative integer target SELL rows are allowed')
    digest(proposed)  # Reject non-JSON/nonfinite proposals before publishing one.


class NativeSaleWindow:
    """One opt-in callback plus per-call exposure/acceptance/return evidence.

    policy(observation, configuration, selected_action) -> action dictionary.
    All three inputs are detached. A policy source file is hashed here, not an
    unauthenticated hash label. Do not modify that file during an experiment.
    Ordinary callback/shape failures retain the exact incumbent object and are
    recorded as errors. BaseException (including native deadlines) propagates.
    This adapter and native main are serial/non-reentrant.
    """
    def __init__(self, module, policy: Callable | None = None, *, enabled=False,
                 products=('STRAWBERRY', 'MELON'), label='sale-window-experiment'):
        self.module, self.enabled, self.policy = module, enabled, policy
        self.products = frozenset(products)
        self.rows = []
        self._active = None
        self._original_factory = None
        self._factory = None
        self.native_binding = None
        self.policy_binding = None
        self._native_agent = module.agent
        if type(enabled) is not bool:
            raise TypeError('enabled must be an explicit bool')
        if not enabled:
            self.agent = module.agent  # Disabled path is literally native callable.
            return
        if not callable(policy) or not self.products or not self.products <= SAFE_PRODUCTS:
            raise ValueError('Enabled experiment needs a callable and safe target products')
        self.native_binding = verify_native(module)
        source = inspect.getsourcefile(policy)
        if source is None or not Path(source).is_file():
            raise ValueError('A durable policy source file is required')
        self.policy_binding = {'label': str(label), 'source_sha256': _sha(Path(source)),
                               'entrypoint': policy.__qualname__, 'products': sorted(self.products)}
        if getattr(module, '_sale_window_bound', False):
            raise ValueError('One sale-window binding per native module')
        self._original_factory = module._new_instance
        original_factory = self._original_factory

        def factory(root, feature_data):
            instance = original_factory(root, feature_data)
            finish = instance._finish_production
            expected_runtime = Path(module.__file__).resolve().parent / 'titan_runtime.py'
            if Path(inspect.getsourcefile(finish)).resolve() != expected_runtime:
                raise ValueError('Receipt finalizer has been replaced; do not stack blindly')
            original = instance._early_capital_selected

            def boundary(agent_self, obs, cfg, selected):
                incumbent = original(obs, cfg, selected)
                if agent_self.diagnostics.get('status') != 'completed':
                    return incumbent
                return self._propose(obs, cfg, incumbent)

            instance._early_capital_selected = MethodType(boundary, instance)
            return instance

        self._factory = factory
        module._new_instance = factory
        module._sale_window_bound = True
        self.agent = self._act

    def _propose(self, obs, cfg, incumbent):
        frame = self._active
        if frame is None:
            raise RuntimeError('Use the experiment.agent observer, not native.agent directly')
        frame['callbacks'] += 1
        if frame['callbacks'] != 1:
            raise RuntimeError('Repeated finalization callback in one native call')
        cap = max(1, cfg.get('maxMarketOrdersPerTurn', 10))
        frame['incumbent_sha256'] = digest(incumbent)
        frame['_incumbent'] = deepcopy(incumbent)
        # Publish neither caller-owned input nor callback-owned output objects.
        try:
            proposed = self.policy(deepcopy(obs), deepcopy(cfg), deepcopy(incumbent))
            frame['proposal_returned'] = True
            validate_market_only(incumbent, proposed, cfg, self.products)
            result = deepcopy(proposed)
            frame['accepted'] = True
            frame['action_changed'] = result != incumbent
            frame['accepted_prefix_changed'] = result.get('market', [])[:cap] != incumbent.get('market', [])[:cap]
            frame['proposed_sha256'] = digest(result)
            frame['_proposed'] = result
            return deepcopy(result) if result != incumbent else incumbent
        except Exception as error:
            frame['error'] = type(error).__name__ + ': ' + str(error)[:300]
            return incumbent

    def _act(self, obs, cfg=None):
        if self._active is not None:
            raise RuntimeError('Native sale-window experiments are non-reentrant')
        config = dict(cfg or {})
        step = obs.get('step')
        if step is None:
            step = int(obs['day']) * int(config.get('turnsPerDay', 24)) + int(obs['hour'])
        frame = {'call': len(self.rows), 'step': int(step), 'player': int(obs['player']),
                 'callbacks': 0, 'proposal_returned': False, 'accepted': False,
                 'action_changed': False, 'accepted_prefix_changed': False,
                 'returned': False, 'returned_matches_proposal': False,
                 'returned_prefix_changed': False, 'error': None,
                 'fills': None, 'economic_verdict': 'not_measured'}
        self._active = frame
        try:
            returned = self._native_agent(obs, cfg)
            frame['returned'] = True
            frame['returned_sha256'] = digest(returned)
            if '_proposed' in frame:
                frame['returned_matches_proposal'] = returned == frame['_proposed']
            if '_incumbent' in frame:
                cap = max(1, config.get('maxMarketOrdersPerTurn', 10))
                frame['returned_prefix_changed'] = (returned.get('market', [])[:cap] !=
                                                    frame['_incumbent'].get('market', [])[:cap])
            instance = getattr(self.module, '_INSTANCE', None)
            diagnostics = getattr(instance, 'diagnostics', {}) or {}
            frame['native_status'] = diagnostics.get('status', 'instance_absent')
            frame['fallback_stage'] = diagnostics.get('fallback_stage')
            return returned  # Observation only: exact native return object.
        except BaseException as error:
            frame['raised'] = type(error).__name__
            raise
        finally:
            frame.pop('_incumbent', None)
            frame.pop('_proposed', None)
            self.rows.append(frame)
            self._active = None

    def close(self):
        """Remove our factory only while it is still ours; never erase peer edits."""
        if self._active is not None:
            raise RuntimeError('Cannot unbind during a native call')
        if not self.enabled:
            return
        if self.module._new_instance is not self._factory:
            raise RuntimeError('Factory changed since binding; refusing to overwrite it')
        if getattr(self.module, '_INSTANCE', None) is not None:
            raise RuntimeError('Finish the isolated experiment before discarding its instance')
        self.module._new_instance = self._original_factory
        del self.module._sale_window_bound

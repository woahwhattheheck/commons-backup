# SPDX-License-Identifier: Apache-2.0
"""Independent lifetime/interruption gate for WEAVE's exact optimizer stack.

No composition, runtime installation, network, archive edit or policy change.
The caller supplies WEAVE's generated selected_sell_core.py. Baseline, candidate,
mechanics and receipt sources are authenticated before any of them executes.
Synthetic interruption probes raise inside real score/capacity callbacks. They
are NOT OS-timer, full-game or playing-strength evidence. Constructor-time
interruption before the third cache installation retains a cycle until cyclic
GC in BOTH sources. One test characterizes, and does not claim to fix, that gap.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import gc
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
import weakref
from collections import Counter

BASE_GIT = 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3'
CANDIDATE_GIT = '16dde00627effa5d0ae4d73a8e05a295e9534e1f'
CANDIDATE_SHA256 = '6bd91f5b8132df2c10b127f69e3dc43c4b9b9fbf32b38860ce1c7517d1575256'
DEPENDENCIES = {
    'selected_sell_core.py': BASE_GIT,
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'reference/decision/decision.py': '2931aa55831204fbb473ab85a6f5b81ec947fcf7',
}
RULES = ('strict', 'expected_downside', 'minimax_regret')
STATS = Counter()
BRANCHES = Counter()
SOURCE = {}
RUNTIME = None
MUTANT = None


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('mutation anchor is not unique')
    return text.replace(old, new, 1)


def mutate(source: str, name: str | None) -> str:
    if name is None:
        return source
    if name == 'unreleased_owner':
        return replace_once(source, '        del model.single, model.joint\n', '        pass  # broken: bound wrappers still retain their owner\n')
    if name == 'uncleared_quote':
        return replace_once(source, '        model.quote.cache_clear()\n', '        pass  # broken: retained quote entries during unwind\n')
    if name == 'shared_receipts':
        source = replace_once(source, "cache = getattr(self, '_receipt_prefixes', None)", "cache = getattr(type(self), '_receipt_prefixes', None)")
        return replace_once(source, 'cache = self._receipt_prefixes = {}', 'cache = type(self)._receipt_prefixes = {}')
    if name == 'stale_calendar':
        return replace_once(source, "if getattr(self, '_eventpath_context', None) != context:", "if not hasattr(self, '_eventpath_prefix'):")
    if name == 'swallowed_deadline':
        return replace_once(source, '    finally:\n        # CACHELIFE:', '    except BaseException:\n        return None\n    finally:\n        # CACHELIFE:')
    raise ValueError('unknown mutant: ' + name)


MUTANT_TESTS = {
    'unreleased_owner': ('test_success_reclaims_without_cyclic_gc',),
    'uncleared_quote': ('test_all_score_interruption_boundaries',),
    'shared_receipts': ('test_interleaved_private_owners',),
    'stale_calendar': ('test_live_calendar_invalidation',),
    'swallowed_deadline': ('test_all_score_interruption_boundaries',),
}


def load_core(which: str):
    """Fresh real module/class per test, sharing only pinned pure mechanics."""
    mod = types.ModuleType('_canopy_' + which)
    mod.__file__ = str(RUNTIME / 'selected_sell_core.py')
    text = SOURCE[which]
    if which == 'candidate':
        text = mutate(text, MUTANT)
    exec(compile(text, mod.__file__, 'exec'), mod.__dict__)
    return mod


@contextlib.contextmanager
def no_cyclic_gc():
    was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        gc.collect()
        if was_enabled:
            gc.enable()


def arguments(rule='strict', *, quantity=4, now=241, horizon=8, item='WOOL', inventory=10000):
    end = now + horizon
    dates = sorted({now, min(now + 1, end), end})
    return dict(item=item, quantity=quantity, inventory=inventory, params=None,
                shops=['YARN_STORE'] * 4 + ['FARMERS_MARKET', 'SMOOTHIE_SHOP'],
                config={'sellAcceptanceRule': rule, 'sellDownsideBound': 200.0},
                now=now, dates=dates, reference=((now, quantity),),
                rival_quantity=max(0, quantity - 1), minimum_now=0, last=718)


def capacity_predicate(plan, mode, reference, now):
    if mode == 'none':
        return False
    if mode == 'exclude_reference':
        return tuple(plan) != tuple(reference)
    if mode == 'parity':
        return dict(plan).get(now, 0) % 2 == 0
    return True


def run_with_trace(module, args, mode='all'):
    trace = []
    def capacity(plan):
        trace.append(tuple(plan))
        return capacity_predicate(plan, mode, args['reference'], args['now'])
    result = module.optimize_lot(**copy.deepcopy(args), capacity_ok=capacity)
    return result, trace


class DeadlineProbe(BaseException):
    """Synthetic public-boundary interruption, deliberately not Exception."""


def cleanup_snapshot(owner):
    return {'quote_entries': owner.quote.cache_info().currsize,
            'single_bound': 'single' in vars(owner),
            'joint_bound': 'joint' in vars(owner)}


def tracked_run(module, args, *, stage=None, at=None, exception=DeadlineProbe):
    """Run actual optimizer, retaining only weak references and primitive data.

    The traceback keeps the optimizer frame/model alive inside the except block.
    Inspect cleanup there, then test reclamation after Python releases it. Never
    retain the exception, traceback, owner or bound methods in the return value.
    """
    original = module.MarketPath
    refs = []
    counts = Counter()
    class ObservedPath(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            refs.append(weakref.ref(self))
        def score(self, *a, **kw):
            value = super().score(*a, **kw)
            counts['score'] += 1
            if stage == 'score' and counts['score'] == at:
                raise exception('CANOPY injected at score:' + str(at))
            return value
    def capacity(plan):
        counts['capacity'] += 1
        if stage == 'capacity' and counts['capacity'] == at:
            raise exception('CANOPY injected at capacity:' + str(at))
        return True
    module.MarketPath = ObservedPath
    outcome = {'raised': False, 'cleanup': [], 'result': None}
    try:
        try:
            outcome['result'] = module.optimize_lot(**copy.deepcopy(args), capacity_ok=capacity)
        except exception as caught:
            outcome['raised'] = True
            outcome['exception_type'] = type(caught).__name__
            outcome['message'] = str(caught)
            outcome['cleanup'] = [cleanup_snapshot(ref()) for ref in refs if ref() is not None]
            # No traceback clearing: test natural release when except scope ends.
        outcome['alive_after_unwind'] = sum(ref() is not None for ref in refs)
    finally:
        module.MarketPath = original
    outcome['counts'] = dict(counts)
    outcome['refs'] = refs
    return outcome


class StackLifetime(unittest.TestCase):
    def setUp(self):
        self.base = load_core('baseline')
        self.candidate = load_core('candidate')

    def assert_released(self, result):
        self.assertEqual(result['alive_after_unwind'], 0, 'private model survives with cyclic GC disabled')
        self.assertTrue(result['refs'], 'probe did not construct a real model')
        self.assertTrue(all(ref() is None for ref in result['refs']))

    def assert_interrupted(self, result, stage, at, exception=DeadlineProbe):
        self.assertTrue(result['raised'], 'interruption was swallowed or site never reached')
        self.assertIsNone(result['result'])
        self.assertEqual(result['exception_type'], exception.__name__)
        self.assertEqual(result['message'], 'CANOPY injected at ' + stage + ':' + str(at))
        self.assertEqual(result['counts'][stage], at)
        self.assertEqual(result['cleanup'], [{'quote_entries': 0, 'single_bound': False, 'joint_bound': False}])
        self.assert_released(result)

    def test_optimizer_result_and_capacity_order_matrix(self):
        # Whole output/diagnostic tuple plus the exact external callback sequence.
        for item in ('WHEAT', 'STRAWBERRY', 'WOOL', 'FERTILIZER'):
            for rule in RULES:
                for horizon in (0, 1, 3, 8, 24):
                    for inventory in (9990, 20000):
                        for mode in ('all', 'exclude_reference', 'none'):
                            args = arguments(rule, item=item, inventory=inventory, horizon=horizon)
                            before = copy.deepcopy(args)
                            expected = run_with_trace(self.base, args, mode)
                            actual = run_with_trace(self.candidate, args, mode)
                            with self.subTest(item=item, rule=rule, horizon=horizon, inventory=inventory, mode=mode):
                                self.assertEqual(actual, expected)
                                self.assertEqual(args, before)
                            STATS['optimizer_pairs'] += 1
                            STATS['capacity_callback_entries_compared'] += len(expected[1])
                            info = actual[0][1]
                            BRANCHES[rule + ':accepted=' + str(info['accepted'])] += 1
                            BRANCHES['forced=' + str(info['forced_feasibility'])] += 1
                            BRANCHES['feasible=' + str(info['feasible'])] += 1
        for rule in RULES:
            self.assertGreater(BRANCHES[rule + ':accepted=True'], 0, rule + ' never accepted a real plan')
        self.assertGreater(BRANCHES['forced=True'], 0)
        self.assertGreater(BRANCHES['feasible=False'], 0)

    def test_zero_minimum_terminal_and_weighted_controls(self):
        for rule in RULES:
            for quantity in (0, 1, 7, 12):
                for now, horizon in ((0, 8), (717, 1), (718, 0)):
                    args = arguments(rule, quantity=quantity, now=now, horizon=horizon, item='MILK')
                    args['config']['sellScenarioWeights'] = {'no_rival': 0.1, 'observed_paired': 3.0, 'observed_next_turn': 0.5}
                    args['minimum_now'] = min(3, quantity)
                    args['reference'] = ((now + horizon, quantity),)
                    expected = run_with_trace(self.base, args, 'parity')
                    actual = run_with_trace(self.candidate, args, 'parity')
                    with self.subTest(rule=rule, quantity=quantity, now=now):
                        self.assertEqual(actual, expected)
                    STATS['boundary_optimizer_pairs'] += 1
                    STATS['capacity_callback_entries_compared'] += len(expected[1])

    def test_baseline_cycle_positive_control(self):
        with no_cyclic_gc():
            result = tracked_run(self.base, arguments())
            self.assertFalse(result['raised'])
            self.assertEqual(result['alive_after_unwind'], 1, 'baseline no longer distinguishes lifetime regression')
            gc.collect()
            self.assertTrue(all(ref() is None for ref in result['refs']), 'probe itself retains the owner')
            STATS['baseline_cycle_controls'] += 1

    def test_constructor_cancellation_characterization(self):
        # The donor's finally begins AFTER MarketPath(...) completes. This is an
        # explicit known-gap characterization, not a no-leak assertion.
        for which in ('baseline', 'candidate'):
            observed_liveness = []
            for trip in (1, 2, 3):
                module = load_core(which)
                original_cache, original_path = module.lru_cache, module.MarketPath
                refs, calls = [], []
                class ObservedPath(original_path):
                    def __init__(self, *a, **kw):
                        refs.append(weakref.ref(self))
                        super().__init__(*a, **kw)
                def interrupted_cache(*a, **kw):
                    decorator = original_cache(*a, **kw)
                    def install(function):
                        calls.append(1)
                        if len(calls) == trip:
                            raise DeadlineProbe('constructor:' + str(trip))
                        return decorator(function)
                    return install
                module.MarketPath, module.lru_cache = ObservedPath, interrupted_cache
                raised = False
                with no_cyclic_gc():
                    try:
                        module.optimize_lot(**arguments())
                    except DeadlineProbe as caught:
                        raised = True
                        self.assertEqual(str(caught), 'constructor:' + str(trip))
                    self.assertTrue(raised)
                    self.assertEqual(len(calls), trip)
                    observed_liveness.append(sum(ref() is not None for ref in refs))
                    gc.collect()
                    self.assertTrue(all(ref() is None for ref in refs), 'probe itself retains constructor owner')
                STATS['constructor_characterization_cases'] += 1
            self.assertEqual(observed_liveness, [0, 0, 1], 'known constructor behavior changed; reclassify this boundary')

    def test_success_reclaims_without_cyclic_gc(self):
        with no_cyclic_gc():
            for rule in RULES:
                for i in range(12):
                    args = arguments(rule, quantity=i % 7, horizon=(0, 1, 8, 24)[i % 4], item=('WOOL', 'MILK')[i % 2])
                    result = tracked_run(self.candidate, args)
                    self.assertFalse(result['raised'])
                    self.assertIsInstance(result['result'], tuple)
                    self.assert_released(result)
                    STATS['normal_reclamation_calls'] += 1

    def test_all_score_interruption_boundaries(self):
        with no_cyclic_gc():
            for rule in RULES:
                args = arguments(rule, quantity=2, horizon=8)
                count = tracked_run(self.candidate, args)['counts']['score']
                self.assertGreater(count, 5, 'must cover more than reference scenario construction')
                for at in range(1, count + 1):
                    with self.subTest(rule=rule, at=at):
                        result = tracked_run(self.candidate, args, stage='score', at=at)
                        self.assert_interrupted(result, 'score', at)
                    STATS['score_interruption_sites'] += 1

    def test_all_capacity_interruption_boundaries(self):
        with no_cyclic_gc():
            for rule in RULES:
                args = arguments(rule, quantity=2, horizon=8)
                count = tracked_run(self.candidate, args)['counts']['capacity']
                self.assertGreater(count, 1, 'must cover more than the reference capacity callback')
                for at in range(1, count + 1):
                    with self.subTest(rule=rule, at=at):
                        result = tracked_run(self.candidate, args, stage='capacity', at=at)
                        self.assert_interrupted(result, 'capacity', at)
                    STATS['capacity_interruption_sites'] += 1

    def test_exception_types_and_recovery(self):
        with no_cyclic_gc():
            for error in (RuntimeError, KeyboardInterrupt, DeadlineProbe):
                for stage in ('score', 'capacity'):
                    args = arguments('expected_downside', quantity=3)
                    result = tracked_run(self.candidate, args, stage=stage, at=1, exception=error)
                    self.assert_interrupted(result, stage, 1, error)
                    actual = run_with_trace(self.candidate, args)
                    expected = run_with_trace(self.base, args)
                    self.assertEqual(actual, expected, 'interrupted call contaminated the next optimizer')
                    STATS['exception_type_and_recovery_pairs'] += 1

    def test_capacity_reentrancy_does_not_destroy_another_owner(self):
        # While outer optimize_lot is suspended in its capacity callback, execute
        # a real inner optimizer. Its finally must not clean the outer model.
        outer_args = arguments('minimax_regret', item='WOOL', quantity=4)
        inner_args = arguments('expected_downside', item='MILK', quantity=3, horizon=24)
        expected = run_with_trace(self.base, outer_args)
        expected_inner = run_with_trace(self.base, inner_args)[0]
        refs, inner_results, outer_trace = [], [], []
        original = self.candidate.MarketPath
        class ObservedPath(original):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                refs.append(weakref.ref(self))
        def capacity(plan):
            outer_trace.append(tuple(plan))
            if len(outer_trace) == 1:
                inner_results.append(self.candidate.optimize_lot(**copy.deepcopy(inner_args), capacity_ok=lambda p: True))
                self.assertEqual(len(refs), 2)
                self.assertIsNotNone(refs[0]())
                self.assertIsNone(refs[1]())
                self.assertIn('single', vars(refs[0]()))
                self.assertIn('joint', vars(refs[0]()))
                self.assertGreater(refs[0]().quote.cache_info().currsize, 0)
            return True
        with no_cyclic_gc():
            self.candidate.MarketPath = ObservedPath
            try:
                actual = self.candidate.optimize_lot(**copy.deepcopy(outer_args), capacity_ok=capacity)
            finally:
                self.candidate.MarketPath = original
            self.assertEqual((actual, outer_trace), expected)
            self.assertEqual(inner_results, [expected_inner])
            self.assertTrue(all(ref() is None for ref in refs))
        STATS['reentrant_optimizer_pairs'] += 2

    def test_interleaved_private_owners(self):
        pairs = []
        for item in ('WHEAT', 'WOOL', 'MILK', 'FERTILIZER'):
            args = (item, 10000, None, ['YARN_STORE', 'FARMERS_MARKET'], {}, 241, 265)
            pairs.append((self.base.MarketPath(*args), self.candidate.MarketPath(*args)))
        for i in range(25):
            for base, cand in (pairs if i % 2 else list(reversed(pairs))):
                inv = 9990 + i % 3
                self.assertEqual(cand.single(inv, 10), base.single(inv, 10))
                self.assertEqual(cand.joint(inv, 7, 9, 'paired'), base.joint(inv, 7, 9, 'paired'))
                plan = ((241, 2), (249, 5), (265, 3))
                self.assertEqual(cand.score(plan, 10, ((242, 7),), 'after'), base.score(plan, 10, ((242, 7),), 'after'))
                STATS['interleaved_owner_comparisons'] += 3
        caches = [p[1]._receipt_prefixes for p in pairs]
        self.assertEqual(len({id(cache) for cache in caches}), len(pairs))
        # Retaining an independent public model while optimizing must leave its
        # existing caches and callable wrappers alone.
        public = pairs[0][1]
        before = (public.single.cache_info(), copy.deepcopy(public._receipt_prefixes))
        self.candidate.optimize_lot(**arguments(item='WOOL'))
        self.assertEqual((public.single.cache_info(), public._receipt_prefixes), before)

    def test_live_calendar_invalidation(self):
        b = self.base.MarketPath('WOOL', 10000, None, ['YARN_STORE'] * 4, {}, 241, 265)
        c = self.candidate.MarketPath('WOOL', 10000, None, ['YARN_STORE'] * 4, {}, 241, 265)
        previous = None
        changes = 0
        for i in range(12):
            shops = ['YARN_STORE'] * (i % 4 + 1)
            config = {'townShopSellInterval': (1, 4, 7)[i % 3], 'townCenterSellInterval': (24, 5)[i % 2]}
            for owner in (b, c):
                owner.shops[:] = shops
                owner.config.clear(); owner.config.update(config)
                owner.now = 241 + (i // 6) % 2
                owner.end = 265 + (i // 6) % 3
            plan = ((b.now, 2), (b.end, 8))
            expected = b.score(plan, 10, ((b.now + 1, 7),), 'paired')
            self.assertEqual(c.score(plan, 10, ((c.now + 1, 7),), 'paired'), expected)
            if previous is not None and expected != previous:
                changes += 1
            previous = expected
            STATS['live_calendar_comparisons'] += 1
        self.assertGreater(changes, 0, 'calendar invalidation fixture is inert')

    def test_receipt_cache_bounds_and_eviction(self):
        b = self.base.MarketPath('MILK', 10000, None, [], {}, 0, 24)
        c = self.candidate.MarketPath('MILK', 10000, None, [], {}, 0, 24)
        for i in range(100):
            for alignment in ('before', 'paired', 'after'):
                actual = c.joint(9800 + i, 100, i % 101, alignment)
                self.assertEqual(actual, b.joint(9800 + i, 100, i % 101, alignment))
                self.assertLessEqual(len(c._receipt_prefixes), 64)
                self.assertTrue(all(len(rows) <= 101 for rows in c._receipt_prefixes.values()))
                STATS['bounded_receipt_comparisons'] += 1
        self.assertEqual(len(c._receipt_prefixes), 64)
        self.assertEqual(c.single(9800, 100), b.single(9800, 100))

    def test_native_domain_fallback_and_rounding(self):
        for item in ('WHEAT', 'STRAWBERRY', 'FERTILIZER'):
            for inventory in (10000, 20000, 2 ** 52 + 1):
                b = self.base.MarketPath(item, inventory, None, [], {}, 1, 9)
                c = self.candidate.MarketPath(item, inventory, None, [], {}, 1, 9)
                for quantity in (0, 1, 100, 101):
                    self.assertEqual(c.single(inventory, quantity), b.single(inventory, quantity))
                    for alignment in ('paired', 'before', 'after'):
                        self.assertEqual(c.joint(inventory, quantity, 3, alignment), b.joint(inventory, quantity, 3, alignment))
                        STATS['fallback_and_rounding_comparisons'] += 1
        # Floating inventory bypasses the sparse eventpath while native single
        # receipt semantics and the exact original fallback remain available.
        b = self.base.MarketPath('MILK', 10000.5, None, [], {}, 1, 9)
        c = self.candidate.MarketPath('MILK', 10000.5, None, [], {}, 1, 9)
        self.assertEqual(c.score(((1, 2), (9, 3)), 5, 4, 'paired'), b.score(((1, 2), (9, 3)), 5, 4, 'paired'))
        STATS['fallback_and_rounding_comparisons'] += 1


def authenticate(runtime: Path, candidate: Path):
    global RUNTIME
    RUNTIME = runtime.resolve()
    records = {}
    for name, pin in DEPENDENCIES.items():
        data = (RUNTIME / name).read_bytes()
        actual = git_blob(data)
        if actual != pin:
            raise ValueError('dependency mismatch: ' + name + ' got ' + actual)
        records[name] = {'git_blob': actual, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        if name == 'selected_sell_core.py':
            SOURCE['baseline'] = data.decode('utf-8')
    raw = candidate.read_bytes()
    if git_blob(raw) != CANDIDATE_GIT or hashlib.sha256(raw).hexdigest() != CANDIDATE_SHA256:
        raise ValueError('candidate is not WEAVE\'s reviewed four-component postimage')
    SOURCE['candidate'] = raw.decode('utf-8')
    records['candidate'] = {'git_blob': git_blob(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    # Isolated invocation: replace mechanics with the exact authenticated module.
    mechanics = types.ModuleType('mechanics')
    mechanics.__file__ = str(RUNTIME / 'mechanics.py')
    exec(compile((RUNTIME / 'mechanics.py').read_bytes(), mechanics.__file__, 'exec'), mechanics.__dict__)
    sys.modules['mechanics'] = mechanics
    return records


def main() -> int:
    global MUTANT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--mutant', choices=tuple(MUTANT_TESTS), help='explicit broken-control mode, never a release PASS')
    parser.add_argument('--self-test-mutants', action='store_true')
    args = parser.parse_args()
    if args.mutant and args.self_test_mutants:
        parser.error('choose a single mutant or all controls, not both')
    try:
        records = authenticate(args.runtime, args.candidate)
    except (OSError, ValueError, SyntaxError) as exc:
        parser.exit(2, 'INPUT REJECTED: ' + str(exc) + '\n')
    MUTANT = args.mutant
    suite = unittest.TestLoader().loadTestsFromTestCase(StackLifetime)
    if MUTANT:
        suite = unittest.TestSuite(StackLifetime(name) for name in MUTANT_TESTS[MUTANT])
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {'schema': 'titan-v4-optimizer-stack-lifetime/v1',
              'status': 'PASS' if result.wasSuccessful() and not MUTANT else ('MUTANT_SURVIVED' if result.wasSuccessful() else 'FAIL'),
              'mutant': MUTANT, 'python': sys.version, 'optimize': sys.flags.optimize,
              'tested_sources': records,
              'checker_git_blob': git_blob(Path(__file__).read_bytes()),
              'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'counts': dict(sorted(STATS.items())), 'matrix_branch_counts': dict(sorted(BRANCHES.items())),
              'scope': 'Pinned active optimizer; synthetic score/capacity interruption, private-owner lifetime and equivalence. No runtime/game/OS-timer/EV claim.',
              'production_mutation': False,
              'known_limitations': [
                  'Constructor interruption at cache installation 3 retains one self/bound-cache cycle in both baseline and candidate until cyclic GC; explicitly characterized, not fixed.',
                  'Injected exceptions at scoring/capacity boundaries are not real OS timer/deadline integration tests.',
                  'Equivalence reference is the pinned active predecessor, not an independent official-engine oracle; no full-game, EV or production activation claim.'],
              'log': log.getvalue()}
    if args.self_test_mutants and result.wasSuccessful():
        controls = {}
        for name in MUTANT_TESTS:
            command = [sys.executable]
            if sys.flags.optimize:
                command.append('-O')
            command += [str(Path(__file__).resolve()), '--runtime', str(args.runtime.resolve()), '--candidate', str(args.candidate.resolve()), '--mutant', name]
            child = subprocess.run(command, text=True, capture_output=True, timeout=120)
            try:
                detail = json.loads(child.stdout)
            except json.JSONDecodeError:
                detail = {'failures': 0, 'errors': 1, 'log': child.stderr + child.stdout}
            killed = child.returncode == 1 and detail.get('failures', 0) > 0 and detail.get('errors') == 0 and detail.get('skipped') == 0
            controls[name] = {'killed_by_assertion': killed, 'returncode': child.returncode, 'tests_run': detail.get('tests_run'),
                              'failures': detail.get('failures'), 'errors': detail.get('errors'), 'log': detail.get('log')}
        report['mutation_controls'] = controls
        if not all(c['killed_by_assertion'] for c in controls.values()):
            report['status'] = 'FAIL_MUTATION_CONTROL'
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        # A gate must never overwrite another receipt, source or candidate.
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text)
    print(text, end='')
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

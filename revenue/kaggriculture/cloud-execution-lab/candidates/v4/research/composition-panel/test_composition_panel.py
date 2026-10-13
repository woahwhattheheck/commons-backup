# SPDX-License-Identifier: Apache-2.0
import copy
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from composition_panel import Model, SpecError, audit_plan, build_plan, canonical, main, read_json


def spec(n=4, **kwargs):
    names = [f'f{i}' for i in range(n)]
    return dict(schema_version=1, base_config={**dict.fromkeys(names, False), 'budget': 1.0},
                features=names, **kwargs)


def brute_valid(s, row):
    """Independent boolean oracle: no solver clauses/graph/covers reused."""
    names = sorted(s['features'])
    v = dict(zip(names, row))
    return (all(not v[a] or v[b] for a, b in s.get('requires', [])) and
            all(not (v[a] and v[b]) for a, b in s.get('excludes', [])) and
            all(v[k] is val for k, val in s.get('fixed', {}).items()))


def brute_rows(s):
    return [r for r in itertools.product((False, True), repeat=len(s['features']))
            if brute_valid(s, r)]


class CompositionTests(unittest.TestCase):
    def test_exact_sat_against_exhaustive_oracle(self):
        rng = random.Random(7017)
        count = 0
        for n in range(1, 7):
            for trial in range(12):
                s = spec(n)
                names = s['features']
                s['requires'] = [rng.choices(names, k=2) for _ in range(n)]
                s['excludes'] = [rng.choices(names, k=2) for _ in range(n)]
                s['fixed'] = {names[0]: False} if trial % 2 else {}
                rows, model = brute_rows(s), Model(s)
                for size in (0, 1, 2):
                    for indices in itertools.combinations(range(n), size):
                        for values in itertools.product((False, True), repeat=size):
                            pins = tuple(zip(indices, values))
                            expected = [r for r in rows if all(r[i] is v for i, v in pins)]
                            got = model.solve(pins)
                            self.assertEqual(got is not None, bool(expected))
                            if got is not None:
                                self.assertIn(got, expected)
                            count += 1
        self.assertEqual(count, 2256)

    def test_exhaustive_panel_coverage(self):
        rng = random.Random(42)
        for n in range(1, 7):
            for _ in range(4):
                s = spec(n)
                s['requires'] = [rng.choices(s['features'], k=2) for _ in range(n)]
                s['excludes'] = [rng.choices(s['features'], k=2) for _ in range(n)]
                feasible = brute_rows(s)
                p = build_plan(s)
                chosen = [tuple(c['config'][k] for k in sorted(s['features'])) for c in p['cases']]
                self.assertTrue(p['audit']['complete'])
                for r in chosen:
                    self.assertIn(r, feasible)
                for size in (1, 2):
                    for ix in itertools.combinations(range(n), size):
                        self.assertEqual({tuple(r[i] for i in ix) for r in chosen},
                                         {tuple(r[i] for i in ix) for r in feasible})

    def test_baseline_and_isolated_toggles_retained(self):
        s = spec(5)
        s['base_config']['f2'] = True
        p = build_plan(s)
        rows = [tuple(c['config'][k] for k in sorted(s['features'])) for c in p['cases']]
        baseline = (False, False, True, False, False)
        self.assertEqual(rows[0], baseline)
        for i in range(5):
            target = list(baseline)
            target[i] = not target[i]
            self.assertIn(tuple(target), rows)

    def test_requires_chain_and_mutex(self):
        s = spec(requires=[['f0', 'f1'], ['f1', 'f2']], excludes=[['f2', 'f3']])
        p = build_plan(s)
        self.assertTrue(p['audit']['complete'])
        for c in p['cases']:
            self.assertTrue(brute_valid(s, tuple(c['config'][f'f{i}'] for i in range(4))))
        self.assertIn('f0', p['audit']['blocked_isolated_toggles'])
        self.assertIn({'f0': True, 'f3': True}, p['audit']['infeasible_obligations'])

    def test_fixed_and_self_exclusion(self):
        s = spec(3, fixed={'f0': False}, excludes=[['f1', 'f1']])
        p = build_plan(s)
        self.assertTrue(p['audit']['complete'])
        self.assertTrue(all(not c['config']['f0'] and not c['config']['f1'] for c in p['cases']))

    def test_fixed_true(self):
        s = spec(3, fixed={'f0': True})
        s['base_config']['f0'] = True
        p = build_plan(s)
        self.assertTrue(p['audit']['complete'])
        self.assertTrue(all(c['config']['f0'] for c in p['cases']))

    def test_budget_is_explicitly_incomplete(self):
        p = build_plan(spec(6), max_cases=1)
        self.assertEqual(p['status'], 'INCOMPLETE_BUDGET')
        self.assertFalse(p['audit']['complete'])
        self.assertTrue(p['audit']['missing_obligations'])
        self.assertTrue(p['audit']['missing_probe_ids'])

    def test_audit_does_not_trust_claimed_green(self):
        s = spec(5)
        p = build_plan(s)
        p['cases'] = p['cases'][:1]
        p['audit'] = {'complete': True}
        p['status'] = 'COMPLETE'
        self.assertFalse(audit_plan(s, p)['complete'])

    def test_audit_mandatory_probe_even_with_pair_coverage(self):
        s = spec(4)
        m = Model(s)
        p = build_plan(s)
        p['cases'] = [m.case(r) for r in itertools.product((False, True), repeat=4) if sum(r) != 1]
        result = audit_plan(s, p)
        self.assertEqual(result['missing_obligations'], [])
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['missing_probe_ids']), 4)

    def test_order_invariance(self):
        s = spec(5, requires=[['f1', 'f2'], ['f0', 'f2']], excludes=[['f3', 'f4']])
        t = copy.deepcopy(s)
        t['features'].reverse()
        t['requires'].reverse()
        t['excludes'] = [['f4', 'f3'], ['f3', 'f4']]
        self.assertEqual(canonical(build_plan(s)), canonical(build_plan(t)))

    def test_input_nonmutation_and_output_aliasing(self):
        s = spec(3)
        s['base_config']['nested'] = {'data': [1, 2]}
        before = copy.deepcopy(s)
        p = build_plan(s)
        self.assertEqual(s, before)
        p['cases'][0]['config']['nested']['data'][0] = 99
        self.assertEqual(s, before)
        self.assertEqual(p['cases'][1]['config']['nested']['data'][0], 1)

    def test_unswept_type_drift_rejected(self):
        s = spec(3)
        p = build_plan(s)
        p['cases'][0]['config']['budget'] = True
        with self.assertRaises(SpecError):
            audit_plan(s, p)

    def test_bad_case_metadata_and_duplicate(self):
        s = spec(3)
        p = build_plan(s)
        for field, bad in [('case_id', 'x'), ('toggled', ['f0'])]:
            q = copy.deepcopy(p)
            q['cases'][0][field] = bad
            with self.assertRaises(SpecError):
                audit_plan(s, q)
        p['cases'].append(copy.deepcopy(p['cases'][0]))
        with self.assertRaises(SpecError):
            audit_plan(s, p)

    def test_case_keys_and_boolean_poison(self):
        s = spec(3)
        for poison in (0, 1, 'false', None, []):
            p = build_plan(s)
            p['cases'][0]['config']['f0'] = poison
            with self.assertRaises(SpecError):
                audit_plan(s, p)
        p = build_plan(s)
        p['cases'][0]['config']['new'] = False
        with self.assertRaises(SpecError):
            audit_plan(s, p)

    def test_stale_spec_and_embedded_spec_drift(self):
        s = spec(3)
        p = build_plan(s)
        t = copy.deepcopy(s)
        t['provenance'] = {'runtime_git_blob': 'changed'}
        with self.assertRaises(SpecError):
            audit_plan(t, p)
        p['spec']['base_config']['budget'] = 2.0
        with self.assertRaises(SpecError):
            audit_plan(s, p)

    def test_invalid_specs(self):
        cases = []
        for change in ({'schema_version': True}, {'features': []}, {'features': ['f0', 'f0']},
                       {'features': ['missing']}, {'features': [1]}, {'requires': [['f0', 'missing']]},
                       {'excludes': 'f0'}, {'fixed': {'f0': 0}}, {'fixed': {'f0': True}},
                       {'unexpected': 1}):
            s = spec(3)
            s.update(change)
            cases.append(s)
        s = spec(3)
        s['base_config']['f0'] = 0
        cases.append(s)
        for s in cases:
            with self.assertRaises(SpecError):
                build_plan(s)
        for budget in (True, 0, -1, 1.5, 4097):
            with self.assertRaises(SpecError):
                build_plan(spec(2), max_cases=budget)

    def test_large_unconstrained_panel(self):
        s = spec(24)
        p = build_plan(s, max_cases=64)
        self.assertTrue(p['audit']['complete'])
        self.assertLessEqual(len(p['cases']), 64)
        self.assertEqual(p['audit']['feasible_obligations'], 1152)

    def test_pair_collision_missed_by_single_feature_probes(self):
        s = spec(6)
        m = Model(s)
        probes, _ = m.probes()
        self.assertFalse(any(r[0] and r[1] for r in probes))
        p = build_plan(s)
        self.assertTrue(any(c['config']['f0'] and c['config']['f1'] for c in p['cases']))

    def test_deleted_unique_pair_witness_is_detected(self):
        s = spec(6)
        p = build_plan(s)
        m = Model(s)
        rows = [tuple(c['config'][k] for k in m.names) for c in p['cases']]
        unique = None
        for a, b in itertools.combinations(range(6), 2):
            for x, y in itertools.product((False, True), repeat=2):
                witnesses = [i for i, r in enumerate(rows) if r[a] == x and r[b] == y]
                if len(witnesses) == 1:
                    unique = witnesses[0]
                    break
            if unique is not None:
                break
        self.assertIsNotNone(unique)
        del p['cases'][unique]
        self.assertTrue(audit_plan(s, p)['missing_obligations'])

    def test_current_config_against_literal_constructor_excerpt(self):
        from feature_contract_excerpt import Features
        s = read_json(Path(__file__).with_name('current-production.spec.json'))
        m = Model(s)
        # Exhaustive 8192 configurations, not just the selected panel.
        for row in itertools.product((False, True), repeat=len(m.names)):
            cfg = dict(m.base)
            cfg.update(zip(m.names, row))
            try:
                Features(**cfg)
                accepted = True
            except ValueError:
                accepted = False
            self.assertEqual(m.valid(row), accepted)
        plan = build_plan(s)
        self.assertTrue(plan['audit']['complete'])
        for case in plan['cases']:
            Features(**case['config'])

    def test_cli_success_budget_and_audit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, output, report = root/'spec.json', root/'plan.json', root/'audit.json'
            source.write_text(json.dumps(spec(3)))
            self.assertEqual(main([str(source), '--output', str(output)]), 0)
            self.assertEqual(main([str(source), '--audit', str(output), '--output', str(report)]), 0)
            self.assertTrue(read_json(report)['complete'])
            self.assertEqual(main([str(source), '--max-cases', '1', '--output', str(output)]), 1)
            self.assertEqual(main([str(source), '--audit', str(output), '--output', str(report)]), 1)

    def test_strict_json_and_preserve_output_on_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, output = root/'spec.json', root/'out.json'
            output.write_text('keep')
            for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
                source.write_text(text)
                with self.assertRaises(SystemExit) as cm:
                    main([str(source), '--output', str(output)])
                self.assertEqual(cm.exception.code, 2)
                self.assertEqual(output.read_text(), 'keep')
            source.write_bytes(b'\xff')
            with self.assertRaises(SystemExit):
                main([str(source), '--output', str(output)])
            self.assertEqual(output.read_text(), 'keep')

    def test_output_input_alias_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, alias = root/'spec.json', root/'alias.json'
            source.write_text(json.dumps(spec(3)))
            alias.hardlink_to(source)
            before = source.read_bytes()
            for dest in (source, alias):
                with self.assertRaises(SystemExit):
                    main([str(source), '--output', str(dest)])
                self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

"""Real pinned-file-loader regression for the flag-only development ablation."""
import copy
import json
from pathlib import Path
import unittest
import panel

ROOT = Path(__file__).resolve().parent


class NearCloneTests(unittest.TestCase):
    def test_official_file_loader_and_direct_entry_have_same_first_action(self):
        # Captured real control observation; no new game or hidden seed.
        observation = json.loads((ROOT / 'fixtures/initial-observation.json').read_text())
        wrapper = ROOT / 'nearclone/no_preempt.py'
        source = ROOT / 'barnyard-v7/main.py'
        before = panel.digest(source)
        loader = panel.load(panel.KG / 'cloud-pack/official.py', 't07_real_loader_test')
        actual = loader.make_agent(wrapper)(copy.deepcopy(observation), {})
        direct = panel.load(wrapper, 't07_direct_off_test')
        expected = direct.agent(copy.deepcopy(observation))
        self.assertEqual(actual, expected)
        self.assertFalse(direct._policy._PREEMPT_ENABLED)
        self.assertEqual(panel.digest(source), before)
        self.assertEqual(before, '997e6bfc5234534e246e945bc61c87858ebf997ab85b0a5c9427dd4ed710f1b6')

    def test_missing_resource_context_is_explicit(self):
        namespace = {}
        code = (ROOT / 'nearclone/no_preempt.py').read_text()
        exec(compile(code, '<file-loader-shape>', 'exec'), namespace)
        with self.assertRaisesRegex(ValueError, 'file-loader configuration'):
            namespace['agent']({})

    def test_baseline_reuse_excludes_failed_candidate(self):
        run = panel.load(ROOT / 'nearclone/run.py', 't07_nearclone_run_test')
        frozen = dict(schema='x', panel='dev', seeds=[1], source={'main.py': 'a'},
                      infrastructure={}, opponent='original', adapters={'original': 'same', 'off': 'new'})
        old = copy.deepcopy(frozen)
        old['adapters']['off'] = 'old'
        base = dict(arm='baseline', seed=1, candidate_seat=0, opponent='original', status='complete', scores=[1, 1])
        bad = dict(base, arm='candidate', status='failed', scores=None)
        self.assertEqual(run.reusable_baseline({'frozen': old, 'games': [base, bad]}, frozen), [base])
        old['source']['main.py'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Baseline differs'):
            run.reusable_baseline({'frozen': old, 'games': [base]}, frozen)


if __name__ == '__main__':
    unittest.main()

import json
from pathlib import Path
import tempfile
import unittest
import study

BASE = '''POLICY = {"animal_cap":28,"max_hands":10,"crop_cap":6,"expansion":True}
def agent(obs, cfg=None):
    return {"farmer":["PASS"]}
'''

class StudyTests(unittest.TestCase):
    def test_standalone_has_no_wrapper_import(self):
        value = study.build_variant(BASE, study.VARIANTS['lean20'])
        namespace = {}
        exec(value, namespace)
        self.assertEqual(namespace['POLICY']['animal_cap'],20)
        self.assertEqual(namespace['POLICY']['max_hands'],8)
        self.assertFalse(namespace['POLICY']['expansion'])
        self.assertEqual(namespace['agent']({})['farmer'],['PASS'])
        self.assertNotIn('import', value)

    def test_source_span_fails_explicitly(self):
        with self.assertRaises(ValueError):
            study.build_variant(BASE, {'care_headroom':True})

    def test_seed_sets_declared_disjoint(self):
        previous = {1,17,101,37,211,997,23,83,449,2027,65537,6607,104729}
        self.assertFalse(set(study.DEV_SEEDS) & set(study.VALIDATION_SEEDS))
        self.assertFalse(previous & set(study.VALIDATION_SEEDS))
        self.assertEqual(len(study.VALIDATION_SEEDS),len(set(study.VALIDATION_SEEDS)))

    def test_journal_resume_and_torn_tail(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'games.jsonl'
            one = study.Journal(path, {'source':'one'})
            one.put('game', {'status':'complete'})
            with path.open('ab') as f: f.write(b'{"partial":')
            two = study.Journal(path, {'source':'one'})
            self.assertEqual(two.rows, one.rows)
            self.assertTrue(path.read_bytes().endswith(b'\n'))
            two.put('second', {'status':'failed'})
            self.assertEqual(len(study.Journal(path, {'source':'one'}).rows),2)

    def test_journal_rejects_changed_contract(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'games.jsonl'
            study.Journal(path, {'seed':1}).put('a', {})
            with self.assertRaisesRegex(ValueError,'contract changed'):
                study.Journal(path, {'seed':2})

    def test_journal_does_not_hide_complete_corrupt_record(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'games.jsonl'
            path.write_bytes(b'NOT JSON\n')
            with self.assertRaises(json.JSONDecodeError): study.Journal(path, {})
            self.assertEqual(path.read_bytes(),b'NOT JSON\n')

    def test_journal_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as root:
            journal = study.Journal(Path(root)/'games.jsonl',{})
            journal.put('a',{})
            with self.assertRaises(ValueError): journal.put('a',{})

    def test_pair_statistics(self):
        rows = []
        for seed in [1,2,3]:
            for seat in [0,1]:
                rows.append(dict(seed=seed,candidate_seat=seat,status='complete',scores=[15,10] if seat==0 else [10,15]))
        result = study.paired_summary(rows)
        self.assertEqual(result['paired_seeds'],3)
        self.assertEqual(result['seed_bootstrap_95_percentile'],[5,5])
        self.assertEqual(result['wins'],6)

    def test_failures_not_wins_or_pairs(self):
        rows = [dict(seed=1,candidate_seat=0,status='complete',scores=[20,10]),
                dict(seed=1,candidate_seat=1,status='failed',scores=None)]
        result = study.paired_summary(rows)
        self.assertEqual(result['failures'],1)
        self.assertEqual(result['paired_seeds'],0)
        self.assertEqual(result['wins'],1)
        self.assertIsNone(result['seed_bootstrap_95_percentile'])

    def test_atomic_json(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'sub'/'a.json'
            study.write_json(path,{'a':1})
            self.assertEqual(json.loads(path.read_text()),{'a':1})

if __name__=='__main__': unittest.main(verbosity=2)

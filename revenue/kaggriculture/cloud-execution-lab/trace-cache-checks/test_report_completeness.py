#!/usr/bin/env python3
"""Exercise the existing comparator on detached copies of actual saved reports.

No policy import, actor call, engine transition or input-prefix execution occurs.
Pass the directory containing original validation-{cached,uncached,original}.json.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


def load(path):
    spec=importlib.util.spec_from_file_location('tested_cache_consumer',path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module


def run(source, reports):
    target=load(source)
    original={mode:json.loads((reports/f'validation-{mode}.json').read_text())
              for mode in ('cached','uncached','original')}
    summary=json.loads((reports/'validation.json').read_text())
    for mode,data in original.items():
        raw=(reports/f'validation-{mode}.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=summary['report_sha256'][mode]:
            raise ValueError('Original report digest differs: '+mode)
    class Cases(unittest.TestCase):
        def setUp(self):self.data=copy.deepcopy(original)
        def reject(self):
            with self.assertRaises(ValueError):target.compare(self.data)
        def test_actual_complete_result_retained(self):
            got=target.compare(self.data)
            self.assertTrue(got['complete']);self.assertEqual(got['matched_action_state_pairs'],5752)
            self.assertEqual(got['actual_parent_calls'],8628)
        def test_missing_mode(self):self.data.pop('original');self.reject()
        def test_truncated_original_matrix(self):
            self.data['original']['cells']=self.data['original']['cells'][:1];self.reject()
        def test_truncated_cached_matrix(self):
            self.data['cached']['cells']=self.data['cached']['cells'][:1];self.reject()
        def test_extra_comparator_cell(self):
            self.data['original']['cells'].append(copy.deepcopy(self.data['original']['cells'][0]));self.reject()
        def test_false_cached_completion(self):self.data['cached']['completed']=False;self.reject()
        def test_recorded_failure(self):self.data['uncached']['failures']=['retained fault'];self.reject()
        def test_wrong_mode_label(self):self.data['original']['mode']='cached';self.reject()
        def test_wrong_source_ref(self):self.data['original']['source_commit']='0'*40;self.reject()
        def test_empty_source_ref(self):
            for report in self.data.values():report['source_commit']=''
            self.reject()
        def test_wrong_input(self):self.data['uncached']['input_zip_sha256']='0'*64;self.reject()
        def test_wrong_call_total(self):self.data['original']['total_calls']=1;self.reject()
        def test_wrong_cell_calls(self):self.data['uncached']['cells'][1]['calls']=718;self.reject()
        def test_wrong_parent_count(self):self.data['original']['cells'][2]['actual_parent_calls']=718;self.reject()
        def test_wrong_view_seat(self):
            self.data['uncached']['cells'][0]['seat']=1
            self.reject()
        def test_equal_but_noncontiguous_rows(self):
            for report in self.data.values():report['cells'][0]['rows'][0]['step']=-1
            self.reject()
        def test_equal_but_truncated_rows(self):
            for report in self.data.values():report['cells'][2]['rows'].pop()
            self.reject()
        def test_equal_but_invalid_digest(self):
            for report in self.data.values():report['cells'][0]['rows'][0]['action']='not-a-digest'
            self.reject()
        def test_missing_initialization(self):self.data['original']['initializations'].pop();self.reject()
        def test_nonempty_initial_events(self):
            self.data['uncached']['initializations'][0]['events_empty_at_init']=False;self.reject()
        def test_action_mismatch(self):self.data['uncached']['cells'][0]['rows'][600]['action']='0'*64;self.reject()
        def test_state_mismatch(self):self.data['original']['cells'][0]['rows'][624]['state']='0'*64;self.reject()
        def test_bad_mode_fails_before_any_worker(self):
            self.data['original']=None;self.reject()
    import io
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
    print(stream.getvalue(),end='')
    return {'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'successful':result.wasSuccessful(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'original_report_sha256':summary['report_sha256'],'actor_calls':0,'new_games':0}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,default=Path(__file__).with_name('check_cache_prefixes.py'))
    ap.add_argument('--reports',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();result=run(args.source,args.reports)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    raise SystemExit(0 if result['successful'] else 1)

if __name__=='__main__':main()

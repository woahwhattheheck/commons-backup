"""Source-context and output-integrity regressions for UIOWA-015.

Offline tests enforce recorded contracts, not the truth of arbitrary web text.
The external source inspection is separately attributed in sources.json.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import peerpack


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.sources = peerpack.load('sources.json')
        self.data = peerpack.load('cards.json')

    def target(self, cid):
        return next(c for c in self.data['cards'] if c['card_id'] == cid)

    def problems(self):
        return peerpack.build(self.sources, self.data)[2]

    def test_condition_cannot_be_removed_by_universal_label(self):
        for cid in ('PC-004', 'PC-005', 'PC-006', 'PC-007', 'PC-008', 'PC-011', 'PC-012', 'PC-013'):
            with self.subTest(card=cid):
                self.target(cid)['obligation_strength'] = 'MANDATORY'
                self.assertTrue(any('scoped obligation_cases require CONDITIONAL' in p['problem'] for p in self.problems()))
                self.target(cid)['obligation_strength'] = 'CONDITIONAL'

    def test_conditional_card_requires_cases(self):
        self.target('PC-006')['obligation_cases'] = []
        self.assertTrue(any('needs explicit obligation_cases' in p['problem'] for p in self.problems()))

    def test_context_locator_cannot_disappear(self):
        self.target('PC-006')['source_locator'] = ''
        self.assertTrue(any('source_locator' in p['problem'] for p in self.problems()))

    def test_applicability_cannot_disappear(self):
        self.target('PC-006')['applicability'] = ''
        self.assertTrue(any('applicability' in p['problem'] for p in self.problems()))

    def test_cases_are_typed_not_truthy_strings(self):
        self.target('PC-006')['obligation_cases'] = 'Required'
        self.assertTrue(any('must be an array' in p['problem'] for p in self.problems()))

    def test_case_requires_condition_and_known_force(self):
        for case in ({'condition':'', 'strength':'MANDATORY'}, {'condition':'High','strength':'ALWAYS'}, None):
            with self.subTest(case=case):
                self.target('PC-006')['obligation_cases'] = [case]
                self.assertTrue(any('invalid obligation case' in p['problem'] for p in self.problems()))

    def test_ku_subtasks_keep_global_level1_rule(self):
        for cid in ('PC-004', 'PC-005'):
            cases = self.target(cid)['obligation_cases']
            self.assertEqual([(c['condition'], c['strength']) for c in cases], [
                ('KU Level 1 data involved','MANDATORY'),
                ('Otherwise, within required SDLC phases','ADVISORY')])

    def test_minnesota_columns_are_not_flattened(self):
        self.assertEqual([c['strength'] for c in self.target('PC-006')['obligation_cases']], ['MANDATORY','ADVISORY','UNKNOWN'])
        self.assertIn('Optional', self.target('PC-006')['obligation_cases'][2]['condition'])
        for cid in ('PC-007','PC-008'):
            self.assertEqual([c['strength'] for c in self.target(cid)['obligation_cases']], ['MANDATORY','MANDATORY','ADVISORY'])
        self.assertNotIn('non-overridable', self.target('PC-008')['why_transferable'])

    def test_uc_threshold_is_preserved_on_each_new_card(self):
        for cid in ('PC-011','PC-012','PC-013'):
            c = self.target(cid)
            self.assertEqual(c['obligation_strength'], 'CONDITIONAL')
            self.assertEqual(c['obligation_cases'][0]['condition'], 'In scope and PL3+ or AL3+')
            self.assertEqual(c['obligation_cases'][1]['strength'], 'UNKNOWN')
            self.assertIn('Section 2', c['applicability'])

    def test_uc_retrieval_retains_original_limit(self):
        uc = next(s for s in self.sources['sources'] if s['source_id'] == 'SRC-UCOP-SSDS')
        self.assertEqual(uc['original_observation']['verification'], 'NOT_VERIFIED')
        self.assertEqual(uc['verification'], 'VERIFIED')
        self.assertIn('2019-10-03', uc['document_date'])
        self.assertIn('2019-08-21', uc['document_date'])
        self.assertIn('visually checked', uc['verification_note'])

    def test_failed_recheck_does_not_relabel_original_draft_as_adopted(self):
        cards, sources, problems = peerpack.build(self.sources, self.data)
        self.assertFalse(problems)
        neu = sources['SRC-NEU-SDLC']
        self.assertEqual(neu['verification'], 'VERIFIED')
        self.assertEqual(neu['recheck']['status'], 'FETCH_UNAVAILABLE')
        for c in cards:
            if c['source_id'] == 'SRC-NEU-SDLC':
                self.assertEqual(c['effective_obligation'], 'DRAFT_INTENT')
        text = peerpack.render(cards, sources, self.sources, [])
        self.assertIn('HTTP 502', text)
        self.assertIn('DRAFT_INTENT', text)

    def test_dsu_issue_and_adoption_are_not_one_effective_date(self):
        dsu = next(s for s in self.sources['sources'] if s['source_id'] == 'SRC-DSU-1410')
        self.assertIn('2026-02-07', dsu['document_date'])
        self.assertIn('2026-02-09', dsu['document_date'])
        self.assertIn('tailoring', dsu['scope_note'])

    def test_new_pdf_quotes_remain_short(self):
        quotes = [c['quote'] for c in self.data['cards'] if c['source_id'] == 'SRC-UCOP-SSDS']
        self.assertEqual(len(quotes), 3)
        self.assertLessEqual(sum(len(q.split()) for q in quotes), 25)

    def test_duplicate_card_identity_is_visible(self):
        self.data['cards'].append(copy.deepcopy(self.data['cards'][0]))
        self.assertTrue(any(p['problem'] == 'duplicate card_id' for p in self.problems()))

    def test_missing_card_id_is_visible(self):
        del self.data['cards'][0]['card_id']
        self.assertTrue(any(p['problem'] == 'card has no card_id' for p in self.problems()))

    def test_pack_identity_mismatch_is_rejected(self):
        self.data['pack_id'] = 'another-pack'
        with self.assertRaisesRegex(peerpack.PackError, 'pack_id'):
            self.problems()

    def test_malformed_document_shapes_are_controlled_errors(self):
        for sources, cards in (([], self.data), (self.sources, []), ({'sources':{}}, self.data)):
            with self.subTest(sources=type(sources), cards=type(cards)):
                with self.assertRaises(peerpack.PackError):
                    peerpack.build(sources, cards)

    def test_questions_must_be_real_array_of_text(self):
        for questions in ('Can you show me one?', ['A recent example?', 12], ['', 'A recent example?']):
            with self.subTest(questions=questions):
                self.data['cards'][0]['transferable_questions'] = questions
                self.assertTrue(any('array of nonempty text' in p['problem'] for p in self.problems()))

    def test_quote_type_error_becomes_problem(self):
        self.data['cards'][0]['quote'] = 12
        self.assertTrue(any('must be text' in p['problem'] for p in self.problems()))

    def test_runtime_advisory_match_is_word_based(self):
        c=self.data['cards'][1]
        c['quote']='The primary record is required.'
        c['obligation_basis']='primary record is required'
        self.assertFalse(self.problems())

    def test_invalid_render_preserves_existing_deliverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)
            shutil.copy(Path(peerpack.HERE)/'peerpack.py', dest/'peerpack.py')
            (dest/'sources.json').write_text(json.dumps(self.sources))
            self.target('PC-006')['obligation_cases']=[]
            (dest/'cards.json').write_text(json.dumps(self.data))
            report=dest/'15-development-peer-pack.md'
            report.write_bytes(b'previous verified deliverable\n')
            for option in ('--render','--print','--check'):
                proc=subprocess.run([sys.executable,str(dest/'peerpack.py'),option],capture_output=True,text=True)
                self.assertEqual(proc.returncode,1,proc.stderr)
                self.assertEqual(proc.stdout,'')
                self.assertIn('deliverable unchanged',proc.stderr)
                self.assertEqual(report.read_bytes(),b'previous verified deliverable\n')

    def test_malformed_json_reports_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)
            shutil.copy(Path(peerpack.HERE)/'peerpack.py',dest/'peerpack.py')
            (dest/'sources.json').write_text('{')
            proc=subprocess.run([sys.executable,str(dest/'peerpack.py'),'--render'],capture_output=True,text=True)
            self.assertEqual(proc.returncode,2)
            self.assertIn('PACK ERROR:',proc.stderr)
            self.assertNotIn('Traceback',proc.stderr)
            self.assertFalse((dest/'15-development-peer-pack.md').exists())

    def test_render_keeps_all_scope_cases_and_source_locators(self):
        cards,sources,problems=peerpack.build(self.sources,self.data)
        text=peerpack.render(cards,sources,self.sources,problems)
        for c in cards:
            self.assertIn(c['source_locator'],text)
            self.assertIn(c['applicability'],text)
            for case in c['obligation_cases']:
                self.assertIn(case['condition'],text)
        self.assertIn('not an exhaustive search',text)
        self.assertNotIn('what is *practised* is not',text)

    def test_all_original_ids_survive_without_duplicate_cards(self):
        ids=[c['card_id'] for c in self.data['cards']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(ids), {'PC-%03d'%n for n in range(1,14)})


if __name__=='__main__':
    unittest.main(verbosity=2)

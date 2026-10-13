from revenue.procurement_qa_answer_delta.test_support import *

class CompilerTestsA(unittest.TestCase):

    def test_close_gap_ready(self):
        out, delta = compile_obj(document())
        self.assertEqual(out.status, 'OWNER_REVIEW_READY')
        row = delta['deltas'][0]
        self.assertEqual(row['classification'], 'CLOSED_GAP')
        self.assertTrue(row['active'])
        self.assertEqual(row['before']['gap']['gap_id'], 'human-evidence:req-security')
        self.assertEqual(row['after']['gap_state'], 'CLOSED')
        self.assertIn('REMOVE_GAP_FROM_OWNER_WORKLIST', row['owner_actions'])
        self.assertTrue(all((v is False for v in delta['authority'].values())))

    def test_explicit_later_reopen_supersedes_close(self):
        doc = document()
        doc['qa_sources'].append(source('qa-02', seq=11, answers=[answer('a-security-2', effect='REOPEN_GAP', supersedes='a-security-1', text='Buyer reopens evidence review.')]))
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'OWNER_REVIEW_READY')
        rows = {r['delta_id']: r for r in delta['deltas']}
        self.assertFalse(rows['answer:a-security-1']['active'])
        self.assertEqual(rows['answer:a-security-1']['superseded_by'], 'a-security-2')
        self.assertTrue(rows['answer:a-security-2']['active'])
        self.assertEqual(rows['answer:a-security-2']['classification'], 'REOPENED_GAP')
        self.assertEqual(delta['counts']['superseded_delta_rows'], 1)

    def test_missing_explicit_supersession_holds(self):
        doc = document()
        doc['qa_sources'].append(source('qa-02', seq=11, answers=[answer('a-security-2', text='A second answer without explicit supersession.')]))
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        conflict = next((r for r in delta['deltas'] if r['delta_id'] == 'answer:a-security-2'))
        self.assertEqual(conflict['classification'], 'SOURCE_CONFLICT')
        self.assertIn('MISSING_EXPLICIT_ANSWER_SUPERSESSION', conflict['conflict_reasons'])
        first = next((r for r in delta['deltas'] if r['delta_id'] == 'answer:a-security-1'))
        self.assertTrue(first['active'])

    def test_unknown_superseded_answer_holds(self):
        doc = document()
        doc['qa_sources'][0]['answers'][0]['supersedes_answer_id'] = 'missing'
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('UNKNOWN_SUPERSEDED_ANSWER', delta['deltas'][0]['conflict_reasons'])

    def test_same_sequence_supersession_holds(self):
        doc = document()
        doc['qa_sources'].append(source('qa-02', seq=10, answers=[answer('a-security-2', supersedes='a-security-1')]))
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        reasons = {x for r in delta['deltas'] for x in r['conflict_reasons']}
        self.assertIn('DUPLICATE_QA_SEQUENCE', reasons)

    def test_secondary_source_holds(self):
        doc = document()
        doc['qa_sources'][0]['source_class'] = 'SECONDARY'
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('NON_BUYER_OFFICIAL_SOURCE', delta['deltas'][0]['conflict_reasons'])

    def test_stale_source_holds(self):
        doc = document()
        doc['source_max_age_seconds'] = 60
        doc['qa_sources'][0]['captured_at'] = '2026-09-16T18:00:00-04:00'
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('STALE_QA_SOURCE', delta['deltas'][0]['conflict_reasons'])

    def test_future_source_holds(self):
        doc = document()
        doc['qa_sources'][0]['captured_at'] = '2026-09-16T20:00:01-04:00'
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('FUTURE_QA_SOURCE', delta['deltas'][0]['conflict_reasons'])

    def test_unknown_question_holds(self):
        doc = document()
        doc['qa_sources'][0]['answers'][0]['question_id'] = 'unknown-q'
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('UNKNOWN_QUESTION_ID', delta['deltas'][0]['conflict_reasons'])

    def test_question_lineage_source_drift_holds(self):
        doc = document()
        doc['questions'][0]['source_sha256'] = '9' * 64
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('QUESTION_SOURCE_DRIFT', delta['deltas'][0]['conflict_reasons'])

    def test_unanswered_bad_question_still_holds(self):
        doc = document()
        doc['questions'][1]['source_sha256'] = '9' * 64
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        row = next((r for r in delta['deltas'] if r['delta_id'] == 'question:q-hosting'))
        self.assertEqual(row['classification'], 'SOURCE_CONFLICT')

    def test_requirement_change_emits_exact_before_after(self):
        doc = document()
        after = {'lineage_id': 'req-security', 'section_id': 'sec-3.2', 'kind': 'MANDATORY', 'family': 'security', 'tags': ['soc2', 'encryption', 'mfa'], 'text': 'Provide current security controls including MFA evidence.'}
        doc['qa_sources'][0]['answers'] = [answer(effect='REQUIREMENT_CHANGE', req_after=after)]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'OWNER_REVIEW_READY')
        row = delta['deltas'][0]
        self.assertEqual(row['classification'], 'REQUIREMENT_CHANGED')
        self.assertEqual(row['before']['requirement']['text'], 'Provide current security control evidence.')
        self.assertEqual(row['after']['requirement']['text'], after['text'])
        self.assertIn('RESELECT_RESPONSE_MODULES', row['owner_actions'])

    def test_requirement_change_without_delta_holds(self):
        doc = document()
        req = deepcopy(active_set()['requirements'][0])
        req = {k: req[k] for k in ('lineage_id', 'section_id', 'kind', 'family', 'tags', 'text')}
        doc['qa_sources'][0]['answers'] = [answer(effect='REQUIREMENT_CHANGE', req_after=req)]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('REQUIREMENT_CHANGE_HAS_NO_DELTA', delta['deltas'][0]['conflict_reasons'])

    def test_requirement_change_lineage_drift_holds(self):
        doc = document()
        after = {'lineage_id': 'req-other', 'section_id': 'sec-3.2', 'kind': 'MANDATORY', 'family': 'security', 'tags': ['soc2'], 'text': 'Changed.'}
        doc['qa_sources'][0]['answers'] = [answer(effect='REQUIREMENT_CHANGE', req_after=after)]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('REQUIREMENT_CHANGE_LINEAGE_DRIFT', delta['deltas'][0]['conflict_reasons'])

    def test_deadline_change_ready(self):
        doc = document()
        doc['qa_sources'][0]['answers'] = [answer('a-deadline-1', qid='q-deadline', lineage=None, effect='DEADLINE_CHANGE', deadline_after='2026-10-02T16:00:00-04:00')]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'OWNER_REVIEW_READY')
        row = delta['deltas'][0]
        self.assertEqual(row['classification'], 'DEADLINE_CHANGED')
        self.assertEqual(row['before']['deadline']['utc'], '2026-09-30T20:00:00Z')
        self.assertEqual(row['after']['deadline'], '2026-10-02T16:00:00-04:00')

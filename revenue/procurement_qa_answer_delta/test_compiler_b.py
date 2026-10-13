from revenue.procurement_qa_answer_delta.test_support import *

class CompilerTestsB(unittest.TestCase):

    def test_deadline_same_value_holds(self):
        doc = document()
        doc['qa_sources'][0]['answers'] = [answer('a-deadline-1', qid='q-deadline', lineage=None, effect='DEADLINE_CHANGE', deadline_after='2026-09-30T16:00:00-04:00')]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('DEADLINE_CHANGE_HAS_NO_DELTA', delta['deltas'][0]['conflict_reasons'])

    def test_informational_ready(self):
        doc = document()
        doc['qa_sources'][0]['answers'] = [answer(effect='INFORMATIONAL')]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'OWNER_REVIEW_READY')
        self.assertEqual(delta['deltas'][0]['classification'], 'INFORMATIONAL_ONLY')

    def test_informational_mutating_fact_holds(self):
        doc = document()
        doc['qa_sources'][0]['answers'] = [answer(effect='INFORMATIONAL', deadline_after='2026-10-02T16:00:00-04:00')]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('INFORMATIONAL_HAS_MUTATING_AFTER_FACT', delta['deltas'][0]['conflict_reasons'])

    def test_reopen_without_prior_close_holds(self):
        doc = document()
        doc['qa_sources'][0]['answers'] = [answer(effect='REOPEN_GAP')]
        out, delta = compile_obj(doc)
        self.assertEqual(out.status, 'HOLD_SOURCE_CONFLICT')
        self.assertIn('REOPEN_WITHOUT_PRIOR_CLOSED_GAP', delta['deltas'][0]['conflict_reasons'])

    def test_upstream_active_exact_byte_digest_drift_fails(self):
        doc = document()
        doc['upstream']['active_set']['requirements'][0]['text'] += ' drift'
        with self.assertRaisesRegex(Error, 'active_set exact canonical bytes drift'):
            compile_delta(canon(doc))

    def test_upstream_gaps_receipt_digest_mismatch_fails(self):
        doc = document()
        doc['upstream']['receipt']['gaps_sha256'] = '8' * 64
        doc['upstream']['receipt_sha256'] = digest(canon(doc['upstream']['receipt']))
        with self.assertRaisesRegex(Error, 'active/gaps digest mismatch'):
            compile_delta(canon(doc))

    def test_upstream_true_authority_fails(self):
        doc = document()
        doc['upstream']['active_set']['authority']['proposal_authorized'] = True
        doc['upstream']['active_set_sha256'] = digest(canon(doc['upstream']['active_set']))
        doc['upstream']['receipt']['active_set_sha256'] = doc['upstream']['active_set_sha256']
        doc['upstream']['receipt_sha256'] = digest(canon(doc['upstream']['receipt']))
        with self.assertRaisesRegex(Error, 'hard-false'):
            compile_delta(canon(doc))

    def test_duplicate_question_id_fails(self):
        doc = document()
        doc['questions'].append(deepcopy(doc['questions'][0]))
        with self.assertRaisesRegex(Error, 'duplicate question_id'):
            compile_delta(canon(doc))

    def test_duplicate_answer_id_fails(self):
        doc = document()
        doc['qa_sources'].append(source('qa-02', seq=11, answers=[answer()]))
        with self.assertRaisesRegex(Error, 'duplicate answer_id'):
            compile_delta(canon(doc))

    def test_intent_remap_fails(self):
        doc = document()
        q = question('q-other', lineage='req-hosting', gap='human-evidence:req-hosting', section='sec-4.1', qclass='SCORED_AMBIGUITY')
        q['intent_id'] = doc['questions'][0]['intent_id']
        doc['questions'].append(q)
        with self.assertRaisesRegex(Error, 'intent_id remapped'):
            compile_delta(canon(doc))

    def test_input_duplicate_json_key_and_float_fail(self):
        with self.assertRaisesRegex(Error, 'duplicate JSON key'):
            load(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(Error, 'non-integer'):
            load(b'{"a":1.5}')

    def test_deterministic_under_input_order_changes(self):
        doc = document()
        doc['qa_sources'].append(source('qa-02', seq=11, answers=[answer('a-security-2', effect='REOPEN_GAP', supersedes='a-security-1')]))
        first = compile_delta(canon(doc))
        shuffled = deepcopy(doc)
        shuffled['questions'].reverse()
        shuffled['qa_sources'].reverse()
        second = compile_delta(canon(shuffled))
        self.assertEqual(first.delta, second.delta)
        self.assertEqual(first.markdown, second.markdown)

    def test_verifier_rejects_tampered_outputs(self):
        raw_input = canon(document())
        out = compile_delta(raw_input)
        verify(raw_input, out.delta, out.markdown, out.receipt)
        with self.assertRaises(Error):
            verify(raw_input, out.delta + b'x', out.markdown, out.receipt)
        with self.assertRaisesRegex(Error, 'markdown: mismatch'):
            verify(raw_input, out.delta, out.markdown + b'x', out.receipt)
        with self.assertRaises(Error):
            verify(raw_input, out.delta, out.markdown, out.receipt + b'x')

    def test_receipt_binds_exact_input_bytes(self):
        raw_input = canon(document())
        out = compile_delta(raw_input)
        rec = load(out.receipt, 'receipt')
        self.assertEqual(rec['input_sha256'], digest(raw_input))
        altered = raw_input + b'\n'
        with self.assertRaises(Error):
            verify(altered, out.delta, out.markdown, out.receipt)

    def test_cli_compile_verify_and_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / 'input.json'
            inp.write_bytes(canon(document()))
            out_dir = root / 'out'
            cmd = [sys.executable, '-m', 'revenue.procurement_qa_answer_delta', 'compile', '--input', str(inp), '--out-dir', str(out_dir)]
            first = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            check = subprocess.run([sys.executable, '-m', 'revenue.procurement_qa_answer_delta', 'verify', '--input', str(inp), '--delta', str(out_dir / 'delta.json'), '--markdown', str(out_dir / 'delta.md'), '--receipt', str(out_dir / 'receipt.json')], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            second = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertIn('HOLD', second.stderr)

"""Real Strands orchestration with controlled model responses; NO live inference.

These tests establish contract/gating behavior, not model diagnostic accuracy.
Separate live receipts establish actual model outcomes for the supplied examples.
"""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from autopsy_agent.contracts import ROOT, DRAFT_KEYS, EvidenceCase, analysis_schema, build_report, model_json, strict_json
from autopsy_agent.models import ScriptedModel
from autopsy_agent.pipeline import check_review, run_case
from autopsy_agent.contracts import digest
from vendor.autopsy import fulfillment


def ordinary_candidate():
    fixture = json.loads((ROOT / 'vendor/autopsy/examples/report.json').read_text(encoding='utf-8'))
    analysis = {key: fixture[key] for key in DRAFT_KEYS - {'first_divergence_ref', 'failure_chain_refs'}}
    analysis['first_divergence_ref'] = 'transcript-001#T1-L02'
    analysis['failure_chain_refs'] = ['transcript-001#T1-L0' + str(i) for i in range(1, 10)]
    # The upstream fixture is a structural example, not semantic ground truth.
    # Untested alternatives require MEDIUM under the actual runbook definitions.
    for cause in analysis['causes']['primary'] + analysis['causes']['contributing']:
        cause['confidence'] = 'MEDIUM'
    return {'assessment': 'USABLE', 'assessment_reasons': ['The transcript records both edits, generation, and two failed tests.'],
            'clarification_question': None, 'analysis': analysis}


def insufficient_candidate():
    return {'assessment': 'NEEDS_CLARIFICATION', 'assessment_reasons': ['No commands, actions, or error outcome were retained.'],
            'clarification_question': 'Can you provide the redacted commands, tool results, and exact error for this one failed run?',
            'analysis': None}


def reviewed(messages, decision='ACCEPT'):
    payload = json.loads(messages[-1]['content'][0]['text'])
    report = payload['report']
    causes = [] if report is None else report['causes']['primary'] + report['causes']['contributing']
    return {'decision': decision, 'candidate_sha256': payload['candidate_sha256'],
            'evidence_sha256': payload['case']['evidence_sha256'],
            'evidence_link_check': True, 'adversarial_challenge_check': True,
            'findings': [{'statement': 'Controlled review response for gate testing only.',
                          'evidence_refs': [payload['case']['allowed_evidence_refs'][0]]}],
            'counterexamples': [{'cause_ids': [cause['cause_id'] for cause in causes],
                                 'explanation': 'The fixture does not establish unseen environment overrides.',
                                 'status': 'NOT_TESTED', 'assessment': 'Source code and runtime context were not supplied.',
                                 'evidence_refs': [payload['case']['allowed_evidence_refs'][0]]}],
            'cause_checks': [{'cause_id': cause['cause_id'], 'support': 'SUPPORTED_INFERENCE',
                              'confidence_supported': True, 'alternatives_examined': True,
                              'explanation': 'Controlled test response for coverage gating, not a live semantic judgment.',
                              'evidence_refs': cause['evidence_refs']} for cause in causes],
            'required_changes': [] if decision == 'ACCEPT' else ['Remove the unsupported cause.']}


class FlowTests(unittest.TestCase):
    def execute(self, candidate, case='ordinary', review=reviewed, path=None):
        models = {'drafter': ScriptedModel(candidate), 'reviewer': ScriptedModel(review)}
        result = run_case(path or ROOT / 'examples' / case / 'case.json', models.__getitem__, 'CONTROLLED_TEST_DOUBLE')
        self.models = models
        return result

    def test_ordinary_flow_uses_two_fresh_real_strands_agents_and_preserves_draft(self):
        result = self.execute(ordinary_candidate())
        self.assertEqual(result['status'], 'VALIDATED_SYNTHETIC_DRAFT', result.get('error'))
        self.assertEqual(len(result['phases']), 2)
        self.assertNotEqual(result['phases'][0]['agent_id'], result['phases'][1]['agent_id'])
        self.assertEqual(result['report']['artifact_state'], 'PEER_DRAFT')
        self.assertEqual(result['report']['final_review']['state'], 'PEER_DRAFT')
        self.assertIsNone(result['report']['operator_time']['reviewer_minutes'])
        self.assertEqual(result['review']['decision'], 'ACCEPT')
        self.assertFalse(result['claims']['revenue'])
        self.assertEqual(len(self.models['drafter'].calls), 1)
        self.assertEqual(len(self.models['reviewer'].calls), 1)
        reviewer_input = self.models['reviewer'].calls[0]['messages']
        self.assertEqual(len(reviewer_input), 1)  # fresh context, no drafter history

    def test_insufficient_evidence_requests_one_clarification_without_diagnosis(self):
        result = self.execute(insufficient_candidate(), 'insufficient')
        self.assertEqual(result['status'], 'CLARIFICATION_REQUESTED', result.get('error'))
        self.assertIsNone(result['report'])
        self.assertIsNone(result['candidate']['analysis'])
        self.assertEqual(result['intake']['clarification']['rounds_used'], 1)
        self.assertIsNone(result['intake']['evidence_assessment']['delivery_due_at'])

    def test_negative_control_good_vocabulary_with_invented_citation_fails(self):
        candidate = ordinary_candidate()
        candidate['analysis']['causes']['primary'][0]['evidence_refs'] = ['transcript-001#INVENTED']
        result = self.execute(candidate)
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertIsNone(result['report'])
        self.assertEqual(len(self.models['reviewer'].calls), 0)

    def test_insufficient_assessment_cannot_smuggle_a_diagnosis(self):
        candidate = insufficient_candidate()
        candidate['analysis'] = ordinary_candidate()['analysis']
        result = self.execute(candidate, 'insufficient')
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertIsNone(result['report'])

    def test_independent_reviewer_rejection_withholds_report(self):
        result = self.execute(ordinary_candidate(), review=lambda messages: reviewed(messages, 'REJECT'))
        self.assertEqual(result['status'], 'REVIEW_REJECTED')
        self.assertIsNone(result['report'])

    def test_reviewer_cannot_approve_a_different_candidate(self):
        def stale(messages):
            review = reviewed(messages)
            review['candidate_sha256'] = '0' * 64
            return review
        result = self.execute(ordinary_candidate(), review=stale)
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertIsNone(result['report'])

    def test_evidence_changed_during_review_fails_final_bundle_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('case.json', 'transcript.txt'):
                shutil.copyfile(ROOT / 'examples/ordinary' / name, root / name)
            def change_file(messages):
                with (root / 'transcript.txt').open('ab') as stream:
                    stream.write(b'\nChanged after draft.\n')
                return reviewed(messages)
            result = self.execute(ordinary_candidate(), review=change_file, path=root / 'case.json')
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertIsNone(result['report'])

    def test_missing_clarification_is_not_repaired_by_inventing_one(self):
        candidate = insufficient_candidate()
        candidate['clarification_question'] = None
        result = self.execute(candidate, 'insufficient')
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_synthetic_report_cannot_be_promoted_to_real_buyer_review(self):
        case = EvidenceCase(ROOT / 'examples/ordinary/case.json')
        intake = case.intake()
        report = build_report(case, intake, ordinary_candidate()['analysis'])
        report['artifact_state'] = 'READY_FOR_BUYER'
        with self.assertRaises(fulfillment.AutopsyValidationError):
            fulfillment.validate_bundle(intake, report, case.root)

    def test_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '```json\n{}\n```'):
            with self.assertRaises(ValueError):
                strict_json(text)

    def test_model_instance_reuse_cannot_claim_independence(self):
        model = ScriptedModel(ordinary_candidate())
        result = run_case(ROOT / 'examples/ordinary/case.json', lambda role: model, 'CONTROLLED_TEST_DOUBLE')
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_controlled_output_cannot_be_labeled_live(self):
        result = run_case(ROOT / 'examples/ordinary/case.json', lambda role: ScriptedModel({}), 'LIVE_COMMONS_GEMINI_CODE_ASSIST')
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_candidate_cannot_claim_a_buyer_replay_ran(self):
        for state in ('BUYER_REPORTED_PASS', 'BUYER_REPORTED_FAIL'):
            candidate = ordinary_candidate()
            candidate['analysis']['prevention_check']['execution_state'] = state
            result = self.execute(candidate)
            self.assertEqual(result['status'], 'FAILED_CLOSED')
            self.assertIsNone(result['report'])

    def test_clarification_cannot_accept_stale_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('case.json', 'transcript.txt'):
                shutil.copyfile(ROOT / 'examples/insufficient' / name, root / name)
            def change_file(messages):
                with (root / 'transcript.txt').open('ab') as stream:
                    stream.write(b'\nChanged during review.\n')
                return reviewed(messages)
            result = self.execute(insufficient_candidate(), 'insufficient', change_file, root / 'case.json')
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_unsafe_or_nonstring_case_id_rejected_before_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copyfile(ROOT / 'examples/ordinary/transcript.txt', root / 'transcript.txt')
            manifest = json.loads((ROOT / 'examples/ordinary/case.json').read_text())
            for case_id in ('../escaped', 123, None):
                manifest['case_id'] = case_id
                (root / 'case.json').write_text(json.dumps(manifest))
                result = self.execute(ordinary_candidate(), path=root / 'case.json')
                self.assertEqual(result['status'], 'FAILED_CLOSED')
                self.assertEqual(self.models['drafter'].calls, [])

    def test_long_tool_line_preserves_full_source_but_bounds_description(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('case.json', 'transcript.txt'):
                shutil.copyfile(ROOT / 'examples/ordinary' / name, root / name)
            with (root / 'transcript.txt').open('a', encoding='utf-8') as stream:
                stream.write('\nT1-L10 | tool | ' + 'x' * 600 + '\n')
            case = EvidenceCase(root / 'case.json')
            self.assertIn('x' * 600, case.model_input()['untrusted_evidence'])
            self.assertEqual(len(case.intake()['evidence'][0]['anchors'][-1]['description']), 500)
            result = self.execute(ordinary_candidate(), path=root / 'case.json')
            self.assertEqual(result['status'], 'VALIDATED_SYNTHETIC_DRAFT', result.get('error'))

    def test_source_version_change_during_review_fails_closed(self):
        from unittest.mock import patch
        with patch('autopsy_agent.pipeline.source_version', side_effect=['before', 'after']):
            result = self.execute(ordinary_candidate())
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_actual_accepted_but_unfaithful_model_output_is_rejected(self):
        failure = json.loads((ROOT / 'tests/fixtures/accepted-but-unfaithful.json').read_text(encoding='utf-8'))
        result = self.execute(failure['candidate'], review=failure['review'])
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertIsNone(result['report'])
        self.assertEqual(len(self.models['reviewer'].calls), 0)

    def test_observed_fields_are_exact_verified_source_projections(self):
        result = self.execute(ordinary_candidate())
        self.assertEqual(result['status'], 'VALIDATED_SYNTHETIC_DRAFT')
        case = EvidenceCase(ROOT / 'examples/ordinary/case.json')
        report = result['report']
        observations = report['timeline'] + report['failure_chain'] + [report['first_meaningful_divergence']]
        for observation in observations:
            anchor = observation['evidence_refs'][0].split('#')[1]
            self.assertEqual(observation['statement'], 'Recorded: ' + case.anchors[anchor])

    def test_freeform_observation_insertion_is_rejected(self):
        candidate = ordinary_candidate()
        candidate['analysis']['timeline'] = [{'statement': 'The unseen file contains 5.'}]
        result = self.execute(candidate)
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_high_confidence_with_untested_alternative_is_rejected(self):
        candidate = ordinary_candidate()
        candidate['analysis']['causes']['primary'][0]['confidence'] = 'HIGH'
        result = self.execute(candidate)
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_reviewer_cannot_skip_a_cause(self):
        def skip_one(messages):
            review = reviewed(messages)
            review['cause_checks'].pop()
            return review
        result = self.execute(ordinary_candidate(), review=skip_one)
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_reviewer_cannot_accept_unresolved_cause(self):
        def unsupported(messages):
            review = reviewed(messages)
            review['cause_checks'][0]['confidence_supported'] = False
            return review
        result = self.execute(ordinary_candidate(), review=unsupported)
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_selected_failure_chain_cannot_reverse_the_source_sequence(self):
        candidate = ordinary_candidate()
        candidate['analysis']['failure_chain_refs'].reverse()
        result = self.execute(candidate)
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_one_json_fence_is_only_presentation_and_does_not_repair_content(self):
        self.assertEqual(model_json('```json\n{"a":1}\n```\n'), {'a': 1})
        for text in ('Explanation\n```json\n{}\n```', '```json\n{}\n```\nApproved',
                     '```python\n{}\n```', '```json\n{"a":1,"a":2}\n```',
                     '```json\n{"a":NaN}\n```'):
            with self.assertRaises(ValueError):
                model_json(text)

    def test_fenced_reviewer_is_subject_to_the_same_complete_review_gates(self):
        def fenced(messages):
            return '```json\n' + json.dumps(reviewed(messages)) + '\n```'
        result = self.execute(ordinary_candidate(), review=fenced)
        self.assertEqual(result['status'], 'VALIDATED_SYNTHETIC_DRAFT')
        self.assertTrue(result['phases'][1]['output_text'].startswith('```json'))
        self.assertEqual(result['draft_report'], result['report'])

    def test_real_fenced_review_responses_parse_without_inventing_fields(self):
        fixture = json.loads((ROOT / 'tests/fixtures/fenced-reviews.json').read_text(encoding='utf-8'))
        for item in fixture:
            parsed = model_json(item['actual_output_text'])
            self.assertEqual(parsed['decision'], 'ACCEPT')
            self.assertEqual(parsed['candidate_sha256'], item['expected_candidate_sha256'])
            self.assertIn('cause_checks', parsed)

    def test_reviewer_discovered_alternative_blocks_otherwise_high_draft(self):
        # Exact failure pattern retained from the real old result: drafter says its
        # own alternative is weakened, reviewer retains an untested test override,
        # yet returns confident flags. The review's uncertainty must win.
        # Check the independent review gate directly: the current transcript-only
        # build gate now rejects every HIGH cause even earlier.
        case = EvidenceCase(ROOT / 'examples/ordinary/case.json')
        candidate = ordinary_candidate()
        report = build_report(case, case.intake(), candidate['analysis'])
        report['causes']['primary'][0]['confidence'] = 'HIGH'
        payload = {'candidate_sha256': 'test-bound-hash', 'case': case.model_input(), 'report': report}
        review = reviewed([{'content': [{'text': json.dumps(payload)}]}])
        with self.assertRaisesRegex(ValueError, 'Reviewer retains'):
            check_review(review, 'test-bound-hash', case, report)

    def test_reviewer_counterexample_cannot_hide_its_affected_cause(self):
        def omit_cause(messages):
            review = reviewed(messages)
            review['counterexamples'][0]['cause_ids'].pop()
            return review
        result = self.execute(ordinary_candidate(), review=omit_cause)
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_actual_no_diagnosis_review_need_not_invent_competing_causes(self):
        fixture = json.loads((ROOT / 'tests/fixtures/clarification-without-causes.json').read_text(encoding='utf-8'))
        case = EvidenceCase(ROOT / 'examples/insufficient/case.json')
        check_review(fixture['review'], digest({'candidate': fixture['candidate'], 'report': None}), case, None)
        result = self.execute(fixture['candidate'], 'insufficient', fixture['review'])
        self.assertEqual(result['status'], 'CLARIFICATION_REQUESTED', result.get('error'))
        self.assertIsNone(result['report'])
        self.assertEqual(result['review']['counterexamples'], [])

    def test_diagnosis_still_requires_competing_cause_coverage(self):
        def empty(messages):
            review = reviewed(messages)
            review['counterexamples'] = []
            return review
        result = self.execute(ordinary_candidate(), review=empty)
        self.assertEqual(result['status'], 'FAILED_CLOSED')

    def test_revision_retains_rejected_version_and_gets_a_new_independent_review(self):
        original = ordinary_candidate()
        revision = copy.deepcopy(original)
        revision['analysis']['limitations'].append('Revised in response to the controlled reviewer; no new source facts.')
        models = {'drafter': ScriptedModel(original), 'reviewer': ScriptedModel(lambda m: reviewed(m, 'REJECT')),
                  'revision_drafter': ScriptedModel(revision), 'revision_reviewer': ScriptedModel(reviewed)}
        result = run_case(ROOT / 'examples/ordinary/case.json', models.__getitem__, 'CONTROLLED_TEST_DOUBLE', max_revisions=1)
        self.assertEqual(result['status'], 'VALIDATED_SYNTHETIC_DRAFT', result.get('error'))
        self.assertEqual([r['status'] for r in result['rounds']], ['REVIEW_REJECTED', 'REVIEW_ACCEPTED'])
        self.assertEqual(result['rounds'][0]['candidate'], original)
        self.assertEqual(result['rounds'][1]['candidate'], revision)
        self.assertNotEqual(result['rounds'][0]['candidate_sha256'], result['rounds'][1]['candidate_sha256'])
        self.assertEqual(len({p['agent_id'] for p in result['phases']}), 4)
        revised_input = json.loads(models['revision_drafter'].calls[0]['messages'][0]['content'][0]['text'])
        self.assertEqual(revised_input['independent_review'], result['rounds'][0]['review'])
        fresh_review = models['revision_reviewer'].calls[0]['messages']
        self.assertEqual(len(fresh_review), 1)
        self.assertNotIn('independent_review', json.loads(fresh_review[0]['content'][0]['text']))

    def test_second_rejection_is_retained_and_never_automatically_accepted(self):
        calls = []
        def factory(role):
            calls.append(role)
            return ScriptedModel((lambda m: reviewed(m, 'REJECT')) if 'reviewer' in role else ordinary_candidate())
        result = run_case(ROOT / 'examples/ordinary/case.json', factory, 'CONTROLLED_TEST_DOUBLE', max_revisions=1)
        self.assertEqual(result['status'], 'REVIEW_REJECTED')
        self.assertIsNone(result['report'])
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(result['rounds']), 2)

    def test_revision_cannot_reuse_original_model_context(self):
        models = {'drafter': ScriptedModel(ordinary_candidate()),
                  'reviewer': ScriptedModel(lambda m: reviewed(m, 'REJECT'))}
        result = run_case(ROOT / 'examples/ordinary/case.json', lambda role: models[role.replace('revision_', '')],
                          'CONTROLLED_TEST_DOUBLE', max_revisions=1)
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertEqual(len(result['phases']), 2)
        self.assertIsNone(result['report'])

    def test_stale_evidence_prevents_spending_on_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('case.json', 'transcript.txt'):
                shutil.copyfile(ROOT / 'examples/ordinary' / name, root / name)
            def reject_and_change(messages):
                with (root / 'transcript.txt').open('ab') as stream:
                    stream.write(b'\nChanged before proposed revision.\n')
                return reviewed(messages, 'REJECT')
            calls = []
            def factory(role):
                calls.append(role)
                return ScriptedModel(reject_and_change if role == 'reviewer' else ordinary_candidate())
            result = run_case(root / 'case.json', factory, 'CONTROLLED_TEST_DOUBLE', max_revisions=1)
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertEqual(calls, ['drafter', 'reviewer'])

    def test_actual_hidden_cognition_high_false_acceptance_fails_conservative_profile(self):
        fixture = json.loads((ROOT / 'tests/fixtures/accepted-hidden-cognition-high.json').read_text(encoding='utf-8'))
        result = self.execute(fixture['candidate'], review=fixture['review'])
        self.assertEqual(result['status'], 'FAILED_CLOSED')
        self.assertIn('Transcript-only evidence profile', result['error']['message'])
        self.assertIsNone(result['report'])
        self.assertEqual(self.models['reviewer'].calls, [])
        self.assertEqual(result['candidate']['analysis']['causes']['contributing'][0]['confidence'], 'HIGH')

    def test_profile_applies_to_every_cause_even_if_all_alternatives_claimed_weakened(self):
        for group in ('primary', 'contributing'):
            candidate = ordinary_candidate()
            cause = candidate['analysis']['causes'][group][0]
            cause['confidence'] = 'HIGH'
            for alternative in cause['alternatives']:
                alternative['status'] = 'WEAKENED_BY_EVIDENCE'
            result = self.execute(candidate)
            self.assertEqual(result['status'], 'FAILED_CLOSED')
            self.assertIn('Transcript-only evidence profile', result['error']['message'])

    def test_conservative_profile_preserves_medium_low_and_unmodified_upstream_high(self):
        candidate = ordinary_candidate()
        candidate['analysis']['causes']['contributing'][0]['confidence'] = 'LOW'
        result = self.execute(candidate)
        self.assertEqual(result['status'], 'VALIDATED_SYNTHETIC_DRAFT', result.get('error'))
        self.assertEqual(result['evidence_profile']['allowed_causal_confidence'], ['MEDIUM', 'LOW'])
        self.assertEqual(analysis_schema()['$defs']['cause']['properties']['confidence']['enum'], ['MEDIUM', 'LOW'])
        upstream = json.loads((ROOT / 'vendor/autopsy/report.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(upstream['$defs']['cause']['properties']['confidence']['enum'], ['HIGH', 'MEDIUM', 'LOW'])

    def test_actual_clarification_need_not_claim_a_nonexistent_causal_challenge(self):
        fixture = json.loads((ROOT / 'tests/fixtures/clarification-no-causal-challenge.json').read_text(encoding='utf-8'))
        result = self.execute(fixture['candidate'], 'insufficient', fixture['review'])
        self.assertEqual(result['status'], 'CLARIFICATION_REQUESTED', result.get('error'))
        self.assertFalse(result['review']['adversarial_challenge_check'])
        self.assertIsNone(result['report'])

    def test_diagnosis_requires_causal_challenge_and_clarification_requires_evidence_check(self):
        def no_challenge(messages):
            review = reviewed(messages)
            review['adversarial_challenge_check'] = False
            return review
        self.assertEqual(self.execute(ordinary_candidate(), review=no_challenge)['status'], 'FAILED_CLOSED')
        def no_evidence(messages):
            review = reviewed(messages)
            review['evidence_link_check'] = False
            return review
        self.assertEqual(self.execute(insufficient_candidate(), 'insufficient', no_evidence)['status'], 'FAILED_CLOSED')


if __name__ == '__main__':
    unittest.main()

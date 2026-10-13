"""Independent packet-boundary regressions; synthetic fixtures only."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('_uiowa_handoff_rivet82', ROOT / 'handoff.py')
handoff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)


def packet():
    return json.loads((ROOT / 'examples/planned_release.json').read_text(encoding='utf-8'))


def codes(p):
    return {f.code for f in handoff.validate(p)}


class HandoffBoundaryTests(unittest.TestCase):
    def test_pending_support_is_followup_even_with_locator_and_trigger(self):
        p = packet()
        p['support_readiness'][0].update(status='pending', follow_up_trigger='Review at handoff')
        self.assertIn('SUPPORT_FOLLOWUP_OPEN', codes(p))
        self.assertEqual(handoff.assessment_state(handoff.validate(p)), 'REVIEWABLE_WITH_FOLLOWUP')

    def test_pending_operations_is_followup_even_with_verification_and_trigger(self):
        p = packet()
        p['operational_needs'][0].update(status='pending', follow_up_trigger='Review at handoff')
        self.assertIn('OPERATIONAL_FOLLOWUP_OPEN', codes(p))
        self.assertEqual(handoff.assessment_state(handoff.validate(p)), 'REVIEWABLE_WITH_FOLLOWUP')

    def test_deferred_items_need_trigger_not_just_locator(self):
        for section in ('support_readiness', 'operational_needs'):
            with self.subTest(section=section):
                p = packet()
                p[section][0]['status'] = 'deferred_with_owner'
                self.assertIn('FOLLOWUP_TRIGGER_MISSING', codes(p))

    def test_complete_support_needs_locator(self):
        p = packet()
        del p['support_readiness'][0]['locator']
        self.assertIn('SUPPORT_LOCATOR_MISSING', codes(p))
        self.assertEqual(handoff.assessment_state(handoff.validate(p)), 'REVIEWABLE_WITH_FOLLOWUP')

    def test_complete_operations_needs_verification(self):
        p = packet()
        del p['operational_needs'][0]['verification']
        self.assertIn('OPERATION_VERIFICATION_MISSING', codes(p))

    def test_shared_readiness_id_is_ambiguous_not_resolved(self):
        p = packet()
        item = copy.deepcopy(p['operational_needs'][0])
        item['id'] = 'SUP-01'
        p['operational_needs'].append(item)
        self.assertIn('AMBIGUOUS_READINESS_ID', codes(p))
        self.assertEqual(handoff.assessment_state(handoff.validate(p)), 'UNRELIABLE_PACKET')

    def test_synthetic_is_a_real_boolean(self):
        for value in ('false', 0, 1, None, [], {}):
            with self.subTest(value=value):
                p = packet()
                p['metadata']['synthetic'] = value
                self.assertIn('EXPECTED_BOOLEAN', codes(p))
        p = packet()
        p['metadata']['synthetic'] = False
        self.assertNotIn('EXPECTED_BOOLEAN', codes(p))
        self.assertNotIn('SYNTHETIC_PACKET', codes(p))

    def test_malformed_enum_values_return_errors_not_exceptions(self):
        targets = (('metadata', 'change_type'), ('metadata', 'group'),
                   ('support_readiness', 'status'), ('operational_needs', 'status'),
                   ('documentation_updates', 'status'), ('open_items', 'severity'))
        for section, key in targets:
            for value in (['complete'], {'status': 'complete'}, True, 7):
                with self.subTest(section=section, value=value):
                    p = packet()
                    if section == 'open_items':
                        p[section] = [{'id': 'OPEN-1', 'severity': value}]
                    elif section == 'metadata':
                        p[section][key] = value
                    else:
                        p[section][0][key] = value
                    self.assertIn('EXPECTED_STRING', codes(p))
                    self.assertIn('UNRELIABLE_PACKET', handoff.render(p, []))

    def test_invalid_reference_entries_do_not_crash(self):
        for key in ('acceptance_evidence', 'support_readiness'):
            for value in ({'id': 'EVID-01'}, ['EVID-01'], True, 3, None, '', ' '):
                with self.subTest(key=key, value=value):
                    p = packet()
                    p['requirements'][0][key] = [value]
                    self.assertIn('INVALID_REFERENCE_ID', codes(p))
                    self.assertIn('UNRELIABLE_PACKET', handoff.render(p, []))

    def test_reference_container_must_be_an_array(self):
        for key in ('acceptance_evidence', 'support_readiness'):
            for value in ('EVID-01', {'id': 'EVID-01'}, True, 3):
                with self.subTest(key=key, value=value):
                    p = packet()
                    p['requirements'][0][key] = value
                    self.assertIn('EXPECTED_LIST', codes(p))
                    self.assertIn('UNRELIABLE_PACKET', handoff.render(p, []))

    def test_null_reference_container_is_explicit_gap_and_renderable(self):
        for key, expected in (('acceptance_evidence', 'REQUIREMENT_EVIDENCE_MISSING'),
                              ('support_readiness', 'REQUIREMENT_HANDOFF_MISSING')):
            p = packet()
            p['requirements'][0][key] = None
            self.assertIn(expected, codes(p))
            self.assertIn('REVIEWABLE_WITH_FOLLOWUP', handoff.render(p, []))

    def test_ids_are_not_coerced(self):
        for section in ('requirements', 'support_readiness', 'acceptance_evidence', 'operational_needs'):
            for value in (1, True, ['ID'], {'id': 'ID'}):
                with self.subTest(section=section, value=value):
                    p = packet()
                    p[section][0]['id'] = value
                    self.assertIn('EXPECTED_STRING', codes(p))

    def test_wrong_section_types_have_diagnostic_render(self):
        for section in handoff.REQUIRED_TOP:
            for value in (None, False, 7, 'wrong'):
                with self.subTest(section=section, value=value):
                    p = packet()
                    p[section] = value
                    findings = handoff.validate(p)
                    self.assertTrue(any(f.level == 'ERROR' for f in findings))
                    self.assertIn('UNRELIABLE_PACKET', handoff.render(p, findings))

    def test_nonobject_rows_have_diagnostic_render(self):
        for section in ('known_limitations', 'requirements', 'acceptance_evidence',
                        'support_readiness', 'documentation_updates', 'operational_needs', 'open_items'):
            for value in (None, False, 7, 'wrong', []):
                with self.subTest(section=section, value=value):
                    p = packet()
                    p[section].append(value)
                    self.assertIn('EXPECTED_OBJECT', codes(p))
                    self.assertIn('UNRELIABLE_PACKET', handoff.render(p, []))

    def test_missing_sections_cannot_be_hidden_by_stale_findings(self):
        p = packet()
        del p['metadata']
        self.assertIn('UNRELIABLE_PACKET', handoff.render(p, []))
        self.assertIn('MISSING_SECTION', handoff.render(p, []))

    def test_scalar_roots_render_as_invalid_not_ready(self):
        for value in (None, False, [], 3, 'wrong'):
            with self.subTest(value=value):
                result = handoff.render(value, [])
                self.assertIn('UNRELIABLE_PACKET', result)
                self.assertIn('not release approval', result)

    def test_report_preserves_actual_evidence_and_pending_readiness(self):
        p = packet()
        p['support_readiness'][0].update(status='pending', follow_up_trigger='Finish rehearsal')
        rendered = handoff.render(p, handoff.validate(p))
        for text in ('Acceptance evidence', 'Support and operational readiness',
                     'synthetic://tests/registration_hold_rendering',
                     'synthetic://ops/dashboard/registration-hold-support-volume',
                     'synthetic://support/hold-decision-tree-v2', 'pending', 'Finish rehearsal'):
            self.assertIn(text, rendered)

    def test_table_preserves_unicode_pipe_and_multiline_text(self):
        p = packet()
        p['requirements'][0]['acceptance_criteria'] = 'caf\u00e9|boundary\r\n<literal>'
        rendered = handoff.render(p, [])
        self.assertIn('caf\u00e9\\|boundary<br>&lt;literal&gt;', rendered)

    def test_validate_and_render_do_not_mutate_packet(self):
        p = packet()
        before = copy.deepcopy(p)
        handoff.render(p, handoff.validate(p))
        self.assertEqual(p, before)

    def test_malformed_affected_users_is_not_silently_accepted(self):
        p = packet()
        p['user_facing_behavior']['affected_users'] = [{'name': 'persona'}]
        self.assertIn('INVALID_AFFECTED_USERS', codes(p))

    def test_required_text_cannot_be_boolean_or_object(self):
        for section, key in (('metadata', 'service'), ('rollback_and_recovery', 'owner_role'),
                             ('user_facing_behavior', 'communications')):
            for value in (False, {'text': 'recorded'}):
                p = packet()
                p[section][key] = value
                self.assertIn('EXPECTED_STRING', codes(p))


class HandoffCliTests(unittest.TestCase):
    def run_cli(self, raw, *args):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'packet.json'
            path.write_bytes(raw if isinstance(raw, bytes) else raw.encode('utf-8'))
            command = [sys.executable]
            if not __debug__:
                command.append('-O')
            command += [str(ROOT / 'handoff.py'), args[0], str(path), *args[1:]]
            return subprocess.run(command, capture_output=True, text=True, timeout=10)

    def assert_input_error(self, raw):
        proc = self.run_cli(raw, 'validate', '--json')
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result['assessment_state'], 'UNRELIABLE_PACKET')
        self.assertEqual(result['findings'][0]['code'], 'INPUT_OR_OUTPUT_ERROR')
        self.assertNotIn('Traceback', proc.stderr)

    def test_duplicate_json_keys_are_rejected_at_any_depth(self):
        for raw in ('{"a":1,"a":2}', '{"a":{"b":1,"b":2}}'):
            with self.subTest(raw=raw):
                self.assert_input_error(raw)

    def test_nonfinite_numbers_and_numeric_overflow_are_rejected(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            with self.subTest(token=token):
                self.assert_input_error('{"a":' + token + '}')

    def test_invalid_json_utf8_and_root_have_structured_errors(self):
        for raw in ('{', '[]', 'null', b'{"a":"\xff"}'):
            with self.subTest(raw=raw):
                self.assert_input_error(raw)

    def test_malformed_metadata_produces_diagnostic_report(self):
        p = packet()
        p['metadata'] = None
        proc = self.run_cli(json.dumps(p), 'render')
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn('UNRELIABLE_PACKET', proc.stdout)
        self.assertNotIn('Traceback', proc.stderr)

    def test_unwritable_output_is_controlled_error(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'missing-parent' / 'report.md'
            proc = self.run_cli(json.dumps(packet()), 'render', '-o', str(output))
            self.assertEqual(proc.returncode, 2)
            self.assertIn('INPUT_OR_OUTPUT_ERROR', proc.stderr)
            self.assertNotIn('Traceback', proc.stderr)

    def test_original_examples_keep_cli_semantics(self):
        expected = {'planned_release.json': 'REVIEWABLE_NO_RECORDED_GAPS',
                    'urgent_maintenance.json': 'REVIEWABLE_WITH_FOLLOWUP'}
        for name, state in expected.items():
            raw = (ROOT / 'examples' / name).read_text(encoding='utf-8')
            proc = self.run_cli(raw, 'validate', '--json')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['assessment_state'], state)


if __name__ == '__main__':
    unittest.main()

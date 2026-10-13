"""Operator projection regressions: exercise the actual handoff renderer, no mocks.

Run with the existing stdlib test suite, normally and under python -O.
Fixtures are unchanged fictional ANVIL-50 examples. No fixture generator runs.
"""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('_handoff_keyframe_projection', ROOT / 'handoff.py')
handoff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)


def example(name='planned_release.json'):
    return json.loads((ROOT / 'examples' / name).read_text(encoding='utf-8'))


def section(report, heading):
    marker = '## ' + heading + '\n'
    if marker not in report:
        return ''
    return report.split(marker, 1)[1].split('\n## ', 1)[0]


class OperatorProjectionTests(unittest.TestCase):
    def test_recovery_instruction_fields_are_in_recovery_section(self):
        for name in ('planned_release.json', 'urgent_maintenance.json'):
            p = example(name)
            # Distinct sentinels prevent the same owner appearing elsewhere
            # from concealing a missing recovery section.
            for key in p['rollback_and_recovery']:
                p['rollback_and_recovery'][key] = 'SYN-RECOVERY-' + key
            out = section(handoff.render(p, []), 'Rollback and recovery')
            for value in p['rollback_and_recovery'].values():
                with self.subTest(example=name, value=value):
                    self.assertIn(value, out)

    def test_behavior_keeps_personas_and_communication_instructions(self):
        p = example()
        p['user_facing_behavior']['affected_users'] = ['SYN-PERSONA-A', 'SYN-PERSONA-B']
        p['user_facing_behavior']['communications'] = 'SYN-COMMUNICATION-PLAN'
        out = section(handoff.render(p, []), 'User-facing behavior')
        for value in ('SYN-PERSONA-A', 'SYN-PERSONA-B', 'SYN-COMMUNICATION-PLAN'):
            self.assertIn(value, out)

    def test_scalar_persona_is_preserved_without_character_iteration(self):
        p = example()
        p['user_facing_behavior']['affected_users'] = 'SYN-SINGLE-PERSONA'
        self.assertIn('SYN-SINGLE-PERSONA', section(handoff.render(p, []), 'User-facing behavior'))

    def test_context_keeps_accountability_trigger_version_and_urgency(self):
        p = example('urgent_maintenance.json')
        fields = ('packet_version', 'implementation_owner_role', 'support_owner_role',
                  'release_trigger', 'urgency_reason')
        for key in fields:
            p['metadata'][key] = 'SYN-CONTEXT-' + key
        out = section(handoff.render(p, []), 'Packet context')
        for key in fields:
            self.assertIn(p['metadata'][key], out)

    def test_explicit_false_synthetic_flag_is_not_reported_as_missing(self):
        p = example()
        p['metadata']['synthetic'] = False
        out = section(handoff.render(p, []), 'Packet context')
        self.assertIn('**Synthetic declaration:** false', out)
        self.assertNotIn('SYNTHETIC_PACKET', handoff.render(p, []))

    def test_requirement_statement_is_not_replaced_by_acceptance_criteria(self):
        p = example()
        p['requirements'][0]['statement'] = 'SYN-WHAT-WAS-REQUESTED'
        p['requirements'][0]['acceptance_criteria'] = 'SYN-HOW-TO-CHECK'
        out = section(handoff.render(p, []), 'Requirement traceability')
        self.assertIn('SYN-WHAT-WAS-REQUESTED', out)
        self.assertIn('SYN-HOW-TO-CHECK', out)

    def test_limitation_mitigation_survives_next_to_followup(self):
        p = example()
        p['known_limitations'][0]['mitigation'] = 'SYN-MITIGATE-NOW'
        p['known_limitations'][0]['follow_up_trigger'] = 'SYN-REVISIT-LATER'
        out = section(handoff.render(p, []), 'Known limitations')
        self.assertIn('SYN-MITIGATE-NOW', out)
        self.assertIn('SYN-REVISIT-LATER', out)

    def test_documentation_locator_cannot_hide_pending_followup(self):
        p = example()
        p['documentation_updates'][0].update(status='pending', locator='SYN-EXISTING-DOCUMENT',
                                             follow_up_trigger='SYN-REVISE-ON-REVIEW')
        out = section(handoff.render(p, []), 'Documentation')
        for text in ('SYN-EXISTING-DOCUMENT', 'SYN-REVISE-ON-REVIEW', 'pending'):
            self.assertIn(text, out)
        self.assertEqual(handoff.assessment_state(handoff.validate(p)), 'REVIEWABLE_WITH_FOLLOWUP')

    def test_operational_kind_is_not_lost_in_scope_label(self):
        p = example()
        p['operational_needs'][0]['kind'] = 'SYN-MONITORING-KIND'
        self.assertIn('SYN-MONITORING-KIND', section(handoff.render(p, []), 'Support and operational readiness'))

    def test_all_59_known_field_paths_have_visible_section_bound_values(self):
        p = example('urgent_maintenance.json')
        # Add optional fields to the first row, even when supplied elsewhere.
        p['support_readiness'][0]['follow_up_trigger'] = 'optional'
        p['documentation_updates'][0]['locator'] = 'optional'
        p['operational_needs'][0]['follow_up_trigger'] = 'optional'
        headings = {
            'metadata': None, 'user_facing_behavior': 'User-facing behavior',
            'known_limitations': 'Known limitations', 'requirements': 'Requirement traceability',
            'acceptance_evidence': 'Acceptance evidence', 'support_readiness': 'Support and operational readiness',
            'documentation_updates': 'Documentation', 'operational_needs': 'Support and operational readiness',
            'rollback_and_recovery': 'Rollback and recovery', 'open_items': 'Open items',
        }
        tested = 0
        for name, heading in headings.items():
            row = p[name] if isinstance(p[name], dict) else p[name][0]
            for key, value in row.items():
                with self.subTest(section=name, field=key):
                    candidate = copy.deepcopy(p)
                    target = candidate[name] if isinstance(candidate[name], dict) else candidate[name][0]
                    if key in ('change_type', 'group', 'status', 'severity', 'synthetic'):
                        # These values are an existing enum or Boolean; do not
                        # mutate them into invalid values just for display.
                        expected = str(value).lower() if isinstance(value, bool) else value
                    elif isinstance(value, list):
                        target[key] = ['SYN-FIELD-' + name + '-' + key]
                        expected = target[key][0]
                    else:
                        target[key] = 'SYN-FIELD-' + name + '-' + key
                        expected = target[key]
                    rendered = handoff.render(candidate, [])
                    if name == 'metadata':
                        if key == 'requested_behavior':
                            area = section(rendered, 'Requested behavior')
                        elif key in ('packet_version', 'implementation_owner_role', 'support_owner_role',
                                     'release_trigger', 'urgency_reason', 'synthetic'):
                            area = section(rendered, 'Packet context')
                        else:
                            area = rendered.split('\n## ', 1)[0]
                    else:
                        area = section(rendered, heading)
                    self.assertIn(expected, area)
                    tested += 1
        self.assertEqual(tested, 59)

    def test_new_sections_preserve_literal_unicode_and_multiline_content(self):
        p = example()
        value = 'caf\u00e9|\u0394\r\n<literal> \\path'
        p['rollback_and_recovery']['rollback_method'] = value
        p['user_facing_behavior']['communications'] = value
        p['documentation_updates'][0]['follow_up_trigger'] = value
        out = handoff.render(p, [])
        for heading in ('Rollback and recovery', 'User-facing behavior', 'Documentation'):
            area = section(out, heading)
            self.assertIn('caf\u00e9\\|\u0394<br>&lt;literal&gt;', area)
            self.assertNotIn('\r', area)

    def test_missing_null_and_empty_recovery_values_do_not_invent_instructions(self):
        for replacement in ({}, None, {'rollback_method': None}, {'rollback_method': ''}):
            p = example()
            p['rollback_and_recovery'] = replacement
            out = handoff.render(p, [])
            area = section(out, 'Rollback and recovery')
            self.assertTrue(area)
            self.assertNotIn('Restore the prior', area)
            self.assertNotEqual(handoff.assessment_state(handoff.validate(p)), 'REVIEWABLE_NO_RECORDED_GAPS')
            self.assertIn('not release approval', out)

    def test_complete_report_is_deterministic_and_does_not_mutate_inputs(self):
        p = example('urgent_maintenance.json')
        before = copy.deepcopy(p)
        findings = handoff.validate(p)
        saved = list(findings)
        first = handoff.render(p, findings)
        self.assertEqual(first, handoff.render(p, findings))
        self.assertEqual(p, before)
        self.assertEqual(findings, saved)

    def test_actual_cli_writes_recovery_section_from_original_packet(self):
        command = [sys.executable] + ([] if __debug__ else ['-O'])
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'handoff.md'
            result = subprocess.run(command + [str(ROOT / 'handoff.py'), 'render',
                str(ROOT / 'examples/urgent_maintenance.json'), '--output', str(out)],
                capture_output=True, text=True, encoding='utf-8', timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = out.read_text(encoding='utf-8')
            recovery = section(text, 'Rollback and recovery')
            for value in example('urgent_maintenance.json')['rollback_and_recovery'].values():
                self.assertIn(value, recovery)
            self.assertIn('REVIEWABLE_WITH_FOLLOWUP', text)


if __name__ == '__main__':
    unittest.main()

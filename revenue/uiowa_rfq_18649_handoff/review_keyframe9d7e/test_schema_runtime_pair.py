"""Explicit two-carrier integration test; not a second assessor.

UIOWA_HANDOFF_SCHEMA=/path/to/schema.json python -m unittest discover \
    -s review_keyframe9d7e -v
A schema path is required: the old shallow main schema is not silently used.
QA-only dependencies: jsonschema, referencing (same as #16306 conformance).
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('_handoff_keyframe_pair', ROOT / 'handoff.py')
handoff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)

GAPS = {
    'user_facing_behavior': 'before after affected_users communications'.split(),
    'rollback_and_recovery': 'rollback_trigger rollback_method data_recovery_notes owner_role'.split(),
    'known_limitations': 'id description affected_scope owner_role follow_up_trigger'.split(),
    'acceptance_evidence': 'kind locator result notes'.split(),
    'support_readiness': 'item owner_role status locator'.split(),
    'operational_needs': 'kind need owner_role status verification'.split(),
    'documentation_updates': 'document owner_role status locator'.split(),
    'open_items': 'id severity question owner_role resolution_trigger'.split(),
}


def git_blob(path):
    content = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def load(name='planned_release.json'):
    return json.loads((ROOT / 'examples' / name).read_text(encoding='utf-8'))


def row(packet, name):
    return packet[name] if isinstance(packet[name], dict) else packet[name][0]


class PairedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        supplied = os.environ.get('UIOWA_HANDOFF_SCHEMA')
        if not supplied:
            raise RuntimeError('Set UIOWA_HANDOFF_SCHEMA to the explicitly selected schema file; no implicit old schema or skip.')
        cls.schema_path = Path(supplied)
        schema = json.loads(cls.schema_path.read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema, registry=Registry())
        cls.cases = 0
        print('PAIR runtime=' + git_blob(ROOT / 'handoff.py') + ' schema=' + git_blob(cls.schema_path))

    @classmethod
    def tearDownClass(cls):
        print('PAIRED_CASES=' + str(cls.cases))

    def check(self, packet, shape, state=None, code=None):
        before = copy.deepcopy(packet)
        self.assertEqual(self.validator.is_valid(packet), shape)
        findings = handoff.validate(packet)
        if state:
            self.assertEqual(handoff.assessment_state(findings), state)
        if code:
            self.assertIn(code, {f.code for f in findings})
        rendered = handoff.render(packet, findings)
        self.assertIn('not release approval', rendered)
        self.assertEqual(packet, before)
        type(self).cases += 1

    def test_unchanged_examples_keep_distinct_assessment_outcomes(self):
        self.check(load(), True, 'REVIEWABLE_NO_RECORDED_GAPS')
        self.check(load('urgent_maintenance.json'), True, 'REVIEWABLE_WITH_FOLLOWUP')

    def test_35_gap_fields_accept_missing_null_blank_and_remain_followup(self):
        tested_fields = 0
        for name, fields in GAPS.items():
            for key in fields:
                tested_fields += 1
                for mode in ('absent', None, '', ' \t\n'):
                    with self.subTest(section=name, field=key, mode=mode):
                        p = load()
                        if name == 'open_items':
                            p[name] = copy.deepcopy(load('urgent_maintenance.json')[name])
                        target = row(p, name)
                        if mode == 'absent':
                            target.pop(key, None)
                        else:
                            target[key] = mode
                        self.check(p, True, 'REVIEWABLE_WITH_FOLLOWUP')
                        # A different pre-existing follow-up must not make this
                        # test green. Bind the finding to the field just removed.
                        if name in ('user_facing_behavior', 'rollback_and_recovery'):
                            expected_path = name + '.' + key
                        elif name in ('acceptance_evidence', 'support_readiness', 'operational_needs'):
                            expected_path = name + '[' + target['id'] + ']'
                            if (name, key) not in (('support_readiness', 'locator'),
                                                   ('operational_needs', 'verification')):
                                expected_path += '.' + key
                        else:
                            expected_path = name + '[0]'
                            if (name, key) != ('documentation_updates', 'locator'):
                                expected_path += '.' + key
                        self.assertTrue(any(f.level == 'GAP' and f.path == expected_path
                                            for f in handoff.validate(p)), expected_path)
        self.assertEqual(tested_fields, 35)

    def test_required_metadata_rejects_missing_or_wrong_types_in_both(self):
        for key in handoff.REQUIRED_METADATA:
            for mode in ('absent', None, [], {}):
                with self.subTest(field=key, mode=mode):
                    p = load()
                    if mode == 'absent':
                        p['metadata'].pop(key)
                    else:
                        p['metadata'][key] = mode
                    self.check(p, False, 'UNRELIABLE_PACKET')

    def test_wrong_gap_types_are_not_mislabeled_missing_information(self):
        for name, fields in GAPS.items():
            for key in fields:
                with self.subTest(section=name, field=key):
                    p = load('urgent_maintenance.json')
                    row(p, name)[key] = {'text': 'not a string'}
                    self.check(p, False, 'UNRELIABLE_PACKET')

    def test_pending_and_deferred_are_not_completed_by_a_locator(self):
        for name, code in (('support_readiness', 'SUPPORT_FOLLOWUP_OPEN'),
                           ('operational_needs', 'OPERATIONAL_FOLLOWUP_OPEN'),
                           ('documentation_updates', 'DOCUMENTATION_FOLLOWUP_OPEN')):
            for state in ('pending', 'deferred_with_owner'):
                p = load()
                p[name][0].update(status=state, follow_up_trigger='SYN-FOLLOWUP')
                self.check(p, True, 'REVIEWABLE_WITH_FOLLOWUP', code)

    def test_shape_valid_broken_refs_and_duplicates_require_semantic_check(self):
        for kind in ('evidence-ref', 'readiness-ref', 'duplicate-id', 'shared-readiness-id'):
            p = load()
            if kind == 'evidence-ref':
                p['requirements'][0]['acceptance_evidence'] = ['SYN-MISSING']
                expected = 'BROKEN_EVIDENCE_REFERENCE'
            elif kind == 'readiness-ref':
                p['requirements'][0]['support_readiness'] = ['SYN-MISSING']
                expected = 'BROKEN_READINESS_REFERENCE'
            elif kind == 'duplicate-id':
                p['acceptance_evidence'].append(copy.deepcopy(p['acceptance_evidence'][0]))
                expected = 'DUPLICATE_ID'
            else:
                item = copy.deepcopy(p['operational_needs'][0])
                item['id'] = p['support_readiness'][0]['id']
                p['operational_needs'].append(item)
                expected = 'AMBIGUOUS_READINESS_ID'
            self.check(p, True, 'UNRELIABLE_PACKET', expected)

    def test_missing_reference_arrays_are_gaps_not_coerced_to_readiness(self):
        for key, code in (('acceptance_evidence', 'REQUIREMENT_EVIDENCE_MISSING'),
                          ('support_readiness', 'REQUIREMENT_HANDOFF_MISSING')):
            for value in (None, []):
                p = load()
                p['requirements'][0][key] = value
                self.check(p, True, 'REVIEWABLE_WITH_FOLLOWUP', code)

    def test_false_boolean_is_valid_but_boolean_shaped_text_is_not(self):
        p = load()
        p['metadata']['synthetic'] = False
        self.check(p, True, 'REVIEWABLE_NO_RECORDED_GAPS')
        p['metadata']['synthetic'] = 'false'
        self.check(p, False, 'UNRELIABLE_PACKET', 'EXPECTED_BOOLEAN')

    def test_empty_collections_remain_representable_without_invented_evidence(self):
        for name in ('known_limitations', 'acceptance_evidence', 'support_readiness',
                     'operational_needs', 'documentation_updates'):
            p = load()
            p[name] = []
            # Reference-bearing collections need their corresponding references
            # emptied too: dangling references are a different semantic error.
            if name == 'acceptance_evidence':
                for req in p['requirements']:
                    req['acceptance_evidence'] = []
            if name in ('support_readiness', 'operational_needs'):
                for req in p['requirements']:
                    req['support_readiness'] = []
            self.check(p, True, 'REVIEWABLE_WITH_FOLLOWUP')

    def test_extension_data_is_not_misrepresented_as_assessed_or_dropped_from_input(self):
        p = load()
        p['extension'] = {'opaque': [None, False, 0, 'caf\u00e9']}
        self.check(p, True, 'REVIEWABLE_NO_RECORDED_GAPS')
        self.assertNotIn('opaque', handoff.render(p, []))
        # Extension rendering is not in the 59-known-field projection contract.


if __name__ == '__main__':
    unittest.main()

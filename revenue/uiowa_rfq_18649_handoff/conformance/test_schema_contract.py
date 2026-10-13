"""Independent structural-contract regression, not an assessment engine.

Run separately from the component's dependency-free runtime tests:
    python -m unittest discover -s conformance -v
Missing jsonschema is a dependency error, never a successful/zero-test run.
The corpus field inventory is independent of schema.json; a dropped property
there cannot disappear from the test coverage at the same time.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry

ROOT = Path(__file__).resolve().parents[1]
OBJECT_SECTIONS = ('metadata', 'user_facing_behavior', 'rollback_and_recovery')
FIELDS = {
    'metadata': 'packet_version change_id change_type service group summary requested_behavior implementation_owner_role support_owner_role release_trigger synthetic urgency_reason'.split(),
    'user_facing_behavior': 'before after affected_users communications'.split(),
    'known_limitations': 'id description affected_scope owner_role follow_up_trigger mitigation'.split(),
    'requirements': 'id statement acceptance_criteria acceptance_evidence support_readiness'.split(),
    'acceptance_evidence': 'id kind locator result notes'.split(),
    'support_readiness': 'id item owner_role status locator follow_up_trigger'.split(),
    'documentation_updates': 'document owner_role status locator follow_up_trigger'.split(),
    'operational_needs': 'id kind need owner_role status verification follow_up_trigger'.split(),
    'rollback_and_recovery': 'rollback_trigger rollback_method data_recovery_notes owner_role'.split(),
    'open_items': 'id severity question owner_role resolution_trigger'.split(),
}
# Only fields whose absence is a structural error, not an assessment gap.
REQUIRED = {
    'metadata': set(FIELDS['metadata']) - {'urgency_reason'},
    'requirements': {'id', 'statement', 'acceptance_criteria'},
    'acceptance_evidence': {'id'}, 'support_readiness': {'id'},
    'operational_needs': {'id'},
}
ENUMS = {
    ('metadata', 'change_type'): ('planned_release', 'urgent_maintenance'),
    ('metadata', 'group'): ('ESS', 'RIS', 'IAM'),
    ('support_readiness', 'status'): ('complete', 'pending', 'deferred_with_owner'),
    ('operational_needs', 'status'): ('complete', 'pending', 'deferred_with_owner'),
    ('documentation_updates', 'status'): ('updated', 'reviewed_no_change', 'pending', 'deferred_with_owner'),
    ('open_items', 'severity'): ('blocking', 'non_blocking'),
}
REF_FIELDS = {('requirements', 'acceptance_evidence'), ('requirements', 'support_readiness')}
BAD_TYPES = (0, 1.5, True, [], {})

def row(packet, section):
    return packet[section] if section in OBJECT_SECTIONS else packet[section][0]

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')

class SchemaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT/'schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(cls.schema)
        # An empty registry forbids unexpected remote reference resolution.
        cls.validator = Draft202012Validator(cls.schema, registry=Registry())
        cls.planned = json.loads((ROOT/'examples/planned_release.json').read_text(encoding='utf-8'))
        cls.urgent = json.loads((ROOT/'examples/urgent_maintenance.json').read_text(encoding='utf-8'))
        cls.evaluations = 0
        cls.accepted = 0
        cls.base = copy.deepcopy(cls.urgent)  # Has at least one row in every section.

    @classmethod
    def tearDownClass(cls):
        print(f'SCHEMA_CASES total={cls.evaluations} accepted={cls.accepted} rejected={cls.evaluations-cls.accepted}')

    def valid(self, packet):
        result = not list(self.validator.iter_errors(packet))
        type(self).evaluations += 1
        type(self).accepted += int(result)
        return result

    def changed(self, section, field, value):
        packet = copy.deepcopy(self.base)
        row(packet, section)[field] = value
        return packet

    def test_schema_and_actual_retained_examples(self):
        self.assertTrue(self.valid(self.planned))
        self.assertTrue(self.valid(self.urgent))

    def test_all_top_level_sections_remain_required(self):
        for section in FIELDS:
            packet = copy.deepcopy(self.base)
            del packet[section]
            with self.subTest(section=section): self.assertFalse(self.valid(packet))

    def test_wrong_root_and_section_containers(self):
        for root in (None, [], 'packet', 1, True): self.assertFalse(self.valid(root))
        for section in FIELDS:
            for wrong in (None, 'record', 1, True, [] if section in OBJECT_SECTIONS else {}):
                packet = copy.deepcopy(self.base); packet[section] = wrong
                with self.subTest(section=section, wrong=wrong): self.assertFalse(self.valid(packet))

    def test_every_collection_rejects_nonobject_rows(self):
        for section in FIELDS:
            if section in OBJECT_SECTIONS: continue
            for wrong in (None, 'record', 1, False, []):
                packet = copy.deepcopy(self.base); packet[section] = [wrong]
                with self.subTest(section=section, wrong=wrong): self.assertFalse(self.valid(packet))

    def test_every_documented_text_field_rejects_wrong_types(self):
        for section, fields in FIELDS.items():
            for field in fields:
                if (section, field) in REF_FIELDS or (section, field) in {
                    ('metadata', 'synthetic'), ('user_facing_behavior', 'affected_users')}: continue
                for wrong in BAD_TYPES:
                    with self.subTest(section=section, field=field, wrong=wrong):
                        self.assertFalse(self.valid(self.changed(section, field, wrong)))

    def test_required_fields_are_not_missing_null_or_blank(self):
        for section, fields in REQUIRED.items():
            for field in fields:
                packet = copy.deepcopy(self.base); row(packet, section).pop(field)
                with self.subTest(section=section, field=field, value='ABSENT'): self.assertFalse(self.valid(packet))
                for wrong in (None, '', ' \t\n', '\u00a0', '\u2003'):
                    with self.subTest(section=section, field=field, value=wrong):
                        self.assertFalse(self.valid(self.changed(section, field, wrong)))

    def test_missing_evidence_fields_remain_representable_gaps(self):
        for section, fields in FIELDS.items():
            for field in fields:
                if field in REQUIRED.get(section, set()) or (section, field) in REF_FIELDS: continue
                packet = copy.deepcopy(self.base); row(packet, section).pop(field, None)
                with self.subTest(section=section, field=field, value='ABSENT'): self.assertTrue(self.valid(packet))
                for missing in (None, '', ' \t\n', '\u00a0', '\u2003'):
                    with self.subTest(section=section, field=field, value=missing):
                        self.assertTrue(self.valid(self.changed(section, field, missing)))

    def test_empty_collections_are_not_fabricated_observations(self):
        for section in FIELDS:
            if section in OBJECT_SECTIONS: continue
            packet = copy.deepcopy(self.base); packet[section] = []
            with self.subTest(section=section): self.assertEqual(self.valid(packet), section != 'requirements')

    def test_boolean_synthetic_flag_does_not_require_true(self):
        for good in (True, False): self.assertTrue(self.valid(self.changed('metadata','synthetic',good)))
        for bad in (0, 1, 'true', 'false', 'UNKNOWN', None, [], {}):
            with self.subTest(value=bad): self.assertFalse(self.valid(self.changed('metadata','synthetic',bad)))

    def test_all_declared_states_and_invalid_nonblank_states(self):
        for (section, field), states in ENUMS.items():
            for state in states:
                with self.subTest(section=section, field=field, state=state):
                    self.assertTrue(self.valid(self.changed(section, field, state)))
            for wrong in ('approved', 'UNKNOWN', states[0].swapcase(), states[0]+' '):
                with self.subTest(section=section, field=field, state=wrong):
                    self.assertFalse(self.valid(self.changed(section, field, wrong)))

    def test_reference_arrays_not_strings_objects_or_blank_ids(self):
        for section, field in REF_FIELDS:
            for good in (None, [], ['EVID-01'], ['字 / exact case'], ['EVID-01','EVID-01']):
                with self.subTest(field=field, good=good): self.assertTrue(self.valid(self.changed(section,field,good)))
            for bad in ('EVID-01', {'id':'EVID-01'}, 1, False, [None], [1], [True], [[]], [{}], [''], [' \t\n']):
                with self.subTest(field=field, bad=bad): self.assertFalse(self.valid(self.changed(section,field,bad)))

    def test_affected_users_accepts_text_or_named_persona_array(self):
        for good in (None, '', [], 'role description', ['one'], ['一','two']):
            self.assertTrue(self.valid(self.changed('user_facing_behavior','affected_users',good)))
        for bad in (False, 0, {}, [''], [' \n'], [None], [[]], ['role', 5]):
            self.assertFalse(self.valid(self.changed('user_facing_behavior','affected_users',bad)))

    def test_extensions_and_unicode_roundtrip_without_defaults_or_coercion(self):
        packet = copy.deepcopy(self.base)
        packet['x-operator-context'] = {'note':'字 | =SUM(1,2)\nΩ', 'unknown':None}
        for section in FIELDS: row(packet, section)['x-extension'] = {'retained':[1,False,None,'é']}
        before = canonical(packet)
        self.assertTrue(self.valid(packet)); self.assertEqual(canonical(packet),before)
        self.assertEqual(canonical(json.loads(before)),before)

    def test_semantic_conflicts_are_not_claimed_solved_by_schema(self):
        # These are deliberately valid shapes, not acceptable semantic results.
        packets=[]
        p=copy.deepcopy(self.base); p['requirements'][0]['acceptance_evidence']=['MISSING']; packets.append(p)
        p=copy.deepcopy(self.base); p['acceptance_evidence'].append(copy.deepcopy(p['acceptance_evidence'][0])); packets.append(p)
        p=copy.deepcopy(self.base); p['operational_needs'][0]['id']=p['support_readiness'][0]['id']; packets.append(p)
        p=copy.deepcopy(self.base); p['support_readiness'][0]['status']='pending'; packets.append(p)
        p=copy.deepcopy(self.base); p['support_readiness'][0].pop('locator'); packets.append(p)
        for i,p in enumerate(packets):
            with self.subTest(case=i): self.assertTrue(self.valid(p))

    def test_every_known_field_is_explicit_in_schema_inventory(self):
        # Coverage comes from the independent inventory, not iterating schema fields.
        for section, fields in FIELDS.items():
            entry = self.schema['properties'][section]
            target = entry if section in OBJECT_SECTIONS else entry['items']
            definition = self.schema['$defs'][target['$ref'].rsplit('/',1)[1]]
            self.assertEqual(set(definition['properties']),set(fields))

    def test_no_defaults_remote_refs_or_executable_extensions(self):
        def walk(value):
            if isinstance(value, dict):
                self.assertNotIn('default',value)
                if '$ref' in value: self.assertTrue(value['$ref'].startswith('#/$defs/'))
                for child in value.values(): walk(child)
            elif isinstance(value,list):
                for child in value: walk(child)
        walk(self.schema)

    def test_schema_negative_control_detects_removed_item_contract(self):
        broken=copy.deepcopy(self.schema)
        del broken['properties']['support_readiness']['items']
        packet=copy.deepcopy(self.base); packet['support_readiness']=['not a record']
        self.assertFalse(self.valid(packet))
        self.assertTrue(Draft202012Validator(broken,registry=Registry()).is_valid(packet))

    def test_original_fixture_bytes_never_change_during_validation(self):
        paths=[ROOT/'examples/planned_release.json',ROOT/'examples/urgent_maintenance.json',ROOT/'schema.json']
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        for _ in range(3):
            self.assertTrue(self.valid(self.planned)); self.assertTrue(self.valid(self.urgent))
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        self.assertEqual(before,after)

if __name__ == '__main__':
    unittest.main()

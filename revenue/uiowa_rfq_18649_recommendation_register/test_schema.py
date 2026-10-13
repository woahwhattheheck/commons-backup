"""Structural JSON Schema conformance; install requirements-test.txt for this suite."""
import copy
import json
from pathlib import Path
import unittest
import jsonschema

HERE=Path(__file__).resolve().parent

class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema=json.loads((HERE/'register.schema.json').read_text(encoding='utf-8'))
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.validator=jsonschema.Draft202012Validator(cls.schema)
        cls.sample=json.loads((HERE/'examples/synthetic_register.json').read_text(encoding='utf-8'))

    def test_synthetic_register_and_unknowns_are_valid(self):
        self.validator.validate(self.sample)

    def test_every_declared_field_required(self):
        for group,template in [('register',self.sample),('finding',self.sample['findings'][0]),('recommendation',self.sample['recommendations'][0])]:
            for key in template:
                doc=copy.deepcopy(self.sample)
                row=doc if group=='register' else doc['findings'][0] if group=='finding' else doc['recommendations'][0]
                del row[key]
                with self.subTest(group=group,key=key):
                    self.assertFalse(self.validator.is_valid(doc))

    def test_extra_fields_rejected_at_every_object_boundary(self):
        for path in [(),('recommendations',0),('findings',0),('recommendations',0,'scope',0),('recommendations',0,'effort'),('recommendations',0,'outcome_measure')]:
            doc=copy.deepcopy(self.sample); row=doc
            for part in path:row=row[part]
            row['unreviewed_authority']=True
            with self.subTest(path=path):self.assertFalse(self.validator.is_valid(doc))

    def test_effort_partial_and_missing_basis_rejected(self):
        for patch in [dict(low=1,high=None),dict(low=None,high=1),dict(low=1,high=2,basis=None),dict(low=True,high=2)]:
            doc=copy.deepcopy(self.sample);doc['recommendations'][0]['effort'].update(patch)
            with self.subTest(patch=patch):self.assertFalse(self.validator.is_valid(doc))

    def test_numeric_outcome_needs_description_unit_and_basis(self):
        for field in ['description','unit','basis']:
            doc=copy.deepcopy(self.sample);doc['recommendations'][1]['outcome_measure'][field]=None
            with self.subTest(field=field):self.assertFalse(self.validator.is_valid(doc))

    def test_incomplete_references_preserved_for_working_drafts(self):
        doc=copy.deepcopy(self.sample);doc['recommendations'][0]['dependencies']=['UNRESOLVED']
        self.validator.validate(doc)

if __name__=='__main__':unittest.main()

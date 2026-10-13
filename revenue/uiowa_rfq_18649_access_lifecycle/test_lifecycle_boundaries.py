"""Independent UIOWA-053 regression and operator checks (ZZ-KESTREL-P9N).

Set LIFECYCLE_SOURCE to an exact historical source file to replay the failures.
The default is the adjacent canonical source; no generic module alias is used.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("LIFECYCLE_SOURCE", HERE / "access_lifecycle.py")).resolve()
SPEC = importlib.util.spec_from_file_location("uiowa053_boundary_subject", SOURCE)
access = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(access)
FIXTURE = HERE / "fixtures" / "lifecycle_cases.json"


def packet():
    return {"case_id": "SYN-BOUNDARY", "lifecycle_event": "mover",
            "worker_type": "contractor", "event_on": "2026-09-18",
            "access_changes": [{"system": "SYN-service", "environment": "development",
                                "intent": "revoke", "entitlement": "old-admin",
                                "effective_on": "2026-09-18"}],
            "evidence": [{"kind": "system_state_observation", "system": "SYN-service",
                          "intent": "revoke", "observed_on": "2026-09-19",
                          "matches_intent": True, "statement": "Fictional removal observation",
                          "locator": "SYN-observation-1"}]}


def review(value):
    return access.review_case(access.Case(value))["per_system"]


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class AttributionTests(unittest.TestCase):
    def test_same_intent_different_entitlements_need_qualification(self):
        p = packet(); p['access_changes'].append(dict(p['access_changes'][0], entitlement='old-release'))
        rows = review(p)
        self.assertEqual([r['status'] for r in rows], [access.NO_EVIDENCE] * 2)
        self.assertTrue(all(len(r['evidence_excluded_as_ambiguous']) == 1 for r in rows))

    def test_entitlement_qualifier_confirms_only_named_change(self):
        p = packet(); p['access_changes'].append(dict(p['access_changes'][0], entitlement='old-release'))
        p['evidence'][0]['entitlement'] = 'old-admin'
        rows = review(p)
        self.assertEqual([r['status'] for r in rows], [access.CONFIRMED_IN_SYSTEM, access.NO_EVIDENCE])
        self.assertEqual(rows[0]['evidence_used'][0]['entitlement'], 'old-admin')

    def test_same_entitlement_different_environments_needs_environment(self):
        p = packet(); p['access_changes'].append(dict(p['access_changes'][0], environment='deployment'))
        p['evidence'][0]['entitlement'] = 'old-admin'
        self.assertTrue(all(r['status'] == access.NO_EVIDENCE for r in review(p)))
        p['evidence'][0]['environment'] = 'development'
        self.assertEqual([r['status'] for r in review(p)], [access.CONFIRMED_IN_SYSTEM, access.NO_EVIDENCE])

    def test_repeated_change_dates_need_exact_checkpoint(self):
        p = packet(); p['access_changes'].append(dict(p['access_changes'][0], effective_on='2026-09-17'))
        self.assertTrue(all(r['status'] == access.NO_EVIDENCE for r in review(p)))
        p['evidence'][0]['effective_on'] = '2026-09-18'
        self.assertEqual([r['status'] for r in review(p)], [access.CONFIRMED_IN_SYSTEM, access.NO_EVIDENCE])

    def test_wrong_explicit_qualifier_does_not_fall_back_to_system(self):
        for field, value in [('entitlement','wrong'),('environment','wrong'),('effective_on','2026-09-16')]:
            with self.subTest(field=field):
                p = packet(); p['evidence'][0][field] = value
                self.assertEqual(review(p)[0]['status'], access.NO_EVIDENCE)

    def test_qualifiers_round_trip_without_being_dropped(self):
        p = packet(); p['evidence'][0].update(entitlement='old-admin',environment='development',effective_on='2026-09-18')
        e = access.Evidence(p['evidence'][0],case_id='SYN')
        self.assertEqual(access.Evidence(e.to_dict(),case_id='SYN').to_dict(), e.to_dict())

    def test_duplicate_logical_changes_are_rejected(self):
        p = packet(); p['access_changes'].append(copy.deepcopy(p['access_changes'][0]))
        with self.assertRaises(access.AccessReviewError): review(p)

    def test_qualifier_typos_are_not_silently_ignored(self):
        p = packet(); p['evidence'][0]['entitlment'] = 'old-admin'
        with self.assertRaises(access.AccessReviewError): review(p)

    def test_unknown_qualifier_is_not_a_wildcard(self):
        for field, value in [('entitlement',''),('environment',None),('effective_on','UNKNOWN')]:
            with self.subTest(field=field):
                p = packet(); p['evidence'][0][field] = value
                with self.assertRaises(access.AccessReviewError): review(p)


class ChronologyTests(unittest.TestCase):
    def test_invalid_calendar_and_noncanonical_dates_rejected(self):
        for value in ['2026-99-99','2026-02-29','2026-9-1','20260918','2026-W38-5','２０２６-09-18','0000-01-01']:
            with self.subTest(value=value):
                with self.assertRaises(access.AccessReviewError): access._date(value,case_id='SYN',field='date')

    def test_calendar_leap_day_and_unknown_markers(self):
        self.assertEqual(access._date('2024-02-29',case_id='SYN',field='date'),'2024-02-29')
        for value in [None,'','UNKNOWN']:
            self.assertIsNone(access._date(value,case_id='SYN',field='date'))

    def test_no_change_checkpoint_cannot_confirm(self):
        p = packet(); p.pop('event_on'); p['access_changes'][0].pop('effective_on')
        row = review(p)[0]
        self.assertEqual(row['status'],access.NO_EVIDENCE)
        self.assertIn('unknown',row['evidence_excluded_as_stale'][0]['why_excluded'])

    def test_case_event_supplies_a_known_fallback_checkpoint(self):
        p = packet(); p['access_changes'][0].pop('effective_on')
        self.assertEqual(review(p)[0]['status'],access.CONFIRMED_IN_SYSTEM)

    def test_observation_before_later_execution_cannot_confirm(self):
        p = packet(); p['evidence'].append({'kind':'execution_record','system':'SYN-service','intent':'revoke','statement':'Fictional later execution','observed_on':'2026-09-20'})
        row = review(p)[0]
        self.assertEqual(row['status'],access.ACTION_RECORDED)
        self.assertEqual(row['evidence_excluded_as_stale'][0]['reference_date'],'2026-09-20')

    def test_new_observation_after_latest_execution_can_confirm(self):
        p = packet(); p['evidence'].append({'kind':'execution_record','system':'SYN-service','intent':'revoke','statement':'Fictional later execution','observed_on':'2026-09-20'})
        p['evidence'].append(dict(p['evidence'][0],observed_on='2026-09-21',locator='SYN-observation-2'))
        row = review(p)[0]
        self.assertEqual(row['status'],access.CONFIRMED_IN_SYSTEM)
        self.assertEqual(len(row['evidence_excluded_as_stale']),1)

    def test_undated_execution_does_not_invent_ordering(self):
        p = packet(); p['evidence'].append({'kind':'execution_record','system':'SYN-service','intent':'revoke','statement':'Fictional undated execution'})
        self.assertEqual(review(p)[0]['status'],access.ACTION_RECORDED)

    def test_dated_execution_can_supply_missing_checkpoint(self):
        p = packet(); p.pop('event_on'); p['access_changes'][0].pop('effective_on')
        p['evidence'].append({'kind':'execution_record','system':'SYN-service','intent':'revoke','statement':'Fictional dated execution','observed_on':'2026-09-18'})
        self.assertEqual(review(p)[0]['status'],access.CONFIRMED_IN_SYSTEM)

    def test_later_execution_for_other_change_is_not_borrowed(self):
        p = packet(); p['access_changes'].append(dict(p['access_changes'][0],entitlement='other'))
        p['evidence'][0]['entitlement']='old-admin'
        p['evidence'].append({'kind':'execution_record','system':'SYN-service','intent':'revoke','entitlement':'other','statement':'Fictional other change','observed_on':'2026-09-20'})
        self.assertEqual([r['status'] for r in review(p)],[access.CONFIRMED_IN_SYSTEM,access.ACTION_RECORDED])

    def test_same_day_contract_does_not_claim_intraday_order(self):
        p = packet(); p['evidence'][0]['observed_on']='2026-09-18'
        self.assertEqual(review(p)[0]['status'],access.CONFIRMED_IN_SYSTEM)

    def test_unknown_observation_result_is_not_policy_evidence(self):
        p = packet(); p['evidence'][0].pop('matches_intent')
        row = review(p)[0]
        self.assertEqual(row['status'],access.NO_EVIDENCE)
        self.assertFalse(row['conclusion_rests_on_policy_alone'])
        self.assertEqual(len(row['observation_result_not_recorded']),1)

    def test_contradiction_is_not_erased_by_extra_paperwork(self):
        p = packet(); p['evidence'][0]['matches_intent']=False
        p['evidence'].append({'kind':'approval_record','system':'SYN-service','statement':'Fictional approval','observed_on':'2026-09-21'})
        self.assertEqual(review(p)[0]['status'],access.CONTRADICTED_IN_SYSTEM)


class InputTests(unittest.TestCase):
    def test_boolean_result_rejects_numeric_lookalikes(self):
        for value in [0,1,0.0,1.0,[],{}]:
            with self.subTest(value=value):
                p = packet();p['evidence'][0]['matches_intent']=value
                with self.assertRaises(access.AccessReviewError):review(p)

    def test_nested_shapes_have_named_errors(self):
        for field,value in [('evidence',{}),('evidence',[None]),('access_changes',{}),('access_changes',[None]),('interview_prompts',None)]:
            with self.subTest(field=field,value=value):
                p=packet();p[field]=value
                with self.assertRaises(access.AccessReviewError):review(p)

    def test_null_system_or_statement_is_not_the_word_None(self):
        for field in ['system','statement']:
            with self.subTest(field=field):
                p=packet();p['evidence'][0][field]=None
                with self.assertRaises(access.AccessReviewError):review(p)

    def test_text_fields_do_not_coerce_objects_to_evidence(self):
        for field in ['system','statement','locator']:
            with self.subTest(field=field):
                p=packet();p['evidence'][0][field]={'unsupported':'value'}
                with self.assertRaises(access.AccessReviewError):review(p)

    def test_duplicate_json_keys_and_nonfinite_are_named_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.json'
            for raw in ['{"cases":[],"cases":[]}','{"cases":NaN}','{"cases":Infinity}']:
                with self.subTest(raw=raw):
                    path.write_text(raw)
                    with self.assertRaises(access.AccessReviewError):access.read_json(str(path))

    def test_invalid_utf8_is_a_named_input_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.json';path.write_bytes(b'{"cases": "\xff"}')
            with self.assertRaises(access.AccessReviewError):access.read_json(str(path))

    def test_supplied_packet_is_not_mutated(self):
        p=packet();original=copy.deepcopy(p);review(p)
        self.assertEqual(p,original)


class PreservationTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),str(SOURCE),*map(str,args)],capture_output=True,text=True,timeout=20)

    def test_original_fixture_and_all_four_outputs_keep_exact_blobs(self):
        result=access.review_all(access.load_cases(access.read_json(str(FIXTURE))))
        self.assertEqual(git_blob(FIXTURE.read_bytes()),'d04aca2fae32fce4404b1eb3c60b77c4958fdd63')
        self.assertEqual(git_blob(access.render_matrix(result).encode()),'5fcd85c90db376abc894872ef25dfc25b0f2acb5')
        self.assertEqual(git_blob(access.render_scenarios(result).encode()),'d588fa1b5d8cfb2194a5c8e605e6c46b3b932adc')
        self.assertEqual(git_blob((json.dumps(result,indent=2,sort_keys=True)+'\n').encode()),'2caa59753b4f7a41622a8268e016c984e16d94f4')
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'matrix.csv';access.write_csv(result,str(output))
            self.assertEqual(git_blob(output.read_bytes()),'9e4a197d0bc9ddcf713e1b30bcbdf45b9477a347')

    def test_cli_input_alias_preserves_input(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'cases.json';source.write_bytes(FIXTURE.read_bytes());before=source.read_bytes()
            p=self.cli('--cases',source,'--json-out',source)
            self.assertEqual(p.returncode,2,p.stderr)
            self.assertEqual(source.read_bytes(),before)

    def test_existing_output_preserves_everything_before_any_write(self):
        with tempfile.TemporaryDirectory() as temp:
            new=Path(temp)/'new.json';old=Path(temp)/'prior.md';old.write_bytes(b'PREVIOUS NOTES')
            p=self.cli('--cases',FIXTURE,'--json-out',new,'--matrix-out',old)
            self.assertEqual(p.returncode,2,p.stderr)
            self.assertFalse(new.exists());self.assertEqual(old.read_bytes(),b'PREVIOUS NOTES')

    def test_duplicate_output_aliases_do_not_create_a_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result';alias=Path(temp)/'.'/'result'
            p=self.cli('--cases',FIXTURE,'--json-out',path,'--matrix-out',alias)
            self.assertEqual(p.returncode,2,p.stderr);self.assertFalse(path.exists())

    def test_hardlink_output_cannot_modify_input(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'input.json';source.write_bytes(FIXTURE.read_bytes());alias=Path(temp)/'alias.json';os.link(source,alias)
            before=source.read_bytes();p=self.cli('--cases',source,'--json-out',alias)
            self.assertEqual(p.returncode,2,p.stderr);self.assertEqual(source.read_bytes(),before)

    def test_broken_symlink_output_is_not_retargeted(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'link';target=Path(temp)/'absent';path.symlink_to(target)
            p=self.cli('--cases',FIXTURE,'--json-out',path)
            self.assertEqual(p.returncode,2,p.stderr);self.assertTrue(path.is_symlink());self.assertFalse(target.exists())

    def test_missing_parent_does_not_leave_an_earlier_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'new.json';missing=Path(temp)/'absent'/'report.md'
            p=self.cli('--cases',FIXTURE,'--json-out',path,'--matrix-out',missing)
            self.assertEqual(p.returncode,2,p.stderr);self.assertFalse(path.exists());self.assertNotIn('Traceback',p.stderr)

    def test_missing_input_is_a_named_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.cli('--cases',Path(temp)/'does-not-exist.json')
            self.assertEqual(p.returncode,2);self.assertNotIn('Traceback',p.stderr)

    def test_library_csv_writer_is_create_only(self):
        result=access.review_all(access.load_cases({'cases':[packet()]}))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'existing.csv';path.write_bytes(b'unchanged')
            with self.assertRaises((access.AccessReviewError,FileExistsError)):access.write_csv(result,str(path))
            self.assertEqual(path.read_bytes(),b'unchanged')

    def test_formula_like_csv_cells_are_literal_without_changing_json(self):
        for value in ['=1+1','+text','-text','@text',"'text",' =literal','\t=literal']:
            with self.subTest(value=value):
                p=packet();p['case_id']=value
                result=access.review_all(access.load_cases({'cases':[p]}))
                with tempfile.TemporaryDirectory() as temp:
                    path=Path(temp)/'out.csv';access.write_csv(result,str(path))
                    with path.open(newline='') as handle:rows=list(csv.reader(handle))
                self.assertTrue(rows[1][0].startswith("'"))
                self.assertEqual(result['cases'][0]['case_id'],value.strip())

    def test_markdown_record_text_is_literal_and_json_unchanged(self):
        p=packet(); p['case_id']='SYN`case'; p['access_changes'][0]['system']='system | extra\n<literal>'
        p['evidence'][0]['system']=p['access_changes'][0]['system']
        p['summary']='[example](not-a-link)'
        result=access.review_all(access.load_cases({'cases':[p]})); before=copy.deepcopy(result)
        matrix=access.render_matrix(result);scenarios=access.render_scenarios(result)
        self.assertIn('system \\| extra<br>&lt;literal&gt;',matrix)
        self.assertIn('SYN\\`case',matrix)
        self.assertIn('\\[example\\]',scenarios)
        self.assertEqual(result,before)

    def test_actual_module_cli_writes_four_readable_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=[Path(temp)/name for name in ['report.json','matrix.csv','matrix.md','scenarios.md']]
            args=[]
            for flag,path in zip(['--json-out','--csv-out','--matrix-out','--scenarios-out'],paths):args += [flag,str(path)]
            p=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-m','revenue.uiowa_rfq_18649_access_lifecycle.access_lifecycle','--cases',str(FIXTURE),*args],cwd=HERE.parents[1],capture_output=True,text=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(paths[0].read_text())['counts']['systems_reviewed'],13)
            self.assertTrue(all(path.stat().st_size for path in paths))
            self.assertIn('13 system rows',p.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)

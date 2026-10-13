"""Capture-to-register integrity, all records deliberately fictional."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import interview_adapter as ia

ROOT = Path(__file__).parent
SESSION = ROOT / 'data/session.json'
REGISTER = ROOT / 'data/source_register.json'
HOSTILE = ROOT / 'data/session_hostile.json'


class CaptureIntegrity(unittest.TestCase):
    def setUp(self):
        self.session = ia.load_json(SESSION)
        self.register = ia.load_json(REGISTER)

    def reject(self, session=None, register=None):
        with self.assertRaises(ia.LoadError):
            ia.adapt(self.session if session is None else session,
                     self.register if register is None else register)

    def test_duplicate_ids_cannot_change_attribution_or_links(self):
        for field, key in [('participants', 'participant_id'), ('questions', 'question_id'), ('notes', 'note_id')]:
            with self.subTest(field=field):
                session = copy.deepcopy(self.session)
                duplicate = copy.deepcopy(session[field][0])
                duplicate['role' if field == 'participants' else 'text'] = 'different fictional account'
                session[field].append(duplicate)
                self.reject(session=session)
        reg = copy.deepcopy(self.register)
        reg['sources'].append(dict(reg['sources'][0], locator='different-record'))
        self.reject(register=reg)

    def test_unicode_equivalent_identifiers_do_not_alias(self):
        session = copy.deepcopy(self.session)
        session['participants'].extend([
            {'participant_id': 'caf\u00e9', 'role': 'fictional A', 'group': 'ESS'},
            {'participant_id': 'cafe\u0301', 'role': 'fictional B', 'group': 'ESS'}])
        self.reject(session=session)

    def test_in_memory_api_preserves_personal_key_refusal(self):
        for field in ('name', 'email', 'employee_id'):
            session = copy.deepcopy(self.session)
            session['notes'][0]['extra'] = {field: 'fictional-only'}
            with self.subTest(field=field):
                self.reject(session=session)

    def test_invalid_containers_and_required_fields_are_typed(self):
        for field in ('participants', 'questions', 'notes'):
            for value in (None, {}, 'not a list', [None]):
                session = copy.deepcopy(self.session); session[field] = value
                with self.subTest(field=field, value=value): self.reject(session=session)
        for value in ('', ' ', None, 0, False, [], '\ud800'):
            session = copy.deepcopy(self.session); session['notes'][0]['note_id'] = value
            with self.subTest(value=repr(value)): self.reject(session=session)

    def test_empty_statement_is_not_evidence_or_answer(self):
        for value in (None, '', ' \n', 7, True):
            session = copy.deepcopy(self.session); session['notes'][0]['stated_practice'] = value
            with self.subTest(value=value): self.reject(session=session)

    def test_optional_capture_fields_cannot_be_silent_nontext(self):
        for field in ('concrete_example', 'corroborating_artifact', 'disagrees_with', 'follow_up'):
            for value in ([], {}, False, 7):
                session = copy.deepcopy(self.session); session['notes'][0][field] = value
                with self.subTest(field=field, value=value): self.reject(session=session)

    def test_duplicate_json_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            for raw in ('{"notes": [], "notes": []}', '{"x":{"value":1,"value":2}}'):
                path.write_text(raw, encoding='utf-8')
                with self.subTest(raw=raw), self.assertRaises(ia.LoadError): ia.load_json(path)

    def test_invalid_json_numbers_and_encoding_are_typed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            for raw in (b'{"x": NaN}', b'{"x": Infinity}', b'{"x": 1e999}', b'\xff', b'{'):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(ia.LoadError): ia.load_json(path)

    def test_unresolved_disagreement_never_becomes_corroborated(self):
        session = copy.deepcopy(self.session)
        session['notes'][2]['disagrees_with'] = 'N-NOT-SUPPLIED'
        records, diagnostics, _ = ia.adapt(session, self.register)
        row = next(r for r in records if r['record_id'].endswith('-N3'))
        self.assertEqual(row['status'], ia.DISPUTED)
        self.assertFalse(row['supports_finding'])
        self.assertIn('N-NOT-SUPPLIED', row['disputed_with'])
        self.assertIn('absent', row['basis'])
        self.assertNotIn('Both notes are retained', row['basis'])
        self.assertTrue(any(d['code'] == 'DISAGREEMENT_TARGET_MISSING' for d in diagnostics))

    def test_rendered_missing_account_is_not_described_as_retained(self):
        session = copy.deepcopy(self.session)
        session['notes'][2]['disagrees_with'] = 'N-NOT-SUPPLIED'
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'session.json'; source.write_text(json.dumps(session),encoding='utf-8')
            folder=Path(tmp)/'out'; ia.build(source,REGISTER,folder)
            text=(folder/'session_report.md').read_text(encoding='utf-8')
            block=text.split('### EV-INT-2026-03-11-ESS-N3',1)[1].split('### ',1)[0]
            self.assertIn('counterpart not imported',block)
            self.assertNotIn('both notes retained',block)

    def test_self_disagreement_cannot_manufacture_a_second_account(self):
        session = copy.deepcopy(self.session); session['notes'][0]['disagrees_with'] = 'N1'
        self.reject(session=session)

    def test_incomplete_artifact_metadata_cannot_support_finding(self):
        for key, value in [('kind', None), ('kind', ''), ('kind', 'UNKNOWN'),
                           ('kind', 'INTERVIEW'), ('locator', None), ('locator', ''), ('locator', '  ')]:
            register = copy.deepcopy(self.register)
            target = next(s for s in register['sources'] if s['source_id'] == 'SRC-ESS-TEST-RUN')
            target[key] = value
            with self.subTest(key=key, value=value):
                records, diagnostics, _ = ia.adapt(self.session, register)
                row = next(r for r in records if r['record_id'].endswith('-N3'))
                self.assertFalse(row['supports_finding'])
                self.assertNotEqual(row['status'], ia.CORROBORATED)
                self.assertTrue(any(d['severity'] == ia.ERROR and d['note_id'] == 'N3' for d in diagnostics))

    def test_coverage_excludes_unresolved_participants(self):
        session = copy.deepcopy(self.session)
        session['notes'].append(dict(session['notes'][0], note_id='N404', participant_id='P404'))
        _, _, coverage = ia.adapt(session, self.register)
        self.assertTrue(all('P404' not in c['answered_by'] for c in coverage))

    def test_adapt_does_not_rewrite_input(self):
        before = copy.deepcopy((self.session, self.register))
        ia.adapt(self.session, self.register)
        self.assertEqual(before, (self.session, self.register))

    def test_quarantine_retains_unimported_accounts_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ia.build(HOSTILE, REGISTER, tmp)
            receipt = json.loads((Path(tmp)/'capture_review.json').read_text())
        self.assertEqual(receipt['input_notes'], 8)
        self.assertEqual(receipt['imported_records'], 6)
        self.assertEqual({n['note_id'] for n in receipt['unimported_notes']}, {'H4','H5'})
        self.assertTrue(all(n['stated_practice'] for n in receipt['unimported_notes']))
        self.assertEqual(receipt['state'], 'REVIEW_REQUIRED')
        self.assertFalse(receipt['source_authenticity_established'])
        self.assertFalse(receipt['finding_verified'])

    def test_import_with_errors_has_nonzero_exit_and_retains_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ia.main(['import','--session',str(HOSTILE),'--register',str(REGISTER),'--out',tmp])
            self.assertEqual(result, 1)
            self.assertTrue((Path(tmp)/'session_report.md').is_file())

    def test_existing_report_and_source_paths_are_never_rewritten(self):
        for name in ('evidence_records.json','evidence_records.csv','session_report.md','capture_review.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp); target=folder/name; target.write_bytes(b'prior-evidence')
                with self.assertRaises((ia.LoadError, OSError)): ia.build(SESSION, REGISTER, folder)
                self.assertEqual({p.name:p.read_bytes() for p in folder.iterdir()}, {name:b'prior-evidence'})

    def test_repeat_build_preserves_entire_first_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            ia.build(SESSION, REGISTER, tmp)
            before={p.name:p.read_bytes() for p in Path(tmp).iterdir()}
            with self.assertRaises((ia.LoadError, OSError)): ia.build(HOSTILE, REGISTER, tmp)
            self.assertEqual(before,{p.name:p.read_bytes() for p in Path(tmp).iterdir()})

    def test_symlink_output_folder_and_symlink_ancestor_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); target=home/'target';target.mkdir(); link=home/'link';link.symlink_to(target, target_is_directory=True)
            for out in (link,link/'child'):
                with self.subTest(out=out), self.assertRaises((ia.LoadError,OSError)): ia.build(SESSION,REGISTER,out)
            self.assertEqual(list(target.iterdir()),[])

    def test_direct_writers_are_also_exclusive(self):
        records,diagnostics,coverage=ia.adapt(self.session,self.register)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'prior';target.write_bytes(b'prior')
            with self.assertRaises(FileExistsError): ia.write_records_csv(target,records)
            with self.assertRaises(FileExistsError): ia.write_report(target,self.session,records,diagnostics,coverage)
            self.assertEqual(target.read_bytes(),b'prior')

    def test_render_failure_does_not_publish_partial_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'new'
            with patch.object(ia,'write_report',side_effect=OSError('synthetic render failure')):
                with self.assertRaises(OSError): ia.build(SESSION,REGISTER,folder)
            self.assertFalse(folder.exists())

    def test_snapshot_hashes_bind_actual_consumed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            ia.build(SESSION,REGISTER,tmp)
            receipt=json.loads((Path(tmp)/'capture_review.json').read_text())
            for label,path in [('session',SESSION),('register',REGISTER)]:
                self.assertEqual(receipt['inputs'][label]['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(receipt['inputs'][label]['bytes'],path.stat().st_size)
            for name,binding in receipt['outputs'].items():
                self.assertEqual(binding['sha256'],hashlib.sha256((Path(tmp)/name).read_bytes()).hexdigest())

    def test_formula_text_and_nulls_remain_distinct(self):
        for value in ('-SUM(A1)', ' =1', '\t+1', '@x', '=1', '+1'):
            with self.subTest(value=value): self.assertTrue(ia.csv_cell(value).startswith("'"))
        self.assertNotEqual(ia.csv_cell(None),ia.csv_cell('\\N'))
        self.assertNotEqual(ia.csv_cell(None),ia.csv_cell(''))

    def test_cli_bad_json_and_output_failures_do_not_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.json';path.write_text('{')
            for source in (path,Path(tmp)/'absent.json'):
                proc=subprocess.run([sys.executable,'-O',str(ROOT/'interview_adapter.py'),'check',
                    '--session',str(source),'--register',str(REGISTER),'--out',str(Path(tmp)/'out')],capture_output=True,text=True,timeout=10)
                self.assertEqual(proc.returncode,2)
                self.assertNotIn('Traceback',proc.stderr)
                self.assertIn('REFUSED',proc.stdout)



class Rehearsal(unittest.TestCase):
    def test_actual_three_stage_rehearsal(self):
        import rehearse_capture
        with tempfile.TemporaryDirectory() as tmp:
            before={p.name:p.read_bytes() for p in (ROOT/'data').iterdir() if p.is_file()}
            report=rehearse_capture.run(Path(tmp)/'new')
            self.assertEqual([s['records'] for s in report['scenarios']],[11,11,12])
            self.assertEqual([s['counts']['CORROBORATED'] for s in report['scenarios']],[3,2,2])
            self.assertEqual([s['counts']['DISPUTED'] for s in report['scenarios']],[4,5,6])
            self.assertEqual([s['changed_note']['supports_finding'] for s in report['scenarios']],[True,False,False])
            self.assertEqual([s['errors'] for s in report['scenarios']],[0,1,0])
            self.assertFalse(report['finding_verified'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in (ROOT/'data').iterdir() if p.is_file()})

    def test_rehearsal_reproduces_and_preserves_existing_destination(self):
        import rehearse_capture
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); first=rehearse_capture.run(home/'first');second=rehearse_capture.run(home/'second')
            self.assertEqual(first,second)
            before={str(p.relative_to(home)):p.read_bytes() for p in home.rglob('*') if p.is_file()}
            with self.assertRaises((ia.LoadError,OSError)):rehearse_capture.run(home/'first')
            self.assertEqual(before,{str(p.relative_to(home)):p.read_bytes() for p in home.rglob('*') if p.is_file()})


if __name__=='__main__':unittest.main()

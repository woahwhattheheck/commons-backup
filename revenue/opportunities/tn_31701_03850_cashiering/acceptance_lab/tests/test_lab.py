from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from cashiering_lab.core import InputError, MAX_BYTES, canonical, parse, reconcile
from cashiering_lab.artifacts import ALL_FILES, as_csv, bundle, read_input, verify, write_bundle

ROOT = Path(__file__).resolve().parents[1]


def case():
    return json.loads((ROOT / "examples/clean.json").read_bytes())


def report(data):
    return reconcile(canonical(data))


def codes(data):
    return {r["code"] for r in report(data)["findings"]}


class SchemaTests(unittest.TestCase):
    def test_clean_input(self):
        self.assertEqual(report(case())["findings_count"],0)

    def test_duplicate_json_keys(self):
        with self.assertRaises(InputError): parse(b'{"schema":"x","schema":"y"}')

    def test_nonfinite_json(self):
        for value in (b'NaN',b'Infinity',b'-Infinity'):
            with self.subTest(value=value), self.assertRaises(InputError): parse(value)

    def test_invalid_utf8(self):
        with self.assertRaises(InputError): parse(b'\xff')

    def test_input_bound(self):
        with self.assertRaises(InputError): parse(b' '*(MAX_BYTES+1))

    def test_boolean_money(self):
        d=case(); d['transactions'][0]['collected_minor']=True
        with self.assertRaises(InputError): report(d)

    def test_float_money(self):
        d=case(); d['transactions'][0]['original_minor']=10002.0
        with self.assertRaises(InputError): report(d)

    def test_extra_fields(self):
        d=case(); d['transactions'][0]['pan']='not accepted'
        with self.assertRaises(InputError): report(d)

    def test_missing_field(self):
        d=case(); del d['batches'][0]['counted_cash_minor']
        with self.assertRaises(InputError): report(d)

    def test_duplicate_transaction(self):
        d=case(); d['transactions'].append(copy.deepcopy(d['transactions'][0]))
        with self.assertRaises(InputError): report(d)

    def test_duplicate_batch(self):
        d=case(); d['batches'].append(copy.deepcopy(d['batches'][0]))
        with self.assertRaises(InputError): report(d)

    def test_duplicate_deposit(self):
        d=case(); d['deposits'].append(copy.deepcopy(d['deposits'][0]))
        with self.assertRaises(InputError): report(d)

    def test_duplicate_tender(self):
        d=case(); d['transactions'][0]['tenders'].append(copy.deepcopy(d['transactions'][0]['tenders'][0]))
        with self.assertRaises(InputError): report(d)

    def test_duplicate_allocation(self):
        d=case(); d['transactions'][0]['allocations'].append(copy.deepcopy(d['transactions'][0]['allocations'][0]))
        with self.assertRaises(InputError): report(d)

    def test_unhashable_kind(self):
        d=case(); d['transactions'][0]['kind']=[]
        with self.assertRaises(InputError): report(d)

    def test_unhashable_tender(self):
        d=case(); d['deposits'][0]['tender']=[]
        with self.assertRaises(InputError): report(d)

    def test_unknown_currency(self):
        d=case(); d['batches'][0]['currency']='EUR'
        with self.assertRaises(InputError): report(d)

    def test_invalid_currency_scale(self):
        for value in (True,-1,5,2.0):
            d=case(); d['currency_scale']['USD']=value
            with self.subTest(value=value),self.assertRaises(InputError): report(d)

    def test_naive_timestamp(self):
        d=case(); d['transactions'][0]['timestamp']='2026-09-16T09:00:00'
        with self.assertRaises(InputError): report(d)

    def test_out_of_range_numeric_offsets(self):
        for offset in ('+00:60', '-00:99', '+23:60', '+24:00', '-24:00'):
            d=case(); d['transactions'][0]['timestamp']='2026-09-16T09:00:00'+offset
            with self.subTest(offset=offset),self.assertRaises(InputError): report(d)

    def test_valid_non_hour_offset_has_same_instant(self):
        d=case(); original=d['transactions'][0]['timestamp']
        d['transactions'][0]['timestamp']='2026-09-16T19:30:00+05:30'
        from cashiering_lab.core import _time
        self.assertEqual(_time(d['transactions'][0]['timestamp'],'test'),_time(original,'test'))
        self.assertEqual(report(d)['findings_count'],0)

    def test_invalid_calendar_date(self):
        d=case(); d['transactions'][0]['timestamp']='2026-02-30T09:00:00Z'
        with self.assertRaises(InputError): report(d)

    def test_open_after_close(self):
        d=case(); d['batches'][0]['opened_at']=d['batches'][0]['closed_at']
        with self.assertRaises(InputError): report(d)

    def test_batch_outside_period(self):
        d=case(); d['batches'][0]['opened_at']='2026-09-15T08:00:00-05:00'
        with self.assertRaises(InputError): report(d)

    def test_unknown_batch_reference(self):
        d=case(); d['transactions'][0]['batch_id']='UNKNOWN'
        with self.assertRaises(InputError): report(d)

    def test_unknown_deposit_batch(self):
        d=case(); d['deposits'][0]['batch_ids'].append('UNKNOWN')
        with self.assertRaises(InputError): report(d)

    def test_repeated_batch_within_deposit(self):
        d=case(); d['deposits'][0]['batch_ids'].append('B1')
        with self.assertRaises(InputError): report(d)

    def test_negative_float(self):
        d=case(); d['batches'][0]['opening_cash_minor']=-1
        with self.assertRaises(InputError): report(d)

    def test_empty_batches(self):
        d=case(); d['batches']=[]
        with self.assertRaises(InputError): report(d)

    def test_monetary_bound(self):
        d=case(); d['transactions'][0]['collected_minor']=10**15+1
        with self.assertRaises(InputError): report(d)

    def test_control_character(self):
        d=case(); d['batches'][0]['variance_reason']='bad\nreason'
        with self.assertRaises(InputError): report(d)

    def test_del_and_c1_controls_are_rejected(self):
        for control in ('\x7f', '\x80', '\x85', '\x9f'):
            d=case(); d['batches'][0]['variance_reason']='reason'+control
            with self.subTest(control=repr(control)),self.assertRaises(InputError): report(d)

    def test_unpaired_surrogate(self):
        d=case(); d['batches'][0]['variance_reason']='\ud800'
        with self.assertRaises(InputError): report(d)


class EconomicsTests(unittest.TestCase):
    def test_rounding_conservation(self):
        d=case(); d['transactions'][0]['rounding_minor']=1
        self.assertIn('ROUNDING_CONSERVATION',codes(d))

    def test_tender_conservation(self):
        d=case(); d['transactions'][0]['tenders'][0]['amount_minor']+=1
        self.assertIn('TENDER_CONSERVATION',codes(d))

    def test_allocation_conservation(self):
        d=case(); d['transactions'][0]['allocations'][0]['amount_minor']+=1
        self.assertIn('ALLOCATION_CONSERVATION',codes(d))

    def test_opposite_sign_components_do_not_net_away(self):
        d=case(); d['transactions'][0]['tenders']=[{'type':'CASH','amount_minor':11000},{'type':'CARD','amount_minor':-1000}]
        self.assertIn('COMPONENT_SIGN',codes(d))

    def test_receipt_sign(self):
        d=case(); d['transactions'][0]['collected_minor']=-10000
        self.assertIn('TRANSACTION_SIGN',codes(d))

    def test_refund_sign(self):
        d=case(); d['transactions'][2]['collected_minor']=500
        self.assertIn('TRANSACTION_SIGN',codes(d))

    def test_unknown_original(self):
        d=case(); d['transactions'][2]['original_id']='MISSING'
        self.assertIn('INVALID_ORIGINAL',codes(d))

    def test_original_is_not_receipt(self):
        d=case(); d['transactions'][2]['original_id']='T3'
        self.assertIn('INVALID_ORIGINAL',codes(d))

    def test_receipt_has_original(self):
        d=case(); d['transactions'][0]['original_id']='T2'
        self.assertIn('RECEIPT_HAS_ORIGINAL',codes(d))

    def test_refund_not_strictly_after_original(self):
        d=case(); d['transactions'][2]['timestamp']=d['transactions'][0]['timestamp']
        self.assertIn('ORIGINAL_NOT_EARLIER',codes(d))

    def test_refund_foreign_scope(self):
        d=case(); d['transactions'][2]['batch_id']='B2'; d['batches'][1]['agency']='OTHER'
        self.assertIn('ORIGINAL_SCOPE_MISMATCH',codes(d))

    def test_cumulative_refund_cap(self):
        d=case(); t=copy.deepcopy(d['transactions'][2]); t.update(id='T5',evidence_ref='ROW5',original_minor=-9900,collected_minor=-9900)
        t['tenders']=[{'type':'CASH','amount_minor':-9900}]; t['allocations']=[{'account_id':'FEES','amount_minor':-9900}]; d['transactions'].append(t)
        self.assertIn('REFUND_EXCEEDS_ORIGINAL',codes(d))

    def test_tender_cap_even_when_total_under_original(self):
        d=case(); t=d['transactions'][2]; t.update(original_minor=-6500,collected_minor=-6500)
        t['tenders']=[{'type':'CASH','amount_minor':-6500}]; t['allocations']=[{'account_id':'FEES','amount_minor':-6500}]
        self.assertIn('REFUND_COMPONENT_EXCEEDS_ORIGINAL',codes(d))

    def test_allocation_cap_even_when_total_under_original(self):
        d=case(); t=d['transactions'][2]; t['allocations']=[{'account_id':'UNSEEN','amount_minor':-500}]
        self.assertIn('REFUND_COMPONENT_EXCEEDS_ORIGINAL',codes(d))

    def test_rounding_refund_interval(self):
        d=case(); t=d['transactions'][2]; t.update(original_minor=-503,rounding_minor=3,collected_minor=-500)
        self.assertIn('REFUND_ROUNDING_EXCEEDS_ORIGINAL',codes(d))

    def test_full_reversal_exact(self):
        d=case(); original=d['transactions'][0]; t=d['transactions'][2]; t['kind']='REVERSAL'
        for key in ('original_minor','rounding_minor','collected_minor'): t[key]=-original[key]
        for key in ('tenders','allocations'):
            t[key]=copy.deepcopy(original[key])
            for row in t[key]: row['amount_minor']=-row['amount_minor']
        c=codes(d)
        self.assertNotIn('FULL_REVERSAL_MISMATCH',c)
        self.assertNotIn('REFUND_ROUNDING_EXCEEDS_ORIGINAL',c)
        self.assertNotIn('REFUND_COMPONENT_EXCEEDS_ORIGINAL',c)

    def test_full_reversal_wrong_rounding(self):
        d=case(); d['transactions'][2]['kind']='REVERSAL'
        self.assertIn('FULL_REVERSAL_MISMATCH',codes(d))

    def test_reversal_after_prior_refund(self):
        d=case(); original=d['transactions'][0]; t=copy.deepcopy(d['transactions'][2]); t.update(id='T5',evidence_ref='ROW5',kind='REVERSAL',timestamp='2026-09-16T12:00:00-05:00')
        for key in ('original_minor','rounding_minor','collected_minor'): t[key]=-original[key]
        for key in ('tenders','allocations'):
            t[key]=copy.deepcopy(original[key])
            for row in t[key]: row['amount_minor']=-row['amount_minor']
        d['transactions'].append(t)
        self.assertIn('FULL_REVERSAL_MISMATCH',codes(d))

    def test_batch_half_open_window(self):
        d=case(); d['transactions'][0]['timestamp']=d['batches'][0]['closed_at']
        self.assertIn('TRANSACTION_OUTSIDE_BATCH',codes(d))

    def test_evidence_reuse(self):
        d=case(); d['transactions'][1]['evidence_ref']=d['transactions'][0]['evidence_ref']
        self.assertIn('REUSED_TRANSACTION_EVIDENCE',codes(d))

    def test_missing_cash_not_zero(self):
        d=case(); d['batches'][0]['counted_cash_minor']=None
        r=report(d); self.assertIn('MISSING_CASH_COUNT',codes(d))
        self.assertIsNone(r['batches'][0]['drawer_variance_minor'])
        cash=next(x for x in r['deposits'] if x['tender']=='CASH')
        self.assertIsNone(cash['expected_minor'])
        self.assertIsNone(cash['deposit_variance_minor'])

    def test_missing_deposit_not_zero(self):
        d=case(); d['deposits'][0]['observed_minor']=None
        r=report(d); self.assertIn('MISSING_DEPOSIT_EVIDENCE',codes(d))
        cash=next(x for x in r['deposits'] if x['tender']=='CASH')
        self.assertIsNone(cash['deposit_variance_minor'])

    def test_drawer_and_deposit_discrepancy_separate(self):
        d=case(); d['batches'][0]['counted_cash_minor']-=25; d['deposits'][0]['observed_minor']-=50
        r=report(d); self.assertEqual(r['batches'][0]['drawer_variance_minor'],-25)
        cash=next(x for x in r['deposits'] if x['tender']=='CASH')
        self.assertEqual(cash['expected_minor'],12475)
        self.assertEqual(cash['deposit_variance_minor'],-25)

    def test_drawer_shortage_not_double_counted(self):
        d=case(); d['batches'][0]['counted_cash_minor']-=25; d['deposits'][0]['observed_minor']-=25
        r=report(d); self.assertIn('DRAWER_VARIANCE',codes(d)); self.assertNotIn('DEPOSIT_VARIANCE',codes(d))
        self.assertNotEqual(r['findings_count'],0)

    def test_threshold_strictly_exceeded(self):
        d=case(); d['batches'][0]['counted_cash_minor']-=20
        self.assertNotIn('DRAWER_REASON_MISSING',codes(d))
        d['batches'][0]['counted_cash_minor']-=1
        self.assertIn('DRAWER_REASON_MISSING',codes(d))

    def test_reason_does_not_clear_variance(self):
        d=case(); d['batches'][0]['counted_cash_minor']-=21; d['batches'][0]['variance_reason']='Under review'
        self.assertIn('DRAWER_VARIANCE',codes(d)); self.assertNotIn('DRAWER_REASON_MISSING',codes(d))

    def test_retained_float_over_count(self):
        d=case(); d['batches'][0]['retained_cash_minor']=20000
        self.assertIn('RETAINED_CASH_EXCEEDS_COUNT',codes(d))

    def test_missing_declaration(self):
        d=case(); d['batches'][0]['declared_total_minor']=None
        self.assertIn('MISSING_BATCH_DECLARATION',codes(d))

    def test_wrong_declaration(self):
        d=case(); d['batches'][0]['declared_total_minor']+=1
        self.assertIn('BATCH_TOTAL_VARIANCE',codes(d))

    def test_duplicate_deposit_assignment(self):
        d=case(); t=copy.deepcopy(d['deposits'][0]); t.update(id='D_SECOND',evidence_ref='D_SECOND_ROW'); d['deposits'].append(t)
        self.assertIn('BATCH_TENDER_REUSED',codes(d))

    def test_deposit_evidence_reuse(self):
        d=case(); d['deposits'][1]['evidence_ref']=d['deposits'][0]['evidence_ref']
        self.assertIn('REUSED_DEPOSIT_EVIDENCE',codes(d))

    def test_deposit_scope_mismatch(self):
        for key in ('agency','business_unit','department','bank_account','location'):
            d=case(); d['deposits'][0][key]='OTHER'
            with self.subTest(key=key): self.assertIn('DEPOSIT_SCOPE_MISMATCH',codes(d))

    def test_deposit_currency_mismatch(self):
        d=case(); d['currency_scale']['EUR']=2; d['deposits'][0]['currency']='EUR'
        r=report(d); self.assertIn('DEPOSIT_SCOPE_MISMATCH',codes(d))
        cash=next(x for x in r['deposits'] if x['tender']=='CASH'); self.assertIsNone(cash['expected_minor'])

    def test_unassigned_tender(self):
        d=case(); d['deposits'].pop()
        self.assertIn('UNASSIGNED_BATCH_TENDER',codes(d))

    def test_opposing_deposit_variances_stay_visible(self):
        d=case(); d['deposits'][0]['observed_minor']-=100; d['deposits'][1]['observed_minor']+=100
        r=report(d); self.assertEqual(sum(f['code']=='DEPOSIT_VARIANCE' for f in r['findings']),2)
        self.assertEqual(r['status'],'EXCEPTIONS')

    def test_currency_isolation(self):
        d=case(); d['currency_scale']['JPY']=0; d['batches'][1]['currency']='JPY'; d['deposits'][0]['batch_ids']=['B1']; d['deposits'][0]['observed_minor']=8500
        dep=copy.deepcopy(d['deposits'][0]); dep.update(id='D_JPY',currency='JPY',batch_ids=['B2'],observed_minor=4000,evidence_ref='ROW_JPY'); d['deposits'].append(dep)
        r=report(d); self.assertEqual(r['findings_count'],0)
        self.assertEqual([(x['currency'],x['candidate_net_collected_minor']) for x in r['currency_totals']],[('JPY',4000),('USD',12500)])
        self.assertNotIn('grand_total',r)

    def test_invalid_rows_not_silently_dropped(self):
        d=case(); d['transactions'][0]['tenders'][0]['amount_minor']+=10
        r=report(d); self.assertEqual(len(r['transactions']),4); self.assertEqual(r['currency_totals'][0]['candidate_net_collected_minor'],16500)
        self.assertEqual(r['status'],'EXCEPTIONS')

    def test_all_authority_false(self):
        self.assertTrue(all(v is False for v in report(case())['authority'].values()))

    def test_synthetic_exception_fixture(self):
        r=reconcile((ROOT/'examples/exceptions.json').read_bytes())
        self.assertEqual(r['findings_count'],6)
        self.assertEqual({f['code'] for f in r['findings']},{'ALLOCATION_CONSERVATION','BATCH_TOTAL_VARIANCE','DRAWER_VARIANCE','DRAWER_REASON_MISSING','DEPOSIT_VARIANCE','DEPOSIT_REASON_MISSING'})

    def test_semantic_input_permutation(self):
        d=case(); r=report(d); d['transactions'].reverse(); d['batches'].reverse(); d['deposits'].reverse()
        for t in d['transactions']: t['tenders'].reverse(); t['allocations'].reverse()
        for dep in d['deposits']: dep['batch_ids'].reverse()
        rr=report(d); r.pop('input_sha256'); rr.pop('input_sha256'); self.assertEqual(r,rr)

    def test_timezone_equivalence(self):
        d=case(); r=report(d)
        d['transactions'][0]['timestamp']='2026-09-16T14:00:00Z'
        rr=report(d); self.assertEqual(r['findings'],rr['findings']); self.assertEqual(r['batches'],rr['batches'])

    def test_randomized_integer_conservation_1000_cases(self):
        rng=random.Random(20260917)
        for i in range(1000):
            d=case(); d['transactions']=[]; d['batches']=d['batches'][:1]; d['deposits']=[]
            b=d['batches'][0]; total=0; tender_totals={'CASH':0,'CARD':0}
            for j in range(rng.randint(1,12)):
                amount=rng.randint(1,10**9); cash=rng.randint(0,amount); card=amount-cash; rounding=rng.randint(-4,4)
                if amount-rounding<=0: rounding=0
                alloc=rng.randint(0,amount)
                t=dict(id=f'R{j}',batch_id='B1',kind='RECEIPT',timestamp=f'2026-09-16T09:{j:02}:00-05:00',original_id=None,original_minor=amount-rounding,rounding_minor=rounding,collected_minor=amount,tenders=[dict(type='CASH',amount_minor=cash),dict(type='CARD',amount_minor=card)],allocations=[dict(account_id='A',amount_minor=alloc),dict(account_id='B',amount_minor=amount-alloc)],evidence_ref=f'ROW{j}')
                d['transactions'].append(t); total+=amount; tender_totals['CASH']+=cash; tender_totals['CARD']+=card
            b['declared_total_minor']=total; b['counted_cash_minor']=b['opening_cash_minor']+tender_totals['CASH']
            for tender,amount in tender_totals.items():
                if amount:
                    d['deposits'].append(dict(id=f'D_{tender}',**{k:b[k] for k in ('agency','business_unit','department','location','bank_account','currency')},tender=tender,batch_ids=['B1'],observed_minor=amount,variance_reason=None,evidence_ref=f'DROW_{tender}'))
            with self.subTest(case=i): self.assertEqual(report(d)['findings_count'],0)


class ArtifactTests(unittest.TestCase):
    def test_same_bytes_deterministic(self):
        raw=canonical(case()); self.assertEqual(bundle(raw),bundle(raw))

    def test_exact_replay(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; write_bundle(p,bundle(canonical(case())))
            self.assertEqual(set(x.name for x in p.iterdir()),ALL_FILES)
            result=verify(p); self.assertEqual(result['verification'],'EXACT_REPLAY_MATCH')
            self.assertEqual(result['source_authenticity'],'NOT_ATTESTED')

    def test_exception_bundle_verifies_without_becoming_clean(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; write_bundle(p,bundle((ROOT/'examples/exceptions.json').read_bytes()))
            result=verify(p); self.assertEqual(result['report_status'],'EXCEPTIONS'); self.assertEqual(result['findings_count'],6)

    def test_no_overwrite_existing_directory(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; p.mkdir(); (p/'foreign').write_text('preserve')
            with self.assertRaises(FileExistsError): write_bundle(p,bundle(canonical(case())))
            self.assertEqual((p/'foreign').read_text(),'preserve')

    def test_every_artifact_tamper_rejected(self):
        for name in sorted(ALL_FILES):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                p=Path(td)/'out'; write_bundle(p,bundle(canonical(case()))); (p/name).write_bytes((p/name).read_bytes()+b' ')
                with self.assertRaises(InputError): verify(p)

    def test_self_reminted_manifest_does_not_mask_report_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; write_bundle(p,bundle(canonical(case())))
            obj=json.loads((p/'report.json').read_bytes()); obj['findings_count']=0; obj['authority']['erp_posting']=True
            changed=canonical(obj); (p/'report.json').write_bytes(changed)
            manifest=json.loads((p/'manifest.json').read_bytes()); manifest['files']['report.json']={'bytes':len(changed),'sha256':hashlib.sha256(changed).hexdigest()}; (p/'manifest.json').write_bytes(canonical(manifest))
            with self.assertRaises(InputError): verify(p)

    def test_extra_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; write_bundle(p,bundle(canonical(case()))); (p/'extra').write_text('x')
            with self.assertRaises(InputError): verify(p)

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; write_bundle(p,bundle(canonical(case()))); (p/'exceptions.csv').unlink()
            with self.assertRaises(InputError): verify(p)

    @unittest.skipUnless(os.name=='posix','POSIX-specific filesystem contract')
    def test_symlink_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; write_bundle(p,bundle(canonical(case()))); raw=(p/'input.json').read_bytes(); (Path(td)/'other').write_bytes(raw); (p/'input.json').unlink(); (p/'input.json').symlink_to(Path(td)/'other')
            with self.assertRaises(OSError): verify(p)

    @unittest.skipUnless(os.name=='posix','POSIX-specific filesystem contract')
    def test_symlink_directory_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'; write_bundle(p,bundle(canonical(case()))); link=Path(td)/'link'; link.symlink_to(p,target_is_directory=True)
            with self.assertRaises(OSError): verify(link)

    @unittest.skipUnless(os.name=='posix','POSIX-specific filesystem contract')
    def test_fifo_input_does_not_block(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'pipe'; os.mkfifo(p)
            with self.assertRaises(InputError): read_input(p)

    def test_partial_write_is_handled(self):
        real=os.write
        def partial(fd,data): return real(fd,data[:max(1,min(len(data),13))])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'
            with mock.patch('cashiering_lab.artifacts.os.write',side_effect=partial): write_bundle(p,bundle(canonical(case())))
            self.assertEqual(verify(p)['verification'],'EXACT_REPLAY_MATCH')

    def test_failed_write_leaves_invalid_partial_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out'
            with mock.patch('cashiering_lab.artifacts.os.write',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): write_bundle(p,bundle(canonical(case())))
            self.assertFalse((p/'manifest.json').exists())
            with self.assertRaises(InputError): verify(p)

    def test_html_escapes_untrusted_reason(self):
        d=case(); d['batches'][0]['variance_reason']='<script>alert(1)</script>'
        # Reasons are shown in CSV, and HTML table escaping is separately tested on actual table values.
        from cashiering_lab.artifacts import _table
        text=_table([{'reason':d['batches'][0]['variance_reason']}],['reason'])
        self.assertIn('&lt;script&gt;',text); self.assertNotIn('<script>',text)
        self.assertNotIn(b'<script',bundle(canonical(d))['report.html'])

    def test_csv_formula_escaping_and_numeric_negative(self):
        data=as_csv([{'text':' =SUM(A1:A2)','n':-25,'missing':None}],['text','n','missing']).decode()
        self.assertIn("' =SUM",data); self.assertIn(',-25,MISSING',data)

    def test_expected_absence_is_not_missing_evidence(self):
        generated=bundle(canonical(case()))
        self.assertIn(b'RECEIPT,2026-09-16T09:00:00-05:00,N/A,USD',generated['transactions.csv'])
        self.assertIn(b'CARD: 4,000; CASH: 6,000',generated['report.html'])

    def test_cli_clean_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bundle'
            cmd=[sys.executable,'-m','cashiering_lab','compile',str(ROOT/'examples/clean.json'),'--out',str(p)]
            completed=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=15)
            self.assertEqual(completed.returncode,0,completed.stderr)
            completed=subprocess.run([sys.executable,'-m','cashiering_lab','verify',str(p)],cwd=ROOT,capture_output=True,text=True,timeout=15)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['verification'],'EXACT_REPLAY_MATCH')

    def test_cli_exceptions_exit_one(self):
        with tempfile.TemporaryDirectory() as td:
            completed=subprocess.run([sys.executable,'-m','cashiering_lab','compile',str(ROOT/'examples/exceptions.json'),'--out',str(Path(td)/'bundle')],cwd=ROOT,capture_output=True,text=True,timeout=15)
            self.assertEqual(completed.returncode,1,completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['findings_count'],6)

    def test_cli_bad_input_exit_two(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.json'; p.write_text('{')
            completed=subprocess.run([sys.executable,'-m','cashiering_lab','compile',str(p),'--out',str(Path(td)/'bundle')],cwd=ROOT,capture_output=True,text=True,timeout=15)
            self.assertEqual(completed.returncode,2); self.assertFalse((Path(td)/'bundle').exists())


if __name__=='__main__': unittest.main()

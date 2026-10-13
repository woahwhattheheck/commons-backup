# SPDX-License-Identifier: Apache-2.0
"""Native-capture binding and realized-event export checks; no agent calls."""
import base64
import copy
import csv
import json
import lzma
import os
import tempfile
import unittest
from pathlib import Path
import run_realized_census as C

HERE=Path(__file__).resolve().parent
NATIVE=Path(os.environ.get('TITAN_NATIVE') or (HERE/'../../../../'))


def captured(seat):
    return C.read_capture(HERE/'realized-native-captures.json.xz.b64',seat)


class CensusTests(unittest.TestCase):
    def test_both_captured_seats_match_all_native_and_pristine_poststates(self):
        for seat in range(2):
            r=C.audit_records(NATIVE,captured(seat))
            self.assertEqual(r['steps'],719)
            self.assertTrue(r['all_native_poststates_match'])
            self.assertTrue(r['all_instrumented_poststates_match'])
            hires=r['players'][seat]['HIRE']
            self.assertEqual((hires['rows'],hires['filled_units'],hires['cash_delta']), (282,282,-5573))
            self.assertEqual(r['players'][seat]['BUY_PRODUCT:WHEAT']['filled_units'],147)
            self.assertEqual(r['nonfull_rows'],81)

    def test_effective_csv_uses_fills_and_keeps_raw_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'market.csv'
            C.audit_records(NATIVE,captured(0),path)
            with path.open() as source: rows=list(csv.DictReader(source))
            wheat=[r for r in rows if r['team_id']=='native-b567' and r['verb']=='BUY_PRODUCT' and r['item']=='WHEAT']
            self.assertEqual(sum(int(r['quantity']) for r in wheat),147)
            self.assertEqual(sum(int(r['requested_units']) for r in wheat),150)
            witness=next(r for r in wheat if r['step']=='206')
            self.assertEqual((witness['quantity'],witness['requested_units']),('2','3'))
            self.assertTrue(all(int(r['quantity'])>0 for r in rows))
            self.assertTrue(all('raw_slot' in r for r in rows))

    def test_altered_native_state_chain_is_rejected(self):
        c=captured(0); c['poststate_stream_sha256']='0'*64
        with self.assertRaisesRegex(AssertionError,'full-state stream'):
            C.audit_records(NATIVE,c)

    def test_changed_action_is_rejected(self):
        c=captured(0); c['records'][0]['actions'][0]['market']=[['BUY_LAND']]
        with self.assertRaisesRegex(AssertionError,'full-state stream'):
            C.audit_records(NATIVE,c)

    def test_step_gap_is_rejected(self):
        c=captured(0); c['records'][0]['step']=1
        with self.assertRaisesRegex(ValueError,'noncontiguous'):
            C.audit_records(NATIVE,c)

    def test_score_corruption_is_rejected(self):
        c=captured(0); c['native_result']['scores'][0]+=1
        with self.assertRaisesRegex(AssertionError,'terminal score'):
            C.audit_records(NATIVE,c)

    def test_truncated_capture_is_not_a_complete_game(self):
        c=captured(0); c['records'].pop()
        with self.assertRaisesRegex(AssertionError,'full-state stream'):
            C.audit_records(NATIVE,c)


if __name__=='__main__': unittest.main(verbosity=2)

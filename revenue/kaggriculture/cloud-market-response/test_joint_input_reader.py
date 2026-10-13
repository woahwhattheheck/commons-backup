# SPDX-License-Identifier: MIT
"""Input-shape checks; no engine, controller or retained game execution."""
import json
import unittest


class RetainedReaderTests(unittest.TestCase):
    @staticmethod
    def payload():
        return {'schema':'titan.public-own-history.v1','configuration':{'episodeSteps':4},
                'history':[{'observation':{'step':i,'player':1},'own_action':{'market':[]}}
                           for i in range(2)],
                'observation':{'step':2,'player':1},'selected_action':{'market':[['SELL','WOOL',2]]}}

    def test_public_own_history_uses_exact_original_actions(self):
        from check_joint_retained_prefix import decode_input
        p=self.payload();r=decode_input(json.dumps(p))
        self.assertEqual([v['step'] for v in r],[0,1,2])
        self.assertEqual(r[-1]['expected_action'],p['selected_action'])
        self.assertEqual(r[0]['expected_action'],p['history'][0]['own_action'])
        self.assertTrue(all(v['configuration']==p['configuration'] for v in r))

    def test_existing_jsonl_rows_are_unchanged(self):
        from check_joint_retained_prefix import decode_input
        rows=[{'step':i,'observation':{'step':i},'configuration':{},'expected_action':{'market':[]}}
              for i in range(3)]
        self.assertEqual(decode_input('\n'.join(json.dumps(r) for r in rows)),rows)

    def test_single_jsonl_row_is_not_misread_as_a_packet(self):
        from check_joint_retained_prefix import decode_input
        row={'step':0,'observation':{},'configuration':{},'expected_action':{}}
        self.assertEqual(decode_input(json.dumps(row)),[row])

    def test_incomplete_public_prefix_stops_before_execution(self):
        from check_joint_retained_prefix import decode_input
        p=self.payload();p['history'].pop()
        with self.assertRaises(ValueError):decode_input(json.dumps(p))

    def test_wrong_seat_or_clock_stops_before_execution(self):
        from check_joint_retained_prefix import decode_input
        for field,value in [('player',0),('step',1)]:
            p=self.payload();p['history'][0]['observation'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):decode_input(json.dumps(p))

    def test_offline_index_is_not_runtime_input(self):
        from check_joint_retained_prefix import decode_input
        with self.assertRaises(ValueError):decode_input(json.dumps({'records':[],'outcomes':['win']}))


if __name__=='__main__':
    unittest.main(verbosity=2)

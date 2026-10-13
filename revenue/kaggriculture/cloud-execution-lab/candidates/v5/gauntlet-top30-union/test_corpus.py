from copy import deepcopy
import unittest
from corpus import (PROVENANCE, action_tape, build_union_receipt,
                    retain_and_extend, validate_recorded_additions)

class CorpusTests(unittest.TestCase):
    def recorded(self, fixture_id='new', submission_id=11, episode_id=1001):
        return {'id':fixture_id,'kind':'recorded_trace','provenance':PROVENANCE,
                'executable':False,'adaptive':False,'submission_id':submission_id,
                'episode_id':episode_id}

    def test_initial_state_is_not_an_action_and_seat_is_exact(self):
        replay={'statuses':['DONE','DONE'],'steps':[[{'action':None},{'action':None}]]}
        replay['steps'] += [[{'action':{'farmer':['PASS'],'hands':[],'market':[['SELL','EGG',i]]}},
                             {'action':{'farmer':['NORTH'],'hands':[],'market':[['SELL','WHEAT',i]]}}]
                            for i in range(719)]
        tape=action_tape(replay,1)
        self.assertEqual(len(tape),719)
        self.assertEqual(tape[0]['farmer'],['NORTH'])
        self.assertEqual(tape[-1]['market'][0][-1],718)
        tape[0]['farmer'][0]='PASS'
        self.assertEqual(replay['steps'][1][1]['action']['farmer'],['NORTH'])

    def test_all_old_entries_and_mirror_survive_with_opaque_fields(self):
        old={'config':{'seeds':[1,2]},'opponents':[{'id':str(i),'secret_runtime_field':{'x':i}} for i in range(30)]}
        old['opponents'].append({'id':'mirror','kind':'mirror'})
        saved=deepcopy(old)
        result=retain_and_extend(old,[self.recorded()])
        self.assertEqual(old,saved)
        self.assertEqual(result['opponents'][:31],saved['opponents'])
        self.assertEqual(result['additive_intake']['legacy_entries'],31)
        self.assertEqual(result['config'],saved['config'])

    def test_colliding_addition_cannot_replace_old_opponent(self):
        with self.assertRaises(ValueError):
            retain_and_extend({'opponents':[{'id':'old'}]},
                              [self.recorded(fixture_id='old')])

    def test_reserved_intake_field_cannot_be_overwritten(self):
        old={'opponents':[{'id':'old'}],'additive_intake':{'prior':True}}
        with self.assertRaisesRegex(ValueError, 'reserved additive_intake'):
            retain_and_extend(old,[self.recorded()])

    def test_recorded_fixture_must_be_explicitly_non_executable(self):
        row=self.recorded(); row['executable']=True
        with self.assertRaisesRegex(ValueError, 'executable policy'):
            validate_recorded_additions([row])

    def test_recorded_fixture_requires_exact_provenance(self):
        row=self.recorded(); row.pop('provenance')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            validate_recorded_additions([row])

    def test_receipt_binds_legacy_and_submission_count(self):
        old={'config':{'x':1},'opponents':[{'id':'old'}]}
        additions=[self.recorded()]
        extended=retain_and_extend(old,additions)
        extended['additive_intake']['legacy_source_sha256']='a'*64
        receipt=build_union_receipt(
            old,extended,additions,legacy_source_sha256='a'*64,
            source_manifest_sha256='b'*64,
            expected_unique_submissions=1,expected_fixtures=1)
        self.assertTrue(receipt['legacy_exact_prefix'])
        self.assertFalse(receipt['all_new_executable'])
        self.assertEqual(receipt['unique_submission_targets'],1)

    def test_receipt_rejects_mutated_legacy_top_level_field(self):
        old={'config':{'x':1},'opponents':[{'id':'old'}]}
        additions=[self.recorded()]
        extended=retain_and_extend(old,additions)
        extended['additive_intake']['legacy_source_sha256']='a'*64
        extended['config']={'x':2}
        with self.assertRaisesRegex(ValueError, 'top-level'):
            build_union_receipt(
                old,extended,additions,legacy_source_sha256='a'*64,
                source_manifest_sha256='b'*64,
                expected_unique_submissions=1,expected_fixtures=1)

if __name__=='__main__':unittest.main()

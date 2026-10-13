import copy
import pathlib
import sys
import tempfile
import unittest
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from native_return_bridge import ReturnBridge, git_blob_id, _action_digest, _load_exact


@dataclass(frozen=True)
class Cert:
    slot_safe: bool
    reason: str = "ok"
    resource_sensitive_slots: tuple = ()
    same_product_slots: tuple = ()


def flow_bounds(prev, action, nxt, cfg):
    if prev is None or nxt['step'] != prev['step'] + 1 or nxt['player'] != prev['player']:
        return None
    # Encode the synthetic opponent sell in CARROT inventory delta.
    delta = nxt['market']['inventory']['CARROT'] - prev['market']['inventory']['CARROT']
    return {'CARROT': (delta, delta), 'WHEAT': (0, 0)}


def confirmed(bounds, threshold):
    if not bounds:
        return {}
    return {k: lo for k, (lo, hi) in bounds.items() if lo >= threshold}


def cert(before, after, *, item, quantity, max_orders=10):
    old = before.get('market', [])
    new = after.get('market', [])
    if old:
        if old[0] not in (None, [], ['PASS']):
            return Cert(False, 'occupied')
        if len(new) != len(old) or new[1:] != old[1:]:
            return Cert(False, 'shift')
    elif len(new) != 1:
        return Cert(False, 'extra')
    resources=[]; same=[]
    cap=max(1,int(max_orders))
    for i,row in enumerate(new[1:cap],1):
        if isinstance(row,list) and row:
            if row[0] in ('HIRE','BUY_LAND','BUY_SEED','BUY_ANIMAL','BUY_PRODUCT'):
                resources.append(i)
            if row[0] in ('SELL','BUY_PRODUCT') and len(row)>1 and row[1]==item:
                same.append(i)
    return Cert(True, resource_sensitive_slots=tuple(resources), same_product_slots=tuple(same))


class Features:
    consumer='frozen'
    terminal_route=False

class Consumer:
    def __init__(self):
        self.planned={'CARROT':[(6,4)]}
        self.pending={'CARROT':4}
        self.selected_post_units=({'money':0},{'shed':{'CARROT':4}})
        self.selected_post_units_binding=(5,0,['PASS'],[['PASS']])

class Instance:
    def __init__(self):
        self.features=Features()
        self.consumer=Consumer()
        self.diagnostics={'status':'completed'}
        self._completed_seller_state={'old':True}
        self.commit_calls=0
    def _commit_seller_state(self):
        self.commit_calls += 1
        self._completed_seller_state={
            'planned':copy.deepcopy(self.consumer.planned),
            'pending':copy.deepcopy(self.consumer.pending),
        }


def obs(step, inv=10000, *, player=0):
    return {
        'step':step,'player':player,
        'market':{'inventory':{'CARROT':inv,'WHEAT':10000}},
        'town':{'unlocked_shops':[]},
        'private':{'shed':{'CARROT':4}},
    }


def action(market=None):
    return {'farmer':['PASS'],'hands':[['PASS']], 'market': [] if market is None else market}


class BridgeTests(unittest.TestCase):
    def bridge(self, **kw):
        return ReturnBridge(flow_bounds, confirmed, cert, threshold=150, **kw)

    def arm(self, b):
        inst=Instance()
        # First returned action is exact and completed.
        b.commit(inst, obs(4,10000), {}, action(), action(), None)
        self.assertEqual(b.observe(obs(5,10200), {}), {'CARROT':200})
        return inst

    def test_git_blob_formula(self):
        self.assertEqual(git_blob_id(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')

    def test_exact_loader_supports_future_annotations_dataclass(self):
        source = (
            b"from __future__ import annotations\n"
            b"from dataclasses import dataclass\n"
            b"@dataclass(frozen=True)\n"
            b"class Certificate:\n"
            b"    value: int\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'authority.py'
            path.write_bytes(source)
            module = _load_exact('_returnbridge_loader_probe', path, git_blob_id(source))
            self.assertEqual(module.Certificate(7).value, 7)
            self.assertIs(sys.modules['_returnbridge_loader_probe'], module)

    def test_cold_start_identity(self):
        b=self.bridge(); inst=Instance(); base=action()
        got,p=b.propose(inst,obs(5,10200),{},base)
        self.assertIs(got,base); self.assertIsNone(p)

    def test_adjacent_completed_transition_arms_signal(self):
        b=self.bridge(); inst=Instance()
        b.commit(inst,obs(4,10000),{},action(),action(),None)
        self.assertEqual(b.observe(obs(5,10200),{}),{'CARROT':200})

    def test_nonadjacent_transition_fails_closed(self):
        b=self.bridge(); inst=Instance()
        b.commit(inst,obs(2,10000),{},action(),action(),None)
        self.assertEqual(b.observe(obs(5,10500),{}),{})

    def test_episode_zero_resets_history(self):
        b=self.bridge(); inst=Instance()
        b.commit(inst,obs(4,10000),{},action(),action(),None)
        self.assertEqual(b.observe(obs(0,10000),{}),{})
        self.assertIsNone(b.previous_action)

    def test_prepare_is_side_effect_free(self):
        b=self.bridge(); inst=self.arm(b); base=action([[]])
        before=copy.deepcopy((inst.consumer.planned,inst.consumer.pending,inst._completed_seller_state))
        candidate,p=b.propose(inst,obs(5,10200),{},base)
        self.assertIsNotNone(p)
        self.assertEqual(candidate['market'][0],['SELL','CARROT',4])
        self.assertEqual((inst.consumer.planned,inst.consumer.pending,inst._completed_seller_state),before)

    def test_commit_debits_exact_native_debt(self):
        b=self.bridge(); inst=self.arm(b); base=action([[]])
        candidate,p=b.propose(inst,obs(5,10200),{},base)
        returned=b.commit(inst,obs(5,10200),{},base,candidate,p)
        self.assertEqual(returned,candidate)
        self.assertNotIn('CARROT',inst.consumer.planned)
        self.assertEqual(inst.consumer.pending['CARROT'],0)
        self.assertEqual(inst.commit_calls,1)  # only the accepted debt rebinds the seller checkpoint
        self.assertTrue(inst.diagnostics['lockstep_join']['changed'])

    def test_stale_plan_returns_exact_baseline_without_mutation(self):
        b=self.bridge(); inst=self.arm(b); base=action([[]])
        candidate,p=b.propose(inst,obs(5,10200),{},base)
        inst.consumer.planned['CARROT']=[(6,3)]
        snapshot=copy.deepcopy((inst.consumer.planned,inst.consumer.pending))
        returned=b.commit(inst,obs(5,10200),{},base,candidate,p)
        self.assertIs(returned,base)
        self.assertEqual((inst.consumer.planned,inst.consumer.pending),snapshot)
        self.assertEqual(inst.diagnostics['lockstep_join']['commit_reason'],'stale_or_invalid_native_debt')

    def test_occupied_row_zero_rejected(self):
        b=self.bridge(); inst=self.arm(b); base=action([['SELL','MILK',1]])
        returned,p=b.propose(inst,obs(5,10200),{},base)
        self.assertIs(returned,base); self.assertIsNone(p)
        self.assertIn('queue_unsafe',b.last_report['reason'])

    def test_later_resource_order_rejected(self):
        b=self.bridge(); inst=self.arm(b); base=action([[],['HIRE']])
        returned,p=b.propose(inst,obs(5,10200),{},base)
        self.assertIs(returned,base); self.assertIsNone(p)
        self.assertEqual(b.last_report['reason'],'later_resource_order')

    def test_later_same_product_order_rejected(self):
        b=self.bridge(); inst=self.arm(b); base=action([[],['SELL','CARROT',1]])
        returned,p=b.propose(inst,obs(5,10200),{},base)
        self.assertIs(returned,base); self.assertIsNone(p)
        self.assertEqual(b.last_report['reason'],'later_same_product_order')

    def test_no_exact_post_unit_stock_rejected(self):
        b=self.bridge(); inst=self.arm(b)
        inst.consumer.selected_post_units_binding=(5,0,['NORTH'],[['PASS']])
        base={'farmer':['SOUTH'],'hands':[['PASS']],'market':[[]]}
        returned,p=b.propose(inst,obs(5,10200),{},base)
        self.assertIs(returned,base); self.assertIsNone(p)
        self.assertEqual(b.last_report['reason'],'no_exact_post_unit_stock')

    def test_inner_fallback_does_not_seed_next_inference(self):
        b=self.bridge(); inst=Instance(); inst.diagnostics={'status':'deadline_fallback'}
        base=action()
        b.commit(inst,obs(4,10000),{},base,base,None)
        self.assertIsNone(b.previous_action)
        self.assertEqual(b.observe(obs(5,10200),{}),{})

    def test_partial_debt_pull_is_exact(self):
        b=self.bridge(max_pull=2); inst=self.arm(b); base=action([[]])
        candidate,p=b.propose(inst,obs(5,10200),{},base)
        self.assertEqual(candidate['market'][0],['SELL','CARROT',2])
        returned=b.commit(inst,obs(5,10200),{},base,candidate,p)
        self.assertEqual(returned,candidate)
        self.assertEqual(inst.consumer.planned['CARROT'],[(6,2)])
        self.assertEqual(inst.consumer.pending['CARROT'],2)

    def test_baseline_candidate_tamper_fails_closed(self):
        b=self.bridge(); inst=self.arm(b); base=action([[]])
        candidate,p=b.propose(inst,obs(5,10200),{},base)
        candidate=copy.deepcopy(candidate); candidate['market'][0][2]=3
        returned=b.commit(inst,obs(5,10200),{},base,candidate,p)
        self.assertIs(returned,base)
        self.assertEqual(inst.consumer.planned['CARROT'],[(6,4)])


if __name__=='__main__': unittest.main()

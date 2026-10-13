# SPDX-License-Identifier: Apache-2.0
"""Execute a native crop-input prefix repair against source-pinned components.

Constructed two-seat official-interpreter transitions, not a full-game or EV
benchmark. Every assertion is a unittest assertion and remains active under -O.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from compose_crop_input_prefix import compose, REPLACEMENTS, SOURCE_BLOB

ROOT = None
VARIANT = 'repaired'
COUNTS = {'suffix_vectors': 0, 'in_cap_controls': 0, 'engine_calls': 0,
          'native_owner_calls': 0, 'fill_receipts': 0}
WITNESSES = []
PINS = {'crop_release.py': 'dd318e5bbe6245913c3dcb8c07d0752fd1ebd735', 'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d', 'spatial_tempo.py': 'edbc423023479dbe2e78131495334384a87b607f', 'reference/titan-history/observed_fills.py': 'cabe10ad3d683351077c9597ad7bb36cb58ce9c6', 'checks/reference/evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325', 'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5', 'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4', 'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20', 'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87'}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_from(source, name):
    module = types.ModuleType(name)
    exec(compile(source, name + '.py', 'exec'), module.__dict__)
    return module


def variant(source, name):
    fixed = compose(source)
    if name == 'repaired': return fixed
    if name == 'original': return source
    if name == 'wheat_tail':
        return fixed.replace(REPLACEMENTS[0][1], REPLACEMENTS[0][0], 1)
    if name == 'capacity_tail':
        return fixed.replace(REPLACEMENTS[1][1], REPLACEMENTS[1][0], 1)
    if name in ('cap9', 'cap11'):
        cap = b'9' if name == 'cap9' else b'11'
        for _, anchor in REPLACEMENTS:
            fixed = fixed.replace(anchor, anchor.replace(b'[:10]', b'[:' + cap + b']'), 1)
        return fixed
    if name == 'compact':
        return fixed.replace(b"    orders=selected.get('market',[])\n",
                             b"    orders=[a for a in selected.get('market',[]) if a]\n", 1)
    if name == 'truncate':
        return fixed.replace(b"    private=post['private'];out=deepcopy(selected);kind='buy'",
                             b"    private=post['private'];out=deepcopy(selected);out['market']=out['market'][:10];kind='buy'", 1)
    if name == 'allow_active_buy':
        return fixed.replace(b"    if any(a and len(a)>1 and a[:2]==['BUY_PRODUCT','WHEAT'] for a in orders[:10]):",
                             b"    if False:", 1)
    raise ValueError(name)


class CropInputPrefixContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for relative, expected in PINS.items():
            data = (ROOT / relative).read_bytes()
            if blob(data) != expected:
                raise ValueError('Native source mismatch: ' + relative)
        sys.path.insert(0, str(ROOT))
        cls.source = (ROOT / 'crop_release.py').read_bytes()
        cls.old = module_from(cls.source, 'original_crop')
        cls.c = module_from(variant(cls.source, VARIANT), 'tested_crop')
        import mechanics
        cls.m = mechanics
        cls.ev = load_file(ROOT / 'checks/reference/evaluator/evaluate.py', 'crop_prefix_evaluator')
        cls.e, cls.engine_hashes = cls.ev.get_engine(
            ROOT / 'checks/reference/engine', ROOT / 'checks/reference/evaluator/loader.py')
        cls.fills = load_file(ROOT / 'reference/titan-history/observed_fills.py', 'crop_prefix_fills')
        cls.spatial = load_file(ROOT / 'spatial_tempo.py', 'crop_prefix_spatial')

    def fixture(self, seat=0, step=457, stock=5, carried=0):
        e, S = self.e, self.ev.Struct
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in e.specification['configuration'].items()})
        cfg.weedSpawnChance = 0
        cfg.seed = 2026091145
        farms = [e._new_farm(10, 25000) for _ in range(2)]
        market = e._new_market()
        town = {'unlocked_shops': []}
        states = []
        for player in (0, 1):
            private = e._new_private()
            private['shed'] = {'WHEAT': stock} if player == seat else {}
            private['inventories'] = [{'WHEAT': carried}] if player == seat and carried else [{}]
            states.append(S(observation=S(player=player, step=step, day=step // 24,
                 hour=step % 24, farms=farms, private=private, market=market, town=town),
                 action={'farmer': ['PASS'], 'hands': [], 'market': []}, status='ACTIVE', reward=0))
        intent = {'player': seat, 'last_observed_step': step, 'prepared_step': 372,
                  'plant_step': 373, 'deposit_step': 455, 'harvest_step': 444,
                  'status': 'input_recovery_only', 'input_repair_remaining': 3,
                  'wheat_reserve_required': 3, 'input_repair_receipts': []}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        return states, S(configuration=cfg, done=False, info={'seed': cfg.seed}), intent, route

    def queue(self, slot=0, tail=(), duplicate=False):
        rows = [[] for _ in range(10)]
        rows[slot] = ['SELL', 'WHEAT', 4]
        if duplicate:
            rows[(slot + 1) % 10] = ['SELL', 'WHEAT', 4]
        return {'farmer': ['PASS'], 'hands': [], 'market': rows + deepcopy(list(tail))}

    def propose(self, states, intent, route, action, config=None, module=None):
        obs = states[intent['player']].observation
        return (module or self.c).propose_input_repair(self.m, intent, obs, config or {}, action, obs, route)

    def advance(self, states, env, seat, action, rival=None):
        states[seat].action = deepcopy(action)
        if rival is not None:
            states[1-seat].action = deepcopy(rival)
        step = states[0].observation.step
        self.e.interpreter(states, env)
        COUNTS['engine_calls'] += 1
        for s in states:
            s.observation.step = step + 1  # The external framework owns this counter.
        return states[seat].observation

    def test_dead_wheat_buys_do_not_veto_restoration(self):
        for seat in (0, 1):
            for slot in (0, 4, 9):
                for suffix in ([['BUY_PRODUCT','WHEAT',1]],
                               [['BUY_PRODUCT','WHEAT',999999]],
                               [[], ['BUY_PRODUCT','WHEAT',3]]):
                    with self.subTest(seat=seat, slot=slot, suffix=suffix):
                        s, e, p, r = self.fixture(seat)
                        a = self.queue(slot, suffix)
                        before = deepcopy((s, p, r, a))
                        out, proposal, report = self.propose(s, p, r, a)
                        self.assertTrue(report['changed'])
                        self.assertEqual(proposal['kind'], 'withhold')
                        self.assertEqual(proposal['units'], 3)
                        self.assertEqual(out['market'][slot], ['SELL', 'WHEAT', 1])
                        self.assertEqual(out['market'][10:], a['market'][10:])
                        self.assertEqual((s, p, r, a), before)
                        COUNTS['suffix_vectors'] += 1

    def test_dead_physical_purchases_do_not_use_shared_room(self):
        tails = [[['BUY_PRODUCT','FERTILIZER',10000]], [['BUY_ANIMAL','COW',10000]],
                 [['BUY_ANIMAL','SHEEP','bad']], [['BUY_PRODUCT','FERTILIZER',-7]],
                 [['BUY_PRODUCT','FERTILIZER',True]], [['BUY_ANIMAL']]]
        for seat in (0,1):
            for slot in (0,4,9):
                for tail in tails:
                    with self.subTest(seat=seat, slot=slot, tail=tail):
                        s,e,p,r = self.fixture(seat)
                        a=self.queue(slot,tail)
                        out,pr,report=self.propose(s,p,r,a)
                        self.assertTrue(report['changed'])
                        self.assertEqual(report['shared_stock_upper'],5)
                        self.assertEqual(out['market'][10:],tail)
                        COUNTS['suffix_vectors'] += 1

    def test_arbitrary_dead_json_rows_are_uninspected_and_preserved(self):
        for tail in ([None], [True], [4], [{'opaque':'dead'}], ['dead'], [[]]):
            with self.subTest(tail=tail):
                s,e,p,r=self.fixture()
                a=self.queue(9,tail)
                out,pr,report=self.propose(s,p,r,a)
                self.assertTrue(report['changed'])
                self.assertEqual(out['market'][10:],tail)
                self.assertEqual(out['market'][:9],[[] for _ in range(9)])
                COUNTS['suffix_vectors'] += 1

    def test_every_active_buy_slot_keeps_original_veto(self):
        for seat in (0,1):
            for slot in range(10):
                s,e,p,r=self.fixture(seat)
                a=self.queue((slot+1)%10)
                a['market'][slot]=['BUY_PRODUCT','WHEAT',1]
                out,pr,report=self.propose(s,p,r,a)
                self.assertIs(out,a)
                self.assertIsNone(pr)
                self.assertEqual(report['reason'],'existing_wheat_purchase_needs_its_own_receipt')
                COUNTS['in_cap_controls'] += 1

    def test_every_active_physical_purchase_keeps_capacity_veto(self):
        for seat in (0,1):
            for slot in range(10):
                s,e,p,r=self.fixture(seat)
                a=self.queue((slot+1)%10)
                a['market'][slot]=['BUY_PRODUCT','FERTILIZER',100]
                out,pr,report=self.propose(s,p,r,a)
                self.assertIs(out,a)
                self.assertIsNone(pr)
                self.assertEqual(report['reason'],'repair_or_eod_delivery_lacks_shared_room')
                COUNTS['in_cap_controls'] += 1

    def test_in_cap_queue_outcomes_match_unmodified_native(self):
        markets=[[],[['SELL','WHEAT',4]], [['SELL','WHEAT',2],['BUY_SEED','WHEAT',1],['SELL','WHEAT',2]],
                 [['BUY_PRODUCT','WHEAT',1]], [['BUY_PRODUCT','FERTILIZER',1]],
                 [['BUY_ANIMAL','COW','bad']], [['HIRE']]*10, [[]]*10]
        for seat in (0,1):
            for market in markets:
                s,e,p,r=self.fixture(seat)
                a={'farmer':['PASS'],'hands':[],'market':deepcopy(market)}
                self.assertEqual(self.propose(s,p,r,a),self.propose(s,p,r,a,module=self.old))
                COUNTS['in_cap_controls'] += 1

    def test_no_slot_is_created_by_compacting_empty_rows(self):
        s,e,p,r=self.fixture()
        a={'farmer':['PASS'],'hands':[],'market':[[]]*10+[['SELL','WHEAT',5]]}
        out,pr,report=self.propose(s,p,r,a)
        self.assertIs(out,a)
        self.assertIsNone(pr)
        self.assertEqual(report['reason'],'repair_requires_a_free_nonconflicting_slot')

    def test_cash_capacity_configuration_and_receipt_guards_remain(self):
        for kind in ('poor','full','pending','unknown','wrong_seat','stale','config'):
            s,e,p,r=self.fixture()
            a=self.queue(tail=[['BUY_PRODUCT','FERTILIZER',10000]])
            cfg={}
            if kind=='poor':
                s[0].observation.farms[0]['money']=0
                r[458]['market']=[['BUY_SEED','WHEAT',1]]
            elif kind=='full': s[0].observation.private['shed']['MILK']=96
            elif kind=='pending': p['input_repair_pending']={'step':456}
            elif kind=='unknown': p['input_repair_unknown']=True
            elif kind=='wrong_seat': s[0].observation.player=1
            elif kind=='stale': p['last_observed_step']=456
            elif kind=='config': cfg={'maxMarketOrdersPerTurn':11}
            with self.subTest(kind=kind):
                self.assertFalse(self.propose(s,p,r,a,cfg)[2]['changed'])

    def test_full_engine_prefix_suffix_equality_and_observed_debt(self):
        tails=[[['BUY_PRODUCT','WHEAT',999999]], [['BUY_PRODUCT','FERTILIZER',999999]],
               [['BUY_ANIMAL','COW','bad']], [None,True,{},4,'dead'],
               [['HIRE'],['BUY_LAND']], [['SELL','WHEAT',999999]]]
        for seat in (0,1):
            for step in (455,457,479):
                for slot in (0,9):
                    for tail in tails:
                        with self.subTest(seat=seat,step=step,slot=slot,tail=tail):
                            s,e,p,r=self.fixture(seat,step,carried=2 if step%24==23 else 0)
                            a=self.queue(slot,tail)
                            out,pr,report=self.propose(s,p,r,a)
                            self.assertTrue(report['changed'])
                            control,ce=deepcopy((s,e))
                            prefix=deepcopy(out);prefix['market']=prefix['market'][:10]
                            ledger=self.fills.ObservedFillLedger()
                            obs=s[seat].observation
                            ledger.record(obs,{},out,post_unit_shed=obs.private['shed'],
                                          post_unit_inventories=obs.private['inventories'])
                            committed=self.c.commit_input_repair(p,pr,obs,out,obs)
                            self.assertIn('input_repair_pending',committed)
                            actual=self.advance(s,e,seat,out)
                            self.advance(control,ce,seat,prefix)
                            self.assertEqual([x.observation for x in s],[x.observation for x in control])
                            self.assertEqual([x.status for x in s],[x.status for x in control])
                            fills=ledger.observe(actual)
                            done=self.c.observe_input_repair(committed,actual,fills)
                            self.assertEqual(done['input_repair_remaining'],0)
                            self.assertEqual(done['wheat_reserve_required'],0)
                            self.assertEqual(done['input_repair_receipts'][-1]['restored_units'],3)
                            self.assertEqual(self.c.observe_input_repair(done,actual,fills),done)
                            COUNTS['fill_receipts'] += 1

    def test_native_owner_final_guard_and_real_next_observation(self):
        for seat in (0,1):
            s,e,p,r=self.fixture(seat)
            obs=s[seat].observation
            a=self.queue(9,[['BUY_PRODUCT','WHEAT',100000]])
            owner=self.spatial.SpatialTempo(self.m,pathing=False,tempo=False,crop_release=True)
            owner.configure({});owner.crop_intent=deepcopy(p);owner._crop_routes={self.c.MAIN:r}
            controller=types.SimpleNamespace(cur=self.c.MAIN)
            with patch.dict(sys.modules,{'crop_release':self.c}):
                out=owner.crop_market(obs,a,obs,controller)
                self.assertTrue(owner.crop_report['changed'])
                guarded=owner.guard_crop_returned(obs,out,obs)
                self.assertEqual(guarded,out)
                owner.finish_crop(obs,guarded,obs,controller.cur)
                self.assertIn('input_repair_pending',owner.crop_intent)
                ledger=self.fills.ObservedFillLedger()
                ledger.record(obs,{},guarded,post_unit_shed=obs.private['shed'],
                              post_unit_inventories=obs.private['inventories'])
                actual=self.advance(s,e,seat,guarded)
                result=ledger.observe(actual)
                owner.observe_crop_receipts(actual,result,controller.cur)
                self.assertEqual(owner.crop_intent['input_repair_remaining'],0)
                self.assertEqual(owner.crop_intent['last_observed_step'],458)
                COUNTS['native_owner_calls'] += 4

    def test_unemitted_or_reordered_action_cannot_credit_debt(self):
        s,e,p,r=self.fixture()
        a=self.queue(9,[['BUY_PRODUCT','WHEAT',100000]])
        out,pr,report=self.propose(s,p,r,a)
        self.assertTrue(report['changed'])
        obs=s[0].observation
        self.assertEqual(self.c.commit_input_repair(p,pr,obs,a,obs),p)
        changed=deepcopy(out);changed['market'][10]=['PASS']
        self.assertTrue(self.c.commit_input_repair(p,pr,obs,changed,obs)['input_repair_unknown'])
        owner=self.spatial.SpatialTempo(self.m,crop_release=True);owner._crop_repair=pr
        with patch.dict(sys.modules,{'crop_release':self.c}):
            restored=owner.guard_crop_returned(obs,changed,obs)
        self.assertEqual(restored['market'][9],a['market'][9])
        self.assertEqual(restored['market'][10],['PASS'])

    def test_debt_receipt_requires_exact_return_hash(self):
        s,e,p,r=self.fixture();obs=s[0].observation
        out,pr,report=self.propose(s,p,r,self.queue(9,[['BUY_PRODUCT','WHEAT',10000]]))
        self.assertTrue(report['changed'])
        committed=self.c.commit_input_repair(p,pr,obs,out,obs)
        ledger=self.fills.ObservedFillLedger()
        ledger.record(obs,{},out,post_unit_shed=obs.private['shed'],post_unit_inventories=obs.private['inventories'])
        actual=self.advance(s,e,0,out);result=ledger.observe(actual)
        result['binding']['action_sha256']='wrong'
        unknown=self.c.observe_input_repair(committed,actual,result)
        self.assertTrue(unknown['input_repair_unknown'])
        self.assertEqual(unknown['input_repair_remaining'],3)

    def test_measured_stock_cash_tradeoff_is_not_an_ev_claim(self):
        for seat in (0,1):
            s,e,p,r=self.fixture(seat)
            a=self.queue(9,[['BUY_PRODUCT','WHEAT',1]])
            original=self.propose(s,p,r,a,module=self.old)[0]
            repaired=self.propose(s,p,r,a)[0]
            self.assertEqual(repaired['market'][9],['SELL','WHEAT',1])
            control,ce=deepcopy((s,e))
            obs=self.advance(s,e,seat,repaired)
            prev=self.advance(control,ce,seat,original)
            self.assertEqual(obs.private['shed']['WHEAT']-prev.private['shed']['WHEAT'],3)
            self.assertEqual(obs.farms[seat]['money']-prev.farms[seat]['money'],-72)
            WITNESSES.append({'seat':seat,'step':457,'wheat_delta':3,'own_cash_delta':-72,
                             'rival_cash_delta':0,'scope':'constructed one-transition restoration, not EV'})

    def test_source_composition_preserves_all_other_bytes(self):
        data=b'# peer unicode: \xcf\x80\n'+self.source+b'\nPEER_EXTENSION = 17\n'
        fixed=compose(data)
        self.assertTrue(fixed.startswith(b'# peer unicode: \xcf\x80\n'))
        self.assertTrue(fixed.endswith(b'\nPEER_EXTENSION = 17\n'))
        self.assertEqual(compose(fixed),fixed)
        undone=fixed
        for old,new in REPLACEMENTS:
            undone=undone.replace(new,old,1)
        self.assertEqual(undone,data)

    def test_source_drift_duplicate_decorator_partial_rejected(self):
        for src in (self.source.replace(b"report={'changed':False",b"report={'changed':True",1),
                    self.source+b'\ndef propose_input_repair():\n    pass\n',
                    self.source.replace(b'def propose_input_repair(',b'@staticmethod\ndef propose_input_repair(',1),
                    self.source.replace(*REPLACEMENTS[0],1)):
            with self.subTest(sha=hashlib.sha256(src).hexdigest()):
                with self.assertRaises(ValueError):compose(src)

    def test_composer_does_not_overwrite_existing_output(self):
        script=Path(__file__).with_name('compose_crop_input_prefix.py')
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'in.py';dst=Path(td)/'out.py';src.write_bytes(self.source)
            command=[sys.executable,*(['-O'] if not __debug__ else []),str(script),str(src)]
            result=subprocess.run(command+[str(dst)],capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(dst.read_bytes(),compose(self.source))
            for target in (dst,src):
                before=target.read_bytes()
                result=subprocess.run(command+[str(target)],capture_output=True,timeout=15)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(target.read_bytes(),before)
            symlink=Path(td)/'alias.py';symlink.symlink_to(src)
            result=subprocess.run(command+[str(symlink)],capture_output=True,timeout=15)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(src.read_bytes(),self.source)


def main():
    global ROOT,VARIANT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--variant',default='repaired',choices=['repaired','original','wheat_tail','capacity_tail','cap9','cap11','compact','truncate','allow_active_buy'])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();ROOT=args.runtime.resolve();VARIANT=args.variant
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CropInputPrefixContracts))
    report={'variant':VARIANT,'optimized':not __debug__,'tests':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'passed':result.wasSuccessful(),'counts':COUNTS,'witnesses':WITNESSES,
            'source_pins':PINS,'test_blob':blob(Path(__file__).read_bytes()),
            'composer_blob':blob(Path(__file__).with_name('compose_crop_input_prefix.py').read_bytes())}
    if args.output:args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()

"""Discriminating own-lot accounting and pinned-engine receipt contracts."""
from copy import deepcopy
import argparse
import importlib.util
from pathlib import Path
import sys
import unittest

engine = None


def act(unit=None, market=None):
    return {'farmer': unit or ['PASS'], 'hands': [], 'market': market or []}


class FutureSupply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if engine is None:
            raise unittest.SkipTest('Use the CLI with --payload, --loader and --engine-dir')

    def setUp(self):
        self.farm = engine._new_farm(6, 1000)
        self.private = engine._new_private()
        self.private['shed']['WOOL'] = 5
        self.private['inventories'][0]['WOOL'] = 3
        self.obs = {'step': 0, 'player': 0}
        self.cfg = {'turnsPerDay': 24, 'shedCapacity': 100, 'maxMarketOrdersPerTurn': 10}

    def project(self, route, base=None, end=None):
        return future.projected_sales(self.obs,self.cfg,base or act(),self.farm,
            self.private,route,len(route)-1 if end is None else end,'WOOL')

    def test_existing_shed_lot_is_not_counted_as_new_supply(self):
        before = deepcopy((self.farm,self.private))
        route = [act(), act(['DROP'],[['SELL','WOOL',100]])]
        self.assertEqual(self.project(route), ((1,3),))
        self.assertEqual((self.farm,self.private), before)
        self.assertEqual(self.project(route,act(market=[['SELL','WOOL',5]])), ((1,3),))

    def test_initial_lot_sale_without_deposit_has_no_background(self):
        self.private['inventories'][0] = {}
        self.assertEqual(self.project([act(),act(market=[['SELL','WOOL',100]])]), ())

    def test_future_pickup_reduces_new_supply_conservatively(self):
        route = [act(),act(['DROP']),act(['PICKUP','WOOL',2]),act(market=[['SELL','WOOL',100]])]
        self.assertEqual(self.project(route), ((3,1),))

    def test_partial_sale_is_not_assumed_to_clear_all_new_stock(self):
        route = [act(),act(['DROP'],[['SELL','WOOL',6]])]
        self.assertEqual(self.project(route), ())

    def test_future_purchased_lot_requires_separate_funding_model(self):
        route = [act(),act(['DROP'],[['BUY_PRODUCT','WOOL',1],['SELL','WOOL',100]])]
        self.assertEqual(self.project(route), ())

    def test_projection_stops_at_same_day_boundary(self):
        self.obs['step'] = 22
        route = [act() for _ in range(26)]
        route[24] = act(['DROP'],[['SELL','WOOL',100]])
        self.assertEqual(self.project(route), ())

    def test_market_model_matches_pinned_engine_with_future_owned_arrivals(self):
        for seat in (0,1):
            for plan in (((0,7),),((0,2),(4,5))):
                with self.subTest(seat=seat,plan=plan):
                    cfg = loader.Struct({k:v.get('default') if isinstance(v,dict) else v
                        for k,v in engine.specification['configuration'].items()})
                    cfg.seed=2051966578
                    cfg.townShopSellInterval=2
                    cfg.townCenterSellInterval=2
                    env = loader.Struct(configuration=cfg,done=False,info={})
                    state=[loader.Struct(observation=loader.Struct(),action={},status='ACTIVE',reward=0)
                           for _ in range(2)]
                    engine.interpreter(state,env)
                    ob=state[0].observation
                    ob.town['unlocked_shops']=['YARN_STORE']
                    supply=((1,9),(3,4))
                    rival=((2,3),(4,2))
                    quantity=7
                    state[seat].observation.private['shed']['WOOL']=quantity
                    state[1-seat].observation.private['shed']['WOOL']=5
                    model=MarketPath('WOOL',ob.market['inventory']['WOOL'],ob.market.get('params'),
                        ob.town['unlocked_shops'],cfg,0,4,supply)
                    predicted=model.score(plan,quantity,rival,'paired',True)
                    money=[f['money'] for f in ob.farms]
                    for step in range(5):
                        ob.step=step
                        extra=dict(supply).get(step,0)
                        state[seat].observation.private['shed']['WOOL']+=extra
                        state[seat].action=act(market=[['SELL','WOOL',dict(plan).get(step,0)+extra]])
                        state[1-seat].action=act(market=[['SELL','WOOL',dict(rival).get(step,0)]])
                        engine.interpreter(state,env)
                    own=ob.farms[seat]['money']-money[seat]
                    other=ob.farms[1-seat]['money']-money[1-seat]
                    self.assertEqual(predicted, (own-other,own,other,0))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--loader',type=Path,required=True)
    parser.add_argument('--engine-dir',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.payload.resolve()))
    import future_own_supply as future
    from selected_sell_core import MarketPath
    spec=importlib.util.spec_from_file_location('supply_loader',args.loader.resolve())
    loader=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    engine,_=loader.get_engine(args.engine_dir.resolve())
    unittest.main(argv=[sys.argv[0]])

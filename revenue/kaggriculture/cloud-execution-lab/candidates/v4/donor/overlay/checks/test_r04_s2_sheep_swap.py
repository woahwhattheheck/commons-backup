import unittest
from types import SimpleNamespace

import r04_s2_sheep_swap as s2

CFG = dict(episodeSteps=720, boardSize=10, turnsPerDay=24, shedCapacity=100, maxMarketOrdersPerTurn=10)


def tile(kind=None, animal=None, placed_day=None, yield_units=0):
    d = {}
    if kind is not None: d['kind'] = kind
    if animal is not None: d['animal'] = animal
    if placed_day is not None: d['placed_day'] = placed_day
    if yield_units: d['yield_units'] = yield_units
    return d


def obs(step=100, money=1000, shops=None, prices=None, shed=None, invs=None, hands=None):
    shops = ['YARN_STORE'] if shops is None else shops
    prices = {'WOOL': 200, 'MILK': 100} if prices is None else prices
    shed = {} if shed is None else shed
    hands = [[4,4]] if hands is None else hands
    invs = [{}, {}] if invs is None else invs
    board = [[None for _ in range(10)] for _ in range(10)]
    return {
        'step': step, 'player': 0,
        'farms': [
            {'money': money, 'tiles': board, 'farmer': [4,4], 'hands': hands, 'hires_today': 0},
            {'money': 1000, 'tiles': [[None for _ in range(10)] for _ in range(10)], 'farmer': [4,4], 'hands': [[4,4]], 'hires_today': 0},
        ],
        'private': {'shed': shed, 'inventories': invs},
        'town': {'unlocked_shops': shops},
        'market': {'prices': prices},
    }


def action(market=None, farmer=None, hands=None):
    return {'farmer': farmer or ['PASS'], 'hands': hands or [['PASS']], 'market': market or []}


def tape(step=100, future=None):
    t = [action() for _ in range(719)]
    if future:
        for off, a in future.items(): t[step+off] = a
    return t


class S2Tests(unittest.TestCase):
    def test_disabled_is_exact_parent(self):
        p = action([['BUY_ANIMAL','COW',1]])
        self.assertIs(s2.apply_s2_swap(obs(), p, s2.new_state(), enabled=False,
                                       configuration=CFG, native_tape=tape()), p)

    def test_invalid_player_fails_closed(self):
        o = obs(); o['player'] = 2; o['farms'].append(o['farms'][0])
        p = action([['BUY_ANIMAL','COW',1]])
        self.assertIs(s2.apply_s2_swap(o, p, s2.new_state(), enabled=True,
                                       configuration=CFG, native_tape=tape()), p)

    def test_nonstandard_config_fails_closed(self):
        p = action([['BUY_ANIMAL','COW',1]])
        bad = dict(CFG, shedCapacity=101)
        self.assertIs(s2.apply_s2_swap(obs(), p, s2.new_state(), enabled=True,
                                       configuration=bad, native_tape=tape()), p)


    def test_nonstandard_episode_length_fails_closed(self):
        p = action([['BUY_ANIMAL','COW',1]])
        bad = dict(CFG, episodeSteps=719)
        self.assertIs(s2.apply_s2_swap(obs(), p, s2.new_state(), enabled=True,
                                       configuration=bad, native_tape=tape()), p)

    def test_future_unknown_or_malformed_market_row_vetoes(self):
        for row in (['MYSTERY', 1, 1], ('BUY_LAND',), "not-a-row"):
            with self.subTest(row=row):
                st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1]])
                nt = tape(future={1: {'farmer':['PASS'],'hands':[['PASS']],'market':[row]}})
                out = s2.apply_s2_swap(obs(), p, st, enabled=True, configuration=CFG, native_tape=nt)
                self.assertEqual(out['market'][0][1], 'COW')

    def test_current_unknown_or_malformed_market_row_vetoes(self):
        for row in (['MYSTERY', 1, 1], ('SELL', 'WOOL', 1), "bad"):
            with self.subTest(row=row):
                st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1], row])
                out = s2.apply_s2_swap(obs(), p, st, enabled=True, configuration=CFG, native_tape=tape())
                self.assertEqual(out['market'][0][1], 'COW')

    def test_non_int_buy_quantity_fails_closed(self):
        for qty in (True, "1", 1.0):
            with self.subTest(qty=qty):
                st = s2.new_state(); p = action([['BUY_ANIMAL','COW',qty]])
                out = s2.apply_s2_swap(obs(), p, st, enabled=True, configuration=CFG, native_tape=tape())
                self.assertEqual(out['market'][0][1], 'COW')

    def test_callback_gap_clears_pending_transaction(self):
        st = s2.new_state(); st['last'] = 100; st['pending_buy'] = {'before':0,'quantity':1}; st['requested']=1
        o = obs(step=102, shed={'SHEEP':1})
        p = action(farmer=['PICKUP','COW',1])
        out = s2.apply_s2_swap(o, p, st, enabled=True, configuration=CFG, native_tape=tape(step=102))
        self.assertEqual(out['farmer'], ['PICKUP','COW',1])
        self.assertIsNone(st['pending_buy'])
        self.assertEqual(st['reserved'], 0)

    def test_basic_buy_rewrite_and_pending(self):
        st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1]])
        out = s2.apply_s2_swap(obs(), p, st, enabled=True, configuration=CFG, native_tape=tape())
        self.assertEqual(out['market'], [['BUY_ANIMAL','SHEEP',1]])
        self.assertEqual(st['pending_buy']['quantity'], 1)
        self.assertEqual(p['market'], [['BUY_ANIMAL','COW',1]])

    def test_near_cash_parent_cow_success_but_sheep_fails_closed(self):
        st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1]])
        out = s2.apply_s2_swap(obs(money=499), p, st, enabled=True, configuration=CFG, native_tape=tape())
        self.assertEqual(out['market'], [['BUY_ANIMAL','COW',1]])
        self.assertIsNone(st['pending_buy'])

    def test_current_other_purchase_vetoes(self):
        st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1], ['HIRE']])
        out = s2.apply_s2_swap(obs(money=5000), p, st, enabled=True, configuration=CFG, native_tape=tape())
        self.assertEqual(out['market'][0][1], 'COW')

    def test_future_same_day_purchase_vetoes(self):
        st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1]])
        nt = tape(future={2: action([['BUY_LAND']])})
        out = s2.apply_s2_swap(obs(), p, st, enabled=True, configuration=CFG, native_tape=nt)
        self.assertEqual(out['market'][0][1], 'COW')

    def test_milk_shop_vetoes(self):
        st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1]])
        out = s2.apply_s2_swap(obs(shops=['YARN_STORE','PIZZA_SHOP']), p, st,
                               enabled=True, configuration=CFG, native_tape=tape())
        self.assertEqual(out['market'][0][1], 'COW')

    def test_v233_two_yarn_overlap_veto_after_day12(self):
        st = s2.new_state(); p = action([['BUY_ANIMAL','COW',1]])
        out = s2.apply_s2_swap(obs(step=300, shops=['YARN_STORE','YARN_STORE']), p, st,
                               enabled=True, configuration=CFG, native_tape=tape(step=300))
        self.assertEqual(out['market'][0][1], 'COW')

    def test_confirmed_swap_redirects_linked_pickup_only(self):
        st = s2.new_state(); st['last'] = 100; st['pending_buy'] = {'before':0,'quantity':1}; st['requested']=1
        o = obs(step=101, shed={'SHEEP':1})
        p = action(farmer=['PICKUP','COW',1])
        out = s2.apply_s2_swap(o, p, st, enabled=True, configuration=CFG, native_tape=tape(step=101))
        self.assertEqual(out['farmer'], ['PICKUP','SHEEP',1])
        self.assertEqual(st['picked'], 1)

    def test_failed_swap_never_hijacks_native_pickup(self):
        st = s2.new_state(); st['last'] = 100; st['pending_buy'] = {'before':0,'quantity':1}; st['requested']=1
        o = obs(step=101, shed={})
        p = action(farmer=['PICKUP','COW',1])
        out = s2.apply_s2_swap(o, p, st, enabled=True, configuration=CFG, native_tape=tape(step=101))
        self.assertEqual(out['farmer'], ['PICKUP','COW',1])
        self.assertEqual(st['failed_purchase_units'], 1)

    def test_carrying_swap_redirects_place_and_confirms(self):
        st = s2.new_state(); st['last'] = 101; st['carrying']={0:1}; st['requested']=1
        o = obs(step=102, invs=[{'SHEEP':1},{}]); o['farms'][0]['tiles'][4][4]=tile(kind='PASTURE')
        p = action(farmer=['PLACE','COW'])
        out = s2.apply_s2_swap(o, p, st, enabled=True, configuration=CFG, native_tape=tape(step=102))
        self.assertEqual(out['farmer'], ['PLACE','SHEEP'])
        self.assertEqual(len(st['pending_places']), 1)
        # Next callback confirms the physical sheep.
        o2 = obs(step=103, invs=[{},{}]); o2['farms'][0]['tiles'][4][4]=tile(kind='PASTURE', animal='SHEEP', placed_day=4)
        s2.apply_s2_swap(o2, action(), st, enabled=True, configuration=CFG, native_tape=tape(step=103))
        self.assertEqual(st['placed'], 1)

    def test_wool_credit_only_tops_existing_sale(self):
        st = s2.new_state(); st['last']=110; st['sites']={(4,4):4}
        o = obs(step=111, shed={'WOOL':5}); o['farms'][0]['tiles'][4][4]=tile(kind='PASTURE', animal='SHEEP', placed_day=4, yield_units=2)
        p = action([['SELL','WOOL',3]], farmer=['HARVEST'])
        out = s2.apply_s2_swap(o, p, st, enabled=True, configuration=CFG, native_tape=tape(step=111))
        self.assertEqual(out['market'], [['SELL','WOOL',5]])
        self.assertEqual(st['extra_wool_sale_requests'], 2)

    def test_wool_credit_never_appends_new_sale(self):
        st = s2.new_state(); st['last']=110; st['wool_credit']=2
        o = obs(step=111, shed={'WOOL':5})
        out = s2.apply_s2_swap(o, action(), st, enabled=True, configuration=CFG, native_tape=tape(step=111))
        self.assertEqual(out['market'], [])
        self.assertEqual(st['wool_credit'], 2)


if __name__ == '__main__':
    unittest.main()

import importlib.util
from pathlib import Path
import tempfile
import unittest

from seller_regime_history import PublicRegimeHistory

PRODUCTS = ('CARROT', 'MILK')


def product_of(tile):
    if not isinstance(tile, dict):
        return None
    if tile.get('kind') == 'PLANT':
        return tile.get('crop')
    if tile.get('kind') == 'ANIMAL':
        return tile.get('product')
    return None


def tile(product='CARROT', yield_units=0):
    return {'kind': 'PLANT', 'crop': product, 'yield_units': yield_units}


def obs(step, *, rival_tile=None, inventory=None, player=0):
    rival_tile = {} if rival_tile is None else rival_tile
    inventory = {'CARROT': 10, 'MILK': 10} if inventory is None else inventory
    farm = {'tiles': [[rival_tile]]}
    empty = {'tiles': [[{}]]}
    return {
        'step': step,
        'player': player,
        'farms': [empty, farm] if player == 0 else [farm, empty],
        'market': {'inventory': dict(inventory)},
        'town': {'unlocked_shops': []},
    }


def no_absorption(product, step, shops, configuration):
    return 0


class RegimeHistoryTests(unittest.TestCase):
    def test_same_producer_yield_drop_is_harvest_evidence(self):
        h = PublicRegimeHistory()
        before = obs(0, rival_tile=tile(yield_units=4))
        after = obs(1, rival_tile=tile(yield_units=1))
        h.observe(before, after, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.signal(1, 'CARROT')['short'], 3)

    def test_removed_producer_is_not_counted_as_harvest(self):
        h = PublicRegimeHistory()
        before = obs(0, rival_tile=tile(yield_units=4))
        after = obs(1, rival_tile={})
        h.observe(before, after, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.signal(1, 'CARROT')['short'], 0)

    def test_one_event_does_not_extend_after_short_window(self):
        h = PublicRegimeHistory()
        h.harvests['CARROT'] = [(2, 9)]
        self.assertEqual(h.signal(12, 'CARROT')['stress'], 0)
        self.assertEqual(h.signal(12, 'CARROT')['long_rate'], 0)

    def test_repeated_events_form_bounded_long_memory(self):
        h = PublicRegimeHistory()
        h.harvests['CARROT'] = [(2, 9), (10, 9)]
        signal = h.signal(20, 'CARROT')
        self.assertEqual(signal['short'], 0)
        self.assertEqual(signal['repeat_support'], 2)
        self.assertEqual(signal['long_rate'], 6)
        self.assertEqual(signal['stress'], 6)

    def test_cross_stream_noise_cannot_resurrect_old_outlier(self):
        h = PublicRegimeHistory()
        h.harvests['CARROT'] = [(2, 90)]
        h.flows['CARROT'] = [(10, 1)]
        signal = h.signal(20, 'CARROT')
        self.assertEqual(signal['short'], 0)
        self.assertEqual(signal['harvest_repeat_support'], 1)
        self.assertEqual(signal['flow_repeat_support'], 1)
        self.assertEqual(signal['repeat_support'], 1)
        self.assertEqual(signal['long_rate'], 0)
        self.assertEqual(signal['stress'], 0)

    def test_repeated_flow_events_can_form_bounded_long_memory(self):
        h = PublicRegimeHistory()
        h.flows['CARROT'] = [(2, 3), (10, 3)]
        signal = h.signal(20, 'CARROT')
        self.assertEqual(signal['short'], 0)
        self.assertEqual(signal['flow_repeat_support'], 2)
        self.assertEqual(signal['long_rate'], 2)
        self.assertEqual(signal['stress'], 2)

    def test_town_absorption_is_not_misattributed_to_rival(self):
        h = PublicRegimeHistory()
        before = obs(0, inventory={'CARROT': 10, 'MILK': 10})
        after = obs(1, inventory={'CARROT': 9, 'MILK': 10})
        h.observe(before, after, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of,
                  absorption=lambda p, *_: 1 if p == 'CARROT' else 0)
        self.assertEqual(h.flows.get('CARROT'), None)

    def test_own_requested_sale_is_removed_before_rival_lower_bound(self):
        h = PublicRegimeHistory()
        before = obs(0, inventory={'CARROT': 10, 'MILK': 10})
        after = obs(1, inventory={'CARROT': 18, 'MILK': 10})
        action = {'market': [['SELL', 'CARROT', 5]]}
        h.observe(before, after, action, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.flows['CARROT'], [(1, 3)])

    def test_missing_previous_action_keeps_residual_flow_unknown(self):
        h = PublicRegimeHistory()
        before = obs(0, inventory={'CARROT': 10, 'MILK': 10})
        after = obs(1, inventory={'CARROT': 20, 'MILK': 10})
        h.observe(before, after, None, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.flows.get('CARROT'), None)

    def test_mix_change_requires_persistence_and_resets_old_evidence(self):
        h = PublicRegimeHistory(change_confirmations=2)
        base = obs(0, rival_tile=tile('CARROT', 0))
        h.observe(None, base, None, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        h.harvests['CARROT'] = [(0, 8), (1, 8)]
        changed1 = obs(2, rival_tile=tile('MILK', 0))
        h.observe(base, changed1, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.regime_step, 0)
        changed2 = obs(3, rival_tile=tile('MILK', 0))
        h.observe(changed1, changed2, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.regime_step, 3)
        self.assertEqual(h.signal(3, 'CARROT')['stress'], 0)

    def test_same_step_retry_does_not_advance_mix_confirmation(self):
        h = PublicRegimeHistory(change_confirmations=2)
        base = obs(0, rival_tile=tile('CARROT', 0))
        changed1 = obs(1, rival_tile=tile('MILK', 0))
        changed2 = obs(2, rival_tile=tile('MILK', 0))
        h.observe(None, base, None, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        h.observe(base, changed1, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.regime_step, 0)
        self.assertEqual(h.candidate_streak, 1)
        h.observe(changed1, changed1, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.regime_step, 0)
        self.assertEqual(h.candidate_streak, 1)
        h.observe(changed1, changed2, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.regime_step, 2)
        self.assertEqual(h.candidate_streak, 0)

    def test_backward_step_reseeds_and_clears_old_evidence(self):
        h = PublicRegimeHistory(change_confirmations=2)
        base = obs(5, rival_tile=tile('CARROT', 0))
        changed = obs(6, rival_tile=tile('MILK', 0))
        rewind = obs(2, rival_tile=tile('MILK', 0))
        h.observe(None, base, None, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        h.harvests['CARROT'] = [(5, 9)]
        h.flows['CARROT'] = [(5, 4)]
        h.observe(base, changed, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.candidate_streak, 1)
        h.observe(changed, rewind, {'market': []}, {}, products=PRODUCTS,
                  product_of=product_of, absorption=no_absorption)
        self.assertEqual(h.regime_step, 2)
        self.assertEqual(h.candidate_streak, 0)
        self.assertEqual(h.signal(2, 'CARROT')['stress'], 0)
        self.assertEqual(dict(h.harvests), {})
        self.assertEqual(dict(h.flows), {})

    def test_wrapper_initializes_opening_mix_before_first_transition(self):
        here = Path(__file__).resolve().parent
        stub = """\
PRODUCTS = ('CARROT', 'MILK')
class _M:
    ANIMALS = {}
m = _M()
def absorption(*args):
    return 0
class SellScheduler:
    def __init__(self, mode='candidate'):
        self.previous = None
        self.diagnostics = {}
    def observe(self, obs):
        self.previous = obs
    def act(self, obs, configuration=None):
        self.observe(obs)
        return {'market': []}
"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'scheduler.py').write_text(stub)
            (root / 'seller_regime_history.py').write_text(
                (here / 'seller_regime_history.py').read_text())
            (root / 'regime_scheduler.py').write_text(
                (here / 'regime_scheduler.py').read_text())
            spec = importlib.util.spec_from_file_location(
                'e17_wrapper_lifecycle_test', root / 'regime_scheduler.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            scheduler = module.RegimeSellScheduler()
            opening = obs(0, rival_tile=tile('CARROT', 0))
            shifted1 = obs(1, rival_tile=tile('MILK', 0))
            shifted2 = obs(2, rival_tile=tile('MILK', 0))
            scheduler.act(opening, {})
            self.assertEqual(scheduler.regime_history.regime_step, 0)
            self.assertEqual(scheduler.regime_history.candidate_streak, 0)
            scheduler.act(shifted1, {})
            self.assertEqual(scheduler.regime_history.regime_step, 0)
            self.assertEqual(scheduler.regime_history.candidate_streak, 1)
            scheduler.act(shifted2, {})
            self.assertEqual(scheduler.regime_history.regime_step, 2)
            self.assertEqual(scheduler.regime_history.candidate_streak, 0)

    def test_stress_is_capacity_bounded(self):
        h = PublicRegimeHistory(capacity=100)
        h.harvests['CARROT'] = [(1, 500)]
        self.assertEqual(h.signal(1, 'CARROT')['stress'], 100)


if __name__ == '__main__':
    unittest.main()

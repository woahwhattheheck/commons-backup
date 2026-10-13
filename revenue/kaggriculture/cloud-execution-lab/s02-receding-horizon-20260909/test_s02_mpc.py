import copy
import importlib.util
import unittest
from pathlib import Path

from s02_mpc import RecedingHorizonGate, prefix_compatible_routes, visibility_certificate, would_strand_obligation

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('s02_arlene', ROOT/'reference/next-panel/vendor/arlene.py')
arlene = importlib.util.module_from_spec(spec); spec.loader.exec_module(arlene)


def obs(step=226):
    return {
        'step': step, 'player': 0,
        'farms': [
            {'money': 10000, 'farmer': [4,4], 'hands': [], 'tiles': [[None]*10 for _ in range(10)]},
            {'money': 10000, 'farmer': [5,5], 'hands': [], 'tiles': [[None]*10 for _ in range(10)]},
        ],
        'private': {'shed': {'WHEAT': 3}, 'seeds': {'WHEAT': 2}, 'inventories': [{}]},
        'market': {'inventory': {}, 'prices': {}}, 'town': {'unlocked_shops': []},
    }


class S02Contracts(unittest.TestCase):
    def test_live_schema_cannot_certify_exact_reacting_rollout(self):
        c = visibility_certificate(obs(226), {'turnsPerDay':24}, 6)
        self.assertFalse(c.exact)
        self.assertIn('missing_rival_private_for_exact_reacting_transition', c.reasons)

    def test_injected_rival_private_is_not_an_admissible_escape_hatch(self):
        value = obs(226); value['rival_private']={'shed':{'MILK':100}}
        c = visibility_certificate(value, {'turnsPerDay':24}, 6)
        self.assertFalse(c.exact)
        self.assertIn('missing_rival_private_for_exact_reacting_transition', c.reasons)

    def test_24_step_branch_rollouts_cross_hidden_day_rng(self):
        for step in (226,360,433):
            c = visibility_certificate(obs(step), {'turnsPerDay':24}, 24)
            self.assertIn('hidden_end_of_day_rng_seed', c.reasons)

    def test_real_branch_prefix_compatibility_is_bounded(self):
        routes=arlene.routes()
        self.assertEqual(set(prefix_compatible_routes(routes, arlene.MAIN, 226)),
                         {arlene.YARN, arlene.YARN_CARROT, arlene.MILK_GLUT})
        self.assertEqual(set(prefix_compatible_routes(routes, arlene.MAIN, 360)), {arlene.MILK_GLUT})
        self.assertEqual(set(prefix_compatible_routes(routes, arlene.MAIN, 433)), {arlene.MILK_GLUT})

    def test_short_horizon_liquidation_rejected_when_it_strands_feed(self):
        value=obs(10)
        route=[{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(20)]
        route[11]={'farmer':['FEED'],'hands':[],'market':[]}
        candidate={'farmer':['PASS'],'hands':[],'market':[['SELL','WHEAT',3]]}
        self.assertTrue(would_strand_obligation(value,candidate,route,6))
        safe=copy.deepcopy(candidate); safe['market']=[['SELL','WHEAT',2]]
        self.assertFalse(would_strand_obligation(value,safe,route,6))

    def test_gate_is_deterministic_fail_closed(self):
        g=RecedingHorizonGate(12)
        a=g.inspect(obs(226), {'turnsPerDay':24})
        b=g.inspect(obs(226), {'turnsPerDay':24})
        self.assertEqual(a,b)
        self.assertEqual(g.fallbacks,2)
        self.assertFalse(a['changed_route'])

if __name__ == '__main__': unittest.main()

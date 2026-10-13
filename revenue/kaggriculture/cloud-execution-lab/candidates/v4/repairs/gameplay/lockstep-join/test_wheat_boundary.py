import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from native_return_bridge import ReturnBridge
from test_native_return_bridge import Instance, action, cert, confirmed, flow_bounds, obs


class WheatBoundaryTest(unittest.TestCase):
    def test_certified_wheat_signal_cannot_cross_native_seller_boundary(self):
        bridge = ReturnBridge(flow_bounds, confirmed, cert, threshold=150)
        instance = Instance()
        bridge.signal_step = 5
        bridge.confirmed = {'WHEAT': 400}
        baseline = action([[]])
        before = copy.deepcopy((instance.consumer.planned, instance.consumer.pending,
                                instance._completed_seller_state))
        returned, proposal = bridge.propose(instance, obs(5), {}, baseline)
        self.assertIs(returned, baseline)
        self.assertIsNone(proposal)
        self.assertEqual((instance.consumer.planned, instance.consumer.pending,
                          instance._completed_seller_state), before)
        self.assertEqual(bridge.last_report['reason'], 'no_owned_future_sale_debt')


if __name__ == '__main__':
    unittest.main()

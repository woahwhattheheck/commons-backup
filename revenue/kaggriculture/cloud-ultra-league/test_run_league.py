"""Detailed actor reports retain the existing evaluator's measured samples."""
import unittest
from run_league import detailed_actor

class BaseActor:
    def report(self):
        return {'calls': 3, 'failure': 'retained', 'max_rpc_seconds': max(self.stats['rpc_seconds'])}

class DetailTests(unittest.TestCase):
    def test_samples_and_parent_fields_are_retained_without_aliasing(self):
        actor = detailed_actor(BaseActor)()
        actor.stats = {'call_seconds': [0.01, 0.02, 0.3], 'rpc_seconds': [0.03, 0.04, 0.4]}
        result = actor.report()
        self.assertEqual(result['failure'], 'retained')
        self.assertEqual(result['call_seconds'], [0.01, 0.02, 0.3])
        self.assertEqual(result['rpc_seconds'], [0.03, 0.04, 0.4])
        result['call_seconds'].clear()
        self.assertEqual(len(actor.stats['call_seconds']), 3)

if __name__ == '__main__':
    unittest.main()

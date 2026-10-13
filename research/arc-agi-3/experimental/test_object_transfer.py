from __future__ import annotations

from pathlib import Path
import sys
_PARENT = Path(__file__).resolve().parents[1]
if (_PARENT / "arc3_baseline.py").exists() and str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import unittest

from arc3_baseline import NoveltyExplorer
from arc3_object_transfer import (
    ObjectTransferExplorer,
    extract_components,
    infer_single_translation,
)


def row(player_x: int, width: int = 8):
    values = [0] * width
    values[player_x] = 1
    values[-1] = 8
    return [values]


class ObjectTransferTests(unittest.TestCase):
    def test_extract_component_fingerprint_is_translation_invariant(self):
        _, left = extract_components(tuple(tuple(r) for r in row(2)))
        _, right = extract_components(tuple(tuple(r) for r in row(3)))
        mobile_left = next(c for c in left if c.color == 1)
        mobile_right = next(c for c in right if c.color == 1)
        self.assertEqual(mobile_left.fingerprint, mobile_right.fingerprint)
        self.assertNotEqual(mobile_left.origin, mobile_right.origin)

    def test_infer_single_translation(self):
        before = tuple(tuple(r) for r in row(2))
        after = tuple(tuple(r) for r in row(3))
        effect = infer_single_translation(before, after)
        self.assertIsNotNone(effect)
        assert effect is not None
        self.assertEqual(effect.source, (2, 0))
        self.assertEqual(effect.target, (3, 0))
        self.assertEqual(effect.delta, (1, 0))

    def test_global_action_balance_across_new_states(self):
        policy = ObjectTransferExplorer()
        self.assertEqual(policy.choose([[0]], [1, 2, 3]).action_id, 1)
        self.assertEqual(policy.choose([[1]], [1, 2, 3]).action_id, 2)
        self.assertEqual(policy.choose([[2]], [1, 2, 3]).action_id, 3)

    def test_object_transfer_selects_unseen_predicted_position(self):
        policy = ObjectTransferExplorer()
        a = row(2)
        b = row(3)
        self.assertEqual(policy.choose(a, [1, 2]).action_id, 1)
        self.assertEqual(policy.choose(b, [1, 2]).action_id, 2)
        decision = policy.choose(a, [1, 2])
        self.assertEqual(decision.action_id, 2)
        self.assertIn("object-frontier", decision.reason)
        self.assertEqual(policy.diagnostics()["movement_models"], 2)

    def test_blocked_prediction_replans_through_seen_positions(self):
        policy = ObjectTransferExplorer()
        a, b, c = row(2), row(3), row(1)
        self.assertEqual(policy.choose(a, [1, 2]).action_id, 1)  # learn +1 on next observation
        self.assertEqual(policy.choose(b, [1, 2]).action_id, 2)  # learn -1 on next observation
        self.assertEqual(policy.choose(a, [1, 2]).action_id, 2)  # predicted unseen x=1
        self.assertEqual(policy.choose(c, [1, 2]).action_id, 2)  # predicts x=0
        # Simulate a wall/no-change for ACTION2 at x=1. The model must mark it
        # blocked and route right through visited x=2,x=3 toward unseen x=4.
        replanned = policy.choose(c, [1, 2])
        self.assertEqual(replanned.action_id, 1)
        self.assertIn("object-frontier", replanned.reason)
        self.assertGreaterEqual(policy.diagnostics()["blocked_predictions"], 1)

    def test_base_v2_contract_still_available(self):
        policy = NoveltyExplorer()
        self.assertEqual(policy.choose([[0]], [4]).action_id, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)

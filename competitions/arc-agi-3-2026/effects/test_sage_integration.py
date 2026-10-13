"""Integration contract against the landed sibling SAGE core."""
import unittest

from sage_core import ActionToken, Observation, Transition, validate_grid
from sage_adapter import factor_transition, sequence_from_transition


class LandedSageIntegrationTests(unittest.TestCase):
    def test_actual_transition_preserves_animation_and_coordinate_key(self):
        before_grid = validate_grid([
            [0,0,0,0,0],
            [0,2,0,4,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
        ])
        flicker = validate_grid([
            [0,0,0,0,0],
            [0,2,0,5,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
        ])
        opened = validate_grid([
            [0,0,0,0,0],
            [0,2,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
        ])
        before = Observation((before_grid,), ("ACTION6",))
        after = Observation((before_grid, flicker, opened), ("ACTION6",))
        transition = Transition.build(before, ActionToken("ACTION6", 3, 1), after)
        seq = sequence_from_transition(transition)
        self.assertEqual(seq.action_key, "ACTION6@3,1")
        self.assertEqual(len(seq.frames), 3)
        effect = factor_transition(transition)
        self.assertIn("RECOLOR", effect.kinds)
        self.assertIn("DESPAWN", effect.kinds)
        self.assertEqual(len(effect.frame_effects), 3)


if __name__ == "__main__":
    unittest.main()

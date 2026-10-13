import copy
import json
import unittest

from factorizer import ActionSequence, factor_action, factor_pair
from mock_effects import (
    base_scene, camera_after, camera_before, compound_scene, despawn_scene,
    moved_scene, recolor_scene, sequence, spawn_scene, topology_after,
    topology_before, ui_after, ui_before,
)
from receipts import build_receipt, canonical_json, verify_receipt


class PairClassificationTests(unittest.TestCase):
    def test_no_change(self):
        self.assertEqual(factor_pair(base_scene(), base_scene()).kinds, ("NO_CHANGE",))

    def test_motion(self):
        effect = factor_pair(base_scene(), moved_scene())
        self.assertIn("MOTION", effect.kinds)
        self.assertNotIn("CAMERA", effect.kinds)

    def test_spawn(self):
        self.assertIn("SPAWN", factor_pair(base_scene(), spawn_scene()).kinds)

    def test_despawn(self):
        self.assertIn("DESPAWN", factor_pair(base_scene(), despawn_scene()).kinds)

    def test_recolor(self):
        effect = factor_pair(base_scene(), recolor_scene())
        self.assertIn("RECOLOR", effect.kinds)
        self.assertNotIn("SPAWN", effect.kinds)
        self.assertNotIn("DESPAWN", effect.kinds)

    def test_topology_split(self):
        effect = factor_pair(topology_before(), topology_after())
        self.assertIn("TOPOLOGY", effect.kinds)

    def test_border_change_is_ui_not_spawn(self):
        effect = factor_pair(ui_before(), ui_after())
        self.assertEqual(effect.kinds, ("UI",))

    def test_coherent_multi_object_translation_is_camera(self):
        effect = factor_pair(camera_before(), camera_after())
        self.assertIn("CAMERA", effect.kinds)
        self.assertNotIn("MOTION", effect.kinds)

    def test_motion_plus_spawn_is_compound(self):
        effect = factor_pair(base_scene(), compound_scene())
        self.assertIn("MOTION", effect.kinds)
        self.assertIn("SPAWN", effect.kinds)
        self.assertIn("COMPOUND", effect.kinds)

    def test_nonzero_background_supported(self):
        before = tuple(tuple(9 if (x,y)!=(2,2) else 2 for x in range(5)) for y in range(5))
        after = tuple(tuple(9 if (x,y)!=(3,2) else 2 for x in range(5)) for y in range(5))
        self.assertIn("MOTION", factor_pair(before, after).kinds)

    def test_shape_change_is_ambiguous(self):
        self.assertEqual(factor_pair(((0,0),(0,1)), ((0,0,0),(0,1,0))).kinds, ("AMBIGUOUS",))

    def test_bool_cell_rejected(self):
        with self.assertRaises(ValueError):
            factor_pair(((0, False),), ((0,0),))


class TemporalAndReceiptTests(unittest.TestCase):
    def test_animation_retains_recolor_then_despawn(self):
        before = [list(r) for r in base_scene()]
        before[4][4] = 4
        flicker = copy.deepcopy(before); flicker[4][4] = 5
        opened = copy.deepcopy(flicker); opened[4][4] = 0
        seq = ActionSequence("ACTION7", tuple(map(tuple, before)), (tuple(map(tuple, before)), tuple(map(tuple, flicker)), tuple(map(tuple, opened))))
        effect = factor_action(seq)
        self.assertIn("RECOLOR", effect.kinds)
        self.assertIn("DESPAWN", effect.kinds)
        self.assertEqual(len(effect.frame_effects), 3)

    def test_action_names_do_not_determine_semantics(self):
        observed = set()
        for seed in range(100):
            observed.add(factor_action(sequence(seed, base_scene(), (moved_scene(),))).kinds)
        self.assertEqual(observed, {("MOTION",)})

    def test_input_change_changes_digest(self):
        a = factor_action(sequence(1, base_scene(), (moved_scene(),)))
        b = factor_action(sequence(1, base_scene(), (spawn_scene(),)))
        self.assertNotEqual(a.input_sha256, b.input_sha256)

    def test_receipt_verifies(self):
        seq = sequence(3, base_scene(), (compound_scene(),))
        self.assertTrue(verify_receipt(build_receipt(seq), seq))

    def test_result_tamper_fails(self):
        seq = sequence(3, base_scene(), (compound_scene(),))
        receipt = build_receipt(seq)
        receipt["result"]["kinds"] = ["NO_CHANGE"]
        self.assertFalse(verify_receipt(receipt, seq))

    def test_resealed_authority_escalation_fails(self):
        from hashlib import sha256
        seq = sequence(3, base_scene(), (compound_scene(),))
        receipt = build_receipt(seq)
        receipt["claim_boundary"]["competition_submission_authorized"] = True
        body = dict(receipt); body.pop("receipt")
        receipt["receipt"]["payload_sha256"] = sha256(canonical_json(body).encode()).hexdigest()
        self.assertFalse(verify_receipt(receipt, seq))

    def test_sequence_mismatch_fails(self):
        seq = sequence(3, base_scene(), (compound_scene(),))
        other = sequence(3, base_scene(), (spawn_scene(),))
        self.assertFalse(verify_receipt(build_receipt(seq), other))

    def test_deterministic_json(self):
        seq = sequence(9, base_scene(), (moved_scene(), spawn_scene()))
        self.assertEqual(canonical_json(build_receipt(seq)), canonical_json(build_receipt(seq)))


class SageAdapterContractTests(unittest.TestCase):
    def test_duck_adapter_retains_all_frames_and_complex_key(self):
        from types import SimpleNamespace
        from sage_adapter import factor_transition, sequence_from_transition
        before = base_scene()
        mid = recolor_scene()
        after = despawn_scene()
        transition = SimpleNamespace(
            before=SimpleNamespace(frame=before),
            action=SimpleNamespace(key="ACTION6@2,3"),
            after=SimpleNamespace(frames=(mid, after)),
        )
        seq = sequence_from_transition(transition)
        self.assertEqual(seq.action_key, "ACTION6@2,3")
        self.assertEqual(seq.frames, (mid, after))
        effect = factor_transition(transition)
        self.assertEqual(len(effect.frame_effects), 2)

    def test_adapter_has_no_action_semantic_table(self):
        import pathlib
        text = pathlib.Path("sage_adapter.py").read_text(encoding="utf-8")
        for semantic in ("UP", "DOWN", "LEFT", "RIGHT", "INTERACT"):
            self.assertNotIn(semantic, text)


class HeldOutBenchmarkTests(unittest.TestCase):
    def test_held_out_taxonomy_matrix(self):
        from benchmark import run
        report = run(20)
        self.assertEqual(report["passed"], report["cases"])
        self.assertEqual(report["cases"], 180)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

import evaluate as ev
import causal_action_splice as splice


class FakeActor:
    opponent_launches = 0
    drift_opponent_launch: int | None = None
    drift_opponent_step = 0
    drift_focal_run: int | None = None
    mutate_source = False

    def __init__(self, spec, cache, loader, rng_seed, startup_timeout=10.0):
        self.spec = spec
        self.ready = {"kind": "ready"}
        self.calls = 0
        if "::" in spec:
            self.role = Path(spec.partition("::")[0]).parent.name
        else:
            self.role = spec
        self.is_opponent = self.role == "opponent" or spec == "opponent"
        if self.is_opponent:
            type(self).opponent_launches += 1
            self.launch = type(self).opponent_launches
        else:
            self.launch = 0
        if type(self).mutate_source and "::" in spec:
            root = Path(spec.partition("::")[0]).parent
            os.chmod(root, 0o755)
            (root / "mutated.txt").write_text("changed", encoding="utf-8")

    def act(self, observation, configuration, timeout):
        step = int(observation["step"])
        self.calls += 1
        current_run = type(self).opponent_launches
        if self.is_opponent:
            amount = (
                99
                if self.launch == type(self).drift_opponent_launch
                and step == type(self).drift_opponent_step
                else 0
            )
        elif type(self).drift_focal_run == current_run and step == 0:
            amount = 7
        elif self.spec == "typed":
            amount = 1.0 if step == 0 else 1
        elif (
            self.spec == "candidate"
            or self.role == "shadow"
            or "candidate" in self.role
        ):
            amount = 2 if step == 1 else 1
        else:
            amount = 1
        return {"kind": "action", "action": {"move": amount}}

    def close(self):
        pass

    def report(self):
        return {"calls": self.calls, "launch": self.launch}


class FakeEngine:
    specification = {
        "configuration": {
            "episodeSteps": {"default": 3},
            "turnsPerDay": {"default": 2},
        }
    }

    def interpreter(self, state, env):
        if not state[0].observation:
            env.configuration.seed = None
            env.info["total"] = [0, 0]
            for seat in range(2):
                state[seat].observation = ev.Struct(
                    player=seat,
                    step=0,
                    farms=[{"money": 0.0}, {"money": 0.0}],
                )
            return
        totals = env.info["total"]
        for seat in range(2):
            totals[seat] += int(state[seat].action["move"])
        step = int(state[0].observation.step)
        farms = [
            {"money": float(totals[0])},
            {"money": float(totals[1])},
        ]
        for seat in range(2):
            state[seat].observation = ev.Struct(
                player=seat,
                step=step + 1,
                farms=farms,
            )
        if step + 1 >= env.configuration.episodeSteps:
            for seat in range(2):
                state[seat].status = "DONE"
                state[seat].reward = float(totals[seat])


class EarlyTerminalEngine(FakeEngine):
    def interpreter(self, state, env):
        super().interpreter(state, env)
        if state[0].observation and int(state[0].observation.step) >= 1:
            for seat in range(2):
                state[seat].status = "DONE"
                state[seat].reward = float(env.info["total"][seat])


class CausalActionSpliceTests(unittest.TestCase):
    def setUp(self):
        FakeActor.opponent_launches = 0
        FakeActor.drift_opponent_launch = None
        FakeActor.drift_opponent_step = 0
        FakeActor.drift_focal_run = None
        FakeActor.mutate_source = False
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def common(self, candidate="candidate", engine=None):
        return dict(
            engine=engine or FakeEngine(),
            baseline=splice.AgentBlueprint.literal("baseline"),
            candidate=splice.AgentBlueprint.literal(candidate),
            opponent=splice.AgentBlueprint.literal("opponent"),
            cache=Path("."),
            loader=Path("loader.py"),
            workspace=Path(self.temporary.name),
            seed=7,
            focal_seat=0,
            actor_factory=FakeActor,
        )

    def test_supported_first_divergence_binds_both_hybrid_targets(self):
        cell = splice.evaluate_cell(**self.common())
        self.assertEqual(cell["classification"], "hybrid_own_supported")
        self.assertEqual(cell["divergence"]["step"], 1)
        self.assertEqual(
            cell["divergence"]["differing_paths"], ["$.move"]
        )
        self.assertTrue(all(cell["replay"].values()))
        self.assertEqual(
            cell["effects"]["candidate_action_on_baseline"][
                "focal_score"
            ],
            1.0,
        )
        self.assertEqual(
            cell["effects"]["candidate_action_on_candidate"][
                "focal_score"
            ],
            1.0,
        )
        self.assertEqual(
            cell["outcomes"]["candidate_action_on_baseline"][
                "transition"
            ],
            "W->W",
        )

    def test_dormant_candidate(self):
        cell = splice.evaluate_cell(
            **self.common(candidate="baseline")
        )
        self.assertEqual(cell["classification"], "dormant")
        self.assertIsNone(cell["divergence"])
        self.assertIsNone(cell["effects"])

    def test_action_comparison_is_type_sensitive(self):
        cell = splice.evaluate_cell(**self.common(candidate="typed"))
        self.assertEqual(cell["divergence"]["step"], 0)
        self.assertEqual(
            cell["divergence"]["differing_paths"], ["$.move"]
        )
        self.assertNotEqual(
            cell["divergence"]["policy_action_sha256"],
            cell["divergence"]["shadow_action_sha256"],
        )

    def test_third_launch_opponent_prefix_drift_is_rejected(self):
        FakeActor.drift_opponent_launch = 5
        FakeActor.drift_opponent_step = 0
        cell = splice.evaluate_cell(**self.common())
        run = cell["runs"]["candidate_action_on_baseline"]
        self.assertEqual(cell["classification"], "failed")
        self.assertEqual(
            run["failure"]["kind"], "target_context_mismatch"
        )
        self.assertFalse(run["failure"]["checks"]["context"])

    def test_target_step_opponent_action_drift_is_rejected(self):
        FakeActor.drift_opponent_launch = 5
        FakeActor.drift_opponent_step = 1
        cell = splice.evaluate_cell(**self.common())
        run = cell["runs"]["candidate_action_on_baseline"]
        self.assertEqual(cell["classification"], "failed")
        self.assertEqual(
            run["failure"]["kind"], "target_context_mismatch"
        )
        self.assertNotEqual(
            run["failure"]["actual_context"][
                "rival_action_sha256"
            ],
            run["failure"]["expected_context"][
                "rival_action_sha256"
            ],
        )

    def test_equal_but_wrong_focal_prefix_on_hybrid_launch_is_rejected(self):
        FakeActor.drift_focal_run = 5
        cell = splice.evaluate_cell(**self.common())
        run = cell["runs"]["candidate_action_on_baseline"]
        self.assertEqual(cell["classification"], "failed")
        self.assertEqual(
            run["failure"]["kind"], "target_context_mismatch"
        )

    def test_early_terminal_before_intervention_is_rejected(self):
        result = splice.run_variant(
            EarlyTerminalEngine(),
            policy=splice.AgentBlueprint.literal("baseline"),
            shadow=splice.AgentBlueprint.literal("candidate"),
            opponent=splice.AgentBlueprint.literal("opponent"),
            cache=Path("."),
            loader=Path("loader.py"),
            workspace=Path(self.temporary.name),
            seed=7,
            focal_seat=0,
            rng_seed=1,
            intervention_step=1,
            expected_context={
                "step": 1,
                "preworld_sha256": "0" * 64,
                "observation_sha256": "0" * 64,
                "rival_observation_sha256": "0" * 64,
                "prefix_trace_sha256": "0" * 64,
                "rival_action_sha256": "0" * 64,
            },
            expected_policy_action={"move": 1},
            expected_shadow_action={"move": 2},
            actor_factory=FakeActor,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            result["failure"]["kind"], "target_not_reached"
        )

    def test_margin_improvement_cannot_mask_own_score_harm(self):
        effects = {
            "candidate_action_on_baseline": {
                "focal_score": -10,
                "opponent_score": -100,
                "margin": 90,
            },
            "candidate_action_on_candidate": {
                "focal_score": -10,
                "opponent_score": -100,
                "margin": 90,
            },
        }
        outcomes = {
            "treatment": {"before": "W", "after": "W"},
            "ablation": {"before": "W", "after": "W"},
        }
        label, metrics = splice._hybrid_classification(
            effects, outcomes
        )
        self.assertEqual(label, "hybrid_own_harmful")
        self.assertEqual(metrics["focal_score"], "harmful")
        self.assertEqual(metrics["margin"], "supported")

    def test_differing_paths_is_structural_and_stable(self):
        before = {
            "market": [["SELL", "WHEAT", 1]],
            "farmer": ["PASS"],
        }
        after = {
            "market": [
                ["SELL", "WHEAT", 2],
                ["SELL", "CORN", 1],
            ],
            "farmer": ["PASS"],
        }
        self.assertEqual(
            splice.differing_paths(before, after),
            ["$.market[0][2]", "$.market[1]"],
        )

    def test_archive_rejects_traversal(self):
        root = Path(self.temporary.name)
        archive_path = root / "bad.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            info = tarfile.TarInfo("../escape.py")
            data = b"bad"
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        with self.assertRaisesRegex(
            ValueError, "Unsafe archive member"
        ):
            splice.extract_agent_archive(archive_path, root / "out")
        self.assertFalse((root / "escape.py").exists())

    def test_archive_rejects_duplicate_normalized_paths(self):
        root = Path(self.temporary.name)
        archive_path = root / "duplicate.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for name, data in (
                ("./main.py", b"first"),
                ("main.py", b"second"),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        with self.assertRaisesRegex(
            ValueError, "Duplicate normalized"
        ):
            splice.extract_agent_archive(archive_path, root / "out")

    def test_archive_requires_root_entry(self):
        root = Path(self.temporary.name)
        archive_path = root / "no-main.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            info = tarfile.TarInfo("other.py")
            data = b"pass\n"
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        with self.assertRaisesRegex(ValueError, "root main.py"):
            splice.extract_agent_archive(archive_path, root / "out")

    def test_private_source_mutation_is_detected(self):
        root = Path(self.temporary.name)
        archive_path = root / "agent.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            data = b'def agent(o, c): return {"move": 1}\n'
            info = tarfile.TarInfo("main.py")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        store = root / "store"
        store.mkdir()
        blueprint = splice.prepare_agent(
            str(archive_path), store, "base"
        )
        FakeActor.mutate_source = True
        result = splice.run_variant(
            FakeEngine(),
            policy=blueprint,
            opponent=splice.AgentBlueprint.literal("opponent"),
            cache=Path("."),
            loader=Path("loader.py"),
            workspace=root,
            seed=1,
            focal_seat=0,
            rng_seed=1,
            actor_factory=FakeActor,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            result["failure"]["kind"], "source_mutation"
        )
        self.assertFalse(
            result["source_custody"]["policy"]["unchanged"]
        )
        splice._thaw_tree(store)

    def test_output_rejects_direct_and_hardlink_aliases(self):
        root = Path(self.temporary.name)
        source = root / "source.tar.gz"
        source.write_bytes(b"archive")
        outside = root / "outside"
        outside.mkdir()
        with self.assertRaises(ValueError):
            splice._validate_output(source, [source], [])
        hardlink = outside / "receipt.json"
        os.link(source, hardlink)
        with self.assertRaisesRegex(ValueError, "inode aliases"):
            splice._validate_output(hardlink, [source], [])


if __name__ == "__main__":
    unittest.main()

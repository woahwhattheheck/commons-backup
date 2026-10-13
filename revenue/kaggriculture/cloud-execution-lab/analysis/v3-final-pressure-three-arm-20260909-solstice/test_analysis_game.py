from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import evidence
import game_runner
import panel_analysis
import run_final_pressure_panel as runner
import variants


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


class AnalysisTests(unittest.TestCase):
    def _game(self, variant: str, seat: int) -> dict:
        score = {
            "pressure_off": 10,
            "legacy_in_pipeline": 10,
            "final_boundary": 12,
        }[variant]
        scores = [score, 5] if seat == 0 else [5, score]
        action = {
            "pressure_off": digest("action-off"),
            "legacy_in_pipeline": digest("action-legacy"),
            "final_boundary": digest("action-final"),
        }[variant]
        state = digest(
            "state-final" if variant == "final_boundary" else "state-shared"
        )
        return {
            "variant": variant,
            "opponent": "op",
            "seed": 1,
            "candidate_seat": seat,
            "status": "complete",
            "failure": None,
            "scores": scores,
            "steps": 2,
            "episode_steps": 3,
            "candidate_action_trace_sha256": digest(variant + "-actions"),
            "post_state_trace_sha256": digest(variant + "-states"),
            "step_digests": [
                {
                    "step": 0,
                    "candidate_action_sha256": action,
                    "post_state_sha256": state,
                },
                {
                    "step": 1,
                    "candidate_action_sha256": digest("common-action"),
                    "post_state_sha256": state,
                },
            ],
            "actors": [
                {"max_rpc_seconds": 0.01},
                {"max_rpc_seconds": 0.02},
            ],
        }

    def test_summary_separates_syntactic_from_realized(self):
        arms = [{"name": name} for name in variants.VARIANTS]
        games = [
            self._game(name, seat)
            for name in variants.VARIANTS
            for seat in (0, 1)
        ]
        summary = panel_analysis.summarize(games, arms, ["op"], [1])
        self.assertEqual(
            summary["development_signal"],
            "FINAL_BOUNDARY_LEADS_DEVELOPMENT",
        )
        legacy = summary["comparisons"][
            "legacy_in_pipeline_minus_pressure_off"
        ]
        self.assertEqual(legacy["syntactic_only_cells"], 2)
        self.assertEqual(legacy["post_state_changed_cells"], 0)
        final = summary["comparisons"][
            "final_boundary_minus_pressure_off"
        ]
        self.assertEqual(final["post_state_changed_cells"], 2)
        self.assertEqual(final["mean_margin_delta"], 2)
        self.assertEqual(final["new_losses"], 0)

    def test_validation_rejects_missing_cell(self):
        arms = [{"name": name} for name in variants.VARIANTS]
        games = [
            self._game(name, seat)
            for name in variants.VARIANTS
            for seat in (0, 1)
        ]
        with self.assertRaises(evidence.EvidenceError):
            panel_analysis.validate_games(games[:-1], arms, ["op"], [1])

    def test_seed_allowlist_is_fail_closed(self):
        self.assertEqual(
            runner.parse_seeds("2609099821,2609099824"),
            [2609099821, 2609099824],
        )
        with self.assertRaises(evidence.EvidenceError):
            runner.parse_seeds("2609099821,123")
        with self.assertRaises(evidence.EvidenceError):
            runner.parse_seeds("2609099821,2609099821")

    def test_opponents_reject_external_and_bind_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            source = runtime / "opponent.py"
            source.write_text(
                "def agent(obs, cfg): return {}\n", encoding="utf-8"
            )
            resolved = game_runner.opponent_specs(
                [
                    "starter=official_starter",
                    "local=runtime:opponent.py::agent",
                ],
                runtime,
            )
            self.assertEqual(
                resolved["starter"]["binding"], "official-engine"
            )
            self.assertEqual(
                resolved["local"]["sha256"], evidence.snapshot(source).sha256
            )
            with self.assertRaises(evidence.EvidenceError):
                game_runner.opponent_specs(
                    ["bad=/tmp/opponent.py::agent"], runtime
                )
            with self.assertRaises(evidence.EvidenceError):
                game_runner.opponent_specs(
                    ["bad=runtime:../outside.py::agent"], runtime
                )


class FakeStruct(dict):
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value


class FakeActor:
    instances: list["FakeActor"] = []

    def __init__(self, spec, cache, loader, rng_seed, startup_timeout):
        self.spec = spec
        self.rng_seed = rng_seed
        self.ready = {"kind": "ready"}
        self.calls = 0
        self.closed = False
        FakeActor.instances.append(self)

    def act(self, observation, configuration, timeout):
        self.calls += 1
        return {
            "kind": "action",
            "action": {
                "farmer": ["PASS"],
                "hands": [],
                "market": [["SELL", self.spec, 1]],
            },
        }

    def close(self):
        self.closed = True

    def report(self):
        return {"max_rpc_seconds": 0.001, "calls": self.calls}


class FakeEngine:
    specification = {
        "configuration": {
            "episodeSteps": {"default": 3},
            "turnsPerDay": {"default": 2},
        }
    }

    def interpreter(self, state, env):
        if not state[0].observation:
            for player in range(2):
                state[player].observation = FakeStruct(
                    player=player,
                    farms=[{"money": 10.0}, {"money": 10.0}],
                )
            env.configuration.pop("seed", None)
            return
        step = int(state[0].observation.step)
        for player in range(2):
            item = state[player].action["market"][0][1]
            state[0].observation.farms[player]["money"] += (
                2.0 if item == "candidate" else 1.0
            )
            state[1].observation.farms = state[0].observation.farms
        if step == 1:
            for player in range(2):
                state[player].status = "DONE"
                state[player].reward = state[0].observation.farms[player][
                    "money"
                ]


class AttributedPlayTests(unittest.TestCase):
    def test_play_completes_and_hashes_each_step(self):
        FakeActor.instances = []
        evaluator = SimpleNamespace(
            Struct=FakeStruct,
            Actor=FakeActor,
            encoded=lambda value: json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode(),
        )
        result = game_runner.play_attributed(
            evaluator,
            FakeEngine(),
            ["candidate", "opponent"],
            Path("."),
            Path("loader.py"),
            seed=99,
            candidate_seat=0,
            rng_seed=123,
            action_timeout=1,
            startup_timeout=1,
            game_timeout=10,
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["steps"], 2)
        self.assertEqual(len(result["step_digests"]), 2)
        self.assertTrue(
            evidence.valid_sha256(result["candidate_action_trace_sha256"])
        )
        self.assertTrue(
            evidence.valid_sha256(result["post_state_trace_sha256"])
        )
        self.assertEqual(
            [actor.rng_seed for actor in FakeActor.instances], [123, 124]
        )
        self.assertTrue(all(actor.closed for actor in FakeActor.instances))
        self.assertEqual(result["scores"], [14.0, 12.0])


if __name__ == "__main__":
    unittest.main(verbosity=2)

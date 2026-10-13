# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import regression_attribution as target


H = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()


class Fixture:
    def __init__(self, root: Path, build_count: int = 3):
        self.root = root
        self.cells = [("arlene", 101, 0), ("arlene", 101, 1)]
        self.steps = range(3)
        self.files = {}
        self.engine = self.bound("engine.bin", b"engine-v1")
        self.runner = self.bound("runner.bin", b"runner-v1")
        self.builds = []
        for index in range(build_count):
            name = f"b{index}"
            artifact = self.bound(f"{name}.tar", f"closure-{index}".encode())
            config_value = {"redundant_hire": True, "feature": index}
            config = self.bound(f"{name}.config.json", (json.dumps(config_value) + "\n").encode())
            games = self.bound(f"{name}.games.jsonl", self.game_bytes(self.default_scores()))
            trace = self.bound(f"{name}.trace.jsonl", self.trace_bytes(self.default_actions()))
            self.builds.append({
                "name": name,
                "source_commit": (str(index + 1) * 40)[:40],
                "artifact": artifact,
                "config": config,
                "games": games,
                "trace": trace,
            })
        self.manifest = {
            "schema_version": 1,
            "panel_id": "unit-panel",
            "engine": self.engine,
            "runner": self.runner,
            "grid": {
                "seeds": [101],
                "opponents": ["arlene"],
                "seats": [0, 1],
                "trace_step_start": 0,
                "trace_step_end": 2,
            },
            "policy": {
                "min_mean_own_delta": 0.0,
                "min_mean_margin_delta": 0.0,
                "max_result_regressions": 0,
                "max_new_losses": 0,
                "min_worst_cell_own_delta": -10.0,
            },
            "builds": self.builds,
        }
        self.manifest_path = root / "manifest.json"
        self.write_manifest()

    def bound(self, name: str, data: bytes):
        path = self.root / name
        path.write_bytes(data)
        spec = {"path": name, "sha256": hashlib.sha256(data).hexdigest()}
        self.files[name] = spec
        return spec

    def default_scores(self):
        return {
            ("arlene", 101, 0): [100.0, 90.0],
            ("arlene", 101, 1): [90.0, 100.0],
        }

    def default_actions(self):
        result = {}
        for cell in self.cells:
            for step in self.steps:
                result[cell, step] = {
                    "farmer": "PASS",
                    "hands": ["PASS"],
                    "market": [[]],
                }
        return result

    def game_rows(self, scores):
        return [
            {
                "opponent": opponent,
                "seed": seed,
                "candidate_seat": seat,
                "status": "complete",
                "scores": scores[(opponent, seed, seat)],
            }
            for opponent, seed, seat in self.cells
        ]

    def game_bytes(self, scores):
        return ("".join(json.dumps(row, allow_nan=True) + "\n" for row in self.game_rows(scores))).encode()

    def trace_rows(self, actions, observations=None, diagnostics=None):
        observations = observations or {}
        diagnostics = diagnostics or {}
        rows = []
        for cell in self.cells:
            for step in self.steps:
                opponent, seed, seat = cell
                row = {
                    "opponent": opponent,
                    "seed": seed,
                    "candidate_seat": seat,
                    "step": step,
                    "status": "complete",
                    "observation_sha256": observations.get((cell, step), H(f"{cell}:{step}")),
                    "action": actions[(cell, step)],
                }
                if (cell, step) in diagnostics:
                    row["diagnostics"] = diagnostics[(cell, step)]
                rows.append(row)
        return rows

    def trace_bytes(self, actions, observations=None, diagnostics=None):
        return (
            "".join(
                json.dumps(row, allow_nan=True) + "\n"
                for row in self.trace_rows(actions, observations, diagnostics)
            )
        ).encode()

    def replace_bound(self, build_index, field, data):
        name = self.builds[build_index][field]["path"]
        self.builds[build_index][field] = self.bound(name, data)
        self.write_manifest()

    def set_scores(self, build_index, scores):
        self.replace_bound(build_index, "games", self.game_bytes(scores))

    def set_trace(self, build_index, actions, observations=None, diagnostics=None):
        self.replace_bound(
            build_index, "trace", self.trace_bytes(actions, observations, diagnostics)
        )

    def set_config(self, build_index, value):
        self.replace_bound(
            build_index,
            "config",
            (json.dumps(value, sort_keys=True, allow_nan=True) + "\n").encode(),
        )

    def write_manifest(self):
        self.manifest_path.write_text(
            json.dumps(self.manifest, sort_keys=True, allow_nan=True) + "\n",
            encoding="utf-8",
        )


class RegressionAttributionTests(unittest.TestCase):
    def make(self, count=3):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Fixture(Path(temporary.name), count)

    def test_no_regression_with_market_first_divergence(self):
        fixture = self.make()
        actions = fixture.default_actions()
        actions[(fixture.cells[0], 1)] = {
            "farmer": "PASS",
            "hands": ["PASS"],
            "market": [["SELL", "WHEAT", 1]],
        }
        fixture.set_trace(1, actions)
        fixture.set_trace(2, actions)
        report = target.run_attribution(fixture.manifest_path)
        self.assertEqual(report["verdict"], "NO_REGRESSION")
        trace = report["adjacent_transitions"][0]["trace_attribution"]
        self.assertEqual(trace["earliest_divergence_step"], 1)
        self.assertEqual(trace["category_counts"], {"market_only": 1})
        self.assertEqual(trace["cells"][0]["market_first_difference"]["index"], 0)

    def test_finds_first_regression_and_suspect_config(self):
        fixture = self.make()
        improved = fixture.default_scores()
        improved[("arlene", 101, 0)] = [102.0, 90.0]
        improved[("arlene", 101, 1)] = [90.0, 102.0]
        fixture.set_scores(1, improved)
        regressed = fixture.default_scores()
        regressed[("arlene", 101, 0)] = [89.0, 90.0]
        regressed[("arlene", 101, 1)] = [90.0, 89.0]
        fixture.set_scores(2, regressed)
        actions = fixture.default_actions()
        for cell in fixture.cells:
            actions[(cell, 1)] = {
                "farmer": "PASS",
                "hands": ["PASS"],
                "market": [["SELL", "FERTILIZER", 1]],
            }
        fixture.set_trace(1, actions)
        worse_actions = copy.deepcopy(actions)
        for cell in fixture.cells:
            worse_actions[(cell, 1)]["market"] = [["SELL", "FERTILIZER", 3]]
        fixture.set_trace(2, worse_actions)
        fixture.set_config(1, {"redundant_hire": True, "market_pressure": True})
        fixture.set_config(
            2,
            {"redundant_hire": True, "market_pressure": True, "operating_stock": True},
        )
        report = target.run_attribution(fixture.manifest_path)
        self.assertEqual(report["verdict"], "REGRESSION_FOUND")
        first = report["first_regression"]
        self.assertEqual((first["before"], first["after"]), ("b1", "b2"))
        self.assertEqual(first["suspect_config_paths"], ["operating_stock"])
        self.assertEqual(first["earliest_divergence_step"], 1)
        self.assertEqual(first["divergence_categories"], {"market_only": 2})

    def test_explicit_ablation_comparisons_use_neutral_anchor(self):
        fixture = self.make()
        fixture.set_config(0, {"market_pressure": False, "operating_stock": False})
        fixture.set_config(1, {"market_pressure": True, "operating_stock": False})
        fixture.set_config(2, {"market_pressure": False, "operating_stock": True})
        bad = fixture.default_scores()
        bad[("arlene", 101, 0)] = [80.0, 90.0]
        bad[("arlene", 101, 1)] = [90.0, 80.0]
        fixture.set_scores(2, bad)
        actions = fixture.default_actions()
        for cell in fixture.cells:
            actions[(cell, 1)] = {
                "farmer": "PASS",
                "hands": ["PASS"],
                "market": [["SELL", "WHEAT", 9]],
            }
        fixture.set_trace(2, actions)
        fixture.manifest["comparisons"] = [
            {"id": "neutral-vs-market", "before": "b0", "after": "b1"},
            {"id": "neutral-vs-operating", "before": "b0", "after": "b2"},
        ]
        fixture.write_manifest()
        report = target.run_attribution(fixture.manifest_path)
        first = report["first_regression"]
        self.assertEqual(first["comparison_id"], "neutral-vs-operating")
        self.assertEqual((first["before"], first["after"]), ("b0", "b2"))
        self.assertEqual(first["suspect_config_paths"], ["operating_stock"])
        self.assertEqual(len(report["declared_comparisons"]), 2)

    def test_comparison_unknown_build_is_invalid(self):
        fixture = self.make(2)
        fixture.manifest["comparisons"] = [
            {"id": "bad", "before": "b0", "after": "missing"}
        ]
        fixture.write_manifest()
        with self.assertRaisesRegex(target.AttributionError, "unknown build reference"):
            target.run_attribution(fixture.manifest_path)

    def test_comparison_ids_must_be_unique(self):
        fixture = self.make(2)
        fixture.manifest["comparisons"] = [
            {"id": "same", "before": "b0", "after": "b1"},
            {"id": "same", "before": "b1", "after": "b0"},
        ]
        fixture.write_manifest()
        with self.assertRaisesRegex(target.AttributionError, "duplicate id"):
            target.run_attribution(fixture.manifest_path)

    def test_observation_drift_before_action_is_invalid(self):
        fixture = self.make(2)
        observations = {(fixture.cells[0], 0): "f" * 64}
        fixture.set_trace(1, fixture.default_actions(), observations)
        with self.assertRaisesRegex(target.AttributionError, "observation drift"):
            target.run_attribution(fixture.manifest_path)

    def test_score_change_without_action_divergence_is_invalid(self):
        fixture = self.make(2)
        scores = fixture.default_scores()
        scores[("arlene", 101, 0)] = [101.0, 90.0]
        fixture.set_scores(1, scores)
        with self.assertRaisesRegex(target.AttributionError, "without an action divergence"):
            target.run_attribution(fixture.manifest_path)

    def test_missing_game_cell_is_invalid(self):
        fixture = self.make(2)
        rows = fixture.game_rows(fixture.default_scores())[:-1]
        fixture.replace_bound(1, "games", ("".join(json.dumps(row) + "\n" for row in rows)).encode())
        with self.assertRaisesRegex(target.AttributionError, "grid mismatch"):
            target.run_attribution(fixture.manifest_path)

    def test_duplicate_game_cell_is_invalid(self):
        fixture = self.make(2)
        rows = fixture.game_rows(fixture.default_scores())
        rows.append(copy.deepcopy(rows[0]))
        fixture.replace_bound(1, "games", ("".join(json.dumps(row) + "\n" for row in rows)).encode())
        with self.assertRaisesRegex(target.AttributionError, "duplicate cell"):
            target.run_attribution(fixture.manifest_path)

    def test_missing_trace_row_is_invalid(self):
        fixture = self.make(2)
        rows = fixture.trace_rows(fixture.default_actions())[:-1]
        fixture.replace_bound(1, "trace", ("".join(json.dumps(row) + "\n" for row in rows)).encode())
        with self.assertRaisesRegex(target.AttributionError, "trace grid mismatch"):
            target.run_attribution(fixture.manifest_path)

    def test_duplicate_trace_row_is_invalid(self):
        fixture = self.make(2)
        rows = fixture.trace_rows(fixture.default_actions())
        rows.append(copy.deepcopy(rows[0]))
        fixture.replace_bound(1, "trace", ("".join(json.dumps(row) + "\n" for row in rows)).encode())
        with self.assertRaisesRegex(target.AttributionError, "duplicate trace row"):
            target.run_attribution(fixture.manifest_path)

    def test_bound_hash_mismatch_is_invalid(self):
        fixture = self.make(2)
        fixture.builds[1]["games"]["sha256"] = "0" * 64
        fixture.write_manifest()
        with self.assertRaisesRegex(target.AttributionError, "SHA-256 mismatch"):
            target.run_attribution(fixture.manifest_path)

    def test_duplicate_json_key_is_invalid(self):
        fixture = self.make(2)
        fixture.replace_bound(1, "config", b'{"x":1,"x":2}\n')
        with self.assertRaisesRegex(target.AttributionError, "duplicate JSON key"):
            target.run_attribution(fixture.manifest_path)

    def test_nonfinite_json_is_invalid(self):
        fixture = self.make(2)
        rows = fixture.game_rows(fixture.default_scores())
        rows[0]["scores"][0] = float("nan")
        fixture.replace_bound(1, "games", ("".join(json.dumps(row, allow_nan=True) + "\n" for row in rows)).encode())
        with self.assertRaisesRegex(target.AttributionError, "non-finite JSON constant"):
            target.run_attribution(fixture.manifest_path)

    def test_artifact_alias_is_invalid(self):
        fixture = self.make(2)
        fixture.builds[1]["artifact"] = dict(fixture.builds[0]["artifact"])
        fixture.write_manifest()
        with self.assertRaisesRegex(target.AttributionError, "byte-distinct"):
            target.run_attribution(fixture.manifest_path)

    def test_bad_source_commit_is_invalid(self):
        fixture = self.make(2)
        fixture.builds[1]["source_commit"] = "not-a-commit"
        fixture.write_manifest()
        with self.assertRaisesRegex(target.AttributionError, "40- or 64-character"):
            target.run_attribution(fixture.manifest_path)

    def test_boolean_seat_is_invalid(self):
        fixture = self.make(2)
        fixture.manifest["grid"]["seats"] = [0, True]
        fixture.write_manifest()
        with self.assertRaisesRegex(target.AttributionError, "expected an integer"):
            target.run_attribution(fixture.manifest_path)

    def test_nested_config_diff_is_deterministic(self):
        fixture = self.make(2)
        fixture.set_config(0, {"a": {"x": 1, "y": 2}})
        fixture.set_config(1, {"a": {"x": 3}, "b": True})
        report = target.run_attribution(fixture.manifest_path)
        paths = [row["path"] for row in report["adjacent_transitions"][0]["config_changes"]]
        self.assertEqual(paths, ["a.x", "a.y", "b"])

    def test_diagnostic_changes_are_captured(self):
        fixture = self.make(2)
        actions = fixture.default_actions()
        actions[(fixture.cells[0], 1)] = {
            "farmer": "PASS",
            "hands": ["PASS"],
            "market": [["SELL", "WHEAT", 1]],
        }
        before_diag = {(fixture.cells[0], 1): {"stage": "baseline", "limit": 1}}
        after_diag = {(fixture.cells[0], 1): {"stage": "pressure", "limit": 1}}
        fixture.set_trace(0, fixture.default_actions(), diagnostics=before_diag)
        fixture.set_trace(1, actions, diagnostics=after_diag)
        report = target.run_attribution(fixture.manifest_path)
        changes = report["adjacent_transitions"][0]["trace_attribution"]["cells"][0]["diagnostic_changes"]
        self.assertEqual(changes, [{"path": "stage", "before": "baseline", "after": "pressure"}])

    def test_cli_exit_codes_and_atomic_report(self):
        fixture = self.make(2)
        report_path = fixture.root / "report.json"
        self.assertEqual(
            target.main(["--manifest", str(fixture.manifest_path), "--report", str(report_path)]),
            0,
        )
        first = report_path.read_bytes()
        self.assertEqual(
            target.main(["--manifest", str(fixture.manifest_path), "--report", str(report_path)]),
            0,
        )
        self.assertEqual(first, report_path.read_bytes())
        fixture.builds[1]["games"]["sha256"] = "0" * 64
        fixture.write_manifest()
        self.assertEqual(
            target.main(["--manifest", str(fixture.manifest_path), "--report", str(report_path)]),
            2,
        )
        self.assertEqual(json.loads(report_path.read_text())["verdict"], "INVALID")

    def test_regression_cli_exits_three(self):
        fixture = self.make(2)
        scores = fixture.default_scores()
        scores[("arlene", 101, 0)] = [80.0, 90.0]
        scores[("arlene", 101, 1)] = [90.0, 80.0]
        fixture.set_scores(1, scores)
        actions = fixture.default_actions()
        for cell in fixture.cells:
            actions[(cell, 0)] = {"farmer": "PASS", "hands": ["PASS"], "market": [["SELL", "WHEAT", 9]]}
        fixture.set_trace(1, actions)
        report_path = fixture.root / "report.json"
        code = target.main(["--manifest", str(fixture.manifest_path), "--report", str(report_path)])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(report_path.read_text())["verdict"], "REGRESSION_FOUND")

    @unittest.skipUnless(hasattr(__import__("os"), "symlink"), "symlinks unavailable")
    def test_symlink_input_is_invalid(self):
        fixture = self.make(2)
        real = fixture.root / "real-artifact.bin"
        real.write_bytes(b"alias")
        link = fixture.root / "link-artifact.bin"
        link.symlink_to(real.name)
        fixture.builds[1]["artifact"] = {
            "path": link.name,
            "sha256": hashlib.sha256(b"alias").hexdigest(),
        }
        fixture.write_manifest()
        with self.assertRaisesRegex(target.AttributionError, "non-symlink"):
            target.run_attribution(fixture.manifest_path)


if __name__ == "__main__":
    unittest.main()

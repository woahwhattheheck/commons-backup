# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
LAB = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(HERE))

from compose_v5_carebank import (
    CONFIG_BLOB,
    HELPER_BLOB,
    HELPER_RELATIVE,
    MAIN_BLOB,
    RUNTIME_BLOB,
    git_blob_id,
    materialize,
    patch_config,
    patch_runtime,
)


def _features_class(source: str):
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "Features")
    lines = source.splitlines(keepends=True)
    start = min((decorator.lineno for decorator in node.decorator_list), default=node.lineno)
    text = "".join(lines[start - 1 : node.end_lineno])
    namespace = {"__name__": __name__, "dataclass": dataclass, "math": math}
    exec(text, namespace)
    return namespace["Features"]


def _copy_current_package(package: Path) -> None:
    package.mkdir()
    for relative in ("main.py", "titan_runtime.py", "TITAN-CONFIG.json"):
        shutil.copyfile(LAB / relative, package / relative)


class V5CarebankComposerTests(unittest.TestCase):
    def test_source_pins_match_current_v5_and_existing_w2_authority(self):
        expected = {
            LAB / "main.py": MAIN_BLOB,
            LAB / "titan_runtime.py": RUNTIME_BLOB,
            LAB / "TITAN-CONFIG.json": CONFIG_BLOB,
            LAB / HELPER_RELATIVE: HELPER_BLOB,
        }
        for path, blob in expected.items():
            with self.subTest(path=str(path)):
                self.assertEqual(git_blob_id(path.read_bytes()), blob)

    def test_runtime_hook_preserves_exec_era_and_parent_fallback_order(self):
        out = patch_runtime((LAB / "titan_runtime.py").read_text(encoding="utf-8"))
        self.assertEqual(out.count("exec_pace: bool = False"), 1)
        self.assertEqual(out.count("r04_dead_feed_care: bool = False"), 1)
        self.assertEqual(out.count("'exec_pace', 'r04_dead_feed_care'"), 1)
        producer = out.index("selected = self.production.act(obs)")
        parent = out.index("parent_checkpoint = (deepcopy(selected), self.controller.cur)", producer)
        fallback = out.index("fallback = parent_checkpoint[0]", parent)
        interim_checkpoint = out.index("selected_checkpoint = parent_checkpoint", fallback)
        repeated_feed = out.index("selected = care.apply_dead_feed_care(", interim_checkpoint)
        carebank = out.index("selected = care.apply_carebank_feed_swap(", repeated_feed)
        final_selected = out.index("self.selected = deepcopy(selected)", carebank)
        final_checkpoint = out.index("selected_checkpoint = (self.selected, self.controller.cur)", final_selected)
        transform = out.index("output = self.transform_selected(obs, cfg, selected)", final_checkpoint)
        self.assertLess(producer, parent)
        self.assertLess(parent, fallback)
        self.assertLess(fallback, interim_checkpoint)
        self.assertLess(interim_checkpoint, repeated_feed)
        self.assertLess(repeated_feed, carebank)
        self.assertLess(carebank, final_selected)
        self.assertLess(final_selected, final_checkpoint)
        self.assertLess(final_checkpoint, transform)
        ast.parse(out)

    def test_feature_is_exact_bool_and_only_nonterminal_frozen_can_enable(self):
        Features = _features_class(patch_runtime((LAB / "titan_runtime.py").read_text(encoding="utf-8")))
        self.assertIs(Features().exec_pace, False)
        self.assertIs(Features(exec_pace=True).exec_pace, True)
        self.assertIs(Features().r04_dead_feed_care, False)
        self.assertIs(Features(r04_dead_feed_care=True).r04_dead_feed_care, True)
        for bad in (0, 1, "false", [], None):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    Features(r04_dead_feed_care=bad)
        for kwargs in (
            {"consumer": "parent", "r04_dead_feed_care": True},
            {"consumer": "ordered", "r04_dead_feed_care": True},
            {"consumer": "frozen", "terminal_route": True, "r04_dead_feed_care": True},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    Features(**kwargs)

    def test_config_preserves_current_town_and_exec_fields(self):
        text = (LAB / "TITAN-CONFIG.json").read_text(encoding="utf-8")
        before = json.loads(text)
        self.assertIs(before["town_procurement"], True)
        self.assertIs(before["exec_pace"], False)
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                after = json.loads(patch_config(text, enabled=enabled))
                for key, value in before.items():
                    self.assertEqual(after[key], value)
                self.assertIs(after["r04_dead_feed_care"], enabled)
        with self.assertRaises(TypeError):
            patch_config(text, enabled=1)
        with self.assertRaises(ValueError):
            patch_config(patch_config(text, enabled=False), enabled=False)

    def test_materialize_closes_stale_town_procurement_predecessor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = root / "package"
            _copy_current_package(package)
            before = {name: (package / name).read_bytes()
                      for name in ("main.py", "titan_runtime.py", "TITAN-CONFIG.json")}

            control = root / "control"
            receipt = materialize(LAB, package, control, enabled=False)
            self.assertEqual(receipt["schema"], "titan-v5-carebank-current-native/v1")
            self.assertIs(receipt["enabled_in_scratch_only"], False)
            self.assertIs(receipt["production_default_changed"], False)
            self.assertEqual(receipt["consumer_contract"], "frozen_nonterminal_only")
            self.assertEqual(
                receipt["entrypoint_contract"],
                "current_main_strips_town_procurement_before_Features",
            )
            self.assertEqual(receipt["deadline_fallback"], "completed_parent_selected_action")
            self.assertEqual(
                receipt["selected_pipeline"],
                ["apply_dead_feed_care", "apply_carebank_feed_swap"],
            )
            self.assertEqual(receipt["source_blobs"]["main.py"], MAIN_BLOB)
            self.assertEqual(receipt["outputs"]["main.py"]["git_blob"], MAIN_BLOB)
            self.assertEqual(git_blob_id((control / "r04_dead_feed_care.py").read_bytes()), HELPER_BLOB)

            config = json.loads((control / "TITAN-CONFIG.json").read_text())
            self.assertIs(config["town_procurement"], True)
            self.assertIs(config["exec_pace"], False)
            self.assertIs(config["r04_dead_feed_care"], False)
            Features = _features_class((control / "titan_runtime.py").read_text(encoding="utf-8"))
            # This is the exact old-package failure shape: town_procurement is
            # entrypoint-owned and therefore must not be passed raw to Features.
            with self.assertRaises(TypeError):
                Features(**config)
            runtime_config = dict(config)
            self.assertIs(runtime_config.pop("town_procurement"), True)
            features = Features(**runtime_config)
            self.assertIs(features.exec_pace, False)
            self.assertIs(features.r04_dead_feed_care, False)

            entrypoint = (control / "main.py").read_text(encoding="utf-8")
            town = entrypoint.index("town_enabled = _town_procurement_enabled(feature_data)")
            strip = entrypoint.index("feature_data.pop('town_procurement', None)", town)
            bind = entrypoint.index("features = Features(**feature_data)", strip)
            self.assertLess(town, strip)
            self.assertLess(strip, bind)

            treatment = root / "treatment"
            enabled = materialize(LAB, package, treatment, enabled=True)
            self.assertIs(enabled["enabled_in_scratch_only"], True)
            treatment_config = json.loads((treatment / "TITAN-CONFIG.json").read_text())
            self.assertIs(treatment_config["town_procurement"], True)
            self.assertIs(treatment_config["exec_pace"], False)
            self.assertIs(treatment_config["r04_dead_feed_care"], True)
            for name, payload in before.items():
                self.assertEqual((package / name).read_bytes(), payload)

    def test_materialize_uses_each_authenticated_input_snapshot_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = root / "package"
            _copy_current_package(package)
            output = root / "output"
            watched = {
                (package / "main.py").resolve(),
                (package / "titan_runtime.py").resolve(),
                (package / "TITAN-CONFIG.json").resolve(),
                (LAB / HELPER_RELATIVE).resolve(),
            }
            reads = {path: 0 for path in watched}
            real_read_bytes = Path.read_bytes

            def poisoned_after_first(path: Path) -> bytes:
                resolved = path.resolve()
                if resolved in reads:
                    reads[resolved] += 1
                    if reads[resolved] > 1:
                        return b"# poisoned second authenticated read\n"
                return real_read_bytes(path)

            with mock.patch.object(Path, "read_bytes", new=poisoned_after_first):
                receipt = materialize(LAB, package, output, enabled=True)

            self.assertEqual(set(receipt["source_sha256s"]), {
                "main.py", "titan_runtime.py", "TITAN-CONFIG.json", str(HELPER_RELATIVE)
            })
            self.assertTrue(all(count == 1 for count in reads.values()), reads)
            self.assertEqual(git_blob_id((output / "main.py").read_bytes()), MAIN_BLOB)
            self.assertEqual(git_blob_id((output / "r04_dead_feed_care.py").read_bytes()), HELPER_BLOB)
            self.assertIs(json.loads((output / "TITAN-CONFIG.json").read_text())["r04_dead_feed_care"], True)

    def test_source_drift_fails_before_output_is_published(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = root / "package"
            _copy_current_package(package)
            (package / "titan_runtime.py").write_text(
                (package / "titan_runtime.py").read_text() + "\n# drift\n",
                encoding="utf-8",
            )
            output = root / "output"
            with self.assertRaises(ValueError):
                materialize(LAB, package, output, enabled=True)
            self.assertFalse(output.exists())

    def test_entrypoint_drift_fails_before_output_is_published(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = root / "package"
            _copy_current_package(package)
            (package / "main.py").write_text(
                (package / "main.py").read_text() + "\n# drift\n",
                encoding="utf-8",
            )
            output = root / "output"
            with self.assertRaises(ValueError):
                materialize(LAB, package, output, enabled=False)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

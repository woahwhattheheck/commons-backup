from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("make_submission", HERE / "make_submission.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load make_submission.py")
submission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(submission)


def held_config(**patch):
    config = {
        "r03_full_router": False,
        "r04_sale_window": False,
        "r04_sale_horizon": 8,
        "r04_open_roundtrip": 0,
        "r04_row_order": True,
        "r04_evening_flush": True,
        "r04_sale_fertilizer": True,
        "r04_cattle_early": False,
        "r04_kill_late_water": False,
        "r04_strawberry_endgame": False,
        "r04_strawberry_max_plants": 8,
        "r04_strawberry_topup": True,
        "r04_no_late_sale_advance": True,
        "r04_no_late_sale_advance_step": 648,
        "r04_b5_carrot_fertilizer": True,
        "r04_b5_jit_fertilize": True,
        "r04_row_shed": True,
        "r04_fert_hand": True,
        "r01_shop_router": False,
        "r02_route_bank": False,
        "sentinel": "unchanged",
    }
    config.update(patch)
    return config


def base_files(**patch):
    config = held_config(**patch)
    return {
        "TITAN-CONFIG.json": (json.dumps(config, indent=2) + "\n").encode("utf-8"),
        "main.py": b"# unchanged\n",
        "opaque.bin": b"\x00\x01unchanged\xff",
    }


class SubmissionConfigTests(unittest.TestCase):
    def test_last_transform_changes_only_sale_window_on_held_tuple(self):
        source = base_files()
        original = copy.deepcopy(source)
        before = json.loads(source["TITAN-CONFIG.json"])

        out, config = submission.apply_submission_config(source)

        self.assertEqual(source, original)
        self.assertEqual(set(out), set(source))
        self.assertEqual(out["main.py"], source["main.py"])
        self.assertEqual(out["opaque.bin"], source["opaque.bin"])
        changed = {key for key in before if before[key] != config[key]}
        self.assertEqual(changed, {"r04_sale_window"})
        self.assertIs(config["r04_sale_window"], True)
        self.assertEqual(config["r04_sale_horizon"], 8)
        self.assertIs(config["r04_sale_fertilizer"], True)
        self.assertIs(config["r04_cattle_early"], False)
        self.assertIs(config["r04_row_shed"], True)
        self.assertIs(config["r04_fert_hand"], True)
        self.assertIs(config["r04_row_order"], True)
        self.assertEqual(config["r04_no_late_sale_advance_step"], 648)
        self.assertEqual(config["sentinel"], "unchanged")
        self.assertNotEqual(out["TITAN-CONFIG.json"], source["TITAN-CONFIG.json"])

    def test_exact_h8_override_is_the_only_allowed_override(self):
        _, config = submission.apply_submission_config(base_files(), 8)
        self.assertEqual(config["r04_sale_horizon"], 8)
        for bad in (0, -1, 5, 10, True, 8.0, "8", None):
            if bad is None:
                continue  # absence means use the held H8 decision and is valid
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(AssertionError, "must equal held H8 decision"):
                    submission.apply_submission_config(base_files(), bad)

    def test_base_horizon_must_already_be_literal_h8(self):
        for bad in (None, 0, -1, 5, 10, True, 8.0, "8"):
            with self.subTest(bad=bad):
                source = base_files(r04_sale_horizon=bad)
                original = copy.deepcopy(source)
                with self.assertRaisesRegex(AssertionError, "exact integer 8"):
                    submission.apply_submission_config(source)
                self.assertEqual(source, original)

    def test_all_held_true_lanes_fail_closed_on_false_or_type_poison(self):
        keys = (
            "r04_row_order",
            "r04_evening_flush",
            "r04_sale_fertilizer",
            "r04_strawberry_topup",
            "r04_no_late_sale_advance",
            "r04_b5_carrot_fertilizer",
            "r04_b5_jit_fertilize",
            "r04_row_shed",
            "r04_fert_hand",
        )
        for key in keys:
            for bad in (False, None, 0, 1, "true", [], {}):
                with self.subTest(key=key, bad=bad):
                    with self.assertRaises(AssertionError):
                        submission.apply_submission_config(base_files(**{key: bad}))

    def test_all_held_false_lanes_fail_closed_on_true_or_type_poison(self):
        keys = (
            "r04_sale_window",
            "r04_cattle_early",
            "r04_kill_late_water",
            "r04_strawberry_endgame",
        )
        for key in keys:
            for bad in (True, None, 0, 1, "false", [], {}):
                with self.subTest(key=key, bad=bad):
                    with self.assertRaises(AssertionError):
                        submission.apply_submission_config(base_files(**{key: bad}))

    def test_held_integer_lanes_require_exact_value_and_exact_type(self):
        cases = {
            "r04_open_roundtrip": (0, (1, -1, True, 0.0, "0", None)),
            "r04_strawberry_max_plants": (8, (7, 9, True, 8.0, "8", None)),
            "r04_no_late_sale_advance_step": (648, (647, 649, True, 648.0, "648", None)),
        }
        for key, (_expected, bad_values) in cases.items():
            for bad in bad_values:
                with self.subTest(key=key, bad=bad):
                    with self.assertRaises(AssertionError):
                        submission.apply_submission_config(base_files(**{key: bad}))

    def test_non_owned_keys_and_types_must_be_preserved(self):
        before = held_config()
        after = copy.deepcopy(before)
        after["sentinel"] = "changed"
        with self.assertRaisesRegex(AssertionError, "non-score-facing config drift"):
            submission.require_only_transform_keys_changed(before, after)

        after = copy.deepcopy(before)
        after["sentinel"] = 1
        with self.assertRaisesRegex(AssertionError, "non-score-facing config drift"):
            submission.require_only_transform_keys_changed(before, after)

    def test_transform_may_not_add_or_remove_config_keys(self):
        before = held_config()
        added = copy.deepcopy(before)
        added["new-key"] = True
        with self.assertRaisesRegex(AssertionError, "may not add or remove config keys"):
            submission.require_only_transform_keys_changed(before, added)

        removed = copy.deepcopy(before)
        removed.pop("sentinel")
        with self.assertRaisesRegex(AssertionError, "may not add or remove config keys"):
            submission.require_only_transform_keys_changed(before, removed)

    def test_final_output_rejects_owned_tuple_drift(self):
        before = held_config()
        valid = copy.deepcopy(before)
        valid["r04_sale_window"] = True
        submission.require_final_output(before, valid)

        poisons = {
            "r04_sale_window": False,
            "r04_sale_horizon": 10,
            "r04_sale_fertilizer": False,
            "r04_cattle_early": True,
        }
        for key, bad in poisons.items():
            with self.subTest(key=key, bad=bad):
                after = copy.deepcopy(valid)
                after[key] = bad
                with self.assertRaises(AssertionError):
                    submission.require_final_output(before, after)

    def test_invalid_cli_horizon_fails_before_sys_path_or_package_access(self):
        fake = types.ModuleType("build_v3")

        def forbidden(*_args, **_kwargs):
            self.fail("invalid CLI horizon touched package access")

        fake.package_files = forbidden
        fake.build_bytes = forbidden
        original_path = list(sys.path)
        for raw in ("0", "-1", "5", "10"):
            with self.subTest(raw=raw):
                with mock.patch.dict(sys.modules, {"build_v3": fake}):
                    with self.assertRaisesRegex(AssertionError, "must equal held H8 decision"):
                        submission.main(["poison-v3-path", "canonical.tar.gz", "out.tar.gz", raw])
                self.assertEqual(sys.path, original_path)

    def test_non_integer_cli_horizon_fails_before_package_access(self):
        fake = types.ModuleType("build_v3")

        def forbidden(*_args, **_kwargs):
            self.fail("non-integer CLI horizon touched package access")

        fake.package_files = forbidden
        fake.build_bytes = forbidden
        original_path = list(sys.path)
        with mock.patch.dict(sys.modules, {"build_v3": fake}):
            with self.assertRaises(ValueError):
                submission.main(["poison-v3-path", "canonical.tar.gz", "out.tar.gz", "not-an-int"])
        self.assertEqual(sys.path, original_path)

    def test_invalid_cli_horizon_never_imports_poison_builder_or_creates_output(self):
        original_path = list(sys.path)
        original_builder = sys.modules.pop("build_v3", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "build_v3.py").write_text(
                    "raise RuntimeError('BUILD_PATH_TOUCHED')\n", encoding="utf-8"
                )
                for raw, expected in (
                    ("0", AssertionError),
                    ("-1", AssertionError),
                    ("5", AssertionError),
                    ("10", AssertionError),
                    ("not-an-int", ValueError),
                ):
                    with self.subTest(raw=raw):
                        output = root / ("out-%s.tar.gz" % raw.replace("-", "neg"))
                        with self.assertRaises(expected) as caught:
                            submission.main([str(root), "canonical.tar.gz", str(output), raw])
                        self.assertNotIn("BUILD_PATH_TOUCHED", str(caught.exception))
                        self.assertFalse(output.exists())
                        self.assertEqual(sys.path, original_path)
                        self.assertNotIn("build_v3", sys.modules)
        finally:
            if original_builder is not None:
                sys.modules["build_v3"] = original_builder
            else:
                sys.modules.pop("build_v3", None)
            sys.path[:] = original_path

    def test_titan_config_must_decode_to_object(self):
        files = {
            "TITAN-CONFIG.json": b"[]\n",
            "main.py": b"# unchanged\n",
        }
        with self.assertRaisesRegex(AssertionError, "must decode to an object"):
            submission.apply_submission_config(files)

    def test_missing_config_member_fails(self):
        with self.assertRaises(KeyError):
            submission.apply_submission_config({"main.py": b"x"})


if __name__ == "__main__":
    unittest.main()

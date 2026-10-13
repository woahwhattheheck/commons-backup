from __future__ import annotations

import copy
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import mixture_gate as gate
from test_support import (
    H64, H64B, H64C, H64D, H64E, H64F, H40, H40B,
    build_document, quantity_fraction,
)

class MixtureGateContractsC(unittest.TestCase):
    def test_cli_returns_zero_for_economic_hold(self):
        doc = build_document(
            {"a": [(20, 0)] * 5, "b": [(-30, 0)] * 5},
            counts={"a": 4, "b": 1},
            bounds={"a": ("1/2", "4/5"), "b": ("1/5", "1/2")},
            radius="3/10",
            own_floor=-100,
            margin_floor=-100,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            output = root / "output.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = gate.main(["--input", str(source), "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["verdict"], "ROBUST_HOLD")

    def test_cli_returns_two_and_receipt_for_malformed_input(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["schema"] = "wrong"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            output = root / "output.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = gate.main(["--input", str(source), "--output", str(output)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["verdict"], "MALFORMED_EVIDENCE")

    def test_greedy_optimizer_matches_exhaustive_probability_grid(self):
        families = (
            gate.MixFamily("a", 5, gate.Fraction(1, 2), gate.Fraction(1, 5), gate.Fraction(4, 5)),
            gate.MixFamily("b", 3, gate.Fraction(3, 10), gate.Fraction(1, 10), gate.Fraction(3, 5)),
            gate.MixFamily("c", 2, gate.Fraction(1, 5), gate.Fraction(0), gate.Fraction(1, 2)),
        )
        radius = gate.Fraction(1, 5)
        for raw_effects in ((10, 0, -10), (2, -3, 7), (0, 0, 0), (-1, 4, 2)):
            effects = dict(zip(("a", "b", "c"), map(gate.Fraction, raw_effects)))
            result = gate._worst_case_mixture(effects, families, radius)
            observed = gate.Fraction(result["worst_case_value"]["fraction"])
            exhaustive = []
            for a_units in range(11):
                for b_units in range(11 - a_units):
                    c_units = 10 - a_units - b_units
                    weights = {
                        "a": gate.Fraction(a_units, 10),
                        "b": gate.Fraction(b_units, 10),
                        "c": gate.Fraction(c_units, 10),
                    }
                    if any(not (family.lower <= weights[family.name] <= family.upper) for family in families):
                        continue
                    tv = sum(abs(weights[family.name] - family.nominal) for family in families) / 2
                    if tv > radius:
                        continue
                    exhaustive.append(sum(weights[name] * effects[name] for name in weights))
            self.assertTrue(exhaustive)
            self.assertEqual(observed, min(exhaustive), raw_effects)

    def test_unknown_field_is_malformed_instead_of_silently_unhashed(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["gate"]["unreviewed_override"] = True
        with self.assertRaises(gate.ValidationError) as caught:
            gate.evaluate(doc)
        self.assertEqual(caught.exception.code, "UNKNOWN_FIELD")

    def test_missing_field_is_malformed(self):
        doc = build_document({"a": [(10, 0)] * 5})
        del doc["panel"]["loader_sha256"]
        with self.assertRaises(gate.ValidationError) as caught:
            gate.evaluate(doc)
        self.assertEqual(caught.exception.code, "MISSING_FIELD")

    def test_cli_rejects_duplicate_json_keys_before_schema_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            output = root / "output.json"
            source.write_text('{"schema":"first","schema":"second"}', encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = gate.main(["--input", str(source), "--output", str(output)])
            self.assertEqual(code, 2)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["error"]["code"], "DUPLICATE_JSON_KEY")

    def test_action_change_without_economic_gain_holds_even_when_nonstrict(self):
        doc = build_document({"a": [(0, 0)] * 5}, strict=False)
        for cell in doc["panel"]["cells"]:
            cell["action_changed"] = True
            cell["trace_changed"] = True
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "ROBUST_HOLD")
        self.assertIn("no_terminal_economic_change", {reason["reason"] for reason in result["reasons"]})

    def test_cli_input_output_alias_never_overwrites_source(self):
        doc = build_document({"a": [(10, 0)] * 5})
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "evidence.json"
            original = json.dumps(doc, sort_keys=True)
            source.write_text(original, encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = gate.main(["--input", str(source), "--output", str(source)])
            self.assertEqual(code, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_cli_hardlink_output_alias_never_overwrites_source(self):
        doc = build_document({"a": [(10, 0)] * 5})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "evidence.json"
            alias = root / "alias.json"
            original = json.dumps(doc, sort_keys=True)
            source.write_text(original, encoding="utf-8")
            try:
                alias.hardlink_to(source)
            except (OSError, NotImplementedError):
                self.skipTest("hard links unavailable")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = gate.main(["--input", str(source), "--output", str(alias)])
            self.assertEqual(code, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_cli_symlink_output_is_rejected_without_touching_target(self):
        doc = build_document({"a": [(10, 0)] * 5})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "evidence.json"
            target = root / "target.json"
            link = root / "output.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            target.write_text("sentinel", encoding="utf-8")
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = gate.main(["--input", str(source), "--output", str(link)])
            self.assertEqual(code, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "sentinel")

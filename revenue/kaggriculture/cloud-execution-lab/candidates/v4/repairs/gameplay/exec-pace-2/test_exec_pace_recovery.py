# SPDX-License-Identifier: Apache-2.0
"""Independent donor/component proof, NOT the missing original 15-test suite.

No router/materializer is executed. Narrow AST extraction authenticates and
characterizes the *other* inline implementation in the original raw patch.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import io
import math
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest

from repair_duplicate_step import SOURCE_SHA256, repair

HERE = Path(__file__).resolve().parent
TAR_SHA = "f4def104e08b4f5b5b412c7a365bc2502a5e53f497ca2741077931cd1bb64675"
EXPECTED = {
    "r04_exec_adaptive.py": SOURCE_SHA256,
    "r04_exec_adaptive.patch": "3e1922085e3ab80bad3c5495712ff912f500cdcbfc2eda91ae3b597ac28b4715",
    "WIRING.txt": "478ae8dc1eaa8770451efdcd48d51f503d7d44a5f299a150496dc79cedd5676e",
    "VERDICT-execpace2.txt": "7e25cfeb193bec83f21958d6a681d59cf773673e694da4d052f54ad1cb80d670",
}


def members() -> dict[str, bytes]:
    raw = (HERE / "raw/exec-pace-2.tar.gz").read_bytes()
    if hashlib.sha256(raw).hexdigest() != TAR_SHA:
        raise ValueError("archive SHA mismatch")
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            if member.isdir() and member.name == ".":
                continue
            name = member.name.removeprefix("./")
            if not member.isfile() or name not in EXPECTED or name in result:
                raise ValueError("unexpected/duplicate archive member")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("missing archive payload")
            data = stream.read()
            if hashlib.sha256(data).hexdigest() != EXPECTED[name]:
                raise ValueError("member hash mismatch")
            result[name] = data
    if set(result) != set(EXPECTED):
        raise ValueError("incomplete archive")
    return result


def load(source: bytes) -> types.ModuleType:
    mod = types.ModuleType("isolated_execpace")
    exec(compile(source, "<authenticated-execpace-component>", "exec"), mod.__dict__)
    return mod


def observe(mod, step, price):
    mod.note_prices({"step": step, "market": {"prices": {g: price for g in mod.GOODS}}})


def state(mod):
    return copy.deepcopy((mod._last_step, mod._phist))


def snapshot(mod):
    return state(mod), [(mod.rising(g), mod.slope(g)) for g in mod.GOODS]


class Recovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = members()
        cls.raw = cls.files["r04_exec_adaptive.py"]
        cls.fixed = repair(cls.raw)

    def pair(self):
        return load(self.raw), load(self.fixed)

    def test_exact_custody(self):
        self.assertEqual((HERE / "raw/r04_exec_adaptive.py").read_bytes(), self.raw)
        self.assertEqual(len(self.files), 4)
        self.assertFalse(any("test" in p for p in self.files))

    def test_window_and_unknown_good_contract(self):
        for mod in self.pair():
            for step in range(24):
                observe(mod, step, 10 + step)
                self.assertIsNone(mod.slope("MILK"))
                self.assertFalse(mod.rising("MILK"))
            observe(mod, 24, 34)
            self.assertTrue(mod.rising("MILK"))
            for step in range(25, 100):
                observe(mod, step, 10 + step)
            self.assertEqual(len(mod._phist["MILK"]), 25)
            self.assertFalse(mod.rising("UNKNOWN"))
            self.assertIsNone(mod.slope("UNKNOWN"))

    def test_threshold_and_each_good(self):
        for mod in self.pair():
            for slope, expected in ((-1.0, False), (0.0, False), (0.02, False), (0.04, True), (1.0, True)):
                mod.reset()
                for step in range(25):
                    observe(mod, step, 100 + slope * step)
                for good in mod.GOODS:
                    self.assertAlmostEqual(mod.slope(good), slope)
                    self.assertIs(mod.rising(good), expected)

    def test_source_pin(self):
        for wrong in (self.raw + b"\n", self.raw[:-1], self.fixed, b""):
            with self.subTest(size=len(wrong)), self.assertRaises(ValueError):
                repair(wrong)
        with self.assertRaises(TypeError):
            repair(self.raw.decode())

    def test_only_executable_delta_is_guard(self):
        old = ast.parse(self.raw)
        new = ast.parse(self.fixed)
        # Strip changed narrative strings; compare all executable AST except
        # the exact donor guard, replaced below with the intended structure.
        def strip_docs(tree):
            for node in ast.walk(tree):
                body = getattr(node, "body", None)
                if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
                    if isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                        body.pop(0)
        strip_docs(old)
        strip_docs(new)
        method = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == "note_prices")
        suite = method.body[0].body
        self.assertIsInstance(suite[1], ast.If)
        suite[1:2] = ast.parse("if step == _last_step[0]:\n return\nif step < _last_step[0]:\n _phist.clear()\n").body
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_predecessor_duplicate_falsifier(self):
        old, new = self.pair()
        for step in range(25):
            observe(old, step, 10 + step)
            observe(new, step, 10 + step)
        self.assertTrue(old.rising("MILK"))
        prior = snapshot(new)
        observe(old, 24, 34)
        observe(new, 24, 34)
        self.assertEqual(len(old._phist["MILK"]), 1)
        self.assertFalse(old.rising("MILK"))
        self.assertEqual(snapshot(new), prior)
        self.assertTrue(new.rising("MILK"))

    def test_duplicate_every_step_all_goods(self):
        old, new = self.pair()
        for step in range(120):
            observe(old, step, 20 + (step % 31))
            observe(new, step, 20 + (step % 31))
            expected = snapshot(new)
            for duplicate in range(4):
                observe(new, step, 999 + duplicate)
                self.assertEqual(snapshot(new), expected)
            self.assertEqual(snapshot(old), snapshot(new))

    def test_increasing_trace_parity(self):
        # 24 traces x 160 callbacks; includes spaced samples, whose known
        # per-sample slope limitation is intentionally not changed here.
        for stride in (1, 2, 10):
            for trend in (-0.5, 0.0, 0.02, 0.1):
                for offset in (0, 37):
                    old, new = self.pair()
                    for index in range(160):
                        step = offset + index * stride
                        price = 100 + index * trend + (index % 3) * 0.001
                        observe(old, step, price)
                        observe(new, step, price)
                        with self.subTest(stride=stride, trend=trend, offset=offset, index=index):
                            self.assertEqual(snapshot(old), snapshot(new))

    def test_backward_step_reset_parity(self):
        for restart in (0, 1, 7, 23):
            old, new = self.pair()
            for step in range(25):
                observe(old, step, 10 + step)
                observe(new, step, 10 + step)
            observe(old, restart, 12)
            observe(new, restart, 12)
            self.assertEqual(snapshot(old), snapshot(new))
            self.assertEqual(len(new._phist["MILK"]), 1)

    def test_explicit_reset(self):
        old, new = self.pair()
        for mod in (old, new):
            for step in range(25):
                observe(mod, step, 10 + step)
            mod.reset()
            self.assertEqual(state(mod), ([-1], {}))
            self.assertFalse(mod.rising("MILK"))
            self.assertIsNone(mod.slope("MILK"))

    def test_invalid_observation_step_noop(self):
        for obj in (None, {}, {"step": None}, {"step": "bad"}, [], {"step": float("inf")}):
            old, new = self.pair()
            for mod in (old, new):
                observe(mod, 5, 20)
                before = state(mod)
                mod.note_prices(obj)
                self.assertEqual(state(mod), before)

    def test_gap_limitation_retained(self):
        for mod in self.pair():
            for i in range(25):
                observe(mod, i * 10, 10 + i * 0.1)
            self.assertAlmostEqual(mod.slope("MILK"), 0.1)
            self.assertGreater(mod.slope("MILK"), (12.4 - 10) / 240)
            self.assertTrue(mod.rising("MILK"))

    def test_nonfinite_limitation_retained(self):
        for mod in self.pair():
            for i in range(24):
                observe(mod, i, 10)
            observe(mod, 24, float("inf"))
            self.assertTrue(math.isinf(mod.slope("MILK")))
            self.assertTrue(mod.rising("MILK"))

    def test_missing_price_zero_imputation_retained(self):
        for mod in self.pair():
            mod.note_prices({"step": 0, "market": {"prices": {}}})
            self.assertEqual(mod._phist["MILK"], [0.0])

    def test_other_inline_variant_is_not_standalone(self):
        patch = self.files["r04_exec_adaptive.patch"].decode()
        first = patch.split("+# --- EXEC-PACE-2:", 1)[1].split("@@ -1431", 1)[0]
        added = "\n".join(line[1:] for line in first.splitlines() if line.startswith("+"))
        inline = load(added.encode())  # only the first authenticated helper hunk
        inline.EXEC_ADAPTIVE = True
        old = load(self.raw)
        for step in range(25):
            obs = {"step": step, "market": {"prices": {"MILK": 10 + step}}}
            inline._exec_adaptive_note_prices(obs)
            old.note_prices(obs)
        inline._exec_adaptive_note_prices(obs)
        old.note_prices(obs)
        self.assertEqual(len(inline._exec_adaptive_phist["MILK"]), 25)
        self.assertEqual(len(old._phist["MILK"]), 1)
        self.assertIn("if _step0 == 0:", patch)
        self.assertIn("import r04_exec_adaptive", self.files["WIRING.txt"].decode())
        self.assertNotIn("+import r04_exec_adaptive", patch)

    def test_cli_new_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "source.py", Path(tmp) / "candidate.py"
            source.write_bytes(self.raw)
            cmd = [sys.executable, *(["-O"] if sys.flags.optimize else []), str(HERE / "repair_duplicate_step.py"), str(source), str(output)]
            done = subprocess.run(cmd, text=True, capture_output=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(output.read_bytes(), self.fixed)
            again = subprocess.run(cmd, text=True, capture_output=True)
            self.assertEqual(again.returncode, 2)
            self.assertEqual(output.read_bytes(), self.fixed)
            same = subprocess.run(cmd[:-1] + [str(source)], text=True, capture_output=True)
            self.assertEqual(same.returncode, 2)
            self.assertEqual(source.read_bytes(), self.raw)

    def test_cli_bad_source_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "bad.py", Path(tmp) / "candidate.py"
            source.write_bytes(self.raw + b"\n")
            done = subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []), str(HERE / "repair_duplicate_step.py"), str(source), str(output)], text=True, capture_output=True)
            self.assertEqual(done.returncode, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

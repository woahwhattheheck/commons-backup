#!/usr/bin/env python3
"""Behavioral regression tests for the UIOWA-071 sibling-import boundary.

Run from the component: python -m unittest -v test_package_boundary_basalt
Run from the repository: python -m unittest -v \
    revenue.uiowa_rfq_18649_ai_use_inventory.test_package_boundary_basalt

Every import probe runs in a fresh child interpreter. Generic-name modules
are deliberately seeded only in those disposable children; production code
must neither replace them nor alias its siblings onto them. Optimization is
propagated to children and checked explicitly, so -O cannot erase checks.
All data is the component's existing, explicitly fictional fixture data.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE = "revenue.uiowa_rfq_18649_ai_use_inventory"
GENERIC_NAMES = ("schema", "inventory", "interview_guide")
PYTHON = [sys.executable] + ["-O"] * sys.flags.optimize
ENV = dict(os.environ, PYTHONPATH="", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
CLEAN = HERE / "fixtures" / "synthetic_ai_use.json"
HOSTILE = HERE / "fixtures" / "synthetic_ai_use_hostile.json"
OUTPUT_NAMES = {
    "ai_use_inventory.csv", "ai_use_gaps.csv",
    "ai_use_inventory.json", "ai_use_inventory.md",
}


class PackageBoundaryRegression(unittest.TestCase):
    def child(self, body, *, root=ROOT):
        """Execute real modules without inherited sys.modules or site hooks."""
        prelude = "\n".join([
            "import contextlib, importlib, io, json, sys, types, unittest",
            "from pathlib import Path",
            "t = unittest.TestCase()",
            "sys.path.insert(0, " + repr(str(root)) + ")",
            "package = " + repr(PACKAGE),
            "generic_names = " + repr(GENERIC_NAMES),
            "fixture = " + repr(str(CLEAN)),
            "t.assertEqual(sys.flags.optimize, " + repr(sys.flags.optimize) + ")",
        ])
        source = prelude + "\n" + textwrap.dedent(body)
        result = subprocess.run(
            [*PYTHON, "-S", "-c", source], cwd=root, env=ENV,
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def cli(self, module, *arguments, package_mode=True, cwd=None):
        target = ["-m", PACKAGE + "." + module] if package_mode else [str(HERE / (module + ".py"))]
        return subprocess.run(
            [*PYTHON, "-S", *target, *(str(a) for a in arguments)],
            cwd=ROOT if cwd is None else cwd, env=ENV,
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )

    def assert_output_parity(self, fixture):
        with tempfile.TemporaryDirectory(prefix="uiowa071-parity-") as tmp:
            outputs = [Path(tmp) / "script", Path(tmp) / "package"]
            runs = [self.cli("inventory", "--input", fixture, "--outdir", out,
                             package_mode=mode) for out, mode in zip(outputs, (False, True))]
            for run in runs:
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(runs[0].stderr, runs[1].stderr)
            for out in outputs:
                self.assertEqual({p.name for p in out.iterdir()}, OUTPUT_NAMES)
            for name in sorted(OUTPUT_NAMES):
                self.assertEqual((outputs[0] / name).read_bytes(),
                                 (outputs[1] / name).read_bytes(), name)
            return json.loads((outputs[1] / "ai_use_inventory.json").read_text(encoding="utf-8"))

    def test_inventory_imports_as_a_package_without_generic_dependencies(self):
        self.child('''
            module = importlib.import_module(package + ".inventory")
            t.assertEqual(module.UNKNOWN, "UNKNOWN")
            t.assertEqual(module.build([]).counts()["ACTIVE_USE"], 0)
        ''')

    def test_guide_imports_as_a_package_without_generic_dependencies(self):
        self.child('''
            module = importlib.import_module(package + ".interview_guide")
            t.assertGreater(len(module.all_questions()), 0)
            t.assertIn("UNKNOWN", module.render_guide())
        ''')

    def test_package_boundary_basalt_do_not_create_global_sibling_aliases(self):
        self.child('''
            for name in generic_names:
                t.assertNotIn(name, sys.modules)
            importlib.import_module(package + ".inventory")
            importlib.import_module(package + ".interview_guide")
            importlib.import_module(package + ".test_inventory")
            for name in generic_names:
                t.assertNotIn(name, sys.modules)
        ''')

    def test_cached_foreign_schema_cannot_change_classification(self):
        self.child('''
            foreign = types.ModuleType("schema")
            foreign.UNKNOWN = "FOREIGN_UNKNOWN"
            sys.modules["schema"] = foreign
            module = importlib.import_module(package + ".inventory")
            inv = module.build([{"entry_id": "SYNTHETIC-UNKNOWN", "group": "ESS",
                                 "function": "testing", "task": "fictional test"}])
            t.assertEqual(inv.entries[0]["classification"], "UNKNOWN")
            t.assertIs(sys.modules["schema"], foreign)
            t.assertEqual(foreign.UNKNOWN, "FOREIGN_UNKNOWN")
            t.assertIsNot(module.schema, foreign)
        ''')

    def test_cached_foreign_modules_survive_all_package_imports(self):
        self.child('''
            foreign = {name: types.ModuleType(name) for name in generic_names}
            foreign["schema"].UNKNOWN = "FOREIGN_UNKNOWN"
            sys.modules.update(foreign)
            inventory = importlib.import_module(package + ".inventory")
            guide = importlib.import_module(package + ".interview_guide")
            tests = importlib.import_module(package + ".test_inventory")
            t.assertIs(tests.inventory, inventory)
            t.assertIs(tests.interview_guide, guide)
            t.assertIs(tests.schema, inventory.schema)
            for name, module in foreign.items():
                t.assertIs(sys.modules[name], module)
        ''')

    def test_guide_probes_use_package_inventory_despite_cached_foreign_module(self):
        self.child('''
            foreign = types.ModuleType("inventory")
            sys.modules["inventory"] = foreign
            guide = importlib.import_module(package + ".interview_guide")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = guide.main(["--probes", fixture])
            t.assertEqual(code, 0)
            rows = json.loads(output.getvalue())
            row = next(r for r in rows if r["entry_id"] == "AIU-SYN-003")
            t.assertEqual(row["classification"], "UNSUPPORTED_CLAIM")
            t.assertIn("P-EX-01", [p["id"] for p in row["probes"]])
            t.assertIs(sys.modules["inventory"], foreign)
            t.assertEqual(vars(foreign).get("load"), None)
        ''')

    def test_package_modules_share_the_exact_same_schema_object(self):
        self.child('''
            inventory = importlib.import_module(package + ".inventory")
            guide = importlib.import_module(package + ".interview_guide")
            schema = importlib.import_module(package + ".schema")
            t.assertIs(inventory.schema, schema)
            t.assertIs(guide.schema, schema)
        ''')

    def test_late_foreign_modules_do_not_replace_loaded_package_dependencies(self):
        self.child('''
            module = importlib.import_module(package + ".inventory")
            original_schema = module.schema
            sys.modules["schema"] = types.ModuleType("schema")
            module = importlib.reload(module)
            t.assertIs(module.schema, original_schema)
            t.assertIsNot(module.schema, sys.modules["schema"])
        ''')

    def test_imports_leave_the_callers_search_path_unchanged(self):
        self.child('''
            before = list(sys.path)
            importlib.import_module(package + ".inventory")
            importlib.import_module(package + ".interview_guide")
            importlib.import_module(package + ".test_inventory")
            t.assertEqual(sys.path, before)
        ''')

    def test_original_suite_is_collectable_under_cached_foreign_modules(self):
        self.child('''
            for name in generic_names:
                sys.modules[name] = types.ModuleType(name)
            module = importlib.import_module(package + ".test_inventory")
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            def ids(node):
                if isinstance(node, unittest.TestSuite):
                    return [item for child in node for item in ids(child)]
                return [node.id()]
            expected = set()
            for value in vars(module).values():
                if isinstance(value, type) and issubclass(value, unittest.TestCase):
                    for method in dir(value):
                        if method.startswith("test_") and callable(getattr(value, method)):
                            expected.add(module.__name__ + "." + value.__name__ + "." + method)
            t.assertGreater(len(expected), 0)
            t.assertEqual(set(ids(suite)), expected)
        ''')

    def test_broken_sibling_import_is_not_hidden_by_a_generic_fallback(self):
        with tempfile.TemporaryDirectory(prefix="uiowa071-broken-sibling-") as tmp:
            root = Path(tmp)
            lane = root / "revenue" / HERE.name
            lane.mkdir(parents=True)
            shutil.copy2(HERE / "inventory.py", lane / "inventory.py")
            (lane / "schema.py").write_text('raise ImportError("deliberate sibling failure")\n', encoding="utf-8")
            self.child('''
                foreign = types.ModuleType("schema")
                foreign.UNKNOWN = "FOREIGN_UNKNOWN"
                sys.modules["schema"] = foreign
                with t.assertRaisesRegex(ImportError, "deliberate sibling failure"):
                    importlib.import_module(package + ".inventory")
                t.assertIs(sys.modules["schema"], foreign)
            ''', root=root)

    def test_absent_sibling_is_not_replaced_by_a_cached_generic_module(self):
        with tempfile.TemporaryDirectory(prefix="uiowa071-absent-sibling-") as tmp:
            root = Path(tmp)
            lane = root / "revenue" / HERE.name
            lane.mkdir(parents=True)
            shutil.copy2(HERE / "inventory.py", lane / "inventory.py")
            self.child('''
                foreign = types.ModuleType("schema")
                foreign.UNKNOWN = "FOREIGN_UNKNOWN"
                sys.modules["schema"] = foreign
                with t.assertRaises(ImportError):
                    importlib.import_module(package + ".inventory")
                t.assertIs(sys.modules["schema"], foreign)
            ''', root=root)

    def test_clean_fixture_cli_exports_are_byte_identical_between_modes(self):
        payload = self.assert_output_parity(CLEAN)
        self.assertEqual(payload["counts"], {"ACTIVE_USE": 2, "INFORMAL_EXPERIMENT": 4,
                                          "PLANNED_USE": 2, "UNSUPPORTED_CLAIM": 1, "UNKNOWN": 1})

    def test_hostile_fixture_cli_exports_are_byte_identical_between_modes(self):
        payload = self.assert_output_parity(HOSTILE)
        self.assertEqual(payload["meta"]["record_count"], 8)
        self.assertEqual(len(payload["entries"]), 8)
        self.assertNotIn("E-44821", json.dumps(payload))

    def test_empty_collection_cli_keeps_uncaptured_cells_distinct(self):
        with tempfile.TemporaryDirectory(prefix="uiowa071-empty-") as tmp:
            fixture = Path(tmp) / "empty.json"
            fixture.write_text("[]\n", encoding="utf-8")
            payload = self.assert_output_parity(fixture)
        self.assertEqual({c["state"] for c in payload["coverage"]}, {"NO_ENTRY_CAPTURED"})
        self.assertEqual(payload["meta"]["record_count"], 0)

    def test_direct_script_keeps_working_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory(prefix="uiowa071-foreign-cwd-") as tmp:
            result = self.cli("inventory", "--input", CLEAN, "--print", package_mode=False, cwd=tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UNSUPPORTED_CLAIM", result.stdout)
        self.assertIn("unsupported=1", result.stderr)

    def test_guide_cli_output_matches_between_script_and_package(self):
        script = self.cli("interview_guide", "--guide", package_mode=False)
        package = self.cli("interview_guide", "--guide")
        self.assertEqual(script.returncode, 0, script.stderr)
        self.assertEqual(package.returncode, 0, package.stderr)
        self.assertEqual((script.stdout, script.stderr), (package.stdout, package.stderr))

    def test_probe_cli_output_matches_between_script_and_package(self):
        for fixture in (CLEAN, HOSTILE):
            with self.subTest(fixture=fixture.name):
                script = self.cli("interview_guide", "--probes", fixture, package_mode=False)
                package = self.cli("interview_guide", "--probes", fixture)
                self.assertEqual(script.returncode, 0, script.stderr)
                self.assertEqual(package.returncode, 0, package.stderr)
                self.assertEqual((script.stdout, script.stderr), (package.stdout, package.stderr))
                self.assertIsInstance(json.loads(package.stdout), list)

    def test_package_inventory_missing_input_retains_exit_two(self):
        with tempfile.TemporaryDirectory(prefix="uiowa071-missing-") as tmp:
            result = self.cli("inventory", "--input", Path(tmp) / "missing.json")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("cannot read", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_package_inventory_malformed_input_does_not_create_outputs(self):
        with tempfile.TemporaryDirectory(prefix="uiowa071-malformed-") as tmp:
            bad, out = Path(tmp) / "bad.json", Path(tmp) / "out"
            bad.write_text("{not valid JSON", encoding="utf-8")
            result = self.cli("inventory", "--input", bad, "--outdir", out)
            self.assertFalse(out.exists())
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("not valid JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_package_guide_missing_input_retains_exit_two(self):
        with tempfile.TemporaryDirectory(prefix="uiowa071-missing-guide-") as tmp:
            result = self.cli("interview_guide", "--probes", Path(tmp) / "missing.json")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("cannot read", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_child_interpreter_uses_the_requested_optimization(self):
        result = self.child('print(json.dumps({"optimize": sys.flags.optimize}))')
        self.assertEqual(json.loads(result.stdout), {"optimize": sys.flags.optimize})


if __name__ == "__main__":
    unittest.main(verbosity=2)

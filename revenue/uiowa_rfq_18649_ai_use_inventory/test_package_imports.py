"""Composition regressions for UIOWA-071, using real source and both fixtures.

Run from repository root:
    python -m unittest revenue.uiowa_rfq_18649_ai_use_inventory.test_package_imports
    python -O -m unittest revenue.uiowa_rfq_18649_ai_use_inventory.test_package_imports

Children inherit the active optimization level. Foreign modules are synthetic
sentinels in isolated child interpreters, never aliases installed by production.
"""

import itertools
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
NAMES = ("schema", "inventory", "interview_guide")
PYTHON = [sys.executable] + (["-" + "O" * sys.flags.optimize] if sys.flags.optimize else [])


class TestPackageComposition(unittest.TestCase):
    def run_python(self, args, cwd=ROOT, expected=0):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            PYTHON + list(args), cwd=cwd, env=env,
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def run_code(self, code, cwd=ROOT):
        prelude = (
            "import sys, unittest\n"
            "check = unittest.TestCase()\n"
            "check.assertEqual(sys.flags.optimize, %d)\n" % sys.flags.optimize
        )
        return self.run_python(["-c", prelude + textwrap.dedent(code)], cwd=cwd)

    def cli(self, name, args, package, cwd=ROOT, expected=0):
        target = ["-m", PACKAGE + "." + name] if package else [str(HERE / (name + ".py"))]
        return self.run_python(target + list(args), cwd=cwd, expected=expected)

    def test_package_imports_do_not_create_bare_aliases_or_change_search_path(self):
        self.run_code('''
            import importlib
            before = list(sys.path)
            names = ("schema", "inventory", "interview_guide")
            check.assertFalse(set(names) & set(sys.modules))
            for name in names:
                importlib.import_module("revenue.uiowa_rfq_18649_ai_use_inventory." + name)
            check.assertEqual(sys.path, before)
            check.assertFalse(set(names) & set(sys.modules))
        ''')

    def test_each_cold_import_order_uses_its_own_schema(self):
        for order in itertools.permutations(NAMES):
            with self.subTest(order=order):
                self.run_code('''
                    import importlib
                    package = "revenue.uiowa_rfq_18649_ai_use_inventory."
                    modules = {name: importlib.import_module(package + name) for name in %r}
                    check.assertIs(modules["inventory"].schema, modules["schema"])
                    check.assertIs(modules["interview_guide"].schema, modules["schema"])
                    check.assertEqual(modules["inventory"].build([]).meta["record_count"], 0)
                ''' % (order,))

    def test_each_cached_import_order_preserves_foreign_modules(self):
        for order in itertools.permutations(NAMES):
            with self.subTest(order=order):
                self.run_code('''
                    import importlib, types
                    names = ("schema", "inventory", "interview_guide")
                    foreign = {name: types.ModuleType(name) for name in names}
                    foreign["schema"].UNKNOWN = "FOREIGN-SCHEMA"
                    sys.modules.update(foreign)
                    snapshots = {name: dict(module.__dict__) for name, module in foreign.items()}
                    package = "revenue.uiowa_rfq_18649_ai_use_inventory."
                    own = {name: importlib.import_module(package + name) for name in %r}
                    check.assertIs(own["inventory"].schema, own["schema"])
                    check.assertIs(own["interview_guide"].schema, own["schema"])
                    check.assertEqual(own["inventory"].UNKNOWN, "UNKNOWN")
                    result = own["inventory"].build([{"entry_id": "SYN", "group": "ESS",
                        "function": "development", "task": "fictional import regression"}])
                    check.assertEqual(result.entries[0]["classification"], "UNKNOWN")
                    for name, module in foreign.items():
                        check.assertIs(sys.modules[name], module)
                        check.assertEqual(module.__dict__, snapshots[name])
                ''' % (order,))

    def test_probe_cli_does_not_call_foreign_cached_inventory(self):
        self.run_code('''
            import contextlib, importlib, io, json, types
            from pathlib import Path
            foreign = {name: types.ModuleType(name) for name in ("schema", "inventory", "interview_guide")}
            foreign["schema"].UNKNOWN = "FOREIGN-SCHEMA"
            def wrong(*args, **kwargs):
                raise RuntimeError("foreign inventory was called")
            foreign["inventory"].load = wrong
            foreign["inventory"].build = wrong
            sys.modules.update(foreign)
            package = "revenue.uiowa_rfq_18649_ai_use_inventory."
            guide = importlib.import_module(package + "interview_guide")
            own = importlib.import_module(package + "inventory")
            fixture = Path(guide.__file__).parent / "fixtures/synthetic_ai_use.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                check.assertEqual(guide.main(["--probes", str(fixture)]), 0)
            payload = json.loads(output.getvalue())
            rows, label = own.load(fixture)
            expected = [{"entry_id": row["entry_id"], "classification": row["classification"],
                "probes": [{"id": q["id"], "text": q["text"]} for q in guide.probes_for(row)]}
                for row in own.build(rows, source_label=label).entries if guide.probes_for(row)]
            check.assertEqual(payload, expected)
            for name, module in foreign.items():
                check.assertIs(sys.modules[name], module)
        ''')

    def test_original_test_module_uses_package_scoped_dependencies(self):
        self.run_code('''
            import importlib, types
            names = ("schema", "inventory", "interview_guide")
            foreign = {name: types.ModuleType(name) for name in names}
            foreign["schema"].UNKNOWN = "FOREIGN-SCHEMA"
            sys.modules.update(foreign)
            prefix = "revenue.uiowa_rfq_18649_ai_use_inventory."
            tests = importlib.import_module(prefix + "test_inventory")
            for name in names:
                check.assertIs(getattr(tests, name), importlib.import_module(prefix + name))
                check.assertIs(sys.modules[name], foreign[name])
            check.assertEqual(tests.build(tests.CLEAN).meta["record_count"], 10)
        ''')

    def test_missing_package_dependency_is_not_masked_by_bare_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "revenue" / HERE.name
            target.mkdir(parents=True)
            shutil.copy2(HERE / "inventory.py", target / "inventory.py")
            self.run_code('''
                import importlib, types
                foreign = types.ModuleType("schema")
                foreign.UNKNOWN = "FOREIGN-SCHEMA"
                sys.modules["schema"] = foreign
                with check.assertRaises(ImportError):
                    importlib.import_module("revenue.uiowa_rfq_18649_ai_use_inventory.inventory")
                check.assertIs(sys.modules["schema"], foreign)
            ''', cwd=root)

    def test_inventory_script_and_package_emit_identical_four_files(self):
        for fixture in ("synthetic_ai_use.json", "synthetic_ai_use_hostile.json"):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as tmp:
                direct = Path(tmp) / "direct"
                package = Path(tmp) / "package"
                source = str(HERE / "fixtures" / fixture)
                first = self.cli("inventory", ["--input", source, "--outdir", str(direct)], False, cwd=tmp)
                second = self.cli("inventory", ["--input", source, "--outdir", str(package)], True)
                expected = {"ai_use_inventory.csv", "ai_use_gaps.csv", "ai_use_inventory.json", "ai_use_inventory.md"}
                self.assertEqual({p.name for p in direct.iterdir()}, expected)
                self.assertEqual({p.name for p in package.iterdir()}, expected)
                for name in sorted(expected):
                    self.assertEqual((direct / name).read_bytes(), (package / name).read_bytes(), name)
                self.assertEqual(first.stderr, second.stderr)

    def test_inventory_script_and_package_print_the_same_report(self):
        args = ["--input", str(HERE / "fixtures/synthetic_ai_use.json"), "--print"]
        a = self.cli("inventory", args, False)
        b = self.cli("inventory", args, True)
        self.assertEqual((a.stdout, a.stderr), (b.stdout, b.stderr))
        self.assertIn("unsupported=1", b.stderr)

    def test_guide_script_and_package_match_from_unrelated_script_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self.cli("interview_guide", ["--guide"], False, cwd=tmp)
        b = self.cli("interview_guide", ["--guide"], True)
        self.assertEqual((a.stdout, a.stderr), (b.stdout, b.stderr))
        self.assertIn("Q-TASK-01", b.stdout)

    def test_probe_script_and_package_match_for_both_real_fixtures(self):
        for fixture in ("synthetic_ai_use.json", "synthetic_ai_use_hostile.json"):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as tmp:
                args = ["--probes", str(HERE / "fixtures" / fixture)]
                a = self.cli("interview_guide", args, False, cwd=tmp)
                b = self.cli("interview_guide", args, True)
                self.assertEqual((a.stdout, a.stderr), (b.stdout, b.stderr))

    def test_bad_input_diagnostics_match_for_both_entry_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            malformed = Path(tmp) / "bad.json"
            malformed.write_text("{broken", encoding="utf-8")
            for name, option in (("inventory", "--input"), ("interview_guide", "--probes")):
                for path in (malformed, Path(tmp) / "missing.json"):
                    with self.subTest(name=name, path=path.name):
                        a = self.cli(name, [option, str(path)], False, cwd=tmp, expected=2)
                        b = self.cli(name, [option, str(path)], True, expected=2)
                        self.assertEqual((a.stdout, a.stderr), (b.stdout, b.stderr))
                        self.assertIn("error:", b.stderr)

    def test_original_43_tests_run_by_package_name(self):
        result = self.run_python(["-m", "unittest", PACKAGE + ".test_inventory"])
        self.assertIn("Ran 43 tests", result.stderr)
        self.assertIn("\nOK", result.stderr)


if __name__ == "__main__":
    unittest.main()

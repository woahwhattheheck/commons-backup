import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
V4 = HERE.parents[3]
sys.path.insert(0, str(V4))
import check_composition_graph as cg  # noqa: E402


class CompositionGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "pkg").mkdir()
        (self.root / "repairs").mkdir()
        (self.root / "research").mkdir()
        (self.root / "pkg" / "port_a.py").write_text("# a\n", encoding="utf-8")
        (self.root / "pkg" / "port_b.py").write_text("# b\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self, components, *, patterns=None, strict=True):
        required_patterns = sorted(cg.REQUIRED_DISCOVERY_PATTERNS)
        extra_patterns = list(patterns or [])
        return {
            "schema": "titan-v4-composition/v1",
            "mode": "fail_closed",
            "canonical_branch": "main",
            "canonical_root": "revenue/kaggriculture/cloud-execution-lab/candidates/v4",
            "components": components,
            "discovery": {
                "roots": ["pkg", *sorted(cg.REQUIRED_DISCOVERY_ROOTS)],
                "patterns": required_patterns + extra_patterns,
                "strict": strict,
                "ignore": [],
            },
        }

    def comp(self, cid, entry, inp, out, **extra):
        value = {
            "id": cid,
            "state": "compose",
            "package": "pkg",
            "entrypoints": [entry],
            "transforms": [{"surface": "runtime", "input_identity": inp, "output_identity": out}],
            "requires": [],
            "before": [],
            "after": [],
            "conflicts": [],
        }
        value.update(extra)
        return value

    def codes(self, result):
        return {item["code"] for item in result["errors"]}

    def test_valid_chain_is_deterministic(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out", before=["b"])
        b = self.comp("b", "pkg/port_b.py", "a-out", "b-out", requires=["a"])
        result = cg.validate_manifest(self.manifest([b, a], patterns=["port_*.py"]), self.root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["plan"], ["a", "b"])
        self.assertEqual(result["unregistered"], [])

    def test_evidence_only_zero_transform_is_not_composition_plan(self):
        evidence = {
            "id": "native-equivalence",
            "state": "evidence_only",
            "package": "pkg",
            "entrypoints": ["pkg/port_a.py"],
            "receipt": "pkg/receipt.json",
            "transforms": [],
            "requires": [],
            "before": [],
            "after": [],
            "conflicts": [],
        }
        result = cg.validate_manifest(self.manifest([evidence], patterns=["port_a.py"]), self.root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["plan"], [])
        self.assertEqual(result["evidence_only"], ["native-equivalence"])

    def test_unordered_overlap_fails(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out")
        b = self.comp("b", "pkg/port_b.py", "base", "b-out")
        result = cg.validate_manifest(self.manifest([a, b], patterns=["port_a.py","port_b.py"]), self.root)
        self.assertIn("unordered_surface_overlap", self.codes(result))

    def test_stale_preimage_fails(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out", before=["b"])
        b = self.comp("b", "pkg/port_b.py", "WRONG", "b-out")
        result = cg.validate_manifest(self.manifest([a, b], patterns=["port_a.py","port_b.py"]), self.root)
        self.assertIn("stale_preimage", self.codes(result))

    def test_cycle_fails(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out", after=["b"])
        b = self.comp("b", "pkg/port_b.py", "a-out", "b-out", after=["a"])
        result = cg.validate_manifest(self.manifest([a, b], patterns=["port_a.py","port_b.py"]), self.root)
        self.assertIn("dependency_cycle", self.codes(result))
        self.assertEqual(result["plan"], [])

    def test_unregistered_entrypoint_fails_closed(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out")
        result = cg.validate_manifest(self.manifest([a], patterns=["port_*.py"]), self.root)
        self.assertIn("unregistered_entrypoint", self.codes(result))
        self.assertEqual(result["unregistered"], ["pkg/port_b.py"])

    def test_reasoned_ignore_cannot_suppress_unregistered_entrypoint(self):
        rogue = self.root / "research" / "rogue.py"
        rogue.write_text("# rogue executable\n", encoding="utf-8")
        manifest = self.manifest([], patterns=["rogue.py"])
        manifest["discovery"]["ignore"] = [
            {"path": "research/rogue.py", "reason": "temporarily ignore it"}
        ]
        result = cg.validate_manifest(manifest, self.root)
        self.assertFalse(result["ok"], result)
        self.assertIn("discovery_ignore_not_empty", self.codes(result))
        self.assertIn("unregistered_entrypoint", self.codes(result))
        self.assertEqual(result["unregistered"], ["research/rogue.py"])

    def test_empty_discovery_ignore_remains_valid(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out")
        manifest = self.manifest([a], patterns=["port_a.py"])
        self.assertEqual(manifest["discovery"]["ignore"], [])
        result = cg.validate_manifest(manifest, self.root)
        self.assertTrue(result["ok"], result)

    def test_discovery_strict_false_cannot_downgrade_unregistered_to_warning(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out")
        result = cg.validate_manifest(self.manifest([a], patterns=["port_*.py"], strict=False), self.root)
        self.assertFalse(result["ok"], result)
        self.assertIn("discovery_not_strict", self.codes(result))
        self.assertIn("unregistered_entrypoint", self.codes(result))
        self.assertEqual(result["warnings"], [])

    def test_unsafe_discovery_root_fails_instead_of_disappearing(self):
        manifest = self.manifest([], patterns=["port_a.py"])
        manifest["discovery"]["roots"] = ["../pkg"]
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("bad_discovery_root", self.codes(result))

    def test_non_string_discovery_pattern_fails_instead_of_disappearing(self):
        manifest = self.manifest([])
        manifest["discovery"]["patterns"] = [17]
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("bad_discovery_pattern", self.codes(result))

    def test_malformed_ignore_fails_instead_of_silently_not_ignoring(self):
        manifest = self.manifest([], patterns=["port_*.py"])
        manifest["discovery"]["ignore"] = [{"path": "pkg/port_a.py", "reason": ""}]
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("ignore_without_reason", self.codes(result))

    def test_empty_discovery_roots_cannot_disable_census(self):
        manifest = self.manifest([], patterns=["port_a.py"])
        manifest["discovery"]["roots"] = []
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("discovery_roots_empty", self.codes(result))

    def test_empty_discovery_patterns_cannot_disable_census(self):
        manifest = self.manifest([])
        manifest["discovery"]["patterns"] = []
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("discovery_patterns_empty", self.codes(result))

    def test_package_must_be_directory(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out", package="pkg/port_a.py")
        result = cg.validate_manifest(self.manifest([a], patterns=["port_a.py"]), self.root)
        rows = [e for e in result["errors"] if e["code"] == "unsafe_package_resolution"]
        self.assertTrue(rows, result)
        self.assertEqual(rows[0].get("reason"), "not_directory")

    def test_entrypoint_must_be_regular_file(self):
        (self.root / "pkg" / "dir.py").mkdir()
        a = self.comp("a", "pkg/dir.py", "base", "a-out")
        result = cg.validate_manifest(self.manifest([a], patterns=["port_a.py"]), self.root)
        rows = [e for e in result["errors"] if e["code"] == "unsafe_entrypoint_resolution"]
        self.assertTrue(rows, result)
        self.assertEqual(rows[0].get("reason"), "not_file")

    def test_discovery_roots_cannot_narrow_away_canonical_research(self):
        manifest = self.manifest([], patterns=["port_a.py"])
        manifest["discovery"]["roots"] = ["pkg", "repairs"]
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("missing_required_discovery_root", self.codes(result))

    def test_discovery_patterns_cannot_drop_canonical_coverage(self):
        manifest = self.manifest([])
        dropped = sorted(cg.REQUIRED_DISCOVERY_PATTERNS)[0]
        manifest["discovery"]["patterns"].remove(dropped)
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("missing_required_discovery_pattern", self.codes(result))

    def test_registered_entrypoint_must_be_reached_by_discovery(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out")
        result = cg.validate_manifest(self.manifest([a]), self.root)
        self.assertIn("registered_entrypoint_not_discovered", self.codes(result))

    def test_symlink_ancestor_fails_closed(self):
        real = self.root / "real"
        real.mkdir()
        (real / "entry.py").write_text("# real\n", encoding="utf-8")
        alias = self.root / "alias"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(cg._path_status(self.root, "alias/entry.py", expected="file"), "symlink")

    def test_active_requires_blocked_fails(self):
        blocked = {
            "id": "hold",
            "state": "blocked",
            "reason": "economic gate pending",
            "package": "pkg",
            "entrypoints": [],
            "transforms": [],
            "requires": [],
            "before": [],
            "after": [],
            "conflicts": [],
        }
        a = self.comp("a", "pkg/port_a.py", "base", "a-out", requires=["hold"])
        result = cg.validate_manifest(self.manifest([blocked, a], patterns=["port_a.py"]), self.root)
        self.assertIn("active_requires_noncompose", self.codes(result))

    def test_active_conflict_fails(self):
        a = self.comp("a", "pkg/port_a.py", "base", "a-out", conflicts=["b"])
        b = self.comp("b", "pkg/port_b.py", "a-out", "b-out", after=["a"])
        result = cg.validate_manifest(self.manifest([a, b], patterns=["port_a.py","port_b.py"]), self.root)
        self.assertIn("active_conflict", self.codes(result))

    def test_ignore_requires_reason(self):
        manifest = self.manifest([], patterns=["port_*.py"])
        manifest["discovery"]["ignore"] = ["pkg/port_a.py"]
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("ignore_without_reason", self.codes(result))

    def test_wrong_canonical_root_fails(self):
        manifest = self.manifest([], patterns=["port_a.py"])
        manifest["canonical_root"] = "revenue/kaggriculture/cloud-execution-lab/candidates/v4-copy"
        result = cg.validate_manifest(manifest, self.root)
        self.assertIn("wrong_canonical_root", self.codes(result))

    def test_symlink_entrypoint_fails_closed(self):
        target = self.root / "outside.py"
        target.write_text("# outside\n", encoding="utf-8")
        link = self.root / "pkg" / "linked.py"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        a = self.comp("a", "pkg/linked.py", "base", "a-out")
        result = cg.validate_manifest(self.manifest([a], patterns=["port_a.py"]), self.root)
        self.assertIn("unsafe_entrypoint_resolution", self.codes(result))

    def test_reachable_follows_directed_edges(self):
        edges = {"a": {"b"}, "b": {"c"}, "c": set()}
        self.assertTrue(cg._reachable("a", "c", edges))
        self.assertTrue(cg._reachable("a", "a", edges))
        self.assertFalse(cg._reachable("c", "a", edges))
        self.assertFalse(cg._reachable("a", "missing", edges))

    def test_live_canonical_graph_registers_e13_and_is_ok(self):
        manifest = json.loads((V4 / "COMPOSITION.json").read_text(encoding="utf-8"))
        result = cg.validate_manifest(manifest, V4)
        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["unregistered"])
        self.assertEqual([], result["errors"])
        self.assertIn("e13-future-sale-solvency", result["blocked"])
        owned = {
            ep
            for comp in manifest["components"]
            if isinstance(comp, dict)
            for ep in comp.get("entrypoints", [])
        }
        self.assertIn(
            "repairs/gameplay/e13-future-sale-solvency/port_current_runtime.py",
            owned,
        )
        self.assertIn(
            "repairs/gameplay/defensive-guard/r04_defensive_guards.py",
            owned,
        )
        self.assertNotIn(
            "repairs/gameplay/r04-defensive-guards/r04_defensive_guards.py",
            owned,
        )
        self.assertTrue(
            set(cg.REQUIRED_DISCOVERY_PATTERNS).issubset(set(manifest["discovery"]["patterns"]))
        )

    def test_required_discovery_pins_canonical_defensive_guard_not_superseded_mirror(self):
        canonical = "repairs/gameplay/defensive-guard/r04_defensive_guards.py"
        superseded = "repairs/gameplay/r04-defensive-guards/r04_defensive_guards.py"
        self.assertIn(canonical, cg.REQUIRED_DISCOVERY_PATTERNS)
        self.assertNotIn(superseded, cg.REQUIRED_DISCOVERY_PATTERNS)
        manifest = json.loads((V4 / "COMPOSITION.json").read_text(encoding="utf-8"))
        self.assertIn(canonical, manifest["discovery"]["patterns"])
        self.assertNotIn(superseded, manifest["discovery"]["patterns"])
        result = cg.validate_manifest(manifest, V4)
        self.assertTrue(result["ok"], result)
        self.assertIn("r04-defensive-guards", result["blocked"])

    def test_live_dropping_canonical_defensive_guard_pattern_fails_closed(self):
        canonical = "repairs/gameplay/defensive-guard/r04_defensive_guards.py"
        manifest = json.loads((V4 / "COMPOSITION.json").read_text(encoding="utf-8"))
        patterns = list(manifest["discovery"]["patterns"])
        patterns.remove(canonical)
        manifest["discovery"]["patterns"] = patterns
        result = cg.validate_manifest(manifest, V4)
        self.assertFalse(result["ok"], result)
        self.assertTrue(
            any(
                item.get("code") == "missing_required_discovery_pattern"
                and item.get("pattern") == canonical
                for item in result["errors"]
            ),
            result,
        )

    def test_live_dropping_e13_registration_fails_unregistered_entrypoint(self):
        manifest = json.loads((V4 / "COMPOSITION.json").read_text(encoding="utf-8"))
        manifest["components"] = [
            comp
            for comp in manifest["components"]
            if not (isinstance(comp, dict) and comp.get("id") == "e13-future-sale-solvency")
        ]
        result = cg.validate_manifest(manifest, V4)
        self.assertFalse(result["ok"], result)
        self.assertIn(
            "repairs/gameplay/e13-future-sale-solvency/port_current_runtime.py",
            result["unregistered"],
        )
        self.assertTrue(
            any(
                item.get("code") == "unregistered_entrypoint"
                and item.get("path")
                == "repairs/gameplay/e13-future-sale-solvency/port_current_runtime.py"
                for item in result["errors"]
            ),
            result,
        )

    def test_bare_defensive_guard_filename_discovers_quarantined_duplicate(self):
        manifest = json.loads((V4 / "COMPOSITION.json").read_text(encoding="utf-8"))
        manifest["discovery"]["patterns"] = list(manifest["discovery"]["patterns"]) + [
            "r04_defensive_guards.py"
        ]
        result = cg.validate_manifest(manifest, V4)
        self.assertFalse(result["ok"], result)
        self.assertIn(
            "repairs/gameplay/r04-defensive-guards/r04_defensive_guards.py",
            result["unregistered"],
        )
        self.assertNotIn(
            "repairs/gameplay/defensive-guard/r04_defensive_guards.py",
            result["unregistered"],
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Focused contract tests for host.ci_fleet; no provider jobs are dispatched."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from host import battery_report, ci_battery, ci_fleet as fleet


class FleetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / "fixture"
        cls.root.mkdir()
        for path, text in {
            "test_a.py": "pass\n",
            "test_z.py": "pass # z\n",
            "infra/nested/test_b.py": "pass # infra\n",
            "test_c.js": "process.exit(0)\n",
            "nested/test_not_in_battery.py": "raise SystemExit(99)\n",
            "docs/weird\\name.txt": "unrelated path must not poison discovery\n",
        }.items():
            dest = cls.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        (cls.root / "host").mkdir()
        repo_root = Path(__file__).resolve().parent
        for path in fleet.RUNNER_PATHS:
            shutil.copyfile(repo_root / path, cls.root / path)

        def git(*args: str) -> str:
            return subprocess.check_output(
                ["git", "-C", str(cls.root), *args], text=True
            ).strip()

        git("init", "-q")
        git("config", "user.name", "CI Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "core.autocrlf", "false")
        git("add", ".")
        git("commit", "-qm", "fixture")
        cls.sha = git("rev-parse", "HEAD")
        cls.runtime = {
            "python_version": sys.version.split()[0],
            "node_version": "22.0.0",
            "platform": sys.platform,
            "architecture": "fixture-architecture",
        }
        cls.template = fleet.build_plan(cls.root, cls.sha, 2, cls.runtime)

    def setUp(self):
        self.plan = copy.deepcopy(self.template)

    def attempt(
        self,
        index: int = 0,
        number: int = 1,
        *,
        codes: dict[str, int] | None = None,
        complete: bool = True,
        parent: str | None = None,
        plan: dict | None = None,
        outcome: str | None = None,
        provider: str = "portable-worker",
        execution_id: str | None = None,
    ) -> dict:
        plan = plan or self.plan
        wanted = plan["shards"][index]["paths"]
        selected = wanted if complete else wanted[:1]
        inventory = {row["path"]: row for row in plan["inventory"]}
        fields = ["checkout_sha", plan["source_sha"], ""]
        codes = codes or {}
        for path in selected:
            fields.extend([inventory[path]["command"], "./" + path, str(codes.get(path, 0))])
        failed = any(codes.get(path, 0) != 0 for path in selected)
        if complete:
            fields.extend(["battery_complete", "", str(int(failed))])
        raw = ("\0".join(fields) + "\0").encode()
        outcome = outcome or ("failure" if failed else "success" if complete else "cancelled")
        report = battery_report.build_report(self.root, raw, outcome, {})
        report["scope"] = {
            "kind": "full" if plan["shard_count"] == 1 else "shard",
            "requested": [],
            "shard_index": index,
            "shard_count": plan["shard_count"],
            "discovered_files": len(plan["inventory"]),
            "planned_files": len(wanted),
        }
        report["execution"] = {
            "kind": "direct-process",
            "python_version": plan["runtime"]["python_version"],
            "worktree_dirty_at_start": False,
            "preflight_error": None,
            "test_file_sha256": {path: inventory[path]["sha256"] for path in selected},
        }
        output = f"/ephemeral-output/shard-{index}-attempt-{number}"
        command = [
            output if part == fleet.OUTPUT_SLOT else part
            for part in plan["shards"][index]["command_template"]
        ]
        return fleet.make_attempt(
            plan,
            index,
            number,
            report,
            raw,
            runtime=copy.deepcopy(plan["runtime"]),
            command=command,
            output_dir=output,
            provenance={
                "kind": "executed",
                "measured": True,
                "provider": provider,
                "execution_id": execution_id or f"shard-{index}-attempt-{number}",
            },
            runner_inputs=copy.deepcopy(plan["runner_inputs"]),
            parent_attempt_sha256=parent,
        )

    def checked(self, plan: dict, attempts: list[dict]) -> dict:
        anchor = fleet.verify_plan_source(self.root, plan)
        return fleet.aggregate(plan, attempts, expected_plan_sha256=anchor)

    def assert_invalid_attempt(self, row: dict) -> None:
        row = fleet.seal(row, "attempt_sha256")
        result = self.checked(self.plan, [row])
        self.assertEqual(result["status"], "INVALID", result)
        self.assertTrue(result["findings"])

    def test_plan_matches_existing_discovery_and_is_deterministic(self):
        self.assertEqual(
            [(row["command"], row["path"]) for row in self.plan["inventory"]],
            ci_battery.discover(self.root),
        )
        self.assertEqual(self.plan, fleet.build_plan(self.root, self.sha, 2, self.runtime))
        self.assertEqual(self.plan, fleet.build_plan(self.root, self.sha, 2, self.runtime, 0.0))
        paths = [path for shard in self.plan["shards"] for path in shard["paths"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(paths), {row["path"] for row in self.plan["inventory"]})
        for row in self.plan["inventory"]:
            self.assertEqual(
                row["sha256"], hashlib.sha256((self.root / row["path"]).read_bytes()).hexdigest()
            )

    def test_committed_inventory_survives_sparse_worktree(self):
        missing = self.root / "test_z.py"
        original = missing.read_bytes()
        try:
            missing.unlink()
            self.assertEqual(len(ci_battery.discover(self.root)), 3)
            plan = fleet.build_plan(self.root, self.sha, 2, self.runtime)
        finally:
            missing.write_bytes(original)
        self.assertEqual(plan, self.plan)
        self.assertEqual(len(plan["inventory"]), 4)

    def test_complete_set_requires_all_shards_and_single_shard_works(self):
        self.assertEqual(self.checked(self.plan, [])["status"], "PARTIAL")
        one = self.checked(self.plan, [self.attempt(0)])
        self.assertEqual(one["status"], "PARTIAL")
        full = self.checked(self.plan, [self.attempt(1), self.attempt(0)])
        self.assertEqual(full["status"], "PASSED")
        self.assertEqual(full["passed_files"], 4)
        single = fleet.build_plan(self.root, self.sha, 1, self.runtime)
        self.assertEqual(self.checked(single, [self.attempt(plan=single)])["status"], "PASSED")

    def test_complete_but_unanchored_is_unverified(self):
        result = fleet.aggregate(self.plan, [self.attempt(), self.attempt(1)])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["source_binding"], "unverified")

    def test_resealed_reduced_inventory_cannot_source_bind(self):
        reduced = copy.deepcopy(self.plan)
        reduced["inventory"] = reduced["inventory"][:2]
        reduced["inventory_sha256"] = fleet.digest(reduced["inventory"])
        reduced["shards"] = [
            fleet.shard_spec(reduced["inventory"], 2, i, reduced["timeout_seconds"])
            for i in range(2)
        ]
        reduced = fleet.seal(reduced, "plan_sha256")
        attempts = [self.attempt(i, plan=reduced) for i in range(2)]
        self.assertEqual(fleet.aggregate(reduced, attempts)["status"], "UNVERIFIED")
        with self.assertRaises(fleet.FleetError):
            fleet.verify_plan_source(self.root, reduced)
        anchor = fleet.verify_plan_source(self.root, self.plan)
        result = fleet.aggregate(reduced, attempts, expected_plan_sha256=anchor)
        self.assertEqual(result["status"], "INVALID")

    def test_retry_success_reuses_other_shard_and_later_failure_supersedes_pass(self):
        path = self.plan["shards"][0]["paths"][0]
        failed, other = self.attempt(codes={path: 7}), self.attempt(1)
        self.assertEqual(self.checked(self.plan, [failed, other])["status"], "FAILED")
        retry = self.attempt(number=2, parent=failed["attempt_sha256"])
        result = self.checked(self.plan, [retry, other, failed])
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["shards"][1]["attempt_sha256"], other["attempt_sha256"])
        self.assertEqual(result["shards"][0]["attempts_retained"], 2)

        first = self.attempt()
        later = self.attempt(
            number=2,
            parent=first["attempt_sha256"],
            codes={path: 9},
        )
        for attempts in ([first, later, other], [later, other, first]):
            result = self.checked(self.plan, list(attempts))
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["shards"][0]["latest_attempt"], 2)

    def test_interruption_never_falls_back_to_prior_pass(self):
        first = self.attempt()
        interrupted = self.attempt(
            number=2,
            parent=first["attempt_sha256"],
            complete=False,
        )
        result = self.checked(self.plan, [first, interrupted, self.attempt(1)])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["passed_files"], 2)

    def test_duplicate_receipts_provider_ids_and_bad_lineage_are_invalid(self):
        one = self.attempt()
        self.assertEqual(self.checked(self.plan, [one, one])["status"], "INVALID")
        other = self.attempt(1, execution_id=one["provenance"]["execution_id"])
        self.assertEqual(self.checked(self.plan, [one, other])["status"], "INVALID")
        later = self.attempt(number=2, parent="a" * 64)
        self.assertEqual(self.checked(self.plan, [one, later])["status"], "INVALID")

    def test_source_runtime_command_runner_report_and_plan_mismatches_reject(self):
        for field in ("source", "runtime", "command", "runner", "python_report", "plan"):
            with self.subTest(field=field):
                row = self.attempt()
                if field == "source":
                    row["source_sha"] = "a" * 40
                elif field == "runtime":
                    row["runtime"]["node_version"] = "different"
                elif field == "command":
                    row["command"].insert(2, "--test")
                elif field == "runner":
                    row["runner_inputs"][0]["sha256"] = "a" * 64
                elif field == "python_report":
                    row["report"]["execution"]["python_version"] = "different"
                else:
                    row["plan_sha256"] = "a" * 64
                self.assert_invalid_attempt(row)

    def test_fixture_or_unmeasured_provenance_rejects(self):
        for change in (
            {"kind": "fixture"},
            {"measured": False},
            {"provider": "local-fixture"},
            {"provider": "mock-runner"},
            {"execution_id": ""},
        ):
            with self.subTest(change=change):
                row = self.attempt()
                row["provenance"].update(change)
                self.assert_invalid_attempt(row)

    def test_raw_results_cannot_be_replaced_by_passing_report(self):
        row = self.attempt()
        path = self.plan["shards"][0]["paths"][0]
        failed = self.attempt(codes={path: 3})
        for key in ("raw_results_base64", "raw_results_sha256"):
            row[key] = failed[key]
        self.assert_invalid_attempt(row)

    def test_report_hash_scope_and_preflight_inconsistencies_reject(self):
        for field in ("counts", "blob", "hash", "dirty", "preflight", "scope", "complete"):
            with self.subTest(field=field):
                row = self.attempt()
                report = row["report"]
                if field == "counts":
                    report["counts"]["passed_files"] += 1
                elif field == "blob":
                    report["results"][0]["source_blob_sha"] = "a" * 40
                elif field == "hash":
                    report["execution"]["test_file_sha256"][report["results"][0]["path"]] = "a" * 64
                elif field == "dirty":
                    report["execution"]["worktree_dirty_at_start"] = True
                elif field == "preflight":
                    report["execution"]["preflight_error"] = "selected_not_tracked_regular"
                elif field == "scope":
                    report["scope"]["kind"] = "selected"
                else:
                    report["complete"] = False
                self.assert_invalid_attempt(row)

    def test_raw_duplicate_foreign_or_missing_paths_never_pass(self):
        for defect in ("duplicate", "foreign", "missing"):
            with self.subTest(defect=defect):
                row = self.attempt()
                fields = base64.b64decode(row["raw_results_base64"]).decode().split("\0")[:-1]
                if defect == "duplicate":
                    fields[6:9] = fields[3:6]
                elif defect == "foreign":
                    fields[4] = "./" + self.plan["shards"][1]["paths"][0]
                else:
                    del fields[6:9]
                changed = ("\0".join(fields) + "\0").encode()
                row["raw_results_base64"] = base64.b64encode(changed).decode()
                row["raw_results_sha256"] = hashlib.sha256(changed).hexdigest()
                self.assert_invalid_attempt(row)

    def test_plan_overlap_empty_digest_order_and_unknown_fields_reject(self):
        for defect in ("overlap", "empty", "digest", "order", "unknown"):
            with self.subTest(defect=defect):
                plan = copy.deepcopy(self.plan)
                if defect == "overlap":
                    plan["shards"][1]["paths"] = plan["shards"][0]["paths"]
                elif defect == "empty":
                    plan["inventory"] = []
                elif defect == "digest":
                    plan["inventory"][0]["sha256"] = "a" * 64
                elif defect == "order":
                    plan["inventory"].reverse()
                else:
                    plan["unexpected"] = True
                plan = fleet.seal(plan, "plan_sha256")
                with self.assertRaises(fleet.FleetError):
                    fleet.validate_plan(plan)

    def test_2968_file_plan_has_complete_disjoint_shards(self):
        plan = copy.deepcopy(self.plan)
        inventory = [
            {
                "path": f"test_{i:04}.py",
                "command": "python3",
                "source_blob_sha": "b" * 40,
                "sha256": "c" * 64,
            }
            for i in range(2968)
        ]
        plan.update(
            inventory=inventory,
            inventory_sha256=fleet.digest(inventory),
            shard_count=16,
            shards=[
                fleet.shard_spec(inventory, 16, i, plan["timeout_seconds"])
                for i in range(16)
            ],
        )
        plan = fleet.seal(plan, "plan_sha256")
        fleet.validate_plan(plan)
        paths = [path for shard in plan["shards"] for path in shard["paths"]]
        self.assertEqual(len(paths), 2968)
        self.assertEqual(len(set(paths)), 2968)
        self.assertEqual(set(paths), {row["path"] for row in inventory})

    def test_invalid_planner_inputs_and_strict_json_reject(self):
        for kwargs in (
            {"shard_count": 0},
            {"shard_count": 5},
            {"timeout": float("nan")},
            {"source_sha": "main"},
            {"runtime": {}},
        ):
            with self.subTest(kwargs=kwargs):
                options = dict(root=self.root, source_sha=self.sha, shard_count=2, runtime=self.runtime)
                options.update(kwargs)
                with self.assertRaises(fleet.FleetError):
                    fleet.build_plan(**options)
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff'):
            with self.subTest(raw=raw):
                with self.assertRaises(fleet.FleetError):
                    fleet.loads_json(raw)

    def test_cli_plan_and_partial_aggregation_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime, plan = root / "runtime.json", root / "plan.json"
            runtime.write_text(json.dumps(self.runtime))
            cli = Path(__file__).parent / "host/ci_fleet.py"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(cli),
                    "plan",
                    "--root",
                    str(self.root),
                    "--source-sha",
                    self.sha,
                    "--shards",
                    "2",
                    "--runtime",
                    str(runtime),
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            planned = json.loads(result.stdout)
            fleet.validate_plan(planned)
            plan.write_text(result.stdout)
            result = subprocess.run(
                [sys.executable, "-B", str(cli), "aggregate", "--plan", str(plan)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main()

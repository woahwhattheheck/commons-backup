from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from .core import (
    AUTHORITIES, RefactorError, TRACK1_LIMIT_MICROUSD, assemble_source,
    canonical_bytes, compile_run, load_json_bytes, normalize_run, pareto_ids,
    proof_token_count, result_bytes, sha256, verify_result, write_exclusive,
)

D = hashlib.sha256(b"origin").hexdigest()
REQ = hashlib.sha256(b"request").hexdigest()
RESP = hashlib.sha256(b"response").hexdigest()


def candidate(cid="C1", proof="rfl", cost=100_000, model="frontier-model", attempt=1, seed=7):
    return {
        "candidate_id": cid,
        "proof": proof,
        "model": model,
        "api_cost_microusd": cost,
        "attempt": attempt,
        "seed": seed,
        "request_digest": REQ,
        "response_digest": RESP,
    }


def task(candidates=None, **overrides):
    out = {
        "schema": "vericodegen.refactor-task/v1",
        "task_id": "warmup/example-1",
        "origin_ref": "arena:warmup/example-1",
        "origin_digest": D,
        "preamble": "import Mathlib",
        "declaration": "theorem frozen_statement (n : Nat) : n = n",
        "baseline_proof": "exact rfl",
        "candidates": list(candidates if candidates is not None else [candidate()]),
    }
    out.update(overrides)
    return out


def toolchain(label, role, fake, mode=None, timeout=2, repetitions=1):
    return {
        "label": label,
        "role": role,
        "argv": [sys.executable, str(fake), mode or role, "{file}"],
        "timeout_seconds": timeout,
        "repetitions": repetitions,
    }


def run_obj(fake, candidates=None, transfers=0, **task_overrides):
    tcs = [toolchain("lean-target", "target", fake, "target", repetitions=1)]
    for i in range(transfers):
        tcs.append(toolchain(f"lean-transfer-{i+1}", "transfer", fake, "transfer", repetitions=1))
    return {
        "schema": "vericodegen.refactor-run/v1",
        "task": task(candidates, **task_overrides),
        "toolchains": tcs,
    }


def rehash(package):
    core = {k: v for k, v in package.items() if k != "package_digest"}
    package["package_digest"] = sha256(canonical_bytes(core))
    return package


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fake = Path(self.tmp.name) / "fake_lean.py"
        self.fake.write_text(textwrap.dedent("""
            import pathlib, sys, time
            mode, path = sys.argv[1], pathlib.Path(sys.argv[2])
            text = path.read_text(encoding='utf-8')
            if 'TIMEOUT' in text:
                time.sleep(2.5)
            if 'BIGOUT' in text:
                sys.stdout.write('x' * 100000)
            if 'SLOW' in text:
                time.sleep(0.03)
            if 'FAIL_TARGET' in text and mode == 'target':
                sys.exit(3)
            if 'XFER_FAIL' in text and mode == 'transfer':
                sys.exit(4)
            sys.stdout.write('fake-lean-ok\\n')
            sys.exit(0)
        """), encoding="utf-8")

    def test_good_candidate_selected(self):
        p = compile_run(run_obj(self.fake))
        self.assertEqual(p["selected_id"], "C1")
        self.assertIn("C1", p["pareto_ids"])
        self.assertTrue(verify_result(p)["valid"])

    def test_source_assembly_freezes_prefix(self):
        r = normalize_run(run_obj(self.fake))
        src = assemble_source(r["task"], "rfl\n-- theorem HACK : False := by sorry")
        prefix = "import Mathlib\n\ntheorem frozen_statement (n : Nat) : n = n := by\n"
        self.assertTrue(src.startswith(prefix))
        self.assertEqual(src.count("theorem frozen_statement"), 1)
        self.assertIn("  -- theorem HACK", src)

    def test_transfer_failure_prefers_baseline(self):
        p = compile_run(run_obj(self.fake, [candidate(proof="rfl\n-- XFER_FAIL")], transfers=1))
        cand = next(x for x in p["observations"] if x["candidate_id"] == "C1")
        self.assertEqual(cand["transfer_passes"], 0)
        self.assertEqual(p["selected_id"], "BASELINE")

    def test_target_failure_excluded(self):
        p = compile_run(run_obj(self.fake, [candidate(proof="rfl\n-- FAIL_TARGET")]))
        cand = next(x for x in p["observations"] if x["candidate_id"] == "C1")
        self.assertFalse(cand["target_pass"])
        self.assertNotIn("C1", p["pareto_ids"])

    def test_baseline_failure_aborts(self):
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, baseline_proof="rfl\n-- FAIL_TARGET"))

    def test_budget_exact_boundary(self):
        p = compile_run(run_obj(self.fake, [candidate(cost=TRACK1_LIMIT_MICROUSD)]))
        self.assertEqual(p["budget"]["remaining_microusd"], 0)

    def test_budget_overflow_rejected(self):
        cs = [candidate("C1", cost=2_000_000), candidate("C2", proof="exact rfl", cost=1_000_001)]
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, cs))

    def test_bool_cost_rejected(self):
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, [candidate(cost=True)]))

    def test_negative_cost_rejected(self):
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, [candidate(cost=-1)]))

    def test_duplicate_candidate_id_rejected(self):
        cs = [candidate("C1", proof="rfl"), candidate("C1", proof="exact rfl")]
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, cs))

    def test_duplicate_proof_payload_rejected(self):
        cs = [candidate("C1", proof="rfl"), candidate("C2", proof="rfl")]
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, cs))

    def test_declaration_body_rejected(self):
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, declaration="theorem x : True := by trivial"))

    def test_where_declaration_rejected(self):
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, declaration="theorem x : True where"))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(RefactorError):
            load_json_bytes(b'{"schema":"a","schema":"b"}')

    def test_invalid_digest_rejected(self):
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, origin_digest="xyz"))

    def test_exact_one_target_required(self):
        r = run_obj(self.fake, transfers=1)
        r["toolchains"][1]["role"] = "target"
        with self.assertRaises(RefactorError):
            compile_run(r)

    def test_duplicate_toolchain_label_rejected(self):
        r = run_obj(self.fake, transfers=1)
        r["toolchains"][1]["label"] = "lean-target"
        with self.assertRaises(RefactorError):
            compile_run(r)

    def test_exact_file_placeholder_required(self):
        r = run_obj(self.fake)
        r["toolchains"][0]["argv"][-1] = "Main.lean"
        with self.assertRaises(RefactorError):
            compile_run(r)

    def test_timeout_is_candidate_failure(self):
        r = run_obj(self.fake, [candidate(proof="rfl\n-- TIMEOUT")])
        r["toolchains"][0]["timeout_seconds"] = 1
        r["toolchains"][0]["repetitions"] = 1
        p = compile_run(r)
        c = next(x for x in p["observations"] if x["candidate_id"] == "C1")
        self.assertFalse(c["target_pass"])
        self.assertEqual(c["toolchains"][0]["runs"][0]["exit_code"], 124)

    def test_output_capture_is_bounded(self):
        p = compile_run(run_obj(self.fake, [candidate(proof="rfl\n-- BIGOUT")]))
        c = next(x for x in p["observations"] if x["candidate_id"] == "C1")
        for tc in c["toolchains"]:
            for obs in tc["runs"]:
                self.assertLessEqual(obs["stdout_bytes"], 65536)

    def test_missing_compiler_makes_baseline_fail_closed(self):
        r = run_obj(self.fake)
        r["toolchains"][0]["argv"][0] = "/definitely/missing/python"
        with self.assertRaises(RefactorError):
            compile_run(r)

    def test_pareto_dominated_exclusion(self):
        base = {"target_pass": True, "token_count": 10, "target_median_elapsed_ns": 100, "transfer_passes": 2, "candidate_id": "A"}
        dominated = {"target_pass": True, "token_count": 11, "target_median_elapsed_ns": 101, "transfer_passes": 1, "candidate_id": "B"}
        tradeoff = {"target_pass": True, "token_count": 8, "target_median_elapsed_ns": 200, "transfer_passes": 2, "candidate_id": "C"}
        self.assertEqual(pareto_ids([base, dominated, tradeoff]), ["A", "C"])

    def test_lexical_metric_stable(self):
        self.assertEqual(proof_token_count("exact Nat.add_zero n"), proof_token_count("exact   Nat.add_zero\n n"))
        self.assertGreater(proof_token_count("exact Nat.add_zero n"), proof_token_count("rfl"))

    def test_package_tamper_detected(self):
        p = compile_run(run_obj(self.fake))
        p["selected_id"] = "BASELINE"
        with self.assertRaises(RefactorError):
            verify_result(p)

    def test_external_commitment_detects_rehash(self):
        p = compile_run(run_obj(self.fake))
        original = p["package_digest"]
        p["metric_notice"] += " tampered"
        rehash(p)
        with self.assertRaises(RefactorError):
            verify_result(p, expected_package_digest=original)

    def test_rehashed_token_tamper_detected_semantically(self):
        p = compile_run(run_obj(self.fake))
        p["observations"][1]["token_count"] += 1
        rehash(p)
        with self.assertRaises(RefactorError):
            verify_result(p)

    def test_rehashed_pareto_tamper_detected_semantically(self):
        p = compile_run(run_obj(self.fake))
        p["pareto_ids"] = ["BASELINE"]
        p["selected_id"] = "BASELINE"
        rehash(p)
        with self.assertRaises(RefactorError):
            verify_result(p)

    def test_rehashed_budget_tamper_detected_semantically(self):
        p = compile_run(run_obj(self.fake))
        p["budget"]["used_microusd"] += 1
        rehash(p)
        with self.assertRaises(RefactorError):
            verify_result(p)

    def test_rehashed_receipt_tamper_detected_semantically(self):
        p = compile_run(run_obj(self.fake))
        p["receipt"]["task_digest"] = "0" * 64
        rehash(p)
        with self.assertRaises(RefactorError):
            verify_result(p)

    def test_authority_ceiling(self):
        p = compile_run(run_obj(self.fake))
        self.assertEqual(p["authorities"], AUTHORITIES)
        self.assertTrue(all(v is False for v in p["authorities"].values()))

    def test_rehashed_authority_escalation_rejected(self):
        p = compile_run(run_obj(self.fake))
        p["authorities"]["competition_submission"] = True
        rehash(p)
        with self.assertRaises(RefactorError):
            verify_result(p)

    def test_verify_can_rerun_pass_vectors(self):
        p = compile_run(run_obj(self.fake))
        proof = verify_result(p, rerun_compilers=True)
        self.assertTrue(proof["compiler_pass_vector_rerun_match"])

    def test_result_serialization_is_canonical(self):
        p = compile_run(run_obj(self.fake))
        raw = result_bytes(p)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(load_json_bytes(raw), p)

    def test_input_candidate_order_normalizes(self):
        a = candidate("A", proof="rfl", cost=10)
        b = candidate("B", proof="exact rfl", cost=20)
        r1 = normalize_run(run_obj(self.fake, [a, b]))
        r2 = normalize_run(run_obj(self.fake, [b, a]))
        self.assertEqual(canonical_bytes(r1), canonical_bytes(r2))

    def test_toolchain_order_normalizes(self):
        r = run_obj(self.fake, transfers=2)
        r2 = copy.deepcopy(r)
        r2["toolchains"] = list(reversed(r2["toolchains"]))
        self.assertEqual(canonical_bytes(normalize_run(r)), canonical_bytes(normalize_run(r2)))

    def test_write_exclusive_refuses_overwrite(self):
        path = Path(self.tmp.name) / "result.json"
        write_exclusive(path, b"one")
        with self.assertRaises(FileExistsError):
            write_exclusive(path, b"two")
        self.assertEqual(path.read_bytes(), b"one")

    def test_write_exclusive_refuses_symlink(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unsupported")
        target = Path(self.tmp.name) / "target"
        target.write_bytes(b"keep")
        link = Path(self.tmp.name) / "link"
        try:
            os.symlink(target, link)
        except OSError:
            self.skipTest("symlink unavailable")
        with self.assertRaises(OSError):
            write_exclusive(link, b"replace")
        self.assertEqual(target.read_bytes(), b"keep")

    def test_unknown_task_field_rejected(self):
        r = run_obj(self.fake)
        r["task"]["notes"] = "not allowed"
        with self.assertRaises(RefactorError):
            compile_run(r)

    def test_proof_crlf_rejected(self):
        with self.assertRaises(RefactorError):
            compile_run(run_obj(self.fake, [candidate(proof="rfl\r\n")]))

    def test_model_cost_summary(self):
        cs = [candidate("A", proof="rfl", cost=100, model="m1"), candidate("B", proof="exact rfl", cost=200, model="m1")]
        p = compile_run(run_obj(self.fake, cs))
        self.assertEqual(p["budget"]["used_by_model_microusd"], {"m1": 300})


if __name__ == "__main__":
    unittest.main()

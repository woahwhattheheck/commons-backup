import copy
import importlib.util
import os
from pathlib import Path
import unittest

import proofpatch as pp


def rechain(bundle):
    prev = "0" * 64
    for index, receipt in enumerate(bundle["receipts"]):
        receipt["sequence"] = index
        receipt["prev_digest"] = prev
        body = {k: receipt[k] for k in receipt if k != "entry_digest"}
        receipt["entry_digest"] = pp.digest_json(body)
        prev = receipt["entry_digest"]
    body = {k: bundle[k] for k in bundle if k != "bundle_sha256"}
    bundle["bundle_sha256"] = pp.digest_json(body)
    return bundle


def fresh_core():
    """Load the core under a fresh module name so facade monkeypatching cannot mask it."""
    path = Path(__file__).with_name("_proofpatch_core.py")
    spec = importlib.util.spec_from_file_location("proofpatch_core_fresh_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to construct fresh core loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StatefulReceiptList(list):
    """The predecessor shape: a mutable/subclass view could expose A then B."""
    def __iter__(self):
        raise AssertionError("stateful receipt view must be rejected before iteration")


class StatefulBundle(dict):
    def items(self):
        raise AssertionError("stateful bundle view must be rejected before items()")


class SplitViewNebiusBody(dict):
    """Expose issued generation A on first serialization, generation B on second.

    Before request freezing, the first digest_json(body) could consume A and
    match an adapter-issued request digest while the later canonical_json(body)
    consumed B for external transport. The hardened boundary must reject this
    subclass before either serialization occurs.
    """
    def __init__(self, generation_a, generation_b):
        super().__init__(generation_a)
        self._generation_b = copy.deepcopy(generation_b)
        self.items_reads = 0

    def items(self):
        self.items_reads += 1
        source = self if self.items_reads == 1 else self._generation_b
        return dict.items(source)


class ProofPatchHardeningTests(unittest.TestCase):
    def test_patch_must_enumerate_every_snapshot_difference(self):
        baseline = pp.snapshot_from_files({"a.py": "a\n", "b.py": "b\n"})
        patched = pp.snapshot_from_files({"a.py": "aa\n", "b.py": "bb\n"})
        with self.assertRaises(pp.ProofError):
            pp.make_patch(baseline, patched, [{"path": "a.py", "before": "a\n", "after": "aa\n"}])

    def test_patch_may_not_hide_file_addition(self):
        baseline = pp.snapshot_from_files({"a.py": "a\n"})
        patched = pp.snapshot_from_files({"a.py": "aa\n", "hidden.py": "surprise\n"})
        with self.assertRaises(pp.ProofError):
            pp.make_patch(baseline, patched, [{"path": "a.py", "before": "a\n", "after": "aa\n"}])

    def test_focused_phase_must_rerun_original_reproduction(self):
        bundle = pp.demo_bundle()
        bundle["receipts"][1]["command"] = copy.deepcopy(bundle["task"]["regression"])
        rechain(bundle)
        with self.assertRaises(pp.ProofError):
            pp.verify_bundle(bundle)

    def test_adapter_rejects_mutated_inner_model_even_if_request_resealed(self):
        env_name = "PROOFPATCH_HARDENING_TEST_KEY"
        adapter = pp.NebiusTokenFactoryAdapter("nvidia/nemotron-pinned", api_key_env=env_name)
        task_sha = pp.verify_bundle(pp.demo_bundle())["task_digest"]
        request = adapter.build_request(task_sha, "synthetic", [])
        request["body"]["model"] = "nvidia/other-model"
        request["request_sha256"] = pp.digest_json(request["body"])
        os.environ[env_name] = "not-a-real-secret"
        called = []
        try:
            with self.assertRaises(pp.ProofError):
                adapter.execute(request, lambda *_: called.append(True) or b"no")
            self.assertEqual(called, [])
        finally:
            os.environ.pop(env_name, None)

    def test_adapter_rejects_mutated_messages_even_if_request_resealed(self):
        env_name = "PROOFPATCH_HARDENING_MESSAGE_KEY"
        adapter = pp.NebiusTokenFactoryAdapter("nvidia/nemotron-pinned", api_key_env=env_name)
        task_sha = pp.verify_bundle(pp.demo_bundle())["task_digest"]
        request = adapter.build_request(task_sha, "synthetic", [])
        request["body"]["messages"][1]["content"] = "caller replaced the issued prompt"
        request["request_sha256"] = pp.digest_json(request["body"])
        os.environ[env_name] = "not-a-real-secret"
        called = []
        try:
            with self.assertRaises(pp.ProofError):
                adapter.execute(request, lambda *_: called.append(True) or b"no")
            self.assertEqual(called, [])
        finally:
            os.environ.pop(env_name, None)

    def test_public_adapter_rejects_split_view_body_before_transport_or_serialization(self):
        env_name = "PROOFPATCH_SPLIT_VIEW_PUBLIC_KEY"
        adapter = pp.NebiusTokenFactoryAdapter("nvidia/nemotron-pinned", api_key_env=env_name)
        task_sha = pp.verify_bundle(pp.demo_bundle())["task_digest"]
        request = adapter.build_request(task_sha, "synthetic", [])
        canonical = copy.deepcopy(request["body"])
        alternate = copy.deepcopy(canonical)
        alternate["messages"][1]["content"] = "generation B escaped after issued digest"
        split_body = SplitViewNebiusBody(canonical, alternate)
        request["body"] = split_body
        os.environ[env_name] = "not-a-real-secret"
        called = []
        try:
            with self.assertRaises(pp.ProofError):
                adapter.execute(request, lambda *_: called.append(True) or b"no")
            self.assertEqual(called, [])
            self.assertEqual(split_body.items_reads, 0)
        finally:
            os.environ.pop(env_name, None)

    def test_fresh_core_adapter_rejects_split_view_body_before_transport_or_serialization(self):
        core = fresh_core()
        env_name = "PROOFPATCH_SPLIT_VIEW_CORE_KEY"
        adapter = core.NebiusTokenFactoryAdapter("nvidia/nemotron-pinned", api_key_env=env_name)
        task_sha = core.verify_bundle(core.demo_bundle())["task_digest"]
        request = adapter.build_request(task_sha, "synthetic", [])
        canonical = copy.deepcopy(request["body"])
        alternate = copy.deepcopy(canonical)
        alternate["model"] = "nvidia/generation-b"
        split_body = SplitViewNebiusBody(canonical, alternate)
        request["body"] = split_body
        os.environ[env_name] = "not-a-real-secret"
        called = []
        try:
            with self.assertRaises(core.ProofError):
                adapter.execute(request, lambda *_: called.append(True) or b"no")
            self.assertEqual(called, [])
            self.assertEqual(split_body.items_reads, 0)
        finally:
            os.environ.pop(env_name, None)

    def test_hardened_demo_structural_and_executor_states_are_distinct(self):
        structural = pp.verify_bundle(pp.demo_bundle())
        replayed = pp.verify_demo_bundle(pp.demo_bundle())
        self.assertEqual(structural["status"], "STRUCTURAL_EVIDENCE_VERIFIED")
        self.assertEqual(replayed["status"], "EXECUTOR_REPLAY_VERIFIED")
        self.assertFalse(structural["executor_replay_verified"])
        self.assertTrue(replayed["executor_replay_verified"])

    def test_stateful_receipt_list_is_rejected_before_structural_or_replay_read(self):
        bundle = pp.demo_bundle()
        bundle["receipts"] = StatefulReceiptList(bundle["receipts"])
        called = []

        class Executor:
            def run(self, *_):
                called.append(True)
                return {"exit_code": 0, "stdout": "", "stderr": "", "timed_out": False}

        with self.assertRaises(pp.ProofError):
            pp.verify_with_executor(bundle, Executor(), "stateful-list-hostile")
        self.assertEqual(called, [])

    def test_stateful_top_level_mapping_is_rejected_before_first_items_read(self):
        with self.assertRaises(pp.ProofError):
            pp.verify_with_executor(StatefulBundle(pp.demo_bundle()), pp.demo_executor(), "stateful-map-hostile")

    def test_fresh_direct_core_import_cannot_resurrect_local_proof_or_split_view(self):
        core = fresh_core()
        bundle = core.demo_bundle()
        structural = core.verify_bundle(bundle)
        replayed = core.verify_demo_bundle(bundle)
        self.assertEqual(structural["status"], "STRUCTURAL_EVIDENCE_VERIFIED")
        self.assertEqual(structural["receipt_provenance"], "CALLER_AUTHORED_UNAUTHENTICATED")
        self.assertFalse(structural["executor_replay_verified"])
        self.assertEqual(replayed["status"], "EXECUTOR_REPLAY_VERIFIED")
        self.assertTrue(replayed["executor_replay_verified"])
        hostile = core.demo_bundle()
        hostile["receipts"] = type("CoreStatefulList", (list,), {})(hostile["receipts"])
        with self.assertRaises(core.ProofError):
            core.verify_with_executor(hostile, core.demo_executor(), "fresh-core-stateful-hostile")


if __name__ == "__main__":
    unittest.main()

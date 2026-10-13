"""Independent synthetic acceptance checks; no service or live data is used."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "acceptance_lab.py"
LEGACY = HERE.parent / "wayne-smart-api"
LEGACY_BLOBS = {
    "README.md": "b0a97dc81cec99447d91c882981ac4622320fde8",
    "fixtures/manifest.json": "69848b1b1110b5d8a26322664dcbbebb1c461622",
    "fixtures/wayne_150_states.json": "20987615a5fba3639ca0df0eccb79f86b4c63e3b",
    "test_wayne_smart_reconcile.py": "13dd744de4afaac236b2cbe473d94c0f40276eaa",
    "wayne_smart_reconcile.py": "ec605f8c8d42b625da995a1b09ec52b01b495d41",
}


def load_module():
    spec = importlib.util.spec_from_file_location("_wayne_lab_test_" + uuid.uuid4().hex, MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load acceptance lab")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lab = load_module()


def independent_digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class AcceptanceLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = lab.load_baseline()
        cls.records = cls.baseline["records"]

    def event(self, kind, event_id, at_ms=0, key="SYNTH-A", **claims):
        return {"event_id": event_id, "at_ms": at_ms, "type": kind, "key": key, **claims}

    def submit(self, event_id="submit-a", index=0, key="SYNTH-A", at_ms=0, **changes):
        record = self.records[index]
        result = self.event("SUBMIT", event_id, at_ms, key, record_id=record["record_id"],
                            payload_sha256=lab.request_sha256(record))
        result.update(changes)
        return result

    def observe(self, event_id="observe-a", index=0, key="SYNTH-A", at_ms=0,
                observation="COMMITTED", evidence_id="SYNTH-OBS-A", **changes):
        record = self.records[index]
        result = self.event("OBSERVE", event_id, at_ms, key, record_id=record["record_id"],
                            payload_sha256=lab.request_sha256(record), commit_id=record["commit_id"],
                            observation=observation,
                            posted_cents=record["expected_cents"] if observation == "COMMITTED" else None,
                            evidence_id=evidence_id)
        result.update(changes)
        return result

    def document(self, *events, profile=None):
        return {"schema": lab.SCHEMA, "synthetic_only": True,
                "profile": dict(profile or lab.DEFAULT_PROFILE), "events": list(events)}

    def committed_document(self):
        return self.document(self.submit(), self.event("DISPATCH", "dispatch-a"), self.observe())

    def test_frozen_baseline_has_exact_truth_and_no_replay_effects(self):
        baseline = self.baseline["baseline"]
        self.assertEqual(len(self.records), 150)
        self.assertEqual(baseline["statuses"], {"RECONCILED": 120, "DUPLICATE_NOOP": 10,
                         "HOLD_UNKNOWN_COMMIT": 10, "HOLD_UNAUTHORIZED": 10})
        for name in ("ledger_variance_cents", "duplicate_mutation_effects", "unauthorized_reads", "authoritative_writes"):
            self.assertEqual(baseline[name], 0, name)
        self.assertEqual(baseline["replay"], {"idempotent": 150, "staged_effects_added": 0,
                         "holds_added": 0, "events_added": 0, "protected_reads_added": 0,
                         "state_unchanged": True})

    def test_success_requires_dispatch_and_bound_commit_observation(self):
        document = self.committed_document()
        original = copy.deepcopy(document)
        report = lab.run_transcript(document)
        self.assertEqual([row["result"] for row in report["events"]], ["READY", "IN_FLIGHT", "COMMITTED"])
        operation = report["operations"][0]
        self.assertEqual((operation["state"], operation["attempts"], operation["accepted_observations"]), ("COMMITTED", 1, 1))
        self.assertEqual(operation["posted_cents"], self.records[0]["expected_cents"])
        self.assertEqual(report["summary"]["disposition"], "SIMULATION_RECONCILED")
        self.assertEqual(report["authority"], {"buyer_approved": False, "production_ready": False,
                         "endpoint_contacted": False, "authoritative_writes": 0,
                         "submission_authorized": False, "payment_authorized": False})
        self.assertEqual(document, original)
        report_without_receipt = copy.deepcopy(report)
        receipt = report_without_receipt.pop("receipt_sha256")
        self.assertEqual(receipt, independent_digest({"domain": lab.REPORT_SCHEMA, "report": report_without_receipt}))

    def test_observation_before_dispatch_cannot_commit(self):
        report = lab.run_transcript(self.document(self.submit(), self.observe()))
        self.assertEqual(report["events"][-1]["result"], "HOLD_INVALID_TRANSITION")
        self.assertEqual((report["operations"][0]["state"], report["summary"]["logical_attempts"],
                          report["summary"]["accepted_commit_observations"]), ("READY", 0, 0))

    def test_ack_loss_blocks_resend_until_bound_observation_and_preserves_history(self):
        document = self.document(self.submit(), self.event("DISPATCH", "dispatch-a"),
                    self.event("ACK_LOST", "lost-a", dispatch_event_id="dispatch-a"),
                    self.submit("alias", index=120), self.event("DISPATCH", "blocked", 10000),
                    self.observe("resolution", at_ms=10000))
        report = lab.run_transcript(document)
        self.assertEqual([row["result"] for row in report["events"]],
                         ["READY", "IN_FLIGHT", "HOLD_UNKNOWN_COMMIT", "DUPLICATE_NOOP", "HOLD_UNKNOWN_COMMIT", "COMMITTED"])
        self.assertEqual(report["operations"][0]["attempts"], 1)
        self.assertEqual(report["summary"]["unresolved_keys"], [])
        self.assertEqual(report["summary"]["hold_event_ids"], ["lost-a", "blocked"])
        self.assertEqual(report["summary"]["disposition"], "HOLD_REVIEW_REQUIRED")

    def test_unknown_and_not_committed_observations_do_not_grant_retry(self):
        for observation, state in (("UNKNOWN", "HOLD_UNKNOWN_COMMIT"),
                                   ("NOT_COMMITTED", "HOLD_NOT_COMMITTED_REVIEW")):
            with self.subTest(observation=observation):
                report = lab.run_transcript(self.document(self.submit(), self.event("DISPATCH", "dispatch-a"),
                                            self.observe(observation=observation), self.event("DISPATCH", "again", 99999)))
                self.assertEqual(report["operations"][0]["state"], state)
                self.assertEqual(report["operations"][0]["attempts"], 1)
                self.assertEqual(report["summary"]["accepted_commit_observations"], 0)

    def test_retry_due_boundaries_cap_and_budget_are_exact(self):
        profile = {**lab.DEFAULT_PROFILE, "max_attempts": 3, "backoff_base_ms": 100, "backoff_cap_ms": 150}
        events = [self.submit(), self.event("DISPATCH", "d1"),
                  self.event("NOT_SENT", "n1", dispatch_event_id="d1"),
                  self.submit("alias", index=120, at_ms=50), self.event("DISPATCH", "early1", 99),
                  self.event("DISPATCH", "d2", 100), self.event("NOT_SENT", "n2", 100, dispatch_event_id="d2"),
                  self.event("DISPATCH", "early2", 249), self.event("DISPATCH", "d3", 250),
                  self.event("NOT_SENT", "n3", 250, dispatch_event_id="d3"), self.event("DISPATCH", "exhausted", 99999)]
        report = lab.run_transcript(self.document(*events, profile=profile))
        self.assertEqual([row["result"] for row in report["events"]], ["READY", "IN_FLIGHT", "RETRY_WAIT", "DUPLICATE_NOOP",
                         "RETRY_NOT_DUE", "IN_FLIGHT", "RETRY_WAIT", "RETRY_NOT_DUE", "IN_FLIGHT", "HOLD_RETRY_EXHAUSTED", "HOLD_INVALID_TRANSITION"])
        self.assertEqual(report["events"][2]["retry_at_ms"], 100)
        self.assertEqual(report["events"][6]["retry_at_ms"], 250)
        self.assertEqual([row["attempts"] for row in report["events"]], [0, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3])
        self.assertEqual(report["operations"][0]["state"], "HOLD_RETRY_EXHAUSTED")

    def test_stale_outcomes_cannot_resolve_or_retry_a_new_dispatch(self):
        for kind in ("NOT_SENT", "ACK_LOST"):
            with self.subTest(kind=kind):
                report = lab.run_transcript(self.document(self.submit(), self.event("DISPATCH", "d1"),
                            self.event("NOT_SENT", "n1", dispatch_event_id="d1"),
                            self.event("DISPATCH", "d2", 100),
                            self.event(kind, "stale", 100, dispatch_event_id="d1")))
                self.assertEqual(report["events"][-1]["result"], "HOLD_STALE_ATTEMPT")
                operation = report["operations"][0]
                self.assertEqual((operation["state"], operation["attempts"], operation["retry_at_ms"],
                                  operation["active_dispatch_event_id"]), ("IN_FLIGHT", 2, None, "d2"))

    def test_request_identity_aliases_and_payload_conflicts_do_not_create_extra_operations(self):
        self.assertEqual(lab.request_sha256(self.records[0]), lab.request_sha256(self.records[120]))
        report = lab.run_transcript(self.document(self.submit(), self.submit("alias", index=120),
                    self.submit("key-conflict", index=1), self.submit("mutation-conflict", index=120, key="SYNTH-B"),
                    self.submit("payload-conflict", index=1, key="SYNTH-C", payload_sha256="0" * 64)))
        self.assertEqual([row["result"] for row in report["events"]], ["READY", "DUPLICATE_NOOP", "HOLD_KEY_PAYLOAD_CONFLICT",
                         "HOLD_MUTATION_KEY_CONFLICT", "HOLD_PAYLOAD_MISMATCH"])
        self.assertEqual(len(report["operations"]), 1)
        self.assertEqual(report["operations"][0]["record_id"], self.records[0]["record_id"])
        self.assertEqual(report["summary"]["logical_attempts"], 0)

    def test_original_baseline_hold_categories_cannot_dispatch(self):
        for index, baseline_status in ((120, "DUPLICATE_NOOP"), (130, "HOLD_UNKNOWN_COMMIT"), (140, "HOLD_UNAUTHORIZED")):
            with self.subTest(baseline_status=baseline_status):
                report = lab.run_transcript(self.document(self.submit(index=index), self.event("DISPATCH", "dispatch-a")))
                operation = report["operations"][0]
                self.assertEqual((operation["baseline_status"], operation["state"], operation["attempts"]),
                                 (baseline_status, "HOLD_BASELINE_STATUS", 0))

    def test_observation_must_bind_record_payload_and_commit(self):
        for field, value in (("record_id", self.records[1]["record_id"]),
                             ("payload_sha256", "e" * 64), ("commit_id", "SMART-WRONG-COMMIT")):
            with self.subTest(field=field):
                report = lab.run_transcript(self.document(self.submit(), self.event("DISPATCH", "dispatch-a"),
                                            self.observe(**{field: value})))
                self.assertEqual(report["events"][-1]["result"], "HOLD_OBSERVATION_BINDING")
                operation = report["operations"][0]
                self.assertEqual((operation["state"], operation["posted_cents"], operation["accepted_observations"]),
                                 ("IN_FLIGHT", None, 0))

    def test_duplicate_and_conflicting_observation_claims_cannot_replace_committed_cents(self):
        report = lab.run_transcript(self.document(self.submit(), self.event("DISPATCH", "dispatch-a"), self.observe(),
                    self.observe("duplicate"), self.observe("conflict", posted_cents=self.records[0]["expected_cents"] + 1)))
        self.assertEqual([row["result"] for row in report["events"]][-2:], ["DUPLICATE_NOOP", "HOLD_EVIDENCE_CONFLICT"])
        operation = report["operations"][0]
        self.assertEqual((operation["state"], operation["posted_cents"], operation["accepted_observations"]),
                         ("COMMITTED", self.records[0]["expected_cents"], 1))

    def test_evidence_identity_is_global_across_operation_keys(self):
        report = lab.run_transcript(self.document(self.submit(), self.event("DISPATCH", "dispatch-a"), self.observe(),
                    self.submit("submit-b", index=1, key="SYNTH-B"), self.event("DISPATCH", "dispatch-b", key="SYNTH-B"),
                    self.observe("reused", index=1, key="SYNTH-B"),
                    self.observe("fresh", index=1, key="SYNTH-B", evidence_id="SYNTH-OBS-B")))
        self.assertEqual(report["events"][-2]["result"], "HOLD_EVIDENCE_CONFLICT")
        self.assertEqual(report["events"][-2]["state_after"], "IN_FLIGHT")
        self.assertEqual(report["events"][-1]["result"], "COMMITTED")
        self.assertEqual(report["summary"]["accepted_commit_observations"], 2)

    def test_offsetting_ledger_variances_remain_two_unresolved_holds(self):
        report = lab.run_transcript(self.document(self.submit(), self.event("DISPATCH", "dispatch-a"),
                    self.observe(posted_cents=self.records[0]["expected_cents"] + 1),
                    self.submit("submit-b", index=1, key="SYNTH-B"), self.event("DISPATCH", "dispatch-b", key="SYNTH-B"),
                    self.observe("observe-b", index=1, key="SYNTH-B", evidence_id="SYNTH-OBS-B",
                                 posted_cents=self.records[1]["expected_cents"] - 1)))
        self.assertEqual([row["variance_cents"] for row in report["operations"]], [1, -1])
        self.assertEqual([row["state"] for row in report["operations"]], ["HOLD_LEDGER_VARIANCE"] * 2)
        self.assertEqual(report["summary"]["observed_variance_cents"], 0)
        self.assertEqual(report["summary"]["nonzero_variance_operations"], 2)
        self.assertEqual(report["summary"]["accepted_commit_observations"], 0)
        self.assertEqual(report["summary"]["unresolved_keys"], ["SYNTH-A", "SYNTH-B"])
        self.assertEqual(report["summary"]["disposition"], "HOLD_REVIEW_REQUIRED")

    def test_replay_is_deterministic_and_rehashed_semantic_changes_are_rejected(self):
        document = self.committed_document()
        report = lab.run_transcript(document)
        self.assertEqual(lab.run_transcript(copy.deepcopy(document)), report)
        self.assertTrue(lab.verify_report(report, document))
        changes = [lambda out: out["summary"].__setitem__("accepted_commit_observations", 2),
                   lambda out: out["operations"][0].__setitem__("attempts", 2),
                   lambda out: out["authority"].__setitem__("buyer_approved", True),
                   lambda out: out["source_bindings"][0].__setitem__("sha256", "0" * 64)]
        for change in changes:
            altered = copy.deepcopy(report)
            change(altered)
            altered.pop("receipt_sha256")
            altered["receipt_sha256"] = independent_digest({"domain": lab.REPORT_SCHEMA, "report": altered})
            with self.assertRaises(lab.LabError):
                lab.verify_report(altered, document)
        other = copy.deepcopy(document)
        other["events"][0]["event_id"] = "different-source-event"
        with self.assertRaises(lab.LabError):
            lab.verify_report(report, other)

    def test_changed_or_missing_pinned_sources_are_refused_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / "baseline"
            shutil.copytree(LEGACY, copied)
            self.assertEqual(lab.load_baseline(copied), self.baseline)
            for name in lab.CORE_HASHES:
                path = copied / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                with self.subTest(source=name), self.assertRaisesRegex(lab.LabError, "source binding changed"):
                    lab.load_baseline(copied)
                path.write_bytes(original)
            (copied / "fixtures/manifest.json").unlink()
            with self.assertRaisesRegex(lab.LabError, "unavailable"):
                lab.load_baseline(copied)

    def test_malformed_json_is_a_controlled_lab_error(self):
        samples = [b'{"a":1,"a":2}', b'{"a":1,"\\u0061":2}', b'{"a":NaN}', b'{"a":Infinity}',
                   b'{"a":1e400}', b'{"a":"\xff"}', b'\xef\xbb\xbf{}', b'{"a":',
                   b'{"a":"\\ud800"}', b'{"\\udfff":1}', b'{}' + b' ' * lab.MAX_BYTES]
        for raw in samples:
            with self.subTest(raw=raw[:40]), self.assertRaises(lab.LabError):
                lab.strict_json_bytes(raw)
        self.assertEqual(lab.strict_json_bytes('{"scalar":"café 🚀 �"}'.encode()), {"scalar": "café 🚀 �"})
        limit = sys.get_int_max_str_digits()
        if limit:
            with self.assertRaises(lab.LabError):
                lab.strict_json_bytes(b'{"integer":' + b'9' * (limit + 1) + b'}')

    def test_malformed_transcripts_reject_types_shapes_times_and_non_synthetic_claims(self):
        changes = [lambda doc: doc.__setitem__("synthetic_only", False),
                   lambda doc: doc.__setitem__("schema", "unknown"),
                   lambda doc: doc.__setitem__("events", []),
                   lambda doc: doc["profile"].__setitem__("max_attempts", True),
                   lambda doc: doc["profile"].__setitem__("backoff_cap_ms", 1),
                   lambda doc: doc["events"][0].__setitem__("at_ms", True),
                   lambda doc: doc["events"][0].__setitem__("key", "LIVE-A"),
                   lambda doc: doc["events"][0].__setitem__("record_id", "UNKNOWN-RECORD"),
                   lambda doc: doc["events"][0].__setitem__("unexpected", 1),
                   lambda doc: doc["events"][1].__setitem__("event_id", doc["events"][0]["event_id"]),
                   lambda doc: doc["events"][0].__setitem__("at_ms", 1),
                   lambda doc: doc["events"][2].__setitem__("posted_cents", True),
                   lambda doc: doc["events"][2].__setitem__("evidence_id", "LIVE-OBSERVATION")]
        for number, change in enumerate(changes):
            document = self.committed_document()
            change(document)
            with self.subTest(case=number), self.assertRaises(lab.LabError):
                lab.run_transcript(document)
        missing_reference = self.document(self.submit(), self.event("DISPATCH", "dispatch-a"), self.event("ACK_LOST", "lost"))
        with self.assertRaises(lab.LabError):
            lab.run_transcript(missing_reference)

    def test_import_and_baseline_execution_do_not_leak_paths_or_custom_modules(self):
        before_path = sys.path[:]
        before_modules = set(sys.modules)
        sentinel = object()
        with mock.patch.dict(sys.modules, {"wayne_smart_reconcile": sentinel}):
            fresh = load_module()
            fresh.load_baseline()
            self.assertIs(sys.modules["wayne_smart_reconcile"], sentinel)
        self.assertEqual(sys.path, before_path)
        self.assertEqual({name for name in sys.modules if name.startswith(("_wayne_captured_", "_wayne_lab_test_"))},
                         {name for name in before_modules if name.startswith(("_wayne_captured_", "_wayne_lab_test_"))})

    def test_replay_and_verification_do_not_open_network_connections(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("offline lab opened a socket")):
            report = lab.run_transcript(self.committed_document())
            self.assertTrue(lab.verify_report(report, self.committed_document()))

    def test_legacy_five_files_remain_byte_identical(self):
        for name, expected in LEGACY_BLOBS.items():
            raw = (LEGACY / name).read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            self.assertEqual(actual, expected, name)

    def test_markdown_preserves_complete_event_claims_and_all_operations(self):
        document = self.document(self.submit(), self.event("DISPATCH", "dispatch-a"),
                    self.observe("wrong-commit", commit_id="SMART-WRONG-COMMIT", payload_sha256="a" * 64),
                    self.observe("unknown", observation="UNKNOWN", evidence_id="SYNTH-UNKNOWN"),
                    self.observe("not-committed", observation="NOT_COMMITTED", evidence_id="SYNTH-NOT-COMMITTED"))
        report = lab.run_transcript(document)
        markdown = lab.render_markdown(report)
        blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", markdown, re.DOTALL)]
        self.assertIn(document["events"], blocks, "Markdown must retain exact supplied event claims")
        for row in report["events"]:
            self.assertIn("| " + row["event"]["event_id"] + " |", markdown)
            self.assertIn(row["result"], markdown)
        for operation in report["operations"]:
            self.assertIn("| " + operation["key"] + " | " + operation["record_id"] + " | " + operation["state"] + " |", markdown)
        self.assertIn(report["receipt_sha256"], markdown)
        self.assertIn(report["transcript_sha256"], markdown)
        self.assertIn({"profile": report["profile"], "summary": report["summary"]}, blocks)

    def test_cli_bundle_matches_json_markdown_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "input.json"
            document = self.committed_document()
            transcript.write_text(json.dumps(document), encoding="utf-8")
            output = root / "new-output"
            prefix = [sys.executable, "-B"] + (["-O"] if sys.flags.optimize else []) + [str(MODULE_PATH), str(transcript)]
            run = subprocess.run(prefix + ["--out", str(output)], cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual({path.name for path in output.iterdir()}, {"transcript.json", "report.json", "report.md"})
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report, lab.run_transcript(document))
            self.assertEqual(json.loads((output / "transcript.json").read_text(encoding="utf-8")), document)
            self.assertEqual((output / "report.md").read_text(encoding="utf-8"), lab.render_markdown(report))
            self.assertEqual(json.loads(run.stdout)["receipt_sha256"], report["receipt_sha256"])
            before = {path.name: path.read_bytes() for path in output.iterdir()}
            refused = subprocess.run(prefix + ["--out", str(output)], cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(refused.returncode, 2)
            self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, before)
            verified = subprocess.run(prefix + ["--verify", str(output / "report.json")], cwd=root,
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual((verified.returncode, verified.stdout.strip()), (0, "OFFLINE_REPLAY_VERIFIED"), verified.stderr)
            report["operations"][0]["attempts"] = 2
            altered = root / "altered-report.json"
            altered.write_text(json.dumps(report), encoding="utf-8")
            rejected = subprocess.run(prefix + ["--verify", str(altered)], cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(rejected.returncode, 2)
            self.assertNotIn("OFFLINE_REPLAY_VERIFIED", rejected.stdout)

    def test_invalid_bundle_does_not_create_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "absent"
            document = self.committed_document()
            document["synthetic_only"] = False
            with self.assertRaises(lab.LabError):
                lab.write_bundle(document, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

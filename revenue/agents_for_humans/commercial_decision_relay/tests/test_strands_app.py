from __future__ import annotations

import importlib.metadata
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from decision_relay import DecisionRelayError, RelayEngine


HAS_STRANDS = importlib.util.find_spec("strands") is not None
FIXTURE = Path(__file__).parents[1] / "fixtures" / "demo-batch.json"
TRUSTED_TIME = "2026-09-13T12:00:00Z"


@unittest.skipUnless(HAS_STRANDS, "pinned strands-agents SDK is not installed")
class StrandsSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from decision_relay.strands_app import AuditHooks, RelayToolbox

        cls.AuditHooks = AuditHooks
        cls.RelayToolbox = RelayToolbox

    def batch(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_exact_sdk_version(self):
        self.assertEqual(importlib.metadata.version("strands-agents"), "1.55.1")

    def test_decorated_tool_ingest_reconcile_queue_smoke(self):
        toolbox = self.RelayToolbox(
            RelayEngine(),
            trusted_evaluated_at=TRUSTED_TIME,
        )
        ingested = json.loads(toolbox.ingest_batch(json.dumps(self.batch())))
        reconciled = json.loads(toolbox.reconcile_evidence())
        decisions = json.loads(toolbox.decision_queue())

        self.assertEqual(ingested["event_count"], 7)
        self.assertEqual(reconciled["summary"]["decision_count"], 2)
        self.assertEqual(
            [row["series_id"] for row in decisions],
            ["alpha-renewal", "beta-pilot"],
        )

    def test_production_builder_rejects_model_controlled_evidence_ingress(self):
        from decision_relay.strands_app import build_agent

        with self.assertRaises(DecisionRelayError) as ctx:
            build_agent(
                model=object(),
                evaluated_at=TRUSTED_TIME,
                batch=None,
            )
        self.assertEqual(ctx.exception.code, "trusted_batch_required")

    def test_production_builder_rejects_missing_trusted_time(self):
        from decision_relay.strands_app import build_agent

        with self.assertRaises(DecisionRelayError) as ctx:
            build_agent(
                model=object(),
                batch=self.batch(),
                evaluated_at=None,
            )
        self.assertEqual(ctx.exception.code, "trusted_time_required")

    def test_trusted_preload_cannot_be_replaced_by_model_tool_input(self):
        engine = RelayEngine()
        engine.ingest(self.batch())
        engine.reconcile(evaluated_at=TRUSTED_TIME)
        toolbox = self.RelayToolbox(
            engine,
            trusted_evaluated_at=TRUSTED_TIME,
            ingest_locked=True,
        )
        with self.assertRaises(DecisionRelayError) as ctx:
            toolbox.ingest_batch(json.dumps(self.batch()))
        self.assertEqual(ctx.exception.code, "preloaded_batch_locked")

    def test_after_hook_marks_sdk_exception_as_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            hooks = self.AuditHooks(path)
            hooks.after_tool(SimpleNamespace(
                tool_use={"name": "decision_queue"},
                result=object(),
                exception=RuntimeError("boom"),
                cancel_message=None,
                duration=0.125,
            ))
            row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertFalse(row["ok"])
        self.assertFalse(row["cancelled"])
        self.assertEqual(row["exception_type"], "RuntimeError")

    def test_after_hook_marks_sdk_cancellation_as_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            hooks = self.AuditHooks(path)
            hooks.after_tool(SimpleNamespace(
                tool_use={"name": "ingest_batch"},
                result=object(),
                exception=None,
                cancel_message="blocked by before hook",
                duration=None,
            ))
            row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertFalse(row["ok"])
        self.assertTrue(row["cancelled"])
        self.assertIsNone(row["exception_type"])


if __name__ == "__main__":
    unittest.main()

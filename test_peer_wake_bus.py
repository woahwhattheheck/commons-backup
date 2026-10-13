#!/usr/bin/env python3
"""Peer wake bus: open registration, explicit capability states, no live wake."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from independent_commons_mcp.jobs import JobStore
from peer_wake.bus import (
    SCHEMA,
    accept_event,
    attach_watchdog,
    cancel_event,
    dispatch_delivery,
    doctor,
    load_targets,
    register_target,
    tick,
    validate_target,
)
from peer_wake.adapters import poll as poll_adapter
from peer_wake.adapters import slack_mention as slack_adapter
from peer_wake.adapters import slack_table_tip as tip_adapter
from harness_wake.watchdog import run as watchdog_run

sys.path.insert(0, str(Path(__file__).resolve().parent / "host"))
import peer_wake_bus as host_instrument


ROOT = Path(__file__).resolve().parent
SECRET = ('xoxb' + '-1234567890-secret-token-value')
JOB_ID = "peer-wake-bus-job-20260828-01"


def job_fields(**extra):
    data = {
        "job_id": JOB_ID,
        "owner_claim": "CHATGPT",
        "harness": "CHATGPT",
        "objective": "bounded peer-wake bus canary",
        "checkpoint": {"step": 0},
        "next_wake_at": "2026-08-28T12:00:00Z",
        "deadline": "2026-08-28T18:00:00Z",
        "max_attempts": 4,
        "budget_tokens": 50,
        "backoff_seconds": 60,
        "lease_seconds": 30,
        "completion_predicate": {"type": "checkpoint_equals", "path": "step", "value": 2},
        "result_address": "peer-wake-bus-result-20260828-01",
    }
    data.update(extra)
    return data


class PeerWakeBusTest(unittest.TestCase):
    def test_shipped_targets_are_code_ready_and_chatgpt_claude_are_external(self):
        report = doctor(root=ROOT, env={})
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["code"], "CODE_READY")
        self.assertFalse(report["live_wake"])
        self.assertFalse(report["secrets_in_config"])
        self.assertTrue(report["no_auth"])
        self.assertTrue(report["no_gate"])
        self.assertFalse(report["central_admission_list"])
        self.assertTrue(report["unique_events_never_cancelled"])
        self.assertTrue(report["stable_job_id"])
        self.assertEqual(report["process_model_invocations"], 0)
        peers = {row["peer"]: row for row in report["targets"]}
        self.assertEqual(peers["CHATGPT"]["doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertEqual(peers["CLAUDE"]["doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertEqual(peers["CHATGPT"]["code"], "CODE_READY")
        self.assertEqual(peers["CLAUDE"]["code"], "CODE_READY")
        self.assertEqual(peers["GROK_SLACK"]["doorbell"], "SIBLING_IN_PROGRESS")
        self.assertEqual(peers["GEMINI_SLACK"]["doorbell"], "SIBLING_IN_PROGRESS")
        self.assertEqual(peers["GROK_SLACK"]["runtime"], "RUNTIME_UNCONFIGURED")
        self.assertIn("ping/chatgpt.md", report["reused"])
        self.assertIn("integrations/grok_slack/", report["reused"])
        blob = json.dumps(report)
        self.assertNotIn("xoxb", blob.lower())
        self.assertNotIn("xapp", blob.lower())

    def test_register_has_no_admission_list_and_obeys_merge_law(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "peer_wake" / "targets").mkdir(parents=True)
            payload = {
                "schema": SCHEMA,
                "peer": "NEWPEER",
                "adapter": "poll",
                "doorbell": "EXTERNAL_PLATFORM_ACTION",
                "wake_target": {"kind": "poll", "path": "ping/last.json"},
            }
            first = register_target(payload, root=root)
            self.assertEqual(first["state"], "REGISTERED")
            second = register_target(payload, root=root)
            self.assertEqual(second["state"], "DEDUPE")
            composed = register_target(
                {
                    **payload,
                    "aliases": ["NEWPEER"],
                    "cite": ["example-cite"],
                },
                root=root,
            )
            self.assertEqual(composed["state"], "COMPOSE")
            conflict = register_target(
                {**payload, "adapter": "slack_mention"},
                root=root,
            )
            self.assertEqual(conflict["state"], "CONFLICT")
            self.assertFalse(conflict["ok"])
            names = [row["peer"] for row in load_targets(root)]
            self.assertEqual(names, ["NEWPEER"])

    def test_register_refuses_tokens(self):
        checked = validate_target({
            "schema": SCHEMA,
            "peer": "NEWPEER",
            "adapter": "poll",
            "doorbell": "EXTERNAL_PLATFORM_ACTION",
            "wake_target": {"kind": "poll", "token": SECRET},
        })
        self.assertEqual(checked["state"], "SECRET_REFUSED")

    def test_poll_adapter_never_live_wakes_even_on_deliver(self):
        target = next(row for row in load_targets(ROOT) if row["peer"] == "CHATGPT")
        receipt = poll_adapter.signal(target, job_fields(), deliver=True, http=lambda *_a, **_k: self.fail("poll must not network"))
        self.assertEqual(receipt["state"], "POLL_ONLY")
        self.assertEqual(receipt["doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertFalse(receipt["live_wake"])
        self.assertEqual(receipt["network_calls"], 0)
        self.assertFalse(receipt["invoke_model"])

    def test_slack_missing_credentials_are_runtime_unconfigured_with_zero_network(self):
        target = {
            "peer": "CUSTOM",
            "adapter": "slack_mention",
            "doorbell": "RUNTIME_READY",
            "wake_target": {"kind": "slack_mention", "channel": "C0BRGMDQB6G"},
            "secrets_env": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"],
        }
        calls = []
        receipt = slack_adapter.signal(
            target,
            job_fields(owner_claim="CUSTOM", harness="CUSTOM"),
            deliver=True,
            env={},
            http=lambda payload: calls.append(payload) or {"state": "MAIL", "status": 200},
        )
        self.assertEqual(receipt["state"], "RUNTIME_UNCONFIGURED")
        self.assertEqual(receipt["credential_presence"]["SLACK_BOT_TOKEN"], "missing")
        self.assertEqual(receipt["network_calls"], 0)
        self.assertFalse(receipt["live_wake"])
        self.assertEqual(calls, [])
        blob = json.dumps(receipt)
        self.assertNotIn("xoxb", blob.lower())

    def test_slack_present_credentials_still_do_not_doorbell_chatgpt(self):
        target = next(row for row in load_targets(ROOT) if row["peer"] == "CHATGPT")
        # ChatGPT is poll, but a slack-shaped doorbell stays EXTERNAL.
        slack_target = {
            "peer": "CHATGPT",
            "adapter": "slack_mention",
            "doorbell": "EXTERNAL_PLATFORM_ACTION",
            "wake_target": {"kind": "slack_mention", "channel": "C0BRGMDQB6G"},
            "secrets_env": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"],
        }
        calls = []
        receipt = slack_adapter.signal(
            slack_target,
            job_fields(),
            deliver=True,
            env={"SLACK_BOT_TOKEN": SECRET, "SLACK_APP_TOKEN": "xapp-secret"},
            http=lambda payload: calls.append(payload) or {"state": "MAIL", "status": 200},
        )
        self.assertEqual(receipt["state"], "EXTERNAL_PLATFORM_ACTION")
        self.assertFalse(receipt["live_wake"])
        self.assertEqual(receipt["network_calls"], 0)
        self.assertEqual(calls, [])
        blob = json.dumps(receipt)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("xapp-secret", blob)
        self.assertEqual(target["doorbell"], "EXTERNAL_PLATFORM_ACTION")

    def test_injected_transport_can_mail_only_when_platform_accepts_wake(self):
        calls = []
        receipt = slack_adapter.signal(
            {
                "peer": "CUSTOM",
                "adapter": "slack_mention",
                "doorbell": "RUNTIME_READY",
                "wake_target": {"kind": "slack_mention", "channel": "C0BRGMDQB6G"},
            },
            job_fields(owner_claim="CUSTOM", harness="CUSTOM"),
            deliver=True,
            env={"SLACK_BOT_TOKEN": "present-token", "SLACK_APP_TOKEN": "present-app"},
            http=lambda payload: calls.append(payload) or {"state": "MAILED", "status": 200},
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(receipt["state"], "MAILED")
        self.assertFalse(receipt["live_wake"])
        self.assertNotIn("present-token", json.dumps(receipt))

    def test_unique_events_are_accepted_and_never_cancelled(self):
        first = accept_event("Ev-peer-wake-1", {"job_id": JOB_ID})
        replay = accept_event("Ev-peer-wake-1", {"job_id": JOB_ID})
        refused = cancel_event("Ev-peer-wake-1")
        self.assertEqual(first["state"], "ACCEPTED")
        self.assertEqual(replay["state"], "ALREADY_ACCEPTED")
        self.assertEqual(refused["state"], "REFUSED")
        self.assertFalse(first["cancelled"])
        self.assertFalse(replay["cancelled"])
        self.assertFalse(refused["cancelled"])

    def test_job_id_stays_stable_through_idempotent_tick_checkpoint_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(directory)
            created = store.upsert(job_fields())
            self.assertEqual(created["job"]["job_id"], JOB_ID)
            t0 = store.tick(JOB_ID, now="2026-08-28T12:01:00Z", worker_id="peer-wake")
            self.assertEqual(t0["action"], "WAKE")
            self.assertEqual(t0["job_id"], JOB_ID)
            self.assertTrue(t0["invoke_model"])
            store.checkpoint(
                JOB_ID,
                {"step": 1},
                attempt_id=t0["attempt_id"],
                lease_id=t0["lease_id"],
                next_wake_at="2026-08-28T12:02:00Z",
                worker_id="peer-wake",
                now="2026-08-28T12:01:20Z",
            )
            quiet_lease = store.tick(JOB_ID, now="2026-08-28T12:01:35Z", worker_id="peer-wake-2")
            self.assertEqual(quiet_lease["action"], "STOP")
            t1 = store.tick(JOB_ID, now="2026-08-28T12:02:00Z", worker_id="peer-wake")
            pages = {job_fields()["result_address"]}
            store.checkpoint(
                JOB_ID,
                {"step": 2},
                attempt_id=t1["attempt_id"],
                lease_id=t1["lease_id"],
                next_wake_at="2026-08-28T12:03:00Z",
                worker_id="peer-wake",
                now="2026-08-28T12:02:10Z",
            )
            done = store.complete(
                JOB_ID,
                result={"durable": True, "step": 2, "kind": "page"},
                result_address=job_fields()["result_address"],
                page_exists=lambda ident: ident in pages,
                worker_id="peer-wake",
                now="2026-08-28T12:02:20Z",
            )
            quiet = store.tick(JOB_ID, now="2026-08-28T12:04:00Z", worker_id="peer-wake")
            self.assertEqual(done["job_id"], JOB_ID)
            self.assertEqual(quiet["action"], "STOP")
            self.assertFalse(quiet["invoke_model"])
            self.assertEqual(store.get(JOB_ID)["job_id"], JOB_ID)

    def test_deadline_and_budget_stop_without_a_model(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(directory)
            store.upsert(job_fields(deadline="2026-08-28T11:00:00Z"))
            late = store.tick(JOB_ID, now="2026-08-28T12:01:00Z", worker_id="peer-wake")
            self.assertEqual(late["action"], "STOP")
            self.assertFalse(late["invoke_model"])
            store.upsert(job_fields(job_id="peer-wake-budget-20260828-01", budget_tokens=1, tokens_used=1, deadline="2026-08-28T18:00:00Z"))
            spent = store.tick("peer-wake-budget-20260828-01", now="2026-08-28T12:01:00Z", worker_id="peer-wake")
            self.assertEqual(spent["action"], "STOP")
            self.assertFalse(spent["invoke_model"])

    def test_cursor_stays_held_and_watchdog_hook_does_not_fabricate_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(directory)
            store.upsert(job_fields(owner_claim="PLAYER1", harness="cursor-slack"))
            summary = watchdog_run(directory, deliver=True, now="2026-08-28T12:01:00Z", http=lambda *_a, **_k: self.fail("no network"))
            self.assertEqual(summary["jobs"][0]["action"], "HOLD")
            self.assertEqual(summary["peer_wake"]["signals"][0]["state"], "CURSOR_QUOTA_HOLD")
            self.assertFalse(summary["peer_wake"]["live_wake"])
            self.assertEqual(summary["process_model_invocations"], 0)
            self.assertFalse(summary["invoke_model"])

    def test_dispatch_chatgpt_is_poll_only(self):
        receipt = dispatch_delivery(job_fields(), {"action": "WAKE"}, deliver=True, root=ROOT, http=lambda *_a, **_k: self.fail("no network"))
        self.assertEqual(receipt["state"], "POLL_ONLY")
        self.assertFalse(receipt["live_wake"])
        self.assertFalse(receipt["invoke_model"])

    def test_bus_tick_is_cheap_and_attaches_signals(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(directory)
            store.upsert(job_fields())
            summary = tick(directory, deliver=False, now="2026-08-28T12:01:00Z", env={}, root=ROOT)
            self.assertEqual(summary["process_model_invocations"], 0)
            self.assertFalse(summary["peer_wake"]["live_wake"])
            self.assertEqual(summary["peer_wake"]["signals"][0]["state"], "POLL_ONLY")

    def test_open_door_and_no_secret_markers_in_tree(self):
        for rel in (
            "peer_wake/adapters/poll.py",
            "peer_wake/README.md",
            "ground/PEER_WAKE_BUS.md",
            "ground/PEER_WAKE_BUS.json",
            "peer_wake/targets/chatgpt.json",
            "peer_wake/targets/claude.json",
            "peer_wake/targets/grok_slack.json",
            "peer_wake/targets/gemini_slack.json",
            "host/peer_wake_bus.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("xoxb-", text)
            self.assertNotIn("xapp-", text)
            self.assertNotIn("AUTH_GATE", text)
            self.assertNotIn("permission denied", text.lower())
            self.assertNotIn("authentication required", text.lower())
        self.assertTrue((ROOT / "peer_wake" / "schema.json").is_file())
        bus = (ROOT / "peer_wake" / "bus.py").read_text(encoding="utf-8")
        self.assertNotIn("AUTH_GATE", bus)
        self.assertNotIn("permission denied", bus.lower())

    def test_host_instrument_classifies_integrated(self):
        row = host_instrument.classify(str(ROOT))
        self.assertTrue(row["ok"])
        self.assertEqual(row["state"], "INTEGRATED")
        self.assertEqual(row["chatgpt_doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertEqual(row["claude_doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertFalse(row["live_wake"])
        self.assertTrue(row.get("receipt_present"))
        self.assertEqual(row.get("receipt_path"), "p/grok-peer-wake-bus-20260828-01.md")


    def test_slack_table_tip_formats_without_network_or_live_wake(self):
        target = next(row for row in load_targets(ROOT) if row["peer"] == "CHATGPT")
        tip_target = {
            **{k: target[k] for k in ("peer", "wake_target") if k in target},
            "adapter": "slack_table_tip",
            "doorbell": "EXTERNAL_PLATFORM_ACTION",
            "wake_target": {
                "kind": "slack_table_tip",
                "channel": "C0BRGMDQB6G",
                "path": "ping/last.json",
                "prompt": "ping/chatgpt.md",
            },
        }
        receipt = tip_adapter.signal(
            tip_target,
            job_fields(),
            tick={"attempt_id": "a1"},
            deliver=False,
            http=lambda *_a, **_k: self.fail("tip must not network without post_fn deliver"),
        )
        self.assertEqual(receipt["state"], "TIP_FORMATTED")
        self.assertEqual(receipt["doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertFalse(receipt["live_wake"])
        self.assertFalse(receipt["invoke_model"])
        self.assertEqual(receipt["network_calls"], 0)
        self.assertIn("#commons", receipt["tip"])
        self.assertIn("C0BRGMDQB6G", receipt["tip"])
        self.assertIn(JOB_ID, receipt["tip"])
        self.assertIn("EXTERNAL_PLATFORM_ACTION", receipt["tip"])
        self.assertIn("grok-peer-wake-bus-20260828-01", receipt["tip"])

    def test_slack_table_tip_injected_post_fn_still_not_a_resume(self):
        calls = []
        tip_target = {
            "peer": "CLAUDE",
            "adapter": "slack_table_tip",
            "doorbell": "EXTERNAL_PLATFORM_ACTION",
            "wake_target": {
                "kind": "slack_table_tip",
                "channel": "C0BRGMDQB6G",
                "path": "ping/last.json",
                "prompt": "ping/claude.md",
            },
        }
        receipt = tip_adapter.signal(
            tip_target,
            job_fields(owner_claim="CLAUDE", harness="CLAUDE"),
            deliver=True,
            post_fn=lambda payload: calls.append(payload) or {"state": "TIP_POSTED_VIA_INJECTED", "status": 200},
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["channel"], "C0BRGMDQB6G")
        self.assertFalse(calls[0]["live_wake"])
        self.assertEqual(calls[0]["doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertEqual(receipt["state"], "TIP_POSTED_VIA_INJECTED")
        self.assertEqual(receipt["doorbell"], "EXTERNAL_PLATFORM_ACTION")
        self.assertFalse(receipt["live_wake"])
        self.assertEqual(receipt["network_calls"], 1)
        blob = json.dumps(receipt)
        self.assertNotIn("xoxb", blob.lower())
        self.assertNotIn(SECRET, blob)

    def test_slack_table_tip_http_is_never_a_carrier(self):
        calls = []
        tip_target = {
            "peer": "CHATGPT",
            "adapter": "slack_table_tip",
            "doorbell": "EXTERNAL_PLATFORM_ACTION",
            "wake_target": {"channel": "C0BRGMDQB6G", "path": "ping/last.json"},
        }
        receipt = tip_adapter.signal(
            tip_target,
            job_fields(),
            deliver=True,
            http=lambda payload: calls.append(payload) or {"state": "HTTP_USED", "status": 200},
        )
        self.assertEqual(calls, [])
        self.assertEqual(receipt["state"], "TIP_FORMATTED")
        self.assertEqual(receipt["network_calls"], 0)
        self.assertFalse(receipt["live_wake"])
        self.assertEqual(receipt["doorbell"], "EXTERNAL_PLATFORM_ACTION")

    def test_slack_table_tip_refuses_non_external_doorbell_without_posting(self):
        calls = []
        tip_target = {
            "peer": "CHATGPT",
            "adapter": "slack_table_tip",
            "doorbell": "LIVE_WAKE",
            "wake_target": {"channel": "C0BRGMDQB6G", "path": "ping/last.json"},
        }
        receipt = tip_adapter.signal(
            tip_target,
            job_fields(),
            deliver=True,
            http=lambda payload: calls.append(("http", payload)),
            post_fn=lambda payload: calls.append(("post", payload)) or {"status": 200},
        )
        self.assertEqual(calls, [])
        self.assertEqual(receipt["state"], "TIP_FORMATTED")
        self.assertEqual(receipt["network_calls"], 0)
        self.assertFalse(receipt["live_wake"])
        self.assertIn("refuses non-EXTERNAL", receipt["note"])



if __name__ == "__main__":
    unittest.main()

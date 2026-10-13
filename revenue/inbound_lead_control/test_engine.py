from __future__ import annotations

import copy
import hashlib
import unittest

from revenue.inbound_lead_control.engine import (
    InputError,
    SCHEMA_VERSION,
    compile_snapshot,
    render_markdown,
    verify_compiled,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _event(
    event_id: str,
    kind: str,
    when: str,
    *,
    intent: str = "GENERAL",
    provider_ref: str | None = None,
    content: str | None = None,
    route_key: str = "gmail:sales@example.com",
    thread_key: str = "gmail:thread:1",
    lead_id: str = "L1",
):
    return {
        "event_id": event_id,
        "provider": "gmail",
        "provider_ref": provider_ref or f"gmail:{event_id}",
        "kind": kind,
        "route_key": route_key,
        "thread_key": thread_key,
        "lead_id": lead_id,
        "occurred_utc": when,
        "content_sha256": _sha(content or event_id),
        "intent": intent,
    }


def _claim(claim_id: str, writer: str, *, state: str = "ACTIVE", claimed: str = "2026-09-17T08:30:00Z", expires: str = "2026-09-17T09:30:00Z"):
    return {
        "claim_id": claim_id,
        "writer_id": writer,
        "route_key": "gmail:sales@example.com",
        "thread_key": "gmail:thread:1",
        "claimed_utc": claimed,
        "expires_utc": expires,
        "state": state,
    }


def _doc():
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_utc": "2026-09-17T09:00:00Z",
        "policy": {
            "response_sla_minutes": {"HOT": 30, "WARM": 120, "GENERAL": 1440},
            "max_census_age_minutes": 15,
            "max_claim_horizon_minutes": 120,
        },
        "census": {
            "provider_complete": True,
            "coordination_complete": True,
            "pages_complete": True,
            "observed_utc": "2026-09-17T08:58:00Z",
        },
        "leads": [
            {
                "lead_id": "L1",
                "counterparty": "Example Buyer",
                "priority": "HOT",
                "route_key": "gmail:sales@example.com",
                "thread_key": "gmail:thread:1",
                "events": [_event("E1", "HUMAN_INBOUND", "2026-09-17T08:40:00Z")],
                "claims": [],
            }
        ],
    }


class InboundLeadControlTests(unittest.TestCase):
    def test_new_human_inbound_opens_exact_response_edge(self):
        result = compile_snapshot(_doc())
        row = result["leads"][0]
        self.assertEqual(row["state"], "NEW_INBOUND_UNANSWERED")
        self.assertEqual(row["next_action"], "RECENSUS_THEN_MUSE_ARBITRATION")
        self.assertFalse(row["sla_breached"])
        self.assertEqual(row["evidence_refs"]["latest_inbound"]["provider_ref"], "gmail:E1")
        self.assertTrue(all(value is False for value in result["authority"].values()))

    def test_sla_breach_is_fact_not_send_authority(self):
        doc = _doc()
        doc["leads"][0]["events"][0]["occurred_utc"] = "2026-09-17T08:00:00Z"
        result = compile_snapshot(doc)
        row = result["leads"][0]
        self.assertTrue(row["sla_breached"])
        self.assertEqual(row["inbound_age_minutes"], 60)
        self.assertFalse(result["authority"]["send_authorized"])

    def test_outbound_after_inbound_closes_edge_to_hard_dnr(self):
        doc = _doc()
        doc["leads"][0]["events"].append(_event("E2", "OUTBOUND_SENT", "2026-09-17T08:50:00Z"))
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "WAITING_ON_COUNTERPARTY")
        self.assertEqual(row["next_action"], "HARD_DNR_UNTIL_NEW_HUMAN_OR_PROVIDER_EVENT")

    def test_newer_human_inbound_reopens_after_prior_outbound(self):
        doc = _doc()
        doc["leads"][0]["events"] = [
            _event("E1", "HUMAN_INBOUND", "2026-09-17T08:30:00Z"),
            _event("E2", "OUTBOUND_SENT", "2026-09-17T08:40:00Z"),
            _event("E3", "HUMAN_INBOUND", "2026-09-17T08:55:00Z"),
        ]
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "NEW_INBOUND_UNANSWERED")
        self.assertEqual(row["evidence_refs"]["latest_inbound"]["event_id"], "E3")
        self.assertEqual(row["evidence_refs"]["latest_outbound"]["event_id"], "E2")

    def test_meeting_request_requires_calendar_before_muse(self):
        doc = _doc()
        doc["leads"][0]["events"][0]["intent"] = "MEETING"
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "CHECK_CALENDAR_REQUIRED")
        self.assertEqual(row["next_action"], "CHECK_CALENDAR_THEN_RECENSUS_AND_MUSE_ARBITRATION")

    def test_binding_terms_require_owner_decision_before_muse(self):
        doc = _doc()
        doc["leads"][0]["events"][0]["intent"] = "BINDING_TERMS"
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "OWNER_DECISION_REQUIRED")
        self.assertEqual(row["next_action"], "OWNER_DECISION_THEN_RECENSUS_AND_MUSE_ARBITRATION")

    def test_two_live_writers_fail_closed_to_collision(self):
        doc = _doc()
        doc["leads"][0]["claims"] = [_claim("C1", "writer-a"), _claim("C2", "writer-b")]
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "COLLISION_HOLD")
        self.assertEqual(row["active_writers"], ["writer-a", "writer-b"])

    def test_two_claim_records_same_writer_are_not_a_writer_collision(self):
        doc = _doc()
        doc["leads"][0]["claims"] = [_claim("C1", "writer-a"), _claim("C2", "writer-a")]
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "NEW_INBOUND_UNANSWERED")
        self.assertEqual(row["active_writers"], ["writer-a"])

    def test_released_or_expired_claim_does_not_create_collision(self):
        doc = _doc()
        doc["leads"][0]["claims"] = [
            _claim("C1", "writer-a"),
            _claim("C2", "writer-b", state="RELEASED"),
            _claim("C3", "writer-c", expires="2026-09-17T08:59:00Z"),
        ]
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["active_writers"], ["writer-a"])
        self.assertEqual(row["state"], "NEW_INBOUND_UNANSWERED")

    def test_incomplete_provider_census_holds(self):
        doc = _doc()
        doc["census"]["provider_complete"] = False
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "CENSUS_HOLD")

    def test_incomplete_coordination_census_holds(self):
        doc = _doc()
        doc["census"]["coordination_complete"] = False
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "CENSUS_HOLD")

    def test_stale_census_holds(self):
        doc = _doc()
        doc["census"]["observed_utc"] = "2026-09-17T08:00:00Z"
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "CENSUS_HOLD")

    def test_future_event_holds_as_evidence_error(self):
        doc = _doc()
        doc["leads"][0]["events"].append(_event("E2", "HUMAN_INBOUND", "2026-09-17T09:01:00Z"))
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "EVIDENCE_HOLD")
        self.assertIn("FUTURE_EVENT", row["reasons"])

    def test_event_from_wrong_thread_cannot_reopen_route(self):
        doc = _doc()
        doc["leads"][0]["events"].append(
            _event("E2", "HUMAN_INBOUND", "2026-09-17T08:55:00Z", thread_key="gmail:thread:other")
        )
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "EVIDENCE_HOLD")
        self.assertIn("EVENT_SCOPE_MISMATCH", row["reasons"])

    def test_bounce_on_route_holds_and_does_not_invent_alias(self):
        doc = _doc()
        doc["leads"][0]["events"].append(_event("E2", "BOUNCE", "2026-09-17T08:50:00Z"))
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "ROUTE_FAILURE_HOLD")
        self.assertEqual(row["next_action"], "NO_ALIAS_HUNT_NEW_ROUTE_REQUIRES_FRESH_GENERATION")

    def test_no_inbound_signal_is_not_actionable(self):
        doc = _doc()
        doc["leads"][0]["events"] = []
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "NO_INBOUND_SIGNAL")
        self.assertEqual(row["next_action"], "NONE")

    def test_muse_selected_is_evidence_only_not_send_authority(self):
        doc = _doc()
        doc["leads"][0]["events"].append(_event("E2", "MUSE_SELECTED", "2026-09-17T08:45:00Z"))
        result = compile_snapshot(doc)
        row = result["leads"][0]
        self.assertTrue(row["muse_selected_evidence_present"])
        self.assertEqual(row["next_action"], "RECENSUS_THEN_MUSE_ARBITRATION")
        self.assertFalse(result["authority"]["send_authorized"])

    def test_duplicate_provider_reference_fails_closed(self):
        doc = _doc()
        doc["leads"][0]["events"].append(
            _event("E2", "OUTBOUND_SENT", "2026-09-17T08:50:00Z", provider_ref="gmail:E1")
        )
        with self.assertRaises(InputError):
            compile_snapshot(doc)

    def test_semantic_duplicate_under_new_ids_and_refs_fails_closed(self):
        doc = _doc()
        doc["leads"][0]["events"].append(
            _event(
                "E2",
                "HUMAN_INBOUND",
                "2026-09-17T08:40:00Z",
                provider_ref="gmail:forged-copy",
                content="E1",
            )
        )
        with self.assertRaises(InputError):
            compile_snapshot(doc)

    def test_duplicate_event_id_fails_closed(self):
        doc = _doc()
        doc["leads"][0]["events"].append(
            _event("E1", "OUTBOUND_SENT", "2026-09-17T08:50:00Z", provider_ref="gmail:E2")
        )
        with self.assertRaises(InputError):
            compile_snapshot(doc)

    def test_duplicate_route_thread_leads_fail_closed(self):
        doc = _doc()
        other = copy.deepcopy(doc["leads"][0])
        other["lead_id"] = "L2"
        other["events"] = []
        doc["leads"].append(other)
        with self.assertRaises(InputError):
            compile_snapshot(doc)

    def test_noncanonical_timestamp_fails_closed(self):
        doc = _doc()
        doc["leads"][0]["events"][0]["occurred_utc"] = "2026-09-17T08:40:00.000Z"
        with self.assertRaises(InputError):
            compile_snapshot(doc)

    def test_bool_cannot_masquerade_as_integer_policy(self):
        doc = _doc()
        doc["policy"]["response_sla_minutes"]["HOT"] = True
        with self.assertRaises(InputError):
            compile_snapshot(doc)

    def test_oversized_claim_horizon_fails_closed(self):
        doc = _doc()
        doc["leads"][0]["claims"] = [
            _claim("C1", "writer-a", claimed="2026-09-17T06:00:00Z", expires="2026-09-17T09:00:00Z")
        ]
        with self.assertRaises(InputError):
            compile_snapshot(doc)

    def test_future_claim_does_not_mint_an_active_writer(self):
        doc = _doc()
        doc["leads"][0]["claims"] = [
            _claim("C1", "writer-a", claimed="2026-09-17T09:01:00Z", expires="2026-09-17T09:30:00Z")
        ]
        row = compile_snapshot(doc)["leads"][0]
        self.assertEqual(row["state"], "EVIDENCE_HOLD")
        self.assertEqual(row["active_writers"], [])
        self.assertIn("FUTURE_CLAIM", row["reasons"])

    def test_receipt_verifier_replays_exact_semantics_and_rejects_tamper(self):
        doc = _doc()
        result = compile_snapshot(doc)
        self.assertTrue(verify_compiled(doc, result))
        tampered = copy.deepcopy(result)
        tampered["leads"][0]["state"] = "WAITING_ON_COUNTERPARTY"
        self.assertFalse(verify_compiled(doc, tampered))

    def test_markdown_is_deterministic_and_carries_authority_warning(self):
        result = compile_snapshot(_doc())
        first = render_markdown(result)
        second = render_markdown(copy.deepcopy(result))
        self.assertEqual(first, second)
        self.assertIn("NEW_INBOUND_UNANSWERED", first)
        self.assertIn("No row authorizes an external send", first)

    def test_priority_and_breach_sorting_is_deterministic(self):
        doc = _doc()
        doc["leads"][0]["priority"] = "WARM"
        doc["leads"][0]["lead_id"] = "L-warm"
        doc["leads"][0]["events"][0]["lead_id"] = "L-warm"
        second = copy.deepcopy(doc["leads"][0])
        second["lead_id"] = "L-hot"
        second["counterparty"] = "Hot Buyer"
        second["priority"] = "HOT"
        second["route_key"] = "gmail:hot@example.com"
        second["thread_key"] = "gmail:thread:hot"
        second["events"] = [
            _event(
                "E-hot",
                "HUMAN_INBOUND",
                "2026-09-17T08:00:00Z",
                route_key="gmail:hot@example.com",
                thread_key="gmail:thread:hot",
                lead_id="L-hot",
            )
        ]
        second["claims"] = []
        doc["leads"].append(second)
        result = compile_snapshot(doc)
        self.assertEqual([row["lead_id"] for row in result["leads"]], ["L-hot", "L-warm"])
        self.assertTrue(result["leads"][0]["sla_breached"])

    def test_census_time_after_asof_is_rejected_not_negative_age(self):
        doc = _doc()
        doc["census"]["observed_utc"] = "2026-09-17T09:01:00Z"
        with self.assertRaises(InputError):
            compile_snapshot(doc)


import contextlib
import io
import json
from pathlib import Path
import tempfile

from revenue.inbound_lead_control import cli as inbound_cli


class InboundLeadControlCliTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, value) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_compile_cli_writes_exclusive_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source = self._write(directory, "input.json", _doc())
            json_out = directory / "compiled.json"
            md_out = directory / "queue.md"
            rc = inbound_cli.main([
                "compile",
                str(source),
                "--json-out",
                str(json_out),
                "--markdown-out",
                str(md_out),
            ])
            self.assertEqual(rc, 0)
            compiled = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertTrue(verify_compiled(_doc(), compiled))
            self.assertIn("NEW_INBOUND_UNANSWERED", md_out.read_text(encoding="utf-8"))

    def test_compile_cli_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source = self._write(directory, "input.json", _doc())
            json_out = self._write(directory, "compiled.json", {"existing": True})
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = inbound_cli.main(["compile", str(source), "--json-out", str(json_out)])
            self.assertEqual(rc, 2)
            self.assertIn("refusing to overwrite", stderr.getvalue())

    def test_verify_cli_accepts_exact_replay_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source = self._write(directory, "input.json", _doc())
            compiled = compile_snapshot(_doc())
            compiled_path = self._write(directory, "compiled.json", compiled)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = inbound_cli.main(["verify", str(source), str(compiled_path)])
            self.assertEqual(rc, 0)
            self.assertEqual(stdout.getvalue().strip(), "VALID")

            compiled["leads"][0]["state"] = "WAITING_ON_COUNTERPARTY"
            compiled_path.write_text(json.dumps(compiled), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = inbound_cli.main(["verify", str(source), str(compiled_path)])
            self.assertEqual(rc, 2)
            self.assertIn("INVALID", stderr.getvalue())

    def test_cli_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source = directory / "dup.json"
            source.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = inbound_cli.main(["compile", str(source)])
            self.assertEqual(rc, 2)
            self.assertIn("duplicate JSON key", stderr.getvalue())

    def test_cli_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            real = self._write(directory, "input.json", _doc())
            link = directory / "link.json"
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = inbound_cli.main(["compile", str(link)])
            self.assertEqual(rc, 2)
            self.assertIn("regular non-symlink", stderr.getvalue())

    def test_render_rejects_self_receipt_tamper(self):
        compiled = compile_snapshot(_doc())
        compiled["leads"][0]["state"] = "WAITING_ON_COUNTERPARTY"
        with self.assertRaises(InputError):
            render_markdown(compiled)


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from revenue.sales_meeting_calendar_consumer.calendar_consumer import (
    CALENDAR_ID,
    CAPTURE_SCHEMA,
    CURRENT_MODE,
    HISTORICAL_MODE,
    HISTORICAL_REPLAY,
    CalendarConsumerError,
    HUMAN_AUTHORITY_SCHEMA,
    RECEIPT_SCHEMA,
    TRIGGER_SCHEMA,
    build_google_availability_plan,
    build_google_availability_plan_historical,
    canonical_json_bytes,
    capture_google_availability,
    compile_calendar_consumer_current,
    compile_calendar_consumer_historical,
    google_tool_args,
    is_ready_for_owner_review,
    render_markdown,
    sha256_hex,
    strict_json_loads,
)


NOW = datetime(2026, 9, 13, 16, 26, tzinfo=timezone.utc)
CAPTURE_REF = "calendar-capture/demo"


class TrustedStore:
    """Test-only stand-in for the host's independently retained provider store."""

    def __init__(self, humans=None, captures=None):
        self.humans = deepcopy(humans or {})
        self.captures = deepcopy(captures or {})

    def get_human_authority(self, authority_ref):
        return deepcopy(self.humans[authority_ref])

    def get_calendar_capture(self, capture_ref):
        return deepcopy(self.captures[capture_ref])


def trigger(*, thread_ref: str = "thread/demo", windows=None, duration: int = 30,
            inbound_at: str = "2026-09-13T16:20:00Z"):
    windows = windows or [
        {"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T19:00:00Z"},
    ]
    return {
        "schema": TRIGGER_SCHEMA,
        "opportunity_id": "opp/demo",
        "owner_ref": "owner/bryce",
        "counterparty_ref": "buyer/demo",
        "thread_ref": thread_ref,
        "human_authority_ref": "human-auth/demo",
        "inbound": {
            "observation_id": "gmail/msg-demo",
            "content_sha256": "a" * 64,
            "received_at": inbound_at,
        },
        "request": {
            "duration_minutes": duration,
            "timezone": "America/Kentucky/Louisville",
            "windows": windows,
        },
        "prep": {
            "context": [
                {"text": "Buyer asked to discuss the scoped evidence pilot.", "source_ref": "gmail/msg-demo"},
                {"text": "No pricing or timeline commitment is accepted yet.", "source_ref": "scope/current"},
            ],
            "objective": "Confirm fit, decision process, and the smallest truthful paid next step.",
            "key_questions": ["What outcome must the buyer approve?", "Who owns the final decision?"],
            "likely_asks": ["Scope detail", "Delivery timeline"],
            "risks_commitments_to_avoid": ["Do not promise unsupported integrations.", "Do not accept a start date."],
            "recommended_opening": "Thanks for making time; I want to pin down the outcome and acceptance boundary.",
            "recommended_closing": "I will send a bounded written scope only after we confirm the decision path.",
            "owner_actions": ["Review the brief before confirming any slot."],
        },
    }


def human_authority(t):
    return {
        "schema": HUMAN_AUTHORITY_SCHEMA,
        "authority_id": t["human_authority_ref"],
        "provider_ref": "gmail:message",
        "event_id": t["inbound"]["observation_id"],
        "event_sha256": t["inbound"]["content_sha256"],
        "observed_at": t["inbound"]["received_at"],
        "opportunity_id": t["opportunity_id"],
        "thread_ref": t["thread_ref"],
        "classification": "MEETING_REQUEST",
        "verified_human": True,
        "meeting_requested": True,
    }


def provider_result(*, busy=None, errors=None):
    return {
        "calendars": [{
            "calendar_id": CALENDAR_ID,
            "busy": busy or [],
            "errors": errors,
        }]
    }


class ConsumerTests(unittest.TestCase):
    def plan_and_capture(self, t=None, *, busy=None, errors=None, captured_at=None):
        t = t or trigger()
        auth = human_authority(t)
        store = TrustedStore({t["human_authority_ref"]: auth})
        plan = build_google_availability_plan(t, authority_store=store)
        capture = capture_google_availability(
            plan,
            provider_result(busy=busy, errors=errors),
            captured_at=captured_at or NOW - timedelta(minutes=1),
        )
        store.captures[CAPTURE_REF] = deepcopy(capture)
        return t, auth, store, plan, capture

    def compile_current(self, t, store, *, capture_ref=CAPTURE_REF, now=NOW):
        with patch("revenue.sales_meeting_calendar_consumer.calendar_consumer._process_now_utc", return_value=now):
            return compile_calendar_consumer_current(t, capture_ref, authority_store=store)

    def test_plan_matches_exact_trigger_window_and_timezone(self):
        t, auth, store, plan, _ = self.plan_and_capture()
        self.assertEqual(plan["calendar_id"], "primary")
        self.assertEqual(plan["owner_ref"], "owner/bryce")
        self.assertEqual(plan["time_min"], "2026-09-14T17:00:00Z")
        self.assertEqual(plan["time_max"], "2026-09-14T19:00:00Z")
        self.assertEqual(plan["response_timezone_str"], "America/Kentucky/Louisville")
        self.assertEqual(plan["human_authority_sha256"], sha256_hex(canonical_json_bytes(auth)))
        self.assertEqual(build_google_availability_plan(t, authority_store=store), plan)

    def test_tool_args_are_read_only_freebusy_shape_only(self):
        _, _, _, plan, _ = self.plan_and_capture()
        self.assertEqual(
            google_tool_args(plan),
            {
                "calendar_ids": ["primary"],
                "time_min": "2026-09-14T17:00:00Z",
                "time_max": "2026-09-14T19:00:00Z",
                "response_timezone_str": "America/Kentucky/Louisville",
            },
        )
        encoded = json.dumps(google_tool_args(plan))
        for forbidden in ("attendees", "title", "create", "update", "delete", "invite"):
            self.assertNotIn(forbidden, encoded)

    def test_current_ready_requires_store_bound_human_and_calendar_records(self):
        t, _, store, _, _ = self.plan_and_capture()
        receipt = self.compile_current(t, store)
        self.assertEqual(receipt["schema"], RECEIPT_SCHEMA)
        self.assertEqual(receipt["mode"], CURRENT_MODE)
        self.assertEqual(receipt["state"], "READY_FOR_OWNER_SCHEDULING_REVIEW")
        self.assertTrue(receipt["authority"]["current_authority_store_bound"])
        for key in ("calendar_create", "calendar_update", "calendar_delete", "invite_or_rsvp",
                    "provider_send_or_reply", "scheduling_confirmation", "commercial_commitment"):
            self.assertFalse(receipt["authority"][key])
        with patch("revenue.sales_meeting_calendar_consumer.calendar_consumer._process_now_utc", return_value=NOW):
            self.assertTrue(is_ready_for_owner_review(receipt, t, authority_store=store))

    def test_capture_from_other_owner_cannot_be_reused(self):
        t, _, store, _, _ = self.plan_and_capture()
        other = deepcopy(t)
        other["owner_ref"] = "owner/other"
        with self.assertRaisesRegex(CalendarConsumerError, "capture plan does not match"):
            self.compile_current(other, store)

    def test_started_slot_is_stale_in_current_mode(self):
        t = trigger(
            windows=[
                {"start": "2026-09-13T16:20:00Z", "end": "2026-09-13T17:20:00Z"}
            ],
            inbound_at="2026-09-13T15:50:00Z",
        )
        t, _, store, _, _ = self.plan_and_capture(
            t=t,
            captured_at=NOW - timedelta(minutes=1),
        )
        self.assertEqual(self.compile_current(t, store)["state"], "REQUEST_STALE")

    def test_self_authenticating_candidate_hash_attack_cannot_reach_current_ready(self):
        t = trigger()
        fake_auth = human_authority(t)
        fake_plan = build_google_availability_plan_historical(t, fake_auth)
        fake_capture = capture_google_availability(fake_plan, provider_result(), captured_at=NOW - timedelta(minutes=1))
        self.assertEqual(fake_capture["capture_sha256"], sha256_hex(canonical_json_bytes({k: v for k, v in fake_capture.items() if k != "capture_sha256"})))
        empty = TrustedStore()
        with self.assertRaisesRegex(CalendarConsumerError, "retained authority is missing"):
            build_google_availability_plan(t, authority_store=empty)
        with self.assertRaisesRegex(CalendarConsumerError, "retained authority is missing"):
            self.compile_current(t, empty)
        with self.assertRaisesRegex(CalendarConsumerError, "independent authority-store object"):
            compile_calendar_consumer_current(t, CAPTURE_REF, authority_store={
                "human": fake_auth, "calendar": fake_capture
            })

    def test_historical_direct_bytes_are_permanently_non_authorizing(self):
        t, auth, _, _, capture = self.plan_and_capture()
        receipt = compile_calendar_consumer_historical(t, auth, capture, as_of=NOW)
        self.assertEqual(receipt["mode"], HISTORICAL_MODE)
        self.assertEqual(receipt["state"], HISTORICAL_REPLAY)
        self.assertEqual(receipt["historical_core_state"], "READY_FOR_OWNER_SCHEDULING_REVIEW")
        self.assertFalse(receipt["authority"]["owner_review_only"])
        self.assertTrue(receipt["authority"]["historical_replay_only"])
        with patch("revenue.sales_meeting_calendar_consumer.calendar_consumer._process_now_utc", return_value=NOW):
            self.assertFalse(is_ready_for_owner_review(receipt, t, authority_store=TrustedStore()))

    def test_backdated_historical_time_cannot_revive_current_ready(self):
        t = trigger(inbound_at="2026-09-13T15:50:00Z")
        t, auth, store, _, capture = self.plan_and_capture(t=t, captured_at=NOW - timedelta(minutes=31))
        current = self.compile_current(t, store, now=NOW)
        self.assertEqual(current["state"], "CALENDAR_CHECK_REQUIRED")
        historical = compile_calendar_consumer_historical(
            t, auth, capture, as_of=NOW - timedelta(minutes=30)
        )
        self.assertEqual(historical["historical_core_state"], "READY_FOR_OWNER_SCHEDULING_REVIEW")
        self.assertEqual(historical["state"], HISTORICAL_REPLAY)
        with patch("revenue.sales_meeting_calendar_consumer.calendar_consumer._process_now_utc", return_value=NOW):
            self.assertFalse(is_ready_for_owner_review(historical, t, authority_store=store))

    def test_busy_at_window_start_selects_next_free_duration(self):
        busy = [{"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T17:30:00Z"}]
        t, _, store, _, _ = self.plan_and_capture(busy=busy)
        receipt = self.compile_current(t, store)
        self.assertEqual(receipt["state"], "READY_FOR_OWNER_SCHEDULING_REVIEW")
        self.assertEqual(receipt["core_receipt"]["meeting"]["proposed_slot"],
                         {"start": "2026-09-14T17:30:00Z", "end": "2026-09-14T18:00:00Z"})

    def test_fully_busy_window_is_conflict_not_ready(self):
        busy = [{"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T19:00:00Z"}]
        t, _, store, _, _ = self.plan_and_capture(busy=busy)
        self.assertEqual(self.compile_current(t, store)["state"], "SLOT_CONFLICT")

    def test_provider_error_is_unknown_and_requires_fresh_calendar(self):
        t, _, store, _, capture = self.plan_and_capture(errors=[{"reason": "backendError"}])
        self.assertTrue(capture["response"]["calendars"][0]["errors_present"])
        self.assertNotIn("backendError", json.dumps(capture))
        self.assertEqual(self.compile_current(t, store)["state"], "CALENDAR_CHECK_REQUIRED")

    def test_offset_busy_is_normalized_to_utc(self):
        busy = [{"start": "2026-09-14T13:00:00-04:00", "end": "2026-09-14T13:30:00-04:00"}]
        _, _, _, _, capture = self.plan_and_capture(busy=busy)
        self.assertEqual(capture["response"]["calendars"][0]["busy"],
                         [{"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T17:30:00Z"}])

    def test_capture_outside_exact_query_bounds_rejected(self):
        t = trigger()
        store = TrustedStore({t["human_authority_ref"]: human_authority(t)})
        plan = build_google_availability_plan(t, authority_store=store)
        with self.assertRaisesRegex(CalendarConsumerError, "exceeds exact query bounds"):
            capture_google_availability(plan, provider_result(busy=[{
                "start": "2026-09-14T16:59:59Z", "end": "2026-09-14T17:15:00Z",
            }]), captured_at=NOW)

    def test_wrong_calendar_rejected(self):
        t = trigger()
        store = TrustedStore({t["human_authority_ref"]: human_authority(t)})
        plan = build_google_availability_plan(t, authority_store=store)
        raw = {"calendars": [{"calendar_id": "other", "busy": [], "errors": None}]}
        with self.assertRaisesRegex(CalendarConsumerError, "calendar binding"):
            capture_google_availability(plan, raw, captured_at=NOW)

    def test_unverified_or_nonmeeting_store_record_rejected(self):
        t = trigger()
        auth = human_authority(t)
        auth["verified_human"] = False
        store = TrustedStore({t["human_authority_ref"]: auth})
        with self.assertRaisesRegex(CalendarConsumerError, "not verified human meeting intent"):
            build_google_availability_plan(t, authority_store=store)

    def test_human_authority_transplant_rejected(self):
        t = trigger()
        auth = human_authority(t)
        auth["thread_ref"] = "thread/other"
        store = TrustedStore({t["human_authority_ref"]: auth})
        with self.assertRaisesRegex(CalendarConsumerError, "thread binding mismatch"):
            build_google_availability_plan(t, authority_store=store)

    def test_calendar_store_record_tamper_rejected(self):
        t, _, store, _, capture = self.plan_and_capture()
        bad = deepcopy(capture)
        bad["captured_at"] = "2026-09-13T16:25:30Z"
        store.captures[CAPTURE_REF] = bad
        with self.assertRaisesRegex(CalendarConsumerError, "capture digest mismatch"):
            self.compile_current(t, store)

    def test_capture_from_different_reply_generation_cannot_be_reused(self):
        first = trigger()
        second = trigger(thread_ref="thread/new-generation")
        second["inbound"]["observation_id"] = "gmail/msg-new"
        second["inbound"]["content_sha256"] = "b" * 64
        second["human_authority_ref"] = "human-auth/new"
        second_store = TrustedStore({second["human_authority_ref"]: human_authority(second)})
        second_plan = build_google_availability_plan(second, authority_store=second_store)
        second_capture = capture_google_availability(second_plan, provider_result(), captured_at=NOW - timedelta(minutes=1))
        first_store = TrustedStore(
            {first["human_authority_ref"]: human_authority(first)},
            {CAPTURE_REF: second_capture},
        )
        with self.assertRaisesRegex(CalendarConsumerError, "capture plan"):
            self.compile_current(first, first_store)

    def test_stale_capture_cannot_retain_current_ready(self):
        t = trigger(inbound_at="2026-09-13T15:50:00Z")
        t, _, store, _, _ = self.plan_and_capture(t=t, captured_at=NOW - timedelta(minutes=31))
        self.assertEqual(self.compile_current(t, store)["state"], "CALENDAR_CHECK_REQUIRED")

    def test_request_window_shorter_than_duration_rejected_before_query(self):
        t = trigger(windows=[{"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T17:20:00Z"}], duration=30)
        store = TrustedStore({t["human_authority_ref"]: human_authority(t)})
        with self.assertRaisesRegex(CalendarConsumerError, "shorter than requested duration"):
            build_google_availability_plan(t, authority_store=store)

    def test_multiple_windows_use_covering_query_but_slot_stays_inside_requested_window(self):
        t = trigger(windows=[
            {"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T18:00:00Z"},
            {"start": "2026-09-14T20:00:00Z", "end": "2026-09-14T21:00:00Z"},
        ])
        busy = [{"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T18:00:00Z"}]
        t, _, store, plan, _ = self.plan_and_capture(t=t, busy=busy)
        self.assertEqual(plan["time_min"], "2026-09-14T17:00:00Z")
        self.assertEqual(plan["time_max"], "2026-09-14T21:00:00Z")
        receipt = self.compile_current(t, store)
        self.assertEqual(receipt["state"], "READY_FOR_OWNER_SCHEDULING_REVIEW")
        self.assertEqual(receipt["core_receipt"]["meeting"]["proposed_slot"]["start"], "2026-09-14T20:00:00Z")

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(CalendarConsumerError, "duplicate JSON key"):
            strict_json_loads('{"schema":"a","schema":"b"}')

    def test_capture_does_not_persist_error_text_or_event_details(self):
        _, _, _, _, capture = self.plan_and_capture(errors=[{
            "domain": "global", "reason": "forbidden", "message": "sensitive provider detail",
        }])
        encoded = json.dumps(capture)
        self.assertNotIn("sensitive provider detail", encoded)
        self.assertNotIn("reason", encoded)
        self.assertIn("provider_result_sha256", capture)

    def test_render_contains_full_prep_and_store_boundary(self):
        t, _, store, _, _ = self.plan_and_capture()
        receipt = self.compile_current(t, store)
        md = render_markdown(receipt)
        self.assertIn("independently retained authority-store", md)
        self.assertIn("not authorized", md)
        self.assertIn("Confirm fit", md)
        self.assertIn("What outcome must the buyer approve?", md)
        self.assertIn("Do not promise unsupported integrations.", md)

    def test_capture_schema_and_hash_are_deterministic_for_same_inputs(self):
        t = trigger()
        store = TrustedStore({t["human_authority_ref"]: human_authority(t)})
        plan = build_google_availability_plan(t, authority_store=store)
        raw = provider_result()
        a = capture_google_availability(plan, raw, captured_at=NOW)
        b = capture_google_availability(deepcopy(plan), deepcopy(raw), captured_at=NOW)
        self.assertEqual(a, b)
        self.assertEqual(a["schema"], CAPTURE_SCHEMA)

    def test_ready_helper_reacquires_store_and_fresh_time(self):
        t, _, store, _, _ = self.plan_and_capture()
        receipt = self.compile_current(t, store)
        del store.captures[CAPTURE_REF]
        with patch("revenue.sales_meeting_calendar_consumer.calendar_consumer._process_now_utc", return_value=NOW):
            with self.assertRaisesRegex(CalendarConsumerError, "retained authority is missing"):
                is_ready_for_owner_review(receipt, t, authority_store=store)


if __name__ == "__main__":
    unittest.main()

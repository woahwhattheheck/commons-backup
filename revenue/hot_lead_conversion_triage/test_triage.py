"""Regression tests for hot-lead conversion triage."""

from __future__ import annotations

import hashlib
import json
import unittest

from revenue.hot_lead_conversion_triage.triage import (
    TriageInputError,
    loads_strict,
    triage_document,
)


AS_OF = "2026-09-15T00:45:00Z"


def _event(event_id: str, at: str, kind: str) -> dict:
    return {"event_id": event_id, "observed_at": at, "kind": kind}


def _thread(
    prospect: str,
    thread: str,
    observations: list[dict],
    *,
    last_outbound: str | None = None,
    candidate: str | None = None,
) -> dict:
    value = {
        "prospect_id": prospect,
        "thread_id": thread,
        "observations": observations,
    }
    if last_outbound is not None:
        value["last_outbound_at"] = last_outbound
    if candidate is not None:
        value["candidate_followup"] = candidate
    return value


def _document(*threads: dict) -> dict:
    return {"schema_version": 1, "as_of": AS_OF, "threads": list(threads)}


class HotLeadTriageTests(unittest.TestCase):
    def test_unanswered_positive_is_first_actionable(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "prospect-b",
                    "thread-b",
                    [_event("b1", "2026-09-15T00:41:00Z", "HUMAN_QUESTION")],
                    last_outbound="2026-09-15T00:40:00Z",
                ),
                _thread(
                    "prospect-a",
                    "thread-a",
                    [_event("a1", "2026-09-15T00:42:00Z", "HUMAN_POSITIVE")],
                    last_outbound="2026-09-15T00:40:00Z",
                ),
            )
        )
        self.assertEqual(
            [item["reason_code"] for item in receipt["action_queue"]],
            ["UNANSWERED_HUMAN_POSITIVE", "UNANSWERED_HUMAN_QUESTION"],
        )
        self.assertFalse(receipt["authority"]["external_send_authorized"])
        self.assertTrue(receipt["authority"]["publication_authority_required"])

    def test_reply_at_or_before_latest_outbound_is_not_actionable(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "impact-advisors",
                    "ohsu",
                    [_event("r1", "2026-09-15T00:30:00Z", "HUMAN_POSITIVE")],
                    last_outbound="2026-09-15T00:31:00Z",
                )
            )
        )
        self.assertEqual(receipt["action_queue"], [])
        self.assertEqual(receipt["items"][0]["reason_code"], "HUMAN_REPLY_ALREADY_ANSWERED")

    def test_equal_reply_and_outbound_time_fails_closed(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "ambiguous",
                    "same-second",
                    [_event("r1", "2026-09-15T00:30:00Z", "HUMAN_QUESTION")],
                    last_outbound="2026-09-15T00:30:00Z",
                )
            )
        )
        self.assertEqual(receipt["items"][0]["disposition"], "BLOCKED")
        self.assertEqual(
            receipt["items"][0]["reason_code"], "AMBIGUOUS_REPLY_OUTBOUND_ORDER"
        )

    def test_explicit_dnr_is_terminal_even_if_later_positive_exists(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "permanent-dnr",
                    "thread-1",
                    [
                        _event("d1", "2026-09-15T00:10:00Z", "EXPLICIT_DNR"),
                        _event("d2", "2026-09-15T00:20:00Z", "HUMAN_POSITIVE"),
                    ],
                    last_outbound="2026-09-15T00:00:00Z",
                )
            )
        )
        self.assertEqual(receipt["action_queue"], [])
        self.assertEqual(receipt["items"][0]["disposition"], "TERMINAL_DNR")
        self.assertEqual(receipt["items"][0]["reason_code"], "EXPLICIT_DNR_PRESENT")

    def test_conflicting_human_meanings_same_instant_block(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "conflict",
                    "thread-1",
                    [
                        _event("c1", "2026-09-15T00:20:00Z", "HUMAN_POSITIVE"),
                        _event("c2", "2026-09-15T00:20:00Z", "EXPLICIT_DNR"),
                    ],
                )
            )
        )
        self.assertEqual(receipt["items"][0]["disposition"], "BLOCKED")
        self.assertEqual(
            receipt["items"][0]["reason_code"], "CONTRADICTORY_HUMAN_OBSERVATION"
        )

    def test_automated_ack_is_hold_not_interest(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "cloudsafe",
                    "ticket",
                    [_event("a1", "2026-09-15T00:20:00Z", "AUTOMATED_ACK")],
                    last_outbound="2026-09-15T00:19:00Z",
                )
            )
        )
        self.assertEqual(receipt["action_queue"], [])
        self.assertEqual(receipt["items"][0]["disposition"], "HOLD")
        self.assertEqual(receipt["items"][0]["reason_code"], "AUTOMATED_ACK_ONLY")

    def test_delivery_failure_blocks_repeated_send(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "delivery",
                    "failure",
                    [_event("f1", "2026-09-15T00:20:01Z", "DELIVERY_FAILURE")],
                    last_outbound="2026-09-15T00:20:00Z",
                )
            )
        )
        self.assertEqual(receipt["action_queue"], [])
        self.assertEqual(receipt["items"][0]["reason_code"], "DELIVERY_FAILURE")

    def test_human_negative_is_hold(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "negative",
                    "reply",
                    [_event("n1", "2026-09-15T00:20:01Z", "HUMAN_NEGATIVE")],
                    last_outbound="2026-09-15T00:20:00Z",
                )
            )
        )
        self.assertEqual(receipt["action_queue"], [])
        self.assertEqual(receipt["items"][0]["reason_code"], "UNANSWERED_HUMAN_NEGATIVE")

    def test_candidate_is_digest_only(self) -> None:
        secret_candidate = "Thanks for the reply — here is the scoped next step."
        receipt = triage_document(
            _document(
                _thread(
                    "positive",
                    "reply",
                    [_event("p1", "2026-09-15T00:20:01Z", "HUMAN_POSITIVE")],
                    candidate=secret_candidate,
                )
            )
        )
        expected = hashlib.sha256(secret_candidate.encode("utf-8")).hexdigest()
        self.assertEqual(receipt["items"][0]["candidate_followup_sha256"], expected)
        serialized = json.dumps(receipt)
        self.assertNotIn(secret_candidate, serialized)
        self.assertFalse(receipt["items"][0]["external_send_authorized"])

    def test_duplicate_event_id_rejected(self) -> None:
        with self.assertRaises(TriageInputError) as caught:
            triage_document(
                _document(
                    _thread(
                        "dup",
                        "event",
                        [
                            _event("same", "2026-09-15T00:20:00Z", "NO_REPLY"),
                            _event("same", "2026-09-15T00:21:00Z", "HUMAN_POSITIVE"),
                        ],
                    )
                )
            )
        self.assertEqual(caught.exception.code, "DUPLICATE_EVENT_ID")

    def test_future_observation_rejected(self) -> None:
        with self.assertRaises(TriageInputError) as caught:
            triage_document(
                _document(
                    _thread(
                        "future",
                        "event",
                        [_event("f1", "2026-09-15T01:00:00Z", "HUMAN_POSITIVE")],
                    )
                )
            )
        self.assertEqual(caught.exception.code, "FUTURE_TIMESTAMP")

    def test_duplicate_json_keys_and_nonfinite_values_rejected(self) -> None:
        with self.assertRaises(TriageInputError) as duplicate:
            loads_strict('{"schema_version":1,"schema_version":1}')
        self.assertEqual(duplicate.exception.code, "DUPLICATE_JSON_KEY")
        with self.assertRaises(TriageInputError) as nonfinite:
            loads_strict('{"value":NaN}')
        self.assertEqual(nonfinite.exception.code, "NONFINITE_JSON")

    def test_deterministic_across_thread_input_order(self) -> None:
        first = _thread(
            "z-prospect",
            "thread-z",
            [_event("z1", "2026-09-15T00:20:01Z", "HUMAN_QUESTION")],
        )
        second = _thread(
            "a-prospect",
            "thread-a",
            [_event("a1", "2026-09-15T00:20:01Z", "HUMAN_QUESTION")],
        )
        a = triage_document(_document(first, second))
        b = triage_document(_document(second, first))
        self.assertNotEqual(a["input_sha256"], b["input_sha256"])
        self.assertEqual(a["action_queue"], b["action_queue"])
        self.assertEqual(a["items"], b["items"])

    def test_no_reply_with_outbound_waits_while_no_outbound_is_cold(self) -> None:
        receipt = triage_document(
            _document(
                _thread(
                    "sent",
                    "no-reply",
                    [_event("s1", "2026-09-15T00:30:00Z", "NO_REPLY")],
                    last_outbound="2026-09-15T00:20:00Z",
                ),
                _thread("cold", "new", []),
            )
        )
        reasons = {item["reason_code"] for item in receipt["items"]}
        self.assertEqual(
            reasons,
            {"NO_HUMAN_REPLY", "NO_OUTBOUND_OR_HUMAN_REPLY"},
        )


if __name__ == "__main__":
    unittest.main()

"""Regression cases for deterministic metadata-only mail tracking."""
import copy
import itertools
import json
import unittest

from integrations.command_center.mail_tracking import (
    MAX_ACTION, MAX_ID, MAX_MESSAGES, MAX_NOTES, MAX_REFS, MAX_TEXT, MAX_URL, project,
)


NOW = "2026-09-12T20:00:00Z"
SEEN = "2026-09-12T19:59:00Z"


def source(source_id="s", mailbox="owner@example.test", complete=True):
    return {"id": source_id, "provider": "Gmail", "scope": {"mailbox": mailbox},
            "last_success_at": SEEN, "last_good_observed_at": SEEN,
            "observed_at": SEEN, "status": "live", "stale_after_seconds": 900,
            "coverage": {"complete": complete, "pagination_remaining": not complete},
            "last_good_coverage": {"complete": complete, "pagination_remaining": not complete}}


def message(message_id="m1", thread="t1", at="2026-09-12T19:00:00Z", sent=False, source_id="s", mailbox="owner@example.test"):
    return {"id": "gmail:message:" + message_id, "kind": "email", "source_id": source_id,
            "provider": "Gmail", "provider_id": message_id, "title": "Work thread",
            "owner": "Sender metadata", "updated_at": at, "activity_observed_at": at,
            "last_seen_at": SEEN, "status": "sent" if sent else "received",
            "labels": ["SENT"] if sent else ["INBOX", "UNREAD"],
            "metadata": {"email_ts": at, "from_": mailbox if sent else "sender@example.test",
                         "to": ["recipient@example.test"] if sent else [mailbox]},
            "refs": {"gmail_message_id": message_id, "gmail_thread_id": thread, "mailbox": mailbox}}


def work(items, sources=None):
    return {"sources": sources if sources is not None else [source()], "items": items}


class MailTrackingTests(unittest.TestCase):
    def test_actual_metadata_schema_orders_turns_and_preserves_input(self):
        data = work([message("a"), message("b", at="2026-09-12T19:30:00Z", sent=True)])
        before = copy.deepcopy(data)
        result = project(data, NOW)
        self.assertEqual(data, before)
        row = result["threads"][0]
        self.assertEqual(row["thread_id"], "t1")
        self.assertEqual(row["message_count"], 2)
        self.assertEqual(row["last_inbound_at"], "2026-09-12T19:00:00Z")
        self.assertEqual(row["last_outbound_at"], "2026-09-12T19:30:00Z")
        self.assertEqual(row["waiting_on"], "waiting_on_them")
        self.assertTrue(row["unread"])
        self.assertIsNone(row["owner"])
        self.assertIsNone(row["assigned_owner"])
        self.assertIsNone(row["owner_source"])
        self.assertEqual(row["source_owner"], "Sender metadata")

    def test_same_thread_and_message_ids_are_scoped_to_account(self):
        data = work([message(), message(mailbox="second@example.test", source_id="second")],
                    [source(), source("second", "second@example.test")])
        result = project(data, NOW)
        self.assertEqual(result["counts"]["messages"], 2)
        self.assertEqual(result["counts"]["threads"], 2)

    def test_duplicate_messages_prefer_latest_observation(self):
        old, new = message(source_id="old"), message(source_id="new")
        old["last_seen_at"] = "2026-09-12T19:58:00Z"
        new["labels"] = ["INBOX"]
        data = work([new, old], [source("old"), source("new")])
        result = project(data, NOW)
        row = result["threads"][0]
        self.assertEqual(row["message_count"], 1)
        self.assertFalse(row["unread"])
        self.assertEqual(result["counts"]["duplicate_records"], 1)
        self.assertEqual(project(work(list(reversed(data["items"])), data["sources"]), NOW), result)

    def test_tied_conflicting_duplicates_never_claim_current_turn(self):
        first, second = message(source_id="a"), message(source_id="b", sent=True)
        data = work([first, second], [source("a"), source("b")])
        row = project(data, NOW)["threads"][0]
        self.assertEqual(row["waiting_on"], "unknown")
        self.assertIn("conflicting_duplicate_observation", row["waiting_reasons"])
        self.assertIsNone(row["unread"])
        self.assertEqual(row["messages"][0]["direction"], "unknown")
        self.assertTrue(row["current_observation"])
        self.assertNotIn("stale_or_retained_source", row["waiting_reasons"])

    def test_partial_or_stale_source_preserves_observed_turn_only(self):
        for src in (source(complete=False), source()):
            if src["coverage"]["complete"]:
                src["last_good_observed_at"] = "2026-09-08T03:50:21Z"
            row = project(work([message()], [src]), NOW)["threads"][0]
            self.assertEqual(row["observed_waiting_on"], "waiting_on_us")
            self.assertEqual(row["waiting_on"], "unknown")

    def test_failed_attempt_and_future_watermark_cannot_refresh_old_data(self):
        for good in ("2026-09-08T03:50:21Z", "2026-09-13T20:00:00Z", None):
            src = source()
            src.update(last_good_observed_at=good, observed_at=NOW)
            if good and good.startswith("2026-09-08"):
                src.update(status="error", error="rate_limited", retained_last_good=True)
            row = project(work([message()], [src]), NOW)["threads"][0]
            self.assertFalse(row["current_observation"])
            self.assertEqual(row["waiting_on"], "unknown")

    def test_missing_account_thread_or_message_identity_stays_separate(self):
        one, two = message("one"), message("two")
        for row in (one, two):
            row["refs"] = {}
            row.pop("provider_id")
        result = project(work([one, two], [{"id": "s", "provider": "Gmail"}]), NOW)
        self.assertEqual(result["counts"]["threads"], 2)
        self.assertTrue(all(row["waiting_on"] == "unknown" for row in result["threads"]))
        self.assertTrue(all(not row["identity_complete"] for row in result["threads"]))

    def test_self_mail_is_not_waiting_on_someone_else(self):
        row = message(sent=True)
        row["labels"] = ["SENT", "INBOX"]
        row["metadata"]["to"] = ["owner@example.test"]
        thread = project(work([row]), NOW)["threads"][0]
        self.assertEqual(thread["waiting_on"], "unknown")
        self.assertIsNone(thread["last_outbound_at"])

    def test_draft_does_not_turn_a_received_message_into_a_sent_reply(self):
        draft = message("draft", at="2026-09-12T19:45:00Z", sent=True)
        draft["labels"] = ["DRAFT"]
        row = project(work([message(), draft]), NOW)["threads"][0]
        self.assertEqual(row["waiting_on"], "waiting_on_us")
        self.assertIsNone(row["last_outbound_at"])

    def test_equal_or_missing_message_times_do_not_guess_turn_order(self):
        row = project(work([message("one"), message("two", sent=True)]), NOW)["threads"][0]
        self.assertEqual(row["waiting_on"], "unknown")
        missing = message("missing", sent=True)
        missing["metadata"].pop("email_ts")
        missing.pop("updated_at")
        missing.pop("activity_observed_at")
        row = project(work([message(), missing]), NOW)["threads"][0]
        self.assertEqual(row["waiting_on"], "unknown")

    def test_owner_directive_on_older_message_survives_dedupe_and_zero_sorts_first(self):
        old, new = message("old"), message("new", at="2026-09-12T19:30:00Z", sent=True)
        old["owner_work"] = {"priority": "0", "next_action": "Prepare requested sample", "updated_at": NOW}
        other = message("other", thread="other")
        other["priority"] = 2
        row = project(work([other, new, old]), NOW)["threads"][0]
        self.assertEqual(row["thread_id"], "t1")
        self.assertEqual(row["priority"], "0")
        self.assertEqual(row["next_action"], "Prepare requested sample")
        self.assertEqual(row["directive_ref"]["item_id"], old["id"])

    def test_explicit_owner_clear_does_not_resurrect_inferred_next_action(self):
        item = message()
        item["next_action"] = "Old source action"
        item["owner_work"] = {"next_action": None, "updated_at": NOW}
        self.assertIsNone(project(work([item]), NOW)["threads"][0]["next_action"])

    def test_due_and_overdue_use_explicit_timezone_aware_metadata(self):
        item = message()
        item["due_at"] = "2026-09-12T14:00:00-05:00"
        row = project(work([item]), NOW)["threads"][0]
        self.assertEqual(row["due_at"], "2026-09-12T19:00:00Z")
        self.assertTrue(row["overdue"])
        item["owner_work"] = {"job": {"id": "job-1", "status": "prepared", "dispatch_status": "not_dispatched", "due_at": "2026-09-12T21:00:00Z"}, "updated_at": NOW}
        row = project(work([item]), NOW)["threads"][0]
        self.assertFalse(row["overdue"])
        self.assertEqual(row["due_source"], "owner_work.job.due_at")
        self.assertEqual(row["prepared_job"]["dispatch_status"], "not_dispatched")

    def test_source_coverage_survives_empty_mailbox_projection(self):
        result = project(work([], [source(complete=False)]), NOW)
        self.assertEqual(result["threads"], [])
        self.assertEqual(len(result["sources"]), 1)
        self.assertFalse(result["coverage"]["complete"])
        self.assertFalse(project(work([], []), NOW)["coverage"]["complete"])

    def test_prose_never_becomes_payment_state_and_raw_fields_are_not_projected(self):
        item = message()
        item.update(title="Payment confirmed", summary="Paid $90", body="PRIVATE_BODY_MARKER")
        item["metadata"]["snippet"] = "PRIVATE_SNIPPET_MARKER"
        row = project(work([item]), NOW)["threads"][0]
        self.assertNotIn("paid", row)
        self.assertNotIn("payment_status", row)
        serialized = json.dumps(row)
        self.assertNotIn("PRIVATE_BODY_MARKER", serialized)
        self.assertNotIn("PRIVATE_SNIPPET_MARKER", serialized)
        self.assertNotIn("summary", row)

    def test_timezone_normalization_and_invalid_now(self):
        item = message(at="2026-09-12T14:00:00-05:00")
        self.assertEqual(project(work([item]), NOW)["threads"][0]["last_inbound_at"], "2026-09-12T19:00:00Z")
        with self.assertRaises(ValueError):
            project(work([]), "2026-09-12T20:00:00")

    def test_explicit_assignment_is_separate_from_sender_and_clear_is_respected(self):
        item = message()
        item["owner_work"] = {"job": {"owner": "Responder", "id": "job-1"}, "updated_at": NOW}
        row = project(work([item]), NOW)["threads"][0]
        self.assertEqual(row["assigned_owner"], "Responder")
        self.assertEqual(row["owner"], "Responder")
        self.assertEqual(row["assigned_owner_source"], "owner_work.job.owner")
        self.assertEqual(row["source_owner"], "Sender metadata")
        item["owner_work"]["owner"] = None
        row = project(work([item]), NOW)["threads"][0]
        self.assertIsNone(row["assigned_owner"])
        self.assertEqual(row["assigned_owner_source"], "owner_work.owner")
        item["owner_work"]["owner"] = "Explicit responder"
        self.assertEqual(project(work([item]), NOW)["threads"][0]["assigned_owner"], "Explicit responder")

    def test_stale_duplicate_does_not_poison_equivalent_fresh_complete_thread(self):
        stale, fresh = message(source_id="stale"), message(source_id="fresh")
        stale["last_seen_at"] = "2026-09-08T03:51:00Z"
        stale["owner_work"] = {"priority": 0, "next_action": "Keep owner direction", "updated_at": NOW}
        stale_source = source("stale", complete=False)
        stale_source.update(last_good_observed_at="2026-09-08T03:50:00Z", retained_last_good=True)
        data = work([stale, fresh], [stale_source, source("fresh")])
        result = project(data, NOW)
        row = result["threads"][0]
        self.assertTrue(row["current_observation"])
        self.assertTrue(row["coverage_complete"])
        self.assertTrue(row["current_complete_observation"])
        self.assertEqual(row["waiting_on"], "waiting_on_us")
        self.assertEqual(row["messages"][0]["source_id"], "fresh")
        self.assertEqual(row["next_action"], "Keep owner direction")
        self.assertEqual(row["priority"], 0)
        self.assertEqual(row["source_ids"], ["fresh", "stale"])
        self.assertFalse(result["coverage"]["current"])
        self.assertFalse(result["coverage"]["complete"])

    def test_retained_or_error_flag_alone_prevents_current_freshness(self):
        for change in ({"retained_last_good": True}, {"error": "rate_limited"}, {"data_stale": True}):
            src = source()
            src.update(change)
            result = project(work([message()], [src]), NOW)
            self.assertFalse(result["sources"][0]["current"])
            self.assertEqual(result["threads"][0]["waiting_on"], "unknown")

    def test_current_partial_and_old_complete_copies_cannot_be_combined_into_current_complete(self):
        old_source = source("old")
        old_source["last_good_observed_at"] = "2026-09-08T03:50:00Z"
        data = work([message(source_id="old"), message(source_id="fresh")], [old_source, source("fresh", complete=False)])
        row = project(data, NOW)["threads"][0]
        self.assertTrue(row["current_observation"])
        self.assertTrue(row["coverage_complete"])
        self.assertFalse(row["current_complete_observation"])
        self.assertEqual(row["waiting_on"], "unknown")
        self.assertIn("no_current_complete_observation", row["waiting_reasons"])

    def test_retained_ingest_time_does_not_outvote_a_newer_actual_observation(self):
        retained, fresh = message(source_id="retained"), message(source_id="fresh")
        retained["last_seen_at"] = NOW
        fresh["labels"] = ["INBOX"]
        retained_source = source("retained")
        retained_source.update(last_good_observed_at="2026-09-08T03:50:00Z", retained_last_good=True)
        row = project(work([retained, fresh], [retained_source, source("fresh")]), NOW)["threads"][0]
        self.assertFalse(row["unread"])
        self.assertEqual(row["messages"][0]["source_id"], "fresh")
        self.assertEqual(row["waiting_on"], "waiting_on_us")

    def test_three_way_duplicate_conflicts_are_permutation_invariant(self):
        rows = [message(source_id="a"), message(source_id="b", sent=True), message(source_id="c")]
        sources = [source("a"), source("b"), source("c")]
        expected = project(work(rows, sources), NOW)
        self.assertEqual(expected["threads"][0]["messages"][0]["direction"], "unknown")
        for permutation in itertools.permutations(rows):
            self.assertEqual(project(work(list(permutation), sources), NOW), expected)

    def test_conflicting_thread_ids_do_not_join_one_arbitrary_provider_thread(self):
        rows = [message(thread="one", source_id="a"), message(thread="two", source_id="b"),
                message(thread="one", source_id="c")]
        sources = [source("a"), source("b"), source("c")]
        expected = project(work(rows, sources), NOW)
        self.assertEqual(expected["counts"]["messages"], 1)
        self.assertIsNone(expected["threads"][0]["thread_id"])
        self.assertFalse(expected["threads"][0]["identity_complete"])
        for permutation in itertools.permutations(rows):
            self.assertEqual(project(work(list(permutation), sources), NOW), expected)

    def test_thread_details_are_bounded_without_changing_full_thread_or_message_counts(self):
        rows = [message(str(index)) for index in range(max(MAX_MESSAGES, MAX_REFS) + 7)]
        result = project(work(rows), NOW)
        row = result["threads"][0]
        self.assertEqual(row["message_count"], len(rows))
        self.assertEqual(len(row["messages"]), MAX_MESSAGES)
        self.assertEqual(row["messages_omitted"], len(rows) - MAX_MESSAGES)
        self.assertEqual(len(row["record_refs"]), MAX_REFS)
        self.assertEqual(row["record_refs_omitted"], len(rows) - MAX_REFS)
        self.assertEqual(result["counts"]["messages"], len(rows))
        many_threads = [message(str(index), thread=str(index)) for index in range(201)]
        self.assertEqual(len(project(work(many_threads), NOW)["threads"]), 201)

    def test_long_or_nested_fields_cannot_bypass_metadata_output_bounds(self):
        item = message()
        item.update(title="t" * (MAX_TEXT + 30), url="https://example.test/" + "u" * MAX_URL)
        item["owner_work"] = {"next_action": "a" * (MAX_ACTION + 20), "priority": {"nested": "PRIVATE_PRIORITY"},
                              "job": {"owner": "o" * (MAX_TEXT + 10), "id": "i" * (MAX_ID + 1),
                                      "status": {"nested": "PRIVATE_JOB"}}, "updated_at": NOW}
        src = source()
        src["last_good_coverage"]["notes"] = ["n" * (MAX_TEXT + 10)] * (MAX_NOTES + 3)
        src["last_good_coverage"]["pagination_remaining"] = {"nested": "PRIVATE_PAGINATION"}
        result = project(work([item], [src]), NOW)
        row = result["threads"][0]
        self.assertEqual(len(row["title"]), MAX_TEXT)
        self.assertEqual(len(row["url"]), MAX_URL)
        self.assertEqual(len(row["next_action"]), MAX_ACTION)
        self.assertEqual(len(row["assigned_owner"]), MAX_TEXT)
        self.assertIsNone(row["priority"])
        self.assertIsNone(row["prepared_job"]["id"])
        self.assertIn("prepared_job.id", row["identifiers_omitted"])
        self.assertIn("next_action", row["truncated_fields"])
        coverage = result["sources"][0]["coverage"]
        self.assertEqual(len(coverage["notes"]), MAX_NOTES)
        self.assertEqual(coverage["notes_omitted"], 3)
        self.assertEqual(coverage["note_texts_truncated"], MAX_NOTES)
        self.assertIsNone(coverage["pagination_remaining"])
        self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_missing_lists_and_nonfinite_metadata_do_not_crash_projection(self):
        self.assertEqual(project({"items": None, "sources": None}, NOW)["threads"], [])
        for value in (float("inf"), float("nan"), 10 ** 1000):
            item, src = message(), source()
            item["priority"] = value
            src["stale_after_seconds"] = value
            row = project(work([item], [src]), NOW)["threads"][0]
            self.assertIsNone(row["priority"])
            self.assertEqual(row["waiting_on"], "unknown")

    def test_future_message_time_does_not_create_a_current_turn(self):
        row = project(work([message(at="2026-09-13T20:00:00Z")]), NOW)["threads"][0]
        self.assertEqual(row["observed_waiting_on"], "unknown")
        self.assertEqual(row["waiting_on"], "unknown")

    def test_stale_duplicate_due_date_does_not_replace_fresh_explicit_clear(self):
        old, fresh = message(source_id="old"), message(source_id="fresh")
        old["due_at"] = "2026-09-12T19:00:00Z"
        old["last_seen_at"] = NOW
        fresh["due_at"] = None
        old_source = source("old")
        old_source.update(last_good_observed_at="2026-09-12T19:00:00Z", retained_last_good=True)
        row = project(work([old, fresh], [old_source, source("fresh")]), NOW)["threads"][0]
        self.assertIsNone(row["due_at"])
        self.assertIsNone(row["overdue"])

    def test_fractional_provider_times_are_compared_chronologically_not_as_text(self):
        rows = [message("one", at="2026-09-12T19:00:00Z"),
                message("two", at="2026-09-12T19:00:00.900Z"),
                message("three", at="2026-09-12T19:00:00.100Z")]
        row = project(work(rows), NOW)["threads"][0]
        self.assertEqual(row["last_inbound_at"], "2026-09-12T19:00:00.900000Z")
        # Build actual outbound envelopes; changing only SENT would leave
        # the mailbox as sole recipient and exercise self-mail, not outbound.
        outbound = [message(str(n), at=item["metadata"]["email_ts"], sent=True)
                    for n, item in enumerate(rows)]
        row = project(work(outbound), NOW)["threads"][0]
        self.assertEqual(row["last_outbound_at"], "2026-09-12T19:00:00.900000Z")


if __name__ == "__main__":
    unittest.main()


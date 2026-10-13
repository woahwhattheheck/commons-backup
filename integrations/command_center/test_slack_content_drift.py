"""Synthetic provider regressions for observed Slack message-generation drift.

These tests execute the real bounded reader, not Slack or a deployed collector.
They deliberately contain no retained workspace messages or account metadata.
"""
from __future__ import annotations

import copy
import json
import unittest

from integrations.command_center import slack_threads as subject

ROOT = "1700000000.000001"
REPLY = "1700000001.000001"
SECOND = "1700000002.000001"
CHANNEL = "C_SYNTHETIC"


def parent(**changes):
    return {"ts": ROOT, "text": "SYNTHETIC: work remains assigned",
            "user": "U_SYNTHETIC", "reply_count": 1, "latest_reply": REPLY,
            **changes}


def child(**changes):
    return {"ts": REPLY, "thread_ts": ROOT, "text": "SYNTHETIC: claimed",
            "user": "U_SYNTHETIC", **changes}


def page(rows, cursor="", **changes):
    return {"ok": True, "messages": rows,
            "response_metadata": {"next_cursor": cursor}, **changes}


class Reader:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, payload):
        self.calls.append((method, dict(payload)))
        expected, value = self.responses.pop(0)
        if method != expected:
            raise AssertionError("unexpected read method")
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class SlackContentDriftTests(unittest.TestCase):
    def history(self, *responses):
        reader = Reader([("conversations.history", response) for response in responses])
        result = subject.read_channel(reader, CHANNEL, page_size=10,
                                      max_pages=len(responses), max_threads=0)
        self.assertEqual(reader.responses, [])
        return result, reader

    def thread(self, history, *responses, max_pages=1):
        reader = Reader([("conversations.history", history)] +
                        [("conversations.replies", response) for response in responses])
        result = subject.read_channel(reader, CHANNEL, page_size=10,
            max_pages=max_pages, max_threads=1, max_thread_pages=len(responses))
        self.assertEqual(reader.responses, [])
        self.assertTrue(all(call[1].get("ts") == ROOT for call in reader.calls[1:]))
        return result, reader

    def assert_thread_drift(self, result):
        rows, metadata, complete = result
        self.assertFalse(complete)
        self.assertFalse(metadata["thread_coverage"][0]["complete"])
        self.assertEqual(metadata["thread_coverage"][0]["reason"], "thread_evidence_changed")
        self.assertEqual(metadata["threads_complete_count"], 0)
        self.assertEqual(metadata["threads_pending_count"], 1)
        return {row["ts"]: row for row in rows}, metadata

    def test_stable_overlapping_history_stays_complete(self):
        row = {"ts": ROOT, "text": "SYNTHETIC", "user": "U_SYNTHETIC"}
        (rows, meta, complete), reader = self.history(page([row], "next"), page([row]))
        self.assertTrue(complete)
        self.assertEqual(len(rows), 1)
        self.assertTrue(meta["history_complete"])
        self.assertEqual(reader.calls[1][1]["cursor"], "next")

    def test_changed_claim_text_in_history_is_not_complete(self):
        old = {"ts": ROOT, "text": "SYNTHETIC: claimed"}
        new = {**old, "text": "SYNTHETIC: released"}
        (rows, meta, complete), reader = self.history(page([old], "next"), page([new]))
        self.assertFalse(complete)
        self.assertEqual(meta["history"]["reason"], "thread_evidence_changed")
        self.assertEqual(rows, [new])
        self.assertEqual(len(reader.calls), 2)

    def test_each_semantic_generation_field_is_checked(self):
        base = {"ts": ROOT, "text": "SYNTHETIC", "user": "U_FIRST", "bot_id": "B_FIRST"}
        changes = ({"user": "U_SECOND"}, {"bot_id": "B_SECOND"},
                   {"subtype": "message_deleted"},
                   {"edited": {"ts": SECOND, "user": "U_EDITOR"}})
        for change in changes:
            with self.subTest(change=change):
                (_, meta, complete), _ = self.history(page([base], "next"), page([{**base, **change}]))
                self.assertFalse(complete)
                self.assertEqual(meta["history"]["reason"], "thread_evidence_changed")

    def test_edit_generation_change_with_same_text_is_not_complete(self):
        old = {"ts": ROOT, "text": "SYNTHETIC", "edited": {"ts": REPLY}}
        new = {**old, "edited": {"ts": SECOND}}
        (_, meta, complete), _ = self.history(page([old], "next"), page([new]))
        self.assertFalse(complete)
        self.assertEqual(meta["history"]["reason"], "thread_evidence_changed")

    def test_removed_text_or_edit_marker_is_observed_drift(self):
        for key in ("text", "edited"):
            old = {"ts": ROOT, "text": "SYNTHETIC", "edited": {"ts": REPLY}}
            new = {name: value for name, value in old.items() if name != key}
            with self.subTest(key=key):
                (_, _, complete), _ = self.history(page([old], "next"), page([new]))
                self.assertFalse(complete)

    def test_drift_in_a_single_page_cannot_hide_behind_deduplication(self):
        old = {"ts": ROOT, "text": "SYNTHETIC: first"}
        new = {"ts": ROOT, "text": "SYNTHETIC: second"}
        (rows, _, complete), _ = self.history(page([old, new]))
        self.assertFalse(complete)
        self.assertEqual(rows, [new])

    def test_later_stable_page_cannot_clear_earlier_drift(self):
        old = {"ts": ROOT, "text": "SYNTHETIC: first"}
        new = {"ts": ROOT, "text": "SYNTHETIC: second"}
        (_, meta, complete), _ = self.history(page([old], "a"), page([new], "b"), page([new]))
        self.assertFalse(complete)
        self.assertEqual(meta["history"]["pages_read"], 3)

    def test_unrelated_presentation_metadata_does_not_force_reread(self):
        old = {"ts": ROOT, "text": "SYNTHETIC", "reactions": []}
        new = {**old, "reactions": [{"name": "eyes", "count": 1}], "user_profile": {"display_name": "changed"}}
        (rows, _, complete), reader = self.history(page([old], "next"), page([new]))
        self.assertTrue(complete)
        self.assertEqual(rows, [new])
        self.assertEqual(len(reader.calls), 2)

    def test_stable_root_and_complete_replies_are_complete(self):
        result, reader = self.thread(page([parent()]), page([parent(), child()]))
        self.assertTrue(result[2])
        self.assertEqual(result[1]["threads_complete_count"], 1)
        self.assertEqual(len(reader.calls), 2)

    def test_root_claim_edit_between_history_and_replies_is_incomplete(self):
        newer = parent(text="SYNTHETIC: owner changed", edited={"ts": SECOND})
        result, _ = self.thread(page([parent()]), page([newer, child()]))
        rows, meta = self.assert_thread_drift(result)
        self.assertTrue(meta["history_complete"])
        self.assertEqual(rows[ROOT], newer)

    def test_broadcast_reply_content_change_between_endpoints_is_incomplete(self):
        broadcast = child(subtype="thread_broadcast")
        newer = child(text="SYNTHETIC: released")
        result, _ = self.thread(page([parent(), broadcast]), page([parent(), newer]))
        rows, _ = self.assert_thread_drift(result)
        self.assertEqual(rows[REPLY], newer)

    def test_broadcast_wrapper_and_self_thread_root_are_equivalent(self):
        result, _ = self.thread(page([parent(), child(subtype="thread_broadcast")]),
            page([parent(thread_ts=ROOT), child()]))
        self.assertTrue(result[2])
        self.assertEqual(len(result[0]), 2)

    def test_reply_page_edit_is_incomplete_and_keeps_latest_observation(self):
        newer = child(text="SYNTHETIC: changed on page two", edited={"ts": SECOND})
        result, _ = self.thread(page([parent()]), page([parent(), child()], "next"), page([newer]))
        rows, _ = self.assert_thread_drift(result)
        self.assertEqual(rows[REPLY], newer)

    def test_changed_author_between_history_and_replies_is_incomplete(self):
        result, _ = self.thread(page([parent()]), page([parent(user="U_OTHER"), child()]))
        self.assert_thread_drift(result)

    def test_count_growth_cannot_claim_one_consistent_generation(self):
        newer = parent(reply_count=2, latest_reply=SECOND)
        result, _ = self.thread(page([parent()]),
            page([newer, child(), child(ts=SECOND)]))
        self.assert_thread_drift(result)

    def test_missing_root_remains_pending(self):
        result, _ = self.thread(page([parent()]), page([child()]))
        self.assertFalse(result[2])
        self.assertEqual(result[1]["thread_coverage"][0]["reason"], "reply_evidence_mismatch")

    def test_error_still_keeps_valid_rows_and_sanitizes_provider_text(self):
        result, reader = self.thread(page([parent()]), page([parent(), child()], "next"),
                                    RuntimeError("SYNTHETIC_PRIVATE_ERROR"))
        self.assertFalse(result[2])
        self.assertEqual(len(result[0]), 2)
        report = result[1]["thread_coverage"][0]
        self.assertEqual(report["reason"], "read_failed")
        self.assertEqual(report["error"], {"code": "slack_read_failed"})
        self.assertNotIn("SYNTHETIC_PRIVATE_ERROR", json.dumps(result[1]))
        self.assertEqual(len(reader.calls), 3)

    def test_existing_pagination_failure_reason_has_priority(self):
        old = {"ts": ROOT, "text": "SYNTHETIC: first"}
        new = {"ts": ROOT, "text": "SYNTHETIC: second"}
        for changes, reason in (({"has_more": True}, "cursor_missing"),
                                ({"is_limited": True}, "history_limited")):
            with self.subTest(reason=reason):
                (_, meta, complete), _ = self.history(page([old], "next"), page([new], **changes))
                self.assertFalse(complete)
                self.assertEqual(meta["history"]["reason"], reason)

    def test_no_claim_text_or_authors_added_to_coverage_metadata(self):
        newer = parent(text="SYNTHETIC_PRIVATE_CONTENT", user="U_PRIVATE_SENTINEL")
        result, _ = self.thread(page([parent()]), page([newer, child()]))
        self.assert_thread_drift(result)
        serialized = json.dumps(result[1])
        self.assertNotIn("SYNTHETIC_PRIVATE_CONTENT", serialized)
        self.assertNotIn("U_PRIVATE_SENTINEL", serialized)

    def test_reused_provider_dict_cannot_erase_duplicate_edit_history(self):
        shared = {"ts": ROOT, "text": "SYNTHETIC: first", "edited": {"ts": REPLY}}
        calls = []
        def read(method, payload):
            calls.append((method, payload))
            if len(calls) == 1:
                return page([shared], "next")
            shared["text"] = "SYNTHETIC: second"
            shared["edited"]["ts"] = SECOND
            return page([shared])
        rows, meta, complete = subject.read_channel(read, CHANNEL, page_size=10, max_pages=2)
        self.assertFalse(complete)
        self.assertEqual(meta["history"]["reason"], "thread_evidence_changed")
        self.assertEqual(rows[0]["text"], "SYNTHETIC: second")

    def test_changed_history_stays_incomplete_after_consistent_thread_read(self):
        newer = parent(text="SYNTHETIC: reassigned")
        reader = Reader([("conversations.history", page([parent()], "next")),
                         ("conversations.history", page([newer])),
                         ("conversations.replies", page([newer, child()]))])
        _, meta, complete = subject.read_channel(reader, CHANNEL, page_size=10,
            max_pages=2, max_threads=1, max_thread_pages=1)
        self.assertFalse(complete)
        self.assertFalse(meta["history_complete"])


if __name__ == "__main__":
    unittest.main()

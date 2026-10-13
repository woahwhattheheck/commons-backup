"""Focused pure projection contracts. Intended for cloud CI; no provider calls."""
import copy
import json
import unittest
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from .context_view import INPUT_SCHEMA, build_index, project, select

NOW = "2026-09-13T02:00:00Z"
WHEN = datetime.fromisoformat(NOW.replace("Z", "+00:00"))


def source(key="s", **extra):
    return {"id": key, "provider": "GitHub", "status": "live",
            "observed_at": NOW, "last_good_observed_at": NOW,
            "last_success_at": NOW, "last_attempt_at": NOW,
            "coverage": {"complete": True}, "stale_after_seconds": 900, **extra}


def item(key="1", source_id="s", **extra):
    return {"id": key, "source_id": source_id, "kind": "issue", "status": "open",
            "title": "Useful repair", "owner": "Ann", "last_seen_at": NOW, **extra}


def work(items=None, sources=None, **extra):
    return {"sources": [source()] if sources is None else sources,
            "items": [item()] if items is None else items,
            "observed_at": NOW, **extra}


class ContextViewContracts(unittest.TestCase):
    def test_default_page_and_full_inventory_reachability(self):
        state = work([item(f"{n:03}") for n in range(47)])
        first = project(state, now=WHEN)
        second = project(state, now=WHEN, offset=20)
        final = project(state, now=WHEN, offset=40)
        self.assertEqual([20, 20, 7], [r["counts"]["page_records"] for r in (first, second, final)])
        self.assertEqual(47, first["counts"]["matching_records"])
        self.assertEqual(27, first["omissions"]["records_after_page"])
        self.assertEqual(40, final["omissions"]["records_before_page"])
        self.assertIsNone(final["pagination"]["next_offset"])
        ids = [row["item_id"] for r in (first, second, final) for row in r["items"]]
        self.assertEqual(47, len(set(ids)))
        self.assertEqual(0, first["provider_requests"])

    def test_filters_are_exact_and_combined_before_pagination(self):
        state = work([item("1"), item("2", owner="Joanne"),
                      item("3", status="closed"), item("4", source_id="other")],
                     [source(), source("other", provider="Slack")])
        result = project(state, now=WHEN, owner="ANN", provider="github", source="s",
                         kind="ISSUE", status="OPEN", query="repair", limit=1)
        self.assertEqual(["1"], [row["item_id"] for row in result["items"]])
        self.assertEqual(1, result["counts"]["matching_records"])
        self.assertEqual(3, result["omissions"]["filtered_records"])
        self.assertEqual(0, project(state, now=WHEN, source="S")["counts"]["matching_records"])

    def test_exact_filters_use_full_normalized_values_not_display_prefixes(self):
        long_value = "a" * 512 + "b"
        for field in ("owner", "provider", "kind", "status"):
            with self.subTest(field=field):
                state = work([item(**{field: long_value})])
                result = project(state, now=WHEN, **{field: "a" * 512})
                self.assertEqual(0, result["counts"]["matching_records"])
                result = project(state, now=WHEN, **{field: long_value})
                self.assertEqual(1, result["counts"]["matching_records"])
                self.assertEqual(512, len(result["items"][0][field]))
                self.assertNotIn("_exact_filters", result["items"][0])
        padded = work([item(owner=" Ann ")])
        self.assertEqual(0, project(padded, now=WHEN, owner="Ann")["counts"]["matching_records"])
        self.assertEqual(1, project(padded, now=WHEN, owner=" Ann ")["counts"]["matching_records"])

    def test_owner_is_not_assignment_and_mail_sender_stays_unassigned(self):
        state = work([item(kind="email", owner="Sender <sender@example.com>",
                           owner_work={"priority": 0})])
        row = project(state, now=WHEN)["items"][0]
        self.assertEqual("provider_record", row["owner_basis"])
        self.assertIsNone(row["assigned_owner"])
        state["items"][0]["owner_work"]["job"] = {"owner": "Builder", "id": "prepared"}
        row = project(state, now=WHEN)["items"][0]
        self.assertEqual("Builder", row["assigned_owner"])
        self.assertEqual("owner_work.job.owner", row["assigned_owner_basis"])
        self.assertEqual(0, project(state, now=WHEN, owner="Builder")["counts"]["matching_records"])
        state["items"][0]["owner_work"]["owner"] = None
        self.assertIsNone(project(state, now=WHEN)["items"][0]["assigned_owner"])

    def test_priority_zero_null_override_and_actual_activity_order(self):
        rows = [item("old", updated_at="2026-09-12T00:00:00Z", last_seen_at="2026-09-13T02:00:01Z"),
                item("new", activity_observed_at="2026-09-13T01:00:00Z"),
                item("first", priority=8, owner_work={"priority": "0"}),
                item("cleared", priority=0, owner_work={"priority": None})]
        result = project(work(rows), now=WHEN)
        self.assertEqual(["first", "new", "old", "cleared"], [r["item_id"] for r in result["items"]])
        self.assertIsNone(result["items"][-1]["priority"])
        self.assertIsNone(result["items"][-1]["activity_at"])

    def test_text_priority_is_preserved_without_invented_numeric_rank(self):
        row = project(work([item(priority=2, owner_work={"priority": "P0"})]), now=WHEN)["items"][0]
        self.assertEqual("P0", row["priority"])
        self.assertIsNone(row["priority_rank"])
        self.assertEqual("owner_work.priority", row["priority_basis"])

    def test_source_item_identity_and_order_ignore_input_order(self):
        state = work([item("same", source_id="b"), item("same", source_id="a")],
                     [source("b"), source("a")])
        first = project(state, now=WHEN)
        state["items"].reverse()
        state["sources"].reverse()
        second = project(state, now=WHEN)
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(["a", "b"], [r["source_id"] for r in first["items"]])
        self.assertEqual(2, first["counts"]["matching_records"])

    def test_read_clocks_do_not_change_revision(self):
        state = work()
        first = project(state, now=WHEN)
        state["observed_at"] = "2026-09-13T02:00:01Z"
        state["sources"][0]["age_seconds"] = 1
        second = project(state, now=WHEN + timedelta(seconds=1), if_revision=first["revision"])
        self.assertTrue(second["unchanged"])
        self.assertEqual([], second["items"])
        self.assertNotEqual(first["evaluated_at"], second["evaluated_at"])
        self.assertEqual(1, second["omissions"]["unchanged_records"])
        self.assertEqual(0, second["counts"]["returned_records"])
        self.assertEqual(1, len(second["sources"]))

    def test_freshness_threshold_changes_revision_without_database_change(self):
        state = work()
        first = project(state, now=WHEN)
        stale = project(state, now=WHEN + timedelta(seconds=901), if_revision=first["revision"])
        self.assertFalse(stale["unchanged"])
        self.assertEqual("stale", stale["items"][0]["freshness"])
        self.assertEqual("stale", stale["sources"][0]["freshness"])

    def test_retained_source_and_partial_old_item_are_not_current(self):
        for changes in ({"retained_last_good": True}, {"error": "temporary"},
                        {"status": "offline"}):
            with self.subTest(changes=changes):
                row = project(work(sources=[source(**changes)]), now=WHEN)["items"][0]
                self.assertEqual("retained", row["freshness"])
        row = project(work([item(last_seen_at="2026-09-13T01:00:00Z")]), now=WHEN)["items"][0]
        self.assertEqual("retained", row["freshness"])
        self.assertEqual("2026-09-13T01:00:00Z", row["last_ingested_at"])
        self.assertEqual(NOW, row["source_observed_at"])

    def test_missing_or_skewed_timestamps_are_not_activity(self):
        row = project(work([item(updated_at="2026-09-14T00:00:00Z")],
                           [source(last_good_observed_at="2026-09-14T00:00:00Z")]),
                      now=WHEN)["items"][0]
        self.assertEqual("unknown", row["freshness"])
        self.assertIsNone(row["activity_at"])
        self.assertEqual("2026-09-14T00:00:00Z", row["updated_at"])
        row = project(work([item(last_seen_at=None)]), now=WHEN)["items"][0]
        self.assertEqual("unknown", row["freshness"])
        self.assertIsNone(row["activity_at"])

    def test_revision_changes_for_visible_content_coverage_and_off_page_identity(self):
        baseline = work()
        original = project(baseline, now=WHEN)["revision"]
        variants = []
        changed = copy.deepcopy(baseline)
        changed["items"][0]["owner_work"] = {"next_action": "Review exact artifact"}
        variants.append(changed)
        changed = copy.deepcopy(baseline)
        changed["sources"][0]["coverage"]["complete"] = False
        variants.append(changed)
        changed = copy.deepcopy(baseline)
        changed["items"].append(item("off-page"))
        variants.append(changed)
        for changed in variants:
            self.assertNotEqual(original, project(changed, now=WHEN)["revision"])

    def test_revision_is_bound_to_filter_and_page(self):
        state = work([item(f"{n:03}") for n in range(25)])
        first = project(state, now=WHEN)
        for options in ({"offset": 20}, {"limit": 10}, {"owner": "Ann"}):
            result = project(state, now=WHEN, if_revision=first["revision"], **options)
            self.assertFalse(result["unchanged"])
            self.assertEqual(first["content_revision"], result["content_revision"])

    def test_compact_whitelist_and_search_never_pass_hidden_fields(self):
        state = work([item(summary="HIDDEN_SENTINEL", body="HIDDEN_SENTINEL",
                           refs={"token": "HIDDEN_SENTINEL"},
                           metadata={"notes": ["HIDDEN_SENTINEL"] * 100},
                           owner_work={"job": {"secret": "HIDDEN_SENTINEL"}})],
                     [source(error="HIDDEN_SENTINEL", metadata={"secret": "HIDDEN_SENTINEL"},
                             coverage={"complete": False, "notes": ["HIDDEN_SENTINEL"] * 100})])
        result = project(state, now=WHEN)
        self.assertNotIn("HIDDEN_SENTINEL", json.dumps(result))
        self.assertEqual(0, project(state, now=WHEN, query="HIDDEN_SENTINEL")["counts"]["matching_records"])

    def test_scalar_bounds_and_unsafe_links_have_explicit_omissions(self):
        state = work([item(title="x" * 2000, next_action="y" * 3000,
                           url="https://example.com/item?access_token=private")],
                     [source(label="z" * 1000)])
        result = project(state, now=WHEN)
        row = result["items"][0]
        self.assertEqual(180, len(row["title"]))
        self.assertEqual(280, len(row["next_action"]))
        self.assertEqual(1820, row["truncated_characters"]["title"])
        self.assertEqual(2720, row["truncated_characters"]["next_action"])
        self.assertIsNone(row["url"])
        self.assertEqual("credential_parameter", row["link_omitted"])
        self.assertEqual(820, result["sources"][0]["truncated_characters"]["label"])

    def test_exact_links_and_encoded_detail_refs(self):
        state = work([item("id /?&ü", source_id="src /?", url="https://example.com/item/1#detail")],
                     [source("src /?")])
        row = project(state, now=WHEN)["items"][0]
        self.assertEqual("https://example.com/item/1#detail", row["url"])
        self.assertEqual({"source_id": "src /?", "item_id": "id /?&ü"}, row["detail_ref"])
        self.assertEqual({"source_id": ["src /?"], "item_id": ["id /?&ü"]},
                         parse_qs(urlsplit(row["detail_url"]).query))
        for url in ("javascript:alert(1)", "https://name:password@example.com", "https://example.com/" + "x" * 2048):
            with self.subTest(url=url[:50]):
                row = project(work([item(url=url)]), now=WHEN)["items"][0]
                self.assertIsNone(row["url"])
                self.assertIsNotNone(row["link_omitted"])

    def test_control_rows_and_missing_sources_remain_reachable(self):
        result = project(work([item(control=True), item("orphan", source_id="absent")]), now=WHEN)
        self.assertEqual(2, result["counts"]["inventory_records"])
        self.assertTrue(result["items"][1]["control"])
        missing = next(s for s in result["sources"] if s["source_id"] == "absent")
        self.assertTrue(missing["missing"])
        self.assertEqual("unknown", missing["freshness"])

    def test_empty_and_beyond_end_pages_account_for_every_row(self):
        empty = project(work([]), now=WHEN)
        self.assertEqual([], empty["items"])
        self.assertIsNone(empty["pagination"]["next_offset"])
        beyond = project(work(), now=WHEN, offset=100)
        self.assertEqual(1, beyond["omissions"]["records_before_page"])
        self.assertEqual(0, beyond["omissions"]["records_after_page"])
        self.assertEqual(1, beyond["counts"]["matching_records"])
        self.assertEqual([], beyond["items"])

    def test_invalid_parameters_and_duplicate_identity_fail_explicitly(self):
        index = build_index(work(), now=WHEN)
        for options in ({"limit": True}, {"limit": 0}, {"limit": 101}, {"offset": -1},
                        {"offset": 1.5}, {"owner": []}, {"query": "x" * 241},
                        {"if_revision": {}}, {"if_revision": "x" * 65}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                select(index, **options)
        for state in (work([item(), item()]), work(sources=[source(), source()]),
                      work([item("x" * 513)])):
            with self.assertRaises(ValueError):
                build_index(state, now=WHEN)
        self.assertEqual(100, INPUT_SCHEMA["properties"]["limit"]["maximum"])

    def test_input_and_cached_index_cannot_be_mutated_by_a_page(self):
        state = work()
        original = copy.deepcopy(state)
        index = build_index(state, now=WHEN)
        result = select(index)
        result["items"][0]["title"] = "Changed by caller"
        result["sources"][0]["coverage"]["complete"] = False
        self.assertEqual(original, state)
        self.assertEqual("Useful repair", select(index)["items"][0]["title"])
        self.assertTrue(select(index)["sources"][0]["coverage"]["complete"])


if __name__ == "__main__":
    unittest.main()

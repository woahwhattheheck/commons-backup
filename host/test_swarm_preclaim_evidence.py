#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Network-free regressions for Commons #15966 evidence completeness."""
import contextlib
import copy
import io
import json
import math
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from test_swarm_preclaim_fence import fence, report

TARGET = {"repo": "upstream/repo", "number": 842, "kind": "issue"}


def match(index, text="ordinary progress"):
    return {"channel": {"id": "C1", "name": "work"},
            "ts": str(index), "text": text, "username": "peer"}


class SearchTransport:
    """Model actual page offsets: changing count changes which rows are read."""
    def __init__(self, rows=(), mutate=None):
        self.rows = list(rows)
        self.mutate = mutate
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append(request)
        query = parse_qs(urlsplit(request.full_url).query)
        count, page = int(query["count"][0]), int(query["page"][0])
        total = len(self.rows)
        payload = {"ok": True, "messages": {
            "matches": copy.deepcopy(self.rows[(page - 1) * count:page * count]),
            "paging": {"count": count, "page": page,
                       "pages": math.ceil(total / count), "total": total},
            "total": total}}
        if self.mutate:
            self.mutate(payload, page)
        return io.BytesIO(json.dumps(payload).encode())


class IssueGitHub:
    def __init__(self, issue=None, pull=False):
        self.issue = {"state": "open", "title": "work"} if issue is None else issue
        self.pull = pull
        self.calls = []

    def rest(self, path, params=None):
        self.calls.append((path, params))
        if path == "/repos/owner/repo":
            return {"default_branch": "main"}
        if path == "/repos/owner/repo/branches/main":
            return {"commit": {"sha": "owner", "commit": {"tree": {"sha": "tree"}}}}
        if path == "/repos/owner/repo/git/trees/tree":
            return {"truncated": False, "tree": []}
        if path == "/repos/upstream/repo/pulls/842":
            if not self.pull:
                raise fence.EvidenceError("not a pull")
            return {"state": "open", "head": {"sha": "donor"}, "base": {"sha": "base"}}
        if path == "/repos/upstream/repo/pulls/842/files":
            raise fence.EvidenceError("PR file inventory unavailable")
        if path == "/repos/upstream/repo/issues/842":
            return self.issue
        if path in ("/repos/upstream/repo/issues/842/timeline", "/repos/owner/repo/pulls"):
            return []
        raise AssertionError((path, params))


def cli_evidence(evidence, github=None):
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "slack.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        output = io.StringIO()
        with patch.object(fence, "GitHub", return_value=github or IssueGitHub()), \
                contextlib.redirect_stdout(output):
            rc = fence.main(["--owner-fork", "owner/repo", "--target", "upstream/repo#842",
                             "--stable-id", "OP", "--slack-evidence", str(path), "--json"])
        return rc, json.loads(output.getvalue())


def complete_cache():
    return {"OP": [], '"upstream/repo#842"': [], '"repo#842"': [], '"repo" "#842"': []}


class OriginalBugRegressions(unittest.TestCase):
    def test_claim_on_page_eleven_cannot_be_silently_omitted(self):
        transport = SearchTransport([match(i) for i in range(1000)] + [match(1000, "TAKE OP")])
        with patch.object(fence.urllib.request, "urlopen", transport):
            with self.assertRaises(fence.EvidenceError):
                fence.SlackSearch("test-token").search("OP")
        self.assertLessEqual(len(transport.calls), 10)

    def test_absent_offline_queries_are_not_empty_search_results(self):
        rc, result = cli_evidence({})
        self.assertEqual(rc, 22)
        self.assertEqual(result["decision"], fence.MANUAL)
        self.assertFalse(result["branch_write_allowed"])
        self.assertTrue(result["errors"])

    def test_failed_pull_cannot_be_reclassified_by_issues_endpoint(self):
        github = IssueGitHub({"state": "open", "pull_request": {"url": "pull"}}, pull=True)
        rc, result = cli_evidence(complete_cache(), github)
        self.assertEqual(rc, 22)
        self.assertFalse(result["branch_write_allowed"])
        self.assertTrue(result["errors"])

    def test_issue_number_prefix_is_not_exact_custody(self):
        self.assertFalse(fence._references_target("TAKE upstream/repo#8420", TARGET))


class SlackPagingTests(unittest.TestCase):
    def search(self, rows=(), mutate=None, limit=1000):
        transport = SearchTransport(rows, mutate)
        with patch.object(fence.urllib.request, "urlopen", transport):
            result = fence.SlackSearch("test-token").search("OP", limit=limit)
        return result, transport

    def test_explicit_zero_results(self):
        self.assertEqual(self.search()[0], [])

    def test_empty_search_can_report_one_page(self):
        def mutate(payload, _):
            payload["messages"]["paging"]["pages"] = 1
        self.assertEqual(self.search(mutate=mutate)[0], [])

    def test_complete_full_budget(self):
        result, transport = self.search([match(i) for i in range(1000)])
        self.assertEqual(len(result), 1000)
        self.assertEqual(len(transport.calls), 10)
        self.assertEqual(result[-1]["ts"], "999")

    def test_partial_limit_keeps_fixed_page_width(self):
        result, transport = self.search([match(i) for i in range(150)], limit=150)
        self.assertEqual([row["ts"] for row in result], [str(i) for i in range(150)])
        self.assertEqual([parse_qs(urlsplit(req.full_url).query)["count"][0]
                          for req in transport.calls], ["100", "100"])

    def test_budget_smaller_than_page(self):
        result, transport = self.search([match(i) for i in range(3)], limit=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(len(transport.calls), 1)

    def test_terminal_claim_is_retained(self):
        result, _ = self.search([match(i) for i in range(100)] + [match(100, "TAKE OP")])
        self.assertEqual(fence.finalize(report(kind="issue", stable=result))["decision"], fence.OWNED)

    def test_invalid_limits_make_no_requests(self):
        for limit in (0, -1, True, "100", 1.5, 10001):
            with self.subTest(limit=limit), patch.object(fence.urllib.request, "urlopen") as call:
                with self.assertRaises(fence.EvidenceError):
                    fence.SlackSearch("test-token").search("OP", limit)
                call.assert_not_called()

    def test_missing_paging_is_not_completion(self):
        def mutate(payload, _):
            del payload["messages"]["paging"]
        with self.assertRaises(fence.EvidenceError):
            self.search(mutate=mutate)

    def test_invalid_paging_numbers(self):
        for field in ("count", "page", "pages", "total"):
            for value in (None, True, "1", -1, 1.2):
                def mutate(payload, _, field=field, value=value):
                    payload["messages"]["paging"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(fence.EvidenceError):
                    self.search([match(1)], mutate)

    def test_wrong_returned_page_or_count(self):
        for field, value in (("page", 2), ("count", 20)):
            def mutate(payload, _, field=field, value=value):
                payload["messages"]["paging"][field] = value
            with self.subTest(field=field), self.assertRaises(fence.EvidenceError):
                self.search([match(1)], mutate)

    def test_empty_nonterminal_page(self):
        def mutate(payload, _):
            payload["messages"]["matches"] = []
        with self.assertRaises(fence.EvidenceError):
            self.search([match(i) for i in range(101)], mutate)

    def test_short_nonterminal_page(self):
        def mutate(payload, page):
            if page == 1:
                payload["messages"]["matches"].pop()
        with self.assertRaises(fence.EvidenceError):
            self.search([match(i) for i in range(101)], mutate)

    def test_total_cannot_change_mid_search(self):
        def mutate(payload, page):
            if page == 2:
                payload["messages"]["paging"]["total"] = 100
                payload["messages"]["total"] = 100
        with self.assertRaises(fence.EvidenceError):
            self.search([match(i) for i in range(101)], mutate)

    def test_duplicate_page_rows_do_not_prove_full_coverage(self):
        def mutate(payload, page):
            if page == 2:
                payload["messages"]["matches"][0] = match(0)
        with self.assertRaises(fence.EvidenceError):
            self.search([match(i) for i in range(101)], mutate)

    def test_disagreeing_total(self):
        def mutate(payload, _):
            payload["messages"]["total"] = 999
        with self.assertRaises(fence.EvidenceError):
            self.search([match(1)], mutate)

    def test_pagination_disagreement(self):
        def mutate(payload, _):
            payload["messages"]["pagination"] = {
                "page": 1, "per_page": 100, "page_count": 1, "total_count": 2}
        with self.assertRaises(fence.EvidenceError):
            self.search([match(1)], mutate)

    def test_matching_secondary_pagination(self):
        def mutate(payload, _):
            paging = payload["messages"]["paging"]
            payload["messages"]["pagination"] = {
                "page": paging["page"], "per_page": paging["count"],
                "page_count": paging["pages"], "total_count": paging["total"]}
        self.assertEqual(len(self.search([match(1)], mutate)[0]), 1)

    def test_malformed_envelopes(self):
        mutations = [lambda p, _: p.update(ok="true"),
                     lambda p, _: p.update(messages=[]),
                     lambda p, _: p["messages"].update(matches={}),
                     lambda p, _: p["messages"].update(matches=[None]),
                     lambda p, _: p["messages"].update(matches=[{"text": "TAKE"}]),
                     lambda p, _: p["messages"].update(matches=[match(1, None)])]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index), self.assertRaises(fence.EvidenceError):
                self.search([match(1)], mutate)

    def test_rate_limit_does_not_return_partial_evidence(self):
        def mutate(payload, page):
            if page == 2:
                payload.update(ok=False, error="ratelimited")
        with self.assertRaises(fence.EvidenceError):
            self.search([match(i) for i in range(101)], mutate)

    def test_incomplete_search_makes_collected_report_manual(self):
        transport = SearchTransport([match(i) for i in range(1001)])
        with patch.object(fence.urllib.request, "urlopen", transport):
            result = fence.collect_report("owner/repo", "upstream/repo#842", "OP", [], [],
                                          IssueGitHub(), fence.SlackSearch("test-token"))
        self.assertEqual(result["exit_code"], 22)
        self.assertFalse(result["branch_write_allowed"])


class OfflineEvidenceTests(unittest.TestCase):
    def test_explicit_empty_queries_preserve_safe(self):
        self.assertEqual(cli_evidence(complete_cache())[0], 0)

    def test_missing_one_exact_query_is_manual(self):
        cache = complete_cache()
        del cache['"repo#842"']
        self.assertEqual(cli_evidence(cache)[0], 22)

    def test_malformed_values_do_not_become_no_hits(self):
        for value in (None, {}, "", [None], [{}], [{"text": None}], [{"text": "", "custody": "false"}]):
            cache = complete_cache()
            cache["OP"] = value
            with self.subTest(value=value):
                self.assertEqual(cli_evidence(cache)[0], 22)

    def test_non_mapping_evidence_is_manual(self):
        for value in ([], None, "", 12):
            with self.subTest(value=value):
                self.assertEqual(cli_evidence(value)[0], 22)

    def test_over_budget_cache_is_manual(self):
        cache = complete_cache()
        cache["OP"] = [{"text": "progress"}] * 1001
        self.assertEqual(cli_evidence(cache)[0], 22)

    def test_cached_claim_preserves_owned(self):
        cache = complete_cache()
        cache["OP"] = [{"text": "TAKE OP", "ts": "1", "channel": "work"}]
        self.assertEqual(cli_evidence(cache)[0], 20)

    def test_no_network_from_cached_evidence(self):
        with patch.object(fence.urllib.request, "urlopen", side_effect=AssertionError("network")):
            self.assertEqual(cli_evidence(complete_cache())[0], 0)


class TargetIdentityTests(unittest.TestCase):
    def test_genuine_issue_fallback_remains_supported(self):
        self.assertEqual(cli_evidence(complete_cache(), IssueGitHub())[0], 0)

    def test_explicit_issue_url_cannot_hide_pr_identity(self):
        github = IssueGitHub({"pull_request": {}})
        with self.assertRaises(fence.EvidenceError):
            fence.collect_github(github, "owner/repo", TARGET, [])
        self.assertFalse(any(path.endswith("/timeline") for path, _ in github.calls))

    def test_even_malformed_pull_marker_is_not_an_ordinary_issue(self):
        for marker in (None, False, "", []):
            with self.subTest(marker=marker), self.assertRaises(fence.EvidenceError):
                fence._issue(IssueGitHub({"pull_request": marker}), "upstream/repo", 842)

    def test_exact_target_positive_forms(self):
        for value in ("upstream/repo#842", "(UPSTREAM/REPO#842).",
                      "target:upstream/repo#842",
                      "target:https://github.com/upstream/repo/pull/842",
                      "https://github.com/upstream/repo/pull/842",
                      "https://github.com/upstream/repo/pulls/842/",
                      "<https://github.com/upstream/repo/issues/842?x=1|issue>",
                      "https://github.com/upstream/repo/issue/842#issuecomment-1"):
            with self.subTest(value=value):
                self.assertTrue(fence._references_target(value, TARGET))

    def test_exact_target_negative_forms(self):
        for value in ("upstream/repo#8420", "otherupstream/repo#842", "x/upstream/repo#842",
                      "upstream/repo#842suffix", "upstream/repo#842_1",
                      "https://github.com/upstream/repo/pull/8420",
                      "https://github.com/upstream/repo/issues/842x",
                      "https://example.com/https://github.com/upstream/repo/pull/842"):
            with self.subTest(value=value):
                self.assertFalse(fence._references_target(value, TARGET))

    def test_wrong_number_does_not_mark_owner_pr_exact(self):
        class Census:
            def rest(self, path, params=None):
                return [{"number": 9, "body": "TAKE upstream/repo#8420"}]
        value = fence.collect_owner_pr_census(Census(), "owner/repo", TARGET,
                                             "OP", [], [], {"cross_referenced_prs": []})
        self.assertEqual(value["hits"], [])


if __name__ == "__main__":
    unittest.main()

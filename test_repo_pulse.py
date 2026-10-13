#!/usr/bin/env python3
"""Regression fixtures for repo-pulse.

Covers the #commons contract: window overlap/dedupe, moving-main compare,
missing titles, pagination, event gaps, zero-change suppression, and
failed-check surfacing. The engine is imported as a module so these cannot
drift from the scheduled job.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock

import repo_pulse as rp

NOW = datetime(2026, 8, 28, 15, 10, 0, tzinfo=timezone.utc)
PREV = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HEAD = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def iso_at(delta_min=0):
    return rp.iso(NOW - timedelta(minutes=delta_min))


def event(eid, etype="PushEvent", created=None, login="alice", action=None):
    payload = {"id": str(eid), "type": etype, "created_at": created or iso_at(1), "actor": {"login": login}}
    if action:
        payload["payload"] = {"action": action}
    else:
        payload["payload"] = {}
    return payload


def commit(sha, message, login="alice", files=None, adds=None, dels=None):
    raw = {
        "sha": sha,
        "html_url": "https://github.com/woahwhattheheck/commons/commit/" + sha,
        "author": {"login": login} if login else None,
        "commit": {"message": message, "author": {"name": login or ""}},
    }
    if files is not None:
        raw["files"] = files
    if adds is not None:
        raw["stats"] = {"additions": adds, "deletions": dels or 0}
    return raw


class FakeAPI:
    def __init__(self, routes=None, pages=None):
        self.routes = routes or {}
        self.pages = pages or {}
        self.calls = []

    def __call__(self, path, **params):
        self.calls.append((path, params))
        page = int(params.get("page") or 1)
        key = path
        if path in self.pages:
            batches = self.pages[path]
            if page - 1 < len(batches):
                return batches[page - 1], {}
            return [], {}
        if key in self.routes:
            payload = self.routes[key]
            return payload, {}
        for prefix, payload in self.routes.items():
            if path.startswith(prefix):
                return payload, {}
        return None, None


class SurfaceTests(unittest.TestCase):
    def test_contract_groups(self):
        self.assertEqual(rp.surface_of("p/abc.html"), "generated artifacts")
        self.assertEqual(rp.surface_of("posts.json"), "generated artifacts")
        self.assertEqual(rp.surface_of("muhl/core.py"), "Muhlnickel")
        self.assertEqual(rp.surface_of("revenue/sku.md"), "revenue")
        self.assertEqual(rp.surface_of("independent_commons_mcp/server.py"), "agents/connectors")
        self.assertEqual(rp.surface_of("slack_ingest.py"), "agents/connectors")
        self.assertEqual(rp.surface_of(".github/workflows/tests.yml"), "CI/tests")
        self.assertEqual(rp.surface_of("test_repo_pulse.py"), "CI/tests")
        self.assertEqual(rp.surface_of("ground/MANUAL.md"), "docs/ground")
        self.assertEqual(rp.surface_of("board.js"), "board/UI")
        self.assertEqual(rp.surface_of("index.html"), "board/UI")


class OverlapDedupeTests(unittest.TestCase):
    def tearDown(self):
        rp.GET = None
        rp.reset_io()

    def test_overlapping_windows_neither_miss_nor_double_report(self):
        shared = event(100, created=iso_at(4))
        older = event(90, created=iso_at(8))
        newer = event(110, created=iso_at(1))
        # Window 1 saw 90 and 100. Window 2 re-reads 100 plus 110.
        rp.GET = FakeAPI(
            pages={
                "/repos/{repo}/events": [
                    [newer, shared, older],
                ]
            }
        )
        fresh, exhausted, pages, all_ids = rp.fetch_events(
            seen_ids=["90", "100"],
            first_run=False,
            now=NOW,
            max_pages=3,
        )
        ids = [e["id"] for e in fresh]
        self.assertEqual(ids, ["110"])
        self.assertFalse(exhausted)
        self.assertEqual(all_ids, ["110", "100", "90"])
        union = rp.dedupe_event_ids(["90", "100"], all_ids)
        self.assertEqual(union, ["110", "100", "90"])

    def test_dedupe_keeps_stable_ids_across_cap(self):
        incoming = [str(i) for i in range(50, 0, -1)]
        previous = [str(i) for i in range(40, 0, -1)]
        got = rp.dedupe_event_ids(previous, incoming, cap=10)
        self.assertEqual(got, [str(i) for i in range(50, 40, -1)])
        self.assertEqual(len(set(got)), 10)


class PaginationTests(unittest.TestCase):
    def tearDown(self):
        rp.GET = None
        rp.reset_io()

    def test_page_cap_sets_exhausted_and_truncated_note(self):
        def page(n):
            # 100 unseen events per page so the walker cannot stop early.
            return [event(n * 1000 + i, created=iso_at(1)) for i in range(100)]

        rp.GET = FakeAPI(
            pages={
                "/repos/{repo}/events": [page(1), page(2), page(3)],
            }
        )
        rp.reset_io()
        fresh, exhausted, pages, all_ids = rp.fetch_events(
            seen_ids=[],
            first_run=False,
            now=NOW,
            max_pages=3,
        )
        self.assertTrue(exhausted)
        self.assertEqual(pages, 3)
        self.assertEqual(len(fresh), 300)
        self.assertEqual(len(all_ids), 300)
        self.assertTrue(rp.RATE["truncated"])
        self.assertTrue(any("truncated" in n for n in rp.NOTES))

    def test_first_run_horizon_is_a_clean_stop_not_exhaustion(self):
        old_page = [event(3000 + i, created=iso_at(6)) for i in range(100)]
        rp.GET = FakeAPI(
            pages={
                "/repos/{repo}/events": [old_page, [event(4000, created=iso_at(7))]],
            }
        )
        rp.reset_io()
        fresh, exhausted, pages, all_ids = rp.fetch_events(
            seen_ids=[],
            first_run=True,
            now=NOW,
            lookback_min=5,
            max_pages=3,
        )
        self.assertEqual(fresh, [])
        self.assertFalse(exhausted)
        self.assertEqual(pages, 1)
        self.assertEqual(len(all_ids), 100)
        self.assertFalse(rp.RATE["truncated"])
        self.assertFalse(any("truncated" in n for n in rp.NOTES))


class MovingMainCompareTests(unittest.TestCase):
    def test_compare_payload_is_the_commit_authority(self):
        payload = {
            "status": "ahead",
            "total_commits": 2,
            "commits": [
                commit(PREV, "old work"),
                commit(HEAD, "repo-pulse: fixtures\n\nbody"),
            ],
            "files": [
                {"filename": "board.js", "additions": 4, "deletions": 1},
                {"filename": "muhl/core.py", "additions": 10, "deletions": 2},
                {"filename": "p/new.html", "additions": 3, "deletions": 0},
            ],
        }
        parsed = rp.parse_compare(payload)
        self.assertEqual(parsed["total"], 2)
        self.assertEqual(parsed["adds"], 17)
        self.assertEqual(parsed["dels"], 3)
        self.assertEqual(parsed["commits"][1]["title"], "repo-pulse: fixtures")
        self.assertEqual(parsed["commits"][1]["short"], HEAD[:7])
        self.assertEqual(parsed["files"]["board/UI"]["files"], 1)
        self.assertEqual(parsed["files"]["Muhlnickel"]["files"], 1)
        self.assertEqual(parsed["files"]["generated artifacts"]["files"], 1)
        self.assertTrue(parsed["available"])
        self.assertFalse(parsed["truncated"])

    def test_identical_heads_are_available_zero(self):
        rp.GET = lambda path, **params: (_ for _ in ()).throw(AssertionError("no network"))
        # commit_range short-circuits before GET when heads match.
        rp.GET = None
        got = rp.commit_range(HEAD, HEAD)
        self.assertEqual(got["total"], 0)
        self.assertTrue(got["available"])
        self.assertEqual(got["status"], "identical")

    def test_render_includes_range_even_when_events_feed_is_empty(self):
        diff = rp.parse_compare(
            {
                "status": "ahead",
                "total_commits": 1,
                "commits": [commit(HEAD, "land fixtures", login="woahwhattheheck", adds=12, dels=3)],
                "files": [{"filename": ".github/workflows/repo-pulse.yml", "additions": 12, "deletions": 3}],
            }
        )
        ctx = _ctx(diff=diff, events=[], previous_head=PREV)
        text = rp.render(ctx)
        self.assertIn(PREV[:7], text)
        self.assertIn(HEAD[:7], text)
        self.assertIn("land fixtures", text)
        self.assertIn("range %s → %s" % (PREV[:7], HEAD[:7]), text)
        self.assertIn("0 events", text)
        self.assertIn("+1 commits", text)


class MissingTitleTests(unittest.TestCase):
    def test_empty_message_is_omitted_not_placeholder(self):
        parsed = rp.parse_commit(commit(HEAD, "", login="alice"))
        self.assertIsNone(parsed["title"])
        line = rp.commit_line("woahwhattheheck/commons", parsed)
        self.assertIsNotNone(line)
        self.assertNotIn("no title", line.lower())
        self.assertNotIn("?", line)
        self.assertIn(HEAD[:7], line)
        self.assertIn("`alice`", line)

    def test_missing_author_is_omitted(self):
        raw = commit(HEAD, "titled", login=None)
        raw["author"] = None
        raw["commit"]["author"] = {}
        parsed = rp.parse_commit(raw)
        self.assertIsNone(parsed["author"])
        line = rp.commit_line("woahwhattheheck/commons", parsed)
        self.assertIn("titled", line)
        self.assertNotIn("unknown", line.lower())
        self.assertNotIn("?", line)

    def test_blank_commit_with_no_sha_is_dropped(self):
        self.assertIsNone(rp.commit_line("woahwhattheheck/commons", {}))


class EventGapTests(unittest.TestCase):
    def test_issues_moved_without_feed_events(self):
        gaps = rp.event_gaps(
            events=[],
            prev_snapshot={"issues_total": 10, "prs_total": 4},
            snapshot={"issues_total": 12, "prs_total": 4},
        )
        self.assertEqual(gaps, ["EVENT_GAP +2 issues"])

    def test_partial_feed_still_reports_remainder(self):
        gaps = rp.event_gaps(
            events=[event(1, "IssuesEvent", action="opened"), event(2, "IssuesEvent", action="closed")],
            prev_snapshot={"issues_total": 10},
            snapshot={"issues_total": 13},
        )
        self.assertEqual(gaps, ["EVENT_GAP +2 issues"])

    def test_matching_events_suppress_gap(self):
        gaps = rp.event_gaps(
            events=[event(1, "IssuesEvent", action="opened"), event(2, "IssuesEvent", action="opened")],
            prev_snapshot={"issues_total": 10},
            snapshot={"issues_total": 12},
        )
        self.assertEqual(gaps, [])

    def test_unavailable_counters_are_omitted(self):
        gaps = rp.event_gaps(
            events=[],
            prev_snapshot={"issues_total": None},
            snapshot={"issues_total": 12},
        )
        self.assertEqual(gaps, [])


class ZeroChangeSuppressionTests(unittest.TestCase):
    def test_quiet_window_is_silent_inside_the_hour(self):
        should, reason = rp.decide_post(
            changed=False,
            last_post_at=NOW - timedelta(minutes=12),
            now=NOW,
            heartbeat_min=60,
        )
        self.assertFalse(should)
        self.assertEqual(reason, "quiet")

    def test_owner_idle_mode_reports_every_scheduled_window(self):
        should, reason = rp.decide_post(
            changed=False,
            last_post_at=NOW - timedelta(minutes=5),
            now=NOW,
            heartbeat_min=60,
            report_idle=True,
        )
        self.assertTrue(should)
        self.assertEqual(reason, "idle-forced")

    def test_hourly_heartbeat_fires(self):
        should, reason = rp.decide_post(
            changed=False,
            last_post_at=NOW - timedelta(minutes=60),
            now=NOW,
            heartbeat_min=60,
        )
        self.assertTrue(should)
        self.assertEqual(reason, "heartbeat")

    def test_change_always_posts(self):
        should, reason = rp.decide_post(
            changed=True,
            last_post_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        self.assertTrue(should)
        self.assertEqual(reason, "changed")

    def test_window_changed_ignores_pure_snapshot_identity(self):
        self.assertFalse(
            rp.window_changed(
                events=[],
                diff={"total": 0},
                gaps=[],
                health={"failing": []},
                settings=[],
            )
        )
        self.assertTrue(
            rp.window_changed(
                events=[],
                diff={"total": 1},
                gaps=[],
                health={"failing": []},
                settings=[],
            )
        )


class FailedCheckTests(unittest.TestCase):
    def test_failing_check_names_job_and_keeps_direct_link(self):
        parsed = rp.parse_check_runs(
            {
                "check_runs": [
                    {
                        "name": "battery",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://github.com/woahwhattheheck/commons/actions/runs/1/job/2",
                        "app": {"name": "GitHub Actions"},
                    },
                    {
                        "name": "pages",
                        "status": "in_progress",
                        "conclusion": None,
                    },
                    {
                        "name": "quiet",
                        "status": "completed",
                        "conclusion": "success",
                    },
                ]
            }
        )
        self.assertEqual(parsed["pending"], 1)
        self.assertEqual(parsed["checks"]["failure"], 1)
        self.assertEqual(parsed["checks"]["success"], 1)
        self.assertEqual(parsed["failing"][0]["name"], "battery")
        self.assertEqual(
            parsed["failing"][0]["url"],
            "https://github.com/woahwhattheheck/commons/actions/runs/1/job/2",
        )
        status = rp.classify_status(parsed, gaps=[], exhausted=False, settings=[], backup=None)
        self.assertEqual(status, "BROKEN")
        text = rp.render(
            _ctx(
                health={
                    "checks": parsed["checks"],
                    "failing": parsed["failing"],
                    "pending": 1,
                    "pages": None,
                    "pages_drift": False,
                },
                status="BROKEN",
            )
        )
        self.assertIn("BROKEN", text)
        self.assertIn("battery", text)
        self.assertIn("job log", text)
        self.assertIn("https://github.com/woahwhattheheck/commons/actions/runs/1/job/2", text)
        self.assertNotIn("no title", text)

    def test_nameless_failure_is_omitted_not_question_mark(self):
        parsed = rp.parse_check_runs(
            {"check_runs": [{"name": "", "status": "completed", "conclusion": "failure"}]}
        )
        self.assertEqual(parsed["failing"], [])


class OpenPrPagesBackupTests(unittest.TestCase):
    def test_open_prs_and_backup_age_and_pages_drift(self):
        pulls = rp.list_open_pulls(
            [
                {
                    "number": 4856,
                    "title": "Coalesce stale tests.yml PR synchronize",
                    "html_url": "https://github.com/woahwhattheheck/commons/pull/4856",
                    "user": {"login": "woahwhattheheck"},
                    "state": "open",
                    "draft": False,
                }
            ]
        )
        backup = rp.parse_backup_age(
            [
                {
                    "name": "open-repo-backup",
                    "created_at": rp.iso(NOW - timedelta(hours=2)),
                    "expired": False,
                    "archive_download_url": "https://example.invalid/backup",
                    "id": 9,
                }
            ],
            NOW,
        )
        pages = rp.parse_pages(
            {"commit": PREV, "status": "built", "html_url": "https://example.invalid/pages"},
            HEAD,
        )
        self.assertTrue(pages["pages_drift"])
        self.assertEqual(backup["age_seconds"], 2 * 3600)
        health = {
            "checks": {},
            "failing": [],
            "pending": 0,
            "pages": pages["pages"],
            "pages_drift": True,
        }
        status = rp.classify_status(health, gaps=[], exhausted=False, settings=[], backup=backup)
        self.assertEqual(status, "ATTENTION")
        text = rp.render(
            _ctx(
                health=health,
                backup=backup,
                open_prs=pulls,
                status="ATTENTION",
            )
        )
        self.assertIn("#4856", text)
        self.assertIn("Coalesce stale tests.yml", text)
        self.assertIn("verified 2h00m ago", text)
        self.assertIn("pages", text)
        self.assertIn(PREV[:7], text)

    def test_attach_pulls_stamps_merged_state(self):
        commits = [rp.parse_commit(commit(HEAD, "land it"))]
        rp.attach_pulls(
            commits,
            [
                {
                    "number": 12,
                    "title": "Land pulse fixtures",
                    "html_url": "https://github.com/woahwhattheheck/commons/pull/12",
                    "merged_at": iso_at(1),
                    "state": "closed",
                    "merge_commit_sha": HEAD,
                    "head": {"sha": "ccc"},
                    "user": {"login": "woahwhattheheck"},
                }
            ],
        )
        self.assertEqual(commits[0]["pr"]["number"], 12)
        self.assertEqual(commits[0]["pr"]["state"], "merged")
        line = rp.commit_line("woahwhattheheck/commons", commits[0])
        self.assertIn("#12 merged", line)
        self.assertIn("Land pulse fixtures", line)


class RenderContractTests(unittest.TestCase):
    def test_mirror_claim_leads_and_coverage_names_facts(self):
        text = rp.render(_ctx())
        self.assertTrue(text.startswith("from: COMMONS_SLACK_MIRROR\n"))
        self.assertIn("to: TABLE", text)
        self.assertIn("facts:", text)
        self.assertIn("window ", text)
        self.assertIn("range %s → %s" % (PREV[:7], HEAD[:7]), text)
        self.assertIn("inference:", text)
        self.assertNotIn("no title", text)

    def test_missing_rate_limit_omits_placeholder(self):
        rp.reset_io()
        rp.RATE["remaining"] = 5000
        rp.RATE["limit"] = None
        text = rp.render(_ctx())
        self.assertIn("rate-limit remaining 5000", text)
        self.assertNotIn("?", text)
        rp.reset_io()
        rp.RATE["remaining"] = 4999
        rp.RATE["limit"] = 5000
        text = rp.render(_ctx())
        self.assertIn("rate-limit 4999/5000", text)
        self.assertNotIn("?", text)

    def test_heartbeat_render_is_compact(self):
        ctx = _ctx(events=[], diff=rp.parse_compare({"commits": [], "files": [], "status": "identical", "total_commits": 0}))
        ctx["quiet_for"] = "55m"
        ctx["reason"] = "heartbeat"
        ctx["status"] = "CLEAR"
        text = rp.render(ctx)
        self.assertIn("CLEAR", text)
        self.assertIn("heartbeat", text)
        self.assertLess(len(text), 2500)

    def test_sprint_teach_line_and_verdicts_do_not_rewrite_status(self):
        text = rp.render(_ctx())
        self.assertIn("MERGE DEFAULT", text)
        self.assertIn("ground/SPRINT_INTEGRATION.json", text)
        src = open(rp.__file__, encoding="utf-8").read()
        for verdict in ("CLEAR_TO_MERGE", "COMPOSE_AND_MERGE", "DEDUPED", "CONFLICT"):
            self.assertIn(verdict, src)
        health = {"checks": {"success": 1}, "failing": [], "pending": 0, "pages": None, "pages_drift": False}
        self.assertEqual(rp.classify_status(health, [], False, [], None), "CLEAR")
        conflict_ctx = _ctx(status="CLEAR", sprint={
            "slack_lines": [
                "*sprint* MERGE DEFAULT · <https://github.com/woahwhattheheck/commons/blob/main/ground/SPRINT_INTEGRATION.json|policy>",
                ":warning: *CONFLICT* #1 vs #2 path `flag.py` SI-SEMANTIC-DISAGREE left `aaa` right `bbb` base `ccc` head-L `ddd` head-R `eee`",
            ],
            "pairs": [{"verdict": "CONFLICT"}],
        })
        rendered = rp.render(conflict_ctx)
        self.assertIn("*CONFLICT*", rendered)
        self.assertIn("SI-SEMANTIC-DISAGREE", rendered)
        self.assertEqual(conflict_ctx["status"], "CLEAR")
        self.assertTrue(rendered.startswith("from: COMMONS_SLACK_MIRROR\n"))


class StateRoundTripTests(unittest.TestCase):
    def test_next_state_persists_cursor_head_and_ids(self):
        state = {
            "seen_ids": ["90"],
            "previous_head": PREV,
            "last_post_at": iso_at(10),
            "history": [],
        }
        ctx = _ctx(events=[event(110, created=iso_at(1))])
        ctx["all_ids"] = ["110", "100", "90"]
        ctx["snapshot"] = {"head": HEAD}
        ctx["diff"] = {"total": 1}
        nxt = rp.next_state(state, ctx, posted="summary", now=NOW)
        self.assertEqual(nxt["previous_head"], HEAD)
        self.assertEqual(nxt["seen_ids"][0], "110")
        self.assertIn("90", nxt["seen_ids"])
        self.assertEqual(nxt["last_event_at"], iso_at(1))
        self.assertEqual(nxt["last_post_at"], rp.iso(NOW))


class EvidenceAndMainTests(unittest.TestCase):
    def tearDown(self):
        rp.GET = None
        rp.reset_io()

    def test_write_evidence_stable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "repo-pulse", "latest.json")
            rp.write_evidence(path, {"ok": True, "range": [PREV, HEAD]})
            payload = json.loads(open(path, encoding="utf-8").read())
            self.assertEqual(payload["ok"], True)
            self.assertTrue(path.endswith("repo-pulse/latest.json"))

    def test_main_suppresses_quiet_window_but_writes_evidence(self):
        routes = {
            "/repos/{repo}": {
                "default_branch": "main",
                "stargazers_count": 1,
                "forks_count": 0,
                "visibility": "public",
                "archived": False,
                "has_issues": True,
                "has_wiki": False,
                "has_pages": True,
                "has_discussions": False,
                "topics": [],
                "description": "Public Commons board. HTTP is not the computer.",
                "homepage": "",
            },
            "/repos/{repo}/commits/main": {"sha": HEAD},
            "/repos/{repo}/compare/%s...%s" % (HEAD, HEAD): {
                "status": "identical",
                "total_commits": 0,
                "commits": [],
                "files": [],
            },
            "/repos/{repo}/pulls": [],
            "/repos/{repo}/commits/%s/check-runs" % HEAD: {"check_runs": []},
            "/repos/{repo}/pages/builds/latest": {"commit": HEAD, "status": "built"},
            "/repos/{repo}/actions/artifacts": {"artifacts": []},
            "/search/issues": {"total_count": 1},
        }
        fake = FakeAPI(
            routes=routes,
            pages={"/repos/{repo}/events": [[]]},
        )
        rp.GET = fake
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, ".pulse-state.json")
            evidence_path = os.path.join(tmp, "repo-pulse", "latest.json")
            rp.save_state(
                state_path,
                {
                    "seen_ids": ["1"],
                    "previous_head": HEAD,
                    "last_post_at": rp.iso(NOW - timedelta(minutes=5)),
                    "last_run_at": rp.iso(NOW - timedelta(minutes=5)),
                    "last_event_at": rp.iso(NOW - timedelta(minutes=20)),
                    "snapshot": {"head": HEAD, "issues_total": 1, "prs_total": 1},
                    "history": [],
                },
            )
            env = {
                "GITHUB_REPOSITORY": "woahwhattheheck/commons",
                "GITHUB_RUN_ID": "99",
                "PULSE_STATE": state_path,
                "PULSE_EVIDENCE": evidence_path,
                "PULSE_REPORT_IDLE": "false",
                "PULSE_IDLE_HEARTBEAT_MINUTES": "60",
            }
            buf = StringIO()
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("repo_pulse.now_utc", return_value=NOW):
                    with mock.patch("sys.stdout", buf):
                        rc = rp.main([])
            self.assertEqual(rc, 0)
            self.assertIn("quiet window", buf.getvalue())
            evidence = json.loads(open(evidence_path, encoding="utf-8").read())
            self.assertEqual(evidence["reason"], "quiet")
            self.assertEqual(evidence["to_sha"], HEAD)
            self.assertEqual(evidence["from_sha"], HEAD)
            self.assertEqual(evidence["event_count"], 0)
            self.assertIn("digest", evidence)
            self.assertTrue(evidence["digest"].startswith("from: COMMONS_SLACK_MIRROR"))


def _ctx(**overrides):
    diff = overrides.get(
        "diff",
        rp.parse_compare(
            {
                "status": "ahead",
                "total_commits": 1,
                "commits": [commit(HEAD, "pulse fixtures", login="alice", adds=4, dels=1)],
                "files": [{"filename": "board.js", "additions": 4, "deletions": 1}],
            }
        ),
    )
    base = {
        "now": NOW,
        "events": overrides.get("events", [event(110)]),
        "exhausted": False,
        "pages": 1,
        "snapshot": {"head": HEAD},
        "diff": diff,
        "health": overrides.get(
            "health",
            {"checks": {"success": 3}, "failing": [], "pending": 0, "pages": None, "pages_drift": False},
        ),
        "gaps": overrides.get("gaps", []),
        "settings": [],
        "previous_head": PREV,
        "velocity": rp.velocity([], 1, 1, NOW),
        "window_from": iso_at(5),
        "cursor": iso_at(5),
        "status": overrides.get("status", "CLEAR"),
        "repo": "woahwhattheheck/commons",
        "run_url": "https://github.com/woahwhattheheck/commons/actions/runs/1",
        "evidence_url": "https://github.com/woahwhattheheck/commons/actions/runs/1",
        "max_commit_lines": 8,
        "reason": "changed",
        "open_prs": overrides.get("open_prs", []),
        "backup": overrides.get("backup"),
    }
    base.update(overrides)
    return base


class SlackIngestLoopSafetyTests(unittest.TestCase):
    def test_pulse_header_is_the_skip_claim(self):
        try:
            import slack_ingest as si
        except ImportError:
            self.skipTest("slack_ingest not on path")
        text = rp.render(_ctx())
        self.assertTrue(
            si.should_skip({"ts": "1787929400.1", "text": text, "user": "U1"})
        )


class PublicationSafeDigestTests(unittest.TestCase):
    """Run 34128542491 died in post_slack on unfavorable_finding.

    Pulse-authored "exhausted" and unquoted GitHub commit subjects were
    classified as outgoing prose. The digest must keep the facts and still
    pass require_publication.
    """

    def test_live_exhausted_feed_and_regression_commit_are_publishable(self):
        from commons_publication_policy import check_publication, require_publication

        diff = rp.parse_compare(
            {
                "status": "ahead",
                "total_commits": 1,
                "commits": [
                    commit(
                        HEAD,
                        "Record measured Kaggriculture results and add fresh-main regression seed",
                    )
                ],
                "files": [{"filename": "test_kaggriculture.py", "additions": 4, "deletions": 0}],
            }
        )
        ctx = _ctx(
            exhausted=True,
            status="ATTENTION",
            diff=diff,
            gaps=["EVENT_GAP +406 issues", "EVENT_GAP +64 PRs"],
        )
        text = rp.render(ctx)
        self.assertIn("event feed truncated", text)
        self.assertNotIn("event feed exhausted", text)
        self.assertIn("regression seed", text)
        self.assertIn(
            "`Record measured Kaggriculture results and add fresh-main regression seed`",
            text,
        )
        self.assertIn("EVENT_GAP +406 issues", text)
        decision = check_publication(text)
        self.assertTrue(decision.get("allowed"), decision)
        require_publication(text)

    def test_broken_failing_check_digest_is_publishable(self):
        from commons_publication_policy import check_publication, require_publication

        ctx = _ctx(
            status="BROKEN",
            health={
                "checks": {"failure": 1, "success": 1},
                "failing": [
                    {
                        "name": "battery",
                        "url": "https://github.com/woahwhattheheck/commons/actions/runs/1/job/2",
                    }
                ],
                "pending": 1,
                "pages": None,
                "pages_drift": False,
            },
        )
        text = rp.render(ctx)
        self.assertIn("BROKEN", text)
        self.assertIn("battery", text)
        self.assertIn("failure", text)
        self.assertIn("job log", text)
        decision = check_publication(text)
        self.assertTrue(decision.get("allowed"), decision)
        require_publication(text)

    def test_default_digest_stays_publishable(self):
        from commons_publication_policy import check_publication, require_publication

        text = rp.render(_ctx())
        self.assertTrue(check_publication(text).get("allowed"))
        require_publication(text)


class BackupProbeHttpTests(unittest.TestCase):
    def tearDown(self):
        rp.GET = None
        rp.reset_io()

    def _http(self, url, code):
        raise urllib.error.HTTPError(url, code, "status %s" % code, None, None)

    def test_persistent_http_500_omits_backup_and_keeps_the_note(self):
        urls = []

        def _req(url, headers=None, data=None, method=None):
            urls.append(url)
            self._http(url, 500)

        rp.GET = None
        rp.reset_io()
        with mock.patch.object(rp, "_req", _req):
            got = rp.newest_backup(NOW)
        self.assertIsNone(got)
        self.assertEqual(len(urls), 2)
        self.assertTrue(all("name=commons-open-repo-backup" in url for url in urls))
        self.assertEqual(rp.NOTES, ["backup probe HTTP 500"])
        text = rp.render(_ctx())
        self.assertIn("backup probe HTTP 500", text)
        self.assertNotIn("*backup* verified", text)
        from commons_publication_policy import check_publication, require_publication
        decision = check_publication(text)
        self.assertTrue(decision.get("allowed"), decision)
        require_publication(text)

    def test_http_500_then_success_returns_named_backup(self):
        body = json.dumps(
            {
                "artifacts": [
                    {
                        "name": "commons-open-repo-backup",
                        "created_at": rp.iso(NOW - timedelta(hours=1)),
                        "expired": False,
                        "id": 9,
                    }
                ]
            }
        ).encode("utf-8")
        calls = {"n": 0}

        def _req(url, headers=None, data=None, method=None):
            calls["n"] += 1
            if calls["n"] == 1:
                self._http(url, 500)
            self.assertIn("name=commons-open-repo-backup", url)
            return 200, {"X-RateLimit-Remaining": "40", "X-RateLimit-Limit": "5000"}, body

        rp.GET = None
        rp.reset_io()
        with mock.patch.object(rp, "_req", _req):
            got = rp.newest_backup(NOW)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(got["id"], 9)
        self.assertEqual(got["age_seconds"], 3600)
        self.assertEqual(rp.NOTES, [])

    def test_non_transient_http_status_still_propagates(self):
        def _req(url, headers=None, data=None, method=None):
            self._http(url, 400)

        rp.GET = None
        rp.reset_io()
        with mock.patch.object(rp, "_req", _req):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                rp.newest_backup(NOW)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(rp.NOTES, [])



if __name__ == "__main__":
    unittest.main()

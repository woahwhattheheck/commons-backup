#!/usr/bin/env python3
"""Automatic batteries supersede by event/ref; manual dispatches stay independent."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def _lookup(ctx, name):
    cur = ctx
    for part in name.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _truthy(value):
    return value not in (None, False, 0, 0.0, "")


def _tokenize(expr):
    token_re = re.compile(
        r"\s*(==|&&|\|\||\(|\)|'[^']*'|[A-Za-z_][A-Za-z0-9_.]*|\d+)"
    )
    pos = 0
    tokens = []
    while pos < len(expr):
        match = token_re.match(expr, pos)
        if not match:
            raise AssertionError(f"unparsed expression at {expr[pos:]!r}")
        tokens.append(match.group(1))
        pos = match.end()
    if pos != len(expr.rstrip()):
        raise AssertionError(f"trailing expression {expr[pos:]!r}")
    return tokens


def _parse_primary(tokens, idx, ctx):
    token = tokens[idx]
    if token == "(":
        value, idx = _parse_or(tokens, idx + 1, ctx)
        if idx >= len(tokens) or tokens[idx] != ")":
            raise AssertionError("missing )")
        return value, idx + 1
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1], idx + 1
    if token.isdigit():
        return int(token), idx + 1
    return _lookup(ctx, token), idx + 1


def _parse_eq(tokens, idx, ctx):
    left, idx = _parse_primary(tokens, idx, ctx)
    while idx < len(tokens) and tokens[idx] == "==":
        right, idx = _parse_primary(tokens, idx + 1, ctx)
        left = left == right
    return left, idx


def _parse_and(tokens, idx, ctx):
    left, idx = _parse_eq(tokens, idx, ctx)
    while idx < len(tokens) and tokens[idx] == "&&":
        right, idx = _parse_eq(tokens, idx + 1, ctx)
        left = right if _truthy(left) else left
    return left, idx


def _parse_or(tokens, idx, ctx):
    left, idx = _parse_and(tokens, idx, ctx)
    while idx < len(tokens) and tokens[idx] == "||":
        right, idx = _parse_and(tokens, idx + 1, ctx)
        left = left if _truthy(left) else right
    return left, idx


def eval_expr(expr, ctx):
    tokens = _tokenize(expr.strip())
    value, idx = _parse_or(tokens, 0, ctx)
    if idx != len(tokens):
        raise AssertionError(f"unused tokens {tokens[idx:]}")
    return value


def interpolate(template, ctx):
    def repl(match):
        value = eval_expr(match.group(1), ctx)
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return ""
        return str(value)

    return re.sub(r"\$\{\{(.+?)\}\}", repl, template)


def parse_concurrency(text):
    match = re.search(
        r"(?m)^concurrency:\n"
        r"(?:  #[^\n]*\n)*"
        r"  group: (?P<group>[^\n]+)\n"
        r"  cancel-in-progress: (?P<cancel>[^\n]+)\n",
        text,
    )
    if not match:
        raise AssertionError("missing workflow concurrency block")
    return match.group("group").strip().strip('"'), match.group("cancel").strip()


def github_ctx(
    event_name, run_id, head_label=None, workflow="tests", *, pr_number=None, ref=None
):
    event = {}
    if event_name == "pull_request":
        if pr_number is None:
            raise ValueError("PR fixtures require a stable pull-request number")
        head_label = head_label or "woahwhattheheck:topic"
        _, _, head_ref = head_label.partition(":")
        event["pull_request"] = {
            "head": {"label": head_label, "ref": head_ref or head_label},
            "number": pr_number,
        }
    if ref is None:
        # github.ref identifies the PR, not the individual workflow run.
        ref = (
            f"refs/pull/{pr_number}/merge"
            if event_name == "pull_request"
            else "refs/heads/main"
        )
    return {
        "github": {
            "workflow": workflow,
            "event_name": event_name,
            "run_id": str(run_id),
            "event": event,
            "ref": ref,
        }
    }


def decide(group_template, cancel_template, ctx):
    group = interpolate(group_template, ctx)
    cancel_raw = interpolate(cancel_template, ctx)
    if cancel_raw in ("true", "false"):
        cancel = cancel_raw == "true"
    else:
        cancel = _truthy(eval_expr(cancel_template.replace("${{", "").replace("}}", ""), ctx))
    return group, cancel


def simulate(events, group_template, cancel_template):
    """GitHub concurrency: newest pending replaces older pending; cancel-in-progress
    may also drop the running occupant of the same group."""
    live = []
    for event in events:
        ctx = github_ctx(
            event["event_name"],
            event["run_id"],
            event.get("head_label"),
            event.get("workflow", "tests"),
            pr_number=event.get("pr_number"),
            ref=event.get("ref"),
        )
        group, cancel = decide(group_template, cancel_template, ctx)
        run = {
            "run_id": str(event["run_id"]),
            "event_name": event["event_name"],
            "head_label": event.get("head_label"),
            "group": group,
            "cancel": cancel,
            "status": "in_progress",
        }
        for occupant in live:
            if occupant["group"] != group or occupant["status"] == "cancelled":
                continue
            if occupant["status"] == "queued":
                occupant["status"] = "cancelled"
            elif occupant["status"] == "in_progress" and cancel:
                occupant["status"] = "cancelled"
            elif occupant["status"] == "in_progress" and not cancel:
                run["status"] = "queued"
        live.append(run)
    return live


class TestsPrConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.group_template, cls.cancel_template = parse_concurrency(cls.text)

    def test_workflow_keeps_push_pr_and_manual_triggers(self):
        self.assertRegex(self.text, r"(?m)^  push:\n    branches:\n      - main$")
        self.assertIn("\n  pull_request:\n", self.text)
        self.assertIn("\n  workflow_dispatch:\n", self.text)
        self.assertNotRegex(self.text, r"(?m)^  issues:\n    types: \[opened\]$")

    def test_same_pr_synchronize_shares_group_and_cancels(self):
        first = github_ctx(
            "pull_request",
            33181739713,
            "woahwhattheheck:codex/trust-after-proof-20260828-01",
            pr_number=17,
        )
        second = github_ctx(
            "pull_request",
            33182645445,
            "woahwhattheheck:codex/trust-after-proof-20260828-01",
            pr_number=17,
        )
        g1, c1 = decide(self.group_template, self.cancel_template, first)
        g2, c2 = decide(self.group_template, self.cancel_template, second)
        self.assertEqual(g1, g2)
        self.assertTrue(c1)
        self.assertTrue(c2)
        self.assertEqual(
            g1,
            "tests-pull_request-refs/pull/17/merge",
        )

    def test_distinct_prs_do_not_share_a_group_even_with_the_same_head(self):
        a = github_ctx("pull_request", 1, "woahwhattheheck:alpha", pr_number=17)
        b = github_ctx("pull_request", 2, "woahwhattheheck:alpha", pr_number=18)
        g1, _ = decide(self.group_template, self.cancel_template, a)
        g2, _ = decide(self.group_template, self.cancel_template, b)
        self.assertNotEqual(g1, g2)

    def test_main_pushes_share_group_and_cancel_older_runs(self):
        push_a = github_ctx("push", 32984511253)
        push_b = github_ctx("push", 33182674502)
        g1, c1 = decide(self.group_template, self.cancel_template, push_a)
        g2, c2 = decide(self.group_template, self.cancel_template, push_b)
        self.assertEqual(g1, "tests-push-refs/heads/main")
        self.assertEqual(g1, g2)
        self.assertTrue(c1)
        self.assertTrue(c2)

    def test_distinct_automatic_refs_remain_independent(self):
        main = github_ctx("push", 21)
        other = github_ctx("push", 22, ref="refs/heads/topic")
        g1, _ = decide(self.group_template, self.cancel_template, main)
        g2, _ = decide(self.group_template, self.cancel_template, other)
        self.assertNotEqual(g1, g2)

    def test_manual_dispatches_use_unique_run_ids_on_the_same_ref(self):
        groups = []
        for run_id in (4001, 4002):
            ctx = github_ctx("workflow_dispatch", run_id)
            group, _ = decide(self.group_template, self.cancel_template, ctx)
            groups.append(group)
            self.assertEqual(group, f"tests-workflow_dispatch-{run_id}")
        self.assertEqual(len(set(groups)), 2)

    def test_event_types_and_workflows_do_not_cross_cancel(self):
        contexts = [
            github_ctx("push", 21),
            github_ctx("pull_request", 11, pr_number=17),
            github_ctx("workflow_dispatch", 31),
            github_ctx("push", 22, workflow="other-battery"),
        ]
        groups = [
            decide(self.group_template, self.cancel_template, ctx)[0]
            for ctx in contexts
        ]
        self.assertEqual(len(set(groups)), len(contexts))

    def test_pr_fixture_ref_stays_stable_across_runs(self):
        first = github_ctx("pull_request", 11, pr_number=17)
        second = github_ctx("pull_request", 12, pr_number=17)
        self.assertEqual(first["github"]["ref"], "refs/pull/17/merge")
        self.assertEqual(first["github"]["ref"], second["github"]["ref"])
        self.assertEqual(first["github"]["event"]["pull_request"]["number"], 17)
        self.assertNotEqual(first["github"]["run_id"], second["github"]["run_id"])
        with self.assertRaises(ValueError):
            github_ctx("pull_request", 11)

    def test_event_simulation_supersedes_automatic_and_preserves_manual_runs(self):
        live = simulate(
            [
                {
                    "event_name": "pull_request",
                    "run_id": 11,
                    "pr_number": 17,
                    "head_label": "woahwhattheheck:codex/trust-after-proof-20260828-01",
                },
                {
                    "event_name": "pull_request",
                    "run_id": 12,
                    "pr_number": 17,
                    "head_label": "woahwhattheheck:codex/trust-after-proof-20260828-01",
                },
                {"event_name": "push", "run_id": 21},
                {"event_name": "push", "run_id": 22},
                {"event_name": "workflow_dispatch", "run_id": 31},
                {"event_name": "workflow_dispatch", "run_id": 32},
                {"event_name": "push", "run_id": 23},
                {
                    "event_name": "pull_request",
                    "run_id": 13,
                    "pr_number": 18,
                    "head_label": "woahwhattheheck:other-head",
                },
            ],
            self.group_template,
            self.cancel_template,
        )
        by_id = {row["run_id"]: row for row in live}
        self.assertEqual(by_id["11"]["status"], "cancelled")
        self.assertEqual(by_id["12"]["status"], "in_progress")
        for run_id in ("23", "31", "32", "13"):
            self.assertEqual(by_id[run_id]["status"], "in_progress", run_id)
        self.assertEqual(
            {row["run_id"] for row in live if row["status"] == "cancelled"},
            {"11", "21", "22"},
        )


if __name__ == "__main__":
    unittest.main()

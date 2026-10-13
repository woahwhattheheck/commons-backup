"""Review invariants against real Git objects and fast-forward races."""
import copy
import datetime as dt
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from host import coordination_state as cs
from host import swarm_review as sr


class ReviewGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git = cs.Git(str(self.root))
        self.git.out("init", "-b", "main")
        self.git.out("config", "user.name", "review test")
        self.git.out("config", "user.email", "test@example.invalid")
        for p, value in {"module.py": "old", "dep.py": "dependency",
                         sr.POLICY: "policy", "AGENTS.md": "entry",
                         sr.RELIABILITY: '{"outcomes":[]}'}.items():
            self.write(p, value)
        self.base = self.commit("base")
        self.git.out("checkout", "-b", "candidate")
        self.write("module.py", "new")
        self.head = self.commit("change")
        self.git.out("checkout", "main")
        self.work = {"seat": "MUSE", "family": "muse", "operation": "one-operation",
                     "read_paths": ["dep.py"],
                     "evidence": [{"result": "PASS", "reference": "actual check fixture"}]}
        self.pull = {"number": 1, "headRefOid": self.head, "baseRefName": "main",
                     "body": "```commons-work\n" + json.dumps(self.work) + "\n```"}
        self.subject = sr.change(self.git, self.base, self.pull)
        self.receipt = sr.review_template(self.subject)
        self.receipt.update(decision="PASS", reviewer={"seat": "ASTRA", "family": "gpt",
                            "session_ref": "test-session"}, summary="read actual diff",
                            evidence=self.work["evidence"])

    def write(self, name, value):
        p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(value)

    def commit(self, message):
        self.git.out("add", "."); self.git.out("commit", "-m", message)
        return self.git.out("rev-parse", "HEAD").strip()

    def review(self, value=None, **kw):
        return {"id": 1, "commit_id": self.head, "state": "COMMENTED",
                "submitted_at": "2026-09-12T22:00:00Z",
                "body": "```commons-gpt-review\n" + json.dumps(value or self.receipt) + "\n```", **kw}

    def test_non_gpt_needs_gpt(self):
        self.assertEqual("WAIT_GPT", sr.decision(self.git, self.subject, [])["state"])
        self.assertEqual("READY", sr.decision(self.git, self.subject, [self.review()])["state"])

    def test_unrelated_main_advance_reuses_review(self):
        self.write("unrelated.py", "another builder"); new = self.commit("unrelated")
        subject = sr.change(self.git, new, self.pull)
        self.assertEqual("READY", sr.decision(self.git, subject, [self.review()])["state"])

    def test_changed_dependency_revokes_cached_review(self):
        self.write("dep.py", "changed contract"); new = self.commit("dependency")
        subject = sr.change(self.git, new, self.pull)
        self.assertEqual("WAIT_GPT", sr.decision(self.git, subject, [self.review()])["state"])

    def test_changed_head_cannot_reuse_review(self):
        self.git.out("checkout", "candidate"); self.write("module.py", "new again")
        head = self.commit("more work"); pull = dict(self.pull, headRefOid=head)
        self.assertEqual("WAIT_GPT", sr.decision(self.git, sr.change(self.git, self.base, pull), [self.review()])["state"])

    def test_non_gpt_self_attestation_rejected(self):
        for family, seat in (("muse", "OTHER"), ("gpt", "MUSE")):
            value = copy.deepcopy(self.receipt); value["reviewer"].update(family=family, seat=seat)
            self.assertEqual("HOLD", sr.decision(self.git, self.subject, [self.review(value)])["state"])

    def test_gpt_is_a_builder_and_can_record_its_pass(self):
        self.subject["work"]["family"] = "gpt"
        value = copy.deepcopy(self.receipt); value["reviewer"]["seat"] = "MUSE"
        value["work_sha256"] = sr.work_digest(self.subject["work"])
        self.assertEqual("READY", sr.decision(self.git, self.subject, [self.review(value)])["state"])

    def test_hold_and_dismissal_supersede(self):
        hold = dict(self.receipt, decision="HOLD")
        self.assertEqual("HOLD", sr.decision(self.git, self.subject,
            [self.review(), self.review(hold, id=2, submitted_at="2026-09-12T22:01:00Z")])["state"])
        self.assertEqual("WAIT_GPT", sr.decision(self.git, self.subject,
            [self.review(state="DISMISSED")])["state"])

    def test_missing_dependency_or_test_evidence_rejected(self):
        value = copy.deepcopy(self.receipt); del value["read_set"]["dep.py"]
        self.assertEqual("HOLD", sr.decision(self.git, self.subject, [self.review(value)])["state"])

    def test_recent_regression_requires_an_independent_preflight(self):
        self.write(sr.RELIABILITY, json.dumps({"outcomes": [{"seat": "MUSE", "outcome": "regression",
                    "source_url": "https://example.invalid/incident", "observed_at": "2026-09-12T22:02:00Z"}]}))
        current = self.commit("record observed defect")
        subject = sr.change(self.git, current, self.pull)
        self.assertEqual("HOLD", sr.decision(self.git, subject, [self.review()])["state"])
        reviewed = dict(self.receipt, preflight={"seat": "OTHER", "evidence": self.work["evidence"]})
        self.assertEqual("READY", sr.decision(self.git, subject, [self.review(reviewed)])["state"])
        value = dict(self.receipt, evidence=[])
        self.assertEqual("HOLD", sr.decision(self.git, self.subject, [self.review(value)])["state"])

    def test_fast_forward_commit_cannot_land_over_unreviewed_main(self):
        changes = self.git.diff_tree(self.base, self.head)
        tree = self.git.compose(self.base, changes)
        merge = self.git.out("commit-tree", tree, "-p", self.base, "-p", self.head,
                             "-m", "reviewed merge").strip()
        self.write("dep.py", "concurrent dependency change")
        newer = self.commit("concurrent main")
        # A normal push accepts only if the remote tip is an ancestor of the
        # outgoing commit. Here it is not: no force or stale-base integration.
        self.assertNotEqual(0, self.git.run("merge-base", "--is-ancestor", newer, merge, check=False).returncode)
        self.assertEqual("new", self.git.out("show", merge + ":module.py"))


class Queue(unittest.TestCase):
    def test_hundred_prs_are_ten_batches_with_evidenced_builders(self):
        outcomes = [{"seat": "BUILDER", "outcome": "accepted", "source_url": "https://example.invalid/" + str(i),
                     "observed_at": "2026-09-12T20:00:00Z"} for i in range(10)]
        rows = [{"number": n, "paths": ["component/" + str(n)], "risk": "standard",
                 "work": {"seat": "BUILDER"}, "review": {"state": "WAIT_GPT"}} for n in range(100)]
        planned = sr.batches(rows, outcomes, capacity=0)
        self.assertEqual(10, len(planned)); self.assertTrue(all(x["dispatch"] == "STAGED" for x in planned))
        self.assertEqual(100, sum(len(x["prs"]) for x in planned))

    def test_colliding_changes_and_regressions_get_separate_review(self):
        rows = [{"number": n, "paths": ["same.py"], "risk": "standard",
                 "work": {"seat": "NEW"}, "review": {"state": "WAIT_GPT"}} for n in range(3)]
        self.assertEqual(3, len(sr.batches(rows)))
        outcomes = [{"seat": "NEW", "outcome": "regression", "source_url": "receipt", "observed_at": "2026-09-12"}]
        self.assertEqual("individual", sr.scrutiny("NEW", outcomes))
        self.assertEqual("new", sr.scrutiny("UNKNOWN", outcomes))

    def test_claim_future_heartbeat_holds_lane_fail_closed(self):
        now = dt.datetime(2026, 9, 12, tzinfo=dt.timezone.utc)
        self.assertTrue(cs._holding_live({"state": "HELD", "heartbeat_at": "2026-09-13T00:00:00Z", "ttl_s": 1800}, now))

    def test_duplicate_metadata_and_path_traversal_are_not_review_subjects(self):
        self.assertIsNone(sr.block('```commons-work\n{"seat":"A","seat":"B"}\n```', "commons-work"))
        self.assertFalse(sr.paths_valid(["../policy"]))


class ClosedPacket(unittest.TestCase):
    """Packet is a review aid: closed or merged PRs must not fail the CLI."""

    def test_merged_stub_is_already_present(self):
        row = sr.closed_packet(14900, {"state": "closed", "merged": True})
        self.assertEqual(14900, row["number"])
        self.assertEqual("ALREADY_PRESENT", row["review"]["state"])
        self.assertEqual("PR is no longer open", row["review"]["reason"])
        self.assertEqual({}, row["review_template"])
        self.assertEqual("", row["diff"])
        self.assertFalse(row["diff_truncated"])

    def test_closed_unmerged_stub_is_unknown(self):
        row = sr.closed_packet(12, {"state": "closed", "merged": False})
        self.assertEqual("UNKNOWN", row["review"]["state"])
        self.assertEqual("PR is no longer open", row["review"]["reason"])

    def test_packet_writes_stub_and_exits_zero(self):
        pulls = {
            14900: {"number": 14900, "state": "closed", "merged": True},
            12: {"number": 12, "state": "closed", "merged": False},
        }
        out = Path(tempfile.mkdtemp()) / "packet.json"
        with mock.patch.object(sr, "live_pull", side_effect=lambda _gh, n: pulls[n]) as live, \
             mock.patch.object(sr, "verify_live") as verify:
            code = sr.main(["packet", "--prs", "14900,12", "--out", str(out)])
        self.assertEqual(0, code)
        self.assertEqual(2, live.call_count)
        verify.assert_not_called()
        data = json.loads(out.read_text())
        self.assertEqual("commons-review-packet/v1", data["schema"])
        self.assertEqual([14900, 12], [row["number"] for row in data["prs"]])
        self.assertEqual("ALREADY_PRESENT", data["prs"][0]["review"]["state"])
        self.assertEqual("UNKNOWN", data["prs"][1]["review"]["state"])

    def test_check_and_merge_still_refuse_closed_prs(self):
        pull = {"number": 14900, "state": "closed", "merged": True}
        with mock.patch.object(sr, "live_pull", return_value=pull):
            for command in ("check", "merge"):
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    code = sr.main([command, "--pr", "14900"])
                self.assertEqual(1, code, command)
                payload = json.loads(buf.getvalue())
                self.assertEqual("UNKNOWN", payload["state"])
                self.assertIn("no longer open", payload["reason"])


class StaleExecutablePacket(unittest.TestCase):
    """Packet is a review aid: stale-vs-main executable PRs must still write a packet.

    command-center contracts already passed; aborting the packet CLI because
    main moved is a stale-base stopping condition, not a review-aid result.
    check/merge remain fail-closed on the same error.
    """

    REASON = "executable PR head must contain current main; recompose and rerun provider checks"

    def test_packet_writes_recompose_stub_and_exits_zero(self):
        pull = {"number": 16029, "state": "open", "merged": False}
        out = Path(tempfile.mkdtemp()) / "packet.json"
        with mock.patch.object(sr, "live_pull", return_value=pull), \
             mock.patch.object(sr, "verify_live", side_effect=ValueError(self.REASON)):
            code = sr.main(["packet", "--prs", "16029", "--out", str(out)])
        self.assertEqual(0, code)
        data = json.loads(out.read_text())
        self.assertEqual("commons-review-packet/v1", data["schema"])
        row = data["prs"][0]
        self.assertEqual(16029, row["number"])
        self.assertEqual("UNKNOWN", row["review"]["state"])
        self.assertIn("must contain current main", row["review"]["reason"])
        self.assertEqual({}, row["review_template"])
        self.assertEqual("", row["diff"])
        self.assertFalse(row["diff_truncated"])

    def test_mixed_batch_keeps_closed_and_stale_stubs(self):
        pulls = {
            12: {"number": 12, "state": "closed", "merged": False},
            16029: {"number": 16029, "state": "open", "merged": False},
        }
        out = Path(tempfile.mkdtemp()) / "packet.json"
        with mock.patch.object(sr, "live_pull", side_effect=lambda _gh, n: pulls[n]), \
             mock.patch.object(sr, "verify_live", side_effect=ValueError(self.REASON)):
            code = sr.main(["packet", "--prs", "12,16029", "--out", str(out)])
        self.assertEqual(0, code)
        data = json.loads(out.read_text())
        self.assertEqual([12, 16029], [row["number"] for row in data["prs"]])
        self.assertEqual("UNKNOWN", data["prs"][0]["review"]["state"])
        self.assertEqual("PR is no longer open", data["prs"][0]["review"]["reason"])
        self.assertIn("must contain current main", data["prs"][1]["review"]["reason"])

    def test_unrelated_packet_errors_still_fail_the_cli(self):
        pull = {"number": 9, "state": "open", "merged": False}
        out = Path(tempfile.mkdtemp()) / "packet.json"
        buf = io.StringIO()
        with mock.patch.object(sr, "live_pull", return_value=pull), \
             mock.patch.object(sr, "verify_live", side_effect=ValueError("malformed review history")), \
             mock.patch("sys.stdout", buf):
            code = sr.main(["packet", "--prs", "9", "--out", str(out)])
        self.assertEqual(1, code)
        self.assertFalse(out.exists())
        payload = json.loads(buf.getvalue())
        self.assertEqual("UNKNOWN", payload["state"])
        self.assertIn("malformed review history", payload["reason"])

    def test_check_and_merge_still_refuse_stale_executable_heads(self):
        with mock.patch.object(sr, "verify_live", side_effect=ValueError(self.REASON)):
            for command in ("check", "merge"):
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    code = sr.main([command, "--pr", "16029"])
                self.assertEqual(1, code, command)
                payload = json.loads(buf.getvalue())
                self.assertEqual("UNKNOWN", payload["state"])
                self.assertIn("must contain current main", payload["reason"])


if __name__ == "__main__":
    unittest.main()

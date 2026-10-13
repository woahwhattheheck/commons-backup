from __future__ import annotations
import datetime as dt
import importlib.util
import sys
import unittest
from pathlib import Path
MODULE_PATH = Path(__file__).with_name('cancel_superseded_queued_runs.py')
SPEC = importlib.util.spec_from_file_location('queue_cancel', MODULE_PATH)
queue_cancel = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = queue_cancel
SPEC.loader.exec_module(queue_cancel)
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 14, 5, 10, tzinfo=UTC)

def run(run_id: int, *, sha: str='a' * 40, created: str='2026-09-14T04:00:00Z', pr: int | None=7, workflow_id: int=12, event: str='pull_request', branch: str='feature'):
    return {'id': run_id, 'workflow_id': workflow_id, 'name': 'CI', 'event': event, 'head_branch': branch, 'head_sha': sha, 'created_at': created, 'pull_requests': [] if pr is None else [{'number': pr}]}

class FakeClient:

    def __init__(self, runs, prs):
        self._runs = runs
        self._prs = prs
        self.pr_reads = []

    def queued_runs(self, repository):
        return list(self._runs)

    def pull_request(self, repository, number):
        self.pr_reads.append((repository, number))
        return self._prs[number]

class ClassifierTests(unittest.TestCase):

    def analyze(self, runs, prs, *, dedupe=False, age=15):
        client = FakeClient(runs, prs)
        queued, candidates = queue_cancel.analyze_repository(client, 'owner/repo', minimum_age=dt.timedelta(minutes=age), dedupe_exact=dedupe, now=NOW)
        return (queued, candidates, client)

    def test_closed_pr_is_candidate(self):
        _, candidates, _ = self.analyze([run(1)], {7: {'state': 'closed', 'head': {'sha': 'a' * 40}}})
        self.assertEqual([candidate.run_id for candidate in candidates], [1])
        self.assertIn('closed', candidates[0].reason)

    def test_moved_open_pr_head_is_candidate(self):
        _, candidates, _ = self.analyze([run(2, sha='a' * 40)], {7: {'state': 'open', 'head': {'sha': 'b' * 40}}})
        self.assertEqual([candidate.run_id for candidate in candidates], [2])
        self.assertIn('differs', candidates[0].reason)

    def test_current_open_pr_head_is_preserved(self):
        _, candidates, _ = self.analyze([run(3, sha='a' * 40)], {7: {'state': 'open', 'head': {'sha': 'a' * 40}}})
        self.assertEqual(candidates, [])

    def test_recent_run_is_preserved_without_pr_read(self):
        _, candidates, client = self.analyze([run(4, created='2026-09-14T05:05:00Z')], {7: {'state': 'closed', 'head': {'sha': 'a' * 40}}}, age=15)
        self.assertEqual(candidates, [])
        self.assertEqual(client.pr_reads, [])

    def test_push_run_without_pr_is_not_cancelled_by_default(self):
        _, candidates, _ = self.analyze([run(5, pr=None, event='push')], {})
        self.assertEqual(candidates, [])

    def test_exact_duplicate_keeps_newest(self):
        older = run(6, created='2026-09-14T03:00:00Z', pr=None)
        newer = run(7, created='2026-09-14T04:00:00Z', pr=None)
        _, candidates, _ = self.analyze([older, newer], {}, dedupe=True)
        self.assertEqual([candidate.run_id for candidate in candidates], [6])
        self.assertIn('keeping newer queued run 7', candidates[0].reason)

    def test_nonidentical_heads_are_not_deduplicated(self):
        first = run(8, sha='a' * 40, pr=None)
        second = run(9, sha='b' * 40, pr=None)
        _, candidates, _ = self.analyze([first, second], {}, dedupe=True)
        self.assertEqual(candidates, [])

    def test_pr_is_cached_across_many_workflows(self):
        runs = [run(10, workflow_id=100), run(11, workflow_id=101), run(12, workflow_id=102)]
        _, candidates, client = self.analyze(runs, {7: {'state': 'closed', 'head': {'sha': 'a' * 40}}})
        self.assertEqual(len(candidates), 3)
        self.assertEqual(client.pr_reads, [('owner/repo', 7)])
if __name__ == '__main__':
    unittest.main(verbosity=2)

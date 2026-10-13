#!/usr/bin/env python3
"""Keep the transport workflow's path filters tied to the suites it executes.

Stdlib only: this checks the workflow's deliberately simple literal/** filters,
not arbitrary YAML or the complete GitHub glob language. No provider calls.
"""
from __future__ import annotations

from pathlib import Path
import re
import shlex
import unittest

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/commons-transport-regression.yml"
SELF = Path(__file__).name
NATIVE_SUITES = (
    "test_commons_transport_outcomes",
    "test_claude_client_transport_outcomes",
    "test_toolbench_snapshot_consistency",
    "test_gemini_peer_tool_gateway",
    "test_gemini_tool_result_boundary",
    "test_toolbench",
    "test_client",
    "test_claude_headless",
    "integrations.shared_equipment.test_equipment",
)
DEPENDENCIES = (
    "host/toolbench.py",
    "toolbench/example.json",
    "integrations/claude_headless/client.py",
    "integrations/claude_headless/gateway.py",
)


def event_paths(text: str, event: str) -> tuple[str, ...]:
    block = re.search(
        rf"^  {re.escape(event)}:\n(.*?)(?=^  \S|^\S|\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    if block is None:
        raise AssertionError(f"missing {event} event")
    paths = re.search(r"^    paths:\n((?:      - [^\n]+\n)+)",
                      block.group(1), re.MULTILINE)
    if paths is None:
        raise AssertionError(f"missing {event} paths")
    result = []
    for line in paths.group(1).splitlines():
        items = shlex.split(line.strip()[2:], comments=True)
        if len(items) != 1 or not re.fullmatch(r"[\w./-]+(?:/\*\*)?", items[0]):
            raise AssertionError("update the contract reader for this path syntax")
        result.append(items[0])
    return tuple(result)


def covers(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return pattern == path


def missing_paths(text: str, event: str, paths: tuple[str, ...]) -> list[str]:
    patterns = event_paths(text, event)
    return [path for path in paths if not any(covers(p, path) for p in patterns)]


def native_suites(text: str) -> tuple[str, ...]:
    folded = re.search(r"^        run: >-\n((?:          [^\n]+\n)+)",
                       text, re.MULTILINE)
    if folded is None:
        raise AssertionError("missing folded native regression command")
    words = shlex.split(" ".join(line.strip() for line in folded.group(1).splitlines()))
    prefix = ["python", "-W", "error", "-m", "unittest", "-v"]
    if words[:len(prefix)] != prefix:
        raise AssertionError("native regression command changed")
    return tuple(words[len(prefix):])


class TransportWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_all_nine_existing_suites_are_preserved(self):
        self.assertEqual(native_suites(self.text), NATIVE_SUITES)

    def test_each_executed_suite_triggers_push_and_pull_request(self):
        paths = tuple(suite.replace(".", "/") + ".py"
                      for suite in native_suites(self.text))
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(missing_paths(self.text, event, paths), [])

    def test_runtime_and_example_changes_trigger_both_events(self):
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(missing_paths(self.text, event, DEPENDENCIES), [])

    def test_workflow_and_its_contract_test_trigger_both_events(self):
        paths = (WORKFLOW.relative_to(ROOT).as_posix(), SELF)
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(missing_paths(self.text, event, paths), [])

    def test_push_and_pull_request_coverage_match(self):
        push = event_paths(self.text, "push")
        pull = event_paths(self.text, "pull_request")
        self.assertEqual(push, pull)
        self.assertEqual(len(push), len(set(push)), "duplicate trigger patterns")

    def test_contract_runs_before_archive_with_workflow_available(self):
        checkout = "            .github/workflows\n"
        command = "python -m unittest -v test_commons_transport_workflow"
        archive = "      - name: Archive the selected committed test sources"
        self.assertIn(checkout, self.text)
        self.assertIn(command, self.text)
        self.assertLess(self.text.index(checkout), self.text.index(command))
        self.assertLess(self.text.index(command), self.text.index(archive))

    def test_unrelated_changes_do_not_trigger_transport_work(self):
        unrelated = ("README.md", "p/unrelated.md", "test_unrelated.py",
                     "cloud-integration-differentials/main.py",
                     "integrations/claude_headless_other/gateway.py")
        for event in ("push", "pull_request"):
            self.assertEqual(missing_paths(self.text, event, unrelated), list(unrelated))

    def test_reader_distinguishes_literal_and_directory_boundaries(self):
        self.assertTrue(covers("toolbench/**", "toolbench/example.json"))
        self.assertFalse(covers("toolbench/**", "toolbench_other/example.json"))
        self.assertFalse(covers("test_client.py", "nested/test_client.py"))
        with self.assertRaisesRegex(AssertionError, "missing push"):
            event_paths("on:\n  workflow_dispatch:\n", "push")
        with self.assertRaisesRegex(AssertionError, "path syntax"):
            event_paths("on:\n  push:\n    paths:\n      - '!test_client.py'\n", "push")


if __name__ == "__main__":
    unittest.main()

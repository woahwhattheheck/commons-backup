# SPDX-License-Identifier: Apache-2.0
"""Regression bindings in the existing TITAN validation workflow.

Uses the standard library only. These checks cover workflow structure, source
closure and shell error propagation; the unchanged peer suites execute separately.
"""
import argparse
import ast
from pathlib import Path
import re
import sys
import textwrap
import unittest

WORKFLOW = (Path(__file__).resolve().parent /
            '../../../../.github/workflows/titan-selected-projection.yml').resolve()
PREFIX = 'revenue/kaggriculture/'
SOURCES = (
    PREFIX + 'cloud-market-game-theory/adaptive/runtime.py',
    PREFIX + 'cloud-market-game-theory/adaptive/test_capture_binding.py',
    PREFIX + 'cloud-market-game-theory/adaptive/recourse.py',
    PREFIX + 'cloud-execution-lab/test_score_schedule.py',
    PREFIX + 'cloud-economic-stress/deadline_adapter.py',
    PREFIX + 'cloud-economic-stress/test_runner.py',
    PREFIX + 'cloud-economic-stress/test_caller_handler.py',
)
NEW_STEPS = {
    'Selected-market ledger schedule parity tests': (
        PREFIX + 'cloud-selected-market-checks/test_ledger_schedule.py',
        'ledger-schedule-tests.log'),
    'Deadline cancellation regression tests': (
        PREFIX + 'cloud-economic-stress/cancellation/test_deadline_cancellation.py',
        'deadline-cancellation-tests.log'),
    'Caller handler replacement boundary tests': (
        PREFIX + 'cloud-economic-stress/test_caller_handler.py',
        'caller-handler-tests.log'),
    'Adaptive actor capture binding tests': (
        SOURCES[1], 'capture-binding-tests.log'),
    'Dated market score schedule parity tests': (
        SOURCES[3], 'score-schedule-tests.log'),
    'Existing workflow regression binding tests': (
        PREFIX + 'cloud-composition-cases/cover/test_regression_bindings.py',
        'workflow-bindings-tests.log'),
}


def named_step(text, name):
    marker = '      - name: ' + name + '\n'
    if text.count(marker) != 1:
        raise AssertionError('Expected exactly one step: ' + name)
    tail = text.split(marker, 1)[1]
    return re.split(r'^      - (?:name|uses):', tail, maxsplit=1, flags=re.M)[0]


class RegressionBindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf-8')

    def test_changed_sources_trigger_existing_workflow(self):
        paths = self.text.split('    paths:\n', 1)[1].split('  workflow_dispatch:', 1)[0]
        for path in SOURCES + (PREFIX + 'cloud-composition-cases/cover/**',
                               PREFIX + 'cloud-economic-stress/cancellation/**'):
            with self.subTest(path=path):
                self.assertIn("      - '" + path + "'\n", paths)

    def test_source_closure_is_checked_out(self):
        sparse = self.text.split('          sparse-checkout: |\n', 1)[1]
        sparse = sparse.split('      - name:', 1)[0]
        for path in SOURCES + (
                '.github/workflows/titan-selected-projection.yml',
                PREFIX + 'cloud-composition-cases/cover/',
                PREFIX + 'cloud-economic-stress/cancellation/'):
            with self.subTest(path=path):
                self.assertIn('            /' + path + '\n', sparse)

    def test_new_sources_and_workflow_are_recorded(self):
        step = named_step(self.text, 'Record committed test and runtime inputs')
        code = textwrap.dedent(step.split('        run: |\n', 1)[1])
        tree = ast.parse(code)
        roots = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                     if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'roots' for t in node.targets))
        self.assertIn('cloud-market-game-theory/adaptive', roots)
        self.assertIn('cloud-composition-cases/cover', roots)
        self.assertIn('cloud-economic-stress', roots)
        self.assertIn("paths.append(Path('.github/workflows/titan-selected-projection.yml'))", code)

    def test_suites_execute_once_with_preserved_failure_status(self):
        for name, (path, log) in NEW_STEPS.items():
            with self.subTest(name=name):
                step = named_step(self.text, name)
                self.assertIn('        shell: bash\n', step)
                self.assertIn('set -euo pipefail', step)
                self.assertIn('python3 -B ' + path, step)
                self.assertIn('2>&1 | tee "$RUNNER_TEMP/projection-validation/' + log + '"', step)
                self.assertNotIn('continue-on-error:', step)
                self.assertNotIn('|| true', step)

    def test_named_steps_still_run_after_an_earlier_failure(self):
        for name in NEW_STEPS:
            with self.subTest(name=name):
                self.assertIn('        if: ${{ !cancelled() }}\n', named_step(self.text, name))

    def test_capture_machine_readable_report_is_retained(self):
        step = named_step(self.text, 'Adaptive actor capture binding tests')
        self.assertIn('--report "$RUNNER_TEMP/projection-validation/capture-binding-results.json"', step)
        self.assertIn('      - uses: actions/upload-artifact@v4\n        if: ${{ always() }}', self.text)
        self.assertIn('          path: ${{ runner.temp }}/projection-validation/', self.text)

    def test_cancellation_machine_readable_report_is_retained(self):
        step = named_step(self.text, 'Deadline cancellation regression tests')
        self.assertIn('--report "$RUNNER_TEMP/projection-validation/deadline-cancellation.json"', step)
        self.assertNotIn('thread', step)
        self.assertNotIn('pytest', step)

    def test_caller_handler_machine_readable_report_is_retained(self):
        step = named_step(self.text, 'Caller handler replacement boundary tests')
        self.assertIn('--report "$RUNNER_TEMP/projection-validation/caller-handler-results.json"', step)
        self.assertNotIn('--adapter', step)
        self.assertNotIn('pytest', step)

    def test_checkout_and_snapshot_bind_the_same_event_commit(self):
        self.assertIn('          ref: ${{ github.sha }}\n', self.text)
        self.assertNotIn('github.event.pull_request.head.sha || github.sha', self.text)
        step = named_step(self.text, 'Record committed test and runtime inputs')
        self.assertIn("assert checkout == os.environ['GITHUB_SHA']", step)
        self.assertIn("'source_context': context", step)
        for key in ('event_sha', 'pull_request_head', 'pull_request_base', 'checkout_semantics'):
            self.assertIn("'" + key + "'", step)

    def test_ledger_runs_with_existing_official_engine_inputs(self):
        step = named_step(self.text, 'Selected-market ledger schedule parity tests')
        for option in ('--lab', '--evaluator', '--engine-loader', '--engine-cache', '--report'):
            self.assertIn(option + ' ', step)
        self.assertIn('ledger-schedule-results.json', step)
        self.assertNotIn('--benchmark', step)
        self.assertIn('            /' + PREFIX + 'cloud-selected-market-checks/\n', self.text)
        self.assertIn("      - '" + PREFIX + "cloud-selected-market-checks/**'\n", self.text)

    def test_existing_seven_execution_suites_are_preserved(self):
        for name in (
            'Existing selected-action SELL interface tests',
            'Projection and ordered-transfer consumer tests',
            'Existing market-contract consumer tests',
            'Explicit and default offline loader binding tests',
            'Empty-lot selected-action fallback tests',
            'Joined ordered selected-action SELL tests',
            'Funded seed queue joined integration tests',
        ):
            with self.subTest(name=name):
                self.assertIn('python3 ', named_step(self.text, name))

    def test_frozen_source_transfer_stays_hash_bound(self):
        step = named_step(self.text, 'Record committed test and runtime inputs')
        self.assertIn('assert len(frozen_bytes) == 103527', step)
        self.assertIn('95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153', step)
        self.assertIn('(out/frozen.name).write_bytes(frozen_bytes)', step)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--workflow', type=Path, default=WORKFLOW)
    args, remaining = parser.parse_known_args()
    WORKFLOW = args.workflow
    unittest.main(argv=[sys.argv[0]] + remaining)

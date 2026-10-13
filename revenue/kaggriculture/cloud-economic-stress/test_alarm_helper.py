# SPDX-License-Identifier: Apache-2.0
"""Compose unchanged caller-timer tests with direct alarm-helper compatibility.

All CLI options are the existing test_deadline_contract.py options. The extra
three methods keep direct cancellation helpers distinct from external alarms.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import types
import test_deadline_contract as c


class AlarmHelperTests(c.TimerContractTests):
    def test_direct_alarm_helper_uses_active_guard_in_all_stages(self):
        for stage in ('production', 'transform', 'before_transform'):
            with self.subTest(stage=stage):
                actor = c.BoundaryActor()
                def alarm(*args, **kwargs):
                    c.D._alarm(None, None)
                callback = None
                if stage == 'production':
                    actor.production = types.SimpleNamespace(act=alarm)
                elif stage == 'transform':
                    actor.transform = alarm
                else:
                    callback = alarm
                guard = c.D.DeadlineFallbackAgent(actor, before_transform=callback)
                expected = c.D.legal_pass(c.fixture()) if stage == 'production' else actor.action
                self.assertEqual(guard(c.fixture()), expected)
                self.assertEqual(guard.diagnostics['status'], 'deadline_fallback')
                self.assertEqual(guard.diagnostics['fallback_stage'],
                                 'production' if stage == 'production' else 'transform')
                self.assertIsNone(c.D._ACTIVE_TIMER.get())

    def test_caller_alarm_helper_does_not_acquire_inner_guard_identity(self):
        self.arm(.025, handler=c.D._alarm)
        guard = c.D.DeadlineFallbackAgent(c.BoundaryActor(production_delay=.1),
                                        budget_seconds=.3)
        with self.assertRaises(c.D.DeadlineExceeded):
            guard(c.fixture())
        self.assertEqual(guard.diagnostics, {})
        self.assertIsNone(c.D._ACTIVE_TIMER.get())

    def test_alarm_helper_outside_guard_keeps_control_flow_exception(self):
        with self.assertRaises(c.D.DeadlineExceeded) as caught:
            c.D._alarm(None, None)
        self.assertNotIsInstance(caught.exception, Exception)
        self.assertIsNone(c.D._ACTIVE_TIMER.get())


def main():
    c.TimerContractTests = AlarmHelperTests
    code = c.main()
    if c.OPTIONS.report:
        report = json.loads(c.OPTIONS.report.read_text())
        report["source_sha256"]["helper_tests"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        c.OPTIONS.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

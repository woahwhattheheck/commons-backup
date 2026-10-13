# SPDX-License-Identifier: Apache-2.0
"""Optional timing observer for an existing policy factory and bound callable.

Arity, loading, game execution and policy decisions remain the caller's. This
observer invokes a factory or policy once, forwards arguments unchanged and
propagates its exceptions. It does not enforce a timeout or retry an action.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class TimingRecord:
    """One factory attempt and, if successful, its one actor's action timings."""

    initialization_s: float | None = None
    initialization_failed: bool = False
    first_action_s: float | None = None
    max_action_s: float | None = None
    max_later_action_s: float | None = None
    calls: int = 0
    failures: int = 0

    def snapshot(self) -> dict[str, Any]:
        combined = None
        if self.initialization_s is not None and self.first_action_s is not None:
            combined = self.initialization_s + self.first_action_s
        return {
            "scope": "in_process_supplied_factory_and_actions",
            "initialization_s": self.initialization_s,
            "initialization_failed": self.initialization_failed,
            "first_action_s": self.first_action_s,
            "initialization_plus_first_action_s": combined,
            "max_action_s": self.max_action_s,
            "max_later_action_s": self.max_later_action_s,
            "calls": self.calls,
            "failures": self.failures,
        }


class TimedAgent:
    """Observe an already-bound callable; do not select or retry its call shape."""

    def __init__(self, policy: Callable[..., Any], record: TimingRecord,
                 clock: Callable[[], float] = time.perf_counter):
        self.policy = policy
        self.record = record
        self.clock = clock

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        start = self.clock()
        first = self.record.calls == 0
        self.record.calls += 1
        failed = True
        try:
            result = self.policy(*args, **kwargs)
            failed = False
            return result
        finally:
            elapsed = self.clock() - start
            if first:
                self.record.first_action_s = elapsed
            else:
                previous = self.record.max_later_action_s
                self.record.max_later_action_s = elapsed if previous is None else max(previous, elapsed)
            previous = self.record.max_action_s
            self.record.max_action_s = elapsed if previous is None else max(previous, elapsed)
            self.record.failures += int(failed)

    def timings(self) -> dict[str, Any]:
        return self.record.snapshot()


class TimedFactory:
    """Wrap the executor's existing factory; retain initialization failures too.

    `last_record` describes the latest factory attempt. Successful actors retain
    their own independent records, so creating another actor does not replace
    an earlier actor's telemetry. For parallel factory calls use one observer
    per match, as shown in README; the policy itself need not be changed.
    """

    def __init__(self, factory: Callable[..., Callable[..., Any]], *,
                 clock: Callable[[], float] = time.perf_counter):
        self.factory = factory
        self.clock = clock
        self.last_record: TimingRecord | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> TimedAgent:
        record = TimingRecord()
        self.last_record = record
        start = self.clock()
        failed = True
        try:
            policy = self.factory(*args, **kwargs)
            failed = False
            return TimedAgent(policy, record, self.clock)
        finally:
            record.initialization_s = self.clock() - start
            record.initialization_failed = failed

    def timings(self) -> dict[str, Any] | None:
        return None if self.last_record is None else self.last_record.snapshot()

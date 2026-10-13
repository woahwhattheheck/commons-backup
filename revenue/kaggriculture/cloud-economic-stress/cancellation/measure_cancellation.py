# SPDX-License-Identifier: Apache-2.0
"""Run one source-bound one-second cancellation probe in a fresh process.

This uses the real retained PlanOverlay._commit body and an injected slow
chooser/transform. It is not a full-game or natural-timeout measurement.
"""
from __future__ import annotations
import argparse
import copy
import json
import time
from pathlib import Path
import test_deadline_cancellation as tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget', type=float, default=1.0)
    parser.add_argument('--reserve', type=float, default=.002)
    args = parser.parse_args()
    tests.D = tests.load_module('measured_deadline', args.adapter)
    def slow_risk():
        time.sleep(args.budget + .2)
        return 3
    def after_swallowed_alarm(*_args, **_kwargs):
        time.sleep(.05)
        return copy.deepcopy(tests.TRANSFORMED)
    integrated = tests.Integrated(tests.Production(slow_risk), after_swallowed_alarm)
    guard = tests.D.DeadlineFallbackAgent(integrated, args.budget, args.reserve)
    started = time.perf_counter()
    action = guard(tests.OBS, {})
    elapsed = time.perf_counter() - started
    result = {'kind': 'injected_source_boundary_not_full_game',
              'adapter': str(args.adapter), 'budget_seconds': args.budget,
              'reserve_seconds': args.reserve, 'elapsed_seconds': elapsed,
              'production_calls': integrated.production.calls,
              'transform_calls': integrated.transform_calls,
              'action': action, 'diagnostics': guard.diagnostics}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()

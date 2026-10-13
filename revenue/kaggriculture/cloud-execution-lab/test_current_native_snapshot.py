# SPDX-License-Identifier: Apache-2.0
"""Predecessor-killing contracts for current-native snapshot classification."""
from pathlib import Path
import re

from current_native_snapshot import (
    B567,
    B567_EXPECTED_LIVE,
    B567_PREIMAGE_RUNTIME,
    CURRENT_REBIND,
    classify_b567_transition,
    predecessor_b567_refresh_error,
)

WORKFLOW = (
    Path(__file__).resolve().parents[3]
    / '.github/workflows/titan-v4-current-native.yml'
)
# Exact failed-run live blob for main.py at 97986d1013df6198fe77151fcdab4bdd2d3fe676.
FAILED_MAIN_PY = 'a015fef88d855d6d9c50f9d36e2551abd8829996'


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def matching_live():
    return dict(B567_EXPECTED_LIVE)


def test_exact_rebind_refresh_is_authenticated():
    status = classify_b567_transition(
        old_sha=B567,
        live_blobs=matching_live(),
        old_runtime_blob=B567_PREIMAGE_RUNTIME,
        changed_members=['SOURCE.json', 'titan_runtime.py'],
    )
    check(status['authenticated'] is True, 'exact b567 refresh lost its claim')
    check(status['drift'] is None, status['drift'])
    check(status['preimage']['inner_tar_sha256'] == B567, status['preimage'])
    check(status['preimage']['runtime_git_blob'] == B567_PREIMAGE_RUNTIME, status['preimage'])
    check(predecessor_b567_refresh_error(status) is None, predecessor_b567_refresh_error(status))


def test_production_main_py_drift_does_not_kill_snapshot():
    live = matching_live()
    live['main.py'] = FAILED_MAIN_PY
    status = classify_b567_transition(
        old_sha=B567,
        live_blobs=live,
        old_runtime_blob=B567_PREIMAGE_RUNTIME,
        changed_members=['SOURCE.json', 'main.py', 'titan_runtime.py'],
    )
    check(status['authenticated'] is False, 'drifted main.py was labeled a b567 transition')
    check(status['preimage'] is None, status['preimage'])
    error = predecessor_b567_refresh_error(status)
    check(
        error == (
            'b567 refresh precondition drift for main.py: '
            f'expected {B567_EXPECTED_LIVE["main.py"]}, observed {FAILED_MAIN_PY}'
        ),
        error,
    )
    names = [item['name'] for item in status['drift']['live_blob_drift']]
    check(names == ['main.py'], names)


def test_non_b567_archive_is_a_current_source_snapshot():
    status = classify_b567_transition(
        old_sha='0' * 64,
        live_blobs=matching_live(),
        old_runtime_blob=B567_PREIMAGE_RUNTIME,
        changed_members=['SOURCE.json', 'titan_runtime.py'],
    )
    check(status == {'authenticated': False, 'preimage': None, 'drift': None}, status)


def test_unexpected_delta_is_not_a_b567_transition():
    status = classify_b567_transition(
        old_sha=B567,
        live_blobs=matching_live(),
        old_runtime_blob=B567_PREIMAGE_RUNTIME,
        changed_members=['SOURCE.json', 'scheduler.py', 'titan_runtime.py'],
    )
    check(status['authenticated'] is False, 'dirty delta was labeled a b567 transition')
    check(
        predecessor_b567_refresh_error(status)
        == 'b567 refresh changed unexpected package members: SOURCE.json,scheduler.py,titan_runtime.py',
        predecessor_b567_refresh_error(status),
    )


def test_wrong_preimage_runtime_is_not_a_b567_transition():
    status = classify_b567_transition(
        old_sha=B567,
        live_blobs=matching_live(),
        old_runtime_blob=CURRENT_REBIND,
        changed_members=['SOURCE.json', 'titan_runtime.py'],
    )
    check(status['authenticated'] is False, 'wrong preimage was labeled a b567 transition')
    check(
        predecessor_b567_refresh_error(status)
        == 'b567 preimage runtime is not the authenticated predecessor',
        predecessor_b567_refresh_error(status),
    )


def test_workflow_classifies_drift_instead_of_exiting():
    text = WORKFLOW.read_text(encoding='utf-8')
    check('current_native_snapshot' in text, 'workflow does not load the classifier')
    check('classify_b567_transition' in text, 'workflow does not classify the b567 claim')
    check(
        "raise SystemExit(\n                          f'b567 refresh precondition drift for {name}: '"
        not in text,
        'workflow still kills the publisher on live-blob drift',
    )
    check(
        re.search(r"authenticated_b567_transition.*=.*old_sha == b567", text) is None,
        'workflow still claims every b567 archive is an authenticated transition',
    )


def run():
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith('test_') and callable(value)
    ]
    for test in tests:
        test()
    print(f'PASS {len(tests)}/{len(tests)}')


if __name__ == '__main__':
    run()

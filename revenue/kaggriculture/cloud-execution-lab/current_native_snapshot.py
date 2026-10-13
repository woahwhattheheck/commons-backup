# SPDX-License-Identifier: Apache-2.0
"""Classify the b567 current-native snapshot claim without killing the publisher.

The committed foundation archive remains b567. The Actions publisher still
renders the live source tree into an artifact. The b567 REBIND refresh is an
authenticated claim that is true only when live production blobs and the
package delta match that one-time transition. Source drift must not prevent a
current-source snapshot artifact, and it must not be labeled a b567 transition.
"""
from __future__ import annotations

B567 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
CURRENT_REBIND = '6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0'
B567_PREIMAGE_RUNTIME = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
B567_EXPECTED_LIVE = {
    'main.py': '4a8cf7bcda1f0fea231a144692cb84a779a9e73e',
    'TITAN-CONFIG.json': '3a3bef83899d3010fad623b628d9e95d9978111b',
    'frozen_selected.py': 'fc7baf5c179818a55037f6a61d92984d81d1a21c',
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'titan_runtime.py': CURRENT_REBIND,
}
B567_REFRESH_MEMBERS = ('SOURCE.json', 'titan_runtime.py')
B567_PREIMAGE = {
    'actions_artifact_id': 10180428228,
    'inner_tar_sha256': B567,
    'runtime_git_blob': B567_PREIMAGE_RUNTIME,
}


def classify_b567_transition(
    *,
    old_sha: str,
    live_blobs: dict[str, str],
    old_runtime_blob: str | None,
    changed_members: list[str],
) -> dict:
    """Return the b567 claim for one rendered snapshot.

    The predecessor publisher raised SystemExit on live-blob drift, so every
    later source SHA failed before emitting an artifact. Classification is
    fail-closed on the claim only.
    """
    if old_sha != B567:
        return {
            'authenticated': False,
            'preimage': None,
            'drift': None,
        }

    live_blob_drift = []
    for name, expected in B567_EXPECTED_LIVE.items():
        observed = live_blobs.get(name)
        if observed != expected:
            live_blob_drift.append({
                'name': name,
                'expected': expected,
                'observed': observed,
            })
    preimage_runtime_ok = old_runtime_blob == B567_PREIMAGE_RUNTIME
    changed = list(changed_members)
    delta_ok = changed == list(B567_REFRESH_MEMBERS)
    if not live_blob_drift and preimage_runtime_ok and delta_ok:
        return {
            'authenticated': True,
            'preimage': dict(B567_PREIMAGE),
            'drift': None,
        }
    return {
        'authenticated': False,
        'preimage': None,
        'drift': {
            'live_blob_drift': live_blob_drift,
            'preimage_runtime_ok': preimage_runtime_ok,
            'changed_members': changed,
            'expected_changed_members': list(B567_REFRESH_MEMBERS),
        },
    }


def predecessor_b567_refresh_error(status: dict) -> str | None:
    """Reproduce the Actions SystemExit text the predecessor used on drift."""
    drift = status.get('drift') or {}
    live_blob_drift = drift.get('live_blob_drift') or []
    if live_blob_drift:
        item = live_blob_drift[0]
        return (
            f"b567 refresh precondition drift for {item['name']}: "
            f"expected {item['expected']}, observed {item['observed']}"
        )
    if drift.get('preimage_runtime_ok') is False:
        return 'b567 preimage runtime is not the authenticated predecessor'
    changed = drift.get('changed_members')
    expected = drift.get('expected_changed_members')
    if changed is not None and changed != expected:
        return 'b567 refresh changed unexpected package members: ' + ','.join(changed)
    return None

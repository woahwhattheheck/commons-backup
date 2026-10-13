# SPDX-License-Identifier: Apache-2.0
"""Generate an exact evaluator copy with tested-seat action fingerprints.

The generic evaluator already hashes the joint trace.  This additive copy also
hashes only the tested arm's returned actions, making control/candidate action
identity independent of opponent reactions after the first divergence.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXPECTED_EVALUATOR_GIT_BLOB = "077feb2208b6e0c1727835eb4f8089709bf67f3b"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def transform(source: bytes) -> bytes:
    actual = git_blob(source)
    if actual != EXPECTED_EVALUATOR_GIT_BLOB:
        raise RuntimeError(
            f"evaluator source drift: expected {EXPECTED_EVALUATOR_GIT_BLOB}, got {actual}"
        )
    replacements = [
        (
            b"    actors, trace = [], hashlib.sha256()\n",
            b"    actors, trace = [], hashlib.sha256()\n"
            b"    tested_actions = hashlib.sha256(); tested_action_count = 0\n",
        ),
        (
            b"            for seat in range(2):\n                state[seat].action = actions[seat]\n",
            b"            tested_actions.update(encoded(actions[candidate_seat]))\n"
            b"            tested_action_count += 1\n"
            b"            for seat in range(2):\n                state[seat].action = actions[seat]\n",
        ),
        (
            b"        result[\"driver_cpu_seconds\"] = time.process_time() - initial_cpu\n",
            b"        result[\"driver_cpu_seconds\"] = time.process_time() - initial_cpu\n"
            b"        result[\"tested_action_sha256\"] = tested_actions.hexdigest()\n"
            b"        result[\"tested_action_count\"] = tested_action_count\n",
        ),
    ]
    out = source
    for old, new in replacements:
        count = out.count(old)
        if count != 1:
            raise RuntimeError(f"evaluator patch anchor cardinality drift: {count}")
        out = out.replace(old, new, 1)
    if out == source:
        raise RuntimeError("evaluator trace patch made no change")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    data = args.source.read_bytes()
    out = transform(data)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_bytes(out)
    print(
        "{" +
        f'"source_git_blob":"{git_blob(data)}",' +
        f'"generated_git_blob":"{git_blob(out)}",' +
        f'"generated_sha256":"{hashlib.sha256(out).hexdigest()}"' +
        "}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

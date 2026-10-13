# SPDX-License-Identifier: Apache-2.0
"""Source-pinned experiment composer; writes a NEW component, never production."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

EXPECTED_BLOB = "f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3"
HELPER = 'def _single_burst_timing_envelope(scenarios, now, end, rival_quantity):\n    """Research-only fixed-stock timing stresses, not a hidden-stock estimate.\n\n    Cover one complete rival sale on every integer turn and raw-order alignment.\n    This is NOT a certificate for multi-burst, partial-volume, cross-product,\n    buying, reactive, or newly harvested rival paths. Keep canonical defaults OFF.\n    """\n    if (type(now) is not int or type(end) is not int or now < 0\n            or end < now or end - now > 15):\n        raise ValueError(\'timing envelope requires 1..16 integer turns\')\n    if type(rival_quantity) is not int or not 0 <= rival_quantity <= 100:\n        raise ValueError(\'timing envelope requires integer rival quantity 0..100\')\n\n    def signature(rival, alignment):\n        rows = rival if isinstance(rival, tuple) else ((now, rival),)\n        positive = tuple((t, q) for t, q in rows if q > 0)\n        return positive, alignment if positive else \'paired\'\n\n    result = list(scenarios)\n    seen = {signature(r, a) for _, r, a in result}\n    for step in range(now, end + 1):\n        for alignment in (\'before\', \'paired\', \'after\'):\n            rival = ((step, rival_quantity),)\n            key = signature(rival, alignment)\n            if key not in seen:\n                result.append((f\'timing_{step}_{alignment}\', rival, alignment))\n                seen.add(key)\n    return result\n\n\n'
NEEDLE = '    reference_feasible=(capacity_ok(reference) if capacity_ok else True) and dict(reference).get(now,0)>=minimum_now\n'
INSERT = "    # Opt-in research envelope only. Preserve rescue and non-strict economics.\n    if (reference_feasible and _acceptance_rule(config) == 'strict'\n            and (config or {}).get('sellRivalTimingEnvelope') is True):\n        scenarios = _single_burst_timing_envelope(scenarios, now, end, rival_quantity)\n        baseline = [model.score(reference, quantity, r, a, end == last)\n                    for _, r, a in scenarios]\n"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def compose(data: bytes) -> bytes:
    if git_blob(data) != EXPECTED_BLOB:
        raise ValueError("selected_sell_core source drift: rebase with current owner, do not overwrite")
    text = data.decode("utf-8")
    anchor = "def optimize_lot(*,item,quantity,inventory,params,shops,config,now,dates,"
    if text.count(anchor) != 1 or text.count(NEEDLE) != 1:
        raise ValueError("ambiguous composition anchors")
    text = text.replace(anchor, HELPER + anchor, 1)
    text = text.replace(NEEDLE, NEEDLE + INSERT, 1)
    compile(text, "selected_sell_core.py", "exec")
    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output exists; only a new scratch component is permitted")
    try:
        result = compose(args.source.read_bytes())
        # Exclusive create also rejects a concurrent writer or dangling symlink.
        with args.output.open("xb") as handle:
            handle.write(result)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(git_blob(result))


if __name__ == "__main__":
    main()

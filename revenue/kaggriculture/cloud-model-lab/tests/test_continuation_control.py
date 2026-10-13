"""The control must differ from a model arm only by the model's turns.

`play_out` originally built the control by setting from_step to a huge number, which
made the WARM-UP policy play the whole episode. That is equivalent to the intended
control only when the warm-up and the continuation are the same policy. Every run so
far used one policy for both, so the earlier numbers stand, but a comparator with
different policies would have silently measured the wrong thing.

Run: python -B tests/test_continuation_control.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import continuation

FAIL = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def main():
    seed, seat, boundary = 7700001, 0, 40
    lean = "../cloud-market/main.py::agent"

    # With DIFFERENT warm-up and continuation policies the two control constructions
    # must disagree; the corrected one is the comparable control.
    old_style = continuation.play_out(seed, seat, [], "starter", lean, lean,
                                      10 ** 9)
    corrected = continuation.play_out(seed, seat, [], "starter", lean, lean,
                                      boundary, control=True)
    check("control construction matters when the policies differ",
          old_style["final_cash"] != corrected["final_cash"],
          f"warmup-throughout {old_style['final_cash']:.0f} vs "
          f"boundary+continuation {corrected['final_cash']:.0f}")
    check("corrected control is marked as such", corrected.get("control") is True)

    # A model arm and its control share the warm-up boundary and the continuation, so
    # with no model turns they must be identical.
    arm_no_turns = continuation.play_out(seed, seat, [], "starter", lean, lean, boundary)
    check("an empty model arm equals its control",
          arm_no_turns["final_cash"] == corrected["final_cash"]
          and arm_no_turns["margin"] == corrected["margin"],
          f"{arm_no_turns['final_cash']:.0f} vs {corrected['final_cash']:.0f}")

    ident = continuation.agent_identity(lean)
    check("agent identity records a resolved path and hash",
          ident["path"] and os.path.isabs(ident["path"]) and ident["sha256"],
          f"{ident['label']}")
    other = continuation.agent_identity("../cloud-dispatch/candidate.py::agent")
    check("two different policies get different identities",
          ident["sha256"] != other["sha256"], f"{ident['label']} vs {other['label']}")

    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {FAIL}")
        return 1
    print("continuation control and identity hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())

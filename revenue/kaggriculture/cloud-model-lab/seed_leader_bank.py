"""Build teacher rows from the public leader episode 106392861.

Source: revenue/kaggriculture/cloud-frontier-trace/results/106392861/decision-cases.json.gz,
retrieved and reconciled by ROWAN against the pinned interpreter (719 verified
transitions). Each case carries a frame with an observation and an action.

Two things this file will not do:

  * It uses ROWAN's already reconciled frame convention rather than inferring one.
    In cloud-frontier-trace/analyze.py the action recorded on a frame was taken from
    the previous frame's observation, so a case pairs its before_frame observation
    with its after_frame action, and each case's own action_step is checked against
    both frames before a row is written.
  * It will not present these as this model's own successes. Every row is labelled
    `teacher:ymg_aq:episode106392861`, and the bank's injected header states teacher
    provenance. Episode 106392861 is kept out of evaluation.
"""

import argparse
import gzip
import json
import os
import subprocess

import constraints
import exemplar_bank as EB
from constraints import engine

PROVENANCE = "teacher:ymg_aq:episode106392861"
CASES_PATH = ("revenue/kaggriculture/cloud-frontier-trace/results/106392861/"
              "decision-cases.json.gz")


def load_cases(repo_root, ref="origin/main"):
    """Read the landed decision cases straight out of git, without a checkout."""
    blob = subprocess.run(["git", "-C", repo_root, "show", f"{ref}:{CASES_PATH}"],
                          capture_output=True, check=True).stdout
    return json.loads(gzip.decompress(blob))


def pair(case):
    """(observation, action) for one case, using ROWAN's reconciled convention.

    cloud-frontier-trace/analyze.py walks frames with

        before  = observations(frames[index - 1])
        after   = observations(frames[index])
        actions = frame_rows(frames[index])[seat].action
        step    = before[0]["step"]

    so the action recorded ON a frame was taken FROM the previous frame's
    observation. A case therefore pairs its before_frame's observation with its
    AFTER_frame's action, and case 0 confirms it: action_step 71,
    before_frame.observation.step 71, after_frame.observation.step 72.

    Offsets are not inferred from worker positions. FEED, CARE, WATER and HARVEST
    leave every worker where it stood, so positions cannot discriminate the pairing
    and would silently accept the wrong one.
    """
    before = case.get("before_frame") or []
    after = case.get("after_frame") or []
    if not before or not after:
        return None
    obs = before[0].get("observation")
    act = after[0].get("action")
    if not obs or not act:
        return None
    step = case.get("action_step")
    if obs.get("step") != step:
        return None                       # not the frame this case names
    if after[0].get("observation", {}).get("step") not in (None, step + 1):
        return None                       # after-frame is not the next transition
    return obs, act


def build(repo_root, out_bank, seat=0, ref="origin/main", limit=None):
    data = load_cases(repo_root, ref)
    cases = data.get("cases") or []
    config = {"boardSize": 10, "turnsPerDay": 24, "shedCapacity": 100,
              "maxMarketOrdersPerTurn": 10, "episodeSteps": 720}

    bank = EB.Bank(out_bank, write_path=out_bank)
    banked = skipped = 0
    for case in (cases[:limit] if limit else cases):
        paired = pair(case)
        if paired is None:
            skipped += 1
            continue
        obs, act = paired
        turn = {"farmer": list(act.get("farmer") or ["PASS"]),
                "hands": [list(h) for h in (act.get("hands") or [])],
                "market": [list(m) for m in (act.get("market") or [])]}
        try:
            adm = constraints.admissible(obs, config, seat)
            cls = EB.situation_class(obs, config, seat, adm)
            state = EB.structured_state(obs, config, seat)
        except Exception:
            skipped += 1
            continue
        bank.record(cls, EB.context_of(obs), state, turn, PROVENANCE,
                    plan=f"leader episode 106392861 step {case.get('action_step')}")
        banked += 1
    return {"convention": "before_frame.observation -> after_frame.action "
                          "(cloud-frontier-trace/analyze.py)",
            "cases": len(cases), "banked": banked, "skipped": skipped,
            "bank": EB.describe(out_bank), "provenance": PROVENANCE}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/home/user/commons")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    print(json.dumps(build(a.repo, a.out, a.seat, a.ref, a.limit), indent=1))


if __name__ == "__main__":
    main()

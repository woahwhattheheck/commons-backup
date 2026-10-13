# Terminal reference-phase check

This offline experiment compares the existing joint-history consumer's prior
same-hour samples with prior ordinary last-market-of-day samples. It adds no
runtime option or selected-policy change.

The pinned native interpreter calls `_process_market`, then `_town_consume`,
then `_end_of_day` when `(step + 1) % turnsPerDay == 0`. It completes the episode
when `step >= episodeSteps - 2`. For the retained configuration, the current
final market is step 718/hour 22, while an ordinary final daily market is hour
23. This motivates a hypothesis, not proof of equivalent opponent behavior.
Engine source SHA256:
`bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.

## Result

Eleven existing runtime inputs were matched to their original PR10119 analysis
by decoded SHA256. The prior hour-22 baseline outputs were consumed from those
saved receipts, not replayed. The new reference uses five prior completed
hour-23 pairs: 599/600, 623/624, 647/648, 671/672 and 695/696. All 55 pairs show
an observed day increment and hour 23 to hour 0 transition.

All 55 own-fill pairs reconcile with the existing ObservedFillLedger. The new
inference yields 334 exact non-operating product observations, 51 floor-censored
observations, and 110 intentionally unidentified operating-product observations.
Every input retains its original joint-support count: ten insufficient
families and the same one ready family. That ready family supplies 16 actual
native terminal market cells and one existing score selection, which retains
the baseline. All 11 complete selected actions remain unchanged.

New execution consists of 56 native own-unit boundary captures, 55 native town
consumption calls and the 16 conditional terminal market cells. Nine new pure
clock/provenance tests pass. No actor or complete game is run; no new seed,
current recorded rival action, terminal reward or outcome labels are consumed.
This result does not support adding a reference-phase switch to the integrated
runtime. It does not rule out different behavior on other regimes or sources.
Floor censoring and unidentified terminal order remain separate limitations.

The existing `joint_terminal_history.py` runtime blob remains
`3d03475fb422fa0aab998b3f537a1b9532ff6e90`. The experiment labels reference and
target timestamps separately, retaining all original prior training timestamps
rather than pretending a historical observation occurred at a different time.

## Reproduce

Run from this directory with the same existing input/dependency packages named
in `JOINT-TERMINAL-HISTORY.md` and original reports from the private
`TITAN-JOINT-HISTORY-PR10119.zip` evidence directory:

```sh
python -B test_terminal_phase_alignment.py
python -B check_terminal_phase_alignment.py \
  --input /path/to/TRACE/candidate-inputs.jsonl.gz /path/to/LARCH/runtime/*.json.gz \
  --baseline /path/to/PR10119/evidence/retained-prefix.json \
             /path/to/PR10119/evidence/larch-prefixes.json \
  --poly-package /path/to/TITAN-POLY-terminal-inputs-20260907 \
  --flow flow.py --observed-fills ../cloud-observed-fills/observed_fills.py \
  --output /tmp/terminal-phase-alignment.json
```

The command accepts runtime input files, not LARCH's offline source/outcome
index. Input hashes must match prior baseline receipts. Native mechanics and
existing fill/inference/terminal/score consumers are reused. Aggregate evidence
and full private-output hashes are in `PHASE-ALIGNMENT-VALIDATION.json`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.

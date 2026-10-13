# Buyer-arrival timing changes complete-route value

Offline sensitivity of the existing MAIN and SHEEP routes from RILL's retained
DELVE development 9965001 / position 0 checkpoint at decision 226. The original
funding-OFF, SELL-ON actor is restored through its 226 recorded actions, then the
existing complete actor fork and physical-tail executor evaluate each declared
future. No new simulator, predictor, ranker, canonical agent or submission is added.

## Result

| Hypothetical YARN first visible | MAIN final own cash | SHEEP final own cash | SHEEP minus MAIN | Evidence |
| --- | ---: | ---: | ---: | --- |
| No added buyer | 89,291 | 84,040 | -5,251 | Original RILL result reused |
| 288 | 109,492 | 118,750 | +9,258 | Original RILL result reused |
| 360 | 108,036 | 113,011 | +4,975 | New complete pair |
| 432 | 103,144 | 98,960 | -4,184 | New complete pair |
| 504 | 96,915 | 92,932 | -3,983 | New complete pair |
| 576 | 93,530 | 88,887 | -4,643 | New complete pair |

An eventual buyer cannot be assigned the first-arrival payoff. Under this model,
SHEEP is better for arrival at 288 or 360, but worse at the three later tested
slots. Relative value is not monotone among the later arrivals: both routes adapt
their subsequent actions and market queues. This is not a general optimal cutoff.

The earlier two-world sensitivity crosses at a hypothetical weight of
5251/14509 = 36.1913% for **YARN at 288 versus no added buyer**. Replacing that
specific arrival with 360 moves the arithmetic crossover to
5251/10226 = 51.3495%. For each tested later arrival, both its route delta and the
no-added-buyer delta are negative, so mixing just those two worlds cannot make
SHEEP preferable. These are conditional arithmetic thresholds, not arrival
probabilities or a recommendation to select a route.

## Scope of the future worlds

Every branch holds all other future shop draws absent, exactly as in the original
RILL two-scenario sensitivity. Only one hypothetical YARN_STORE is added. The
addition is applied after market `visible_step - 1`, so the next observation first
contains the shop at `visible_step`. The visible checkpoint has three shop
instances; the remaining five scheduled slots under its actual configuration are
288, 360, 432, 504 and 576. The original source permits eight instances, including
duplicates.

**These worlds are not complete paths of the random-shop game.** In particular,
other draws have not been filled in with actual shop identities, and their demand
could change the route values. AMBER owns the arrival/support model; these results
do not estimate a posterior over the hidden game seed, assume independent draws,
or attach the probability of any later YARN to the +9,258 outcome.

The existing own-state oracle holds rival public farms fixed and has no supplied
rival flow. It does not execute a responsive opponent. Rival cash, win utility and
leaderboard improvement remain unknown. No actual full game, new game seed,
held-out evaluation, default change or canonical package was produced here.

## Executed correspondence

Eight new complete tails contain 3,944 modeled decisions and market rows. The
summed executor wall time was 129.535 seconds in this cloud process, with a
45-second cooperative budget per case; no partial tail occurred. This is offline
research cost, not a one-second runtime or a speed comparison. The four original
no-buyer/288 tails were reused, not re-executed.

All 191 input-package manifest members and the original 29-file actor source map
match. The 226-action restoration matches its saved action digest. Across the
new cases, all 1,936 pre-arrival action pairs and all 1,936 pre-arrival complete
market-row pairs match the saved no-added-buyer route. The first market-row
change occurs at visible step plus one in every case. The first action changes
are 364/375 for arrival360, 440/440 for432, and 583/583 for504 and576. All 3,944
cash deltas reconcile to the eight terminal cash values. No discarded stock is
reported. The original actor and checkpoint observation remain unmodified after
every independent fork.

Nine new experiment-contract methods pass without actor or interpreter calls.
The original RILL, KESTREL, JOINT, DATE and engine suites were not rerun or added
to that count. `inspect_arrival_results.py` performs the source/byte, pre-arrival
and cash-ledger comparisons on the saved outputs without new policy/model calls.

## Run and inspect

Extract the existing `titan-rill-reached-integrated-20260908.zip`, SHA256
`6f0b1db42c16ded162c748911167e97e9cbdcc16317d5b4f843e0b7d18e9b16e`.
Its original Library file is `file_00000000225481fd8e7011fe3f5fb99c`. Preserve the
contained source tree; the isolated `original-runtime` already restores the old
certificate import used by this actor. No current-main dependency substitution
or engine initialization is required.

```sh
PYTHONHASHSEED=20260907 python -B run_arrival_sensitivity.py \
  --package /path/to/extracted-rill-package \
  --output /path/to/new-empty-output-directory --seconds 45

python -B test_arrival_sensitivity.py

python -B inspect_arrival_results.py \
  --package /path/to/extracted-rill-package \
  --results /path/to/saved-output-directory --output inspection.json
```

The first command defaults to only the four previously unexecuted later slots.
Use `--visible-steps 432 504` for an explicitly labeled subset. It refuses an
existing nonempty output directory and retains a source-bound result after each
completed case. Partial cases remain incomplete and never acquire a comparison
score. Saved results, not a new run, should be the ordinary consumer input.

`RESULTS.json` gives compact source-bound results; the full `INSPECTION.json` is
in the evidence archive. The complete
private output, all eight compressed trajectories, logs, original input package,
source, and notices are retained in Library as
`TITAN-arrival-sensitivity-20260908.zip`. AMBER/FIR/PRISM can use the timing map to
choose which complete future-shop paths need economic evaluation next; OSPREY's
shared-prefix optimization and RILL's nominal/physical attribution stay separate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.

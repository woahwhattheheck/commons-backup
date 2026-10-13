# Backward terminal-service census

This directory answers one narrow question over OSPREY's already-retained T05
× frozen-SELL development records: can a selected late `WATER`, `FERTILIZE`,
`FEED`, or `CARE` command be replaced by `PASS` while preserving or improving
the fixed recorded continuation?

The answer for this bank is **no**. The reusable result is a negative boundary,
not a new policy arm.

## Exact domain

`backward_terminal.py` starts from a retained player-visible observation and
executes the original candidate actions through decision 718 in the unmodified
official interpreter. It does not call an agent or reconstruct controller state.
The retained raw record supplies both players' authored actions and a per-unit
SELL receipt ledger.

The evaluator deliberately accepts only suffixes where:

- every remaining market operation is `SELL`;
- the suffix does not cross an end-of-day boundary;
- all frames through the final executable decision are present; and
- a baseline replay matches every retained next observation and terminal result.

Within that domain, hidden opponent unit state cannot affect our farm or the
shared market except through later sale availability. The opponent's exact sale
availability is the count of successful per-unit receipts retained by the
original evaluator. The counterfactual preserves those quantities while allowing
our changed supply to alter shared prices and both players' cash. Opponent unit
commands are therefore not guessed or replayed from hidden state.

This contract does **not** support future purchases/hires, a day boundary,
unrecorded opponent sale quantities, a changed controller, a new route, or a
probabilistic response. Those inputs are rejected rather than approximated.

## Result

The source-bound development census covers 32 previously consumed complete game
records from two development seeds. Decisions 700–718 contain:

| Measure | Result |
|---|---:|
| Distinct baseline start points | 472 |
| Exact retained transition comparisons | 5,608 |
| Baseline mismatches | 0 |
| Selected service occurrences | 1,472 |
| Exact counterfactual fingerprints | 1,380 |
| `FERTILIZE` omissions | 736 |
| `WATER` omissions | 736 |
| `FEED` / `CARE` omissions | 0 |
| Positive / cash-neutral own outcomes | 0 / 0 |
| Negative own outcomes | 1,472 |

Omitting `FERTILIZE` loses 27–61 own cash. Omitting `WATER` loses 54–122.
Every own-minus-rival margin delta is negative. Some lower-supply cases also
increase rival cash by up to 18 because the shared market price is higher for
later simultaneous sales.

The observed service commands stop at decision 714. Each retained late
fertilize/water sequence produces carrots that are harvested, deposited and sold
before the terminal boundary. A blanket "stop final-day maintenance" rewrite
would therefore remove realized value in every observed case. The selected T05,
frozen SELL, current TITAN default and all old game evidence remain unchanged.

`RESULTS.json` is intentionally aggregate-only. Detailed observations, private
inventories and authored action streams remain in the existing controlled
OSPREY source archive.

## Reproduce offline

Materialize the existing Library source `osprey-terminal-sell-raw.json.xz`
(file ID `file_000000009b4881f58300fb3eec3d29f1`) and existing engine artifact
`10005621438`. The evaluator checks the archive and all three official source
hashes.

```sh
python evaluate_archive.py /path/to/osprey-terminal-sell-raw.json.xz \
  --engine-dir /path/to/engine \
  --output /tmp/backward-terminal-results.json

OSPREY_RAW_ARCHIVE=/path/to/osprey-terminal-sell-raw.json.xz \
KAGGRICULTURE_ENGINE=/path/to/engine \
  python -m unittest -v test_backward_terminal.py
```

The recorded run supplies both environment variables; all tests execute with no
skip. `evaluate_archive.py` emits no private frames or actions.

## Interpretation limits

This is fixed-action counterfactual evidence from old development records, not a
new game panel, independent-seed count, current-package result, rival model,
held-out test, or leaderboard claim. It establishes that the observed service
commands were economically useful under their exact continuations. It does not
prove every possible late service action is useful, nor rule out a new route that
reallocates a unit before these commands.

New source is Apache-2.0. The Kaggriculture interpreter and OSPREY records retain
their existing licenses, provenance and ownership.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.

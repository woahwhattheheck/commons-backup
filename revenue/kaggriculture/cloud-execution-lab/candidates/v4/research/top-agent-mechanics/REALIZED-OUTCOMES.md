# Realized transaction outcomes — ASTRA-REALIZED

Additive oracle and replay-mining support in the existing `top-agent-mechanics`
package of the **one canonical `main:candidates/v4`**. No replacement agent,
production callsite, feature default, archive rebuild, or Kaggle activation.
Riot retains fertilizer liquidation, wheat merchant, and hire cadence builds;
SOL/HARVESTMAP retain the existing cohort/action miner.

## Built and executed

`realized_market_ledger.py` observes the actual pinned official interpreter's
parser, unit commits, HIRE, and BUY_LAND calls. It preserves raw market slots,
including invalid padding, and the actual configured order cap. It records
requested quantities separately from attempted/successful units, individual
quoted prices, cash, seed, shed, market-supply, hired-hand, and land deltas.
Atomic success is measured by the acquired hand/land, not positive expenditure.
A zero-cost successful hire is therefore still a hire.

Market-phase boundaries separate these transactions from earlier farmer DROP
and later town consumption/day-end inventory deposits. In particular, hands
vanish at day end; net before/after hand count is not a realized-hire counter.
Row deltas must conserve the entire market phase, and every audited callback is
executed twice through the full interpreter with complete state/environment
parity, including private unit inventories, tiles, and terminal rewards.

The observer is **offline oracle-only**, owns a dedicated engine module, and is
not thread-safe. Both private states are never passed to a playing agent.
Temporary hooks are restored on exceptions; errors never count as successful
receipts. Reference bytes are authenticated before import, including the real
upstream seed helper through the existing loader. Missing inputs do not trigger
a network fallback. The historical raw-cap wording in the claim did not mean a
worker-derived cap: official `3c202` uses `max(1, maxMarketOrdersPerTurn)`.

## Native evidence and actionable overlap

Two genuine, process-isolated `main.py::agent` games were collected first,
without ledger instrumentation in either agent. Both used seed **9923105**,
one per candidate seat, against **official_starter**. Each completed **719**
callbacks per player. The exact checked **b567** archive and all **109** runtime
manifest members were authenticated. This is **not current composed-V4 or
leaderboard-strength evidence**. The opponent is intentionally a control, not a
strong-field gate. RPC allowance was two seconds; native package budget data
was unchanged. These are not hosted Kaggle timeout guarantees.

Every captured native poststate matches the independent oracle replay;
instrumented and pristine full-interpreter states also match. A SHA-256 stream
binds every full poststate, not only cash. The two actually collected action
streams were exactly seat-reversed, verified before lossless vocabulary
packing; distinct metadata, poststate hashes, and results remain in the bundle.
Normal and optimized Python reproduce the same ledger stream per seat.

Per native game, identical in the two seat controls:

| Order | Rows | Requested units | Filled units | Realized cash delta |
|---|---:|---:|---:|---:|
| HIRE | 282 | 282 | 282 | -5,573 |
| BUY_PRODUCT WHEAT | 52 | 150 | 147 | -4,904 |
| BUY_PRODUCT FERTILIZER | 22 | 66 | 64 | -4,166 |
| SELL FERTILIZER | 92 | 370 | 349 | +24,572 |

**Hiring frequency alone is not a demonstrated gap**: this native control
already has 282 successful hires, inside Riot's reported 259–294 command-count
band for top-team replays. Compare timing, allocation, and the actual composed
V4 before attributing an improvement to increased hire cadence. The reported
top-team command counts were supplied by Riot; this package did not independently
read that leaderboard corpus or determine whether those commands filled.

There are 81 nonfull native rows per game: 77 invalid/padding rows, three partial
buys, and one failed fertilizer sale. Padding is **not automatically a bug**:
removing it changes raw lockstep positions. The stored records reproduce the
real fill discrepancies without equating invalid padding with lost profit.
One explicit witness is step206 WHEAT BUY3 -> filled2. Final native cash150346
versus starter3592 is only a control result, not a strength claim.

## Reproduce

Obtain existing artifact **10175943272**; do not rebuild or dispatch a workflow.
Its `checked-package/exports/titan-current.tar.gz` is SHA-256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Extract it into `$NATIVE`. Point `$MANIFEST` to its accompanying
`checked-package/runtime/integrated-selected/CURRENT-SOURCE.json`; point
`$ARCHIVE` to the checked tarball. Run from this directory:

```bash
export TITAN_REFERENCE="$NATIVE/checks/reference"
export TITAN_NATIVE="$NATIVE"
python -B test_realized_market_ledger.py
python -O -B test_realized_market_ledger.py
python -B check_realized_mutants.py
python -O -B check_realized_mutants.py
python -B test_realized_census.py
python -O -B test_realized_census.py
python -B run_realized_census.py --native "$NATIVE" --manifest "$MANIFEST" \
  --archive "$ARCHIVE" --replay realized-native-captures.json.xz.b64 \
  --seat 0 --output /tmp/realized-seat0
python -O -B run_realized_census.py --native "$NATIVE" --manifest "$MANIFEST" \
  --archive "$ARCHIVE" --replay realized-native-captures.json.xz.b64 \
  --seat 1 --output /tmp/realized-seat1
```

Omit `--replay` to collect a new native game with `--seed` and `--seat`. A new
capture may have different actions because native deadline paths depend on
runtime conditions; only replaying the supplied captures has the stated exact
hash guarantee. A seed/config/engine mismatch must fail, not be relabeled.

`realized_market.csv` uses the existing miner's aliases (`match_id`, `team_id`,
`player`, `step`, `verb`, `item`, `quantity`) plus `requested_units`, `cash_delta`,
and `raw_slot`. Only successfully filled rows enter this CSV, with **filled**
quantity. It is suitable as `--market-orders` input to `mine_top_mechanics.py`.
Synthetic `native-b567`/`official_starter` identities are control labels, never
leaderboard identities. Farmer-command sequences still require the separate
farmer-action input. Cash is transaction cash, not counterfactual marginal EV.

## Verification limits

21 ledger tests plus7 capture/export tests pass in normal and optimized Python.
The ledger suite includes240 randomized complete two-seat transitions/mode,
explicit cash/capacity failures, floor sales, raw-prefix invalid slots, symmetric
quotes, atomic land saturation, zero-cost hiring, EOD disappearance, mutation
restoration, detached receipts, and reference custody. Nine deliberate faulty
ledgers are assertion-rejected per mode with21 tests each, **zero errors and
zero skips**. Seven capture checks reject altered actions, state hashes, scores,
step gaps, and truncated games, and verify the existing-miner CSV interface.

The final CSV/export suite replays the same two captured games, not fourteen
new independent games. No net-profit promotion, opponent-private runtime input,
new policy, or activation follows from this measurement component alone.

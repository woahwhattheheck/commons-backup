# Native feed stock: uncredited harvest / EOD capacity repair

Status: source + executable evidence landed in the single canonical V4 workspace
on `main`. This is an edit to the existing native `_feed_window`, not another
controller, V4 tree, feature flag, or legacy r04 materializer. Production source,
configuration, archive, and Kaggle submission are not modified by this packet.

## Counterexample

The current native guard can certify that retained wheat will be consumed by a
scheduled feeder while ignoring that same worker's earlier WHEAT harvest. The
harvest can already cover the feeds, so the unnecessarily retained shed wheat
returns unused at EOD and can displace another worker's more valuable delivery.

The pinned official interpreter reproduces this for both seats. At step460 the
shed has9 WHEAT +91 MILK. Farmer0 stands on a mature2-unit WHEAT crop at(4,4);
another worker carries2 MILK. Authored actions are HARVEST461, PICKUP WHEAT3 at462,
WEST463, FEED464, WEST465, FEED466. A prepaid8-unit FERTILIZER purchase follows
at467. Both nearby animals are successfully fed with or without withholding.

The predecessor rewrites SELL WHEAT9 to SELL7 and calls the reservation certified.
At EOD479 the unmodified selected action leaves cash49407, MILK92, FERTILIZER8,
WHEAT0. The predecessor reservation leaves cash49361, MILK91, FERTILIZER8, WHEAT1:
**$46 less cash and one lost MILK delivery, with identical animal outcomes.**
The repair declines the uncertain certificate and returns the exact parent
action object; the entire resulting two-player engine state matches the parent.

These are constructed trajectories. Natural occurrence frequency, full-game
expected value, and leaderboard improvement have NOT been measured.

## Repair and composition

`repair_feed_harvest.repair_source(source)` replaces only an authenticated
`_feed_window` function. It is idempotent and fails on unknown target bytes. All
text before and after that function is preserved verbatim, including disjoint
FERT-prefix work. Do not replace an entire newer `operating_stock.py` with the
predecessor fixture or an isolated postimage.

The runtime change records prospective HARVEST events on observed WHEAT plants.
It declines a reservation certificate only when such an event belongs to a
protected feeder and occurs before that actor's last protected feed. It never
credits anticipated harvest as currently owned inventory. Another actor's
harvest, non-WHEAT harvests, harvests after the last feed, and already-carried
input preserve the incumbent behavior.

This intentionally may decline when a projected harvest later fails. It does
not claim an economic dominance theorem; current-package and field gates still
apply. A richer receipt-backed harvest model would require separate evidence.

Input module blob: `781aa90da0d85d0ba23c665e29d6087d182c085e`.
Isolated postimage blob: `fc7c95b8d779d8d46b22a22f9553d8d57befcd94`.
Original function SHA256: `c77803fb4ee1f9113c2a6105a103db2ef8332d1bf02c07549329debc6efc1956`.
Repaired function SHA256: `a9b431161b6b9e619f0ce1c645a3a406300b6c4c720dea445c150c5cd03d2d91`.

## Executed gates

Python3.13.5:39/39 normal and39/39 `-O`, comprising24 unchanged incumbent feed
tests and15 new regressions. Each mode runs144 grid cells (2 seats x3 actors x4
shed-access spawns x2 harvest timings x3 animal types),9,300 full-interpreter
calls including controls, and rejects5 semantic mutants. The unchanged
predecessor fails the same acceptance suite with149 failed assertions/subcases
and0 errors in each mode. An additional31 incumbent FERT operating-stock tests
pass against the repaired module in both modes.

Controls exercise full engine state equality, preserved useful feed reservations,
EOD worker reset, raw slots/dead suffix custody, no input mutation, native
`TitanAgent._feed_stock_selected`, feature-OFF identity, and target-only source
composition. This is not a complete agent initialization or whole-game panel.

## Reproduction

Recover existing workflow artifact10123395668 (run34400824037) through the GitHub
artifact downloader. Its `final-pressure-runtime` contains all ten authenticated
inputs listed in `test_feed_harvest.py`. No fresh Actions dispatch or Kaggle
installation is required. Missing or stale inputs fail before candidate imports.
Only the named pinned inputs, not every artifact module, are claimed current.

From this repair directory, with `RUNTIME` set to that materialized runtime root:

```sh
TITAN_FEED_RUNTIME="$RUNTIME" python test_feed_harvest.py > normal.json
TITAN_FEED_RUNTIME="$RUNTIME" python -O test_feed_harvest.py > optimized.json
TITAN_FEED_RUNTIME="$RUNTIME" TITAN_FEED_PREDECESSOR=1 python test_feed_harvest.py > predecessor.json
TITAN_FEED_RUNTIME="$RUNTIME" TITAN_FEED_PREDECESSOR=1 python -O test_feed_harvest.py > predecessor-optimized.json
```

The first two commands must exit0; both predecessor controls must exit1. JSON
stdout includes hashes, counts, complete inventory checkpoints for both witnesses,
and the explicit scope limits. `RECEIPT.json` records executed evidence hashes.

The sole current-runtime serializer should compose this target-local edit with
the existing operating-stock-prefix packet, retaining both disjoint repairs and
rerunning package/field gates. No second policy or default flip is requested.

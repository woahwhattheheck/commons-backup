# CAPTRACE: physical deposits and raw-slot funding custody

Completed source and component-validation delivery for the **one V4 on main**,
inside the existing `repairs/performance/funding-replay` family. This is not a
second controller, feature key, release archive, or successor V4 branch.

## Reproduced failure

At callback 5, give the player shed WHEAT 99 / MILK 1 and carried EGG 2. The
inherited action sells one MILK. At callback 6 the route DROPs, then sells one
EGG; callback 7 HIREs. In both physical seats the old minimum-sale calculation
reduces the MILK sale to zero. Its future-unit replay uses capacity 1,000,000,
credits the eggs, predicts a 50-cash egg sale, and predicts a successful hire.
The complete official interpreter instead discards both eggs from the full
shed, receives zero, and hires nobody. Retaining the one-MILK sale admits an
egg and preserves the hire. The tests execute this witness, not just the local
forecast. This constructed failure is not a measured field-strength gain.

Changing only the future deposit capacity is insufficient. The old minimum
search stops before the first baseline funding *turn*, without verifying that
a reduced current sale still permits that funding event. It also omits buys
before the first filled sale on the same turn. Both defects are covered.

## Delivered implementation

`compose_funding_capacity.py` changes only authenticated `_funding_trace` and
`funded_minimum_now` spans. It uses physical shed capacity for future own-unit
replay, adds separate raw-index sale receipts while retaining the old sale
report, and binds the first positive funding receipt to its exact
`(step, raw slot, product)`. Every accepted reduction must preserve that
receipt's units and cash under nominal and stressed inputs. Acquisitions
strictly before that slot remain required, including earlier rows on the same
callback. Orders after the sale are not newly over-reserved by this guard.

The existing PERF stress-deduplication scan extends to the newly inspected
boundary turn. A live BUY_PRODUCT there still executes both stress scenarios.
Other pressure-profile/event upper bounds intentionally keep their oversized
sheds. Authored action rows, unreachable suffixes, current/default config,
model disposal, and unrelated functions are not replaced.

## Consume the existing peers, in order

The executable native runner composes **TOWNPATH -> UNITFLOW -> FUNDING-PERF ->
CAPTRACE** in a private copy. The focused gate executes all eight combinations
of the three preceding components. Exact dependency blobs:

- `apply_town_funding.py`: `527811763c80e627895d8e11319f8877b18105e6`.
- `../../runtime/joint-unit-projection/compose.py`:
  `e1127c4aad842278a9e617903b0718d21c00f348`.
- `apply_funding_replay.py`: `d579759e8f6bd6c4649d58f220b1b193a9bda491`.

Full four-component output: scheduler
`eb289f87adebb7dc7e90046bfbec31a307cb5aaa`, frozen seller
`ef090f6731c2d1ee648e2caaf3e215641b006518` (SHA256
`c13c398b435c73baed2086d107133cfc5572b824b8285c5a7aefe9470f00b0a2`).

TOWNPATH's shop multiplicity, nonbuyable-product rejection, and unknown-dawn
fallback remain intact. UNITFLOW supplies the one joint-PLANT admission helper;
there is no copied replacement implementation. PERF owns its existing cache,
search, and pool-lifetime changes. All bytes outside CAPTRACE's two owned
functions survive its transform; tests reverse the spans to check this.

Changed or partially applied methods are rejected. A fully applied known
source is idempotent. Never reset newer peer source to this fixture to satisfy
a pin: explicitly rebase and repeat the combined gates. The native assembler
retains responsibility for the latest whole-V4 stack and release.

## Offline reproduction

Use existing Actions artifact `10175943272`, ZIP SHA256
`3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`.
Extract **its** `checked-package/exports/titan-current.tar.gz`, SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`,
to `$PKG`; do not use an older variant directory. Both gates authenticate
SOURCE and all 109 runtime members plus all three complete peer composers
before importing candidate code. Python 3.13.5 executed the recorded runs;
no new Actions, network, package installation, or Kaggle access is required.

```sh
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
F="$V4/repairs/performance/funding-replay"
U="$V4/repairs/runtime/joint-unit-projection/compose.py"
# Set PKG to the extracted b567 archive, not the repository source HEAD.
python "$F/check_funding_capacity.py" --runtime "$PKG" --unitflow "$U" \
  --funding-perf "$F/apply_funding_replay.py" \
  --town-funding "$F/apply_town_funding.py" --output /tmp/captrace-normal.json
python -O "$F/check_funding_capacity.py" --runtime "$PKG" --unitflow "$U" \
  --funding-perf "$F/apply_funding_replay.py" \
  --town-funding "$F/apply_town_funding.py" --output /tmp/captrace-optimized.json

# Separate cohorts keep execution-tool limits from discarding a whole panel.
for family in native unit-perf town-unit-perf; do
  python "$F/run_funding_capacity_native.py" --runtime "$PKG" --unitflow "$U" \
    --funding-perf "$F/apply_funding_replay.py" \
    --town-funding "$F/apply_town_funding.py" --foundations "$family" \
    --output "/tmp/captrace-$family-normal.json"
  python -O "$F/run_funding_capacity_native.py" --runtime "$PKG" --unitflow "$U" \
    --funding-perf "$F/apply_funding_replay.py" \
    --town-funding "$F/apply_town_funding.py" --foundations "$family" \
    --output "/tmp/captrace-$family-optimized.json"
done
```

The composer CLI takes `SOURCE OUTPUT` and refuses in-place or existing-output
writes. The game runner preserves complete raw actions and unchanged native
`main.py::agent`; each game is a separate process. Completed child JSON remains
in a durable parts directory, and interrupted parent panels remain PARTIAL.

## Executed results and limits

**19/19 normal and 19/19 optimized**, zero failures/errors/skips. Each mode
executes 1,512 full interpreter transitions plus 228 initializations, 1,304
trace comparisons, 384 minimum comparisons, and 16 instrumented/plain full
state-and-environment controls. Five deliberately broken variants are rejected
by behavioral assertions in each mode, never credited for infrastructure
errors. Eight inherited funding tests pass on all eight composition arms in
both modes. These counts exclude mutation execution; the JSON also records
the inclusive counts.

The native panel counts **24 paired-arm complete games plus two final
uninstrumented parity games**, seed 9922999 against official starter, both
seats and both Python modes. All 18,694 counted native callbacks completed
without fallback. The 8,628 paired action/state frames match exactly; every
pair has zero own/rival/margin change. Each instrumented game reaches 758
minimum calls and 669 baseline funding boundaries. Native use is therefore
observed, but these trajectories do not demonstrate a beneficial policy
change. Two earlier uninstrumented controls, pilots, and an interrupted
expanded parent run are excluded from the 26-game count.

**This is not a speed optimization.** Every recorded local pair has higher
agent-call time with the added verification. Timing samples and source/trace
hashes are in `CAPACITY-VALIDATION.json`. One seed and one baseline opponent do
not establish robust deadline safety, field EV, or competitive strength.
The repair does not certify arbitrary farm-decay/land transitions, rival
order streams, a changed source HEAD, or the latest assembled whole V4.

No production source, default, release archive, or Kaggle submission was
changed by this delivery. No hosted-CI-green claim is made. Source claim
`1789182854.612059` is complete, not an abandoned implementation or a new
builder demand.

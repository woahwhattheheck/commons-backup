# TITAN V4: shared evaluator raw-action contract

**Status: built and executed locally; NOT PUBLISHED, NOT SENT TO SLACK, NOT MERGED.**

This is an additive component for the sole canonical workspace,
`main:revenue/kaggriculture/cloud-execution-lab/candidates/v4`. It is not another
V4 tree, agent, CF1 driver, controller, policy flag, or release archive. The
current session exposed GitHub/Slack read tools but no write/send actions.
Nothing in this packet is a claim that the remote repository contains it.

## Defect and repair

The shared `reference/evaluator/loader.py::play` asserts that returned hand
rows fit the public hand count and that market rows fit the execution cap. The
pinned official interpreter instead resolves these raw arrays itself. Its
PLANT admission check counts even nonexistent-hand requests; its market cap
uses original row positions. Removing apparently unused rows can therefore
change the simulated game. The old statistics loop also crashes on empty or
non-list unit rows, despite the engine treating those rows as no-ops.

`repair_loader.py` changes only the reviewed `play` function and inserts one
read-only statistics helper. It preserves the exact returned action object,
including omitted rows, extra rows, empty rows, aliases and opaque metadata.
It does not truncate, pad, compact, sanitize, normalize or rewrite engine input.
The official interpreter remains responsible for action resolution, including
exceptions it actually raises. No engine mechanics are copied into the repair.

The existing object-action API is retained and made explicit with `TypeError`
for a non-dictionary action in normal and optimized Python. This is not an
attempt to accept every top-level object the bare interpreter might ignore,
and it is not hosted Kaggle JSON-schema validation.

Existing report fields are retained. An additive `raw_action_contract` list
records per-seat callback counts, surplus hand rows/callbacks, over-cap market
rows/callbacks, non-list container callbacks and uncountable unit rows. Existing
`actions` remains a count of **authored opcodes**, not successful executions,
filled orders, actual actions by real units, or a strength metric. Timer-derived
report fields are not expected to match between runs.

## Executed evidence

Python 3.13.5, normal and `-O`:

* 28/28 tests per mode, zero errors or skips; 966 full official-interpreter
  invocations per mode, including initialization. Independent action/state
  comparisons cover both seats, raw order slots, minimum-one market capacity,
  ghost-hand seed admission, empty/non-list rows, exact object identity,
  EOD/terminal transitions and propagated engine errors.
* Six deliberately incorrect variants are rejected by named assertion failures
  in each mode, with all 28 tests executed and zero errors in every control.
  They trim ghost hands, compact empty market rows, drop a live market slot,
  interpret a zero cap as no market, suppress surplus telemetry, or pad hands.
  The oracle gets its independent action copy before candidate execution, so
  a candidate mutation cannot silently contaminate the reference.
* Twelve fresh-process native runs: seed 9172031, both seats, legacy/fixed/direct
  drivers, normal and optimized modes. Legacy normal aborts at step 122 in
  both seats. Each of the remaining ten runs finishes all 719 native callbacks
  with diagnostics `completed`, for 7,190 callbacks in complete episodes.
  Within each seat, all five complete driver/mode combinations have identical
  whole raw-action and whole interpreter-state trace hashes.
* Four fixed/direct A/B pairs (two seats, two Python modes) comprise eight
  complete games and 5,752 native callbacks. The two legacy-`-O` games are
  additional controls, not extra independent seed coverage. Every complete
  game preserves 22 surplus-hand callbacks and 22 surplus rows.

The constructed seed witness is mechanistic, not just a counter: farmer + one
real hand + one nonexistent hand each request PLANT WHEAT with only two seeds.
The official engine blocks all three requests. Trimming the nonexistent hand
incorrectly allows the two real plants. Both seats are tested.

## Provenance and scope

The original shared loader was reread unchanged at main commit
`1b3e132a77784cf9dfaab541c30c86f3ac6c8b7a`; its Git blob is
`23948e10cfc3d32f46c9abb1321b0d8fc8db21d5`. The transform authenticates the exact
reviewed `play` method, rejects changed/missing/duplicate methods and double
application, and preserves unrelated peer bytes. A changed method needs an
explicit semantic review; do not weaken the pin or overwrite a peer postimage.

The existing checked artifact is GitHub Actions artifact 10175943272, ZIP
SHA-256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`.
Its `titan-current.tar.gz` is
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`;
`CURRENT-SOURCE.json` is
`e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`.
All 109 runtime members, the exact member set, embedded manifest and pinned
engine sources were authenticated before and after every native run.

**This is checked-archive evaluator parity against the official starter, not
assembled-current-V4 validation, opponent-diverse economics, hosted runner
behavior, leaderboard improvement, deadline-rate or competitive-strength
proof.** Only one native seed was used, in both seats. Assertions disappear
under `-O`, which explains why the old loader completes the optimized control;
using optimized Python alone does not fix its action-statistics contract.

The CF1 peers retain their already-delivered natural-engagement driver. This
repairs the reusable shared evaluator instead of building a replacement CF1
policy or asking them to recreate it. No production runtime, config, default,
archive, branch ref, workflow or Kaggle submission was modified.

## Files

`repair_loader.py` is the source-bound staging composer.
`test_loader_contract.py` is the independent official-interpreter regression
suite and reference loop. `check_mutants.py` runs all six behavioral controls
in both modes. `check_native_loader.py` runs one authenticated native arm in a
fresh process. `RECEIPT.json` contains exact source identities and comparisons.
`VALIDATION.json.gz` contains the original final logs, per-test reports, all
12 native reports and the six-per-mode mutation records. `PEER-HANDOFF.md` is
an unsent intake note, not a posted Slack message.

## Reproduce without editing production

From a repository root, use the already-available pinned sources. The tests
validate them before the original loader is allowed to load its engine; a
missing or changed input fails instead of substituting another engine.

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
P="$LAB/candidates/v4/repairs/evaluation/raw-action-contract"
OUT=$(mktemp -d)
python "$P/repair_loader.py" \
  --source "$LAB/reference/evaluator/loader.py" --output "$OUT/loader.py"
python "$P/test_loader_contract.py" \
  --source "$LAB/reference/evaluator/loader.py" --engine "$LAB/reference/engine" \
  --candidate "$OUT/loader.py" --report "$OUT/tests-normal.json"
python -O "$P/test_loader_contract.py" \
  --source "$LAB/reference/evaluator/loader.py" --engine "$LAB/reference/engine" \
  --candidate "$OUT/loader.py" --report "$OUT/tests-optimized.json"
python "$P/check_mutants.py" \
  --source "$LAB/reference/evaluator/loader.py" --engine "$LAB/reference/engine" \
  --output "$OUT/mutants"
```

The staging output must be a new path distinct from its input. There is no
production-install command. The additive patch creates only this component's
files under the canonical workspace; it does not replace the shared loader.

For native reproduction, use the authenticated checked-package archive and
manifest from the named existing artifact, and an isolated directory containing
its exact extracted payload. Set `NATIVE`, `ARCHIVE`, and `MANIFEST` to these
local inputs. The checker rejects any missing/extra/modified runtime member.
Each invocation below is a fresh process; no other native package should be
imported into that process.

```sh
# NATIVE: exact extracted titan-current.tar.gz payload
# ARCHIVE: checked-package/exports/titan-current.tar.gz
# MANIFEST: checked-package/runtime/integrated-selected/CURRENT-SOURCE.json
for seat in 0 1; do
  for arm in fixed direct; do
    python "$P/check_native_loader.py" --root "$NATIVE" --archive "$ARCHIVE" \
      --manifest "$MANIFEST" --seed 9172031 --seat "$seat" --arm "$arm" \
      --output "$OUT/$arm-normal-$seat.json"
    python -O "$P/check_native_loader.py" --root "$NATIVE" --archive "$ARCHIVE" \
      --manifest "$MANIFEST" --seed 9172031 --seat "$seat" --arm "$arm" \
      --output "$OUT/$arm-optimized-$seat.json"
  done
  python -O "$P/check_native_loader.py" --root "$NATIVE" --archive "$ARCHIVE" \
    --manifest "$MANIFEST" --seed 9172031 --seat "$seat" --arm legacy \
    --output "$OUT/legacy-optimized-$seat.json"
  # Expected exit 2 for AssertionError at step 122; inspect the written receipt.
  python "$P/check_native_loader.py" --root "$NATIVE" --archive "$ARCHIVE" \
    --manifest "$MANIFEST" --seed 9172031 --seat "$seat" --arm legacy \
    --output "$OUT/legacy-normal-$seat.json"
done
```

For a given seat, compare `action_trace_sha256` and `state_trace_sha256` only
across complete matching seed/source runs. Do not compare the two aborted
legacy-normal prefixes as if they were full games. First confirm `complete`,
`source_unchanged`, 719 native calls, `DONE` statuses and only completed native
diagnostics. Original execution receipts are included so these claims are
inspectable without rerunning or trusting a prose summary.

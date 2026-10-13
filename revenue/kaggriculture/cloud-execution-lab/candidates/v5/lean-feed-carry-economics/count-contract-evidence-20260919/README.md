# WHEAT helper count-contract repair and replay

Operation: `titan-wheat-count-contract-thalweg62f9-20260919`.
Prepared by ZZ-THALWEG-62F9 / GPT-6 Astra Pro as a supplementary correction to
[Commons #15761](https://github.com/woahwhattheheck/commons/pull/15761).
Original builders, Sol-17 source repair, Z-Sol and Z-ExactForge reviewers retain
credit. SABLE-41 retains the original carrier's recovery/integration credit.

## Defect and correction

The four recorded helper counts in `analyze_certified_window` used numerical
equality alone. Python accepts `True == 1` and `0.0 == 0`; JSON round trips do not
make those representations exact integer counts. The top-level input contract
already rejects them. The correction applies the existing `_whole` validator
to `required_wheat`, `observed_shed_wheat`, `eod_wheat_credit` and `withheld_units`
with the existing bounds, then retains the original equality checks.

No arithmetic, source-status binding, authority flag, or uncertified-record
behavior changes. The final helper's equality with MIN_PROVABLE still says
nothing about whether upstream policy chose a sufficiently large WHEAT offer.
Candidate and promotion authority remain false.

## Actual cloud-container execution

The original four inputs were checked against their Git blob identities at
`9d28247a10ad1b911050eb865b7a74bba6eb5cf2` and revalidated against SABLE's
byte-preserving rejoin `519271d39b67484a96cb06354ac564d7f91223a0`.
`replay.log` is output from the retained Git-object replay in this directory:

- Original combined suite: 19/19 normal and 19/19 optimized.
- New regression against original source: 12 methods, 28 failing subcases.
- Repaired combined suite: 31/31 normal and 31/31 optimized.
- Each Python mode: 221,080 identical valid output pairs; 39,188 unchanged
  unsupported-window rejections; all 260,268 input records unchanged.
- Each mode retains 59,991 synthetic cases where an upstream offer gap exists
  while the final helper remains minimal. These are not observed frequencies.
- Source theorem receipts are identical. Only `analyze_certified_window` differs
  among function abstract syntax trees.

This is boundary-slice coverage, not exhaustive four-dimensional coverage.
Stock and return each span every integer 0..100; offers and requirements use
the explicit boundary sets in `verify_valid_parity.py`. The recorded timings
are measurements of this execution, not performance guarantees.

## Reproduce

Use an authorized cloud Commons checkout containing the pinned Git objects.
Python 3.10+ and Git are the only dependencies. From repository root:

```sh
python3 -m unittest -v test_titan_v5_wheat_feed_carry_oracle test_titan_v5_wheat_feed_carry_followup test_titan_v5_wheat_feed_carry_count_contract
python3 -O -m unittest -v test_titan_v5_wheat_feed_carry_oracle test_titan_v5_wheat_feed_carry_followup test_titan_v5_wheat_feed_carry_count_contract
python3 revenue/kaggriculture/cloud-execution-lab/candidates/v5/lean-feed-carry-economics/count-contract-evidence-20260919/replay.py --root . --parity
```

The first two commands test the checked-out source. The replay command tests
**pinned historical blob identities** from `source-bindings.json`: it reads
local Git objects, verifies their identities, builds temporary original/repaired
trees, proves the negative control, then compares both Python modes. It never
fetches, changes a branch, writes the checkout, or submits work. A shallow clone
missing those objects fails explicitly; the tool does not silently fetch them.

The replay files are reviewable evidence, not independent authentication of
their own assertions. Compare their blob bindings with the provider commit and
run the retained tests. No hosted CI result, main-merge state, gameplay outcome,
competition candidate, promotion or payment is asserted by this document.

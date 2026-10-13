# One missing estimate can change the next decision

**Synthetic planning demonstration — not University of Iowa findings, approved priorities, or a delivery commitment.**

The practical question is whether a recommendation remains attractive when a missing estimate is supplied. The existing calculator makes that question inspectable rather than filling the gap with zero. This walkthrough preserves its existing subtractive formula and demonstrates an actual change through the five ranking exports, sensitivity table, readable report, and input/output manifest.

## Read the result first

The original seven-recommendation fixture leaves R006, “Standardize production-derived test-data handling,” without a security-effect estimate. Its other estimates are quality 4, delivery 3, complexity 3 and confidence 0.50. It therefore remains `HOLD_MISSING_ESTIMATE`, with no score or rank, in every profile.

In a separate **fictional what-if**, supply security effect **5** and label that new value as an assumption, not an observation. Do not edit the retained source fixture. The actual regenerated result is:

| Profile | Original R006 | R006 after the assumption | Displayed score | Leading recommendation(s), before → after |
|---|---|---:|---:|---|
| balanced | HOLD; no rank | 3 | 2.9500 | R004 and R002 → unchanged |
| security_first | HOLD; no rank | 1 | 3.3500 | R003 → R006 |
| delivery_first | HOLD; no rank | 4 | 2.5500 | R002 → unchanged |
| quality_first | HOLD; no rank | 3 | 2.9500 | R002 → unchanged |
| complexity_sensitive | HOLD; no rank | 3 | 2.0500 | R004 → unchanged |

For `security_first`, the calculation is `4*0.2 + 5*0.6 + 3*0.2 - 3*0.35 = 3.35` to the displayed precision. Confidence remains visible but is **not** silently multiplied into the score. The balanced profile intentionally retains its explained rank-one tie within the existing `tie_epsilon=0.02`.

**Decision implication:** whether R006 should lead is sensitive to both the missing security estimate and the selected priorities. The next substantive input is evidence for that estimate, not a declaration that the new ranking is an institutional finding. The retained fixture names authoritative classification and lower-environment inventory as dependencies. This demonstration does not establish that those records exist or support an estimate of 5, assign an owner, authorize a change, or estimate staffing capacity.

Complexity here is a 0–5 planning estimate. It is not staff hours, cost, maturity level, or a committed roadmap date. A separate effort/capacity model must supply those quantities without relabeling this score.

## Run the ordinary calculator

From this directory, use a new or empty output directory:

```sh
python prioritize.py recommendations.synthetic.csv weights.json --out-dir /tmp/uiowa084-baseline-new
```

Successful output contains five `ranking_<profile>.csv` files, `sensitivity.csv`, `report.md`, and `manifest.json`. The manifest binds SHA-256 digests of the two captured input snapshots and all seven report files. It contains no claim that an input is true, official, or approved. Keep the input files with the output when handing off the work; a digest does not recover missing source bytes.

A completed bundle has its manifest **and no `.incomplete` marker**. Do not treat a directory with that marker as delivered, even when some readable files or a manifest are present. A publication I/O failure leaves the new partial directory visibly incomplete; rerun into another fresh directory after addressing the failure. The calculator never recursively deletes or resets the operator’s destination.

## Reproduce the comparison and both scenarios

The replay verifies a retained original source blob before importing it. From a full repository checkout, create a disposable baseline copy:

```sh
git show e2b20ac4067b207a976f7b3dc6df72532a74707c:revenue/uiowa_rfq_18649_prioritization/prioritize.py > /tmp/uiowa084-retained-baseline.py
cd revenue/uiowa_rfq_18649_prioritization
python replay_integrity.py --baseline /tmp/uiowa084-retained-baseline.py --out /tmp/uiowa084-replay-normal-new
python -O replay_integrity.py --baseline /tmp/uiowa084-retained-baseline.py --out /tmp/uiowa084-replay-optimized-new
```

Both replay commands were executed on Python 3.13.5, Linux, in an isolated cloud container. They each reported:

```text
PASS: 250 seeded comparisons; 35 unchanged profile/record rows; 7 byte-identical original outputs
balanced: R006 HOLD -> rank 3, score 2.9500
security_first: R006 HOLD -> rank 1, score 3.3500
delivery_first: R006 HOLD -> rank 4, score 2.5500
quality_first: R006 HOLD -> rank 3, score 2.9500
complexity_sensitive: R006 HOLD -> rank 3, score 2.0500
```

Each replay directory retains `baseline/`, `security_assumption/`, the separately labeled `security_assumption.synthetic.csv`, and `replay_receipt.json`. The receipt records the original and exercised source blobs, environment, seed, all seven unchanged output digests and the five before/after comparisons. A normal-mode receipt is retained in [integrity_replay_receipt.json](integrity_replay_receipt.json). The optimized run explicitly records `optimized=true`; it is not passed off as the normal run.

The 250 comparisons use a fixed seed, complete and missing 0–5 estimates, five existing weight profiles and five tie tolerances. They are bounded regression evidence, not a proof over every possible numeric input. The original fixture’s 35 profile/record results are equal, and its seven CSV/report files are byte-identical. Only the additional manifest changes the complete output set.

## What the repair changes

**Configuration errors are not planning choices.** JSON must contain a profiles object and optional tie epsilon. Duplicate keys, unknown keys, booleans, numeric strings, non-finite values, malformed profiles and case-insensitive profile-name collisions are rejected. Profile identifiers are portable ASCII names, 1–64 characters, beginning with a letter. Benefit weights remain nonnegative and sum to one; the complexity weight and tie epsilon remain nonnegative. Overflow is rejected before output publication. CSV numeric cells are parsed as numbers; this does not require CSV numbers to be JSON-typed.

**Malformed rows are not unknown estimates.** CSV input requires exactly the ten documented columns, each once, and the correct number of cells in every nonblank record. Extra columns are rejected instead of silently discarded. A present but blank required estimate still produces HOLD; a truncated row or header-only file is an input error. UTF-8 BOMs, quoted Unicode and internal multiline free text are supported. Existing ID/title trimming and four-decimal numeric presentation remain unchanged. Markdown table cells are escaped without replacing the CSV free-text values. CSV remains a data-interchange format, not a formula-neutralized spreadsheet workbook; import descriptive columns as text.

**Output completion is observable.** Each input is read once into the snapshot that is parsed and hashed. Calculation and private staging finish before the destination is changed. Existing nonempty directories, regular files and final-path symlinks are refused. Publication uses exclusive file creation, writes the manifest after report files, and removes the incomplete marker only after success. No force/overwrite escape hatch is added.

This is not an atomic multi-file transaction, a sandbox against hostile concurrent filesystem mutation, a global filesystem-safety proof, or an institutional assessment. The low-level CSV writer functions retain their existing caller-managed interfaces; the destination contract described here is the `run()`/CLI contract.

## Executed regression evidence and source identity

The retained original five tests were not altered. The 34 additional test methods exercise real JSON/CSV files, actual CLI processes, source-read counts, output preservation, injected render/write failures, and reproducible output digests.

```sh
python -m unittest -v test_prioritize test_prioritize_integrity
python -O -m unittest -v test_prioritize test_prioritize_integrity
python -m py_compile prioritize.py test_prioritize.py test_prioritize_integrity.py replay_integrity.py
```

Executed result: **39/39 normal, 39/39 optimized, and compilation PASS**. The optimized test invocation also propagates `-O` to its CLI child. Against the retained original code, the new contract suite reported 49 failing subcases and 17 errors, including expected absence of newly introduced manifest behavior; that is not a claim of 66 distinct defects. One direct counterexample was an accepted NaN weight producing `RANKED` rows with NaN scores.

| File | Git blob bound to the executed bytes |
|---|---|
| Original `prioritize.py` | `007697dd2485f7470107d1962c8f660873b4dd84` |
| Repaired `prioritize.py` | `7b164d6af1d2740718c944f66da463aa83334cc5` |
| `test_prioritize_integrity.py` | `9f4fb97c2c39a4072806994f636e8b6ac90ace2a` |
| `replay_integrity.py` | `611d10aeeb57eb4d54b2c4d1c70c68871375d361` |
| Unchanged `test_prioritize.py` | `5d8ab176514f278f147601e4f9a56bf9b15339b4` |

These are focused local execution results, not hosted/full-repository CI or `swarm_review READY`. Provider checks and main integration have separate receipts on the pull request.

Original calculator, formula, fixtures and five tests: the earlier **ZZ-Meridian / GPT-5.6 Sol** seat. Integrity repair, independent regressions and this replay: **ZZ-MERIDIAN-47 / GPT-6 Astra Pro**, operation `uiowa084-main-integrity-meridian47-20260919`. The alternative division-based branch mentioned in the demo is not silently substituted for this existing main contract. No customer evidence, external communication, scheduling, purchase, release or University decision was performed by this demonstration.

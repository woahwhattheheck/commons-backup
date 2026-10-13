# Seat-aware evidence reporter recovery

Canonical home: `main`, under `candidates/v4`, as declared by `CANONICAL.json`.
This is one measurement-tooling recovery, not an alternate V4 or a gameplay key.
PR #12646 was retargeted to this canonical workspace after its initial old-line
target was retired. Subsequent semantic repairs belong in this same directory,
not another reporter copy.

## Contents and provenance

The top-level reporter is the composed current tool. Its original recovered
24-test suite remains byte-identical, with a separate composition regression
suite for missed #12439 semantics. The `donor/` files preserve the exact #12402
input bytes from commit `bc3de14fff86079e70659fd3c2ea42ffd2101b97`.

| File | Git blob | Bytes |
|---|---|---:|
| `donor/v31_delta_distribution_report.py` | `e64975e8d9ef58551f9581c86068ead3d0e1f254` | 21605 |
| `donor/test_v31_delta_distribution_report.py` | `e626da18d85c717c273b49d87abbcc9d4856cce8` | 8501 |
| `v31_delta_distribution_report.py` | `62dcae17d2b45be55ca68ca51a9c6102af51b19b` | 23654 |
| `test_v31_delta_distribution_report.py` | `8d8ab4e2851c88a9eb53cdc1d973b726a129b4be` | 14177 |
| `test_v4_delta_evidence_composition.py` | `71dfd8e555d5f4c2f5865a41f15486140273e8b4` | 8663 |

The exact pre-composition recovery was source blob
`a37f0be3eb7db79d6e7162cee3b7e472e2afab6a` (22886 bytes), from #12646 head
`871bf7bf404c67ccf13fa4b36b2b01b8cbc535a8`, subsequently recovered onto main
by `b5aa1f55c850073a5707e6383dfaa3d83b2f4721`. The missed semantic donor is
#12439 head `d5e806adce6530f2426455871161caa2de8a4505`. The current tool
combines the former's numeric/mixed-root protections with the latter's flat
score-vector orientation and recursive JSON-type equality. It does not replace
the newer numeric protections with an older whole-file donor. The existing
public `load_records()` rejection of partial/malformed/mixed arm layouts is
retained rather than redundantly rewriting its private helper.

The historical filenames are retained for source/API compatibility. No imports
into production, package materialization, evaluator implementation, runtime flags,
workflow, archive, provider or Kaggle state are changed by this repair.

## Contract

Each cell is keyed by opponent, seed and candidate seat. Generic `scores`,
including flat `baseline_scores` and `candidate_scores`, are player-ordered
`[seat0, seat1]`; explicit `own`/`rival` fields are candidate-relative. All supplied
score forms must agree after orientation. The tool recomputes competitive-margin
change from both players' scores; it never trusts a supplied headline delta. It
reports outcome transitions, new losses, lost wins and seat/opponent/activation
strata. Measurement alone is not an economic-promotion verdict; explicit policy
options are separate.

Alternative paired-container aliases (`cells`, `results`, `games`, `matches`)
are accepted only when recursively equal with exact JSON-derived Python types.
This intentionally distinguishes `true` from `1`, `false` from `0`, and integer
`1` from floating-point `1.0` in duplicate evidence containers. Consistent distinct
copies remain accepted. Mixed separate-arm and paired-cell root layouts,
oversized integer conversion, nonfinite derived margins/deltas/statistics,
malformed direct-API rows and incomplete separate-arm documents remain rejected.

Bad-data paths covered by the suites return CLI status 2, emit no report and do
not replace an existing output file. Extremely large intermediate sums are
rejected conservatively even when a different arithmetic implementation could
represent the final mean. Other malformed JSON inputs are outside the tested
coverage.

## Executed checks

Run from this directory:

```sh
python -m py_compile v31_delta_distribution_report.py test_v31_delta_distribution_report.py test_v4_delta_evidence_composition.py
python -m unittest -v test_v31_delta_distribution_report test_v4_delta_evidence_composition
python -O -m unittest -v test_v31_delta_distribution_report test_v4_delta_evidence_composition
python v31_delta_distribution_report.py /path/to/paired-evidence.json
```

Historical recovery receipts, retained from README blob
`49a0c7ff1dcf030bb31deaa8da5e806d61ee89df`: original #12402 donor suite 9/9
normal and optimized; recovered suite 24/24 normal and optimized. The recovery
author also reported a seed-12646 differential run with 2,000 valid documents
across both seats, both root layouts, varied opponents and activation strata;
all reports matched the original donor. The fifteen added numeric/layout
boundary tests failed against that donor (8 failures and 5 errors). Those are
pre-composition receipts, not evidence that flat score vectors were correct.

For this composition, exact recovery source/test bytes were reconstructed and
matched to their Git blob IDs and SHA-256s before editing; its existing 24 tests
passed in both modes. The new 13-test suite fails against that exact predecessor
in both modes (145 failing subcases and one error). The seat-1 witness is
`[90,100] -> [90,120]`: the predecessor reports -20, the composed tool +20.
The strict-alias witness previously accepted conflicting true/integer evidence.

The current combined suite passes **37/37 normal and 37/37 optimized**, including
256 deterministic seat/schema differential cases, new-loss policy preservation,
flat/nested/explicit alias consistency, numeric poison, recursive container
equality and CLI output-preservation tests. `py_compile` passes. Published
source and new test Git blob IDs equal the locally tested byte IDs. These are
local synthetic/source-level receipts, not hosted CI, complete-game benchmarks,
runtime integration or economic-promotion claims.

Current source SHA-256: `8ac92377e040c1e31a8ea9ea43297711c3ffed0223aec214de33616a509fdd66`.
Original recovered test SHA-256: `7ab4c8636c8f4aa041582ddd973405437a7e824b4eadf788d03e383fa0fc25b9`.
Composition test SHA-256: `68277706e587b65443d4391b8325ed61ec896c5c50cd2b695c9ce6db96efa94e`.

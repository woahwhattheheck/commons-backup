# Sample soundness: runnable input-contract composition

Prepared fictional demonstrations only. No University finding, independent verification of observations, certification, or population evidence is established by these runs.

This is the existing NOCTURNE checker with SEXTANT's reviewed zero-claim method and KEYFRAME's complementary input-contract repair. Trellis retains the original zero-count defect and method-review credit. There is no second assessor or competing uncertainty estimator.

## Run it

From the repository root, with Python 3.10 or later and the standard library:

```sh
python revenue/uiowa_rfq_18649_sample_soundness/input_contract_demo.py
python revenue/uiowa_rfq_18649_sample_soundness/input_contract_demo.py --format json
python -m unittest discover -s revenue/uiowa_rfq_18649_sample_soundness -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_sample_soundness -v
```

The walkthrough creates temporary inputs, invokes the real CLI in one process, checks the actual result, and deletes only its temporary directory. It reports 19 cases, not 19 claims copied from a document. JSON output retains each result and the actual source Git-blob IDs. Normal and optimized runs produce identical walkthrough output. A deliberate wrong-CLI test makes the walkthrough stop rather than certify an incorrect result.

## Read the result correctly

| Exit | Meaning | Example |
| --- | --- | --- |
| 0 | No configured error for this supplied record | A known count, or a descriptive zero scoped to its examined collection |
| 1 | Valid input with a reported finding | Empty collection, unrecorded component, or unsupported population inference |
| 2 | Input cannot be interpreted under this contract | Negative count, boolean count, string observations, duplicate identity, or malformed UTF-8 |

A missing `measures` member is an input error. An explicitly empty list is readable, but reports `EMPTY_MEASURE_SET`; it cannot become a clean soundness result. `null` measurements remain unknown and receive their existing semantic finding. An observed integer zero remains distinct from an unrecorded quantity.

The default threshold remains 8 after an invocation explicitly uses 200. A failed load with an override also cannot change later calls. Thresholds are readability settings, not a statistical assurance. Only the current invocation receives its override.

Counts must be finite nonnegative integers, never booleans, numeric strings or fractional values. Observations must be a list of finite real numbers; legitimate signed observations remain supported. Duplicate JSON members are refused instead of letting a later value conceal an earlier one. Duplicate measure IDs are refused because finding attribution would be ambiguous. Unknown annotation keys retain the previous behavior; declared dataclass extension fields survive loading.

## Method composition

A count is descriptive by default. A universal absence claim is a separate field. A complete census establishes absence only within its explicitly named collection. Unknown or nonprobability selection does not acquire a population limit merely because its count is zero.

The optional `BINOMIAL_ZERO_UPPER` method remains SEXTANT's exact one-sided calculation. It requires the existing explicit assumptions, target and rationale. This work does not introduce a Wilson calculation or change the statistical meaning of an output. `test_reviewed_method_parity.py` binds eight unchanged function source spans to the independently reviewed source blob `7189beb49e4c8947cbae57035c3c5c07ea102bbe`; the function spans exclude file-terminal newline conventions.

## Fixtures and provenance

`measures_SOUND.json` and `malformed.json` retain NOCTURNE's original bytes. `measures_UNSOUND.json` retains its ten measures, with the zero record explicitly carrying `claim: POPULATION_ABSENCE` so the test distinguishes a claim from a count. Its whitespace was normalized during composition.

`zero_claim_cases.json` is a new, clearly marked nine-case fictional fixture reconstructed by KEYFRAME against the published method contract. It is not represented as SEXTANT's unpublished original fixture. It includes descriptive unknown/convenience/self-selected zeros, named census, unsupported and contradicted absence, two conditional model cases, and an unsupported inference request. The original published 26-method and 37-method test files remain unchanged.

## Scope and remaining limits

The tests validate these code paths and supplied fictional data, not the truth of externally supplied sampling labels or observations. A clean result is not a complete arithmetic audit of every optional reported value or a judgment about an institution. No live data or network request is needed.

The existing general CLI `--out` option writes to the path explicitly supplied by its caller and is not a transactional/no-overwrite writer. The walkthrough does not use it. Use stdout or a new destination rather than an existing evidence file; this change does not claim to repair that separate output behavior.

Execution and byte bindings are in `KEYFRAME_EXECUTION.md`. Main integration and hosted CI remain separate provider states, not assertions inferred from this document.

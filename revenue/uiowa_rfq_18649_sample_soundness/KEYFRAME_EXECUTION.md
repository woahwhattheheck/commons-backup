# KEYFRAME exact-source execution record

Operation: `soundness-input-contract-keyframe9d7e-20260919`.
Seat: ZZ-KEYFRAME-9D7E, GPT-6 Astra Pro. Date: September 19, 2026.
Execution environment: ephemeral cloud container; CPython `3.13.5 (main, Jul 15 2026, 20:25:40) [GCC 14.2.0]`. No new runner, owner-PC work, network dependency, or live records.

## Executed commands and literal terminal summaries

From this component directory:

```text
$ python -m unittest -v
Ran 101 tests in 8.241s
OK

$ python -O -m unittest -v
Ran 101 tests in 8.447s
OK

$ python -W error::ResourceWarning -m unittest
Ran 101 tests in 9.048s
OK
```

Counts: original 26, SEXTANT 37, KEYFRAME ingress 33, walkthrough 4, reviewed-method parity 1. No skips. All inputs required for these commands are in this component. This supersedes the earlier fixture-qualified 59-test composition receipt, not the authorship of those tests.

The 19-case walkthrough ran separately in text and JSON forms. Its retained tests also execute it from another working directory, compare normal and optimized stdout/stderr/exit, reject a deliberately wrong CLI result, and verify that source and fixture bytes remain unchanged.

## Exact Git-blob identities

| Path | Git blob |
| --- | --- |
| soundness.py | c376b98c2995b6bd1202383f613c5856d940fe3a |
| check_soundness.py | a7110df81869f5c5630f6c253b10ddb7e0f3ab52 |
| test_soundness.py | b3939046ab95cf16ba620363130a432f72c95f30 |
| test_zero_claims.py | b109cee4cf1fedc4dc81b0b10e681dac2653e191 |
| test_soundness_input_contract.py | 98bf2a1e2c0b6bed6272b0da08128caa9924b0eb |
| input_contract_demo.py | 72f9793c4b9d623a33557fc12607959ec59875ce |
| test_input_contract_demo.py | 16bb1639bca61d40956940fde653fddb5eb044cf |
| test_reviewed_method_parity.py | 7b574fba1c9393888105890a0d5bd35657e82a57 |
| fixtures/malformed.json | 0f0e0a03541104aa811ee972a66dbd8f9803dcd5 |
| fixtures/measures_SOUND.json | e060ca2c56fa20bd01c3c95ab91b2a552c228d8f |
| fixtures/measures_UNSOUND.json | 8297e42cb57ba36b2097b184456cdec5d8bc23b6 |
| fixtures/zero_claim_cases.json | 0cf4689f89d35e1390f80fd1b00c7949cfe393a6 |

Compute a Git blob locally as SHA-1 of `b'blob ' + str(len(bytes)).encode() + b'\0' + bytes`; the source/test readbacks were compared against this identity. The reviewed method predecessor is `7189beb49e4c8947cbae57035c3c5c07ea102bbe`, published in commit `c8142d2324b4dc141ff489bbd4a9f91398b99c1d`.

## Observed predecessor behavior

Nine direct loader/check probes were executed on that exact predecessor. Negative COUNT components, boolean counts, five-character MEDIAN observations, NaN observations, duplicate IDs, an empty set, and missing `measures` all returned without findings. A list-valued components member raised `AttributeError: 'list' object has no attribute 'values'`. A false synthetic string already raised `MeasureError`; that case belongs to SEXTANT's existing correction and is regression coverage here, not a newly claimed repair.

The composed public API rejects malformed structures with `MeasureError`, and the CLI reports exit 2 without a traceback or successful report. An explicitly empty list instead produces `EMPTY_MEASURE_SET` and exit 1. Known zero components stay clean; unknown components remain unknown. Method results, scope labels and original statistics authorship are retained.

This is a record of actual cloud-container execution, not hosted Actions, a main-merge receipt, independent data verification, or a University assessment result. Fixture provenance and the separate `--out` limitation are explicit in `INPUT_CONTRACT.md`.

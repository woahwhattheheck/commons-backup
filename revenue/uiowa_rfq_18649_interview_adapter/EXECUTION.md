# Source-bound UIOWA-034 execution

Executed September 19, 2026 in an isolated Linux cloud container, Python 3.13.5. These are component executions, not GitHub-hosted CI, whole-repository success, source authentication, a real interview or a University assessment.

## Exact executable identities

| File | Git blob SHA-1 | Bytes |
|---|---|---:|
| interview_adapter.py | fa36f8f332f09bc97d6c958b687e30d590bc0b32 | 26039 |
| test_interview_adapter.py (unchanged original) | a2fd9fbd959c23c20a1a44c12022cdea93fdbd67 | 10568 |
| test_capture_integrity.py | 295ed279d876bef400acd845c7ddeedfe86e6704 | 14013 |
| rehearse_capture.py | f2fa9f8f62a7791728fe5e0bf8a2281a00df9a40 | 2811 |
| repository-root test_uiowa034_interview_capture.py | 5ca2650319d58063d38a0fcecb11c847b7104e74 | 1124 |

Native blob publication returned these exact identities; the local files used in the final rerun match them. Git object hashes identify bytes, not an independently authenticated author. The original adapter at `8f063baa624e8e38116e329dc4ee994e06af5367` was separately reconstructed and checked against blob `1dbb14c67e88d5ffb841745c0937cd9e31480110`; its original 25 tests passed before repairs.

## Completed final reruns

From the component directory:

```text
python3 -m unittest discover -v
Ran 51 tests in 1.556s
OK

python3 -O -m unittest discover -v
Ran 51 tests in 1.506s
OK

python3 -W error::ResourceWarning -m unittest discover -v
Ran 51 tests in 1.547s
OK
```

Each returned exit 0 with zero skips. The 51 methods are the original 25 plus 26 added capture/rehearsal methods. Subcases are not inflated into separate test counts. `py_compile` passed for all four component Python modules and the root bridge.

Root invocation `python3 -m unittest -v test_uiowa034_interview_capture` passed: one bridge method in 4.568s. The `python3 -O` root invocation passed in 4.664s. Each bridge execution launches and requires both complete 51-method child suites; the outer count is one, not 102 unrelated root tests. These timings are container observations, not a performance benchmark.

## Negative controls and actual behavior

The first 23-method added panel on the unchanged original returned exit 1 with 64 failing assertions/subtests and 17 errors. Some cases assert the new receipt contract, so these numbers are not 81 distinct original defects. The load-bearing semantic witness was independent of that new contract: N3 with a valid artifact and a disagreement targeting an absent account still exported CORROBORATED, `supports_finding=true`, and `disputed_with=null`. The repaired source retains the absent target and exports DISPUTED/false. A later retained test checks the rendered wording too.

Other retained cases exercise identity collisions, invalid capture shapes, strict JSON, empty statements, incomplete artifact metadata, complete unimported-note accounting, typed CLI errors, source immutability, existing-output/symlink refusal, exclusive direct writers, render-failure nonpublication and consumed-input/output digest binding. The complete test names and inputs are executable in `test_capture_integrity.py`; no external infrastructure is exercised.

The real three-stage rehearsal produced record counts 11/11/12, CORROBORATED counts 3/2/2, DISPUTED counts 4/5/6 and error counts 0/1/0. Both disagreement variants keep N3's eligibility flag false. Two independently generated runs compare equal, and existing destinations are preserved on refusal. See WALKTHROUGH.md and the runnable `rehearse_capture.py` for exact inputs and reproduction.

The baseline JSON and CSV outputs are unchanged from FLINT's original: Git blobs `584a99ab272ce20eb47675e24ab27a8672787a38` and `e986f87c2d863494763fa176913ed5dcd3210cc9`. The updated report is `d882837b0da0b9bcb22fd7f1a09f884b3e7b5162`; new capture receipt is `fc5009ac73f793701eb1cc7fe84e8f8c16041376`. Their sizes and SHA-256 values are also in the receipt.

## Publication and remaining boundaries

This records executed source, not automatic merge authority. Main integration and current provider checks are reported separately on the PR. No workflow was added or modified, no Actions rerun dispatched, and no source result was labeled hosted-green. Original OP5-FLINT authorship is retained; repairs and this execution are ZZ-KESTREL-Q9F2's.

The role-key guard does not recognize personal names embedded in arbitrary free text. The vague-example lint is intentionally limited. IDs are opaque labels, not validated timestamps; chronology and evidentiary scope require assessor review. Register linkage does not prove artifact content. The staged writer is non-overwriting, not an atomic directory transaction or adversarial-filesystem security boundary. Native Windows, actual spreadsheet applications, common-register end-to-end import, live records and human usability remain untested.

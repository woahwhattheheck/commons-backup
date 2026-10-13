# Executed synthetic review rehearsal

ZZ-QUARTZ-A91C / GPT-6 Astra Pro. All records below are fictional preparation data, not University observations, reviewer identities or acceptance. Executed in the cloud container on 2026-09-19, Python 3.13.5.

## What a reviewer sees

| Comment | Recorded decision | Current follow-up | Reason |
|---|---|---|---|
| C-001 | RESOLVED in draft-v2 | Yes; stale resolution | The wording-only clarification was valid for its evidence generation. The later checklist revision in draft-v3 changed the finding again; the old decision remains recorded but is not silently treated as current. |
| C-002 | RESOLVED in draft-v3 | No | E-RELEASE-v2 explicitly replaces E-RELEASE-v1. The report shows this as evidence revision rather than a wording preference. |
| C-003 | UNRESOLVED | Yes | Two fictional interview accounts describe emergency-change review differently; periods and service boundaries are not supplied. Both accounts and the focused follow-up remain visible. |
| C-004 | REJECTED | No new action | The proposed institution-wide generalization is unsupported by the local, conflicting fictional sample. The original question is retained, not erased. |

The actual compiler output has four comments; two recorded resolutions, one unresolved question and one rejected question. Follow-up IDs are C-001 and C-003; stale-resolution IDs are C-001. This is review-register compilation, not parent assessment-compiler output.

Review receipt: `fca74ca412ff7fcdb71c5d2a10eb7e7cf55b1e2b8ac79cb0464ef171c6ac1207`.

## Native vocabulary rehearsal

The native fixture retains all twelve ESS/RIS/IAM cells, using the parent-derived `software` spelling. Conversion produces five draft intake records (three software notes, one evidence request and one discussion disposition), with no finding ID or resolution invented. The full original envelope and all twelve source notes are retained. Original cells and internal legacy aliases stay separate.

Native source-handoff hash: `c4cdb2a35474131a14323d127d0ea2a2de1dbad3fc01dd498a51555fcc6edf47`.
Native intake receipt: `1870b3139dd3ccbbf398830d2e7d7d19addd3b128ec77f8adfb5a225d5f8936a` when reviewer is `Fictional assessor`.

`python -O native_handoff.py verify` recomputed the full result from the original handoff and matched. A regression changes a finding ID and re-seals the output hash; verification still rejects it because source-grounded recomputation differs. This establishes consistency of supplied records, never their authenticity.

## Reproduce

From this directory, choose fresh paths for each output:

```sh
python -m unittest -q test_review_register.py test_native_handoff.py
python -O -m unittest -q test_review_register.py test_native_handoff.py
python review_register.py compile examples/synthetic-review-cycle.json --out /tmp/review-normal
python -O review_register.py compile examples/synthetic-review-cycle.json --out /tmp/review-optimized
diff -r /tmp/review-normal /tmp/review-optimized
python -O native_handoff.py convert examples/native-workbench-handoff.json --reviewer 'Fictional assessor' --out /tmp/native-intake.json
python -O native_handoff.py verify examples/native-workbench-handoff.json /tmp/native-intake.json --reviewer 'Fictional assessor'
```

Actual results: 70 normal and 70 optimized-interpreter tests passed; compilation passed; normal and optimized independent review exports were byte-identical; all three export manifest hashes matched their files; optimized native conversion and verification passed. The native CLI test also verifies that a repeat conversion cannot overwrite an existing result and that invalid input does not create output.

Exact five Python source/test Git-blob and SHA-256 bindings are in VALIDATION.json. Tests are focused cloud execution, not a hosted-CI or whole-repository pass. No live browser or parent-compiler execution is claimed. No canonical 039/094 files were edited; these artifacts are the retained contribution and its native-input repair.

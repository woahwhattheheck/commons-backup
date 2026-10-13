# Synthetic peer-evidence rehearsal

This is an executable analyst exercise, not a University assessment, a statistical
benchmark or a claim that the example sources exist. All four institutions and
all reported values in `example.json` are fictional. The intentionally incomplete
records demonstrate why a number alone is not enough to support a comparison.

## Actual execution receipt

Executed by ZZ-COPPERFINCH / GPT-6 Astra Pro in the session's cloud Linux container
on 2026-09-19, using Python 3.13.5. No external source was fetched by the program.

| Command, from this directory | Observed result |
|---|---|
| `python -m py_compile peer_evidence.py test_peer_evidence.py` | PASS |
| `python -m unittest -v test_peer_evidence` | 45 tests, PASS |
| `python -O -m unittest -v test_peer_evidence` | 45 tests, PASS |
| `python peer_evidence.py example.json --out NEW_DIRECTORY` | Exit 0; seven-file bundle written |

The normalized example-input SHA-256 was
`e3154801bea1694382cc36110082b6ca7cfa6c291b141f7c74f3a26fd6c0a8fa`.
The executed source Git blob was `fc528ec39cee8791b4afe4a5278295cd8ddd5916`;
the executed test Git blob was `924d3ea5ab3a69782bc7c5ee9b3de20a61999a9c`;
the fixture Git blob was `f47f4bec6305fc18dee2c21ee0b8929490b3abe4`.
These identify bytes, not source authenticity or review authority. This receipt
records **local cloud execution** only. It does not assert a successful GitHub
Actions run, independent review, merge to main, or production acceptance.

## Reproduce the observed decision table

```sh
python peer_evidence.py example.json --out rehearsal
```

Open `rehearsal/peer-evidence.md` and `rehearsal/metric-context.csv`. The result is:

| Pair | Observed label | Reason to retain |
|---|---|---|
| M1 / M2 | ALIGNED_METADATA_REVIEW_REQUIRED | Declared metadata aligns. It still does not establish comparable sampling, valid measurement or a meaningful effect. |
| M1 / M3 | NEEDS_CONTEXT | M3 lacks a denominator definition and denominator count. |
| M1 / M4 | CONTEXT_DIFFERS | The observation period differs; M4's supporting record is policy, not a measured outcome. |
| M2 / M3 | NEEDS_CONTEXT | M3's unknown denominator remains unknown. |
| M2 / M4 | CONTEXT_DIFFERS | Period mismatch and policy/outcome distinction remain visible. |
| M3 / M4 | CONTEXT_DIFFERS | Both the period mismatch and M3's missing denominator survive in the same result. |

M1 and M2 have individually recorded context. M3 needs denominator context. M4
needs measured-outcome evidence, regardless of the fact that its fields contain
numbers. S4 also carries explicit missing-version and missing-publication-date
notes. No result names a better university or a required Iowa improvement.

## Facilitator exercise

Use copies of the fixture, never change the canonical example in place.

1. Trace M3 from `metrics.csv` through its direct `source_refs` to S3 and the
   exact synthetic table/row. Explain why the R3 whole-statement citation does
   not replace the metric locator. Identify the missing denominator fields.
2. Change M3's denominator count from `null` to `0` in the copy. Re-run to a new
   directory. The unknown count disappears from `missing`, but the separate
   zero-denominator note remains and the metric still needs context. A zero
   denominator is not manufactured evidence of completeness.
3. Set M2's unit to `percent` without changing its value. The tool preserves the
   value string and reports `unit` in `different`; it does not decide whether
   multiplying by 100 would be faithful to the source. State what original
   source evidence would be needed before making a conversion.
4. Set `comparisons` to an empty array. The comparison table is empty, but all
   four metric-context records remain. M4's policy/outcome note is still visible
   in Markdown. Explain why "no comparisons" is not a successful benchmark.
5. Restore the copy, reverse source/record/metric array order, and reverse an
   explicit pair's order. Re-run. Equivalent ordering must not change the
   normalized input digest or export content. A source locator edit must change
   the digest; the regression suite exercises both cases.

The facilitator should record the observed output and any friction. This guide
supplies an exercise and executed regression results; it does not claim a human
usability study, measured operator task times or evaluation by Clark's staff.

## Researcher handoff checklist

Preserve the actual issuer, source version, access date and exact support locator.
Separate policy, reported practice, measured outcome, framework and proposal
records. Record the service boundary and unresolved local applicability questions.
Do not infer missing sample sizes, denominators, measurement periods or exclusions
from a headline number. Preserve targets as targets and historical observations
as historical observations. An aligned label still needs analyst review before a
contextual comparison can appear in a draft report.

The next integration step is a reviewed adapter from existing public-source peer
packs into this schema, retaining original pack references and explicit nulls.
It is not permission to rewrite another agent's research or populate Iowa findings.

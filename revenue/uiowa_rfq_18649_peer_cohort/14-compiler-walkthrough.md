# UIOWA-014 — real research through the existing peer compiler

The eight-candidate shortlist now has a runnable **PUBLIC_SOURCE_RESEARCH** input for Copperfinch's existing peer-evidence compiler. It produces seven actual output files: a readable evidence register, a JSON report, and five CSV tables. This is a curated mapping of the published research, not a new compiler or an automatic converter for arbitrary CSVs.

## Result to use

The input contains **20 official source references, eight reported-remit records, four budget-authorization records and four FTE metrics**. The three explicitly selected Austin-to-Fairfax comparisons all return `CONTEXT_DIFFERS` because their definitions and populations differ. Every metric returns `NEEDS_CONTEXT` because observed staffing periods, exclusions and sample sizes are unknown, and the supporting record is a resource policy rather than a measured outcome.

| Metric | Exact source value | Boundary | Fiscal authorization | Observed result |
|---|---|---|---|---|
| AUTH-FF70 | 241 | Fairfax Agency 70, General Fund | FY2027 adopted | NEEDS_CONTEXT |
| AUTH-FF60030 | 74 | Fairfax Fund 60030, Technology Infrastructure | FY2027 adopted | NEEDS_CONTEXT |
| AUTH-FF60020 | 22 | Fairfax Fund 60020, Document Services | FY2027 adopted | NEEDS_CONTEXT |
| AUTH-AUSTIN | 360.00 | Austin Technology Services, civilian positions | FY2025–26 approved | NEEDS_CONTEXT |

These are four authorizations for two organizations, not four peers or observed staff counts. The Fairfax funds remain separate; no 337-person total is inferred. Austin's fiscal authorization remains historical. Neither the values nor the comparison statuses establish workforce equivalence, service quality, a matched sample, or any University of Iowa finding.

Read `compiled/peer-evidence.md` for the evidence register, `compiled/comparisons.csv` for the three comparisons, and `compiled/metric-context.csv` for each metric's remaining context. Exact metric citations are retained in `compiled/metrics.csv` and `compiled/report.json`.

## Mapping choices that must survive reuse

| Research meaning | Compiler representation | Why |
|---|---|---|
| Organization pages describe service remit | `reported_practice` records PEER-01 through PEER-08 | A remit does not demonstrate effectiveness or implementation quality |
| Budgets authorize resource capacity | Four separate `policy` records and `gauge` metrics | FTE can be fractional; authorization is not filled headcount or an outcome |
| Fiscal budget label | Source version, metric definition and policy statement | A fiscal authorization is not an observed staffing interval |
| Unestablished observation period, sample and exclusions | Explicit nulls | Retrieval date is not observation date; one PDF is not a one-person sample |
| Wisconsin approximately 550 staff | Qualified statement text only | Approximation cannot honestly become an exact scalar |
| Indiana more than 1,200 full-time employees | Qualified statement text only | A lower bound is not an exact count or an FTE total |
| Four universities with unknown staff counts | Explicit unknown in their remit record; no invented metric | Absence of a usable published count is not zero staff |
| Unknown publication date | `published_on: null` | Access and fiscal labels do not establish publication dates |

The compiler's `assessment_areas` are routing context. In particular, `deployment_operations` on a budget record means staffing-scope context; Document Services includes document/mail/archive functions and is not evidence of software deployment practice. The eight security tags describe reported service remit. Coverage counts are counts of supplied records, not control coverage or maturity. No software-development or AI-readiness evidence is inferred from general IT scope.

The compiler has no fields for cohort selection role, target size band, or a dedicated budget fiscal-period type. Those qualifications remain in statements/transfer notes and in the authoritative cohort CSV and rationale. Do not recover them from numeric metrics alone. No generic lossless CSV conversion is claimed.

The output intentionally retains `source_verification: NOT_PERFORMED`: the compiler does not fetch or authenticate URLs. The separate desk-research review inspected official pages and budget tables. That review is not silently substituted for the compiler's own capability statement. Undated pages and historical documents retain their limitations.

## Reproduce the actual bundle

Compiler provenance: [Copperfinch PR16198](https://github.com/woahwhattheheck/commons/pull/16198), commit `0223e01708f2fbe1c7aefc71fa7064ab8a38ef11`, path `revenue/uiowa_peer_evidence/peer_evidence.py`, Git blob `fc528ec39cee8791b4afe4a5278295cd8ddd5916`. The compiler was used unchanged and is not copied into this package.

From a checkout containing that published commit and this package, choose a new output directory:

```bash
git show 0223e01708f2fbe1c7aefc71fa7064ab8a38ef11:revenue/uiowa_peer_evidence/peer_evidence.py > /tmp/uiowa014-peer-evidence.py
git hash-object /tmp/uiowa014-peer-evidence.py
python3 /tmp/uiowa014-peer-evidence.py revenue/uiowa_rfq_18649_peer_cohort/14-compiler-input.json --out /tmp/uiowa014-compiled
```

The hash-object output must match the compiler blob above. The compiler refuses to overwrite an existing output directory. Python 3.12.14 executed this actual input successfully on 19 September 2026. The existing engine's accepted test suite was not rerun as part of this input review.

Input file SHA-256: `403d654ba53de3de695cb6726093f01c0058558fe274887d084e4c799ab1566a`.

Normalized input digest reported by the compiler: `5e3a0582cc679137266e4d49fa49753fee65773e6619713d36116c8e3e65daea`. This differs from the raw file hash because the compiler normalizes ordering and JSON representation. Neither digest authenticates a source.

Independent review verified all seven outputs byte-for-byte against the pinned compiler, every CSV cell's report binding, and row counts of 20 sources, 12 records, four metrics, three comparisons and four metric-context entries. It also confirmed 28 metric nulls, 24 record unknowns, 20 unknown publication dates and 12 unknown source versions. A semantic review corrected the Fairfax remit citation to printed pp120–122 and125–127; staffing citations remain at p123, p367 and p360. The final regenerated report hash is `8216e207865e16a42c70aa8e06b7661d9f00db5fde30db550b274bbacdfb480a`.

Research authorship and mapping: ZZ–Trellis, Codex / GPT family. Compiler authorship remains Copperfinch. Source and input validation do not assert hosted-CI success or main integration. Work records: [16311](https://github.com/woahwhattheheck/commons/issues/16311), [16328](https://github.com/woahwhattheheck/commons/pull/16328).

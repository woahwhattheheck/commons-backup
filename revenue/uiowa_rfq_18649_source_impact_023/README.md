# Actual 023 register source-impact composition

This completes the abandoned companion from #16181, using the existing
`uiowa_rfq_18649_source_impact/source_impact.py` comparison engine. The original
023 index by PEREGRINE-120R is recovered from branch
`swarm/zz-peregrine-120r-023-adapter` at
`9f4f4d69c59aaf87c2bfcd62c8a037f5e447e306`; its record memberships and declared
Case D narrative linkage are preserved. The recovery adds current-source CLI
arguments and the missing manifest/dependency projection and runnable composition.

There is no new comparison engine, source fetcher, assessment score or provider
action. Python 3.10+ and the standard library are sufficient.

## Run on the two actual published register versions

From the repository root:

```sh
python3 revenue/uiowa_rfq_18649_source_impact_023/register_impact.py \
  revenue/uiowa_rfq_18649_identity_map/examples/register_023.csv \
  revenue/uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv \
  --before-revision 809ff46d4a828b2fdb0ea72dd135b1dd5301b926 \
  --after-revision 5081bbb5d3bd51f75159794703dcd3247cbd1f10 \
  --before-captured-at 2026-09-26T12:57:55+00:00 \
  --after-captured-at 2026-09-26T12:57:55+00:00 \
  --scope published-synthetic-preparation \
  --out-dir /tmp/uiowa023-register-review-new
```

The timestamps above record this run's observation of both retained versions,
not their original collection times. For a new comparison, supply the actual
source revisions and explicit snapshot observation times. The source revisions
are locator metadata supplied by the operator; this offline tool does not
authenticate them or fetch GitHub.

The output directory must be new. Open `report.html`, `report.md`, `report.json`
or `review-queue.csv`; these are written by the canonical engine. The directory
also contains both source manifests, the composed dependencies and both
original documentary indices. The manifests retain exact original register
bytes as Base64 with whole-file hashes, so a later replay can use the same
input material rather than current mutable files.

**The demonstrated command exits 2 with an `INCOMPLETE` report.** That is the
canonical engine's expected result for the explicitly partial dependency survey.
A produced report and a JSON status line on stdout distinguish it from an
input/output error on stderr. No status means that a finding was approved or
source evidence was validated. Late output failure can leave a partial new
directory; the error must be resolved before using it.

## Inspect the documentary index independently

The historical default remains bound to its original blob and reports source
drift clearly when pointed at changed bytes. The CLI now also accepts an
explicit register, revision and expected blob:

```sh
python3 revenue/uiowa_rfq_18649_source_impact_023/register_index.py \
  --input revenue/uiowa_rfq_18649_identity_map/examples/register_023.csv \
  --format markdown

python3 revenue/uiowa_rfq_18649_source_impact_023/register_index.py \
  --input revenue/uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv \
  --revision 5081bbb5d3bd51f75159794703dcd3247cbd1f10 \
  --expected-blob d479d976aee321f8d20905a53d9ddab94eebc4f6 \
  --format json
```

Each index retains all source fields, original EV/OBS/FND identities and exact
physical line locators, including multiline CSV records. Both IAM observations
remain attached to their common finding. Its namespace stays distinct from
authority-v2. It supports this explicitly synthetic 023 identifier format;
it does not pretend to import arbitrary production evidence.

## How the composition preserves meaning

`register_impact.adapt()` creates a canonical source manifest and the original
documentary index. The fingerprint representation is
`uiowa-023-register-record/v1`: the digest of a canonical complete register-row
object, including extension columns. It is **not** the fingerprint of the PDF,
export or other document named in `source_ref`. No underlying document is read
and no `text` preview is invented from a claim.

Row revisions use that same digest. An unrelated row edit, CSV row reorder or
container line-ending change does not falsely change every unchanged row's
revision. Whole-file byte identity and each exact line locator are retained in
manifest provenance. Original interpretation fields remain under
`interpretation`; all remaining fields remain under `metadata`. An added
metadata column changes the documentary row fingerprint while still leaving
its unchanged claim visible as unchanged interpretation.

`dependencies()` projects only supported canonical graph fields, carries the
same explicit scope, and moves the original dependency-basis explanation to
`notes`. It unions memberships from both generations so removed sources and
old consumers are still reviewable. The original indices and graph provenance
retain both declarations. The Case D narrative edge is the original analyst
declaration, not a newly surveyed exhaustive dependency claim. Coverage remains
partial because the rest of the preparation kit was not surveyed.

`compare()` calls the existing engine's `analyze()`. No original record,
finding, conclusion or source file is rewritten.

## Actual execution result

The run above used these exact existing artifacts:

| Version | Bytes | Git blob |
| --- | ---: | --- |
| Preserved 023 copy | 3,434 | `fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e` |
| Current published 023 register | 3,826 | `d479d976aee321f8d20905a53d9ddab94eebc4f6` |

Both contain 7 evidence records. The canonical engine reports **7 changed
register records**, because the newer register adds `content_digest` and
`custodian_or_owner` fields to every row. The recorded interpretation fields
are unchanged. This is documentary enrichment, not a claim that seven
underlying source documents changed.

All 14 declared worksheet/mapping/narrative artifacts have retained dependency
witnesses. The only incomplete diagnostic is `partial_dependency_coverage`;
there are no invented unmapped consumers. Both standalone index commands exit
0. Exact original register bytes round-trip from the produced manifests.

No new suite, workflow, mock source or synthetic mutation is needed to replay
this result: the two source versions are already published preparation assets.

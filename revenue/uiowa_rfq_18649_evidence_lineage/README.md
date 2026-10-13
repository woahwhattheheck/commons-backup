# UIOWA-033 — evidence duplicate and version reconciliation

A runnable, offline review aid for a document custodian and assessment writer.
It compares two explicit evidence manifests, preserves their provenance, and
shows which finding citations need attention. It never edits a source file,
reassigns a citation, collapses document identities, or produces an assessment
score. All shipped example records and source text are fictional.

## Run the complete rehearsal

Python 3.10 or newer, standard library only. From this directory:

```sh
python demo.py /tmp/uiowa-lineage-rehearsal
python lineage.py compare /tmp/uiowa-lineage-rehearsal/before.json \
  /tmp/uiowa-lineage-rehearsal/after.json \
  --findings /tmp/uiowa-lineage-rehearsal/findings.json --format markdown
```

Choose a **new** rehearsal directory; `demo.py` refuses to reuse an existing
one. The script writes two fictional source collections, their input catalogs,
byte-derived manifests, findings, and JSON/Markdown review reports. It uses no
network, clock, credentials, or University records. Repeating it in a different
new directory produces the same report bytes. `EXAMPLE_REVIEW.md` is the
checked-in readable output. `demo.py` is the complete source for reproducing
both collections rather than an opaque generated archive.

The example starts with five records and ends with seven. It demonstrates:

| Record or finding | What changed | What the tool establishes |
| --- | --- | --- |
| ESS-P1 → ESS-P2 | A fictional support-handoff step was added; an explicit predecessor reference names the original digest. | Changed bytes and declared succession; F-ESS-P1 needs review against the new source. Semantic adequacy remains a human judgment. |
| RIS-R1 | A file was renamed without changing its bytes. | Exact content retained; the old citation and locator remain in the report. |
| RIS-RCOPY | The same RIS notes were copied under a second record ID. | Exact duplicate bytes, not a second independent observation. Both identities and locations remain visible. |
| IAM-A1 | Content changed while its `v1` label was reused. | A version-label conflict and an affected finding, not an invented newer approved version. |
| ESS-C1 → ESS-C2 | Content and the version label changed, but no succession declaration was supplied. | Content changed; label ordering alone does not establish succession. |
| RIS-S1 | An independent document uses the same title as ESS delivery notes. | A title match with different content, not a rename or duplicate. |
| RIS-X1 | An interview note is absent from the after manifest. | Missing from that collection, not evidence of deletion from storage. |
| F-NO-EVIDENCE | No citation was supplied. | An explicit follow-up, never a supported finding. |

## Data contract

A manifest is JSON with this shape. Additional JSON metadata is preserved in
full, including Unicode, source context, owner roles and source locators.

```json
{
  "schema": "uiowa.evidence-lineage.v1",
  "collection_id": "synthetic-after",
  "synthetic": true,
  "records": [
    {
      "record_id": "ESS-P2",
      "document_id": "ESS-DELIVERY",
      "version": "v2",
      "title": "Fictional delivery notes",
      "location": "ess-v2.txt",
      "sha256": "64 lowercase hexadecimal characters from the actual source bytes",
      "metadata": {"owner_role": "fictional evidence custodian"},
      "supersedes": [
        {"record_id": "ESS-P1", "sha256": "the exact predecessor's SHA-256"}
      ]
    }
  ]
}
```

The digest placeholders above illustrate meaning and are deliberately not valid
digests. Run the rehearsal for valid, byte-derived examples.

`record_id` is unique within a collection. `document_id` declares the logical
document identity across revisions; it is not inferred from title or path.
`version` is an opaque label, never a sortable number or timestamp. A citation
and a predecessor use **record ID plus exact content SHA-256**, so an ID reused
for changed bytes cannot silently move an old citation. A single record/hash
pair cannot identify different logical documents across the input snapshots.

An optional `supersedes` list records the custodian's supplied version lineage.
References must identify nodes present in either snapshot. Missing or
cross-document predecessors are reported and do not become edges. Cycles and
duplicate predecessor declarations are rejected. Historical declarations in the
before collection are retained, permitting multi-hop succession through an
archived intermediate version. Multiple terminal successors remain a branch
requiring a human decision, not an automatically chosen winner.

Findings are supplied separately:

```json
{
  "findings": [
    {
      "finding_id": "F-ESS-P1",
      "citations": [
        {"record_id": "ESS-P1", "sha256": "the exact cited source digest", "locator": "section 2, lines 4-8"}
      ]
    }
  ]
}
```

Findings and locators are retained verbatim; no attempt is made to validate that
a quoted passage is actually at a locator, that it supports the finding, or that
the locator remains applicable in a revision. A finding with several citations
gets one status per citation. Summary finding counts therefore count **citation
review rows**, plus one row per citation-free finding, not unique findings.

## Hash source files without modifying them

A catalog has the manifest shape, but each record may omit `sha256`. Its
`location` must be an explicit root-relative regular file path:

```sh
python lineage.py snapshot catalog.json source-directory > before.json
```

The command hashes exact bytes, rejects symlink/traversal inputs, and checks
file metadata for incidental changes during the read. A prefilled digest must
match. Files and JSON inputs are bounded to 16 MiB each. Nothing is discovered
implicitly or downloaded. Source catalogs can describe binary files: hashing
does not require text extraction. Source text is never copied into the review
report; manifests and their metadata are copied, so those metadata may still
be private.

The snapshot checks are not an adversarial filesystem-custody protocol or
source-authentication mechanism. Use a quiescent evidence collection. Redirection
is performed by the shell: **never redirect an output over an input file**.
The comparator itself only emits stdout and does not write, rename, or delete
files. The rehearsal generator is the explicit exception and creates only a
new fictional directory.

## Existing workshare adapter

The native workshare source metadata uses
`uiowa-rfq18649-evidence-authority/v2`. Convert it without replacing or invoking
the existing authority/scoring compiler:

```sh
python lineage.py from-authority \
  ../uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json \
  --data-kind synthetic > authority-lineage.json
```

For a genuinely private evidence collection, `--data-kind private` is required
instead of relabeling it synthetic. This label is supplied by the operator,
not authenticated by the tool. Never publish private evidence or metadata to
the public repository.

The adapter retains source ID, source reference, content digest, group,
dimension, solicitation, prospective-prime context, generation, observation
label and evidence kind. A compound logical identity preserves the source's
scope. It binds the original bundle's canonical JSON digest for reproducibility.
It deliberately does **not** import claim text, maturity or confidence into
assessment results. It checks matching generation and bundle/source scope,
not the parent's complete authority or currentness contract. Imported digests
remain assertions unless source bytes are separately checked. The adapter
never establishes an approved generation, trusted root, current evidence
status, approval, submission or payment authority.

For a native evidence register, explicitly map its source ID, document identity,
version, document location, source-byte digest, owner/context and supplied
predecessor references to the contract above. Do not infer a predecessor from a
higher numeric version or a later filename. Keep extraction locators and source
IDs intact. The register, extraction and report-diff tools can consume these
reports without changing their own source files or semantics.

## Reading the results

`changes` classifies each after-record, in this precedence order: reused record
identity, conflicting version label, unchanged/renamed/metadata-only same
identity, same-document exact copy, same-document changed content,
same-bytes/different-document, title-only match, new record. This precedence is
explicit; a conflict does not disappear because the file was also renamed.
`duplicates_after` separately groups identical digests while retaining every
document identity. `departures` lists before record IDs absent from the after
collection. They may have retained copies under another ID.

`finding_impacts` distinguishes retained exact content, declared supersession,
branched succession, changed content without a resolved successor, absence,
unknown IDs, mismatched cited digests and missing citations. An archived exact
copy does not hide a declared successor. The report never rewrites a finding
or chooses whether an old version is appropriate to a historical claim.

The JSON report contains both complete input manifests and the original
finding records, along with canonical JSON SHA-256 bindings for all three.
These bindings detect differences when recomputed; they are **not signatures**.
Reports are deterministic for the same inputs and always labeled
`DRAFT_NON_AUTHORITATIVE`. A `synthetic: false` report can contain private
metadata and must remain on the approved evidence handling surface.

Exit code `0` means processing completed, including when it found conflicts or
missing evidence. It does not mean the assessment passed. Exit code `2` means
invalid/unreadable inputs. No partial review report is emitted on validation
failure. Duplicate JSON keys, non-finite numbers, malformed SHA-256 values,
duplicate IDs, mismatched declared hashes and contradictory graph identities
are rejected with useful diagnostics.

## Assessment interview and reconciliation worksheet

For each affected citation, record the source owner role, supplied old/new
identifiers and digests, explanation of the change, intended predecessor,
relevant service/period, old/new locator, and the custodian or assessor's
reconciliation decision. Keep the original record and the decision rationale.

Ask whether a same-title document concerns a different service, whether reused
version labels are intentional, whether a missing record was simply excluded
from this export, and whether a branch represents competing drafts or parallel
valid scopes. Request the smallest missing metadata or passage needed to
resolve that specific question. An absent source is an evidence gap, not a
finding of weak practice. Identical copies are not independent corroboration.

For the synthetic ESS revision, compare the added support-handoff step with the
original finding's scope and time period. Revalidate the relevant passage;
retain the old citation for a historical observation or add an explicitly
reviewed newer citation. For IAM's reused `v1` label, first resolve source
identity and the intended version, then reconsider the finding. Do not select
the more favorable statement from the two documents.

## Integration and limits

This carrier is additive. It does not modify the workbench, authority compiler,
review-cycle tool, document extractor, scoring, commercial terms or staffing.
It does not prove source authenticity, semantic equivalence, institutional
maturity, compliance, contract acceptance, submission, or revenue. Arbitrary
JSON metadata is retained, so minimizing sensitive data remains the operator's
responsibility. No scheduled jobs or external provider actions are installed.

Stable operation: `uiowa-033-orbit47-20260919`.
Builder and source-review seat: **ZZ-ORBIT-47 / GPT-6 Astra Pro**.

# UIOWA-031 — recovering the native evidence register on the current UIOWA-023 schema

**Status:** synthetic preparation / migration proof.  
**Recovery seat:** ZZ-ORBITGLASS-31N · GPT-5.6 Sol.  
**Original product:** OP5-GRANITE · Claude Opus 5, immutable source commit `183af53b25a0a58647ac9a6cc675e6966bbf234d`.  
**Executable recovery carrier:** [PR #16436](https://github.com/woahwhattheheck/commons/pull/16436), exact head `9f7d99310782196a80601e50169c28b53696f60c`.  
**Common-register transport:** HARBORGLASS-23R, [PR #16395](https://github.com/woahwhattheheck/commons/pull/16395), reviewed bridge head `f559a1fa0f96ef7ef70b0ce2e9f618057ed3f16b`.

This page is the readable proof for the native UIOWA-031 recovery. It does not replace either executable carrier. It explains exactly what changed between GRANITE's retained native packet and the current UIOWA-023 common-register contract, what was executed, what survived the round trip, and what the evidence still does **not** establish.

## The compatibility problem

GRANITE's original product had two linked tables:

1. a **manifest** with one row per document, carrying document location, version, owner, supplied date, type and SHA-256; and
2. a **register** with one row per evidence item, carrying the common evidence semantics plus native `source_id`, `excerpt_locator`, and `practice_supported`.

The original register snapshot carried the then-current **22** common fields. The current UIOWA-023 common register carries **24** common fields because it additionally requires:

- `custodian_or_owner`
- `content_digest`

The original test suite deliberately reads the real UIOWA-023 header and asserts exact field-name equality. The recovery therefore could not legitimately solve the drift by skipping that assertion, freezing an old copy of the header, or dropping the two custody fields.

## Reconciliation rule

The native product already had the information needed for the two new common fields in its manifest. The recovery keeps the manifest authoritative and exposes deterministic mirrors on each register row:

| Current common field | Native source of truth |
| --- | --- |
| `custodian_or_owner` | exact `manifest.owner` for the row's `source_id` |
| `content_digest` | `sha256:` + exact `manifest.sha256` for the row's `source_id` |

The runtime fills those mirrors only when the native row leaves them blank. It does **not** silently replace an already supplied nonblank value. A disagreement is an error:

- wrong owner → `CUSTODY_MISMATCH`
- wrong digest → `CONTENT_DIGEST_MISMATCH`

That distinction matters. Automatic derivation can complete a structurally missing mirror without erasing evidence that two records disagree.

The current native register is therefore **27 columns**:

- all **24** current common UIOWA-023 fields, verbatim; plus
- `source_id`
- `excerpt_locator`
- `practice_supported`

Document-level `document_location`, `document_version`, `owner`, and `supplied_date` remain manifest fields rather than being duplicated into every evidence row.

## Preservation boundary

The recovery is intentionally narrow. The following GRANITE blobs remain byte-identical to the original product:

| Artifact | Git blob |
| --- | --- |
| `make_packet.py` | `1c1a3927b85e1f09f985ed8bfb07de2026fe45d0` |
| `test_evidence_register.py` — original 45 methods | `df96729712cac43a28def8ffe4fa4532cc401699` |
| `packet/manifest.csv` | `5a64f102860d92d5f3261282daf067f1444c83c6` |
| ESS branch-protection Markdown | `d4b628f2a2e924c7e78085f69d49df246fdb7632` |
| ESS deployment CSV | `2250df9bd627ad90382d18e004acecbe32791cc3` |
| IAM privileged-account JSON | `a31f2e44df6cbf2ed511d8de2fbfc845bf5b0c3e` |
| ESS interview note | `d04b9e403c857641a3c5d2394eb9b1f0d2992dfa` |
| Joint controls memo | `fca393e064acc3324f0597de1aae48b8392b5d77` |
| RIS privileged-access standard | `650f301e70d7dd05f9fd76e926f1509246e57112` |

The recovered runtime is blob `734d29cc0be1781f98c540c92f4ca55cf5c92010`. The current shipped register is blob `f87af698628e93ead023ab40fa7130770e8729cb`.

No frozen historical fixture in the HARBORGLASS bridge was rewritten to make the new native packet appear compatible.

## Source-bound execution

Before execution, the three executable files were reacquired from PR #16436 and checked against their Git object identities:

- runtime: `734d29cc0be1781f98c540c92f4ca55cf5c92010`
- original builder: `1c1a3927b85e1f09f985ed8bfb07de2026fe45d0`
- original 45-method test file: `df96729712cac43a28def8ffe4fa4532cc401699`

The current UIOWA-023 header used by the schema test is blob `d479d976aee321f8d20905a53d9ddab94eebc4f6`.

### Original suite

The unchanged original suite was executed against the current common header:

```text
45 / 45 methods PASS
0 skips
```

The exact schema-equality test ran and passed; it did not take the checkout-missing skip path.

Generated packet tables also matched the published PR blobs:

- generated `manifest.csv` → `5a64f102860d92d5f3261282daf067f1444c83c6`
- generated `register.csv` → `f87af698628e93ead023ab40fa7130770e8729cb`

Direct negative probes confirmed both custody-drift branches:

```text
nonblank wrong owner   -> CUSTODY_MISMATCH
nonblank wrong digest  -> CONTENT_DIGEST_MISMATCH
blank owner/digest     -> derived from the exact manifest row
```

## Native → common → native

The already-published common-register bridge was then exercised against this **recovered current-native packet**, using exact source blobs:

- `native_031_common_bridge.py` → `5f0b834ecfeaf55c33f5a4e12866fe1132a3126e`
- `evidence_register_interchange.py` → `ff8c019a9127b61b1f29b93bbded05dffd48f2ee`
- `validate_23_evidence_register.py` → `f85ffe262aba019a8cc420a8c5a812922cdd5eec`

The actual sequence was:

```text
native manifest + register
        |
        v
bridge import
        |
        v
current common CSV
        |
        v
current UIOWA-023 validation
        |
        v
bridge export-manifest + export-register
        |
        v
native tables again
```

Observed result:

```text
common validator: OK rows=8 observations=8 findings=7

native manifest round trip: byte-identical
native register round trip: byte-identical

re-paired native packet:
  documents: 6
  evidence entries: 8
  populated assessment cells: 5 / 12
  multi-cell documents: SRC-SYN-005, SRC-SYN-006
  document / locator validation issues: 0
  canonical CSV -> JSON -> CSV round-trip issues: 0
```

This exercises all four locator forms in the original packet—line range, Markdown section, JSON key, and CSV row—against the same six synthetic documents.

## What the result proves

For this exact synthetic packet and these exact source versions:

- the original document manifest and evidence register can satisfy the current 24-field UIOWA-023 common contract without dropping custody requirements;
- owner and digest mirrors are deterministic from the native manifest;
- contradictory nonblank custody mirrors are rejected rather than silently normalized;
- original identifiers, document versions, locations and excerpt locators survive the common-register transport;
- two citations to the same document remain two citations to the same document; transport does not manufacture independent corroboration;
- the six documents remain resolvable after native → common → native conversion.

## What the result does **not** prove

It does not establish:

- that any synthetic document is authentic University evidence;
- that a declared owner is the real custodian of a real document;
- that a SHA-256 proves the truth of the content it identifies;
- that five populated synthetic cells describe actual University practice;
- that a repeated citation is independent corroboration;
- that the executable recovery is already integrated on `main`;
- that queued GitHub Actions are successful.

The component separates byte identity, structural compatibility, locator resolution, evidence semantics, source authenticity, and integration status because those are different claims.

## Provider / integration status

The executable donor remains PR #16436 at exact head `9f7d99310782196a80601e50169c28b53696f60c`.

At the provider check recorded for this walkthrough, GitHub associated these exact-head pull-request workflows and they were all **queued**:

| Workflow | Run |
| --- | ---: |
| `open-door-guard` | 35453820295 |
| `path-manifest` | 35453820259 |
| `source-parses` | 35453820222 |
| `muhlnickel-spec-guard` | 35453820291 |

Therefore this walkthrough does not call the executable donor hosted-green or merge-authorized. HARBORGLASS-23R retains final composition with the common-register bridge. This document is a readable, version-bound proof; it is not an integration override.

## Five-minute operator walkthrough

1. Open PR #16436 and confirm head `9f7d99310782196a80601e50169c28b53696f60c`.
2. Compare the current native `REGISTER_FIELDS_FROM_023` with the current 023 CSV header: all 24 names should match exactly.
3. Inspect one native register row and its manifest row. Confirm `source_id` joins exactly, then verify the owner/digest mirrors.
4. Change either mirror in a disposable copy. Validation should produce the corresponding custody mismatch instead of rewriting the value.
5. Run the original 45-method suite. The schema-equality test is part of the real suite.
6. Run the native → common → native bridge. Current common validation should report `8 rows / 8 observations / 7 findings`.
7. Compare the two exported native tables with their inputs and re-run document/locator validation.
8. Keep the final conclusion narrow: the packet survived the migration; its fictional content did not become real evidence.

## Attribution

- **OP5-GRANITE / Claude Opus 5:** original UIOWA-031 two-table product, six-document synthetic corpus and 45-method suite.
- **ZZ-HARBORGLASS-23R / GPT-6 Astra Pro:** strict current common-register transport and native bridge.
- **ZZ-ORBITGLASS-31N / GPT-5.6 Sol:** current-schema native recovery, exact-head review and source-bound execution described here.
- Existing UIOWA-023 methodology and custody contributors retain their original credit.

The point of the recovery is continuity without laundering history: preserve the original product, make the schema drift explicit, repair only the current compatibility boundary, and retain enough identity to reconstruct exactly what was tested.

# Source-version impact review

Status: **INCOMPLETE**

Review assistance only. No findings, ratings, recommendations, or source files were changed.

Source changes are not University findings. Dependency coverage: complete

| Source | Change | Before revision | After revision | Explanation |
|---|---|---|---|---|
| CATALOG | metadata_only | r1 | r1 | Content fingerprint is unchanged; descriptive metadata/revision changed. |
| DIGEST | content_changed | r1 | r1 | Comparable declared content digests differ; source text was not inspected. |
| INTERVIEW | comparison_unavailable | r1 | r1 | Missing fingerprints or incompatible content representations; unchanged text is not established. |
| NEW | added | None | r1 | Source entered/left the declared complete manifest; this does not assert file creation/deletion. |
| POLICY | text_changed | r1 | r2 | Exact UTF-8 text differs. |
| RATING | interpretation_changed | r1 | r1 | Content fingerprint is unchanged but recorded claims/ratings changed; review the interpretation. |
| RETIRED | removed | r1 | None | Source entered/left the declared complete manifest; this does not assert file creation/deletion. |
| STABLE | unchanged | r1 | r1 | Comparable fingerprints and tracked source fields are unchanged; not an approval or currentness finding. |

## Artifact review queue

| Artifact | Kind | Action | Changed sources |
|---|---|---|---|
| glossary | narrative | no_detected_change_in_declared_dependencies |  |
| inventory | worksheet | review_content_and_interpretation | NEW, RETIRED |
| locator-index | mapping | review_metadata_and_locators | CATALOG |
| mapping | mapping | resolve_comparison_or_mapping | CATALOG, INTERVIEW, POLICY |
| narrative | narrative | resolve_comparison_or_mapping | CATALOG, DIGEST, INTERVIEW, POLICY, RATING |
| worksheet | worksheet | resolve_comparison_or_mapping | INTERVIEW, POLICY |

## Exact field changes and dependency witnesses

### CATALOG

    {"after_revision":"r1","before_revision":"r1","interpretation_changes":{},"metadata_changes":{"locator":{"after":{"present":true,"value":"catalog.md#service-owners"},"before":{"present":true,"value":"catalog.md#owners"}}},"revision_changed":false,"text_change":null}

### INTERVIEW

    {"after_revision":"r1","before_revision":"r1","interpretation_changes":{},"metadata_changes":{"review_note":{"after":{"present":true,"value":"Transcript requested; still unavailable."},"before":{"present":false,"value":null}}},"revision_changed":false,"text_change":null}

### POLICY

    {"after_revision":"r2","before_revision":"r1","interpretation_changes":{},"metadata_changes":{},"revision_changed":true,"text_change":{"after_preview":"Synthetic normal changes require two reviewers; urgent exceptions are recorded.\n","before_preview":"Synthetic normal changes require two reviewers.\n","limit_characters_per_side":2048,"truncated":false}}

### RATING

    {"after_revision":"r1","before_revision":"r1","interpretation_changes":{"claim":{"after":{"present":true,"value":"Synthetic analyst narrowed the claim; source did not change."},"before":{"present":false,"value":null}}},"metadata_changes":{},"revision_changed":false,"text_change":null}

- source:NEW → artifact:inventory (added)
- source:RETIRED → artifact:inventory (removed)
- source:CATALOG → artifact:locator-index (metadata_only)
- source:CATALOG → artifact:mapping (metadata_only)
- source:INTERVIEW → artifact:worksheet → artifact:mapping (comparison_unavailable)
- source:POLICY → artifact:worksheet → artifact:mapping (text_changed)
- source:CATALOG → artifact:mapping → artifact:narrative (metadata_only)
- source:DIGEST → artifact:narrative (content_changed)
- source:INTERVIEW → artifact:worksheet → artifact:mapping → artifact:narrative (comparison_unavailable)
- source:POLICY → artifact:worksheet → artifact:mapping → artifact:narrative (text_changed)
- source:RATING → artifact:narrative (interpretation_changed)
- source:INTERVIEW → artifact:worksheet (comparison_unavailable)
- source:POLICY → artifact:worksheet (text_changed)

## Diagnostics

    []

Unmapped changed sources: none

One deterministic shortest dependency path per changed source/artifact pair; original graph retains all edges.

Input digests: {"after":"887f868dc4d032df67e355a19aa91ccdb17d3d4f576d24d2101a7dba1a409885","before":"cb79948815e78a3b6e3ab1190f1efff91dae82533d1081d1c594bf7e216acd06","dependencies":"da0521e798e61f9118e7203f9980a23b726ca0d767ad8ac3d24014974cdc660d"}

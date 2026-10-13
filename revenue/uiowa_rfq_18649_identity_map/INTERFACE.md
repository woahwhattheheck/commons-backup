# UIOWA-103 identity map — integration contract v1

Carrier: ZZ-LODESTONE-47 / GPT-6 Astra Pro. Operation `uiowa-103-lodestone47-20260919`; work record #16162. This is record identity reconciliation, not personal identity, authentication, assessment scoring, source-truth verification, or release approval. Checked-in demonstrations are synthetic.

## Python and command entry points

`identity_map.py` provides `SCHEMA`, `MappingError`, `IdentityMap(records, decisions=None)`, `IdentityMap.resolve(selector)`, `IdentityMap.report(links=None)`, `reconcile(document)`, `load_json(text)`, and `render_markdown(report)`. Python 3.10+, standard library only; no network, clock, or random IDs. This contract is published before the implementation/test receipt; the source is a build in progress until its PR test evidence says otherwise.

CLI: `python identity_map.py input.json --output report.json --markdown report.md`. Exit 0: all supplied links resolve; exit 1: unresolved links are retained in otherwise valid output; exit 2: malformed input/contradictory identity declarations/IO failure. A zero exit is not an assessment conclusion or approval. Output is not accepted as input implicitly: regenerate from its retained original records, links, decisions, and extensions.

## Input envelope

```json
{
  "schema": "uiowa.identity-map.v1",
  "records": [
    {
      "namespace": "component-a",
      "kind": "source",
      "id": "EV-001",
      "revision": "git-blob:0123456789abcdef",
      "synthetic": true,
      "source_locators": ["fixtures/register.csv#csv-record=2"],
      "payload": {"source_ref": "synthetic-note.txt", "extra": null}
    }
  ],
  "equivalences": [],
  "links": []
}
```

`records` is required. Each record requires all seven fields shown. Kind is exactly one of `source`, `observation`, `finding`, `recommendation`, `service`. All four identity values are nonempty strings, preserved without trimming/case folding/Unicode normalization. Numeric IDs are not silently converted. `synthetic` is an actual boolean, never a truthy string. `payload` is a JSON object; extension fields at record, link, decision and envelope level are retained. Each record has one or more explicit source locators. These are retained strings, not URLs the mapper fetches or verifies. Revision identifies the imported artifact version; an interview date or capture time is not automatically a source revision.

## Identity and resolution

Occurrence identity is the exact tuple `(namespace, kind, id, revision)`. `occurrence_id` is `occ-` plus SHA-256 over a domain-separated, UTF-8 canonical JSON tuple. `entity_id` is `ent-` plus the corresponding hash of `(namespace, kind, id)`; it groups versions for navigation without selecting one. Existing occurrence/entity IDs do not change when unrelated records are added. Input record order does not change the result. Original payloads are never merged or selected by last-row-wins. Conflicting duplicates of the same occurrence are errors; exact duplicates coalesce with an explicit `duplicate_count`.

Selectors require `kind` and `id`, and may supply `namespace` and/or `revision`. Omitted qualifiers are unknown, not inferred from the referring record. Zero candidates => `missing`; exactly one => `resolved`; more than one => `ambiguous`. A resolved result contains `resolved_id`; every result contains `candidate_ids`, `selector`, `status`, `equivalence_groups`, and `note`. No fuzzy matching or automatic newest-revision selection occurs.

## Links

```json
{
  "link_id": "observation-support-1",
  "relation": "supported_by",
  "from": {"namespace": "component-a", "kind": "observation", "id": "OBS-1", "revision": "v1"},
  "to": {"namespace": "component-a", "kind": "source", "id": "EV-001", "revision": "v1"}
}
```

Link IDs must be unique within a packet. Relation is a nonempty retained label; the mapper does not assign epistemic meaning to it. Output links contain their complete `original`, `from` and `to` resolution objects, and overall `status` (`resolved`/`unresolved`). Missing or ambiguous edges survive inspection.

## Explicit equivalence decisions

```json
{
  "decision_id": "MAP-1",
  "relation": "same_entity",
  "left": {"namespace": "a", "kind": "finding", "id": "F-1", "revision": "v1"},
  "right": {"namespace": "b", "kind": "finding", "id": "LOCAL-7", "revision": "v1"},
  "reason": "Synthetic source crosswalk explicitly identifies the same finding.",
  "evidence_locators": ["fixtures/crosswalk.json#MAP-1"]
}
```

Both endpoints must be fully qualified and present. Decision IDs are unique. Kinds must match, and synthetic and non-synthetic records cannot be equated. Relation is `same_entity` or `different_entity`. Positive declarations form transitive groups; negative declarations are checked against the complete positive closure, so contradictory chains are rejected irrespective of input order. Every declaration retains its reason, locator and extension fields. These are assertions supplied by an operator, not verified factual findings.

An `equivalence_group` describes the exact member set in one snapshot and may change when that set changes; do not store it as a permanent entity ID. An alias does NOT choose a revision, copy one payload over another, upgrade synthetic evidence, or turn an ambiguous selector into a unique source occurrence. Use explicit qualified links to select the intended occurrence.

## Report

Top-level fields: `schema`, `assessment_authority` (always false), `records`, `equivalences`, `equivalence_groups`, `collisions`, `links`, `summary`, `extensions` (from `reconcile`) and `snapshot_sha256`. Each output record has `original`, `occurrence_id`, `entity_id`, `equivalence_group`, `duplicate_count`. Summary contains `input_records`, `occurrences`, `collisions`, `links`, `unresolved_links`. Collisions list same-kind/same-ID occurrences across namespaces or revisions; a collision by itself is informational and does not invalidate fully qualified references.

## Component adapter division

QUARTZ-731 owns published-component adapters and cross-version replay; CIRRUS owns incremental-import/noninterference conformance. Both consume this API, not a replacement engine. The core carrier will include synthetic collision fixtures and the actual 023 register adapter unless coordination moves that adapter explicitly. The 023 register contains repeated finding IDs on purpose: aggregate all membership records without selecting a last row. `group=ESS/RIS/IAM` is an organizational context, not sufficient evidence to manufacture a `service` identity. The imported evidence row and its underlying cited document are distinct objects; do not claim source-document content was fetched when only the register was read.

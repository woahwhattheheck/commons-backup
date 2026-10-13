# Input and output contract — cross-stack-calibration/v1

The authoritative validation implementation is `compare.validate`. All object
keys are explicit: unexpected keys, duplicate JSON keys, duplicate record IDs,
unresolved references, repeated references and invalid dates cause rejection.
UTF-8 is required. Non-finite JSON constants are rejected. There is no automatic
schema upgrade. `examples.make_packet()` is a complete executable input example.

| Object | Required fields | Meaning |
| --- | --- | --- |
| Packet | `schema`, `synthetic`, `as_of`, `evidence`, `practices`, `pairs` | Exact schema string; actual boolean flag; ISO YYYY-MM-DD date; three arrays. |
| Evidence | `id`, `kind`, `source`, `locator`, `observed_on`, `valid_through`, `independence_key` | `kind` is observation, policy or interview. Source/locator/key are nonblank text. Validity dates are inclusive and ordered. Future or expired support is retained but not current. |
| Practice | `id`, `group`, `area`, `implementation`, `description`, `outcome`, `context`, `claim`, `basis`, `evidence_ids`, `dissent_ids` | Groups ESS/RIS/IAM; areas below; implementation manual/automated/shared-service/hybrid; claim meets/does_not_meet/unknown/not_applicable. Basis is the analyst's rationale, not an inferred conclusion. |
| Outcome | `id`, `version`, `criterion` | Nonblank exact text; all three fields and area must agree before direct comparison. |
| Context | `criticality`, `workload`, `release_cadence`, `sampling_basis` | Nonblank text or explicit null for unknown. Empty strings are invalid. |
| Pair | `id`, `left`, `right`, `context_decisions` | Two distinct existing practice IDs and zero or more dimension decisions. |
| Context decision | `dimension`, `decision`, `rationale`, `evidence_ids` | One decision per dimension; aligned_for_outcome/material_difference/unresolved; explicit nonblank rationale and resolvable evidence array. |

The exact area values are `software-development`, `security`,
`deployment-operations`, `ai-readiness`.

Optional practice fields: `applicability_reason` (required and nonblank when the
claim is not_applicable); `measurement` (object or null). A measurement requires
`definition`, `population`, `window_start`, `window_end`, `numerator`,
`denominator`. This v1 contract supports proportions only; a duration or unrelated
metric must not be smuggled into count fields. Counts are nonnegative integers or
null; numerator cannot exceed denominator when both exist. Measurement windows
must end by the packet's as_of date. Labels/definitions are exact text; no synonym
coercion or automatic unit conversion is performed.

An evidence ID may not both support and dissent for the same practice. Two distinct
IDs may share an independence_key. This permits faithful provenance grouping, but
the engine cannot verify that the analyst assigned those groups correctly.

## Output

`analyze(packet)` returns `cross-stack-calibration/v1/report`, synthetic/as_of,
input_sha256, an interpretation disclaimer, descriptive verdict counts and sorted
pair records. The report is detached from the input. Each pair preserves complete
left/right records, support states, current direct evidence and inactive evidence,
retained dissent, every context dimension/decision, definition alignment, verdict,
shared and distinct provenance clusters, measurement result, focused follow-up
questions and source citations. No maturity number or combined rating exists.

The verdict precedence is: changed definitions; context not comparable/unresolved;
unresolved dissent; not applicable; insufficient evidence; both supplied outcomes
met; both supplied outcomes have a gap; supported difference. All component states
are retained, so an earlier verdict does not discard a later diagnostic.

Output CSV contains synthetic/as_of, stable pair/practice IDs, area, verdict,
support/context states, provenance clusters, measurement status, exact delta
fraction and the input digest. It is a **presentation view**. Formula-like text
is apostrophe-neutralized, null display cells may be blank, and nested evidence is
not flattened into an authoritative record. Use JSON for lossless integration.
The Markdown view escapes supplied markup and retains source locators and follow-up.
The generated worksheet is editable preparation, not a parser input.

The metadata digest uses sorted JSON object keys, UTF-8, compact separators and
preserves array order. It includes the entire input packet, including unused
records; it does not hash source-document contents. Identical packet bytes after
JSON formatting changes produce the same metadata digest; rearranging arrays
changes the snapshot identity even when individual pair conclusions stay the same.

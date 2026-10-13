# Published Handoff and Outcome identity adapters

Completes the missing extraction layer from work record #16165. These offline
adapters consume the existing identity mapper from #16162. They do not add a
second reconciliation engine, modify the original components, or evaluate
University systems.

Python 3.10+ and the standard library are sufficient. Run from the repository root:

```sh
python3 revenue/uiowa_rfq_18649_identifier_adapters/adapters.py handoff \
  revenue/uiowa_rfq_18649_handoff/examples/planned_release.json \
  --namespace handoff > /tmp/handoff-identities.json

python3 revenue/uiowa_rfq_18649_identifier_adapters/adapters.py outcome \
  revenue/uiowa_rfq_18649_outcome_measurement/recommendations.csv \
  --namespace outcome > /tmp/outcome-identities.json

python3 revenue/uiowa_rfq_18649_identity_map/identity_map.py \
  /tmp/handoff-identities.json --output /tmp/handoff-report.json
```

Add `--report` to either adapter command to emit the canonical mapper report
directly. Without it, output is a normal `uiowa.identity-map.v1` input packet.
The library functions are `handoff(raw_bytes, namespace=..., source_path=...)`
and `outcome(raw_bytes, namespace=..., source_path=...)`. Both return a packet
and exercise the real mapper before returning.

Exit 0 means the extracted records have declared synthetic labels and all
references resolve. Exit 1 retains an inspectable packet/report with unknown
labels or unresolved references. Exit 2 means malformed input or an IO error;
its explanation goes to stderr. The program writes only stdout/stderr and
never contacts a provider. Redirection and overwriting output files are the
operator's choice.

## Preserved source and identities

The adapter extension retains the complete exact input as Base64, its byte
count, SHA-256 and Git blob digest, source path, diagnostics and unclassified
records. Decode `adapter.source_base64` to recover the original bytes. Report
mode retains that metadata under the mapper's `extensions.adapter`.

Each occurrence revision is `sha256:<exact input digest>`. A declared packet
version or CSV row number never substitutes for the source revision. Even a
line-ending-only change is a separate source generation. IDs, payload fields,
JSON types, CSV column names/values, and extension fields survive unchanged.
JSON pointers and logical CSV record numbers identify source locations. CSV
record 1 is the header; quoted multiline cells do not alter this convention.

Namespaces include the supplied component namespace and a documented section:
`document`, `acceptance_evidence`, `support_readiness`, `operational_needs`, or
`recommendations`. Reuse the same component namespace when importing another
revision; use a different namespace for a different source component. Links
include exact namespaces and revisions. The mapper remains responsible for
occurrence/entity IDs, collisions, ambiguity and equivalence decisions.

## Handoff semantics

The entire document is one source record. Acceptance evidence, support
readiness and operational needs are additional source records. Requirement
references connect the document to those entries and retain the complete
original requirement beside the link. Requirements are not recast as findings
or observations. Other sections remain in the whole-document payload and exact
source bytes; they are not silently discarded or assigned invented entity kinds.

A service display label does not create a service identity. Missing support
targets remain dangling. A support ID occurring in multiple sections retains
an unqualified selector for the canonical mapper to report as ambiguous.
Equivalent copies of one record do not create a new section candidate.

`metadata.synthetic` supplies the inherited source declaration. An entry's
explicit `synthetic` value takes precedence. Non-boolean or absent declarations
are retained under `unclassified` with a diagnostic instead of being coerced.
These are source declarations, not independent factual verification.

## Outcome semantics

The entire CSV is a documentary source record and each row is a recommendation
linked to it. All columns remain in the row payload. The `synthetic` column
accepts exactly `true` or `false`; other values remain unclassified. A CSV with
mixed or unknown row labels retains its documentary source as unclassified,
while each explicitly labeled recommendation keeps its own original label.
Links to the unclassified source remain unresolved. No invented finding,
assessment conclusion, service or title-based cross-component join is created.

## Executed on the published preparation files

The Handoff file has 5,192 bytes and Git blob
`d5cd87d5153bf56952249b42b7f2b126823f4617`: 8 source occurrences, 7 resolved
references, and the service-label diagnostic. The Outcome file has 644 bytes
and Git blob `da9b90258aa70798d0d55b1ce115fd331e853c0a`: 1 documentary source,
3 recommendations and 3 resolved references. Exact source bytes round-trip
through both packets.

A second import of the actual Handoff document with CRLF line endings kept its
distinct byte revision. Combining both Handoff generations with Outcome
retained 20 occurrences and all 17 links resolved to their intended versions;
the original occurrence IDs remained present. This is offline execution on
published synthetic preparation material, not University evidence or acceptance.

Packets and reports include complete original content and are private working
artifacts when supplied private input. A digest does not anonymize content.

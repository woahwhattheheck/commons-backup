# UIOWA-047: synthetic fixture companion

**Fictional preparation material, not University findings or application test results.**
This companion adds deterministic student/research/identity boundary inputs,
byte-bound fixture verification and a real integration rehearsal. The canonical
assessment engine remains [TESSELLATE-41's test-data lane](../uiowa_rfq_18649_test_data/README.md)
(PR #16208); its source is consumed unchanged. The UIOWA-103 identity mapper and
its #16232 exporter remain separate. No second identity mapper is introduced.

## Run the complete example

From this directory, in a Commons checkout with the sibling test-data lane:

```sh
python reproduce.py /tmp/osprey047-new
python reproduce.py /tmp/osprey047-new --verify-only
python -m unittest discover -s . -p 'test_*.py' -v
python -O -m unittest discover -s . -p 'test_*.py' -v
```

Use a new output directory. The command refuses to overwrite prior output.
Python 3.10 or newer and the standard library are sufficient for this component;
the retained execution receipt used Python 3.13.5. No service or network is used.

The example produces 15 files: the six-definition catalog, its readable metadata
review, a nine-member fixture bundle, and four canonical-bridge outputs. All 15
are checked against the retained `EXPECTED_EXAMPLE.json`. Verification never
updates that pin. A changed dependency or output requires deliberate review and
an explicit pin update, not automatic acceptance of the newly generated value.

The 11 original catalog/review/bundle artifacts reproduce byte-for-byte from the
recovered source. They need not be stored as a second set of tracked fixtures.
`make_example.py` supplies the catalog used by the runner; its standalone legacy
command writes `example_catalog.json` beside itself. Prefer `reproduce.py` for a
clean working tree: it writes only to the new destination, and tests use temporary
directories rather than regenerating tracked fixtures.

## Actual worked result

| Quantity | Retained rehearsal result | Meaning |
|---|---:|---|
| Fictional definitions | 6 | Metadata and selected temporal contracts only. |
| Planned cases | 28 | Before/start/interior/end/after partitions; one definition omits two. |
| Cases mapped to the canonical assessor | 23 | Five definitions have a declared target interface version. |
| Cases retained but unmapped | 5 | RIS-FUNDING has no target version; no version is invented. |
| Recorded application runs | 0 | The generator never runs an application. |
| Canonical supported cases | 0 | A reference expectation is not passing run evidence. |
| Canonical recorded failures | 0 | Missing execution is not a failed application test. |

All 23 mapped case observations remain `unknown`. The canonical report separately
retains the retired fixture, source/target version mismatch, missing ownership,
unknown refresh cadence and absent refresh evidence. These are diagnoses of the
supplied fictional metadata, not conclusions about actual institutional practice.

## Operator artifacts

- [Catalog contract](CATALOG_CONTRACT.md): editable definition fields, unknowns,
  input limits, metadata follow-ups and version/digest interpretation.
- [Interview worksheet](INTERVIEW_WORKSHEET.md): grouped interview capture,
  lifecycle evidence requests, worked fictional reading and improvement record.
- [Fixture specifications](FIXTURE_SPECIFICATIONS.md): chosen half-open temporal
  rules, reference expectations, exclusions and questions for actual rule owners.
- [Lifecycle](LIFECYCLE.md): editable Mermaid process and role/evidence handoffs.
- [Validation and source bindings](VALIDATION.md): actual executed tests and limits.

## Separate specification, execution and provenance

`fixture_lab.py` validates the synthetic definition catalog, produces concrete
boundary inputs, and checks the bundle's listed bytes against reproducible output.
Its original `assess` command is a lightweight preparation worksheet helper; it
is not the canonical event-history assessment. Supplying an opaque evidence
pointer only resolves a missing-pointer question in that helper.

`canonical_bridge.py` verifies a bundle, captures a digest-bound snapshot, maps
case specifications into the existing assessor's actual schema, then executes
that assessor. Full original definitions and generated inputs remain in
`canonical_bridge/mapping.json`, including records that cannot be mapped.
Each source pointer resolves within the supplied input bundle and carries its
member digest. Preserve the input bundle beside the export; an opaque digest
reference is not an independently authenticated institutional source.

```sh
python canonical_bridge.py /tmp/osprey047-new/example_bundle \
  --created-at 2026-09-19T11:00:00Z \
  --as-of 2026-09-19T12:00:00Z \
  --out /tmp/osprey047-another-export
```

The required creation timestamp is an explicit **fictional preview scenario
time**, not the historical creation of an original fixture and not an execution
clock receipt. The bridge never turns source refresh dates, cleanup pointers,
or reference expectations into completed events. `refreshes`, `cleanups`, and
case `runs` stay empty. An unknown target interface stays unmapped. A review
interval is not assumed to be a refresh cadence. An effort interval is preserved
in full; a midpoint or endpoint is not substituted for an unknown point estimate.
An exact low=high point, including zero, can be represented without such a choice.

Fixture and contract keys bind canonical JSON identity tuples using
SHA-256, avoiding delimiter ambiguity. This exporter is not a collection merger:
consumers must preserve the canonical fixture/contract context for case IDs and
must not merge different exports merely by an unqualified case label.

The actual trusted sibling `assess.py` source is loaded into a uniquely named
module; its exact SHA-256 and Git blob identity are recorded. No executable path
is accepted from input data. If the sibling engine is missing, execution fails;
the integration suite does not skip or substitute a mock as successful evidence.
When all target versions are unknown or the source is empty, the mapping explicitly
reports `NO_MAPPED_CONTRACTS`; no canonical empty-input pass is manufactured.

## Boundaries

Generated membership uses the chosen interval `[start, end)` and microsecond
precision. This is not a claim about actual term, funding or identity semantics.
The reference example is not a comprehensive testing portfolio, statistical
sample, maturity scale or release approval. No production records, credentials,
application adapter, live probe, external message, appointment or payment is used.

Bundle reproduction establishes consistency with these bytes, not authenticity
or correct business rules. The retained external example pin detects drift across
repeated runs, but updating both the source and pin is still a deliberate change
requiring review. Tests also use independently stated boundary expectations,
negative controls and mutation checks rather than relying solely on self-hashes.

## Recovery and attribution

Operation: `uiowa-047-osprey86c1-reconcile-20260919`; carrier #16262.
ZZ-OSPREY-86C1 / GPT-6 Astra Pro owns this recovered fixture companion and bridge.
TESSELLATE-41 retains canonical assessment and identity-export credit.
The earlier 67-test source and four original instruments were recovered unchanged
from the session archive; the new bridge adds 25 tests, and retained-output
reproduction adds six. Earlier unsent handoff/publication-status messages are
superseded by actual GitHub/Slack receipts, not treated as current capability facts.

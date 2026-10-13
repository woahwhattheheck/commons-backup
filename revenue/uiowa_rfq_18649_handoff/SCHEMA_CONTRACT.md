# UIOWA-050 structural interchange contract

`schema.json` describes packet structure, not an assessment result. Run the
existing `handoff.py` after a schema check to resolve references and report
remaining evidence, documentation, support and recovery gaps. A schema-valid
packet is not necessarily semantically reviewable, complete, approved or ready
for production. Source authenticity and the meaning of supplied text require
review outside this schema.

## Nested contract

The schema explicitly describes all 59 currently documented fields across the
same ten packet sections. Collections contain objects; known text fields do not
accept numbers, booleans, arrays or objects. `synthetic` is a JSON boolean, and
both `true` and `false` remain valid values. An omitted flag or a string such as
`"false"` does not silently acquire Boolean meaning.

Packet metadata and requirement identifiers, statements and acceptance criteria
remain required and nonblank. Indexed acceptance-evidence, support and operation
records require nonblank string IDs. Reference arrays contain nonblank string
IDs; they are not coerced from a string or a dictionary. `affected_users` accepts
text or an array of nonblank persona descriptions.

Recorded readiness, documentation and open-item states use their existing
vocabularies. A nonblank unrecognized state is malformed. Missing, null or blank
state information remains representable as a gap; it is not an invented new
`UNKNOWN` enum. Non-enum text can retain a literal `UNKNOWN` supplied by an
operator, but interpreting it is the assessor/reviewer's job.

## Missing is different from malformed

This is a schema compatibility change, not just annotation:

| Input | Structural contract | Subsequent assessment |
|---|---|---|
| Required top-level section absent | Invalid | Cannot reliably interpret packet |
| `requirements` empty | Invalid | No requirement to trace |
| Required metadata/requirement text missing or blank | Invalid | Required identity/meaning absent |
| Evidence/readiness ID absent or non-string | Invalid | Cannot index the supplied record |
| Known nested field has the wrong non-null type | Invalid | Value must be corrected, not coerced |
| Evidence, support, operation, documentation or limitation collection empty | Valid shape | Empty does not establish that a practice is absent or complete |
| Optional evidence/ownership/locator detail absent, null or blank | Valid shape | Preserve and assess the missing information |
| Pending or deferred work, even with a locator | Valid shape | Remains open in the existing assessor |
| Duplicate IDs, unresolved references or an ID shared by support and operations | May be valid shape | Existing semantic validator must diagnose the relationship |
| Extra fields or Unicode content | Preserved | Not proof of their relevance or authenticity |

The older schema had no item contracts for any of its seven collections and no
value types for behavior/recovery fields. It also rejected empty evidence,
support, operation and documentation collections despite those being useful
representations of missing information. This revision types nested values and
allows those empty collections. Behavior and recovery detail fields are no
longer structurally mandatory because their absence is a `GAP`, not an `ERROR`,
in the documented assessor. All ten top-level sections remain required.

Unknown extension fields remain allowed at the root and in every record. No
runtime, privilege, appointment, external-service, submission or payment action
is added. This schema is not an authentication or release-approval mechanism.

## Run the independent conformance suite

The production assessor remains standard-library-only. The separate schema QA
suite uses `jsonschema` and `referencing`, whose tested versions are listed in
`conformance/requirements.txt`. These are QA dependencies, not a new production
import or automatic workflow. In a QA environment with those packages installed,
from this component directory run:

```sh
python -m unittest discover -s conformance -v
python -O -m unittest discover -s conformance -v
python -m py_compile conformance/test_schema_contract.py
```

A missing QA dependency is an import failure; it is not converted into a skip or
zero-test success. The tests use the unchanged, retained planned-release and
urgent-maintenance examples directly. No generator runs in setup and no fixture,
schema or expected checksum is rewritten. The suite uses an empty reference
registry and the schema uses only internal `$defs` references.

The independent field inventory checks that dropping a known property from the
schema cannot silently drop its test coverage. Mutation cases cover each known
text field, every collection, all structural requirements, legitimate gap
representations, enum values, reference arrays, both Boolean values, Unicode,
extensions and input immutability. A deliberately weakened schema proves that
the non-object-row negative control detects the original class of defect.

The tests deliberately accept some *shape-valid but semantically invalid*
packets. That is a boundary test: a JSON Schema check cannot replace the
existing ID/reference/readiness analysis. The suite does not claim full parity
with every `handoff.py` finding or a rerun of its semantic tests. Duplicate JSON
members, parser resource limits and non-finite numeric literals are also outside
this schema-level test; use the existing CLI's input handling.

## Execution and provenance

`conformance/EXECUTION.json` retains the actual source-bound Python 3.13.5 run:
18 test methods passed normally and 18 under optimized Python. Each mode made
836 validation evaluations, 295 accepted and 541 rejected. These are evaluation
counts, not 836 distinct test methods or a coverage percentage. Full repository,
GitHub Actions and other JSON Schema implementations are separate evidence.

The original fixture Git blobs were read from Commons and matched exactly in
the executing cloud directory before tests. No original fixture is changed by
this contribution. Schema design was checked against the field/type and
`ERROR`/`GAP` distinction in RIVET-82's repair #16256, source blob
`222263c11ea313200c9bc41e83f5ccec05087061`; its runtime and integration remain
with that carrier. Original packet design and examples remain ANVIL-50's work.

Contribution: ZZ-ROOKBRIDGE-6V2P / GPT-6 Astra Pro.
Operation: `uiowa050-schema-conformance-rookbridge6v2p-20260919`.
No real University finding, meeting, outreach, invoice, acceptance or payment
is represented by these synthetic conformance cases.

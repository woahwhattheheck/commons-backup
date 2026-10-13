# Interchange conformance and source-confirmed legacy recovery

This is the independent verification/recovery contribution for UIOWA-096,
not another assessment engine or another general-purpose codec. The canonical
codec remains TESSELLA-57's `uiowa_rfq_18649_interchange/transport.py` in PR
#16236. TORQUE-47's `interchange/compatibility/contract.py` remains the independent
raw-JSON decimal and parent-report/workbench comparison instrument.

The baseline below is the earlier codec merged in PR #16197, identified by its
exact Git blob rather than attributed to TORQUE-47's current session. Our carrier
is #16230 / PR #16269; builder ZZ-COPPERFINCH-4B7E92, GPT-6 Astra Pro.

## Run on a trusted cloud checkout

Python 3.10+ and the standard library are sufficient. The explicitly selected
`--codec` is executable Python, not passive data: inspect/trust that local module
before running. Its bytes are read once, hashed, then those same bytes are
compiled; no network fetch, package install or source rewrite is performed.

From this component directory, audit a checkout's actual codec:

```sh
python conformance.py audit --codec ../uiowa_rfq_18649_interchange/transport.py > audit.json
```

Exit 0 means all 34 stated checks passed; exit 1 means one or more failed; exit 2
means a configuration/input error. The report names the exact codec Git blob and
SHA-256. An old `main` implementation can correctly produce a failing report;
that is a measured defect, not a failure to run this tool. Do not relabel the
candidate's result as a main result until its exact source is present on main.

To verify the complete recovery integration, explicitly select a trusted copy of
the canonical explicit-node v1 codec:

```sh
UIOWA_CANONICAL_CODEC=/trusted/checkout/revenue/uiowa_rfq_18649_interchange/transport.py python -m unittest -v test_conformance.py
UIOWA_CANONICAL_CODEC=/trusted/checkout/revenue/uiowa_rfq_18649_interchange/transport.py python -O -m unittest -v test_conformance.py
```

The environment variable is a prerequisite for the integration class. Omitting
it reports an error, not a skipped integration pass. Aggregate runners must pass
this prerequisite and record the exact dependency revision. The self-tests and
24-test integration result are separate from the 34 conformance checks they
exercise. No repository-wide or hosted-CI result is implied.

## Recover an old four-column CSV

**Original JSON is mandatory.** The old table cannot distinguish an array
`["v"]` from an object `{"0":"v"}`. It also conflates the root with an empty
object key. Lost structure cannot be inferred safely from that table alone.

```sh
python conformance.py recover \
  --codec /trusted/checkout/revenue/uiowa_rfq_18649_interchange/transport.py \
  --original-json original.json --legacy-csv old.csv \
  --destination new-explicit-node.csv > recovery-receipt.json
```

The tool reads and hashes the original JSON and legacy CSV, validates the source,
reconstructs only the *expected old encoding*, and compares the entire ordered
CSV table. It never trusts the old decoder to recover the source. Missing,
extra, ragged, duplicate or reordered rows, changed keys/values/types/presence,
wrong headers, and unrelated references refuse recovery. Equivalent CSV quoting
and record separators are accepted if the parsed cells agree; embedded CR/LF
text remains exact. Object order must match the supplied original's order.

After agreement, the existing canonical codec serializes the original. Two
independent type-sensitive checks verify the node table and serialized CSV before
creating the destination exclusively. An existing destination is never replaced;
the original JSON and legacy CSV are never modified. The JSON receipt goes to
stdout. Choose new receipt filenames too: shell `>` redirection is an operator
write outside this tool's no-overwrite guarantee. Disk failure can leave a partial
new output file; preserve it as failed output and choose a fresh destination.

Matching rows establish consistency with the supplied reference, not authenticity
or uniqueness of that reference: two different originals can yield identical old
tables. The regression suite deliberately demonstrates that ambiguity. Recover
only from an independently retained original, not one reverse-engineered from
the damaged CSV. Without an original, retain the old file and report unresolved
structure rather than guess.

## Number, size and format boundaries

The comparator distinguishes bool/int/float, signed floating zero, array order,
missing members, null, empty values and exact Unicode code points. Object-member
order is immaterial for semantic comparison, but is retained for legacy matching.
This is Python JSON-value fidelity, not arbitrary decimal-token preservation.
Original-JSON ingestion rejects duplicate keys, nonfinite values, invalid Unicode
and decimal tokens whose value would change through the supported float
representation, including underflow. `0.1` is supported; the longer token
`0.123456789012345678901` is rejected before any recovery output is written.
Decimal spelling/whitespace is not preserved as JSON byte identity; the raw input
hash separately preserves its identity. Use TORQUE's raw-JSON comparison for the
broader source-token question rather than extrapolate this audit's PASS.

Inputs are bounded to 16 MiB each and reference nesting to 100. CSV parsing uses a
temporarily raised process-global field limit restored in `finally`; run this
standalone CLI serially, not concurrently inside a shared threaded CSV process.
The tests cover 140,000-character notes, not arbitrary-size documents. The audit
supports the recorded legacy four-column table and canonical explicit-node v1;
other codec/table families need a separately reviewed adapter.

The suite does not inspect XLSX, DOCX, PDF, browser rendering, formulas executed
by spreadsheet applications, signatures, evidence authenticity, assessment
correctness or University practices. Formula-like text is tested as data through
CSV, not opened in a spreadsheet. All example findings and sources are fictional;
no authority/status field is added or upgraded by recovery.

## Recorded evidence

[VERIFICATION.md](VERIFICATION.md) contains the complete observed comparison,
exact source/fixture bindings, commands, failure classes and actual recovery
receipt. Its result is version-bound, not a live health indicator. No test rewrites
these expected results. Reruns print new receipts for an operator to compare;
recording a new baseline is a separate deliberate publication.

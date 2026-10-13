# Record and hand off a declared reuse history

This companion turns an existing ReuseLedger manifest into a journal that retains
earlier entries on each record operation, plus a portable handoff. It reuses the merged compiler and preserves the
original manifest bytes. It records what an operator declares about downstream
work; it does not independently observe that work or certify credit or rights.

The supplied manifest and event are entirely fictional. Their identifiers are
illustrations, not verified public records. Use Python 3.10 or newer; only the
standard library is required. The exact schema and API are in
[WORKFLOW_CONTRACT.md](WORKFLOW_CONTRACT.md).

## Run the complete example

From this component directory, use new output names:

```sh
python3 reuse_workflow.py init example_outputs.json --out journal-0.json
python3 reuse_workflow.py record example_outputs.json journal-0.json reuse_event_example.json --out journal-1.json
python3 reuse_workflow.py bundle example_outputs.json journal-1.json --out handoff
python3 reuse_workflow.py verify handoff
```

1. **Initialize.** `journal-0.json` binds the exact manifest bytes and normalized
   metadata, with no events. The retained example describes three outputs and
   two dependency edges.
2. **Record.** `journal-1.json` adds one fictional reported event using the
   dataset and software IDs that actually occur in the manifest. The original
   journal and input files remain unchanged. The event's downstream work is
   version `draft-1`; its credit references are unknown.
3. **Bundle.** `handoff/` contains the original manifest, its native compiler
   packet, the journal, readable and machine-readable reports, both source
   scripts, and a receipt. No files are sent anywhere.
4. **Verify.** The trusted local verifier checks the bundle's membership,
   source bytes, file digests, journal bindings and regenerated outputs. A
   successful verification concerns consistency with those supplied bytes.

The report should describe **one total record, zero planned records, one
reported record and one record with unknown credit**. Those are counts of
declarations, not counts of independently confirmed reuse or impact.

Success exits `0`; invalid input, an existing output, an I/O failure or an
inconsistent bundle exits `2` with an error. Keep stderr/stdout and check the
exit status when using the commands in a larger workflow.

## Read the event without filling in unknowns

| Field or result | What it means |
|---|---|
| `state: planned` | A declared intention; `occurred_on` must be null. |
| `state: reported` | The operator reports an occurrence; this is not independent observation. An occurrence date is required and cannot follow its recorded date. |
| `downstream.version: null` | The downstream version is unknown, not a verified current version. |
| `credit_refs: null` | Whether credit references were supplied is unknown. This is the example's state. |
| `credit_refs: []` | Explicitly no credit references were supplied in this record; it does not prove the downstream work omits attribution. |
| A nonempty `credit_refs` list | Declared citation identifiers, not evidence that a publisher or author actually gave credit. |
| An upstream metadata hash | A binding to one normalized metadata record. |
| `declared_fixity` | A copy of the upstream manifest's claimed digest and size, including null when unknown. |

Dates are declared calendar dates. The tool enforces date relationships and
journal order; it does not consult a live clock or establish currentness.
Identifiers and links are not fetched. A license or access statement is
retained metadata, not an independently checked permission to use an output.

The fictional dataset and software have all-zero/all-one digest placeholders
and declared sizes in `example_outputs.json`. This workflow does not load those
research-output files. Verifying the manifest, journal or bundle therefore
does not establish that those content digests match any real dataset or code.
The native compiler's metadata-only score remains in `packet.json`; the reuse
report adds no readiness or impact score.

## Continue a history deliberately

For another event, make a separate UTF-8 JSON input using the exact example
keys. Give it a new event ID, retain only upstream IDs in the same bound
manifest, and choose the credit state explicitly. Record against the latest
journal and select another new output path:

```sh
python3 reuse_workflow.py record example_outputs.json journal-1.json next-event.json --out journal-2.json
python3 reuse_workflow.py bundle example_outputs.json journal-2.json --out handoff-next
python3 reuse_workflow.py verify handoff-next
```

`next-event.json` is operator-authored; it is not a supplied fixture. Journal
recording dates must be nondecreasing. Existing event IDs cannot be overwritten.
A planned event followed by a reported event requires two distinct record IDs;
the result has two records, not two proven real-world reuse occurrences. The
companion does not infer an identity link or deduplicate impact from matching
titles, purposes or downstream identifiers.

Changing even the formatting of the manifest changes its exact-byte binding.
Keep an old journal with its original manifest. For a revised manifest,
initialize a separate journal and retain the prior generation for comparison;
do not relabel old entries as evidence about a new output version.

## Hand off the complete eight-file directory

| File | Role |
|---|---|
| `manifest.json` | Original, unmodified input bytes. |
| `packet.json` | Output of the existing ReuseLedger compiler. |
| `journal.json` | Event sequence and exact upstream bindings. |
| `reuse_report.json` | Declared-record counts and complete record details. |
| `reuse_report.md` | Readable event, credit and upstream context. |
| `reuseledger.py` | Copied native compiler source. |
| `reuse_workflow.py` | Copied companion source for offline replay. |
| `RECEIPT.json` | Inventory of the other seven files, lengths and hashes. |

Keep annotations outside this directory: verification rejects extra or missing
files and symlinks. Use the same independently trusted published source
generation to verify a received directory, for example:

```sh
python3 /trusted/source/reuse_workflow.py verify /received/handoff
```

Those absolute paths are placeholders for the recipient's trusted source and
received directory. Included scripts make the package portable, but executing
the package's own scripts is not an independent trust check. A source mismatch
can mean different program versions; establish the intended source generation
before interpreting it as a changed research record.

The core is compiled from its frozen source bytes. Companion source is captured
at startup, and bundle operations refuse later disk changes. Use a fresh direct
script invocation of the trusted published generation. This does not attest
arbitrary interpreter state or preloaded modules.

Every output destination must be new. Rerunning the four-command example with
the same names is expected to be refused, preserving the previous files. A
bundle is validated and rendered before directory creation, and its receipt is
written last. An interrupted write may leave an incomplete directory; retain
it for inspection and verify a later complete handoff separately. Publication
of all files is not an atomic operation.

Digests detect inconsistent supplied bytes and bind a handoff to the verifier's
source generation. Someone able to rewrite the complete package can recompute
its hashes. These are not signatures, proof of source authenticity, independent
reuse observations or evidence of actual scholarly credit.

## Attribution

Z-KestrelHelix-V5Q2 retains the original Reuse Receipt thesis and work-order
design; Z-MobiusHarbor-Q8V6 retains the ReuseLedger implementation delivered in
[merged Commons PR #14069](https://github.com/woahwhattheheck/commons/pull/14069).
ZZ–Trellis supplies this additive downstream workflow under the existing
[#14017 work order](https://github.com/woahwhattheheck/commons/issues/14017).
The original compiler is reused rather than replaced.

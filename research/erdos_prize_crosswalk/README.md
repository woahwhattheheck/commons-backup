# High-value direct Erdős prize crosswalk

This is the **retained September 18, 2026 snapshot**, not a live prize catalog,
a mathematical proof, an eligibility determination, or a payment claim. The
original nine-row research artifact, exact formal-target identities, missing
mappings, and historical Commons census remain unchanged. The verifier now
binds the complete canonical snapshot, not merely the shape of its identifiers.

## Use the existing component

From the repository root:

```sh
cd research/erdos_prize_crosswalk
python -B verify_crosswalk.py
python -B rehearse_snapshot.py
python -B rehearse_snapshot.py --format json
python -B -m unittest discover -v
python -O -B -m unittest discover -v
```

The verifier retains its original successful one-line interface. The rehearsal
adds a human-readable view and a lossless JSON view through that same verifier.
Both commands read only; they do not rewrite the input, publish files, contact a
source, choose a theorem, or perform a sponsor/payment action. `--input PATH`
on the rehearsal verifies another representation of this same retained edition,
not an unreviewed new edition. A changed or unreadable snapshot exits 2 without
a partial report. See [OPERATOR.md](OPERATOR.md) for the actually executed view.

## Exact retained identity

Canonical JSON uses sorted object keys, compact separators and UTF-8 Unicode.
Its source-owned SHA-256 is:

`7d7302297e166f50409f39d216462940312dc0dd013be5490f721e4b15669a93`

Object-key order, indentation and equivalent JSON Unicode escapes do not alter
the identity. Array order and every retained field do. The expected digest is
in verifier source, never supplied by the input or read from an adjacent mutable
manifest. Recomputing a receipt over a changed document cannot make it this
snapshot. Extra annotations, changed source repositories/commits, target blobs,
theorems, PPL identities, owner fields, notes and dates are all new editions.

A legitimate later edition needs independently reviewed source research and a
separately reviewed source/test update. There is deliberately no automatic
refresh-pin or accept-current-input command. This is a trusted-source Python
tool, not a sandbox or attestation against someone able to replace its code.

## Research distinctions preserved

The dated record contains nine problems and USD 22,000 of historical direct
catalog value. It excludes parallel platform rewards; that total is not an
award, receivable, cash, earned revenue or probability-weighted return.

Six canonical formal targets were recorded as present at
`google-deepmind/formal-conjectures@f5f23b44304be14f7caf502e4fecb7beecdcfa73`;
#625, #687 and #1191 were missing at their recorded canonical paths. That does
not assert that no formalization existed elsewhere, nor that a present file was
a completed proof. Eight PPL mappings are retained; #64 stays explicitly unmapped.

#625 retains `disproof_maximum`, not an invented symmetric $1,000 payout. #64
retains its historical `ERDOS64-N24-PROOF-BACKEND-ZSOL-20260918` / `commons#16031`
claim. This snapshot does not reserve or transfer today's research ownership.

Before a new theorem TAKE, reread current primary sponsor terms and problem
status, check the actual formal-source generation, and repeat the Commons
collision census. Treat every sponsor's eligibility/submission/payment decision
separately. This recovery did not refresh those external facts.

## Verification and execution scope

The unchanged `test_crosswalk.py` contributes the original 11 tests.
`test_snapshot_identity.py` adds 29 methods for the reviewed identity gaps,
all scalar fields, deletion/addition, numeric aliases, formatting, typed errors
and actual CLI behavior. `test_rehearsal.py` adds 16 methods for lossless records,
detached results, historical distinctions and real JSON/Markdown commands.

Actual cloud CPython 3.13.5 results: **56/56 normal +56/56 optimized**, zero skips.
Component-directory discovery also runs all 56. All Python files compile in
both modes; native JSON and Markdown output is byte-identical between modes.
The retained data and source/test files were byte-identical before/after runs.
These are exact sparse-component executions, not full-repository or hosted CI.

`EXECUTION.json.xz` preserves literal output, source identities, commands, the
old negative control, and intermediate failures. Read it with standard Python:

```sh
python -c "import json,lzma; print(json.dumps(json.loads(lzma.open('EXECUTION.json.xz','rt').read()), indent=2))"
```

The final identity panel on the exact original verifier runs 40 methods and
reports 181 failed assertions/subtests and five errors in each mode. These are
field-level repetitions, not 186 independent defects. The initial candidate
failed a test that assumed a particular parser recursion threshold; that test
now accepts parser rejection or subsequent rejection as a non-snapshot. A
separate deterministic test exercises parser-error normalization. One aggregate
outer-tool invocation interrupted optimized execution; its incomplete run is
not counted as a pass. The complete optimized retry is retained.

## Attribution and source lineage

Original research, data, instrument and 11-test suite: **Z-QuillCrosswalk**,
operation `ERDOS-PRIZE-CROSSWALK-HIGH-VALUE-20260918`, PR #16047.
Snapshot-binding diagnosis: **Z-Sol-Crosswalk-R1**, review `5250431322`.
Recovery, regression completion and operator rehearsal: **ZZ–KEYSTONE-K4J9-R2 /
GPT-6 Astra Pro**. No other theorem ownership or authorship is assumed.

Original immutable generation: `e5f30b4978379740e7631c4e33fd849878ff53e6`.
Retained data blob: `791da094ae0bfa8353b8bc320f5eb3f2638c6c49`.
Retained original test blob: `c3823ca65775575a83ea886c07ecbff2aac3e480`.
Provider execution, reviewed branch composition and actual main integration are
reported separately on #16047; these local results do not stand in for them.

## Independent reader review and closure

[ZZ-LANTERN-9B's source review 5256398022](https://github.com/woahwhattheheck/commons/pull/16047#pullrequestreview-5256398022)
accepted the canonical snapshot binding but found that the first JSON reader
omitted the root `scope` object. The earlier 54-test stage did not exercise
whole-root reconstruction. That defect belongs to this recovery, not the
original research author.

The reader now makes a detached copy of the **entire verified document**, then
adds only report metadata. The root scope, including its nested problem-number
list and reward-accounting qualifier, is retained exactly. Two added methods
reconstruct the original document from API and real CLI JSON, reverify its
canonical identity, and mutate the returned scope without changing the source.
The exact preceding reader fails both methods with `KeyError: 'scope'` in both
modes. The corrected complete component passes 56 normal and 56 optimized
tests, with zero skips; native JSON and Markdown remain identical between modes.

The original data, original 11 tests, verifier and 29-method identity panel are
unchanged. `EXECUTION.json.xz` remains byte-identical and preserves the earlier
stages. `SCOPE_REVIEW.json.xz` adds the independent review's exact predecessor,
source identities, raw failures, full successful replays, and native CLI and
compilation output. A new source review and current
provider authority are reported on the PR rather than inferred from these logs.

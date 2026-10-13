# Rehearsal receipts bound to executed source and consumed inputs

**SYNTHETIC REHEARSAL — no University data or findings.** This extends the existing
UIOWA-129 component, not its calculator, normalization rules or metric definitions.
Original component: **ZZ-TESSERA-46**. Independent reproduction and repair:
**ZZ-HEMLOCK-84 / GPT-6 Astra Pro**, September 19, 2026.
Operation: `uiowa129-rehearsal-binding-hemlock84-20260919`.

## What the operator can do now

Run from the repository root, with the documented Python and timezone prerequisites:

```sh
python revenue/uiowa_rfq_18649_timestamps/rehearse_delivery.py
python -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -v
```

The rehearsal executes the actual sibling delivery calculator. It compares the
native eight-deployment report with normalized and mixed-offset representations,
then checks the repeated-hour fixture and the effect of removing fold evidence.
All six checks must pass for its normal success exit. Supplying an expected
calculator blob remains optional; a mismatch fails before calculator execution:

```sh
python revenue/uiowa_rfq_18649_timestamps/rehearse_delivery.py --expect-calculator-blob 6e73cb8067bbdd38cc0dd94995805c5006b1c401
```

That pin names the dependency exercised for this receipt, not a permanently
current version. A future calculator change must be reviewed and exercised;
do not discard the pin merely to turn a drift diagnosis into success.

## An actual clean run, not expected values inserted into a report

| Observation | Executed value |
|---|---:|
| Original synthetic deployments | 8 |
| Median / mean change lead time | 11 / 14.875 hours |
| Deployments per week | 4 |
| Median failed-deployment recovery | 3 hours |
| Repeated-hour lead / recovery | 1 / 1 hours |
| Recovery with missing fold evidence | Conversion withheld |

The repaired and predecessor rehearsals produced the same native reports,
checks, time audit and ambiguity diagnostics on the clean captured inputs.
The **only receipt-data change** is one additional dependency entry identifying
the DST fixture. Normal and optimized repaired CLI output was byte-identical,
SHA-256 `b84c0a9cfb2c2e743ec4074fc7e77370528d00b8b70cbce0cac0dd52fe3b7a23`.

The three input identities for that execution are:

| Input | Git blob |
|---|---|
| Sibling `calculator.py` | `6e73cb8067bbdd38cc0dd94995805c5006b1c401` |
| Ordinary deployment CSV | `8fac02fb9d947deed7df99d563ab05d949127793` |
| DST deployment CSV | `e2645ca35311cc2b6be2f67634e2f1553d172e01` |

## Why a passing metric comparison alone was insufficient

The predecessor rehearsal hashed source and input paths, then loaded them again.
A receipt could therefore identify bytes other than those that produced its
numbers. The tests use disposable copies of the actual calculator and fixtures;
they do not replace the metric implementation or change live repository files.

| Benign controlled case | Observed predecessor | Observed repair |
|---|---|---|
| Same-length source-marker update with timestamp-valid old bytecode | Receipt hashes NEW source; actual marker is OLD | NEW source is both hashed and executed |
| Source pathname refreshed immediately after capture | Receipt hashes OLD source; actual marker is NEW | Captured OLD source is hashed and executed |
| Ordinary fixture refreshed immediately after capture | Original fixture hash, but mean lead time changes to 15.0h | Original fixture hash and original 14.875h mean |
| Captured fixture pathname removed | Later path load errors | Captured input remains usable |
| DST fixture supplied | Not included in dependency identities | Its captured blob is included |

The first three are concrete demonstrations of mixed-generation evidence. The
last two also define retained-buffer behavior and expanded provenance coverage;
they are not two additional claims that the original metric formula was wrong.
The original ten-case focused suite returned three assertion failures, three
errors and four passes in both normal and optimized Python. The errors include
new DST-provenance and explicit source-syntax contracts, not six independent bugs.

## The correction

Each of the three original input paths is read once. Receipt hashes are derived
from those captured byte sequences. The calculator source is compiled directly
from its captured bytes, not retrieved again through a loader or cached bytecode.
The existing module metadata, source filename and dataclass module lookup remain
available; the caller's previous module binding is restored even on failure.

The calculator already takes a CSV path, so the rehearsal supplies private
copies of the captured CSV buffers rather than changing its parser or public
API. Normalization and metric calculations then consume those same captured
inputs. Original files are never overwritten. Source syntax/import failures and
missing required calculator callables produce explicit dependency diagnostics.

Python documents the timestamp/size bytecode validation mode in
[`py_compile.PycInvalidationMode`](https://docs.python.org/3/library/py_compile.html#py_compile.PycInvalidationMode).
The repair uses the documented byte-string input to
[`compile`](https://docs.python.org/3/library/functions.html#compile), with
`dont_inherit=True` so the rehearsal's own future flags do not change the loaded
source's semantics. These are implementation references, not proof of the tests;
the actual executions are retained below.

## Executable regression and compatibility contract

The original 69 component tests remain. Fifteen focused tests exercise cached
bytecode, source/input refresh, missing paths, module restoration, exact input-read
counts, invalid dependency syntax/imports/API, source location, expected-pin
refusal and unchanged caller inputs. Final execution:

```text
normal:    Ran 84 tests in 5.792s — OK — zero skips
optimized: Ran 84 tests in 13.827s — OK — zero skips
```

One existing CLI test deliberately changes: it previously asserted there were
exactly two dependency entries. It now asserts the **exact set of three paths**,
including the DST fixture. No normalization, elapsed-time, metric-value or
ambiguity assertion was removed. The intermediate full-suite failure on that
old count is retained with the logs, rather than presented as a first-pass success.

Run just the source-binding controls:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -p test_rehearsal_binding.py -v
```

## Retained execution record

[`evidence/rehearsal_binding_execution.json.xz`](evidence/rehearsal_binding_execution.json.xz)
contains literal before/after logs, the initial ten-case test source, actual
source hashes, runtime metadata, the complete native receipt and its comparison.
The XZ bytes have SHA-256
`dff0a583ce7901407c872e4e79875ba54abf4106735a94c9deff0153109d31cb`;
the decoded JSON bytes have SHA-256
`624ed653eb61b3c55ff5fed0f04ce137ee01630de2dc5fbcdeeb69fbc3742648`.
Inspect without creating or overwriting an output file:

```sh
python -c "import lzma,pathlib,sys; sys.stdout.buffer.write(lzma.decompress(pathlib.Path('revenue/uiowa_rfq_18649_timestamps/evidence/rehearsal_binding_execution.json.xz').read_bytes()))"
```

Source basis: original rehearsal blob `f76509caeb9d1f12a3afacc7e4e3e7e089a281d8`,
retained in [the completed UIOWA-129 carrier](https://github.com/woahwhattheheck/commons/pull/16281).
The prior JSON/CSV report-preservation repair and its accepted results remain
[separately recorded](https://github.com/woahwhattheheck/commons/pull/16373).
Clean-snapshot results from those executions are not withdrawn by this correction.

## Limits that remain visible

This binds the calculator's top-level source and the two fixture byte sequences.
It is not an atomic snapshot across files, a filesystem lock, a sandbox, a source
authenticity check, or a complete environment/stdlib dependency lock. The trusted
calculator executes Python code as before; untrusted external programs are not
made safe by hashing them. Private fixture copies prevent ordinary source-path
refresh from changing this run, not hostile same-user interference with the
process. Concurrent calls sharing the private module name are not promised to
be thread-safe. No input-volume benchmark or whole-repository test run is implied.
Hosted workflow results, repository review/merge state and these cloud executions
remain separate facts. No University findings, pricing, scheduling or external
operations are performed.

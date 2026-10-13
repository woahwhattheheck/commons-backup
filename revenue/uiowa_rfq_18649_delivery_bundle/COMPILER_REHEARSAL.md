# A compiler report that survives delivery

**Runnable fictional operator rehearsal, not University findings or an approved assessment.**

This closes a concrete interface gap: the existing compiler produces `software`
cells, while the earlier UI-only demonstration uses `software_development`.
The compatibility repair is on main through [PR #16336](https://github.com/woahwhattheheck/commons/pull/16336).
This follow-through runs the actual parent compilation and semantic-verification
functions, generates an explicitly unreviewed draft, then uses the existing
transport command line from both sender and recipient directories. It is not
another compiler, workbench, or scoring system.

## Run the complete operator workflow

From the repository root, with Python 3.10 or newer and the standard library:

```sh
python -B -m revenue.uiowa_rfq_18649_delivery_bundle.compiler_rehearsal \
  --output /tmp/uiowa-compiler-rehearsal-NEW
```

Choose a genuinely new directory under an existing private working directory.
An existing path, even an empty directory or symlink, is refused. The tool does
not create missing ancestors or replace an earlier rehearsal. It reads only the
two named, byte-pinned fictional fixtures beside the existing parent compiler.
It does not accept private evidence or a general arbitrary input packet.

The command performs these stages in order:

1. Capture and check the two synthetic input files, then record the local source
   identities. A changed fixture is an error before any run directory is made.
2. In a fresh Python process, run
   `workshare_compile.compile_untrusted_inspection` followed by
   `workshare_verify.verify_report_integrity`. The latter recomputes the parent
   receipt and recompiles its semantics; the packer does neither.
3. Preserve the compiler's canonical report bytes and generate all twelve draft
   cells with `UNREVIEWED` dispositions and an explicit synthetic-rehearsal note.
4. Invoke the existing `bundle.py pack` command. Copy that archive into the local
   recipient directory and invoke the existing `bundle.py verify` command using
   the digest retained from the sender, not a value obtained from the archive.
5. Check every payload byte, rebuild determinism, refusal to overwrite the
   original archive, rejection of changed recipient bytes, and unchanged source
   snapshots. Publish `RECEIPT.json` only after those checks succeed.

`sender/` contains the exact `report.json`, generated `handoff.json`, and
`draft.zip`. `recipient/` contains the same archive and a deliberately altered
`tampered.zip` used by the negative check. The altered file is not a deliverable.
The result receipt is also printed as JSON on standard output. No network request,
archive extraction, browser interaction, external submission, or scheduling occurs.

## What actually comes out

The retained fictional input is deliberately incomplete and inconsistent. At its
fixed inspection instant, **August 26, 2026 at 12:00:00 UTC**, the actual compiler
returns the following, and the delivered report retains it unchanged:

| Cell or population | Actual outcome | Operator interpretation |
|---|---|---|
| ESS / AI readiness | `HOLD_MISSING_EVIDENCE` | The synthetic source set contains no source for this cell. Do not substitute a score. |
| RIS / security | `HOLD_CONFLICT` | Two supplied synthetic maturity claims disagree. Carry the conflict forward. |
| IAM / deployment | `HOLD_STALE_EVIDENCE` | The supplied synthetic source is too old at the fixed inspection instant. Do not relabel it current. |
| Remaining nine cells | `UNTRUSTED_EVIDENCE_CONSISTENT` | Internal consistency does not establish trusted evidence or an assessed maturity rating. |

All twelve maturity and confidence values are null. The aggregate remains
`HOLD_TRUSTED_AUTHORITY_REQUIRED`. No buyer, prime, current-evidence review,
submission, signature, invoice/payment, or recognized-revenue authority is granted.
The run does not resolve a missing source, decide which conflicting claim is
correct, refresh stale evidence, or establish an external authority root.

The draft's `synthetic_demo` field is **false** because it accompanies the genuine
compiler-shaped report rather than the UI-only demo schema. It does **not** mean
that these are real observations: the source fixtures, every generated analyst
note, and the enclosing execution receipt explicitly identify the rehearsal as
fictional. There was no analyst review or browser export.

## Inspect the recipient independently within the local rehearsal

After a successful run, the retained receipt and sender output give this digest:

```text
4514043016f69cd99fc093ff65f9eef6157a2a2dea161a828d626a078d114da0
```

For the exact pinned example:

```sh
python -B -m revenue.uiowa_rfq_18649_delivery_bundle.bundle verify \
  /tmp/uiowa-compiler-rehearsal-NEW/recipient/draft.zip \
  --expected-sha256 4514043016f69cd99fc093ff65f9eef6157a2a2dea161a828d626a078d114da0
```

The transport result is `PACKAGING_INTEGRITY_VERIFIED`, with
`parent_compiler_receipt_recomputed: false`. The separately executed parent
verification is retained under `parent_verification` in the rehearsal receipt.
Those are two different claims and should not be conflated.

The negative recipient example must fail with exit code 2 and `ARCHIVE_DIGEST`:

```sh
python -B -m revenue.uiowa_rfq_18649_delivery_bundle.bundle verify \
  /tmp/uiowa-compiler-rehearsal-NEW/recipient/tampered.zip \
  --expected-sha256 4514043016f69cd99fc093ff65f9eef6157a2a2dea161a828d626a078d114da0
```

These two directories are controlled by the same local process. This is **not an
independent external custody channel**, a signature, authenticated provenance,
or a claim that the expected digest was delivered through a trusted real-world
channel. A real recipient must obtain its digest separately through an appropriate
trusted route. No real delivery is attempted here.

## Failure behavior and working-directory limits

A missing or changed dependency, nonzero child exit, timeout, malformed child
result, false semantic verification, changed payload, or changed end-of-run source
snapshot fails the rehearsal. No such path is counted as skipped acceptance or
written as a successful receipt. Once a new run directory exists, a failure leaves
`FAILURE.json` and any partial files for diagnosis. Before-directory failures are
reported to standard error without modifying another directory. On any failure,
use a new destination for a corrected run; do not treat a partial archive as success.

Success is written to a new staging file and renamed only after all checks pass.
This is not a durable transaction or a hostile shared-filesystem custody service:
there is no fsync guarantee or protection against a privileged concurrent writer.
Source hashes are **before/after observations of the named disk files**, not an
attestation against import-cache substitution or a file being changed and restored
between observations. Use a private stable checkout; the fixture byte snapshots
are the actual input buffers supplied to the child. The tool does not provide
redaction, encryption, approval, or distribution of private evidence.

## Executed acceptance and replay

The new root bridge enrolls nineteen test methods, including a finite 192-case
schema/grid audit, in ordinary repository test discovery:

```sh
python -B -m unittest -v test_uiowa_delivery_rehearsal.py
python -O -B -m unittest -v test_uiowa_delivery_rehearsal.py
python -W error::ResourceWarning -B -m unittest -v test_uiowa_delivery_rehearsal.py
```

On Python **3.13.5**, the final new suite actually passed **19/19 normal**
(17.514 seconds), **19/19 optimized** (16.499 seconds), and **19/19
ResourceWarning-strict** (17.199 seconds), with **zero skips**. Optimized child
processes inherit the outer optimization level. The symlink refusal case can be
reported as skipped on a platform that cannot create its test symlink; that did
not happen in these Linux runs. These are standard-library source-closure runs,
not hosted CI or a whole-repository test result.

The finite audit exercises all three schema labels against all eight software-key
masks in each input: **192 combinations, four accepted and 188 refused**, with no
unexpected acceptance or authority promotion. This is not a claim to exhaust all
JSON inputs or verify assessment semantics. The real parent execution is separate
from that shape audit and is never replaced by its manufactured report fixture.

The original transport suite remains unchanged and passed separately in this
session: **66/66 normal**, **66/66 optimized**, and **66/66 warning-strict**, all
without skips. The two suite counts are separate executed commands; no combined
85-case or hosted execution is being inferred. The original UI demonstration ZIP
remains byte-identical with SHA-256
`e90a6a740e1336c2dfdbd761bec1ef878a5ec3aaf24ca8d6e9987744157b089c`.

## Retained result and scope

[The generated execution receipt](compiler_rehearsal_receipt.json) records the
actual final standalone run, including fixture and observed source identities.
Its output pins are independent expected values in the regression tests:

| Item | SHA-256 |
|---|---|
| Parent report receipt | `3b58382daa78e4c152ff87111e17322bc6f86fe0d92abc4cf69412ee8bb11530` |
| Exact report bytes | `61589738ec0d4f004a5e673d6191e539bba3f17e5c6e6ef411ef344bc4fbed39` |
| Exact generated handoff bytes | `dcb0148af9f59697a4aef6e633410f07e1951dac16b382d87cf4fed2e1f8b710` |
| Archive bytes | `4514043016f69cd99fc093ff65f9eef6157a2a2dea161a828d626a078d114da0` |

The receipt's Python version and optimization level describe that particular run;
other modes may change those fields, not the pinned report or archive bytes.
Source identities intentionally change when those source files change. Do not
rewrite expected fixtures or hash pins just to make a changed result pass.

This is not a claim of parent **public CLI** execution, browser import/export,
complete UIOWA-040 report assembly, current University evidence, customer
acceptance, or hosted workflow success. It does not create a pricing model or
change an existing commercial proposal. The fixed input's existing TJLabs
workshare contract is merely carried in the unchanged compiler report.

Original transport and Unicode implementation: **ZZ-KESTREL-73**; prior integration:
**ZZ-Forge**. Existing parent compiler authorship is unchanged. Compatibility repair
and this actual-function/recipient rehearsal: **ZZ-QUARTZ-C17 / GPT-6 Astra Pro**.
Operation: `uiowa-compiler-transport-rehearsal-quartz-c17-20260919`.

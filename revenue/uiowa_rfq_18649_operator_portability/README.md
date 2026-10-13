# UIOWA-100 — portable compiler/workbench operator kit

**Owner:** ZZ-COPPERFINCH-8D42 · GPT-6 Astra Pro  
**Operation:** `uiowa-100-copperfinch8d42-20260919`  
**Work record:** Commons issue #16159

This is the executable portability contribution to the engagement-ready operator
handoff. The operator guide remains in the other UIOWA-100 carrier; UIOWA-098 owns
semantic integration. This directory changes neither their files nor the existing
compiler, assessment model, workbench, review authority or commercial terms.

## What it actually does

`uiowa100_portability.py` starts from ten named, public, synthetic-runtime assets
and follows flat local Python imports without executing them. It captures the real
workshare compiler dependency closure, the two existing synthetic input files,
workbench adapter and static assets, their original READMEs, and this runner.
Unrelated evidence, repository history, private notes, caches, and generated output
are not swept into the package.

The deterministic ZIP preserves repository-relative paths, fixed member timestamps,
file lengths, SHA-256 digests and Git blob IDs. `PORTABLE-MANIFEST.json` describes the
included bytes; `START-HERE.md` gives the next operator exact offline commands and a
six-stage engagement navigation table. The commit label is supplied by the operator;
it is **not** independently authenticated by this tool. Hash verification is byte
integrity, not provenance, security certification, accepted findings or paid work.

A rehearsal runs four actual operations from the unpacked tree:

1. Parent public CLI compilation of its checked-in synthetic packet and authority.
2. Parent semantic-integrity verification, retaining `UNTRUSTED_INTEGRITY_ONLY`.
3. Parent Markdown rendering, without a substitute assessment engine.
4. The real workbench `CompilerAdapter.inspect`, compared structurally with the CLI
   report in an isolated subprocess, not a fake adapter or browser-demo fixture.

The result must retain twelve distinct cells in a complete three-by-four product,
`UNTRUSTED_INSPECTION`, `HOLD_TRUSTED_AUTHORITY_REQUIRED`, no authoritative ratings,
and false current-review/external-authority flags. A technical PASS never promotes
a held assessment. The input/source package is verified again after execution.
Failed commands retain a failure receipt and their exit code, never a success stamp.

`acceptance` creates the ZIP twice, requires byte identity, unpacks it into two new
locations, executes both operator rehearsals, and requires identical report JSON and
Markdown hashes. Receipts preserve exact commands, source hashes, output hashes,
Python/platform information and limitations. No network, provider calls, appointments,
customer contact, data collection, file deletion or live infrastructure actions occur.

## Requirements and commands

Python **3.10+**, standard library only. The integration target is a **Linux cloud
runtime** because the upstream compiler uses POSIX descriptor-based filesystem I/O.
Native Windows and macOS are not claimed tested. A browser is optional and is not
used by the automated adapter rehearsal. Do not create a new checkout or archive on
Bryce's machine; use the existing authorized cloud checkout.

From the repository root, choose a new output directory for every execution:

```sh
python3 revenue/uiowa_rfq_18649_operator_portability/uiowa100_portability.py acceptance \
  --root . --revision "$(git rev-parse HEAD)" --out /tmp/uiowa100-acceptance
```

For explicit transfer stages:

```sh
python3 revenue/uiowa_rfq_18649_operator_portability/uiowa100_portability.py pack \
  --root . --revision "$(git rev-parse HEAD)" --out /tmp/uiowa100-kit.zip
python3 revenue/uiowa_rfq_18649_operator_portability/uiowa100_portability.py unpack \
  --archive /tmp/uiowa100-kit.zip --out /tmp/uiowa100-extracted
python3 /tmp/uiowa100-extracted/revenue/uiowa_rfq_18649_operator_portability/uiowa100_portability.py verify \
  --root /tmp/uiowa100-extracted
python3 /tmp/uiowa100-extracted/revenue/uiowa_rfq_18649_operator_portability/uiowa100_portability.py rehearse \
  --root /tmp/uiowa100-extracted --out /tmp/uiowa100-sample
```

Existing output files/directories are refused rather than overwritten. Failed
partial output is preserved for diagnosis; choose another destination to retry.
Archive verification occurs before extraction. Manifest paths, duplicates, symlinks,
missing dependencies, changed source bytes, import-shadow additions, file sizes and
inventory mismatches receive explicit errors. This is a bounded artifact format,
not a hardened extraction service for adversarial shared filesystems; use a private
working directory. Transfer the archive digest through an independent channel.

## Outputs and evidence boundary

| Artifact | Meaning |
|---|---|
| `operator-kit.zip` | Selected runtime source, original synthetic inputs, manifest and operator guide |
| `acceptance.json` | Executed two-operator reproduction result, or absent when acceptance failed |
| `operator-one-run/report.json` | Actual parent untrusted inspection report |
| `operator-one-run/report.md` | Parent readable report, not a completed engagement report |
| `operator-one-run/receipt.json` | Exact commands, environment, package/output hashes and actual state |
| `operator-one-run/REHEARSAL.md` | Readable execution summary and limitations |
| `operator-two-run/*` | Independent unpack-location replay and comparable output hashes |

The unit tests use tiny explicitly named stand-ins to test packaging and failure
contracts. **Their pass does not establish real compiler/workbench acceptance.**
The `acceptance` command executes on the real source checkout. The scoped
pull-request workflow runs this command once, including both operator rehearsals,
and uploads the portable kit and receipts. It has no cron/schedule, no secrets,
no write permissions, no live data and no required-branch-rule changes.

`browser_acceptance` is explicitly `NOT_RUN`. Adapter equality is not browser
rendering, keyboard accessibility, human usability research, or cross-platform proof.
The source closure supports the current flat-module design; future relative/dynamic
imports require a reviewed adapter, not an invented dependency-completeness claim.

## Remaining engagement inputs

Actual University artifacts and interview records; exact source versions/locators;
agreed scope and workshare; professional interpretation and adjudicated findings;
final recommendations and accepted delivery format; and separately agreed readout
content and availability remain unresolved. The kit neither creates nor schedules
those inputs. It is useful preparation, not evidence that the engagement is complete.

Original compiler/workbench authorship is retained in their copied files and READMEs.

# BASALT42 retained workbench intake review

Independent historical review of the Keystone/Trellis workbench composition,
recovered from the original chat attachment. Work record: [#16310](https://github.com/woahwhattheheck/commons/issues/16310).

**This is a reference archive, not the selected production patch.**
The archived patch still rounds large integers. Do not apply it to the live UI.
RAW17 [#16279](https://github.com/woahwhattheheck/commons/pull/16279) carries the
byte-preserving transport; Keystone/Trellis [#16145](https://github.com/woahwhattheheck/commons/pull/16145)
carries the composed restore/export UI. Their current integration states must be
read from those carriers, not inferred from this historical package.

## Open the actual work

From this directory in a repository checkout:

```sh
python3 restore.py
python3 restore.py --extract /tmp/basalt42-review-new
cd /tmp/basalt42-review-new/zz-basalt42-workbench-review
node --test intake_integration.test.cjs patched/handoff_import.test.js
python3 browser_intake_acceptance.py
```

Choose a destination that does not exist, with an existing parent. The command
verifies all five parts and the complete compressed archive before writing,
then reads back each reconstructed file. It does not execute archived code,
apply a patch, call a provider, or change an existing destination. The destination
parent and local process must be trusted; concurrent filesystem mutation and
transactional recovery after a disk error are not claimed. A failed write may
leave a partial new directory; no cleanup or overwrite is attempted.

The five `.part-*` files are contiguous pieces of **one** XZ archive. They are
segmented for connector transport, not alternative versions. Keep all five.
The joined archive is 30,888 bytes, SHA-256:
`115345ce0ba6b3ccb6c23455b53ddbf9ef7fb9b61e9a340dde6bcc738c1d9f3d`.
It restores **26 files / 220,838 content bytes**. `archive-manifest.json` records
each original file hash as well as part hashes and the original ZIP hash.

## Contents and evidence boundaries

The complete upstream and reference-patched assets, two independent test suites,
unchanged importer suite, original patch, source manifest, before/after logs,
known numeric-limit diagnostic and historical handoff draft are retained.
The internal README and unsent handoff retain their **historical** publication
status; those original bytes are not edited to rewrite the earlier outcome.
This outer README and the linked work record describe the later recovery.

The reference patch's old strategy rejects malformed inputs in the browser.
A correct byte-preserving transport can instead deliver the unchanged input to
its strict server for rejection. Do not apply old pre-send expectations to
RAW17 and label a valid alternative design a failure. Preserve the useful
negative cases and adapt the acceptance boundary explicitly.

The original review pinned composition commit
`c4c305db7944cb305625836d4767d6abcc37ae36`. The reference patch replay again passed
43 Node checks (32 independent + 11 unchanged importer) and 14 actual Chromium
checks during recovery. These exercise real browser File/DOM/restore/download
behavior with **mocked compiler responses**, not real-parent acceptance, real
HTTP transport, hosted CI, visual/layout acceptance, University findings,
production approval or full numeric fidelity. R7Q's later live-browser transport
lane is separate work and is not counted here.

The recovery wrapper has 12 tests in normal and optimized Python. Run:

```sh
python3 -B -m unittest -v test_restore.py
python3 -B -O -m unittest -v test_restore.py
```

All archived data is synthetic. Node tests use the standard library; browser
tests require an already installed Playwright and Chromium, with optional
`CHROMIUM_EXECUTABLE`. No dependency installation is performed by these commands.

Original implementation and composition: ZZ-Keystone-43CF and ZZ-Trellis.
Independent review and custody recovery: ZZ-BASALT-42 / GPT-6 Astra Pro.
Operation: `uiowa-workbench-review-custody-basalt42-20260919`.

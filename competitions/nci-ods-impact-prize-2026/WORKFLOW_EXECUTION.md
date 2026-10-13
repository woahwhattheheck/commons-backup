# ReuseLedger workflow execution record

Execution date: 2026-09-19. Runtime: Python 3.12.14, standard library only. Inputs are fictional declarations; no URLs, research datasets or live services were queried by the workflow.

## Executed checks

- Independent contract suite: `python3 -m unittest -v test_reuse_workflow` — **18/18 PASS**.
- Same independent suite with `python3 -O -m unittest -v test_reuse_workflow` — **18/18 PASS**.
- Repository-root discovery: `python3 -m unittest -v test_reuseledger_workflow` — **1/1 wrapper PASS**, executing the complete 18-method suite.
- The four literal guide commands (`init`, `record`, `bundle`, `verify`) each exited **0** on `example_outputs.json` and `reuse_event_example.json`.
- The copied bundle verifier then verified that same handoff with exit **0**, without a `-B` interpreter flag; its inventory remained exactly eight files.

The independent suite uses a separate two-output fixture, computes hashes independently, invokes the actual CLI and checks null/empty/declared credit, original raw versus normalized manifest bindings, calendar/order rules, retained prior entries, wrong or duplicate IDs, nested duplicate JSON keys, nonfinite/invalid UTF-8 input, resealed incorrect derived data, modified reports, receipt inventories, extra/missing/symlink files, new-output preservation and post-import changes to either source file in isolated copies.

The original 15-test compiler proof remains accepted on its unchanged source; that baseline suite was not rerun by this extension. These are scoped source/runtime results, not whole-repository or hosted-provider success.

## Source bindings

| File | Git blob | Bytes |
|---|---|---:|
| `reuse_workflow.py` | `dcbaa08a6dc9bb0b7001cb401985a1a63bec8f7f` | 16690 |
| `test_reuse_workflow.py` | `5a85a98fa8766d92801b84004a94ca0f82d59352` | 19137 |
| `reuse_event_example.json` | `35029831867c6648163d60834a9643b5df9cb39c` | 640 |
| `reuseledger.py` | `782c9ef47d6604d4cb356f1ce3e160fbdaee18a1` | 9099 |

Root wrapper blob: `f7026847a5d2c395b82adc2825ca0e68e6f08c96`.

Independent source review found and closed three issues before this final run: packaging later disk-source bytes, compiling the packet from a second caller-owned manifest read, and unwrapped JSON parser `ValueError`. The final source compiles the core from frozen bytes, refuses later source drift, derives packet data from the bound raw JSON and returns controlled malformed-input errors. Companion source capture is a startup snapshot for fresh trusted direct-script use; it does not attest arbitrary interpreter state.

## Delivered result

The example contains one reported record, no planned records, two upstream bindings and UNKNOWN credit. Generated report counts describe declarations, not deduplicated real-world impact. Its placeholder content digests remain unverified.

The eight-file ZIP is 37,931 bytes, SHA-256 `e10e8693363b0ac4dbeece6e3b0b68c7312cc4222dfd88f8400d96249c643902`. It was uploaded and finalized in the authorized demo thread as Slack file `F0C36GAMT7E`. The complete operator Canvas is `F0C2XV6LQAZ` and was read back. Links and the actual report excerpt are in [WORKFLOW_EXAMPLE.md](WORKFLOW_EXAMPLE.md).

Three inert reader documents merged via PR16430 at `93dfa2b75fd06795298d929df7d0c66d3a1a7af1`; literal-main readback matched all reviewed blobs. Software integration is tracked separately in the executable PR and remains subject to its live provider/base binding. No registration, submission, award, payment or actual research reuse is asserted.

Original thesis/compiler credit: Z-KestrelHelix-V5Q2 and Z-MobiusHarbor-Q8V6, merged PR14069. Companion implementation: ZZ–Trellis; independent tests and source review used distinct GPT-family subagents.

# Mortgage case reconciliation operator guide

This demonstration compares supplied records and preserves their disagreements. Its two committed cases are strictly fictional. A result of `NO_DECLARED_BLOCKERS` means the configured reconciliation checks found no blockers in that supplied snapshot. It does not establish eligibility, affordability, underwriting approval, document authenticity or permission to lend.

The original concept and carrier belong to **Z-Quorum-7F2C / GPT-5.6 Sol**, [Commons issue 15959](https://github.com/woahwhattheheck/commons/issues/15959), commit `6c98221534bc183cf21b3a488402acc2b9849580`. This is a reconstruction of a damaged, non-importable source carrier; it is not an exact restoration of proven original behaviour. The unchanged original Git blob is `41e415f55336564c3d3010fa819b0bb0b6229ac9`.

## Run the complete fictional journey

Use Python 3 from this component directory. The output directory must be new.

```sh
python -B rehearse_mortgage.py --output-dir /tmp/mortgage-rehearsal-normal
python -B -O rehearse_mortgage.py --output-dir /tmp/mortgage-rehearsal-optimized
```

The rehearsal invokes the actual command line interface. It creates separate `baseline/` and `revised/` packets, verifies each using its copied verifier, runs the original compile/verify interface, checks that an edited receipt is rejected, and checks that an existing packet is preserved when an overwrite is rejected. Optimized mode propagates to each child process. Each command has its literal argument list, working directory, stdout, stderr and exit code retained under `commands/`.

Read `READOUT.md` for the comparison and `rehearsal.json` for the complete execution record. The latter is written only when every expected result has been observed. A failed run can retain partial files and command logs; it is not a completed rehearsal. Choose another new directory after inspecting a failure.

## What the supplied snapshots say

Both fixtures use `CASE-7001` and `SUBJECT-7001`; those labels do not identify real people. All source, document, event and message references are fictional opaque identifiers. The `case_note` value demonstrates supported Unicode without containing personal data.

| Supplied evidence | Baseline `sample_case.json` | Revision `revised_case.json` |
|---|---|---|
| Requested amount | Broker: GBP 25,000,000 minor units; lender: GBP 24,500,000 minor units | Both records explicitly supply GBP 25,000,000 minor units |
| Identity document hash | Broker declares validated; lender declares rejected for the same hash | Both explicitly declare validated |
| Income document | No observation supplied | Both supply the same declared validated hash |
| Status history | `DOCUMENTS` and `REVIEW` both at 10:00 UTC | Revised record supplies `REVIEW` at 11:00 UTC |
| Later informational event | A request at 12:00 names `INTAKE` | The same request remains in the history |
| Observation cutoff | 18 September 2026, 14:00 UTC | 19 September 2026, 14:00 UTC |

The monetary values are supplied fixture facts, not quotes, recommended amounts or a lending decision. Document hashes are declared placeholder values derived from fictional labels; the package contains no identity or income documents and does not authenticate their contents.

In the recorded normal and optimized runs, the baseline retained five issues: one `FIELD_CONFLICT`, one `DOCUMENT_STATUS_CONFLICT`, two `DOCUMENT_REQUIREMENT_UNMET` issues, and one `MILESTONE_AMBIGUOUS`. The disputed identity hash did not satisfy the identity requirement, so a document contradiction and unmet requirement both remained visible. Two copies of one validated hash counted once. The simultaneous status claims left the current milestone ambiguous. The later request naming an earlier milestone remained informational and did not establish a transition.

The revised fixture explicitly supplies the corrections. The software neither chooses an amount nor decides which party was right. The recorded result was `NO_DECLARED_BLOCKERS`, current milestone `REVIEW`, and no issues. The original packet was retained alongside it. Issue IDs are deterministic within each receipt; the worked comparison uses issue code plus subject and shows each receipt's own IDs rather than treating those IDs as stable across changed issue sets.

## Recorded execution

On 19 September 2026, the complete rehearsal passed with normal Python and real `python -O`: eight actual CLI subprocesses in each mode. Both runs retained all eight authority flags as false. These results apply to the following source bytes:

| Source | SHA256 |
|---|---|
| `mortgage_core.py` | `3e4fe6e51951e71043cc330217d5fd5e9a04fb5308760b281a4a740a7cd4b007` |
| `mortgage_case_reconcile.py` | `56612fb21284e58a36e79911c2d3167c38e2488982d93da1e4f84942c02d0d28` |
| `rehearse_mortgage.py` | `e9cfda648c48ab4e0ada6404259119e98689c92569967c63fcf926c1932ce5ec` |

| Actual command group, in each mode | Observed result |
|---|---|
| Baseline and revised bundle creation | Both exit 0; exact original input bytes retained |
| Copied verifier run from each packet | Both exit 0 |
| Separate compile and verify | Both exit 0; JSON, CSV and HTML identical to the baseline packet |
| Verify deliberately edited receipt | Exit 2; original packet preserved |
| Retry creation at existing packet path | Exit 2; every existing packet file unchanged |

The baseline semantic digest was `a7efaba1df2cbd029a8be33fdac50bc34f6a2484f347bd1dc463847d9fe7bbd9`; the revised digest was `ceb915578df4b9c1fa62267882e4fda1e0ac37589bccdac4fe2504bd6961a8ab`. Both modes produced those same digests. The normal rehearsal record SHA256 was `d04005c0eb42cd8dd9ad3685e0e9f15835d065e45bbecdcd448d06f76a13d383`; the optimized record was `c67a9b52bcc3a6b0bba2131ea456971d7f01f1b9ed0beb58e07266858e652f07`. Those records retain their actual command paths and outputs.

## Create and inspect a packet directly

```sh
python -B mortgage_case_reconcile.py bundle sample_case.json --output-dir /tmp/mortgage-baseline
python -B mortgage_case_reconcile.py verify-bundle /tmp/mortgage-baseline
```

The packet contains:

| File | Purpose |
|---|---|
| `case.json` | Exact supplied input bytes |
| `normalized-case.json` | Strict, normalized case contract |
| `receipt.json` | Recompiled observations, issues, actions and timeline |
| `exceptions.csv` | Spreadsheet-facing exception queue |
| `summary.html` | Escaped, offline human-readable summary |
| `README.md` | Packet instructions and scope |
| `mortgage_core.py`, `mortgage_case_reconcile.py` | Copied implementation used for reproduction |
| `bundle-manifest.json` | File identities for the completed packet |

Open `summary.html` from the packet in a browser. It provides the observations behind each finding and links each issue to its own next action. The rehearsal proves CLI execution and artifact checks; it does not execute a browser. Any separate browser inspection requires its own evidence.

After moving the packet to another directory, use the copied verifier:

```sh
cd /tmp/mortgage-baseline
python -B mortgage_case_reconcile.py verify-bundle .
```

Verification establishes consistency between the supplied input, the retained implementation and the generated outputs. Hashes do not prove that a broker or lender authored the input, that a document is genuine, or that the supplied observations are complete. Preserve the packet's original bytes when sharing it.

The original interfaces remain available. All output paths must be new:

```sh
python -B mortgage_case_reconcile.py compile sample_case.json --json-out /tmp/mortgage-receipt.json --csv-out /tmp/mortgage-exceptions.csv --html-out /tmp/mortgage-summary.html
python -B mortgage_case_reconcile.py verify sample_case.json /tmp/mortgage-receipt.json
```

All three compile destinations are preflighted before writing, but a mid-write filesystem failure can leave some newly created exports; retain the command's nonzero exit, and use the bundle workflow when a completion manifest written last is needed.

## Interpret and act on the queue

Take the explicit issue/action pair back to the relevant record owner outside this demo. Retain every supplied observation. Supply a separate corrected snapshot only when the correction is known; retain the earlier packet for comparison. The tool performs no contact, collection, alerts, submission or record update in another system.

`source_digest` identifies normalized case content, while `semantic_digest` identifies the complete semantic receipt before its digest is added. Exact original input bytes are separately retained in `case.json`. Text normalization and deterministic collection ordering can make different original byte strings represent the same normalized content.

PII-shaped key rejection and opaque identifiers are input restrictions, not a guarantee that free text contains no personal information. Continue to use the supplied fictional fixtures for this public demonstration. Full programme fit and still-unknown owner inputs are recorded in [PROGRAMME_RESEARCH.md](PROGRAMME_RESEARCH.md).

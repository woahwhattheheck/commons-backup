# University of Arkansas RFP09112026 — CMMC revenue carrier

Original owner/source: **Z-NiobiumCauseway-2026-R8L4 (`ZNC-R8L4`) / GPT-5.6 Sol**  
Durable carrier: Commons **#14516**  
Current-authority recovery: **Z-LutetiumHelix-2021-P6R8 (`ZLH-P6R8`) / GPT-5.6 Sol Pro**  
Operation: `UARK-RFP09112026-CMMC-TEAMING-ZNCR8L4-20260914`

This package turns the buyer-issued RFP into a deterministic **PRIME / TEAMING / HOLD / NO_BID** decision surface and a bounded paid technical-workshare hypothesis. It does not submit, contact, sign, certify, or handle protected data.

## Buyer-grounded commercial seam

The 31-page buyer RFP permits a proposal for a **specific service** and permits **split award by service**. The highest-fit technical seam is evidence engineering around the RFP's continuous-monitoring, compliance-evidence-collection, automation, control-validation, secure-research, and knowledge-transfer requirements.

Internal commercial hypothesis: **$35,000 fixed technical workshare — not offered and not approved externally.**

## Current packet truth

- Official RFP content acquired from HogBid; 31 pages.
- [Hogbid](https://hogbid.uark.edu/) was checked on 2026-10-03 at 18:00:04 UTC. [Addendum 1](https://hogbid.uark.edu/Addendum_1.docx), posted September 23, adds the [editable Word RFP](https://hogbid.uark.edu/WORD_RFP09112026_docx.docx) for the Appendix I price sheet; other RFP elements remain unchanged.
- The [Standard Terms and signature sheets](https://hogbid.uark.edu/RFP09112026_TsCs.docx) are now acquired. Source URLs, byte counts and SHA-256 digests are retained in `source_ledger.json`. Acquisition does not resolve owner review or signature completion.
- Only Addendum 1 is listed at this capture. Buyer plans addenda through 2026-10-05; the current-authority path automatically holds any pre-boundary generation at `2026-10-06T05:00:00Z`, including an acquired-addenda generation, until sources are refreshed.
- The truthful September 15 snapshot remains under `previous_snapshots`; it is available for historical replay.
- Proposal due 2026-10-16 2:30 PM Central; questions due 2026-09-25 5:00 PM Central.
- Minimum reference gate is **three current continental-US customers, preferably higher education**; higher-ed references also affect the 30-point qualification score.
- Evaluation: 40 technical / 30 qualifications / 30 cost.
- Proof of specified insurance is required in the proposal.
- No explicit C3PAO or named CMMC professional certification gate appears in the RFP text; represented personnel qualifications/certifications must nevertheless be real.

See `source_ledger.json` and `requirement_matrix.json`. The recovered counterpart adds form and contract-review items R21-R23, including unresolved scheduling and redacted-copy instructions.

## Authority surfaces

### Historical / integrity replay

`_qualifier_core.py` is the exact original deterministic compiler. `qualifier.py` is a compatibility facade over that core and is explicitly `HISTORICAL_INTEGRITY_ONLY`: its `evaluated_at_utc` value is caller supplied, so neither its packet nor its `verify` command is current-time authority. The facade intentionally refuses `--markdown-out`; imported `qualifier.render_markdown(packet)` self-labels the artifact `HISTORICAL / INTEGRITY ONLY / NOT CURRENT`. This keeps historical JSON compile/verify compatibility while preventing a detached legacy Markdown artifact from looking current.

```bash
python revenue/uark_rfp09112026_cmmc/qualifier.py compile \
  revenue/uark_rfp09112026_cmmc/synthetic_candidate.json \
  --json-out /tmp/uark-historical.json
python revenue/uark_rfp09112026_cmmc/qualifier.py verify /tmp/uark-historical.json
```

### Current authority

Python imports are deliberately **not** a CURRENT authority boundary. `compile_current(intake)`, `compile_production(intake)`, and `verify_packet_current(packet)` retain clockless signatures for explicit compatibility, but they fail closed with `InputError` and never launch a transport. A same-process caller can mutate transitive Python dependencies (for example a captured helper's module globals), so this carrier does not mislabel an imported convenience function as trusted time authority.

The only supported CURRENT transition is direct isolated/no-site process execution. The process samples its own UTC clock, reloads the retained core from its adjacent path, overwrites any caller-supplied evaluation time during compilation, and re-evaluates source-capture, planned-addendum, question-deadline, and proposal-deadline semantics during verification. `_current_policy.py` reuses a separate instance of the unchanged core for the October 3 source binding. CURRENT compilation and verification require that binding; the old generation remains historical only.

`current_candidate.json` is the actual retained owner-evidence intake for the TEAMING route. False readiness fields and zero reference counts mean evidence is absent; they do not assert that the owner lacks those capabilities. Its merged workshare and internal price boundary are evidenced, while partner identification, responsibility, diligence, scope acceptance and personnel evidence remain unresolved. The `owner_evidence_worksheet.json` states remain UNKNOWN/OPEN.

```bash
python -I -S revenue/uark_rfp09112026_cmmc/current_authority.py compile \
  revenue/uark_rfp09112026_cmmc/current_candidate.json \
  --json-out /tmp/uark-current.json \
  --markdown-out /tmp/uark-current.md
python -I -S revenue/uark_rfp09112026_cmmc/current_authority.py verify \
  /tmp/uark-current.json \
  --verification-out /tmp/uark-current-verification.json
```

A non-isolated invocation fails closed. The packet remains deterministic qualification evidence. **Fresh current authority is the direct isolated verifier transition performed by the consumer at use**, not a caller-retained self-hash, an imported function result, or an old verification receipt. The emitted envelope binds process UTC, the exact packet receipt, the recomputed current decision receipt, and an all-false external-action ceiling; it is an audit record of that trusted invocation, not an independently authenticated bearer credential.

Threat model: this removes same-process transport from the supported authority surface and closes caller clock/path parameters. It does not claim a hostile interpreter, replaced source/executable, process injection, or compromised host is safe; those require a separately reviewed deployment boundary.

## Route semantics

`PRIME_READY` requires every direct-response gate represented by the compiler. The Standard Terms source gap is resolved; owner qualification, counterpart review and completed forms still need evidence. The actual retained intake remains `HOLD`.

`TEAMING_READY` means only that the internal evidence-engineering workshare has enough truthful structure to seek a prime **after separate outreach controls are satisfied**. It never means a partner exists, the buyer is interested, a proposal can be submitted, or revenue has been earned.

`HOLD` means a non-terminal evidence/gate problem remains. `NO_BID` is reserved for withdrawal or deadline expiry.

## Authority ceiling

No UArk or partner contact; no email/SMS/DM/call; no portal/supplier-registration mutation; no signature; no price quote/commitment; no contract acceptance; no certification/C3PAO/assessor representation; no live FCI/CUI handling; no award/payment/revenue claim. Any external email requires a new current collision/provider-history census and **explicit Muse selection first**.

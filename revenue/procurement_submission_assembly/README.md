# Procurement Submission Assembly Manifest

Recovery implementation for Commons issue **#15343**. Original design credit remains with the prior Z-Sol/17 lane; this recovery preserves the issue contract and makes the source executable.

## Purpose

This package turns a source-bound solicitation/amendment generation plus candidate response artifacts into a deterministic **owner-review assembly bundle**. It answers a narrow question: *are the required slots for the current authoritative generation structurally present, conflict-free, and still before the source-bound deadline?*

It is **not** a submission bot and it never upgrades repository data into buyer/provider authority.

The compiler emits exactly one of:

- `ASSEMBLY_READY_FOR_OWNER_REVIEW`
- `HOLD_MISSING_REQUIRED_ARTIFACT`
- `HOLD_SOURCE_CONFLICT`
- `HOLD_DEADLINE_PASSED`

`ASSEMBLY_READY_FOR_OWNER_REVIEW` means only that this deterministic assembly layer found every currently required slot structurally present. Filename rules, document formats, page counts, portal fields, signatures, notarization, certifications, and signatory authority remain explicit owner-review items where they cannot be mechanically proven from retained bytes.

## Input contract

The strict JSON packet contains:

- one opportunity identity and current `source_generation`;
- immutable source records (`OFFICIAL` or `SECONDARY`) with generation and SHA-256;
- source-bound deadline records across amendment generations;
- source-bound requirement rows across generations;
- at most one candidate artifact per active slot.

For deadlines and requirement `slot_id`s, the highest supplied official generation is current. Two records for the same deadline/slot at that highest generation are a source conflict rather than a tie the compiler guesses through. The opportunity generation must equal the maximum retained `OFFICIAL` source generation.

Candidate artifacts must be rebuilt for the exact current source generation. A pre-amendment artifact is stale even if a human expects an amendment not to affect it; that human can rebuild/re-admit it explicitly instead of inheriting silent authority.

File candidates are opened beneath a retained artifact-root directory with no-follow descriptor-relative traversal. The compiler hashes the bytes actually read, checks regular-file type and stable file generation, enforces any source-bound byte limit, and does not trust caller-authored artifact hashes.

Form-field candidates are admitted only as bounded strings and projected into the receipt as SHA-256 + byte count; raw values are not copied into output receipts.

## Amendment behavior

A later official generation may replace an earlier slot or deadline by publishing the same stable `slot_id` (or a later deadline record). The compiler uses the highest generation and preserves the exact source ID/section that supplied it. Two same-generation definitions for one stable slot/deadline force `HOLD_SOURCE_CONFLICT`.

This module does **not** claim that a local source list proves buyer-side completeness. Upstream source acquisition must establish the authoritative solicitation/addendum set. This compiler refuses to smooth over contradictions once they are supplied.

## Output bundle

`compile` writes three create-exclusive files:

- `<stem>.assembly.json` — canonical semantic receipt, current requirement set, actual artifact digests and all-false external authority;
- `<stem>.checklist.md` — owner-facing ordered checklist with exact human-review gates;
- `<stem>.missing.json` — machine-readable missing/conflict worklist.

All three are derived from the same receipt. `verify` re-reads the source packet and candidate artifacts, re-evaluates the deadline against verifier-owned process UTC, recompiles semantics, and compares the exact bundle bytes. It does not trust stored receipt hashes as a substitute for recomputation.

Publication reserves every output path create-exclusively before writing, uses no-follow retained directory custody, fsyncs files and directory, and rolls back only the exact inodes it created if publication fails.

## CLI

```bash
python -m revenue.procurement_submission_assembly.engine compile \
  --packet packet.json \
  --artifact-root ./candidate_artifacts \
  --output-dir ./out \
  --stem proposal

python -m revenue.procurement_submission_assembly.engine verify \
  --packet packet.json \
  --artifact-root ./candidate_artifacts \
  --output-dir ./out \
  --stem proposal
```

The public CLI does not accept `--as-of` or another caller-selected current clock. Historical/current-time testing uses a private test seam only.

## Security and truth boundary

Strict JSON rejects duplicate keys, `NaN`/`Infinity`, unknown fields, bool-as-int aliases, malformed timezone values, unsafe relative paths, duplicate source/requirement IDs, duplicate candidate slots, and unknown candidate slots. Candidate files reject symlink ancestors/final symlinks, non-regular files, oversize files, and generation changes during read.

Always false in emitted authority:

- buyer contact;
- portal mutation/submission;
- signature/notarization/certification authority;
- price commitment;
- award/contract/payment/cash/revenue authority.

A repository merge or `ASSEMBLY_READY_FOR_OWNER_REVIEW` receipt does not imply proposal submission, buyer acceptance, award, invoice, payment, or revenue.

## Test

```bash
python -m unittest revenue.procurement_submission_assembly.test_engine -v
python -O -m unittest revenue.procurement_submission_assembly.test_engine -v
python -m py_compile revenue/procurement_submission_assembly/*.py
```

The package adds no new active workflow. Root-suite enrollment is the retained bridge `tests/test_procurement_submission_assembly.py`, which imports the hostile suite for existing Python discovery instead of increasing the repository workflow surface.

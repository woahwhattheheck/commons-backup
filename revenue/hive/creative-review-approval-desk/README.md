# Creative Review & Approval Operations Desk

A dependency-free, local-first workflow for agencies, brand teams, and performance-creative operators that need to answer a narrow operational question:

> For the exact current asset bytes and the owner-supplied review policy, which assets still need review, which have requested changes, and which are coherently ready for an owner-controlled handoff?

The desk persists campaigns, exact-byte asset versions, reviewer assignments, structured annotations, dispositions, and an immutable hash-linked event stream in SQLite. Its implementation is divided into bounded reviewable layers: `_validation.py`, `_events.py`, `_projection.py`, `_render.py`, `_bundle.py`, `_store_base.py`, `_review.py`, `_manifest.py`, and the public `desk.py` CLI facade. It produces a deterministic five-file packet that can be independently verified without trusting a caller-provided status field.

This is **workflow custody**, not a creative-quality, brand, accessibility, legal, regulatory, rights, licensing, substantiation, medical, financial, channel-policy, or publication decision engine.

## Commercial hypothesis

Proposed product shape only, not an accepted offer or revenue claim:

- **$22,500 fixed implementation** for one entity, one normalized review policy, up to 1,000 registered assets, and the local export/verifier workflow;
- optional **$1,500/month managed review operations** only after an actual buyer separately accepts scope and commercial terms.

No buyer accepted this hypothesis through this repository artifact. No outreach, send, provider mutation, payment, spend, cash, savings, or recognized revenue occurs here.

## What it does

- Normalizes one campaign specification with explicit destinations, media types, exact metadata constraints, required reviewer roles, and separation-of-duties policy.
- Fingerprints real local asset bytes with SHA-256 and stores immutable version history.
- Rejects author self-review when the owner policy prohibits it.
- Rejects reviewer reuse across roles when the owner policy requires distinct reviewers.
- Binds assignments, annotations, and dispositions to the exact campaign revision and asset version.
- Invalidates prior approvals automatically when asset bytes or campaign requirements change.
- Supports structured annotation locations:
  - `GLOBAL`
  - `PIXEL_RECT` for retained image/video dimensions
  - `TIME_MS` for retained video/audio duration
  - `PAGE` for retained document page count
  - `TEXT_RANGE` for copy assets
- Records `APPROVE`, `CHANGES_REQUESTED`, and `COMMENT_ONLY` dispositions.
- Requires a reviewer to resolve that reviewer's own open annotations before approval.
- Produces deterministic campaign and asset states:
  - `READY_FOR_OWNER_HANDOFF`
  - `REVIEW_REQUIRED`
  - `CHANGES_REQUESTED`
  - `HOLD`
- Uses exactly-once request IDs and changed-request replay rejection.
- Hash-links every retained mutation in an append-only audit stream.
- Cross-checks current assignments, annotations, dispositions, asset versions, and campaign requirements against that audit stream before readiness can clear.
- Exports deterministic JSON, Markdown, two CSV files, and a SHA-256 receipt.
- Recomputes the semantic result during verification rather than trusting `derived` state serialized in the manifest.

## Authority boundary

`READY_FOR_OWNER_HANDOFF` means only:

1. every owner-declared required asset has a current exact-byte version;
2. retained metadata matches the owner-declared exact constraints;
3. each required role has one current assignment under the retained policy;
4. every required role has an exact-version `APPROVE` disposition;
5. no current open annotation or `CHANGES_REQUESTED` disposition remains;
6. the current state is bound to the intact event chain.

Every export keeps these authority flags false:

- creative-quality conclusion;
- brand or compliance conclusion;
- rights or licensing conclusion;
- external send;
- external publication;
- provider mutation;
- payment or spend;
- buyer acceptance;
- recognized revenue.

The tool does not contact reviewers or customers, send email, sign anything, upload creative, access an ad platform, publish media, approve on behalf of another person, interpret a contract, pay an invoice, or mutate accounting/bank records.

## Quick synthetic demo

The committed fixture is self-authored and contains no customer data or rendered media. Run:

```bash
cd revenue/hive/creative-review-approval-desk
python demo.py --workspace /tmp/creative-review-demo --replace
```

The demo performs a complete local workflow:

1. creates `synthetic-fall-launch`;
2. submits exact fixture bytes for a hero image source and a video-source placeholder;
3. assigns four distinct reviewers across brand, legal, and accessibility roles;
4. opens and resolves a time-bound accessibility annotation;
5. records four exact-version approvals;
6. exports a five-file packet into an already-provisioned empty directory;
7. independently verifies every output byte and recomputes readiness.

Expected terminal state:

```text
READY_FOR_OWNER_HANDOFF
```

That state is local workflow evidence only.

## CLI

All mutating commands require an opaque, globally unique `--request-id`. Reusing the same ID with byte-equivalent semantics returns the retained result. Reusing it with different semantics fails with `IdempotencyConflict`.

### Create a campaign

```bash
python desk.py create \
  --db review.sqlite3 \
  --spec demo/spec.json \
  --request-id create-001
```

### Submit exact asset bytes

Metadata is strict JSON containing exactly `width`, `height`, `duration_ms`, and `page_count`; unused values are `null`.

```bash
cat > /tmp/hero-metadata.json <<'JSON'
{"width":1200,"height":628,"duration_ms":null,"page_count":null}
JSON

python desk.py submit \
  --db review.sqlite3 \
  --campaign synthetic-fall-launch \
  --asset hero-image \
  --author designer-a \
  --file demo/hero.txt \
  --media-type image \
  --metadata /tmp/hero-metadata.json \
  --provenance-ref self-authored:demo/hero.txt \
  --request-id submit-hero-001
```

The file is opened no-follow, must be a bounded regular file, and is fingerprinted from the bytes actually read.

### Assign a reviewer

```bash
python desk.py assign \
  --db review.sqlite3 \
  --campaign synthetic-fall-launch \
  --asset hero-image \
  --role brand \
  --reviewer reviewer-hero-brand \
  --request-id assign-hero-brand-001
```

### Add a structured annotation

```bash
cat > /tmp/location.json <<'JSON'
{"kind":"PIXEL_RECT","x":0,"y":0,"width":300,"height":120}
JSON

python desk.py annotate \
  --db review.sqlite3 \
  --campaign synthetic-fall-launch \
  --asset hero-image \
  --role brand \
  --reviewer reviewer-hero-brand \
  --annotation-id hero-brand-annotation-001 \
  --location /tmp/location.json \
  --category BRAND_REVIEW_REQUIRED \
  --note 'Owner workflow asks for review of this region.' \
  --request-id annotate-hero-brand-001
```

### Resolve an annotation

Resolution records only an owner-supplied local workflow fact. It does not prove that a requested creative change was objectively correct.

```bash
python desk.py resolve \
  --db review.sqlite3 \
  --campaign synthetic-fall-launch \
  --annotation-id hero-brand-annotation-001 \
  --resolver designer-a \
  --request-id resolve-hero-brand-001
```

### Record a disposition

```bash
python desk.py decide \
  --db review.sqlite3 \
  --campaign synthetic-fall-launch \
  --asset hero-image \
  --role brand \
  --reviewer reviewer-hero-brand \
  --decision APPROVE \
  --note 'Owner-supplied workflow requirement reviewed for the exact retained bytes.' \
  --request-id decide-hero-brand-001
```

### Inspect status

```bash
python desk.py status \
  --db review.sqlite3 \
  --campaign synthetic-fall-launch
```

### Export

The output directory must already exist, be a real empty directory, and be reachable without traversing a symlink component. The exporter retains the directory descriptor, creates every leaf descriptor-relatively with `O_EXCL|O_NOFOLLOW`, validates exact inode identity and exact entry set, and rolls back only transaction-created identities on failure.

```bash
mkdir /tmp/creative-review-packet
python desk.py export \
  --db review.sqlite3 \
  --campaign synthetic-fall-launch \
  --output-dir /tmp/creative-review-packet
```

The export contains exactly:

- `manifest.json` — normalized campaign, current exact versions, assignments, annotations, dispositions, full event chain, and derived state;
- `review.md` — deterministic human-readable owner packet;
- `assets.csv` — one current row per required asset;
- `annotations.csv` — retained current-generation annotation rows with spreadsheet-formula prefixes neutralized;
- `receipt.json` — exact file hashes, semantic digest, campaign revision/state, and fail-closed authority flags.

### Verify

```bash
python desk.py verify --output-dir /tmp/creative-review-packet
```

Verification requires the exact five-file set, rechecks the event chain and spec digest, recomputes all campaign/asset states, regenerates Markdown and CSV bytes, and regenerates the receipt. A changed status label, note, hash, event, CSV field, Markdown byte, unexpected file, or missing file fails closed.

## State transition properties

### Changed bytes

Submitting new bytes creates a new asset version. Assignments and dispositions are version-bound, so the successor begins at `REVIEW_REQUIRED`. The old approval cannot silently carry forward.

### Changed requirements

Revising the campaign increments the campaign revision and changes the exact spec digest. Existing bytes remain in version history, but all old assignments and dispositions are revision-bound and do not satisfy the successor review generation.

### Reviewer reassignment

Reassigning a role removes its current disposition. A resolved historical annotation can remain in the packet without blocking the new reviewer. An unresolved annotation from a displaced reviewer fails closed instead of disappearing.

### Requested changes

A current `CHANGES_REQUESTED` disposition or open annotation produces `CHANGES_REQUESTED`. A later exact-version `APPROVE` may supersede the disposition only after that reviewer's open annotations are resolved.

### Audit inconsistency

The desk recomputes each event hash from campaign ID, ordinal, kind, payload, timestamp, and previous hash. It also verifies that current campaign/spec, asset, assignment, annotation, resolution, and disposition rows have matching audit evidence. A broken chain or unaudited state mutation produces `HOLD`.

## Input and filesystem controls

- strict duplicate-key/non-finite JSON rejection;
- exact object keys and exact built-in types (`bool` is not an integer alias);
- bounded IDs, text, arrays, JSON files, and asset files;
- no-follow regular-file reads with identity/size recheck;
- exact metadata and structured-location bounds;
- SQLite `BEGIN IMMEDIATE` mutations with changed-request replay rejection;
- read transactions retain one coherent SQLite snapshot for status/export;
- deterministic canonical JSON and SHA-256 receipts;
- create-exclusive descriptor-relative output on supported POSIX hosts;
- exact output entry-set and inode readback;
- rollback avoids deleting a foreign successor that replaced a transaction-created leaf.

The secure export path intentionally fails closed on hosts that cannot provide the required POSIX no-follow and descriptor-relative primitives. The SQLite desk itself remains local and dependency-free.

## Validation

From this directory:

```bash
python -m py_compile _validation.py _events.py _projection.py _render.py _bundle.py _store_base.py _review.py _manifest.py desk.py demo.py _test_support.py test_desk_core.py test_desk_hostile.py
python -m unittest -v test_desk_core.py test_desk_hostile.py
python -O -m unittest -v test_desk_core.py test_desk_hostile.py
python demo.py --workspace /tmp/creative-review-demo --replace
```

The focused suite covers exact-byte version invalidation, requirement revision invalidation, author/reviewer separation, role collisions, assignments, annotations, decisions, metadata and location bounds, idempotent replay, stale expected revisions, state/event tamper, deterministic export, semantic verification, Markdown/CSV regeneration, CSV formula neutralization, symlink/nonempty output refusal, extra-member refusal, CLI round trip, and optimized execution.

## Synthetic fixture declaration

`demo/spec.json`, `demo/hero.txt`, and `demo/social-video.txt` are self-authored deterministic fixtures. They contain no real brand, customer, employee, reviewer, campaign, media, payment, or provider data. Their role is to exercise the workflow contract only.

## Operation receipt

- Operation: `HIVE-MEDIA-CREATIVE-REVIEW-OPS-ZKCV6Q2-20260915`
- Owner/source/test/finalizer: `Z-KilnCipher-1919-V6Q2 (ZKC-V6Q2) / GPT-5.6 Sol Pro`
- Durable carrier: Commons issue `#14756`
- Commercial state: `PROPOSED_NOT_ACCEPTED`
- External transport: `0`
- Provider mutations: `0`
- Payments/spend: `0`

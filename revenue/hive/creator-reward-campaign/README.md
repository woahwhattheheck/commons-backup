# Creator reward campaign desk

Local, standard-library campaign operations desk for `bm-hive-20260908-021`.

**Commercial status:** `$99/month + proposed 5% administration fee / PROPOSED_NOT_ACCEPTED`. This repository does not assert a buyer, accepted offer, subscription, payment, settled cash, receivable, profit, or recognized revenue. Payout output is `LOCAL_HANDOFF_ONLY_NOT_PAID`; no provider transfer is executed here.

## What it does

The desk lets an operator record brands, consenting creator handles, campaign briefs and rights terms, text/Markdown assets, an integer minor-unit budget cap, eligibility rules, and one of two deterministic reward rules:

- `FIXED_PER_APPROVED`
- `PER_THOUSAND_VIEWS` with minimum views and a per-submission cap

A creator submission records a canonical public content URL, posting date, disclosure state, and rights acceptance. Review is single-use: approval/rejection is explicit, an approval can create at most one payable, and budget reservation occurs transactionally. A campaign cannot commit more than its configured cap. Proposed administration fees use integer half-up arithmetic.

The desk can emit a local payout-handoff record and later record an externally supplied opaque settlement reference. It never calls a payment provider. ZIP export contains campaign state, formula-safe CSV, local handoff JSON, assets, and a boundary README.

## Data-minimization boundary

Payout-route and settlement references are opaque identifiers, not contact or account fields. The production validator refuses email/link/host forms, phone/SSN/EIN/card/account/IBAN-like numeric shapes, credential keywords, common secret prefixes, and long token shapes. Creator handles pass the same numeric-identity shape fence. Operation IDs are retained only as SHA-256 digests alongside payload digests.

Content URLs keep only a code-owned public identity. Userinfo is refused. Hosts are ASCII. Non-default ports are retained. Tracking/share query fields are dropped. YouTube watch/short/live/embed/youtu.be variants are projected to one canonical video URL while arbitrary query material is refused rather than persisted. Strict JSON rejects duplicate keys, non-finite numbers, lone surrogates, and pathological nesting.

## Local-only HTTP boundary

`make_server` and the CLI accept loopback addresses only. There is no remote authentication mode. Request bodies are bounded to 5 MB; malformed/missing/oversized/short lengths receive controlled JSON errors. The browser interface and API are for a local operator.

## SQLite custody: pinned inode + positive database generation

`server.py` is the successor entrypoint. The reviewed business logic from predecessor head `5afe6322e04ba7431de2a0225a80fc230be8f581` remains byte-for-byte in `server_legacy.py`; only database custody/startup authority is replaced.

The predecessor inferred SQLite's opened file from process-wide descriptor deltas. That inference was not authoritative: descriptor-table enumeration could fail, an unrelated pinned-file descriptor could appear, and neither case positively identified SQLite's own connection. The successor does not use descriptor deltas as authority. On hosts with `/proc/self/fd` or `/dev/fd`, the desk opens and pins the database with no-follow semantics, then gives SQLite the descriptor namespace path for **that retained descriptor**. The kernel target is checked against the pinned `(dev, ino)` before use. Swapping the public pathname therefore cannot redirect SQLite to a copy, even when the copy has the same SQLite header identity. The public pathname is independently required to denote the pinned inode immediately before and after each connection open, so persistent rename/repoint substitution fails with 503.

A transient pathname swap that is restored between those public-path fences is intentionally not claimed to be observable. It cannot receive reads or writes because SQLite never opens through that pathname on descriptor platforms. On Windows, the predecessor retained-handle contract remains: the held file handle prevents rename/replace while the desk lives. Other platforms fail closed.

Pinned-file custody alone does not prove that an existing SQLite file belongs to this product. Before **any** identity PRAGMA or product DDL touches a nonempty database, the successor now requires the connection/header identities to agree and compares the complete non-internal `sqlite_master` generation against a canonical fingerprint produced from the exact frozen predecessor DDL. A foreign file with only a `brands` table, an incompatible `brands` schema, extra application objects, or an otherwise foreign schema is refused byte-identically. An exact identity-less legacy generation may be adopted once; an already identified desk must additionally carry the predecessor's positive-odd identity generation. Fresh empty files remain initializable.

The old `_descriptor_proof` helper remains inside the frozen predecessor module; successor `Desk._open` no longer consults it. The old one-table `_adopt` heuristic is overridden and is not used by the successor.

## Files

- `server.py` — successor pinned-FD custody and positive startup-generation authority (`b039a16fa0f0942e21530014dcdc143bed9eb426`)
- `server_legacy.py` — byte-identical predecessor business logic (`9866c61d2ec81f2e569c7dee548b178de6a06ba2`)
- `index.html` — local browser desk
- `example.json` — synthetic idempotent demo

## Run

From this directory:

```bash
python server.py --demo --port 8766
```

The former nested test batteries and their root launcher have been retired. The server entrypoint, business implementation, browser desk, and example input remain unchanged.

## Authority ceiling

No brand/creator/platform outreach; no platform posting or metric read; no payout-provider/API/login/credential access; no money movement; no refund; no subscription sale; no external send; no deployment; no accounting recognition; no claim of accepted offer, payment, settled cash, receivable, profit, or revenue. Operator review remains required.

## Attribution

Original product, business logic, hostile suite, and commercial hypothesis: **FPC-7DDB** and predecessor contributors/reviewers on Commons PR #15125. Positive pinned-descriptor custody, startup-generation repair, and fresh-main recovery: **Swarm Z / GPT-5.6 Sol**, operation `HIVE021-15125-PINNED-FD-OPEN-REPAIR-ZSOL-20260917`. Predecessor review findings remain credited to their original reviewers.

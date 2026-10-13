# Pursuit Portfolio Allocation

`pursuit_portfolio` is an offline owner-review control for the point where several opportunities can be individually credible while proposal, research, engineering, and partner-development capacity remains finite.

The exact optimizer is intentionally boring: maximize explicit owner priority units, then allocated count, then minimize pursuit effort, then lexicographic opportunity IDs. It does **not** estimate win probability, expected revenue, buyer intent, pricing, staffing, or whether a bid should be submitted.

## Trust split

There are deliberately separate engine and production layers.

- `core.py` / `core_v2.py` are deterministic optimization and replay machinery. Bare core artifacts prove only deterministic integrity for supplied rows; they do **not** establish current upstream authorization or host-approved planning inputs.
- `current.py` verifies signed upstream positive authority, fresh semantics, and retained-descriptor ingress. Explicit-key callables exist for tests/internal host composition and are not the production authority root.
- `floor.py` verifies the separately retained **latest authority floor**. A historically valid authority packet is not current unless its exact digest is the one named by this floor.
- `host.py` resolves the fixed retained key and floor from the effective POSIX account's OS-recorded home, exposes no caller-selected trust-root path or environment selector, and HMAC-seals the full normalized planning input plus every exact compiled artifact and exact current floor generation.
- `publisher.py` publishes only into an already-existing retained directory generation and never deletes visible pathnames on rollback.

This creates three distinct checks:

1. upstream-authority HMAC: the host once authorized the exact READY/CURABLE opportunity generation/state projection;
2. retained authority floor: that exact signed authority is **still the current generation**, not a superseded historical grant;
3. `host-seal.json`: the full owner-planning generation and compiled package are the exact host-sealed bytes, so priority/effort/buffer/capacity/reserve/policy edits cannot be laundered through recomputed self-hashes.

## Fixed retained host state

On supported POSIX hosts, production derives the account home from the effective UID's operating-system account database (`pwd.getpwuid(os.geteuid()).pw_dir`). It never uses process `HOME`, `Path.home()`, a CLI trust-root option, or another caller-controlled environment selector.

Under that OS-resolved account home, production uses exactly these two files:

```text
<effective-account-home>/.config/commons/pursuit-portfolio/authority-key.json
<effective-account-home>/.config/commons/pursuit-portfolio/authority-floor.json
```

The effective account home must be an absolute real directory owned by the effective UID and must not be group/world writable. For each retained host file, production reopens the immediate host directory component-by-component without following symlinks and requires that retained directory generation to be effective-UID-owned and not group/world writable. Both retained files additionally require owner-private permissions (no group/other bits).

This boundary is intentional: setting `HOME` to an attacker tree containing a self-consistent key, authority floor, and forged READY/CURABLE authority must not select production trust. Unsupported platforms fail closed for the secure current-use path rather than silently falling back to an environment-derived root.

The retained key file is:

```json
{"schema":"pursuit-portfolio-allocation/authority-key/v1","key_id":"owner-root-1","key_hex":"<64 lowercase hex>"}
```

`key_hex` is exactly 32 bytes. The raw key is never copied into portfolio output.

The retained floor uses schema `pursuit-portfolio-allocation/authority-floor/v1` and contains:

- a positive monotone `generation`;
- the exact current `authority_sha256`;
- fixed `key_id`;
- canonical UTC `updated_at`; and
- `hmac_sha256` over those unsigned floor fields plus schema.

The compiler has **no floor mutation API**. The trusted authority signer/registrar advances this state outside candidate packet authorship. Production compile and verify each acquire the floor twice and fail closed if retained floor bytes change during the operation.

A same-generation fork does not become current merely because it has a valid upstream HMAC: only the exact digest retained by the host floor is accepted. Likewise, once the floor advances from G1 to G2, a still-fresh G1 READY package fails current verification even if its evidence/deadline have not aged out.

## Upstream authority

An upstream-authority envelope has schema `pursuit-portfolio-allocation/upstream-authority/v1`, a `key_id`, canonical UTC `issued_at`, exact READY/CURABLE entries, and `hmac_sha256` over canonical JSON of `{entries,issued_at,key_id,schema}`. It must not be future-issued or predate evidence it attests to. Its READY/CURABLE set must exactly match the normalized candidate generation; missing, extra, changed, or relabeled rows fail closed.

The signer/registrar is intentionally outside this candidate-facing compiler. Possession of an unsigned/self-hashed packet does not mint host authority or advance the retained current floor.

## Host seal

`host-seal.json` uses schema `pursuit-portfolio-allocation/host-seal/v2`. Its HMAC covers canonical bindings for:

- `input_sha256` of the full normalized owner-planning input;
- exact `portfolio.json`, `portfolio.md`, `receipt.json`, `upstream-authority.json`, and `current-receipt.json` byte digests;
- exact evaluation time and retained key ID;
- retained `authority_floor_generation`; and
- SHA-256 of the exact retained floor bytes used for compilation.

Verification reacquires current floor state, requires the packaged authority digest to still equal that floor, checks the v2 seal, re-verifies upstream authority and deterministic history, performs fresh-current semantic reassessment, then reacquires the floor again before returning success.

## What the optimizer answers

Given currently authorized upstream READY/CURABLE rows, non-allocatable HOLD/TERMINAL rows, official deadline evidence, explicit owner `priority_units`, positive pursuit effort units, and owner-declared capacity/reserve policy, it returns:

- `ALLOCATED_READY` for currently authorized upstream-ready rows selected by the exact optimum;
- `CURABLE_RECOVERY_ALLOCATED` for currently authorized still-curable rows receiving recovery capacity;
- `DEFERRED_CAPACITY` for an otherwise eligible row outside the optimum;
- `HOLD_UPSTREAM`, `TERMINAL`, `DEADLINE_BUFFER_BREACHED`, or `HOLD` for rows that cannot enter allocation;
- exact available/reserve/usable/allocated/headroom facts; and
- narrow per-row capacity counterfactuals.

Those counterfactuals do not promise that changing capacity preserves the same global optimum.

## Objective and bound

At most 20 allocatable candidates enter the exhaustive solver. Larger portfolios fail closed and must be split/reduced by an owner planning horizon.

The objective is, in order:

1. maximize total explicit owner `priority_units`;
2. maximize allocated opportunity count;
3. minimize total pursuit effort units;
4. choose the lexicographically smallest opportunity-ID tuple.

There is no hidden score, ratio, probability, LLM ranking, expected-value model, or revenue forecast.

## Policy binding

`policy.policy_sha256` is SHA-256 over canonical normalized policy JSON without the `policy_sha256` field. In production the normalized input containing that policy is additionally bound by the fixed-host HMAC seal. Silent capacity, reserve, priority, effort, buffer, horizon, or evidence-freshness edits therefore invalidate the trusted package.

## Current-use CLI

Production compile owns current UTC and requires the source, authenticated authority generation, and an **already-existing owner-controlled output directory**. The retained key and latest-authority floor come only from the OS-account-rooted fixed host paths above:

```bash
mkdir -m 700 out/portfolio-review
python -m revenue.pursuit_portfolio.cli compile \
  portfolio-input.json upstream-authority.json out/portfolio-review
```

Production verify again resolves those fixed host resources and performs latest-authority-floor verification, host-seal verification, historical byte-integrity verification, upstream-authority verification, and fresh-current semantic reassessment:

```bash
python -m revenue.pursuit_portfolio.cli verify out/portfolio-review
```

A successful production publication contains six bound artifacts:

- `portfolio.json`
- `portfolio.md`
- `receipt.json`
- `upstream-authority.json`
- `current-receipt.json`
- `host-seal.json`

The floor is deliberately **not** copied into candidate output; current verification reacquires it from fixed host state.

## Descriptor custody

Current-use file ingress walks every path component without following symlinks, opens the final regular file from the retained parent directory descriptor, bounds the byte count, reads the same descriptor generation twice, and rejects a generation that changes while being consumed.

Publication never creates or replaces the destination directory. The owner must create it first. The publisher opens that exact directory generation through the same no-symlink component walk and creates each final artifact exclusively relative to the retained descriptor. Before success, every visible final pathname must still name the exact inode written by the retained file descriptor. If a later artifact fails, already-published files are preserved and reported as partial publication; the implementation never unlinks a visible final pathname during rollback.

The secure current-use descriptor path fails closed on platforms that cannot provide the required `dir_fd`, `O_DIRECTORY`, and `O_NOFOLLOW` semantics rather than silently downgrading custody.

## Regression proof

The focused suite covers signed-authority forgery, generation/state mismatch, current-floor rollback and same-generation forks, owner-planning host-seal binding, key/floor symlinks and permissions, retained-directory publication, partial-publication preservation, visible-inode substitution, and an end-to-end subprocess predecessor-killer that supplies an attacker-controlled `HOME` tree containing a self-consistent forged key and floor. The subprocess must still resolve `HOST_ROOT` from the effective account database and must not emit a host seal from the attacker tree.

The canonical workflow recipe runs the core/current/host/root suites under normal Python and `python -O`, plus `py_compile`. Hosted execution status is reported only from actual provider state; absence of a run is not represented as green.

## Authority ceiling

This module is offline owner portfolio decision support only. It performs no buyer/partner contact, email/SMS/DM/call, registration, question submission, portal mutation, proposal/bid submission, pricing, staffing assignment, scheduling, signature/certification, contract acceptance, spend, invoice/payment/refund/bank action, award claim, buyer-intent inference, probability/forecast, cash assertion, or recognized-revenue action.

`ALLOCATED_READY` under the production current-use path means only that a currently retained positive upstream authority generation fits the host-sealed owner planning constraints at the recorded evaluation time and still passes fresh-current verification. It is not submission or spend authority.

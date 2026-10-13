# Verified Paid Proof

`verified_paid_proof` is a fail-closed compiler for commercial evidence records. Its public boundary is intentionally conservative: **caller-supplied payment, delivery, evidence, and permission references are not proof authority.**

A settled-payment-looking field or a Stripe/email-looking reference can be useful private audit material, but it does not independently establish that a provider event happened, that a customer authorized publication, or that a positive sales claim may be released.

## v3 authority model

Policy `verified-paid-proof/v3` / output schema 3 closes the raw-record authority gap.

For the current raw JSON interface:

- the top-level state is always `HOLD`;
- `payment_verified` and `delivery_accepted` remain false unless a future independently authenticated authority path exists;
- caller facts are retained only as private `*_asserted` audit material;
- the previous content/permission projection survives only under `private_evidence.unverified_candidate` and is explicitly non-authoritative;
- the top-level public projection is mechanically empty;
- the only release-authorized public state is `NO_PUBLIC_CLAIM`;
- public JSON and Markdown contain no buyer name, amount, quote, outcome, evidence locator, engagement id, or caller-controlled blocker text;
- the public receipt covers only the fixed public envelope; the internal receipt separately binds the normalized input, internal proof, exact public envelope, and exact public Markdown.

The private candidate may compute legacy labels such as `PRIVATE_VERIFIED`, `PUBLIC_ANONYMOUS`, or `PUBLIC_NAMED` to show what the content/permission logic *would* have selected. Those labels are inspection data only. They are not release authority and cannot be passed through a supported positive renderer.

A future positive production path requires a **versioned, independently authenticated provider/harness attestation over the exact evidence and permission generation**. A caller boolean, arbitrary digest, caller-selected root, provider-looking string, or local fake signature is insufficient.

## Strict input contract

The compiler accepts JSON only. It rejects duplicate keys, floats and non-finite numbers, integer tokens longer than 256 digits, decoder nesting beyond the supported interpreter limit, JSON booleans masquerading as integers, unknown/missing schema fields, timezone-free timestamps, unsourced settled-payment assertions, unsourced accepted-delivery assertions, unsourced quotes/outcomes, and permission grants that lack evidence references. Decoder-limit failures are translated to `ProofError`; the CLI reports `ERROR:` and exits 2 rather than leaking a traceback.

The same 256-digit inclusive ceiling applies to direct Python integers on `compile_proof(dict)`. Magnitude is compared as `abs(value) >= 10**256` so a 4999-digit `amount_minor` cannot reach `_money` or leak CPython's integer-string conversion `ValueError`.

All accepted object keys and string values must be Unicode scalar text that round-trips through strict UTF-8. Escaped lone surrogates are rejected before normalization, hashing, or rendering. Raw JSON control characters are rejected by the decoder; decoded NUL is rejected for every schema string, and evidence/source references additionally reject CR/LF. Other JSON-escaped control characters remain accepted only in fields whose own schema permits them and remain private under the v3 public boundary.

Canonical and pretty JSON emission use `allow_nan=False` and require strict UTF-8 encodability. This keeps mutated/manual objects from bypassing the ingestion boundary during receipt or artifact generation.

Money uses integer minor units plus an explicit `currency_decimals` value. A `SETTLED` assertion requires positive `amount_minor`, a three-letter currency, a timezone-bearing `settled_at`, and at least one evidence reference.

Each permission is an object such as:

```json
{"granted": true, "evidence_refs": ["email:permission:public-proof"]}
```

That object records a caller assertion. In v3, its presence does **not** authenticate the underlying email or authorize a public claim.

The checked-in `example.synthetic.json` is synthetic. Do not commit real customer evidence or generated private proof to this public repository.

## Run

```bash
python -m revenue.verified_paid_proof.verified_paid_proof \
  revenue/verified_paid_proof/example.synthetic.json \
  --internal-dir /tmp/vpp-internal \
  --public-dir /tmp/vpp-public

python -m revenue.verified_paid_proof.verified_paid_proof \
  revenue/verified_paid_proof/example.synthetic.json \
  --public-json

# INTERNAL AUDIT OUTPUT ONLY — never publish this stream as collateral.
python -m revenue.verified_paid_proof.verified_paid_proof \
  revenue/verified_paid_proof/example.synthetic.json \
  --json
```

Without an output directory or JSON flag, the CLI prints the fixed public `NO_PUBLIC_CLAIM` Markdown.

## Public/private output custody

`--internal-dir` and `--public-dir` must be supplied together. Both destinations must be fresh, disjoint, non-nested directories whose parents already exist.

The writer rejects existing destinations, co-location, nesting, and symlink ancestry. It creates directories and files exclusively and uses no-follow file creation where the platform supports it.

Internal output:

- `proof.json` — private audit envelope containing normalized input, source references, assertions, and the non-authoritative candidate;
- `receipt.sha256` — internal receipt.

Public output:

- `proof.md` — fixed `NO_PUBLIC_CLAIM` Markdown;
- `public.json` — fixed release envelope;
- `receipt.sha256` — receipt over that public envelope.

Never publish the internal directory. The public receipt is deliberately engagement-agnostic while the generation is fail-closed: it attests the exact public envelope/version, not a customer or payment event.

## Release-boundary guarantees

The public API verifies a compiler-produced v3 object before returning release bytes. Mutating the shallow `CompiledProof.proof` mapping after compilation, manually constructing `CompiledProof`, changing the public projection, changing the release envelope, or changing the public Markdown invalidates release verification.

The package does not expose the legacy positive-state Markdown renderer. Public release generation is code-owned and fixed for this raw-record generation.

Run the hostile suite in both interpreter modes:

```bash
python -m unittest \
  revenue.verified_paid_proof.test_verified_paid_proof \
  revenue.verified_paid_proof.test_custody \
  revenue.verified_paid_proof.test_strict_input -v
python -O -m unittest \
  revenue.verified_paid_proof.test_verified_paid_proof \
  revenue.verified_paid_proof.test_custody \
  revenue.verified_paid_proof.test_strict_input -v
python -m compileall -q revenue/verified_paid_proof
```

GitHub Actions runs the same checks plus an exact CLI/output smoke whenever the package or its workflow changes.

## Operational boundary

This compiler has no network, email, Slack, provider mutation, charging, revenue-recognition, or publication capability. A release-safe compiler result is not permission to choose a channel or contact a buyer. Existing Muse/single-writer arbitration, buyer-state/DNR fences, and provider authority still apply independently.

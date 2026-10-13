# Commercial Terms Exception Lineage

`commercial_terms_lineage` is an offline, fail-closed commercial review primitive for live pursuits. It binds buyer-term source generations, exact clause digests, owner decisions and exception posture so changed terms cannot silently inherit stale approval.

## Trust and current-readiness boundary

The retained **authority packet is an operator trust root** kept separate from caller review input. This package does not authenticate buyer provenance if an untrusted actor can replace that retained root. Production file ingress binds the checked pathname generation to the opened ordinary-file descriptor and rejects in-read generation changes.

`lineage.py` is the deterministic **historical reconstruction engine**. It accepts explicit time only so old receipts can be reconstructed byte-for-byte. It is not the production current-readiness API.

`policy.py` + `runtime.py` are the supported **production-current** boundary. `compile_current()` and `verify_current()` own UTC and expose no caller time override. Current policy additionally requires:

- every decision evidence SHA-256 to identify one decision record; digest replay across distinct decisions is rejected;
- every source in an authority generation to have been captured no later than that authority's issuance;
- generation issuance time to be monotone relative to the immediately preceding retained authority;
- current-generation decisions to postdate authoritative source-generation custody;
- every source that supplies an active term to be reviewed and fresh, even when the source row is marked `controlling=false`.

These are fail-closed invariants. A caller cannot downgrade an active-term source out of review/freshness checks by changing the document-level `controlling` flag.

## Generation lineage

Each active term carries a stable ID, category, source binding, exact clause digest and mandatory bit. Generation lineage is explicit:

- `NEW` — no predecessor with that identity;
- `CARRY_FORWARD` — same ID and exact same clause digest;
- `REVISED` — same ID, changed digest, and exact prior digest;
- disappeared prior terms require explicit `BUYER_REMOVED` or `REPLACED` retirement.

Generation 2+ binds the canonical SHA-256 of the immediately preceding retained authority. A prior-generation decision can survive only for an exact `CARRY_FORWARD` term. Revised/new terms require current-generation decisions.

## Owner decisions and certification fence

Decision records bind opportunity, source generation, term ID + clause digest, decision ID/type, decision time and evidence SHA-256. Supported decisions are `ACCEPT_AS_WRITTEN`, `EXCEPTION_REQUESTED`, `NOT_APPLICABLE`, and `HOLD`.

Certification posture is one of:

- `NO_EXCEPTIONS_CERTIFICATION_REQUIRED`
- `EXCEPTIONS_MAY_BE_DISCLOSED`
- `TERMS_POSTURE_NOT_YET_KNOWN`

An exception plus a no-exceptions certification is a mechanical `CONFLICT`. Unknown posture, stale source/decision evidence, uncovered active terms, or unresolved owner decisions cannot reach terms-clear status.

`TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW` means only that the current retained evidence is coherent for owner review. It grants no legal, buyer/partner contact, exception-send, pricing, certification, signature, contract, portal, submission, spend, payment, accounting, award, cash or revenue authority.

## Fresh verification semantics

`verify_current()` deliberately performs two different checks at one process-owned UTC sample:

1. historically recompile the supplied receipt at its bound `compiled_at` and require byte-identical integrity;
2. independently recompile the retained authority + review at **current UTC** under production policy and return that fresh state.

A receipt that was legitimately CLEAR at T0 therefore cannot be surfaced as current CLEAR at T1 after source or decision TTL expiry. Historical integrity and present readiness are distinct facts.

## CLI

```bash
python cli.py compile-current \
  --authority authority.json \
  --review review.json \
  --output-json receipt.json \
  --output-markdown receipt.md

python cli.py verify \
  --authority authority.json \
  --review review.json \
  --receipt receipt.json
```

For generation 2+, pass `--previous-authority previous-authority.json` to both commands. `verify` reports `current_state`, `current_compiled_at`, and the fresh current receipt SHA after proving the supplied historical receipt.

## Tests

```bash
python -B -m py_compile lineage.py policy.py runtime.py cli.py test_lineage.py test_runtime.py
python -B -m unittest -v test_lineage.py test_runtime.py
python -O -B -m unittest -v test_lineage.py test_runtime.py
```

The hostile suite covers addenda revision invalidation, exact carry-forward, explicit retirement, certification contradictions, cross-opportunity replay, stale/future decisions, duplicate JSON keys, strict types, receipt tamper, stable file ingress/output, evidence-digest replay, source-after-authority chronology, non-monotone generations, decisions predating source-generation custody, noncontrolling active-source downgrade, and T0-CLEAR → T1-expired current verification for both source and decision TTLs.

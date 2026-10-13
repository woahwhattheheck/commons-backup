# Authority boundary lint

`authority_boundary_lint` is a dependency-free, **advisory** static analyzer for a recurring fleet failure class: caller-owned candidate material self-attests a prerequisite and then directly promotes itself into a readiness/commercialization state.

The motivating shape is a qualification function that accepts a `candidate` object, trusts `candidate.diagnostic_passed`, removes `PRIOR_DIAGNOSTIC_PASS_REQUIRED`, and returns `QUALIFIED_FOR_OWNER_SALES_REVIEW`. Canonicalization or hashing proves that the candidate was represented consistently; it does not make the candidate an independent authority for its own prerequisite.

## What it detects

The scanner supports Python, JavaScript/MJS/CJS, TypeScript/TSX/JSX, JSON, and lightweight YAML hints. It looks for candidate-like inputs; readiness fields such as `*_passed`, `approved`, `verified`, `ready`, `qualified`, or `authorized`; promotion sinks containing states such as `READY`, `QUALIFIED`, `AUTHORIZED`, `PROVEN`, `RELEASE`, `SUBMIT`, or `SALES`; and the absence of independently consumed authority/reference/retained-root/receipt/source evidence in the gate.

A direct gate such as `candidate.diagnostic_passed && diagnosticReceipt.verified` is a negative control because the promotion consumes an independent receipt. In Python, simple locals derived from an authority parameter before the gate are also tracked. Structured-data rules are intentionally hints, not semantic proofs.

## Findings are not authority

Every report states `authorization_scope=REVIEW_SIGNAL_ONLY`, `mutation_authorized=false`, and `buyer_state_authorized=false`. A finding means **review the authority boundary**. It is not proof of exploitability, a compliance failure, buyer state, an invalid sale, or permission to mutate anything. A clean scan is likewise not proof that an application is safe or authorized.

## Exact-fingerprint baseline

Legacy findings may be acknowledged with `authority-boundary-lint-baseline/v1`:

```json
{
  "schema": "authority-boundary-lint-baseline/v1",
  "findings": [
    {
      "rule_id": "ABL001_SELF_ATTESTED_PROMOTION",
      "path": "path/to/file.js",
      "content_fingerprint": "<64 lowercase hex sha256>"
    }
  ]
}
```

Suppression is exact on rule + path + content fingerprint. If the gated bytes change, the finding returns with `baseline_drift=true`; a broad path/rule waiver cannot hide later drift.

## CLI

```sh
python -m tools.authority_boundary_lint path/to/changed.py path/to/changed.js --root . \
  --json-out /tmp/authority-boundary-lint.json \
  --markdown-out /tmp/authority-boundary-lint.md
```

The default is advisory exit `0` even when findings exist. `--fail-on-findings` is available for consumers that deliberately choose a blocking policy; the bundled Commons workflow does **not** make findings merge authority.

## Deterministic receipt

Findings are sorted by stable path/line/rule keys. JSON is canonicalized to compute `receipt_digest` (SHA-256) before pretty rendering. Each finding includes path, line, rule, candidate field, promotion sink, evidence text, and a content fingerprint.

## Verification

```sh
python -m py_compile tools/authority_boundary_lint/*.py
python -B -m unittest -v tools.authority_boundary_lint.test_lint
python -O -B -m unittest -v tools.authority_boundary_lint.test_lint
```

Hostile fixtures reproduce the freight `diagnostic_passed` pattern; negative controls require an independent diagnostic receipt in the promotion gate.

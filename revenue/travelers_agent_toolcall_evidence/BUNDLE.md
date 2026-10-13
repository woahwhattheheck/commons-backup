# End-to-end evidence bundles

The receipt verifier and the ledger/root verifiers answer different questions:

- **receipt verification** asks whether each receipt is exactly reproducible from the supplied synthetic envelope under the validated policy; and
- **ledger/root verification** asks whether a set of already-created receipt bytes is preserved by the expected append-only hash chain and daily Merkle commitment.

A structurally valid chain is not, by itself, proof that a receipt was policy-correct. A caller could alter a detached receipt and recompute every structural hash. `bundle.py` closes that composition gap by requiring both layers.

## Build

```bash
python -m revenue.travelers_agent_toolcall_evidence.bundle_cli build envelopes.jsonl 2026-09-17 > bundle.json
```

The bundle contains the canonical receipts, ledger, daily root, SHA-256 commitments to the input-envelope list and each evidence layer, and a final bundle digest.

## Verify

```bash
python -m revenue.travelers_agent_toolcall_evidence.bundle_cli verify envelopes.jsonl bundle.json
```

Verification succeeds only if all of the following are simultaneously true:

1. receipts exactly recompile from the supplied envelopes and validated policy;
2. the ledger is byte-identical to the canonical chain built from those verified receipts;
3. the full ledger chain verifies;
4. the daily root is byte-identical to a root built from that verified ledger;
5. the root verifies against the chain;
6. envelope, receipt, ledger and root layer digests match; and
7. the final bundle digest matches the whole artifact.

The hostile suite changes a decision and reason, rewrites the receipt digest, rebuilds the entire chain and Merkle root, rewrites every layer digest and the bundle digest, and still requires rejection because the forged receipt no longer recompiles from the source envelope. It performs the same end-to-end rewrite after widening a detached receipt into a fake production/current authority claim and requires rejection.

This remains synthetic/nonproduction replay evidence. A valid bundle does not execute a tool and does not prove a present-time production authorization, a real Travelers approval, a production customer-data event, payment, award, or revenue.

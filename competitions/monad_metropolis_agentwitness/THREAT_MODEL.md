# AgentWitness threat model

## Protected invariant

For one exact triggering event, **at most one claimant wins the on-chain claim slot**. All applications deriving the same v1 descriptor must derive the same `event_key`.

## What the chain proves

The registry can prove that:

1. a specific address was the first claimant for an `event_key`;
2. the claimant committed to a specific intent hash;
3. that same claimant later committed one first outcome;
4. only an `OUTCOME_UNKNOWN` first outcome can be reconciled once;
5. all state transitions are publicly indexable through events.

## What the chain does not prove

A claim is **not** evidence that an external action was authorized, attempted, accepted, or paid. An outcome hash is a commitment to off-chain evidence, not automatic verification of Gmail, Stripe, a deployment provider, a customer, or a bank.

The surrounding application must independently establish authorization and provider truth.

## Main threats and controls

### Alias race

**Threat:** two agents change draft text, price, recipient, route, worker name, or retry label to evade a mutex.

**Control:** those fields are absent from the closed event schema. The key is bound only to version/network/namespace/provider/exact event ID.

### Private-data leakage

**Threat:** raw email body, credentials, customer data, prompts, or payment details become permanently public.

**Control:** the event descriptor accepts only bounded opaque identifiers. Intent and outcome payloads are committed as domain-separated hashes.

### Provider-ID aliasing

**Threat:** `Gmail`, `googlemail`, and `gmail-api` become three keys for one provider.

**Control:** provider is a strict lowercase token; applications should maintain their own reviewed provider registry. AgentWitness never silently normalizes aliases because hidden normalization can merge distinct authority domains.

### Cross-application replay

**Threat:** an event key valid for one application is replayed in another.

**Control:** `network` and `namespace` are key material. Applications should allocate stable namespaces and never reuse a namespace with changed semantics.

### Claim squatting

**Threat:** an attacker who knows an event key claims it first.

**Control:** v1 intentionally makes claimant authorization an application-layer concern. Production deployments should place the registry behind an application allowlist, account-abstraction policy, or signature-verifying router when the event IDs themselves are observable. This source carrier does not pretend an open public registry solves authorization.

### Provider timeout / ambiguous result

**Threat:** a provider performs a side effect but the caller times out, then retries and duplicates it.

**Control:** finalize `OUTCOME_UNKNOWN`, reconcile provider truth, and never mint a new event ID merely to retry. Only a genuinely new external event creates a new key.

### Outcome rewriting

**Threat:** a claimant overwrites a failed outcome with a more favorable one.

**Control:** first outcome is immutable. Only `OUTCOME_UNKNOWN` admits exactly one explicit resolution with its own evidence hash and event.

### Hash substitution

**Threat:** receipt claims are edited after generation.

**Control:** deterministic canonical JSON plus domain-separated SHA-256 gives a reproducible receipt digest; changing any receipt field changes the digest.

## Explicit non-goals for v1

- custody or transfer of user funds;
- arbitrary external calls;
- proof that a private off-chain payload is truthful;
- identity KYC / proof-of-personhood;
- cross-chain global consensus;
- provider API integration;
- autonomous authorization to send, pay, deploy, or sign.

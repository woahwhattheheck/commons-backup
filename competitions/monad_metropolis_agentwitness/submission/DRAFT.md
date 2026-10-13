# Monad Metropolis submission draft — AgentWitness

## Track

Trust, Identity & AI Infrastructure.

## One sentence

AgentWitness is a Monad-backed one-event/one-claim rail that lets concurrent AI agents race safely for an irreversible side effect and leaves a privacy-preserving audit trail of who won and what outcome was later observed.

## The problem

Multi-agent systems are increasingly capable of sending messages, paying invoices, deploying software, booking resources, and mutating production systems. Their coordination layer is often eventually consistent. Two independent agents can both perform a correct preflight and still execute the same real-world action twice.

Ordinary idempotency keys help only when every provider supports them and every caller chooses the same key. Human messaging, heterogeneous SaaS tools, and cross-agent workflows often do not satisfy that assumption.

## The product

AgentWitness separates three facts that agent systems routinely collapse:

1. **claim** — who won the right to attempt one event;
2. **outcome** — what the external provider appeared to do;
3. **reconciliation** — what authoritative provider evidence later established after an ambiguous result.

A minimal Solidity registry stores only content digests and the winner address. The off-chain reference library derives a deterministic event key from a closed schema and provides byte-for-byte reproducible receipts. Private drafts and customer payloads never need to touch the chain.

## Why Monad

The primitive benefits from a low-latency shared ordering surface: the safety property comes from all concurrent actors contending on one chain state instead of trusting eventually consistent bot-to-bot coordination. The application is intentionally small at the contract layer so the critical race is easy to audit.

## Demo story

1. Load one synthetic Gmail reply event.
2. Launch 64 concurrent synthetic agents with different private drafts and different addresses.
3. All compute the same event key.
4. Exactly one `claim` succeeds; 63 lose without calling the external provider.
5. Winner records `OUTCOME_UNKNOWN` to model a provider timeout.
6. A provider reconciliation later resolves the outcome exactly once.
7. Show the public receipt: hashes + winner + state, with no email body or customer data.
8. Repeat with a new human event ID and show that the new event is independently claimable.

## What is already implemented in the source carrier

- Solidity registry state machine;
- deterministic canonical event/key compiler;
- intent/outcome/receipt domain separation;
- executable thread-safe reference model;
- concurrent race harness;
- hostile tests for aliasing, unauthorized finalization, double-finalization, reconciliation rules, strict JSON, zero hashes, domain separation, receipt tamper and privacy leakage;
- threat model.

## Remaining external gates before a truthful submission

- capture controlling Monad Metropolis registration/rules and exact prize/bounty conditions;
- register through the official provider and accept rules as the human entrant where required;
- choose/create an authorized Monad wallet without exposing a private key to repository/tool logs;
- compile the Solidity contract with an authoritative Solidity toolchain and run EVM-level tests;
- deploy to the competition-designated Monad network if required;
- capture transaction/contract explorer receipt;
- build a public front-end against the deployed contract;
- record a short demo;
- submit through the official hackathon surface.

Until those events actually happen, state remains **SOURCE BUILT / NOT DEPLOYED / NOT REGISTERED / NOT SUBMITTED / $0 AWARDED**.

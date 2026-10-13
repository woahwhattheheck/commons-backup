# Mermail RFQ Agent — evidence-bound vendor quote workflow

A companion skill for the Superteam **Build and Demo a Mermail Agent Skill** bounty. It turns Mermail into a procurement/RFQ control plane without giving the agent purchasing or payment authority.

## Why this use case

Procurement is fundamentally an email-identity and thread-integrity problem: multiple vendors reply with changing prices, lead times, MOQs, shipping/tax caveats, and amendments. A useful agent must keep those facts attached to the right sender and thread and must not turn “cheapest” into “authorized to buy.”

This package combines:

- a Mermail companion skill that routes to the platform's existing inbox/composition tools;
- a deterministic, network-free quote ledger with append-only amendment handling;
- timeline custody that rejects pre-round solicitations and pre-solicitation quotes, and makes comparison reports true historical `as-of` snapshots that cannot consume future quote evidence;
- strict JSON requirements commitment: values JSON would silently erase/coerce are rejected instead of being allowed to alias the RFQ digest;
- one-to-one source-message custody: a Mermail `sourceEmailId` cannot back multiple conflicting quote identities or amendments;
- hostile tests for spoofed sender, thread drift, quote-id collisions, source-email replay, requirements-digest aliasing, version/time regression, future-evidence leakage, missing price, expiry, MOQ mismatch, and cross-currency ranking;
- a synthetic demo that performs no live email, wallet, purchase, or payment action.

## Run it

Requires Node.js 22+.

```bash
npm test
npm run demo
```

## Demo story

1. Buyer freezes an RFQ for 1,000 FKM-75 precision gaskets.
2. The skill sends isolated solicitations only after exact preview and fresh approval.
3. Mermail replies are read through bounded inbox/thread tools and treated as untrusted evidence.
4. The ledger binds each quote to the expected sender + original thread + solicitation timeline + unique source email identity, preserves quote versions, and reports missing terms.
5. A comparison at time `T` uses only quote versions received on or before `T`; later amendments remain invisible until their recorded receipt time.
6. Same-currency explicit unit prices can be ranked for review, but output always states `awardAuthorized: false` and `paymentAuthorized: false`.

The checked-in demo starts at step 4 with synthetic Mermail identities, so validation never creates external side effects.

## Layout

- `skill/SKILL.md` — agent workflow and authority boundary
- `skill/agents/openai.yaml` — OpenAI/Codex skill metadata + Mermail MCP dependency
- `skill/references/` — tool routing and security contracts
- `src/quote-ledger.mjs` — deterministic commercial evidence ledger
- `test/quote-ledger.test.mjs` — hostile regression suite
- `demo/` — synthetic end-to-end comparison fixture

## Submission notes

This is intentionally a **community companion** rather than a new official tool-owning domain: it recombines the official Mermail inbox and composition capabilities while respecting their existing ownership and approval rules. A separate upstream proposal can be used if Mermail maintainers want to graduate the workflow into the official skill catalog.

# Source truth — IntentLease

## Proven by this carrier

- Deterministic single-writer lease engine exists.
- Collision identity binds action kind, opaque target, purpose, and business-object generation.
- Exact request replay is non-mutating and changed replay material fails closed.
- Expiry/reclaim, release, transfer, privacy fencing, receipt hashes, and a hostile concurrency race have local tests.
- OpenServ adapter uses current v2 SDK shapes documented in `openserv-labs/sdk`: `Agent`, Zod input schemas, a run-less structured-output capability, and `run(agent)`.
- Side-effect authority is permanently false in every core receipt.

## Not proven here

- OpenServ account registration or data-collection eligibility configuration.
- Availability of an `OPENSERV_API_KEY` in any deployment environment.
- A live SERV Reasoning/provider execution.
- Cross-process/distributed lease durability. The demo/core is a single-registry process; production deployment should put the same transition contract behind a transactional shared store.
- Competition submission, eligibility acceptance, judging, prize, payout, customer sale, or recognized revenue.

## Review rule

Do not upgrade any item in “Not proven here” without a provider/external receipt tied to the exact source generation being claimed.

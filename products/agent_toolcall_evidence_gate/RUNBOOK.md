# Deployment runbook

1. Keep policy and approval-authority generations in an operator-controlled store. Publish their canonical SHA-256 roots independently of request-producing agents.
2. Keep the replay ledger append-only. Retain its exact head in a monotonic/transactional store. Do not accept a ledger head chosen by the request producer.
3. Construct a request with a globally unique operation key and trace ID. Do not reuse either across retries.
4. Run the gate immediately before the side effect. A HOLD is terminal for that attempted request generation until new evidence/policy creates a new request.
5. If `EXECUTE_ALLOWED`, atomically reserve the operation against the receipt's `expected_pre_reservation_ledger_head`. If compare-and-swap fails, re-read the ledger and re-evaluate; do not blind retry the provider.
6. Invoke the provider exactly once from the reservation winner. Persist the terminal outcome as a ledger event. Provider timeout/ambiguous persistence must be recorded as an uncertain terminal outcome; do not infer SENT or retry automatically.
7. A policy, authority, agent-version, request, ledger-head, or approval-scope change requires a new evaluation. Never edit an old receipt.

Commercial use: this gate can serve as the preflight layer in an agent integration/acceptance engagement, but the software contains no customer acceptance, pricing agreement, contract, payment, or revenue authority.

# Judge script (under three minutes)

1. **Problem (20s)** — A caller can fabricate a plausible coding-agent transcript; a hash alone proves only that the transcript stayed unchanged afterward.
2. **Bounded task (20s)** — Show one task, one repository snapshot, one allowed path, structured reproduction/regression commands.
3. **Structural proof (30s)** — `verify` checks full root delta, exact before/after bytes, phase ordering, chained receipts and authority ceilings, but labels caller receipt provenance unauthenticated.
4. **Executor replay (35s)** — `demo-verify` uses a verifier-owned fixed hermetic executor. It reruns every claimed command by exact repo digest and requires exact result equality before emitting `EXECUTOR_REPLAY_VERIFIED`.
5. **Patch boundary (25s)** — Show the one-line `//` → `/` change; hide a second file mutation and verification fails.
6. **Transcript attack (25s)** — Reseal a plausible success output. Structural verification can still describe it as self-consistent, while executor replay rejects the mismatch. That separation is intentional.
7. **Nebius/NVIDIA path (25s)** — Show outer+inner pinned NVIDIA model, deterministic request, environment credential only at injected transport. No secret enters evidence.
8. **Boundary (20s)** — Live Nebius runtime, provider attestation, deployment, video and Devpost remain separately evidenced gates; no prize/payment/revenue claim.

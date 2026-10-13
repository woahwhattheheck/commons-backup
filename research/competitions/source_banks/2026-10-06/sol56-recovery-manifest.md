# Competition source banks — 2026-10-06

Model / seat: GPT-5.6 Sol / recovery-competition / ChatGPT cloud harness.

This manifest records three source-complete packets produced and locally validated in this seat. Exact archives are retained in the owner Google Drive under `Swarm Recovery/`.

## GitLab Life After Code — native Duo flow R1

- Drive file: `gitlab-life-after-code-native-flow-r1.zip`
- Drive file ID: `1t83G4gO7XtfB6RlCRPcZD6CIDvUrESaL`
- SHA-256: `c83d5f3325868450f6c3afc9f0e7a3b6f39af347790f5b16ffde23dd4132b5d7`
- Validation: focused static flow-contract checker PASS; 5 focused tests PASS; Python compilation PASS.
- Boundary: no live GitLab Duo execution or hosted-CI green claim.
- Intended source path: `research/competitions/gitlab_life_after_code/native_duo_flow_r1/`.

## Gemma 4 Developer Agent — G4-B router/scheduler R1

- Drive file: `gemma4-router-scheduler-r1.zip`
- Drive file ID: `1Y01M7IyhQlNIUKmq_aJIiOjCl6wJwuMG`
- SHA-256: `7f1a85f6417e533b049ce689ef9071af1880376bcab7353050d74046b2b5748c`
- Validation: 6 focused tests PASS; Python compilation PASS.
- Frozen-sample invariant: deterministic order test → narrow bug → build/config → API → navigation; 2,760 seconds allocated while preserving global reserve.
- Boundary: scheduler-invariant evidence only; no competition pass-rate claim.

## Gemma 4 Developer Agent — G4-D verifier/repair R1

- Drive file: `gemma4-verifier-repair-r1.zip`
- Drive file ID: `1qXTCliOHd2byjjLNR9wjjVblaNykXI5d`
- SHA-256: `7a3beecae187e01c47aad7fa19967df011742e022777709275950e495e90cba6`
- Validation: 6 focused tests PASS; Python compilation PASS.
- Frozen-fixture invariant: selects 32s targeted validation set, retains 180s broad suite as fallback, and stops on repeated identical failures, infrastructure failures, repair caps, or lower expected value than queue switch.
- Boundary: verifier/scheduler invariant evidence only; no hidden-eval or pass-rate claim.

## Publication note

During this seat, GitHub read/authentication was healthy, while branch/tree mutations were intermittently stopped before provider execution by the platform safety layer. The Drive artifacts above are the durable exact-byte carriers; this manifest is the recovery index for a healthy publisher.

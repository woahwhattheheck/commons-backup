# Public experiment matrix

Use this only after authorized model/evaluator access. Keep selection and holdout generations physically separate.

| Family | Surface | Public hypothesis | Required ablation | Promotion rule |
|---|---|---|---|---|
| prompt baseline | input | bounded honesty instruction reduces dishonest responses without broad capability loss | empty/no-op prompt | must beat no-op on every target model's dev mean |
| activation vector | state | participant-trained steering vector adds robust benefit beyond prompt-only | prompt-only; state-only; composed | composed worst-model mean must improve without larger max regression |
| decoding guard | output | bounded decoding policy reduces dishonest continuations not caught upstream | same pipeline without output guard | must not trade one model's failure for aggregate-only gain |
| structure adapter | structure | lightweight model-local adapter can generalize better than prompt/state alone | same training split and budget | provenance + artifact digest required; no holdout selection |
| composition order | multi-surface | intervention order has causal impact | all safe order permutations | choose on TRAIN/DEV only; disclose HOLDOUT once after freeze |

For every run record: exact model identifier/revision, public-vs-private evidence class, intervention fingerprint, artifact digest/source/license, evaluator revision, split, replicate/seed, normalized dishonesty reduction, capability regression vector, wall time, and execution environment. Do not publish tuned competitive artifacts if doing so would compromise the intended evaluation; this public carrier is tooling and protocol, not a final secret submission.

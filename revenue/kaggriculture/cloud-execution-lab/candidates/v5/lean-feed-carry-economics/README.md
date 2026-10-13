# TITAN V5 lean-feed carry economics

Additive research/evaluation tooling for issue #14337. The package is default inert and does not alter a runtime policy, release pointer, archive, competition submission, or provider state.

It provides three comparison arms (`MIN_PROVABLE`, `CURRENT_POLICY`, and `PLUS_ONE`), validates complete paired evidence across both seats and multiple opponent regimes, records decision-window telemetry, and emits deterministic JSON, JSONL, CSV, Markdown, and manifest artifacts.

Candidate economics and promotion authority are intentionally separate. The base evaluator may identify a research candidate, but the official CLI routes through `lean_feed_hardening.py`. While the exact D2 archive member bytes remain unavailable, synthetic-positive candidate economics are reported only as `SOURCE_MODEL_BLOCKED`: promotion stays unauthorized and synthetic census/delta/run arrays are suppressed rather than exposed as if they described the official engine. Conservative candidate `NO_PROMOTION` results remain conservative.

The included examples are synthetic contract fixtures. They exercise the evidence and hardening contracts only; they are not official-engine results and cannot authorize promotion.

Pinned D2 archive identity: `3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8`.

## D2 archive recovery gate

`d2_archive_authority.py` is the fail-closed ingress boundary for the still-missing exact D2 archive. It authenticates the raw 424,145-byte gzip tarball and its 94-member identity before reading any member, never extracts or executes archive content, rejects unsafe/ambiguous tar structures, and binds `main.py`, the retained runtime member, and retained `operating_stock.py` lineage by cryptographic identity.

A successful source check is intentionally **not** a promotion: the verifier keeps `candidate_build_authorized=false` and `promotion_authorized=false`. The WHEAT-only census, prospective development panel, untouched holdout, independent review, and explicit code-retained authority root remain separate requirements. See `D2_RECOVERY.md` and `D2_RECOVERY_STATUS.json`.

## Local commands

```bash
python -m py_compile feed_carry_oracle.py lean_feed_hardening.py d2_archive_authority.py test_feed_carry_oracle.py test_promotion_gate_hardening.py test_d2_archive_authority.py test_cli_smoke.py examples/generate_synthetic_contracts.py
python -m unittest -v test_feed_carry_oracle.py test_promotion_gate_hardening.py test_d2_archive_authority.py test_cli_smoke.py
python -O -m unittest -v test_d2_archive_authority.py
python d2_archive_authority.py
python examples/generate_synthetic_contracts.py
python feed_carry_oracle.py examples/synthetic_positive_contract.json --out /tmp/lean-feed-positive
python feed_carry_oracle.py examples/synthetic_no_redeployment.json --out /tmp/lean-feed-negative
```

Expected fixture conclusions through the official CLI:

- positive contract: candidate economics `PROMOTE_RESEARCH_CANDIDATE`, final conclusion `SOURCE_MODEL_BLOCKED`, `authority_verified=false`, synthetic economic arrays empty
- no-redeployment contract: candidate economics `NO_PROMOTION`, final conclusion `NO_PROMOTION`

Official promotion remains blocked until exact D2 source bytes and normalized evidence are authenticated, independently reviewed, and their authority root is explicitly retained by code review.

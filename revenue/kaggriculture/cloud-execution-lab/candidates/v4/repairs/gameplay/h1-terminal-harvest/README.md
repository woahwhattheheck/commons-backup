# H1 terminal-harvest donor custody

Canonical V4 source custody for the reviewed H1 first-decay annual HARVEST rescue from legacy PR #12621.

- Legacy owner head: `d21734e6a9e12c6019c7f4eae62361d2ebebee7b`
- Exact source blob: `5814bf4ae43573f5a4ecc5edb76e0ca70958e05a`
- Exact focused test blob: `a4ead93da00b6f000f6255f614423aee30f0b7bc`
- Legacy lane status: source-safe/default-OFF evidence only; no economic promotion claim.

The theorem is deliberately narrow: in the standard 24-turn/day engine, unit actions execute before plant decay. For annual WHEAT/CARROT/MELON at exact `max_lifespan_step == step` in the late window, authored `WATER` can be replaced by `HARVEST` only when mature physical yield is already present. Malformed, nonstandard, disabled and non-matching states preserve parent identity.

This directory preserves reviewed donor bytes and provenance only. It does **not** execute the legacy `apply_v4.py`, wire a current-production key, enable the mechanism, modify runtime/config/defaults, or authorize production/Kaggle promotion. Any semantic port into the current `titan_runtime` ABI requires a separate current-engine validation and composition receipt.

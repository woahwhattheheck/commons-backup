# SPDX-License-Identifier: Apache-2.0
"""Promotion queue service for Titan V3 candidate promotion.

Orchestration and receipt layer around the existing
``titan-v3-paired-game-gate`` scripts. The queue never reimplements the
gate: it pins inputs, builds per-predecessor gate bundles, shells out to
the real gate scripts, and seals the outcome in a tamper-evident receipt.
"""

SCHEMA_VERSION = 1
POLICY_VERSION = "promotion-policy/v1"
RECEIPT_TYPE = "titan-promotion-queue-receipt/v1"
GATE_DIR_NAME = "titan-v3-paired-game-gate"

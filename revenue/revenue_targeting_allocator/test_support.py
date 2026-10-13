from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import revenue.revenue_targeting_allocator.allocator as allocator_module
from revenue.revenue_targeting_allocator.allocator import (
    AllocationError,
    compile_portfolio,
    validate_input,
    verify_bundle,
)

FIXTURE = Path(__file__).with_name("synthetic_portfolio.json")


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def candidate(**changes):
    base = {
        "opportunity_id": "opp-a",
        "offer_id": "offer-a",
        "currency": "USD",
        "commercial_value_minor": 100_000,
        "route_state": "VERIFIED_CLEAR",
        "relationship_state": "CLEAR",
        "collision_state": "CLEAR",
        "freshness_state": "FRESH",
        "buyer_stage": "PUBLIC_FIT",
        "buyer_stage_state": "VERIFIED",
        "fit_state": "STRONG",
        "delivery_state": "READY",
        "evidence_bundle_sha256": digest("base"),
    }
    base.update(changes)
    return base


def document(*rows):
    return {
        "schema": "revenue-targeting-allocator-input/v1",
        "portfolio_id": "test-port",
        "candidates": list(rows),
    }

class AllocatorBase(unittest.TestCase):
    def assertHold(self, **changes):
        out, _, _ = compile_portfolio(document(candidate(**changes)))
        row = out["rows"][0]
        self.assertEqual(row["queue"], "HOLD")
        self.assertTrue(row["hold_reasons"])
        self.assertIsNone(row["rank"])
        return row

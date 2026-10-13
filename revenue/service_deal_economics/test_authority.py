from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from . import authority as a
from .cli import build_parser

NOW = datetime(2026, 9, 13, 21, 45, 0, tzinfo=timezone.utc)
NOW_TEXT = "2026-09-13T21:45:00Z"
ISSUED = "2026-09-13T20:00:00Z"
EXPIRES = "2026-09-14T20:00:00Z"
START = "2026-09-15T00:00:00Z"
END = "2026-09-25T00:00:00Z"
KEY_HEX = "ab" * 32


def packet() -> dict:
    return {
        "schema": "commons.service-deal-economics.input/v1",
        "policy": {
            "policy_id": "owner-policy", "generation": 7, "currency": "USD",
            "minimum_gross_margin_bps": 3000, "risk_reserve_bps": 1000,
            "snapshot_max_age_hours": 24, "quote_validity_hours": 72,
            "source_ref": "owner-policy-source", "source_sha256": "1" * 64,
            "observed_at": "2026-09-13T20:30:00Z",
        },
        "deal": {
            "deal_id": "deal-1", "scope_id": "scope-v1", "scope_revision": 3,
            "currency": "USD", "target_price_cents": 700000,
            "delivery_start": START, "delivery_end": END,
            "source_ref": "scope-source", "source_sha256": "2" * 64,
            "observed_at": "2026-09-13T20:30:00Z",
            "items": [
                {"item_id": "implementation", "planned_minutes": 600,
                 "internal_rate_cents_per_hour": 12000, "external_cost_cents": 30000,
                 "source_ref": "cost-impl", "source_sha256": "3" * 64,
                 "observed_at": "2026-09-13T20:30:00Z"},
                {"item_id": "acceptance", "planned_minutes": 900,
                 "internal_rate_cents_per_hour": 10000, "external_cost_cents": 50000,
                 "source_ref": "cost-accept", "source_sha256": "4" * 64,
                 "observed_at": "2026-09-13T20:30:00Z"},
            ],
        },
        "capacity": {
            "snapshot_id": "capacity-v1", "window_start": START, "window_end": END,
            "total_minutes": 3000, "reserved_minutes": 1000,
            "source_ref": "capacity-source", "source_sha256": "5" * 64,
            "observed_at": "2026-09-13T20:30:00Z",
        },
    }


def _mac(obj: dict, key: bytes, skip: str = "mac_sha256") -> str:
    payload = {k: obj[k] for k in sorted(set(obj) - {skip})}
    return hmac.new(key, a.canonical_json(payload).encode(), hashlib.sha256).hexdigest()


class HostAuthority:
    def __init__(self, root: Path):
        self.root = root
        self.key = root / "authority-key.json"
        self.registry = root / "current-authority.json"
        self.floor = root / "authority-floor.json"
        root.mkdir(parents=True, exist_ok=True)
        self.write_key()

    @property
    def paths(self): return (self.key, self.registry, self.floor)

    def write_key(self, key_hex: str = KEY_HEX, mode: int = 0o600):
        self.key.write_text(a.canonical_json({"schema": a.KEY_SCHEMA, "key_hex": key_hex}) + "\n", encoding="utf-8")
        if os.name == "posix": os.chmod(self.key, mode)

    def sign(self, p: dict, generation: int = 1, issued: str = ISSUED, expires: str = EXPIRES,
             subject: dict | None = None, *, write_floor: bool = True) -> dict:
        subject = subject or a.authority_subject(p)
        reg = {"schema": a.AUTHORITY_SCHEMA, "generation": generation, "issued_at": issued,
               "expires_at": expires, **subject, "mac_sha256": "0" * 64}
        reg["mac_sha256"] = _mac(reg, bytes.fromhex(KEY_HEX))
        self.registry.write_text(a.canonical_json(reg) + "\n", encoding="utf-8")
        if write_floor:
            floor = {"schema": a.FLOOR_SCHEMA, "generation": generation,
                     "registry_sha256": a.digest(reg), "mac_sha256": "0" * 64}
            floor["mac_sha256"] = _mac(floor, bytes.fromhex(KEY_HEX))
            self.floor.write_text(a.canonical_json(floor) + "\n", encoding="utf-8")
        return reg


class AuthorityTests(unittest.TestCase):
    def host(self):
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        h = HostAuthority(Path(td.name)); return h, patch.object(a, "_host_paths", return_value=h.paths)

    def test_candidate_only_ready_is_held_without_host_authority(self):
        p = packet()
        with tempfile.TemporaryDirectory() as td, patch.object(a, "_host_paths", return_value=(Path(td)/"k", Path(td)/"r", Path(td)/"f")):
            report = a._compile_current_at(p, NOW)
        self.assertEqual(report["calculation"]["candidate_disposition"], a.READY)
        self.assertEqual(report["state"], a.AUTHORITY_HOLD)
        self.assertFalse(report["input_authority"]["authenticated"])

    def test_valid_independent_authority_allows_ready(self):
        h, ctx = self.host(); h.sign(packet())
        with ctx:
            report = a._compile_current_at(packet(), NOW)
        self.assertEqual(report["state"], a.READY)
        self.assertTrue(report["input_authority"]["authenticated"])
        self.assertTrue(all(v is False for v in report["external_authority"].values()))

    def test_owner_policy_forgery_cannot_mint_ready(self):
        base = packet(); h, ctx = self.host(); h.sign(base)
        forged = copy.deepcopy(base); forged["policy"]["minimum_gross_margin_bps"] = 0; forged["policy"]["risk_reserve_bps"] = 0
        forged["policy"]["source_sha256"] = "9" * 64; forged["policy"]["observed_at"] = NOW_TEXT
        with ctx: report = a._compile_current_at(forged, NOW)
        self.assertEqual(report["state"], a.AUTHORITY_HOLD)
        self.assertIn("AUTHORITY_POLICY_SHA256_MISMATCH", report["reasons"])

    def test_cost_basis_forgery_cannot_mint_ready(self):
        base = packet(); h, ctx = self.host(); h.sign(base)
        forged = copy.deepcopy(base); forged["deal"]["items"][0]["internal_rate_cents_per_hour"] = 1; forged["deal"]["items"][0]["external_cost_cents"] = 0
        forged["deal"]["items"][0]["source_sha256"] = "8" * 64
        with ctx: report = a._compile_current_at(forged, NOW)
        self.assertEqual(report["state"], a.AUTHORITY_HOLD)
        self.assertIn("AUTHORITY_SCOPE_COST_SHA256_MISMATCH", report["reasons"])

    def test_capacity_inflation_cannot_mint_ready(self):
        base = packet(); h, ctx = self.host(); h.sign(base)
        forged = copy.deepcopy(base); forged["capacity"]["total_minutes"] = 99999999; forged["capacity"]["reserved_minutes"] = 0; forged["capacity"]["source_sha256"] = "7" * 64
        with ctx: report = a._compile_current_at(forged, NOW)
        self.assertEqual(report["state"], a.AUTHORITY_HOLD)
        self.assertIn("AUTHORITY_CAPACITY_SHA256_MISMATCH", report["reasons"])

    def test_retimestamp_and_rehash_still_changes_authority_subject(self):
        base = packet(); h, ctx = self.host(); h.sign(base)
        forged = copy.deepcopy(base)
        forged["deal"]["source_sha256"] = "6" * 64; forged["deal"]["observed_at"] = NOW_TEXT
        with ctx: report = a._compile_current_at(forged, NOW)
        self.assertEqual(report["state"], a.AUTHORITY_HOLD)

    def test_target_price_is_intended_decision_variable(self):
        base = packet(); h, ctx = self.host(); h.sign(base)
        changed = copy.deepcopy(base); changed["deal"]["target_price_cents"] = 800000
        self.assertEqual(a.authority_subject(base), a.authority_subject(changed))
        with ctx: report = a._compile_current_at(changed, NOW)
        self.assertTrue(report["input_authority"]["authenticated"])

    def test_registry_mac_tamper_holds(self):
        p = packet(); h, ctx = self.host(); reg = h.sign(p); reg["policy_sha256"] = "0" * 64
        h.registry.write_text(a.canonical_json(reg) + "\n")
        floor = json.loads(h.floor.read_text()); floor["registry_sha256"] = a.digest(reg); floor["mac_sha256"] = _mac(floor, bytes.fromhex(KEY_HEX)); h.floor.write_text(a.canonical_json(floor)+"\n")
        with ctx: report = a._compile_current_at(p, NOW)
        self.assertEqual(report["state"], a.AUTHORITY_HOLD)

    def test_floor_mac_tamper_holds(self):
        p = packet(); h, ctx = self.host(); h.sign(p); floor=json.loads(h.floor.read_text()); floor["generation"] += 1; h.floor.write_text(a.canonical_json(floor)+"\n")
        with ctx: self.assertEqual(a._compile_current_at(p, NOW)["state"], a.AUTHORITY_HOLD)

    def test_floor_registry_digest_blocks_same_generation_fork(self):
        p = packet(); h, ctx = self.host(); h.sign(p, generation=4); floor_before=h.floor.read_text()
        h.sign(p, generation=4, issued="2026-09-13T20:01:00Z", write_floor=False)
        h.floor.write_text(floor_before)
        with ctx: self.assertEqual(a._compile_current_at(p, NOW)["state"], a.AUTHORITY_HOLD)

    def test_floor_generation_mismatch_holds(self):
        p=packet(); h,ctx=self.host(); h.sign(p,generation=3); floor=json.loads(h.floor.read_text()); floor["generation"]=2; floor["mac_sha256"]=_mac(floor,bytes.fromhex(KEY_HEX)); h.floor.write_text(a.canonical_json(floor)+"\n")
        with ctx: self.assertEqual(a._compile_current_at(p,NOW)["state"],a.AUTHORITY_HOLD)

    def test_future_authority_holds(self):
        p=packet(); h,ctx=self.host(); h.sign(p,issued="2026-09-13T22:00:00Z",expires="2026-09-14T22:00:00Z")
        with ctx: r=a._compile_current_at(p,NOW)
        self.assertEqual(r["state"],a.AUTHORITY_HOLD); self.assertIn("AUTHORITY_NOT_YET_VALID",r["reasons"])

    def test_expired_authority_holds(self):
        p=packet(); h,ctx=self.host(); h.sign(p,issued="2026-09-12T20:00:00Z",expires="2026-09-13T21:44:59Z")
        with ctx: r=a._compile_current_at(p,NOW)
        self.assertEqual(r["state"],a.AUTHORITY_HOLD); self.assertIn("AUTHORITY_EXPIRED",r["reasons"])

    def test_valid_current_receipt_verifies(self):
        p=packet(); h,ctx=self.host(); h.sign(p,generation=9)
        with ctx:
            report=a._compile_current_at(p,NOW)
            result=a._verify_current_at(p,report,NOW)
        self.assertEqual(result["state"],"CURRENT_VERIFIED")

    def test_new_generation_supersedes_historical_receipt(self):
        p=packet(); h,ctx=self.host(); h.sign(p,generation=9)
        with ctx: report=a._compile_current_at(p,NOW)
        h.sign(p,generation=10,issued="2026-09-13T21:00:00Z")
        with ctx: result=a._verify_current_at(p,report,NOW)
        self.assertTrue(result["historical_receipt_valid"])
        self.assertEqual(result["state"],"STALE_OR_AUTHORITY_SUPERSEDED")

    def test_same_generation_new_registry_root_supersedes(self):
        p=packet(); h,ctx=self.host(); h.sign(p,generation=9)
        with ctx: report=a._compile_current_at(p,NOW)
        h.sign(p,generation=9,issued="2026-09-13T20:01:00Z")
        with ctx: result=a._verify_current_at(p,report,NOW)
        self.assertEqual(result["state"],"STALE_OR_AUTHORITY_SUPERSEDED")

    def test_packet_tamper_breaks_historical_receipt(self):
        p=packet(); h,ctx=self.host(); h.sign(p)
        with ctx: report=a._compile_current_at(p,NOW)
        changed=copy.deepcopy(p); changed["deal"]["target_price_cents"] += 1
        with ctx: result=a._verify_current_at(changed,report,NOW)
        self.assertEqual(result["state"],"INVALID_HISTORICAL_RECEIPT")

    def test_report_tamper_breaks_historical_receipt(self):
        p=packet(); h,ctx=self.host(); h.sign(p)
        with ctx: report=a._compile_current_at(p,NOW)
        report["state"]="READY_FOR_OWNER_QUOTE_REVIEW" if report["state"] != a.READY else "HOLD_MARGIN"
        with ctx: self.assertEqual(a._verify_current_at(p,report,NOW)["state"],"INVALID_HISTORICAL_RECEIPT")

    def test_embedded_registry_digest_cannot_be_rewritten_and_resealed(self):
        p=packet(); h,ctx=self.host(); h.sign(p,generation=2)
        with ctx: report=a._compile_current_at(p,NOW)
        report["input_authority"]["registry_sha256"] = "f" * 64
        base={k:v for k,v in report.items() if k!="receipt_sha256"}; report["receipt_sha256"]=a.digest(base)
        with ctx: self.assertFalse(a._historical_valid(p,report))

    def test_missing_authority_hold_remains_historically_reproducible(self):
        p=packet()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); paths=(root/"k",root/"r",root/"f")
            with patch.object(a,"_host_paths",return_value=paths): report=a._compile_current_at(p,NOW)
            h=HostAuthority(root); h.sign(p)
            with patch.object(a,"_host_paths",return_value=h.paths):
                self.assertTrue(a._historical_valid(p,report))
                self.assertEqual(a._verify_current_at(p,report,NOW)["state"],"STALE_OR_AUTHORITY_SUPERSEDED")

    def test_key_rotation_fails_closed_for_old_receipt(self):
        p=packet(); h,ctx=self.host(); h.sign(p)
        with ctx: report=a._compile_current_at(p,NOW)
        h.write_key("cd"*32)
        with ctx: self.assertEqual(a._verify_current_at(p,report,NOW)["state"],"INVALID_HISTORICAL_RECEIPT")

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics")
    def test_key_permissions_must_be_owner_only(self):
        p=packet(); h,ctx=self.host(); h.sign(p); os.chmod(h.key,0o644)
        with ctx: self.assertEqual(a._compile_current_at(p,NOW)["state"],a.AUTHORITY_HOLD)

    @unittest.skipUnless(hasattr(os,"symlink") and hasattr(os,"O_NOFOLLOW"), "symlink/no-follow unavailable")
    def test_symlinked_key_refused(self):
        p=packet(); h,ctx=self.host(); h.sign(p); real=h.root/"real-key.json"; h.key.rename(real); os.symlink(real,h.key)
        with ctx: self.assertEqual(a._compile_current_at(p,NOW)["state"],a.AUTHORITY_HOLD)

    def test_extra_registry_key_rejected(self):
        p=packet(); h,ctx=self.host(); reg=h.sign(p); reg["surprise"]=1; h.registry.write_text(a.canonical_json(reg)+"\n")
        floor=json.loads(h.floor.read_text()); floor["registry_sha256"]=a.digest(reg); floor["mac_sha256"]=_mac(floor,bytes.fromhex(KEY_HEX)); h.floor.write_text(a.canonical_json(floor)+"\n")
        with ctx: self.assertEqual(a._compile_current_at(p,NOW)["state"],a.AUTHORITY_HOLD)

    def test_external_authority_always_false_on_hold(self):
        with tempfile.TemporaryDirectory() as td, patch.object(a,"_host_paths",return_value=(Path(td)/"k",Path(td)/"r",Path(td)/"f")):
            r=a._compile_current_at(packet(),NOW)
        self.assertTrue(all(v is False for v in r["external_authority"].values()))

    def test_markdown_states_candidate_math_is_not_authority(self):
        p=packet(); h,ctx=self.host(); h.sign(p)
        with ctx: r=a._compile_current_at(p,NOW)
        text=a.render_current_markdown(r)
        self.assertIn("not authority by itself",text)
        self.assertIn("Candidate JSON hashes/timestamps cannot mint it",text)

    def test_package_namespace_does_not_expose_legacy_compile_report_name(self):
        import revenue.service_deal_economics as package
        self.assertFalse(hasattr(package, "compile_report"))
        self.assertTrue(hasattr(package, "compile_arithmetic_report"))
        self.assertTrue(hasattr(package, "compile_current"))

    def test_cli_has_no_authority_key_time_or_provisioning_switch(self):
        parser=build_parser()
        for argv in (["compile","in","out","--as-of",NOW_TEXT],["compile","in","out","--authority","x"],["verify","in","out","--key","x"],["provision"]):
            with self.assertRaises(SystemExit): parser.parse_args(argv)

    @unittest.skipUnless(os.name == "posix" and a.pwd is not None, "POSIX account home semantics")
    def test_fixed_root_ignores_home_environment(self):
        with patch.dict(os.environ,{"HOME":"/tmp/attacker-home"}):
            self.assertNotEqual(str(a._fixed_host_root()),"/tmp/attacker-home/.config/commons/service-deal-economics")

    def test_authority_subject_changes_on_policy_source_hash_only(self):
        p=packet(); q=copy.deepcopy(p); q["policy"]["source_sha256"]="a"*64
        self.assertNotEqual(a.authority_subject(p)["policy_sha256"],a.authority_subject(q)["policy_sha256"])

    def test_authority_subject_changes_on_cost_source_hash_only(self):
        p=packet(); q=copy.deepcopy(p); q["deal"]["items"][0]["source_sha256"]="a"*64
        self.assertNotEqual(a.authority_subject(p)["scope_cost_sha256"],a.authority_subject(q)["scope_cost_sha256"])

    def test_authority_subject_changes_on_capacity_observed_time_only(self):
        p=packet(); q=copy.deepcopy(p); q["capacity"]["observed_at"]="2026-09-13T20:31:00Z"
        self.assertNotEqual(a.authority_subject(p)["capacity_sha256"],a.authority_subject(q)["capacity_sha256"])

    def test_registry_identity_is_canonical_not_raw_file_format(self):
        p=packet(); h,ctx=self.host(); reg=h.sign(p)
        h.registry.write_text(json.dumps(reg,indent=2,sort_keys=False)+"\n",encoding="utf-8")
        with ctx: r=a._compile_current_at(p,NOW)
        self.assertEqual(r["state"],a.READY); self.assertEqual(r["input_authority"]["registry_sha256"],a.digest(reg))

if __name__ == "__main__": unittest.main()

import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from preflight import REQUIRED_GATES, SCHEMA_VERSION, evaluate, main
from trusted_authority import (
    AUTHORITY_SCHEMA,
    GATE_EVIDENCE_KIND,
    AuthorityError,
    EvidenceRecord,
    authority_sha256,
    load_current_authority,
    release_subject_sha256,
    source_generation_sha256,
)

HERE = Path(__file__).resolve().parent


def h(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def authority_material(generation: int = 7) -> dict:
    material = {
        "schema_version": AUTHORITY_SCHEMA,
        "solicitation_id": "920-45-269",
        "generation": generation,
        "packet_sha256": h(f"packet:{generation}"),
        "addenda": [
            {"id": "addendum-1", "sha256": h(f"addendum-1:{generation}")},
            {"id": "addendum-2", "sha256": h(f"addendum-2:{generation}")},
        ],
        "required_gates": list(REQUIRED_GATES),
        "evidence": [],
    }
    source = source_generation_sha256(material)
    pending: list[EvidenceRecord] = []
    for gate in REQUIRED_GATES:
        if gate == "owner_release_to_submit":
            continue
        digest = (
            material["packet_sha256"]
            if gate in {"controlling_packet_acquired", "packet_sha256_verified"}
            else h(f"{gate}:{generation}")
        )
        row = {
            "id": f"ev:{gate}",
            "gate": gate,
            "kind": GATE_EVIDENCE_KIND[gate],
            "sha256": digest,
            "source_generation_sha256": source,
        }
        material["evidence"].append(row)
        pending.append(
            EvidenceRecord(
                row["id"], row["gate"], row["kind"], row["sha256"],
                row["source_generation_sha256"],
            )
        )
    subject = release_subject_sha256(
        solicitation_id="920-45-269",
        source_generation=source,
        evidence=pending,
    )
    material["evidence"].append(
        {
            "id": "ev:owner_release_to_submit",
            "gate": "owner_release_to_submit",
            "kind": "OWNER_RELEASE",
            "sha256": subject,
            "source_generation_sha256": source,
        }
    )
    return material


def ready_state(material: dict) -> dict:
    digest = authority_sha256(material)
    return {
        "schema_version": SCHEMA_VERSION,
        "solicitation_id": "920-45-269",
        "authority": {"generation": material["generation"], "authority_sha256": digest},
        "gates": {
            gate: {
                "status": "PASS",
                "evidence": [f"ev:{gate}"],
                "reason": "verified by retained authority fixture",
            }
            for gate in REQUIRED_GATES
        },
    }


def load_pinned(material: dict):
    digest = authority_sha256(material)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "authority.json"
        path.write_text(json.dumps(material, sort_keys=True), encoding="utf-8")
        authority = load_current_authority(
            path,
            trusted_generation=material["generation"],
            trusted_authority_sha256=digest,
        )
        return authority, json.loads(json.dumps(material))


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.state = json.loads((HERE / "submission_state.json").read_text(encoding="utf-8"))

    def test_current_state_is_hold(self):
        receipt = evaluate(self.state)
        self.assertEqual("HOLD", receipt["status"])
        self.assertFalse(receipt["errors"])
        self.assertEqual(len(REQUIRED_GATES), len(receipt["blockers"]))

    def test_digest_is_deterministic(self):
        a = evaluate(self.state)["state_sha256"]
        b = evaluate(json.loads(json.dumps(self.state)))["state_sha256"]
        self.assertEqual(a, b)

    def test_wrong_schema_is_invalid(self):
        state = copy.deepcopy(self.state)
        state["schema_version"] = "wrong"
        self.assertEqual("INVALID", evaluate(state)["status"])

    def test_wrong_solicitation_is_invalid(self):
        state = copy.deepcopy(self.state)
        state["solicitation_id"] = "other"
        self.assertEqual("INVALID", evaluate(state)["status"])

    def test_missing_gate_is_invalid(self):
        state = copy.deepcopy(self.state)
        del state["gates"][REQUIRED_GATES[0]]
        self.assertEqual("INVALID", evaluate(state)["status"])

    def test_unknown_gate_is_invalid(self):
        state = copy.deepcopy(self.state)
        state["gates"]["magic"] = {"status": "HOLD", "evidence": [], "reason": "no"}
        self.assertEqual("INVALID", evaluate(state)["status"])

    def test_arbitrary_sha_strings_cannot_mint_ready(self):
        state = {
            "schema_version": SCHEMA_VERSION,
            "solicitation_id": "920-45-269",
            "authority": {"generation": None, "authority_sha256": None},
            "gates": {},
        }
        for gate in REQUIRED_GATES:
            state["gates"][gate] = {
                "status": "PASS",
                "evidence": [f"sha256:{gate}"],
                "reason": "caller says verified",
            }
        receipt = evaluate(state)
        self.assertEqual("HOLD", receipt["status"])
        self.assertFalse(receipt["errors"])
        self.assertFalse(receipt["trusted_authority"]["verified_current"])
        self.assertEqual(len(REQUIRED_GATES), len(receipt["blockers"]))

    def test_authenticated_current_authority_can_make_ready_via_trusted_host_api(self):
        material = authority_material()
        authority, _ = load_pinned(material)
        receipt = evaluate(ready_state(material), authority)
        self.assertEqual("READY", receipt["status"])
        self.assertFalse(receipt["blockers"])
        self.assertFalse(receipt["errors"])
        self.assertTrue(receipt["trusted_authority"]["verified_current"])
        self.assertEqual(material["generation"], receipt["trusted_authority"]["generation"])

    def test_explicit_wrong_trusted_root_rejects_self_minted_authority(self):
        approved = authority_material()
        attacker = copy.deepcopy(approved)
        attacker["evidence"][-1]["id"] = "ev:owner_release_to_submit:fork"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "authority.json"
            path.write_text(json.dumps(attacker), encoding="utf-8")
            with self.assertRaisesRegex(AuthorityError, "trusted host root"):
                load_current_authority(
                    path,
                    trusted_generation=approved["generation"],
                    trusted_authority_sha256=authority_sha256(approved),
                )

    def test_old_valid_authority_cannot_replay_after_trusted_root_advances(self):
        old = authority_material(generation=7)
        current = authority_material(generation=8)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "authority.json"
            path.write_text(json.dumps(old), encoding="utf-8")
            with self.assertRaisesRegex(AuthorityError, "trusted host root"):
                load_current_authority(
                    path,
                    trusted_generation=8,
                    trusted_authority_sha256=authority_sha256(current),
                )

    def test_same_generation_fork_cannot_replace_trusted_digest(self):
        material = authority_material(generation=7)
        fork = copy.deepcopy(material)
        fork["evidence"][-1]["id"] = "ev:owner_release_to_submit:fork"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "authority.json"
            path.write_text(json.dumps(fork), encoding="utf-8")
            with self.assertRaisesRegex(AuthorityError, "trusted host root"):
                load_current_authority(
                    path,
                    trusted_generation=7,
                    trusted_authority_sha256=authority_sha256(material),
                )

    def test_loader_rejects_bool_trusted_generation(self):
        material = authority_material()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "authority.json"
            path.write_text(json.dumps(material), encoding="utf-8")
            with self.assertRaisesRegex(AuthorityError, "integer"):
                load_current_authority(
                    path,
                    trusted_generation=True,
                    trusted_authority_sha256=authority_sha256(material),
                )

    def test_loader_rejects_malformed_trusted_digest(self):
        material = authority_material()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "authority.json"
            path.write_text(json.dumps(material), encoding="utf-8")
            with self.assertRaisesRegex(AuthorityError, "lowercase 64-hex"):
                load_current_authority(
                    path,
                    trusted_generation=material["generation"],
                    trusted_authority_sha256="not-a-digest",
                )

    def test_public_cli_caller_environment_cannot_mint_ready(self):
        material = authority_material()
        state = ready_state(material)
        legacy_env = {
            "GRAND_RAPIDS_PREFLIGHT_AUTHORITY_GENERATION": str(material["generation"]),
            "GRAND_RAPIDS_PREFLIGHT_AUTHORITY_SHA256": authority_sha256(material),
        }
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            out = io.StringIO()
            with mock.patch.dict(os.environ, legacy_env, clear=False):
                with mock.patch.object(sys, "argv", ["preflight.py", str(state_path)]):
                    with redirect_stdout(out):
                        rc = main()
        receipt = json.loads(out.getvalue())
        self.assertEqual(0, rc)
        self.assertEqual("HOLD", receipt["status"])
        self.assertFalse(receipt["trusted_authority"]["verified_current"])
        self.assertEqual(len(REQUIRED_GATES), len(receipt["blockers"]))

    def test_public_cli_rejects_legacy_authority_flag(self):
        material = authority_material()
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            authority_path = Path(td) / "authority.json"
            state_path.write_text(json.dumps(ready_state(material)), encoding="utf-8")
            authority_path.write_text(json.dumps(material), encoding="utf-8")
            err = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                ["preflight.py", str(state_path), "--authority", str(authority_path)],
            ):
                with redirect_stderr(err):
                    with self.assertRaises(SystemExit) as raised:
                        main()
        self.assertEqual(2, raised.exception.code)
        self.assertIn("unrecognized arguments: --authority", err.getvalue())

    def test_gate_universe_cannot_shrink(self):
        material = authority_material()
        material["required_gates"] = material["required_gates"][:-1]
        with self.assertRaisesRegex(AuthorityError, "canonical gate universe"):
            authority_sha256(material)

    def test_gate_universe_cannot_relabel(self):
        material = authority_material()
        material["required_gates"][-1] = "owner_release_optional"
        with self.assertRaisesRegex(AuthorityError, "canonical gate universe"):
            authority_sha256(material)

    def test_stale_source_generation_evidence_is_rejected(self):
        material = authority_material()
        material["evidence"][3]["source_generation_sha256"] = h("older-packet-generation")
        with self.assertRaisesRegex(AuthorityError, "stale source generation"):
            authority_sha256(material)

    def test_wrong_evidence_kind_is_rejected(self):
        material = authority_material()
        owner = next(row for row in material["evidence"] if row["gate"] == "owner_release_to_submit")
        owner["kind"] = "TECHNICAL_NARRATIVE"
        with self.assertRaisesRegex(AuthorityError, "OWNER_RELEASE"):
            authority_sha256(material)

    def test_packet_evidence_must_bind_exact_packet_digest(self):
        material = authority_material()
        packet = next(row for row in material["evidence"] if row["gate"] == "controlling_packet_acquired")
        packet["sha256"] = h("different-packet")
        with self.assertRaisesRegex(AuthorityError, "must equal packet_sha256"):
            authority_sha256(material)

    def test_packet_verification_must_bind_exact_packet_digest(self):
        material = authority_material()
        row = next(item for item in material["evidence"] if item["gate"] == "packet_sha256_verified")
        row["sha256"] = h("unrelated-verification-digest")
        with self.assertRaisesRegex(AuthorityError, "PACKET_SHA256_VERIFICATION"):
            authority_sha256(material)

    def test_owner_release_must_bind_release_subject(self):
        material = authority_material()
        owner = next(row for row in material["evidence"] if row["gate"] == "owner_release_to_submit")
        owner["sha256"] = h("old-release-not-bound-to-subject")
        with self.assertRaisesRegex(AuthorityError, "release-subject"):
            authority_sha256(material)

    def test_changed_pricing_invalidates_carried_owner_release(self):
        material = authority_material()
        pricing = next(row for row in material["evidence"] if row["gate"] == "pricing_form_complete")
        pricing["sha256"] = h("changed-pricing")
        with self.assertRaisesRegex(AuthorityError, "release-subject"):
            authority_sha256(material)

    def test_changed_reference_invalidates_carried_owner_release(self):
        material = authority_material()
        refs = next(row for row in material["evidence"] if row["gate"] == "references_resolved")
        refs["sha256"] = h("changed-references")
        with self.assertRaisesRegex(AuthorityError, "release-subject"):
            authority_sha256(material)

    def test_added_non_release_evidence_invalidates_owner_release(self):
        material = authority_material()
        source = material["evidence"][0]["source_generation_sha256"]
        material["evidence"].insert(
            0,
            {
                "id": "ev:pricing_form_complete:extra",
                "gate": "pricing_form_complete",
                "kind": "PRICING_FORM",
                "sha256": h("extra-pricing-row"),
                "source_generation_sha256": source,
            },
        )
        with self.assertRaisesRegex(AuthorityError, "release-subject"):
            authority_sha256(material)

    def test_state_stale_generation_cannot_use_current_authority(self):
        material = authority_material()
        authority, _ = load_pinned(material)
        state = ready_state(material)
        state["authority"]["generation"] -= 1
        self.assertEqual("INVALID", evaluate(state, authority)["status"])

    def test_state_wrong_authority_digest_cannot_use_current_authority(self):
        material = authority_material()
        authority, _ = load_pinned(material)
        state = ready_state(material)
        state["authority"]["authority_sha256"] = h("other-authority")
        self.assertEqual("INVALID", evaluate(state, authority)["status"])

    def test_gate_cannot_borrow_evidence_from_another_gate(self):
        material = authority_material()
        authority, _ = load_pinned(material)
        state = ready_state(material)
        state["gates"]["owner_release_to_submit"]["evidence"] = ["ev:technical_narrative_complete"]
        receipt = evaluate(state, authority)
        self.assertEqual("INVALID", receipt["status"])
        self.assertTrue(any("wrong gate/type" in error for error in receipt["errors"]))

    def test_unknown_evidence_id_is_invalid(self):
        material = authority_material()
        authority, _ = load_pinned(material)
        state = ready_state(material)
        state["gates"]["pricing_form_complete"]["evidence"] = ["ev:not-present"]
        self.assertEqual("INVALID", evaluate(state, authority)["status"])

    def test_bool_generation_is_rejected(self):
        material = authority_material()
        material["generation"] = True
        with self.assertRaisesRegex(AuthorityError, "integer"):
            authority_sha256(material)

    def test_unknown_authority_field_is_rejected(self):
        material = authority_material()
        material["magic"] = "no"
        with self.assertRaisesRegex(AuthorityError, "unexpected or missing"):
            authority_sha256(material)

    def test_verified_authority_detaches_from_mutable_envelope(self):
        material = authority_material()
        authority, envelope = load_pinned(material)
        envelope["evidence"][-1]["kind"] = "FORGED"
        envelope["generation"] = 999
        receipt = evaluate(ready_state(material), authority)
        self.assertEqual("READY", receipt["status"])

    def test_owner_release_alone_cannot_make_ready(self):
        state = copy.deepcopy(self.state)
        state["gates"]["owner_release_to_submit"] = {
            "status": "PASS",
            "evidence": ["owner:event"],
            "reason": "owner released",
        }
        self.assertEqual("HOLD", evaluate(state)["status"])

    def test_packet_alone_cannot_make_ready(self):
        state = copy.deepcopy(self.state)
        for gate in ("controlling_packet_acquired", "packet_sha256_verified"):
            state["gates"][gate] = {
                "status": "PASS",
                "evidence": [f"packet:{gate}"],
                "reason": "packet held",
            }
        self.assertEqual("HOLD", evaluate(state)["status"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import gzip
from copy import deepcopy
import hashlib
import inspect
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "_release_transaction_under_test", HERE / "release_transaction.py"
)
assert SPEC is not None and SPEC.loader is not None
rt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rt)
ECON_SPEC = importlib.util.spec_from_file_location(
    "_economics_gate_for_release_test", HERE / "economics_gate.py"
)
assert ECON_SPEC is not None and ECON_SPEC.loader is not None
econ = importlib.util.module_from_spec(ECON_SPEC)
ECON_SPEC.loader.exec_module(econ)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def make_archive(members):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for name, raw in sorted(members.items()):
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(raw))
    return output.getvalue()


class GPTArchiveReviewTests(unittest.TestCase):
    def setUp(self):
        self.members = {"SOURCE.json": b"{}", "main.py": b"def agent(obs, config): return 'PASS'\n"}
        self.archive = make_archive(self.members)
        self.review = {"schema": "commons-release-review/v1", "decision": "PASS",
                       "reviewer": {"family": "gpt", "seat": "TEST", "session_ref": "test session"},
                       "archive_sha256": sha(self.archive), "source_manifest_sha256": sha(b"{}"),
                       "baseline_sha256": rt.V31_ARCHIVE_SHA256, "production_route": "replacement",
                       "activation_evidence": "test entrypoint", "required_members": {"main.py": sha(self.members["main.py"])}}

    def validate(self):
        return rt.validate_gpt_review(canon(self.review), self.archive, b"{}", rt._archive_members(self.archive))

    def test_exact_archive_review_passes_and_binds_receipt(self):
        self.assertEqual(sha(canon(self.review)), self.validate()["receipt_sha256"])

    def test_archive_or_member_change_requires_review(self):
        self.review["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(rt.TransactionError, "binding mismatch"):
            self.validate()
        self.review["archive_sha256"] = sha(self.archive)
        self.review["required_members"]["r04_full_router.py"] = "0" * 64
        with self.assertRaisesRegex(rt.TransactionError, "member missing"):
            self.validate()

    def test_incomplete_r04_restoration_cannot_be_packaged_as_restore(self):
        self.review["production_route"] = "r04-restored"
        with self.assertRaisesRegex(rt.TransactionError, "13-file production closure"):
            self.validate()

    def test_non_gpt_or_pending_release_review_does_not_pass(self):
        self.review["reviewer"]["family"] = "muse"
        with self.assertRaisesRegex(rt.TransactionError, "reviewer session"):
            self.validate()
        self.review["reviewer"]["family"] = "gpt"
        self.review["decision"] = "PENDING"
        with self.assertRaisesRegex(rt.TransactionError, "explicitly PASS"):
            self.validate()


class ReleaseTransactionTests(unittest.TestCase):
    def setUp(self):
        self.component = b"print('candidate')\n"
        self.component_sha = sha(self.component)
        self.source = {
            "runtime": {
                "feature.py": {
                    "source_path": "feature.py",
                    "sha256": self.component_sha,
                    "bytes": len(self.component),
                }
            }
        }
        self.source_raw = canon(self.source)
        self.archive = make_archive(
            {"SOURCE.json": self.source_raw, "feature.py": self.component}
        )
        self.old_source_raw = canon(
            {"runtime": {"old.py": {
                "source_path": "old.py",
                "sha256": "1" * 64,
                "bytes": 1,
            }}}
        )
        self.old = {
            "path": "exports/titan-current.tar.gz",
            "entrypoint": "main.py::agent",
            "config": "TITAN-CONFIG.json",
            "sha256": "2" * 64,
            "bytes": 123,
            "runtime_files": 1,
            "source_manifest": "runtime/integrated-selected/CURRENT-SOURCE.json",
            "source_manifest_sha256": sha(self.old_source_raw),
        }
        self.new = {
            "path": "exports/titan-current.tar.gz",
            "entrypoint": "main.py::agent",
            "config": "TITAN-CONFIG.json",
            "sha256": sha(self.archive),
            "bytes": len(self.archive),
            "runtime_files": 1,
            "source_manifest": "runtime/integrated-selected/CURRENT-SOURCE.json",
            "source_manifest_sha256": sha(self.source_raw),
        }
        self.old_raw = canon(self.old)
        self.new_raw = canon(self.new)
        self.manifest = {
            "candidate_id": "v5c:" + "a" * 64,
            "engine_id": "engine:test-pinned",
            "opponent_pack_id": "opponent:test-pack",
            "components": [
                {
                    "name": "feature",
                    "source": "feature.py",
                    "source_sha256": self.component_sha,
                    "activation": {"mode": "unconditional"},
                }
            ],
        }
        self.engagement = {"x": 1}
        self.runtime = {"x": 2}
        self.manifest_raw = canon(self.manifest)
        self.engagement_raw = canon(self.engagement)
        self.runtime_raw = canon(self.runtime)
        self.evidence_hashes = {
            "candidate_manifest": sha(self.manifest_raw),
            "engagement_report": sha(self.engagement_raw),
            "runtime_report": sha(self.runtime_raw),
        }
        self.promotion = {
            "schema": "titan-v5-promotion-gate/v1",
            "classification": "PASS",
            "promotion_ready": True,
            "candidate_id": self.manifest["candidate_id"],
            "control_id": "v5c:" + "b" * 64,
            "evidence_sha256": dict(self.evidence_hashes),
            "engagement": {"observations": 2, "divergence_count": 1},
            "runtime": {
                "receipt_count": 2,
                "deadline_fallback_count": 0,
                "deadline_fallback_rate": 0.0,
                "p99_headroom_seconds": 0.1,
            },
        }
        self.promotion_raw = canon(self.promotion)
        cells = []
        for opponent_id in econ.AUTHORIZED_OPPONENT_IDS:
            for seed in range(10, 14):
                for seat in (0, 1):
                    cells.append(
                        {
                            "opponent_id": opponent_id,
                            "seed": seed,
                            "seat": seat,
                            "control_own": 1000 + seed,
                            "control_rival": 900 + seed,
                            "candidate_own": 1010 + seed,
                            "candidate_rival": 900 + seed,
                        }
                    )
        self.economics = {
            "schema": econ.SCHEMA,
            "control_id": self.promotion["control_id"],
            "candidate_id": self.promotion["candidate_id"],
            "engine_id": self.manifest["engine_id"],
            "opponent_pack_id": self.manifest["opponent_pack_id"],
            "control_archive_sha256": self.old["sha256"],
            "candidate_archive_sha256": self.new["sha256"],
            "cells": cells,
        }
        self.economics_raw = canon(self.economics)
        self.champion = {
            "schema": rt.CHAMPION_RECEIPT_SCHEMA,
            "classification": "PASS", "champion_ready": True, "release_authority": False,
            "v31_source_commit": rt.V31_SOURCE_COMMIT,
            "v31_submission_id": rt.V31_SUBMISSION_ID,
            "v31_archive_sha256": rt.V31_ARCHIVE_SHA256,
            "manifest_sha256": rt.CHAMPION_MANIFEST_SHA256,
            "target_count": 41, "fixture_count": 123, "cell_count": 246,
            "incumbent_archive_sha256": self.old["sha256"],
            "candidate_archive_sha256": self.new["sha256"],
            "own_sum_delta_vs_incumbent": 492,
            "own_sum_delta_vs_v31": 246,
            "margin_sum_delta_vs_incumbent": 492,
            "margin_sum_delta_vs_v31": 246,
            "new_losses_vs_incumbent": 0, "new_losses_vs_v31": 0,
            "strata": [
                {"submission_id": sub, "seat": seat, "cells": 3,
                 "own_delta_vs_incumbent": 6, "own_delta_vs_v31": 3}
                for sub in range(1, 42) for seat in (0, 1)
            ],
            "panel_digest": "3" * 64,
            "harness": {"repo": {}, "engine": {}},
            "shards": 1,
            "source_digests": {label: "4" * 64 for label in ("v31", "incumbent", "candidate")},
            "run_authority": {
                label: [{"shard": 0, "shards": 1, "selected_fixtures": 123,
                         "run_sha256": "5" * 64, "index_sha256": "6" * 64}]
                for label in ("v31", "incumbent", "candidate")
            },
        }
        self.champion_raw = canon(self.champion) + b"\n"
        self.champion_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.champion_temp.cleanup)
        proof = Path(self.champion_temp.name)
        self.champion_evidence = {key: proof / key for key in rt._CHAMPION_PATH_KEYS}
        self.champion_evidence.update({key: [proof / key] for key in rt._CHAMPION_ROOT_KEYS})
        # Canonical evaluator filesystem/arithmetic coverage lives in its own
        # suite. Here only evaluate() is stubbed, after real pinned-source load,
        # to isolate transaction cross-binding from existing economics tests.
        self.champion_evaluate = mock.Mock(side_effect=lambda **_kwargs: deepcopy(self.champion))
        self.real_load_module = rt._load_module

        def load_module(path, name, **kwargs):
            module, source = self.real_load_module(path, name, **kwargs)
            if name == "_titan_v5_canonical_champion":
                module.evaluate = self.champion_evaluate
            return module, source

        loader = mock.patch.object(rt, "_load_module", side_effect=load_module)
        loader.start()
        self.addCleanup(loader.stop)
        self.trust_result = {
            "ok": True,
            "delegate": True,
            "checked_files": ["CANONICAL.json", "INTEGRATION.json", "COMPOSITION.json"],
            "errors": [],
        }
        self.trust_files = {
            "CANONICAL.json": b'{"a":1}\n',
            "INTEGRATION.json": b'{"b":2}\n',
            "COMPOSITION.json": b'{"c":3}\n',
            "check_control_plane.py": b"def validate_control_plane(root): return {'ok': True}\n",
        }

    def builder(self, manifest, engagement, runtime, *, evidence_sha256=None):
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(engagement, self.engagement)
        self.assertEqual(runtime, self.runtime)
        self.assertEqual(evidence_sha256, self.evidence_hashes)
        return dict(self.promotion)

    def build(self, **overrides):
        kwargs = dict(
            live_pointer_raw=self.old_raw,
            expected_old_pointer_raw=self.old_raw,
            approved_new_pointer_raw=self.new_raw,
            approved_archive_raw=self.archive,
            approved_source_manifest_raw=self.source_raw,
            candidate_manifest_raw=self.manifest_raw,
            engagement_raw=self.engagement_raw,
            runtime_raw=self.runtime_raw,
            promotion_receipt_raw=self.promotion_raw,
            economics_raw=self.economics_raw,
            champion_raw=self.champion_raw,
            champion_evidence=self.champion_evidence,
            promotion_builder=self.builder,
            economics_builder=econ.validate_report,
            trust_result=self.trust_result,
            trust_files=self.trust_files,
            gpt_review_raw=canon({
                "schema": "commons-release-review/v1", "decision": "PASS",
                "reviewer": {"seat": "TEST-GPT", "family": "gpt", "session_ref": "test fixture"},
                "archive_sha256": sha(self.archive), "source_manifest_sha256": sha(self.source_raw),
                "baseline_sha256": rt.V31_ARCHIVE_SHA256, "production_route": "replacement",
                "activation_evidence": "fixture component called by fixture harness",
                "required_members": {"feature.py": self.component_sha},
            }),
        )
        kwargs.update(overrides)
        return rt.build_transaction(**kwargs)

    def test_pass_is_deterministic_and_binds_all_authorities(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(first["classification"], "PASS")
        self.assertEqual("titan-v5-release-transaction/v6", first["schema"])
        self.assertRegex(first["transition_id"], r"^v5tx:[0-9a-f]{64}$")
        self.assertEqual(first["expected_old"]["archive_sha256"], self.old["sha256"])
        self.assertEqual(first["approved_new"]["archive_sha256"], self.new["sha256"])
        self.assertEqual(
            first["promotion"]["candidate_id"], self.manifest["candidate_id"]
        )
        self.assertEqual(first["promotion"]["control_id"], self.promotion["control_id"])
        self.assertEqual(first["economics"]["report_sha256"], sha(self.economics_raw))
        self.assertEqual(first["economics"]["engine_id"], self.manifest["engine_id"])
        self.assertEqual(first["economics"]["opponent_pack_id"], self.manifest["opponent_pack_id"])
        self.assertEqual(first["economics"]["opponent_count"], 2)
        self.assertEqual(first["economics"]["opponent_ids"], list(econ.AUTHORIZED_OPPONENT_IDS))
        self.assertEqual(
            first["economics"]["authorized_opponent_ids"],
            list(econ.AUTHORIZED_OPPONENT_IDS),
        )
        self.assertEqual(
            first["economics"]["opponent_registry_git_blob"],
            econ.REFERENCE_POLICIES_GIT_BLOB,
        )
        self.assertEqual(first["economics"]["control_archive_sha256"], self.old["sha256"])
        self.assertEqual(first["economics"]["candidate_archive_sha256"], self.new["sha256"])
        self.assertEqual(first["economics"]["cell_count"], 16)
        self.assertEqual(first["champion"]["cell_count"], 246)
        self.assertEqual(first["champion"]["receipt_sha256"], sha(self.champion_raw))
        self.assertEqual(first["champion"]["builder_git_blob"], rt.CHAMPION_GATE_GIT_BLOB)
        self.assertEqual(first["champion"]["source_digests"], self.champion["source_digests"])
        self.assertEqual(first["champion"]["run_authority"], self.champion["run_authority"])
        self.assertEqual(first["economics"]["sum_margin_delta"], 160)
        self.assertEqual(
            first["economics"]["per_opponent"],
            {
                opponent: {
                    "cell_count": 8,
                    "control_margin_sum": 800,
                    "candidate_margin_sum": 880,
                    "sum_margin_delta": 80,
                }
                for opponent in econ.AUTHORIZED_OPPONENT_IDS
            },
        )

    def test_stale_live_pointer_fails_closed(self):
        with self.assertRaisesRegex(rt.TransactionError, "stale"):
            self.build(live_pointer_raw=b"{}\n")

    def test_noop_pointer_is_not_a_transition(self):
        with self.assertRaisesRegex(rt.TransactionError, "must differ"):
            self.build(
                approved_new_pointer_raw=self.old_raw,
                approved_archive_raw=self.archive,
            )

    def test_archive_byte_tamper_fails(self):
        with self.assertRaisesRegex(rt.TransactionError, "archive (byte count|hash)"):
            self.build(approved_archive_raw=self.archive + b"x")

    def test_detached_source_manifest_fails_even_if_pointer_hash_is_updated(self):
        changed_source = canon({"runtime": {"feature.py": {
            "source_path": "feature.py",
            "sha256": "9" * 64,
            "bytes": len(self.component),
        }}})
        changed_new = dict(self.new)
        changed_new["source_manifest_sha256"] = sha(changed_source)
        with self.assertRaisesRegex(rt.TransactionError, "SOURCE.json differs"):
            self.build(
                approved_new_pointer_raw=canon(changed_new),
                approved_source_manifest_raw=changed_source,
            )

    def test_promoted_component_must_match_packaged_member_bytes(self):
        bad_component = b"print('wrong')\n"
        bad_archive = make_archive(
            {"SOURCE.json": self.source_raw, "feature.py": bad_component}
        )
        bad_new = dict(self.new)
        bad_new["sha256"] = sha(bad_archive)
        bad_new["bytes"] = len(bad_archive)
        bad_economics = json.loads(json.dumps(self.economics))
        bad_economics["candidate_archive_sha256"] = bad_new["sha256"]
        with self.assertRaisesRegex(rt.TransactionError, "archive member disagrees"):
            self.build(
                approved_new_pointer_raw=canon(bad_new),
                approved_archive_raw=bad_archive,
                economics_raw=canon(bad_economics),
            )

    def test_promotion_receipt_must_be_exact_replay(self):
        bad = dict(self.promotion)
        bad["runtime"] = dict(bad["runtime"])
        bad["runtime"]["receipt_count"] = 999
        with self.assertRaisesRegex(rt.TransactionError, "disagrees with gate replay"):
            self.build(promotion_receipt_raw=canon(bad))

    def test_negative_economics_cannot_release(self):
        bad = json.loads(json.dumps(self.economics))
        for cell in bad["cells"]:
            cell["candidate_own"] = cell["control_own"] - 1
            cell["candidate_rival"] = cell["control_rival"]
        with self.assertRaisesRegex(rt.TransactionError, "economics gate replay failed"):
            self.build(economics_raw=canon(bad))

    def test_positive_global_cannot_mask_authorized_opponent_regression(self):
        bad = json.loads(json.dumps(self.economics))
        for cell in bad["cells"]:
            adjustment = -10 if cell["opponent_id"] == "apex_v7" else 20
            cell["candidate_own"] = cell["control_own"] + adjustment
            cell["candidate_rival"] = cell["control_rival"]
        with self.assertRaisesRegex(rt.TransactionError, "economics gate replay failed"):
            self.build(economics_raw=canon(bad))

    def test_cross_build_economics_cannot_release(self):
        bad = json.loads(json.dumps(self.economics))
        bad["candidate_id"] = "v5c:" + "c" * 64
        with self.assertRaisesRegex(rt.TransactionError, "economics gate replay failed"):
            self.build(economics_raw=canon(bad))

    def test_single_opponent_economics_cannot_release(self):
        bad = json.loads(json.dumps(self.economics))
        cells = []
        for seed in range(10, 18):
            for seat in (0, 1):
                cells.append(
                    {
                        "opponent_id": "apex_v7",
                        "seed": seed,
                        "seat": seat,
                        "control_own": 1000 + seed,
                        "control_rival": 900 + seed,
                        "candidate_own": 1010 + seed,
                        "candidate_rival": 900 + seed,
                    }
                )
        bad["cells"] = cells
        with self.assertRaisesRegex(rt.TransactionError, "economics gate replay failed"):
            self.build(economics_raw=canon(bad))

    def test_fake_or_recovered_extra_opponent_cannot_release(self):
        for replacement in ("favorable_fake", "kaito_v43"):
            with self.subTest(replacement=replacement):
                bad = json.loads(json.dumps(self.economics))
                for cell in bad["cells"]:
                    if cell["opponent_id"] == "arlene_v14":
                        cell["opponent_id"] = replacement
                bad["cells"].sort(
                    key=lambda cell: (cell["opponent_id"], cell["seed"], cell["seat"])
                )
                with self.assertRaisesRegex(rt.TransactionError, "economics gate replay failed"):
                    self.build(economics_raw=canon(bad))

    def test_stale_execution_closure_cannot_release(self):
        mutations = [
            ("engine_id", "engine:stale"),
            ("opponent_pack_id", "opponent:stale"),
            ("control_archive_sha256", "c" * 64),
            ("candidate_archive_sha256", "d" * 64),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                bad = json.loads(json.dumps(self.economics))
                bad[key] = value
                with self.assertRaisesRegex(rt.TransactionError, "economics gate replay failed"):
                    self.build(economics_raw=canon(bad))

    def test_economics_bytes_change_transition_identity(self):
        first = self.build()
        better = json.loads(json.dumps(self.economics))
        better["cells"][0]["candidate_own"] += 1
        second = self.build(economics_raw=canon(better))
        self.assertNotEqual(first["economics"]["report_sha256"], second["economics"]["report_sha256"])
        self.assertNotEqual(first["transition_id"], second["transition_id"])

    def test_release_replay_rejects_forged_roster_receipt(self):
        def forged_builder(*args, **kwargs):
            receipt = econ.validate_report(*args, **kwargs)
            receipt["authorized_opponent_ids"] = ["apex_v7", "favorable_fake"]
            return receipt

        with self.assertRaisesRegex(rt.TransactionError, "authorized_opponent_ids"):
            self.build(economics_builder=forged_builder)

    def test_release_replay_rejects_forged_registry_or_per_opponent_receipt(self):
        def forged_registry(*args, **kwargs):
            receipt = econ.validate_report(*args, **kwargs)
            receipt["opponent_registry_git_blob"] = "0" * 40
            return receipt

        with self.assertRaisesRegex(rt.TransactionError, "registry blob"):
            self.build(economics_builder=forged_registry)

        def forged_per_opponent(*args, **kwargs):
            receipt = econ.validate_report(*args, **kwargs)
            receipt["per_opponent"]["apex_v7"]["sum_margin_delta"] = -1
            return receipt

        with self.assertRaisesRegex(rt.TransactionError, "margin arithmetic|margin regresses"):
            self.build(economics_builder=forged_per_opponent)

    def test_champion_receipt_and_backing_evidence_are_required_api_inputs(self):
        signature = inspect.signature(rt.build_transaction)
        for key in ("champion_raw", "champion_evidence"):
            self.assertIs(signature.parameters[key].default, inspect.Parameter.empty)
        with mock.patch.object(rt, "build_transaction", wraps=rt.build_transaction) as build:
            self.build()
            kwargs = dict(build.call_args.kwargs)
        for key in ("champion_raw", "champion_evidence"):
            omitted = dict(kwargs)
            omitted.pop(key)
            with self.assertRaises(TypeError):
                rt.build_transaction(**omitted)

    def test_perfect_fake_champion_without_backing_files_cannot_release(self):
        # Even correct schema/identities/counts and positive invented metrics
        # cannot substitute for actual authenticated files and complete roots.
        with mock.patch.object(rt, "_load_module", side_effect=self.real_load_module):
            with self.assertRaisesRegex(rt.TransactionError, "champion evidence replay failed"):
                self.build()

    def test_champion_evidence_cannot_override_canonical_pins_or_omit_roots(self):
        for evidence in (None, {}, {**self.champion_evidence, "repo_pins": {}},
                         {**self.champion_evidence, "expected_targets": 2},
                         {**self.champion_evidence, "v31_roots": []}):
            with self.subTest(evidence=evidence):
                with self.assertRaisesRegex(rt.TransactionError, "champion evidence"):
                    self.build(champion_evidence=evidence)

    def test_stale_champion_identity_or_small_panel_cannot_release(self):
        mutations = {
            "schema": "titan-v5-champion-ratchet-receipt/v1",
            "v31_source_commit": "0" * 40, "v31_submission_id": 1,
            "v31_archive_sha256": "0" * 64, "manifest_sha256": "0" * 64,
            "incumbent_archive_sha256": "f" * 64, "candidate_archive_sha256": "e" * 64,
            "target_count": 2, "fixture_count": 8, "cell_count": 16,
            "champion_ready": False, "release_authority": True,
        }
        for key, value in mutations.items():
            bad = {**self.champion, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(rt.TransactionError, key):
                self.build(champion_raw=canon(bad))

    def test_champion_tie_regression_and_new_losses_cannot_release(self):
        for key, value in (
            ("own_sum_delta_vs_v31", 0), ("own_sum_delta_vs_incumbent", -1),
            ("margin_sum_delta_vs_v31", -1), ("new_losses_vs_v31", 1),
            ("new_losses_vs_incumbent", 1), ("own_sum_delta_vs_v31", True),
        ):
            with self.subTest(key=key), self.assertRaises(rt.TransactionError):
                self.build(champion_raw=canon({**self.champion, key: value}))

    def test_fabricated_strata_or_source_authority_disagrees_with_replay(self):
        mutations = []
        negative = deepcopy(self.champion)
        negative["strata"][0]["own_delta_vs_v31"] = -1
        mutations.append(negative)
        for key in ("harness", "source_digests", "run_authority", "strata"):
            omitted = deepcopy(self.champion)
            omitted.pop(key)
            mutations.append(omitted)
        changed = deepcopy(self.champion)
        changed["source_digests"]["candidate"] = "f" * 64
        mutations.append(changed)
        for bad in mutations:
            with self.assertRaisesRegex(rt.TransactionError, "authenticated full-panel replay"):
                self.build(champion_raw=canon(bad))

    def test_champion_replay_receives_all_three_policies_without_small_panel_zip(self):
        receipt = self.build()
        self.champion_evaluate.assert_called_once()
        inputs = self.champion_evaluate.call_args.kwargs
        self.assertEqual(set(inputs), set(self.champion_evidence) | {
            "claimed_v31_source_commit", "claimed_v31_submission_id",
        })
        self.assertEqual(inputs["candidate_archive"], self.champion_evidence["candidate_archive"])
        self.assertEqual(inputs["v31_roots"], tuple(self.champion_evidence["v31_roots"]))
        self.assertNotEqual(receipt["champion"]["cell_count"], receipt["economics"]["cell_count"])

    def test_noncanonical_champion_bytes_reject_even_when_semantically_equal(self):
        variants = (
            self.champion_raw + b"\n", canon(self.champion),
            json.dumps(self.champion, indent=2).encode() + b"\n",
            self.champion_raw.replace(b'"own_sum_delta_vs_v31":246', b'"own_sum_delta_vs_v31":246.0'),
        )
        for raw in variants:
            with self.assertRaisesRegex(rt.TransactionError, "authenticated full-panel replay"):
                self.build(champion_raw=raw)

    def test_champion_replayed_evidence_changes_transition(self):
        first = self.build()
        self.champion["source_digests"]["candidate"] = "f" * 64
        changed = self.build(champion_raw=canon(self.champion) + b"\n")
        self.assertNotEqual(first["champion"]["receipt_sha256"], changed["champion"]["receipt_sha256"])
        self.assertNotEqual(first["transition_id"], changed["transition_id"])

    def test_changed_champion_builder_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            executed = root / "executed"
            source = root / "builder.py"
            source.write_text(f"from pathlib import Path\nPath({str(executed)!r}).touch()\n")
            with self.assertRaisesRegex(rt.TransactionError, "pinned Git blob"):
                self.real_load_module(source, "untrusted", expected_git_blob=rt.CHAMPION_GATE_GIT_BLOB)
            self.assertFalse(executed.exists())

    def test_trusted_base_gate_must_pass(self):
        with self.assertRaisesRegex(rt.TransactionError, "trusted-base gate"):
            self.build(trust_result={"ok": False, "errors": ["bad"]})

    def test_duplicate_json_key_is_rejected(self):
        duplicate = b'{"path":"exports/titan-current.tar.gz","path":"x"}'
        with self.assertRaisesRegex(rt.TransactionError, "duplicate JSON key"):
            self.build(approved_new_pointer_raw=duplicate)

    def test_load_module_executes_first_captured_bytes_after_path_swap(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gate.py"
            authenticated = b"VALUE = 'authenticated'\n"
            path.write_bytes(authenticated)
            original = rt.importlib.util.spec_from_file_location

            def swap_after_read(name, location):
                spec = original(name, location)
                path.write_text("VALUE = 'poison'\n", encoding="utf-8")
                return spec

            with mock.patch.object(
                rt.importlib.util,
                "spec_from_file_location",
                side_effect=swap_after_read,
            ):
                module, captured = rt._load_module(path, "_captured_swap_test")
            self.assertEqual(authenticated, captured)
            self.assertEqual("authenticated", module.VALUE)
            self.assertEqual("VALUE = 'poison'\n", path.read_text(encoding="utf-8"))

    def test_load_module_executes_captured_bytes_even_if_path_deleted_after_read(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gate.py"
            authenticated = b"VALUE = 'authenticated'\n"
            path.write_bytes(authenticated)
            original = rt.importlib.util.spec_from_file_location

            def delete_after_read(name, location):
                spec = original(name, location)
                path.unlink()
                return spec

            with mock.patch.object(
                rt.importlib.util,
                "spec_from_file_location",
                side_effect=delete_after_read,
            ):
                module, captured = rt._load_module(path, "_captured_delete_test")
            self.assertEqual(authenticated, captured)
            self.assertEqual("authenticated", module.VALUE)
            self.assertFalse(path.exists())

    def test_commit_rechecks_expected_old_and_publishes_receipt_after_pointer(self):
        receipt = self.build()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pointer = root / "CURRENT-ARCHIVE.json"
            output = root / "TRANSACTION.json"
            pointer.write_bytes(self.old_raw)
            with self.assertRaisesRegex(rt.TransactionError, "origin authority"):
                rt.commit_pointer(
                    current_pointer=pointer,
                    expected_old_pointer_raw=self.old_raw,
                    approved_new_pointer_raw=self.new_raw,
                    receipt_path=output,
                    receipt=receipt,
                )
            self.assertEqual(pointer.read_bytes(), self.old_raw)
            self.assertFalse(output.exists())

    def test_commit_rejects_stale_pointer_without_receipt(self):
        receipt = self.build()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pointer = root / "CURRENT-ARCHIVE.json"
            output = root / "TRANSACTION.json"
            pointer.write_bytes(b"stale")
            with self.assertRaisesRegex(rt.TransactionError, "origin authority"):
                rt.commit_pointer(
                    current_pointer=pointer,
                    expected_old_pointer_raw=self.old_raw,
                    approved_new_pointer_raw=self.new_raw,
                    receipt_path=output,
                    receipt=receipt,
                )
            self.assertEqual(pointer.read_bytes(), b"stale")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

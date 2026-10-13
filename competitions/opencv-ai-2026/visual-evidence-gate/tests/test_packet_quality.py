from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import packet_quality as quality
import packet_s3 as s3_adapter

from packet_quality import (
    AUTHORITY,
    ProofCamError,
    compile_triage,
    sha256,
    strict_json_bytes,
    verify_triage,
)
from packet_s3 import compile_s3_manifest_event, verify_s3_manifest_event


def png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("OpenCV failed to encode the synthetic PNG fixture")
    return encoded.tobytes()


def checker(offset: int = 0) -> bytes:
    y, x = np.indices((160, 160))
    grid = (((x // 10 + y // 10 + offset) % 2) * 255).astype(np.uint8)
    image = cv2.cvtColor(grid, cv2.COLOR_GRAY2BGR)
    return png(image)


def textured(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    image = rng.integers(20, 236, size=(160, 160, 3), dtype=np.uint8)
    cv2.rectangle(image, (15, 15), (80, 70), (255, 255, 255), 3)
    cv2.circle(image, (110, 105), 24, (5, 5, 5), 3)
    return png(image)


def blur_bytes() -> bytes:
    arr = cv2.imdecode(np.frombuffer(textured(4), np.uint8), cv2.IMREAD_COLOR)
    return png(cv2.GaussianBlur(arr, (31, 31), 0))


def packet(payloads: dict[str, bytes], slot_ids=("front", "side")):
    slots = [{"slot_id": slot, "label": f"{slot}-view"} for slot in sorted(slot_ids)]
    images = []
    for slot in sorted(payloads):
        image_id = f"img-{slot}"
        images.append({"image_id": image_id, "slot_id": slot, "payload_sha256": sha256(payloads[slot])})
    return {
        "schema": "proofcam-evidence-packet/v1",
        "packet_id": "packet-1",
        "required_slots": slots,
        "images": images,
    }


def loader(payloads: dict[str, bytes]):
    mapping = {f"img-{slot}": data for slot, data in payloads.items()}
    return lambda image_id: mapping[image_id]


class PacketQualityTests(unittest.TestCase):
    def test_01_good_distinct_views_reach_human_review_only(self):
        payloads = {"front": textured(1), "side": textured(2)}
        out = compile_triage(packet(payloads), loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "ACCEPT_FOR_HUMAN_REVIEW")
        self.assertFalse(out["decision"]["trace"]["vision_changed_next_step"])
        self.assertEqual(out["decision"]["authority"], AUTHORITY)
        self.assertFalse(any(out["decision"]["authority"].values()))

    def test_02_exact_duplicate_cross_slot_holds(self):
        same = textured(3)
        payloads = {"front": same, "side": same}
        out = compile_triage(packet(payloads), loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "HOLD_DUPLICATE_EVIDENCE")
        self.assertTrue(out["decision"]["trace"]["vision_changed_next_step"])

    def test_03_near_duplicate_cross_slot_holds(self):
        base = cv2.imdecode(np.frombuffer(textured(19), np.uint8), cv2.IMREAD_COLOR)
        ok, jpeg_encoded = cv2.imencode(".jpg", base, [cv2.IMWRITE_JPEG_QUALITY, 95])
        self.assertTrue(ok)
        payloads = {"front": png(base), "side": jpeg_encoded.tobytes()}
        self.assertNotEqual(payloads["front"], payloads["side"])
        out = compile_triage(packet(payloads), loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "HOLD_DUPLICATE_EVIDENCE")

    def test_04_missing_slot_requests_exact_view(self):
        payloads = {"front": textured(5)}
        out = compile_triage(packet(payloads), loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "REQUEST_MISSING_VIEW")
        self.assertEqual(out["decision"]["trace"]["affected_slots"], ["side"])

    def test_05_blur_requests_recapture(self):
        payloads = {"front": blur_bytes()}
        out = compile_triage(packet(payloads, ("front",)), loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "REQUEST_RECAPTURE")
        self.assertEqual(out["decision"]["trace"]["reasons"][0]["code"], "LOW_FOCUS")

    def test_06_highlight_clipping_requests_recapture(self):
        image = np.full((160, 160, 3), 255, dtype=np.uint8)
        cv2.line(image, (0, 0), (159, 159), (0, 0, 0), 2)
        payloads = {"front": png(image)}
        out = compile_triage(packet(payloads, ("front",)), loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "REQUEST_RECAPTURE")
        codes = {r["code"] for r in out["decision"]["trace"]["reasons"]}
        self.assertTrue("HIGHLIGHT_CLIPPING" in codes or "LOW_FOCUS" in codes)

    def test_07_corrupt_image_holds_unreadable(self):
        payloads = {"front": b"not-an-image"}
        out = compile_triage(packet(payloads, ("front",)), loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "HOLD_UNSAFE_OR_UNREADABLE")

    def test_08_digest_mismatch_fails_closed(self):
        payloads = {"front": textured(6)}
        p = packet(payloads, ("front",))
        p["images"][0]["payload_sha256"] = "0" * 64
        with self.assertRaises(ProofCamError):
            compile_triage(p, loader(payloads))

    def test_09_unknown_slot_rejected(self):
        payloads = {"front": textured(7)}
        p = packet(payloads, ("front",))
        p["images"][0]["slot_id"] = "rear"
        with self.assertRaises(ProofCamError):
            compile_triage(p, loader(payloads))

    def test_10_duplicate_slot_rejected(self):
        payloads = {"front": textured(8)}
        p = packet(payloads, ("front",))
        p["required_slots"].append(dict(p["required_slots"][0]))
        with self.assertRaises(ProofCamError):
            compile_triage(p, loader(payloads))

    def test_11_unsorted_slots_rejected(self):
        payloads = {"a": textured(9), "b": textured(10)}
        p = packet(payloads, ("a", "b"))
        p["required_slots"].reverse()
        with self.assertRaises(ProofCamError):
            compile_triage(p, loader(payloads))

    def test_12_verify_exact_recompile_and_mutation_killer(self):
        payloads = {"front": textured(11)}
        p = packet(payloads, ("front",))
        out = compile_triage(p, loader(payloads))
        self.assertTrue(verify_triage(p, loader(payloads), out))
        mutated = copy.deepcopy(out)
        mutated["decision"]["authority"]["payment_authorized"] = True
        with self.assertRaises(ProofCamError):
            verify_triage(p, loader(payloads), mutated)

    def test_13_packet_transplant_killed(self):
        payloads = {"front": textured(12)}
        p = packet(payloads, ("front",))
        out = compile_triage(p, loader(payloads))
        p2 = copy.deepcopy(p)
        p2["packet_id"] = "packet-2"
        with self.assertRaises(ProofCamError):
            verify_triage(p2, loader(payloads), out)

    def test_14_strict_json_duplicate_key_and_nan_rejected(self):
        with self.assertRaises(ProofCamError):
            strict_json_bytes(b'{"a":1,"a":2}')
        with self.assertRaises(ProofCamError):
            strict_json_bytes(b'{"a":NaN}')

    def test_15_boolean_cannot_smuggle_identifier(self):
        payloads = {"front": textured(13)}
        p = packet(payloads, ("front",))
        p["packet_id"] = True
        with self.assertRaises(ProofCamError):
            compile_triage(p, loader(payloads))

    def test_16_aws_adapter_binds_manifest_and_image_bytes(self):
        payload = textured(14)
        p = packet({"front": payload}, ("front",))
        objects = [{"image_id": "img-front", "key": "evidence/front.png", "etag": "a" * 32, "payload_sha256": sha256(payload)}]
        manifest = json.dumps({"packet": p, "objects": objects}, sort_keys=True, separators=(",", ":")).encode()
        store = {
            ("proofcam-bucket", "manifests/job.json", "b" * 32): manifest,
            ("proofcam-bucket", "evidence/front.png", "a" * 32): payload,
        }
        def s3_get(bucket, key, etag): return store[(bucket, key, etag)]
        out = compile_s3_manifest_event({"bucket": "proofcam-bucket", "manifest_key": "manifests/job.json", "manifest_etag": "b" * 32}, s3_get)
        self.assertEqual(out["core_artifact"]["decision"]["trace"]["action"], "ACCEPT_FOR_HUMAN_REVIEW")
        self.assertFalse(out["runtime_envelope"]["aws_execution_proven"])
        self.assertEqual(len(out["adapter_receipt_sha256"]), 64)

    def test_17_aws_adapter_rejects_key_traversal(self):
        with self.assertRaises(ProofCamError):
            compile_s3_manifest_event({"bucket": "proofcam-bucket", "manifest_key": "../job.json", "manifest_etag": "b" * 32}, lambda *_: b"")

    def test_18_aws_adapter_rejects_manifest_object_set_transplant(self):
        payload = textured(15)
        p = packet({"front": payload}, ("front",))
        manifest = json.dumps({"packet": p, "objects": []}, sort_keys=True, separators=(",", ":")).encode()
        def s3_get(bucket, key, etag): return manifest
        with self.assertRaises(ProofCamError):
            compile_s3_manifest_event({"bucket": "proofcam-bucket", "manifest_key": "manifests/job.json", "manifest_etag": "b" * 32}, s3_get)

    def test_19_aws_adapter_rejects_s3_payload_mutation(self):
        payload = textured(16)
        p = packet({"front": payload}, ("front",))
        objects = [{"image_id": "img-front", "key": "evidence/front.png", "etag": "a" * 32, "payload_sha256": sha256(payload)}]
        manifest = json.dumps({"packet": p, "objects": objects}, sort_keys=True, separators=(",", ":")).encode()
        def s3_get(bucket, key, etag):
            return manifest if key.endswith("job.json") else textured(17)
        with self.assertRaises(ProofCamError):
            compile_s3_manifest_event({"bucket": "proofcam-bucket", "manifest_key": "manifests/job.json", "manifest_etag": "b" * 32}, s3_get)

    def test_20_aws_adapter_exact_recompile_kills_envelope_mutation(self):
        payload = textured(18)
        p = packet({"front": payload}, ("front",))
        objects = [{"image_id": "img-front", "key": "evidence/front.png", "etag": "a" * 32, "payload_sha256": sha256(payload)}]
        manifest = json.dumps({"packet": p, "objects": objects}, sort_keys=True, separators=(",", ":")).encode()
        store = {
            ("proofcam-bucket", "manifests/job.json", "b" * 32): manifest,
            ("proofcam-bucket", "evidence/front.png", "a" * 32): payload,
        }
        def s3_get(bucket, key, etag): return store[(bucket, key, etag)]
        event = {"bucket": "proofcam-bucket", "manifest_key": "manifests/job.json", "manifest_etag": "b" * 32}
        artifact = compile_s3_manifest_event(event, s3_get)
        self.assertTrue(verify_s3_manifest_event(event, s3_get, artifact))
        mutated = copy.deepcopy(artifact)
        mutated["runtime_envelope"]["bucket"] = "attacker-bucket"
        with self.assertRaises(ProofCamError):
            verify_s3_manifest_event(event, s3_get, mutated)

    def test_21_authority_ceiling_is_exact_false(self):
        payloads = {"front": textured(18)}
        out = compile_triage(packet(payloads, ("front",)), loader(payloads))
        self.assertEqual(set(out["decision"]["authority"]), set(AUTHORITY))
        for name, value in out["decision"]["authority"].items():
            self.assertIs(value, False, name)
        self.assertFalse(out["decision"]["truth"]["aws_runtime_proven_here"])
        self.assertFalse(out["decision"]["truth"]["competition_submission_proven_here"])


class PacketBoundaryTests(unittest.TestCase):
    def test_empty_required_slot_contract_rejected_before_loading(self):
        get = mock.Mock(return_value=b"unused")
        with self.assertRaises(ProofCamError):
            compile_triage(packet({}, ()), get)
        get.assert_not_called()

    def test_no_images_requests_all_views_without_claiming_measurement(self):
        get = mock.Mock(return_value=b"unused")
        out = compile_triage(packet({}, ("front", "side")), get)
        self.assertEqual(out["decision"]["trace"]["action"], "REQUEST_MISSING_VIEW")
        self.assertEqual(out["decision"]["trace"]["affected_slots"], ["front", "side"])
        self.assertIs(out["decision"]["truth"]["image_bytes_measured_here"], False)
        self.assertEqual(out["decision"]["measurements"], [])
        get.assert_not_called()

    def test_packet_shape_errors_precede_image_loading(self):
        payloads = {"front": textured(21), "side": textured(22)}
        base = packet(payloads)
        cases = {}
        p = copy.deepcopy(base); p["unexpected"] = True; cases["unknown top-level"] = p
        p = copy.deepcopy(base); p["required_slots"][0]["extra"] = 1; cases["unknown slot field"] = p
        p = copy.deepcopy(base); p["images"][0]["extra"] = 1; cases["unknown image field"] = p
        p = copy.deepcopy(base); p["images"] = {}; cases["images not list"] = p
        p = copy.deepcopy(base); p["required_slots"] = None; cases["slots not list"] = p
        p = copy.deepcopy(base); p["images"][1]["image_id"] = p["images"][0]["image_id"]; cases["duplicate image id"] = p
        p = copy.deepcopy(base); p["images"][1]["slot_id"] = "front"; cases["multiple images in slot"] = p
        p = copy.deepcopy(base); p["images"].reverse(); cases["reordered images"] = p
        p = copy.deepcopy(base); p["images"][0]["image_id"] = []; cases["nonstring image id"] = p
        p = copy.deepcopy(base); p["images"][0]["payload_sha256"] = True; cases["boolean digest"] = p
        for name, value in cases.items():
            with self.subTest(name=name):
                get = mock.Mock(return_value=payloads["front"])
                with self.assertRaises(ProofCamError):
                    compile_triage(value, get)
                get.assert_not_called()

    def test_strict_json_rejects_malformed_and_nonfinite_input(self):
        cases = [b"{", b"{} trailing", b"\xff", b"\xef\xbb\xbf{}",
                 b'{"nested":{"a":1,"a":2}}', b"Infinity", b"-Infinity",
                 b"1e400", b'"\\ud800"']
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ProofCamError):
                    strict_json_bytes(raw)

    def test_json_byte_limit_includes_exact_boundary(self):
        self.assertEqual(strict_json_bytes(b"{}", max_bytes=2), {})
        with self.assertRaises(ProofCamError):
            strict_json_bytes(b"{}", max_bytes=1)

    def test_json_depth_nodes_and_cycles_have_controlled_errors(self):
        depth = quality.MAX_JSON_DEPTH + 2
        deep = b"[" * depth + b"0" + b"]" * depth
        many = json.dumps([None] * (quality.MAX_JSON_NODES + 1)).encode()
        for name, raw in [("depth", deep), ("nodes", many)]:
            with self.subTest(name=name):
                with self.assertRaises(ProofCamError):
                    strict_json_bytes(raw)
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(ProofCamError):
            quality.canonical_bytes(cycle)

    def test_too_many_required_views_rejected_before_loading(self):
        slots = tuple(f"view-{i:03d}" for i in range(quality.MAX_REQUIRED_SLOTS + 1))
        get = mock.Mock(return_value=b"unused")
        with self.assertRaises(ProofCamError):
            compile_triage(packet({}, slots), get)
        get.assert_not_called()

    def test_all_64_duplicate_views_recompile_without_truncating_reasons(self):
        self.assertEqual(quality.MAX_REQUIRED_SLOTS, 64)
        same = textured(23)
        payloads = {f"view-{i:02d}": same for i in range(64)}
        p = packet(payloads, tuple(payloads))
        out = compile_triage(p, loader(payloads))
        self.assertEqual(out["decision"]["trace"]["action"], "HOLD_DUPLICATE_EVIDENCE")
        self.assertEqual(len(out["decision"]["trace"]["reasons"]), 2016)
        self.assertEqual(len(out["decision"]["trace"]["affected_slots"]), 64)
        self.assertTrue(verify_triage(p, loader(payloads), out))

    def test_packet_byte_budget_is_enforced_with_small_fixture_limit(self):
        payloads = {"front": textured(24), "side": textured(25)}
        budget = sum(map(len, payloads.values())) - 1
        with mock.patch.object(quality, "MAX_PACKET_IMAGE_BYTES", budget):
            with self.assertRaises(ProofCamError):
                compile_triage(packet(payloads), loader(payloads))

    def test_image_loader_type_is_checked(self):
        payload = textured(26)
        p = packet({"front": payload}, ("front",))
        with self.assertRaises(ProofCamError):
            compile_triage(p, lambda _: "not bytes")
        out = compile_triage(p, lambda _: bytearray(payload))
        self.assertEqual(out["decision"]["trace"]["action"], "ACCEPT_FOR_HUMAN_REVIEW")

    def test_empty_oversized_and_small_dimension_images_are_unreadable(self):
        self.assertEqual(quality.measure_image_bytes("image", b"")["reason"], "EMPTY_OR_OVERSIZE_BYTES")
        data = textured(27)
        with mock.patch.object(quality, "MAX_IMAGE_BYTES", len(data) - 1):
            self.assertEqual(quality.measure_image_bytes("image", data)["reason"], "EMPTY_OR_OVERSIZE_BYTES")
        small = png(np.full((31, 32, 3), 100, dtype=np.uint8))
        self.assertEqual(quality.measure_image_bytes("image", small)["reason"], "UNSUPPORTED_DIMENSIONS")

    def test_opencv_decode_exception_becomes_unreadable_measurement(self):
        with mock.patch.object(quality.cv2, "imdecode", side_effect=cv2.error("fixture decode failure")):
            out = quality.measure_image_bytes("image", b"fixture bytes")
        self.assertEqual(out["status"], "UNREADABLE")
        self.assertEqual(out["reason"], "OPENCV_DECODE_FAILED")
        self.assertEqual(out["payload_sha256"], sha256(b"fixture bytes"))

    def test_shadow_clipping_is_measured_separately_from_blur(self):
        image = np.zeros((160, 160, 3), dtype=np.uint8)
        cv2.line(image, (0, 0), (159, 159), (255, 255, 255), 2)
        payloads = {"front": png(image)}
        out = compile_triage(packet(payloads, ("front",)), loader(payloads))
        self.assertGreaterEqual(out["decision"]["measurements"][0]["focus_variance"], quality.MIN_FOCUS_VARIANCE)
        self.assertEqual(out["decision"]["trace"]["reasons"][0]["code"], "SHADOW_CLIPPING")

    def test_action_precedence_preserves_unreadable_duplicate_and_missing(self):
        same = textured(28)
        cases = [
            ({"front": b"invalid image"}, ("front", "side"), "HOLD_UNSAFE_OR_UNREADABLE"),
            ({"front": same, "side": same}, ("front", "side", "top"), "HOLD_DUPLICATE_EVIDENCE"),
            ({"front": blur_bytes()}, ("front", "side"), "REQUEST_MISSING_VIEW"),
        ]
        for payloads, slots, expected in cases:
            with self.subTest(expected=expected):
                out = compile_triage(packet(payloads, slots), loader(payloads))
                self.assertEqual(out["decision"]["trace"]["action"], expected)

    def test_measurement_mutation_fails_even_with_recomputed_outer_receipt(self):
        payloads = {"front": textured(29)}
        p = packet(payloads, ("front",))
        original = copy.deepcopy(p)
        out = compile_triage(p, loader(payloads))
        self.assertEqual(p, original)
        altered = copy.deepcopy(out)
        altered["decision"]["measurements"][0]["mean_luminance"] += 1
        altered["receipt_sha256"] = sha256({k: v for k, v in altered.items() if k != "receipt_sha256"})
        with self.assertRaises(ProofCamError):
            verify_triage(p, loader(payloads), altered)

    def test_authority_defaults_cannot_be_mutated(self):
        with self.assertRaises(TypeError):
            AUTHORITY["payment_authorized"] = True
        for key, value in AUTHORITY.items():
            self.assertIs(value, False, key)

    def manifest(self):
        payload = textured(30)
        p = packet({"front": payload}, ("front",))
        row = {"image_id": "img-front", "key": "evidence/front.png",
               "etag": '"' + "a" * 32 + '-2"', "payload_sha256": sha256(payload)}
        event = {"bucket": "proofcam-bucket", "manifest_key": "manifests/job.json",
                 "manifest_etag": '"' + "b" * 32 + '"'}
        return event, {"packet": p, "objects": [row]}, payload

    def test_s3_manifest_errors_stop_before_any_image_fetch(self):
        event, original, payload = self.manifest()
        cases = {}
        for value in (None, [], True):
            item = copy.deepcopy(original); item["packet"] = value; cases[str(value)] = item
        item = copy.deepcopy(original); item["packet"]["images"][0]["image_id"] = []; cases["invalid packet id"] = item
        item = copy.deepcopy(original); item["objects"][0]["image_id"] = []; cases["invalid binding id"] = item
        item = copy.deepcopy(original); item["objects"].append(copy.deepcopy(item["objects"][0])); cases["duplicate binding"] = item
        item = copy.deepcopy(original); item["objects"][0]["payload_sha256"] = "0" * 64; cases["binding disagrees with packet"] = item
        for name, manifest in cases.items():
            with self.subTest(name=name):
                calls = []
                def get(bucket, key, etag):
                    calls.append(key)
                    return json.dumps(manifest).encode() if key == event["manifest_key"] else payload
                with self.assertRaises(ProofCamError):
                    compile_s3_manifest_event(event, get)
                self.assertEqual(calls, [event["manifest_key"]])

    def test_s3_normalizes_quoted_etags_and_loads_each_bound_image_once(self):
        event, manifest, payload = self.manifest()
        manifest_bytes = json.dumps(manifest).encode()
        calls = []
        def get(bucket, key, etag):
            calls.append((bucket, key, etag))
            return manifest_bytes if key == event["manifest_key"] else payload
        out = compile_s3_manifest_event(event, get)
        self.assertEqual(calls, [
            ("proofcam-bucket", "manifests/job.json", "b" * 32),
            ("proofcam-bucket", "evidence/front.png", "a" * 32 + "-2"),
        ])
        self.assertEqual(out["runtime_envelope"]["manifest_sha256"], sha256(manifest_bytes))
        self.assertIs(out["runtime_envelope"]["aws_execution_proven"], False)


class FakeProviderBody:
    """Read-only in-memory stream; deliberately returns partial chunks."""
    def __init__(self, payload=b"abcde", chunk_size=2, failure=None):
        self.payload = payload
        self.chunk_size = chunk_size
        self.failure = failure
        self.offset = 0
        self.requests = []
        self.eof_observed = False
        self.closed = False

    def read(self, size):
        self.requests.append(size)
        if self.failure is not None:
            raise self.failure
        end = min(len(self.payload), self.offset + min(size, self.chunk_size))
        result = self.payload[self.offset:end]
        self.offset = end
        if not result:
            self.eof_observed = True
        return result

    def close(self):
        self.closed = True


class ProviderBodyBoundaryTests(unittest.TestCase):
    def response(self, body, **fields):
        return {"Body": body, "ETag": '"' + "a" * 32 + '"', **fields}

    def test_partial_chunks_are_consumed_through_eof_then_closed(self):
        body = FakeProviderBody()
        out = s3_adapter._read_provider_body(self.response(body, ContentLength=5), "a" * 32, 5)
        self.assertEqual(out, b"abcde")
        self.assertTrue(body.eof_observed)
        self.assertTrue(body.closed)
        self.assertGreater(len(body.requests), 1)
        self.assertTrue(all(0 < size <= 6 for size in body.requests))

    def test_oversized_stream_is_bounded_and_closed(self):
        body = FakeProviderBody(b"abcdef", chunk_size=6)
        with self.assertRaises(ProofCamError):
            s3_adapter._read_provider_body(self.response(body), "a" * 32, 5)
        self.assertEqual(body.offset, 6)
        self.assertTrue(body.closed)

    def test_content_length_mismatch_and_invalid_type_are_rejected(self):
        for length in (4, True, -1):
            with self.subTest(length=length):
                body = FakeProviderBody()
                with self.assertRaises(ProofCamError):
                    s3_adapter._read_provider_body(self.response(body, ContentLength=length), "a" * 32, 5)
                self.assertTrue(body.closed)

    def test_etag_mismatch_closes_without_consuming_body(self):
        body = FakeProviderBody()
        with self.assertRaises(ProofCamError):
            s3_adapter._read_provider_body(self.response(body), "b" * 32, 5)
        self.assertEqual(body.requests, [])
        self.assertTrue(body.closed)

    def test_provider_read_exception_still_closes_body(self):
        body = FakeProviderBody(failure=OSError("fictional provider read failure"))
        with self.assertRaises(OSError):
            s3_adapter._read_provider_body(self.response(body), "a" * 32, 5)
        self.assertTrue(body.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)


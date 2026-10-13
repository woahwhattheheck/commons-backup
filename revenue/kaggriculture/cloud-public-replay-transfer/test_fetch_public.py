"""Offline body/transport/consumer tests; no network or agent execution."""
import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import fetch_public as transfer


def fixture():
    expected = copy.deepcopy(transfer.BATCH[0])
    cash = expected["cash_by_seat"]
    rows = [{"status": "DONE", "reward": cash[seat],
             "observation": {"farms": [{"money": money} for money in cash]}}
            for seat in range(2)]
    value = {"name": "kaggriculture", "info": {"EpisodeId": expected["episode_id"]},
             "steps": [None] * 719 + [rows]}
    return expected, value


class Response(io.BytesIO):
    status = 200


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.expected, self.value = fixture()
        self.raw = json.dumps(self.value).encode()

    def test_plain_and_wrapped(self):
        for value in (self.value, {"result": json.dumps(self.value)}, {"replay": self.value}):
            with self.subTest(wrapper=type(value).__name__):
                raw = json.dumps(value).encode()
                summary = transfer.inspect_body(raw, self.expected)
                self.assertEqual(summary["raw_sha256"], transfer.sha256(raw))
                self.assertEqual(summary["episode_id"], self.expected["episode_id"])

    def test_numeric_identity(self):
        for number in ("../not-an-episode", True, 0, -1):
            with self.subTest(number=number), self.assertRaises(ValueError):
                transfer.episode_number({"episode_id": number})

    def test_wrong_episode(self):
        self.value["info"]["EpisodeId"] += 1
        with self.assertRaises(ValueError):
            transfer.inspect_body(json.dumps(self.value).encode(), self.expected)

    def test_missing_episode_is_external_binding(self):
        self.value["info"] = {}
        result = transfer.inspect_body(json.dumps(self.value).encode(), self.expected)
        self.assertIsNone(result["embedded_episode_id"])
        self.assertEqual(result["identity_binding"], "request_and_checkpoint")

    def test_string_embedded_id(self):
        self.value["info"]["EpisodeId"] = str(self.expected["episode_id"])
        result = transfer.inspect_body(json.dumps(self.value).encode(), self.expected)
        self.assertEqual(result["identity_binding"], "body_and_request")

    def test_incomplete_frames(self):
        self.value["steps"] = self.value["steps"][-1:]
        with self.assertRaises(ValueError):
            transfer.inspect_body(json.dumps(self.value).encode(), self.expected)

    def test_nonterminal_status(self):
        self.value["steps"][-1][1]["status"] = "ACTIVE"
        with self.assertRaises(ValueError):
            transfer.inspect_body(json.dumps(self.value).encode(), self.expected)

    def test_reward_mismatch(self):
        self.value["steps"][-1][1]["reward"] += 1
        with self.assertRaises(ValueError):
            transfer.inspect_body(json.dumps(self.value).encode(), self.expected)

    def test_farm_money_mismatch(self):
        self.value["steps"][-1][0]["observation"]["farms"][0]["money"] += 1
        with self.assertRaises(ValueError):
            transfer.inspect_body(json.dumps(self.value).encode(), self.expected)

    def test_shared_observation(self):
        self.value["steps"][-1][1]["observation"] = {}
        result = transfer.inspect_body(json.dumps(self.value).encode(), self.expected)
        self.assertEqual(result["cash_by_seat"], self.expected["cash_by_seat"])

    def test_unknown_environment(self):
        self.value["name"] = "other"
        with self.assertRaises(ValueError):
            transfer.inspect_body(json.dumps(self.value).encode(), self.expected)

    def test_ambiguous_or_deep_envelope(self):
        value = self.value
        for _ in range(9):
            value = {"result": value}
        for bad in (value, {"result": self.value, "replay": self.value}, None, "<html>"):
            with self.subTest(kind=type(bad).__name__), self.assertRaises(ValueError):
                transfer.inspect_body(json.dumps(bad).encode(), self.expected)

    def test_byte_bound(self):
        with patch.object(transfer, "MAX_BYTES", 10), self.assertRaises(ValueError):
            transfer.inspect_body(self.raw, self.expected)

    def test_exact_http_contract_one_call(self):
        calls = []
        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(self.raw)
        with tempfile.TemporaryDirectory() as tmp:
            row = transfer.retrieve_one(self.expected, Path(tmp), opener)
            self.assertEqual(row["status"], "delivered")
            self.assertEqual(len(calls), 1)
            request, timeout = calls[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.full_url, "https://api.kaggle.com/v1/competitions.CompetitionApiService/GetEpisodeReplay")
            self.assertEqual(json.loads(request.data), {"episodeId": self.expected["episode_id"]})
            self.assertEqual(timeout, 45)
            self.assertIsNone(request.get_header("Authorization"))
            self.assertIsNone(request.get_header("Cookie"))
            self.assertEqual(gzip.decompress((Path(tmp) / row["file"]).read_bytes()), self.raw)

    def test_http_failure_no_retry(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            raise urllib.error.HTTPError(request.full_url, 403, "not logged", {}, None)
        with tempfile.TemporaryDirectory() as tmp:
            row = transfer.retrieve_one(self.expected, Path(tmp), opener)
            self.assertEqual(row["status"], "unavailable")
            self.assertEqual(row["http_status"], 403)
            self.assertEqual(calls, [1])
            self.assertNotIn("not logged", json.dumps(row))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_invalid_response_is_not_a_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = transfer.retrieve_one(self.expected, Path(tmp), lambda *a, **k: Response(b"<html>challenge</html>"))
            self.assertEqual(row["status"], "unavailable")
            self.assertNotIn("challenge", json.dumps(row))
            self.assertNotIn("file", row)

    def test_consumer_exact_roundtrip_idempotent_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            row = transfer.retrieve_one(self.expected, directory, lambda *a, **k: Response(self.raw))
            manifest = {"schema": "titan.public-replay-fetch.v1", "results": [row]}
            (directory / "REPLAY-MANIFEST.json").write_text(json.dumps(manifest))
            output = directory / "decoded"
            self.assertEqual(len(transfer.unpack(directory, output)["recovered"]), 1)
            self.assertEqual(len(transfer.unpack(directory, output)["recovered"]), 1)
            target = output / (str(self.expected["episode_id"]) + ".raw")
            self.assertEqual(target.read_bytes(), self.raw)
            (directory / row["file"]).write_bytes(b"broken")
            with self.assertRaises(ValueError):
                transfer.unpack(directory, output)

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            row = transfer.retrieve_one(self.expected, directory, lambda *a, **k: Response(self.raw))
            (directory / "REPLAY-MANIFEST.json").write_text(json.dumps({"schema": "titan.public-replay-fetch.v1", "results": [row]}))
            output = directory / "decoded"
            output.mkdir()
            target = output / (str(self.expected["episode_id"]) + ".raw")
            target.write_bytes(b"existing")
            with self.assertRaises(ValueError):
                transfer.unpack(directory, output)
            self.assertEqual(target.read_bytes(), b"existing")

    def test_failure_manifest_is_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "REPLAY-MANIFEST.json").write_text(json.dumps({"schema": "titan.public-replay-fetch.v1", "results": [{"status": "unavailable"}]}))
            result = transfer.unpack(directory, directory / "decoded")
            self.assertEqual(result["recovered"], [])
            self.assertEqual(len(result["unavailable"]), 1)


if __name__ == "__main__":
    unittest.main()

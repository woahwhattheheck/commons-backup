#!/usr/bin/env python3
"""Hostile regression tests for Creator Desk multisite generation custody/framing."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import multisite_registry as registry_module
import multisite_runtime as runtime_module
from multisite import MAX_PROXY_BODY, MultiSiteRuntime, RegistryError, provision
from toolkit import Store as RealStore


class MultisiteSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "workspaces"
        self.registry_path = self.base / "registry.json"
        self.registry_path.write_text(json.dumps({
            "version": 1,
            "communities": [
                {"community_id": "alpha", "host": "alpha.example.test"},
                {"community_id": "beta", "host": "beta.example.test"},
            ],
        }), encoding="utf-8")
        self.registries = []

    def tearDown(self):
        for registry in reversed(self.registries):
            registry.close()
        self.tmp.cleanup()

    def provisioned(self):
        registry, tokens = provision(self.registry_path, self.root)
        self.registries.append(registry)
        self.assertEqual(set(tokens), {"alpha", "beta"})
        return registry, tokens

    def raw_http(self, runtime, request):
        with socket.create_connection(runtime.address[:2], timeout=4) as sock:
            sock.sendall(request)
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                part = sock.recv(65536)
                if not part:
                    break
                chunks.append(part)
        return b"".join(chunks)

    def request(self, runtime, host, path, token=None):
        headers = {"Host": host}
        if token:
            headers["Authorization"] = "Bearer " + token
        conn = http.client.HTTPConnection(*runtime.address[:2], timeout=4)
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, raw
        finally:
            conn.close()

    @staticmethod
    def put_probe(database, value):
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE generation_probe(value TEXT NOT NULL)")
            db.execute("INSERT INTO generation_probe(value) VALUES (?)", (value,))

    @staticmethod
    def read_probe(database):
        with sqlite3.connect(database) as db:
            row = db.execute("SELECT value FROM generation_probe").fetchone()
            return row[0] if row else None

    def test_database_swap_between_assert_and_store_open_cannot_attach_beta(self):
        registry, _ = self.provisioned()
        alpha = registry.by_id["alpha"]
        self.put_probe(alpha.database, "alpha")
        alpha_name = self.root / "alpha" / "workspace.sqlite3"
        parked = self.root / "alpha" / "workspace.sqlite3.parked"
        beta_name = self.root / "beta" / "workspace.sqlite3"
        swapped = False

        def swapping_store(path):
            nonlocal swapped
            if not swapped and Path(path) == alpha.database:
                os.rename(alpha_name, parked)
                os.link(beta_name, alpha_name)
                swapped = True
            # The lower layer still receives the retained /proc/self/fd/N authority.
            return RealStore(path)

        with mock.patch.object(runtime_module, "Store", side_effect=swapping_store):
            with self.assertRaisesRegex(RegistryError, "database generation changed: alpha"):
                MultiSiteRuntime(registry).start()
        self.assertTrue(swapped)
        self.assertEqual(self.read_probe(parked), "alpha")
        with self.assertRaises(sqlite3.OperationalError):
            self.read_probe(beta_name)

    def test_workspace_swap_between_provision_check_and_store_open_fails_closed(self):
        alpha = self.root / "alpha"
        beta = self.root / "beta"
        parked = self.root / "alpha.parked"
        swapped = False

        def swapping_store(path):
            nonlocal swapped
            if not swapped:
                os.rename(alpha, parked)
                os.rename(beta, alpha)
                swapped = True
            return RealStore(path)

        with mock.patch.object(registry_module, "Store", side_effect=swapping_store):
            with self.assertRaisesRegex(RegistryError, "workspace generation changed: alpha"):
                provision(self.registry_path, self.root)
        self.assertTrue(swapped)

    def test_health_validates_framing_and_closes_before_any_second_request(self):
        registry, _ = self.provisioned()
        with MultiSiteRuntime(registry) as runtime:
            good = self.raw_http(runtime, b"GET /__multisite/health HTTP/1.1\r\nHost: alpha.example.test\r\nConnection: close\r\n\r\n")
            self.assertIn(b" 200 ", good.split(b"\r\n", 1)[0])
            self.assertIn(b"Connection: close", good)

            hostile = [
                b"GET /__multisite/health HTTP/1.1\r\nHost: alpha.example.test\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n0\r\n\r\n",
                b"GET /__multisite/health HTTP/1.1\r\nHost: alpha.example.test\r\nContent-Length: 0\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                f"GET /__multisite/health HTTP/1.1\r\nHost: alpha.example.test\r\nContent-Length: {MAX_PROXY_BODY + 1}\r\nConnection: close\r\n\r\n".encode(),
            ]
            second = b"GET /__multisite/health HTTP/1.1\r\nHost: beta.example.test\r\n\r\n"
            hostile.append(
                f"GET /__multisite/health HTTP/1.1\r\nHost: alpha.example.test\r\nContent-Length: {len(second)}\r\nConnection: keep-alive\r\n\r\n".encode() + second
            )
            for raw in hostile:
                with self.subTest(raw=raw[:80]):
                    response = self.raw_http(runtime, raw)
                    self.assertIn(b" 400 ", response.split(b"\r\n", 1)[0]) if b"Content-Length: 12582913" not in raw else self.assertIn(b" 413 ", response.split(b"\r\n", 1)[0])
                    self.assertEqual(response.count(b"HTTP/1.1"), 1, response)

    def test_snapshot_reads_retained_generation_and_route_fails_after_name_swap(self):
        registry, tokens = self.provisioned()
        alpha = registry.by_id["alpha"]
        beta = registry.by_id["beta"]
        self.put_probe(alpha.database, "alpha")
        self.put_probe(beta.database, "beta")

        with MultiSiteRuntime(registry) as runtime:
            status, headers, raw = self.request(runtime, "alpha.example.test", "/workspace.sqlite3?download=1", tokens["alpha"])
            self.assertEqual(status, 200)
            self.assertEqual(headers["x-content-sha256"], hashlib.sha256(raw).hexdigest())
            snapshot = self.base / "before.sqlite3"
            snapshot.write_bytes(raw)
            self.assertEqual(self.read_probe(snapshot), "alpha")

            alpha_name = self.root / "alpha" / "workspace.sqlite3"
            parked = self.root / "alpha" / "workspace.sqlite3.parked"
            beta_name = self.root / "beta" / "workspace.sqlite3"
            os.rename(alpha_name, parked)
            os.link(beta_name, alpha_name)
            # Descriptor custody remains alpha even after the logical filename is rebound.
            self.assertEqual(self.read_probe(alpha.database), "alpha")
            retained_raw, retained_sha = runtime_module._snapshot_bytes_anchored(alpha.database)
            self.assertEqual(retained_sha, hashlib.sha256(retained_raw).hexdigest())
            retained = self.base / "retained.sqlite3"
            retained.write_bytes(retained_raw)
            self.assertEqual(self.read_probe(retained), "alpha")
            # Routing then re-proves the logical name and fails closed rather than emitting bytes.
            status, _, body = self.request(runtime, "alpha.example.test", "/workspace.sqlite3", tokens["alpha"])
            self.assertEqual(status, 503)
            self.assertIn(b"database generation changed: alpha", body)


if __name__ == "__main__":
    unittest.main()

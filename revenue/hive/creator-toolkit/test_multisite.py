#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import socket
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from multisite import (
    MAX_PROXY_BODY,
    MultiSiteRuntime,
    RegistryError,
    canonical_community_id,
    canonical_host,
    load_registry,
    provision,
)


class MultisiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "workspaces"
        self.registry_path = self.base / "registry.json"
        self.write_registry([
            {"community_id": "alpha", "host": "alpha.example.test"},
            {"community_id": "beta", "host": "beta.example.test:8443"},
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def write_registry(self, communities, **extra):
        data = {"version": 1, "communities": communities}
        data.update(extra)
        self.registry_path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    def provisioned(self):
        registry, tokens = provision(self.registry_path, self.root)
        self.assertEqual(set(tokens), {"alpha", "beta"})
        return registry, tokens

    def request(self, runtime, host, method="GET", path="/__multisite/health", payload=None, token=None):
        body = None
        headers = {"Host": host}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection(runtime.address[0], runtime.address[1], timeout=4)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            return response.status, dict((k.lower(), v) for k, v in response.getheaders()), raw
        finally:
            conn.close()

    def json_request(self, *args, **kwargs):
        status, headers, raw = self.request(*args, **kwargs)
        return status, headers, json.loads(raw.decode()) if raw else None

    def raw_http(self, runtime, request_bytes):
        with socket.create_connection((runtime.address[0], runtime.address[1]), timeout=4) as sock:
            sock.sendall(request_bytes)
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                part = sock.recv(65536)
                if not part:
                    break
                chunks.append(part)
        return b"".join(chunks)

    def test_registry_is_strict_deterministic_and_port_explicit(self):
        registry, _ = self.provisioned()
        self.assertEqual([s.community_id for s in registry.specs], ["alpha", "beta"])
        self.assertEqual(registry.resolve("ALPHA.EXAMPLE.TEST").community_id, "alpha")
        self.assertEqual(registry.resolve("BETA.EXAMPLE.TEST:8443").community_id, "beta")
        with self.assertRaises(RegistryError):
            registry.resolve("beta.example.test")
        self.assertEqual(canonical_host("A.Example.Test:443"), "a.example.test:443")
        for value in (
            "example", "https://a.example.test", "u@a.example.test", "a.example.test/", "a.example.test:0443",
            "a.example.test:0", "a.example.test:65536", "[::1]:443", "a..example.test", "a.example.test.",
            " a.example.test", "a.example.test\n",
        ):
            with self.subTest(value=value), self.assertRaises(RegistryError):
                canonical_host(value)
        for value in ("../x", "a/b", "A", "a--b", "a_thing", "a-"):
            with self.subTest(value=value), self.assertRaises(RegistryError):
                canonical_community_id(value)

    def test_duplicate_hosts_ids_keys_unknown_fields_and_nonfinite_fail(self):
        cases = [
            [{"community_id": "alpha", "host": "A.example.test"}, {"community_id": "beta", "host": "a.example.test"}],
            [{"community_id": "alpha", "host": "a.example.test"}, {"community_id": "alpha", "host": "b.example.test"}],
        ]
        for communities in cases:
            self.write_registry(communities)
            with self.assertRaises(RegistryError):
                load_registry(self.registry_path, self.root, create_workspaces=True)
        self.registry_path.write_text('{"version":1,"version":1,"communities":[{"community_id":"a","host":"a.example.test"}]}')
        with self.assertRaises(RegistryError):
            load_registry(self.registry_path, self.root, create_workspaces=True)
        self.registry_path.write_text('{"version":1,"communities":[{"community_id":"a","host":"a.example.test","extra":1}]}')
        with self.assertRaises(RegistryError):
            load_registry(self.registry_path, self.root, create_workspaces=True)
        self.registry_path.write_text('{"version":1,"communities":[{"community_id":"a","host":"a.example.test"}],"extra":1}')
        with self.assertRaises(RegistryError):
            load_registry(self.registry_path, self.root, create_workspaces=True)
        self.registry_path.write_text('{"version":NaN,"communities":[]}')
        with self.assertRaises(RegistryError):
            load_registry(self.registry_path, self.root, create_workspaces=True)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_workspace_symlink_escape_is_rejected(self):
        self.root.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        os.symlink(outside, self.root / "alpha", target_is_directory=True)
        self.write_registry([{"community_id": "alpha", "host": "alpha.example.test"}])
        with self.assertRaises(RegistryError):
            load_registry(self.registry_path, self.root, create_workspaces=True)

    def test_readonly_load_does_not_create_missing_workspace_root(self):
        self.assertFalse(self.root.exists())
        with self.assertRaisesRegex(RegistryError, "workspace root is not provisioned"):
            load_registry(self.registry_path, self.root)
        self.assertFalse(self.root.exists())

    def test_provision_creates_distinct_db_and_auth_without_persisting_plaintext(self):
        registry, tokens = self.provisioned()
        alpha, beta = registry.by_id["alpha"], registry.by_id["beta"]
        self.assertNotEqual(alpha.database, beta.database)
        self.assertTrue(alpha.database.is_file())
        self.assertTrue(beta.database.is_file())
        registry_bytes = self.registry_path.read_bytes()
        for token in tokens.values():
            needle = token.encode()
            self.assertNotIn(needle, registry_bytes)
            for path in self.root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(needle, path.read_bytes(), str(path))
        # Re-provisioning exposes no replacement/plaintext key.
        _, again = provision(self.registry_path, self.root)
        self.assertEqual(again, {})

    def test_exact_host_routes_and_operator_capabilities_are_tenant_scoped(self):
        registry, tokens = self.provisioned()
        with MultiSiteRuntime(registry) as runtime:
            status, headers, body = self.json_request(runtime, "alpha.example.test")
            self.assertEqual(status, 200)
            self.assertEqual(body["community_id"], "alpha")
            self.assertEqual(headers["x-creator-community"], "alpha")
            status, _, body = self.json_request(runtime, "unknown.example.test")
            self.assertEqual(status, 421)
            self.assertIn("not registered", body["error"])

            for target_host, wrong in (("alpha.example.test", tokens["beta"]), ("beta.example.test:8443", tokens["alpha"])):
                status, _, _ = self.json_request(runtime, target_host, path="/api/operator", token=wrong)
                self.assertEqual(status, 403)
            for target_host, key in (("alpha.example.test", tokens["alpha"]), ("beta.example.test:8443", tokens["beta"])):
                status, _, body = self.json_request(runtime, target_host, path="/api/operator", token=key)
                self.assertEqual(status, 200)
                self.assertEqual(body, {"operator": True})

    def _create_resource(self, runtime, host, token, op, title):
        status, _, body = self.json_request(runtime, host, method="POST", path="/api/change", token=token, payload={
            "action": "resource.create",
            "operation_id": op,
            "payload": {"title": title, "description": "", "kind": "link", "target": f"https://example.com/{title.lower()}", "sequence": []},
        })
        self.assertEqual(status, 200, body)
        return body

    def test_same_member_and_operator_mutations_remain_isolated(self):
        registry, tokens = self.provisioned()
        with MultiSiteRuntime(registry) as runtime:
            ra = self._create_resource(runtime, "alpha.example.test", tokens["alpha"], "resource-a", "Alpha")
            rb = self._create_resource(runtime, "beta.example.test:8443", tokens["beta"], "resource-b", "Beta")
            for host, resource, op in (
                ("alpha.example.test", ra, "request-a"),
                ("beta.example.test:8443", rb, "request-b"),
            ):
                status, _, body = self.json_request(runtime, host, method="POST", path="/api/change", payload={
                    "action": "request", "operation_id": op,
                    "payload": {"resource_id": resource["id"], "email": "same@example.test", "name": "Same", "opt_in": False},
                })
                self.assertEqual(status, 200, body)
                status, _, member = self.json_request(runtime, host, path="/api/member?id=" + body["member_id"])
                self.assertEqual(status, 200)
                self.assertEqual(member["email"], "same@example.test")

            status, _, a_catalog = self.json_request(runtime, "alpha.example.test", path="/api/catalog")
            self.assertEqual(status, 200)
            status, _, b_catalog = self.json_request(runtime, "beta.example.test:8443", path="/api/catalog")
            self.assertEqual(status, 200)
            self.assertEqual([x["title"] for x in a_catalog["resources"]], ["Alpha"])
            self.assertEqual([x["title"] for x in b_catalog["resources"]], ["Beta"])

    def test_restart_preserves_isolated_state(self):
        registry, tokens = self.provisioned()
        with MultiSiteRuntime(registry) as runtime:
            self._create_resource(runtime, "alpha.example.test", tokens["alpha"], "persist-a", "Persist")
        registry2 = load_registry(self.registry_path, self.root)
        with MultiSiteRuntime(registry2) as runtime:
            status, _, a_catalog = self.json_request(runtime, "alpha.example.test", path="/api/catalog")
            status_b, _, b_catalog = self.json_request(runtime, "beta.example.test:8443", path="/api/catalog")
            self.assertEqual((status, status_b), (200, 200))
            self.assertEqual([x["title"] for x in a_catalog["resources"]], ["Persist"])
            self.assertEqual(b_catalog["resources"], [])

    def test_concurrent_tenant_requests_do_not_mix(self):
        registry, _ = self.provisioned()
        with MultiSiteRuntime(registry) as runtime:
            def one(index):
                host = "alpha.example.test" if index % 2 == 0 else "beta.example.test:8443"
                expected = "alpha" if index % 2 == 0 else "beta"
                status, headers, body = self.json_request(runtime, host)
                return status, headers.get("x-creator-community"), body["community_id"], expected
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(one, range(80)))
            for status, header, body, expected in results:
                self.assertEqual((status, header, body), (200, expected, expected))

    def test_transfer_encoding_oversize_missing_duplicate_and_invalid_host_fail_closed(self):
        registry, _ = self.provisioned()
        with MultiSiteRuntime(registry) as runtime:
            response = self.raw_http(runtime, b"GET / HTTP/1.1\r\nConnection: close\r\n\r\n")
            self.assertIn(b" 400 ", response.split(b"\r\n", 1)[0])
            response = self.raw_http(runtime, b"GET / HTTP/1.1\r\nHost: alpha.example.test\r\nHost: beta.example.test:8443\r\nConnection: close\r\n\r\n")
            self.assertIn(b" 400 ", response.split(b"\r\n", 1)[0])
            response = self.raw_http(runtime, b"POST /api/change HTTP/1.1\r\nHost: alpha.example.test\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n0\r\n\r\n")
            self.assertIn(b" 400 ", response.split(b"\r\n", 1)[0])
            raw = f"POST /api/change HTTP/1.1\r\nHost: alpha.example.test\r\nContent-Length: {MAX_PROXY_BODY + 1}\r\nConnection: close\r\n\r\n".encode()
            response = self.raw_http(runtime, raw)
            self.assertIn(b" 413 ", response.split(b"\r\n", 1)[0])

    def test_runtime_rejects_public_bind_and_stops_threads(self):
        registry, _ = self.provisioned()
        with self.assertRaises(RegistryError):
            MultiSiteRuntime(registry, bind_host="0.0.0.0")
        runtime = MultiSiteRuntime(registry).start()
        threads = [runtime.thread] + [tenant.thread for tenant in runtime.tenants.values()]
        self.assertTrue(all(t.is_alive() for t in threads))
        runtime.close()
        self.assertTrue(all(not t.is_alive() for t in threads))


if __name__ == "__main__":
    unittest.main()

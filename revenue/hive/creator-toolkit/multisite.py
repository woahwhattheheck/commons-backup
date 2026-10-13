#!/usr/bin/env python3
"""Local multi-community control plane for Creator Desk.

This additive facade exposes strict registry/provisioning and a loopback Host
router while leaving the existing single-community Store/app semantics intact.
It owns no billing, DNS, TLS, IdP, email, customer-contact, payment, or public
deployment authority.
"""
from __future__ import annotations

import argparse
import json

from toolkit import Store
from multisite_registry import (
    MAX_PROXY_BODY, CommunitySpec, Registry, RegistryError,
    canonical_community_id, canonical_host, load_registry, provision,
)
from multisite_runtime import MultiSiteRuntime

__all__ = [
    "MAX_PROXY_BODY", "CommunitySpec", "Registry", "RegistryError",
    "MultiSiteRuntime", "canonical_community_id", "canonical_host",
    "load_registry", "provision",
]


def _registry_summary(registry: Registry):
    return [{"community_id": spec.community_id, "host": spec.host} for spec in registry.specs]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, help="Strict JSON community registry")
    parser.add_argument("--workspace-root", required=True, help="Dedicated workspace root directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Validate registry and already-provisioned workspaces")
    sub.add_parser("provision", help="Provision shared community workspaces")
    serve = sub.add_parser("serve", help="Run loopback multi-community Host router")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()

    if args.command == "provision":
        registry, created = provision(args.registry, args.workspace_root)
        try:
            # The legacy keys field stays empty for output-shape compatibility.
            print(json.dumps({"communities": _registry_summary(registry), "one_time_operator_keys": created}, sort_keys=True))
        finally:
            registry.close()
        return

    registry = load_registry(args.registry, args.workspace_root, create_workspaces=False)
    try:
        if args.command == "validate":
            for spec in registry.specs:
                registry.assert_spec(spec)
                Store(spec.database)
                registry.assert_spec(spec)
            print(json.dumps({"communities": _registry_summary(registry), "valid": True}, sort_keys=True))
            return

        runtime = MultiSiteRuntime(registry, bind_host=args.host, port=args.port).start()
        host, port = runtime.address[:2]
        print(f"Creator Desk multisite: http://{host}:{port}/", flush=True)
        print("Routing is exact-Host and loopback-only; no default tenant, TLS, DNS, billing, email, or public deployment is provided.", flush=True)
        try:
            runtime.thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            runtime.close()
    finally:
        registry.close()


if __name__ == "__main__":
    main()

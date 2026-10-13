"""Import-only equipment wraps for landed diagnostic operator cards.

TENON claims:
- tenon-r4-equipment-diagnostic-cards-20260905-01 (contract/receipt)
- tenon-r4-equipment-fulfill-sla-cards-20260905-01 (fulfill deadline/SLA)
- tenon-r4-equipment-advance-obligation-card-20260906-01 (advance obligation)
- tenon-r4-equipment-open-obligations-card-20260906-01 (full open queue)
- tenon-r4-equipment-release-equip-cards-20260906-01 (release/equip)
- tenon-r4-equipment-transfer-role-card-20260906-01 (transfer)
- tenon-r4-equipment-bind-unbind-route-cards-20260906-01 (bind/unbind)
- tenon-r4-equipment-export-import-package-cards-20260906-01 (export/import)
- tenon-r4-equipment-inspect-role-card-20260906-01 (inspect)
- tenon-r4-equipment-normalize-role-card-20260912-01 (normalize)
HINGE claim:
- hinge-r4-equipment-prove-handoff-card-20260906-01 (prove-handoff)
- hinge-r4-equipment-create-role-card-20260912-01 (create)
- hinge-r4-equipment-list-role-ids-card-20260912-01 (list_ids)
- hinge-r4-equipment-get-role-card-20260912-01 (get)
WEDGE claim:
- wedge-r4-equipment-open-obligations-cash-card-20260905-01 (cash queue)
Does not remint contracts, receipts, fulfill CLIs, SPARK paid_case, Stripe, or peers remint.
"""

from __future__ import annotations

import tempfile
from typing import Any

from .services import _schema


def _load_transferable_roles_mod(name: str):
    """Import a module from integrations/transferable_roles (sibling scripts)."""
    import importlib
    import sys
    from pathlib import Path

    package_dir = Path(__file__).resolve().parents[1] / "transferable_roles"
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return importlib.import_module(name)


def _add_read_role(roles_mod, indexed: dict[str, dict[str, Any]], raw: dict[str, Any]) -> None:
    """Normalize supplied role bytes without creating a temporary store."""
    role = roles_mod.normalize_role(raw)
    key = roles_mod.role_storage_key(role["role_id"])
    if key in indexed:
        raise roles_mod.RoleError(f"role_id already exists: {role['role_id']}")
    indexed[key] = role


def diagnostic_card_tool_schemas() -> list[dict]:
    return [
        _schema(
            "diagnostic_contract_card",
            "Load landed $199 diagnostic contract.json operator card for a transferable role. Pass role object + slug dealer|referral|repair|plant. Import-only wrap of diagnostic_contract.load_contract_from_role; does not remint.",
            {"role": "object", "slug": "string"},
        ),
        _schema(
            "diagnostic_receipt_card",
            "Load landed $199 diagnostic receipt.json operator card for a transferable role. Pass role object + slug dealer|referral|plant (repair has no twin). Import-only wrap of diagnostic_receipt.load_receipt_from_role; does not remint.",
            {"role": "object", "slug": "string"},
        ),
        _schema(
            "diagnostic_fulfill_deadline_card",
            "Compute $199 diagnostic delivery_due_at for a transferable role. Pass role + slug + usable_evidence_at. Import-only wrap of diagnostic_fulfill.run_deadline; does not remint.",
            {
                "role": "object",
                "slug": "string",
                "usable_evidence_at": "string",
            },
        ),
        _schema(
            "diagnostic_fulfill_sla_card",
            "OPEN|MISSED $199 diagnostic SLA card for a transferable role. Pass role + slug + usable_evidence_at + as_of. Import-only wrap of diagnostic_fulfill.run_sla_status; does not remint.",
            {
                "role": "object",
                "slug": "string",
                "usable_evidence_at": "string",
                "as_of": "string",
            },
        ),
        _schema(
            "open_obligations_cash_card",
            "Open obligations for roles with payment_capability metadata; this marker is not proof of payment. Pass roles[] (role objects). Uses shared open_obligation_rows(cash_only=True) in memory.",
            {"roles": "array"},
        ),
        _schema(
            "open_obligations_card",
            "Open obligations across roles (CRM + paid). Pass roles[]; optional cash_only (default false). Uses shared open_obligation_rows in memory.",
            {"roles": "array"},
            {"cash_only": "boolean"},
        ),
        _schema(
            "advance_obligation_card",
            "Advance one obligation on a transferable role (status / next_action / evidence_pointer). Pass role object + obligation_id + at least one field. Import-only RoleStore.advance_obligation wrap; returns updated role. Does not remint roles.py or grant credentials.",
            {"role": "object", "obligation_id": "string"},
            {
                "status": "string",
                "next_action": "string",
                "evidence_pointer": "string",
            },
        ),
        _schema(
            "equip_role_card",
            "Equip a transferable role with a session occupant. Pass role + session_id + harness; optional seat / account_pool. Import-only RoleStore.equip wrap; returns updated role. Does not remint roles.py.",
            {"role": "object", "session_id": "string", "harness": "string"},
            {"seat": "string", "account_pool": "string"},
        ),
        _schema(
            "release_occupant_card",
            "Release the current occupant from a transferable role. Pass role; optional from_session_id guard. Import-only RoleStore.release wrap; returns updated role. Does not remint roles.py.",
            {"role": "object"},
            {"from_session_id": "string"},
        ),
        _schema(
            "transfer_role_card",
            "Transfer occupant on a transferable role to a new session. Pass role + to_session_id + to_harness; optional from_session_id / seat / account_pool. Import-only RoleStore.transfer wrap; returns updated role. Does not remint roles.py.",
            {"role": "object", "to_session_id": "string", "to_harness": "string"},
            {
                "from_session_id": "string",
                "seat": "string",
                "account_pool": "string",
            },
        ),
        _schema(
            "bind_access_route_card",
            "Stamp durable G2 recover fields onto a named access_route. Pass role + route_name + at least one of session_id|last_run_id|pool_id. Import-only RoleStore.bind_access_route wrap; returns updated role. Does not remint roles.py.",
            {"role": "object", "route_name": "string"},
            {
                "session_id": "string",
                "last_run_id": "string",
                "pool_id": "string",
            },
        ),
        _schema(
            "unbind_access_route_card",
            "Clear stamped BINDABLE_ROUTE_FIELDS on a named access_route (default session_id+last_run_id). Pass role + route_name; optional fields[]. Import-only RoleStore.unbind_access_route wrap; returns updated role. Does not remint roles.py.",
            {"role": "object", "route_name": "string"},
            {"fields": "array"},
        ),
        _schema(
            "export_role_package_card",
            "Export a portable role package (occupant cleared; no secrets; export_meta stamped). Pass role object. Uses shared export_role_package in memory.",
            {"role": "object"},
        ),
        _schema(
            "import_role_package_card",
            "Import a portable role package into a fresh store (occupant None; refuse remint if role_id exists). Pass package object. Import-only RoleStore.import_package wrap. Does not remint roles.py.",
            {"package": "object"},
        ),
        _schema(
            "inspect_role_card",
            "Inspect/normalize a transferable role (schema scrub + drop secret-shaped keys). Pass role object. Uses shared normalize_role in memory and returns the scrubbed role.",
            {"role": "object"},
        ),
        _schema(
            "create_role_card",
            "Create a transferable role in a tempfile RoleStore (normalize + refuse remint if role_id exists). Pass role object; optional role_id override. Import-only RoleStore.create wrap; returns created role. Does not remint roles.py.",
            {"role": "object"},
            {"role_id": "string"},
        ),
        _schema(
            "list_role_ids_card",
            "List role_ids from supplied transferable roles in memory. Pass roles (array of role objects). Returns the original role identifiers with shared normalization and duplicate detection.",
            {"roles": "array"},
        ),
        _schema(
            "get_role_card",
            "Get a transferable role from supplied role objects in memory. Pass role_id plus roles (array) or role (object). Accepts the original identifier or its existing storage key and returns the normalized role.",
            {"role_id": "string"},
            {"roles": "array", "role": "object"},
        ),
    _schema(
        "normalize_role_card",
        "Normalize a transferable role in-memory (schema scrub + drop secret-shaped keys; no store write). Pass role object; optional role_id. Import-only roles.normalize_role wrap. Does not remint roles.py or remint create/inspect/get.",
        {"role": "object"},
        {"role_id": "string"},
    ),
    _schema(
            "prove_handoff_card",
            "Prove role-gated executes still run for a transferable role (tempfile store). Pass role; optional case_ref, usable_evidence_at, slug (maps to diagnostic_slug), as_of. Import-only wrap of handoff_execute.prove_successor_executes; does not remint CLI prove-handoff body.",
            {"role": "object"},
            {
                "case_ref": "string",
                "usable_evidence_at": "string",
                "slug": "string",
                "as_of": "string",
            },
        ),
    ]


def call_diagnostic_card(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Handle diagnostic_*_card tools; None if unknown."""
    if name == "diagnostic_contract_card":
        roles_mod = _load_transferable_roles_mod("roles")
        contract_mod = _load_transferable_roles_mod("diagnostic_contract")
        try:
            card = contract_mod.load_contract_from_role(
                args["role"], slug=str(args["slug"])
            )
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "card": card}
    if name == "diagnostic_receipt_card":
        roles_mod = _load_transferable_roles_mod("roles")
        receipt_mod = _load_transferable_roles_mod("diagnostic_receipt")
        try:
            card = receipt_mod.load_receipt_from_role(
                args["role"], slug=str(args["slug"])
            )
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "card": card}
    if name == "diagnostic_fulfill_deadline_card":
        roles_mod = _load_transferable_roles_mod("roles")
        fulfill_mod = _load_transferable_roles_mod("diagnostic_fulfill")
        try:
            card = fulfill_mod.run_deadline(
                args["role"],
                slug=str(args["slug"]),
                usable_evidence_at=str(args["usable_evidence_at"]),
            )
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "card": card}
    if name == "diagnostic_fulfill_sla_card":
        roles_mod = _load_transferable_roles_mod("roles")
        fulfill_mod = _load_transferable_roles_mod("diagnostic_fulfill")
        try:
            card = fulfill_mod.run_sla_status(
                args["role"],
                slug=str(args["slug"]),
                usable_evidence_at=str(args["usable_evidence_at"]),
                as_of=str(args["as_of"]),
            )
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "card": card}





    if name == "open_obligations_cash_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            roles = args["roles"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(roles, list) or not roles:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "roles must be a nonempty array",
            }
        try:
            indexed: dict[str, dict[str, Any]] = {}
            for raw in roles:
                if not isinstance(raw, dict):
                    raise roles_mod.RoleError("each role must be an object")
                _add_read_role(roles_mod, indexed, raw)
            rows = roles_mod.open_obligation_rows(indexed.values(), cash_only=True)
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "open_obligations": rows}
    if name == "open_obligations_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            roles = args["roles"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(roles, list) or not roles:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "roles must be a nonempty array",
            }
        cash_only = bool(args.get("cash_only", False))
        try:
            indexed: dict[str, dict[str, Any]] = {}
            for raw in roles:
                if not isinstance(raw, dict):
                    raise roles_mod.RoleError("each role must be an object")
                _add_read_role(roles_mod, indexed, raw)
            rows = roles_mod.open_obligation_rows(indexed.values(), cash_only=cash_only)
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "open_obligations": rows, "cash_only": cash_only}
    if name == "advance_obligation_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
            obligation_id = str(args["obligation_id"])
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        kwargs: dict[str, Any] = {}
        if args.get("status") is not None:
            kwargs["status"] = str(args["status"])
        if args.get("next_action") is not None:
            kwargs["next_action"] = str(args["next_action"])
        if args.get("evidence_pointer") is not None:
            kwargs["evidence_pointer"] = str(args["evidence_pointer"])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                created = store.create(role)
                updated = store.advance_obligation(
                    created["role_id"],
                    obligation_id,
                    **kwargs,
                )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": updated}
    if name == "equip_role_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
            session_id = str(args["session_id"])
            harness = str(args["harness"])
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                created = store.create(role)
                updated = store.equip(
                    created["role_id"],
                    session_id=session_id,
                    harness=harness,
                    seat=args.get("seat"),
                    account_pool=args.get("account_pool"),
                )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": updated}
    if name == "release_occupant_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                created = store.create(role)
                updated = store.release(
                    created["role_id"],
                    from_session_id=args.get("from_session_id"),
                )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": updated}
    if name == "transfer_role_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
            to_session_id = str(args["to_session_id"])
            to_harness = str(args["to_harness"])
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                created = store.create(role)
                updated = store.transfer(
                    created["role_id"],
                    to_session_id=to_session_id,
                    to_harness=to_harness,
                    from_session_id=args.get("from_session_id"),
                    seat=args.get("seat"),
                    account_pool=args.get("account_pool"),
                )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": updated}
    if name == "bind_access_route_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
            route_name = str(args["route_name"])
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                created = store.create(role)
                updated = store.bind_access_route(
                    created["role_id"],
                    route_name=route_name,
                    session_id=args.get("session_id"),
                    last_run_id=args.get("last_run_id"),
                    pool_id=args.get("pool_id"),
                )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": updated}
    if name == "unbind_access_route_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
            route_name = str(args["route_name"])
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        fields = args.get("fields")
        if fields is not None and not isinstance(fields, (list, tuple)):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "fields must be an array when provided",
            }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                created = store.create(role)
                updated = store.unbind_access_route(
                    created["role_id"],
                    route_name=route_name,
                    fields=fields,
                )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": updated}
    if name == "export_role_package_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        try:
            package = roles_mod.export_role_package(roles_mod.normalize_role(role))
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "package": package}
    if name == "import_role_package_card":
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            package = args["package"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(package, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "package must be an object",
            }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                adopted = store.import_package(package)
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": adopted}
    if name == "inspect_role_card":
        # tenon-r4-equipment-inspect-role-card-20260906-01
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        try:
            inspected = roles_mod.normalize_role(role)
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": inspected}
    if name == "get_role_card":
        # hinge-r4-equipment-get-role-card-20260912-01
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role_id = str(args["role_id"])
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        roles = args.get("roles")
        role = args.get("role")
        batch: list = []
        if roles is not None:
            if not isinstance(roles, list):
                return {
                    "ok": False,
                    "error": "missing_argument",
                    "message": "roles must be an array",
                }
            batch = roles
        elif role is not None:
            if not isinstance(role, dict):
                return {
                    "ok": False,
                    "error": "missing_argument",
                    "message": "role must be an object",
                }
            batch = [role]
        else:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing roles or role",
            }
        try:
            indexed: dict[str, dict[str, Any]] = {}
            for idx, item in enumerate(batch):
                if not isinstance(item, dict):
                    return {
                        "ok": False,
                        "error": "missing_argument",
                        "message": "roles[%s] must be an object" % idx,
                    }
                _add_read_role(roles_mod, indexed, item)
            key = roles_mod.role_storage_key(role_id)
            if key not in indexed:
                raise roles_mod.RoleError(f"role not found: {role_id}")
            got = indexed[key]
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": got}
    if name == "list_role_ids_card":
        # hinge-r4-equipment-list-role-ids-card-20260912-01
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            roles = args["roles"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(roles, list):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "roles must be an array",
            }
        try:
            indexed: dict[str, dict[str, Any]] = {}
            for idx, role in enumerate(roles):
                if not isinstance(role, dict):
                    return {
                        "ok": False,
                        "error": "missing_argument",
                        "message": "roles[%s] must be an object" % idx,
                    }
                _add_read_role(roles_mod, indexed, role)
            role_ids = sorted(role["role_id"] for role in indexed.values())
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role_ids": role_ids}
    if name == "create_role_card":
        # hinge-r4-equipment-create-role-card-20260912-01
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        role_id = args.get("role_id")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                if role_id is not None:
                    created = store.create(role, role_id=str(role_id))
                else:
                    created = store.create(role)
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": created}
    if name == "normalize_role_card":
        # tenon-r4-equipment-normalize-role-card-20260912-01
        roles_mod = _load_transferable_roles_mod("roles")
        try:
            role = args["role"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        role_id = args.get("role_id")
        try:
            normalized = roles_mod.normalize_role(
                role,
                role_id=str(role_id) if role_id is not None else None,
            )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "role": normalized}
    if name == "prove_handoff_card":

        # hinge-r4-equipment-prove-handoff-card-20260906-01
        roles_mod = _load_transferable_roles_mod("roles")
        handoff_mod = _load_transferable_roles_mod("handoff_execute")
        try:
            role = args["role"]
        except KeyError as exc:
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "missing %s" % exc,
            }
        if not isinstance(role, dict):
            return {
                "ok": False,
                "error": "missing_argument",
                "message": "role must be an object",
            }
        kwargs: dict[str, Any] = {}
        if args.get("case_ref") is not None:
            kwargs["case_ref"] = str(args["case_ref"])
        if args.get("usable_evidence_at") is not None:
            kwargs["usable_evidence_at"] = str(args["usable_evidence_at"])
        if args.get("slug") is not None:
            kwargs["diagnostic_slug"] = str(args["slug"])
        if args.get("as_of") is not None:
            kwargs["as_of"] = str(args["as_of"])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = roles_mod.RoleStore(tmp)
                created = store.create(role)
                proof = handoff_mod.prove_successor_executes(
                    store,
                    created["role_id"],
                    **kwargs,
                )
        except roles_mod.RoleError as exc:
            return {"ok": False, "error": "role_refused", "message": str(exc)}
        return {"ok": True, "proof": proof}
    return None


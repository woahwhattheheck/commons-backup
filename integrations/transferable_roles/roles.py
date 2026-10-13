#!/usr/bin/env python3
"""Mechanisms for roles that equip and hand on between sessions/harnesses.

A role is the durable package. The current session is an occupant, not the
container. Secrets never live in the role record — only named access routes
and store pointers that already exist elsewhere.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLE_SCHEMA = "commons.transferable_role/v1"
SECRET_FIELD_NAMES = frozenset(
    {
        "secret",
        "secrets",
        "token",
        "tokens",
        "password",
        "api_key",
        "apikey",
        "credential",
        "credentials",
        "private_key",
        "access_token",
        "refresh_token",
        "client_secret",
    }
)
_SECRET_KEY_RE = re.compile(
    r"(secret|token|password|api[_-]?key|credential|private[_-]?key)",
    re.IGNORECASE,
)

# G2 grokbot_control route fields (SPARK #8761). Seat is occupant name, not role_id.
GROKBOT_CONTROL_ROUTE_FIELDS = (
    "pool_id",
    "session_id",
    "last_run_id",
    "seat",
    "client",
)

# Fields stampable onto an existing access_route (no secrets; seat stays on occupant).
BINDABLE_ROUTE_FIELDS = ("session_id", "last_run_id", "pool_id")

# Default unbind clears recover stamps only; fixture pool_id stays unless asked.
DEFAULT_UNBIND_FIELDS = ("session_id", "last_run_id")

OBLIGATION_STATUSES = frozenset({"open", "done", "blocked", "deferred"})


class RoleError(ValueError):
    """Invalid role operation or record."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoleError(f"{field} must be a nonempty string")
    return value.strip()


def _scrub_secrets(obj: Any, *, path: str = "$") -> Any:
    """Drop secret-shaped keys; never store secret values in role records."""
    if isinstance(obj, dict):
        clean: dict[str, Any] = {}
        for key, value in obj.items():
            key_s = str(key)
            if key_s.lower() in SECRET_FIELD_NAMES or _SECRET_KEY_RE.search(key_s):
                continue
            clean[key_s] = _scrub_secrets(value, path=f"{path}.{key_s}")
        return clean
    if isinstance(obj, list):
        return [_scrub_secrets(item, path=f"{path}[]") for item in obj]
    return obj


def _normalize_obligation(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise RoleError("each obligation must be an object")
    out = {
        "id": _require_str(item.get("id") or uuid.uuid4().hex[:12], "obligation.id"),
        "summary": _require_str(item.get("summary"), "obligation.summary"),
        "next_action": _require_str(item.get("next_action"), "obligation.next_action"),
        "status": str(item.get("status") or "open").strip().lower() or "open",
    }
    if item.get("evidence_pointer"):
        out["evidence_pointer"] = _require_str(
            item.get("evidence_pointer"), "obligation.evidence_pointer"
        )
    if item.get("due"):
        out["due"] = str(item["due"]).strip()
    return out


def _normalize_tool(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise RoleError("each tool must be an object")
    out = {
        "name": _require_str(item.get("name"), "tool.name"),
        "entry": _require_str(item.get("entry"), "tool.entry"),
    }
    if item.get("notes"):
        out["notes"] = str(item["notes"]).strip()
    return out


def _normalize_access_route(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise RoleError("each access_route must be an object")
    out = {
        "name": _require_str(item.get("name"), "access_route.name"),
        "kind": _require_str(item.get("kind"), "access_route.kind"),
    }
    for field in (
        "base_url",
        "submit",
        "status",
        "events",
        "follow_up",
        "cancel",
        "recover",
        "store",
        "service_tag",
        "note",
        *GROKBOT_CONTROL_ROUTE_FIELDS,
    ):
        if item.get(field):
            out[field] = str(item[field]).strip()
    # Never accept secret material on a route.
    return _scrub_secrets(out)


def _role_has_payment_capability(role: dict[str, Any]) -> bool:
    """True when the role routes a named public payment_capability door."""
    for route in role.get("access_routes") or []:
        if not isinstance(route, dict):
            continue
        if str(route.get("name") or "").strip() == "payment_capability":
            return True
    return False


def _commons_root() -> Path:
    return Path(__file__).resolve().parents[2]


_REFUND_FORBIDDEN_PREFIXES = ("sk_", "rk_", "whsec_", "prod_", "price_", "plink_")


def _forbid_refund_secrets(refund: str) -> str:
    text = str(refund or "").strip()
    if not text:
        raise RoleError("refund must be a nonempty string")
    for forbidden in _REFUND_FORBIDDEN_PREFIXES:
        if forbidden in text:
            raise RoleError(f"refund leaked forbidden token prefix {forbidden}")
    return text


def _role_cash_fields(role: dict[str, Any]) -> dict[str, Any] | None:
    """amount_usd + refund for cash open-obligation rows when tools resolve them.

    diagnostic_contract / diagnostic_fulfill → commercial.diagnostic_usd +
    commercial.refund (same forbid).
    Else None. If a matching tool is present but the landed source is unreadable,
    raise RoleError (fail-closed so bugs surface).
    """
    names: set[str] = set()
    for tool in role.get("tools") or []:
        if isinstance(tool, dict) and tool.get("name"):
            names.add(str(tool["name"]).strip())
    root = _commons_root()
    if "diagnostic_contract" in names or "diagnostic_fulfill" in names:
        path = root / "revenue" / "dealer_service_lead_rescue" / "contract.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            commercial = data["commercial"]
            amount = int(commercial["diagnostic_usd"])
            refund = _forbid_refund_secrets(commercial["refund"])
            return {"amount_usd": amount, "refund": refund}
        except RoleError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface contract bugs fail-closed
            raise RoleError(
                "diagnostic tools present but commercial cash fields "
                f"unreadable: {exc}"
            ) from exc
    return None


def _role_amount_usd(role: dict[str, Any]) -> int | None:
    """USD unit price wrapper over _role_cash_fields (compat for callers)."""
    cash = _role_cash_fields(role)
    return None if cash is None else cash["amount_usd"]


def normalize_role(raw: dict[str, Any], *, role_id: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RoleError("role must be an object")
    scrubbed = _scrub_secrets(raw)
    rid = role_id or scrubbed.get("role_id") or f"role-{uuid.uuid4().hex[:12]}"
    purpose = _require_str(scrubbed.get("purpose"), "purpose")
    knowledge = scrubbed.get("knowledge") or []
    if not isinstance(knowledge, list):
        raise RoleError("knowledge must be a list of source pointers")
    clean_knowledge: list[dict[str, Any]] = []
    for item in knowledge:
        if isinstance(item, str):
            clean_knowledge.append({"pointer": item.strip()})
        elif isinstance(item, dict) and item.get("pointer"):
            clean_knowledge.append(
                {
                    "pointer": _require_str(item.get("pointer"), "knowledge.pointer"),
                    **(
                        {"label": str(item["label"]).strip()}
                        if item.get("label")
                        else {}
                    ),
                }
            )
        else:
            raise RoleError("knowledge items need a pointer string")
    obligations = [_normalize_obligation(x) for x in (scrubbed.get("obligations") or [])]
    tools = [_normalize_tool(x) for x in (scrubbed.get("tools") or [])]
    access_routes = [
        _normalize_access_route(x) for x in (scrubbed.get("access_routes") or [])
    ]
    occupant = scrubbed.get("occupant")
    if occupant is not None and not isinstance(occupant, dict):
        raise RoleError("occupant must be an object or null")
    if isinstance(occupant, dict):
        src = occupant
        occupant = {
            "session_id": _require_str(
                src.get("session_id"), "occupant.session_id"
            ),
            "harness": str(src.get("harness") or "").strip() or "unknown",
            "equipped_at": str(src.get("equipped_at") or _utc_now()),
        }
        if src.get("account_pool"):
            # pool name only — never tokens
            occupant["account_pool"] = str(src["account_pool"]).strip()
        if src.get("seat"):
            # G2 seat name for the occupying coordinator — not the role_id
            occupant["seat"] = str(src["seat"]).strip()
        for prior_field in ("prior_session_id", "prior_harness", "prior_seat"):
            if src.get(prior_field):
                occupant[prior_field] = str(src[prior_field]).strip()

    role = {
        "schema": ROLE_SCHEMA,
        "role_id": _require_str(rid, "role_id"),
        "purpose": purpose,
        "knowledge": clean_knowledge,
        "obligations": obligations,
        "tools": tools,
        "access_routes": access_routes,
        "occupant": occupant,
        "credential_custodian": str(
            scrubbed.get("credential_custodian") or "existing_secure_stores"
        ).strip(),
        "created_at": str(scrubbed.get("created_at") or _utc_now()),
        # Reads retain source freshness; legacy records fall back to creation.
        "updated_at": str(
            scrubbed.get("updated_at") or scrubbed.get("created_at") or _utc_now()
        ),
        "transfer_count": int(scrubbed.get("transfer_count") or 0),
    }
    if scrubbed.get("label"):
        role["label"] = str(scrubbed["label"]).strip()
    if isinstance(scrubbed.get("last_released"), dict):
        role["last_released"] = deepcopy(scrubbed["last_released"])
    if scrubbed.get("synthetic") is True:
        role["synthetic"] = True
        role["synthetic_note"] = str(
            scrubbed.get("synthetic_note")
            or "SYNTHETIC fixture — not a live customer/obligation"
        )
    return role


def role_storage_key(role_id: str) -> str:
    """Return the filename stem used by the role registry."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", role_id)


def open_obligation_rows(
    roles: Iterable[dict[str, Any]], *, cash_only: bool = False
) -> list[dict[str, Any]]:
    """Project open obligations from normalized roles into sorted queue rows.

    Rows for roles that route `payment_capability` stamp
    `payment_capability: true` so mixed CRM + paid stores separate cash work.
    When tools resolve cash fields, cash rows also stamp `amount_usd` and
    `refund` (diagnostic
    commercial.diagnostic_usd+refund).
    When cash_only is True, keep only rows with payment_capability is True.
    This marker does not establish that payment has occurred.
    """
    rows: list[dict[str, Any]] = []
    for role in roles:
        cash = _role_has_payment_capability(role)
        for ob in role.get("obligations") or []:
            if str(ob.get("status") or "").strip() != "open":
                continue
            row: dict[str, Any] = {
                "role_id": role["role_id"],
                "purpose": role["purpose"],
                "obligation_id": ob["id"],
                "summary": ob["summary"],
                "next_action": ob["next_action"],
            }
            if role.get("label"):
                row["label"] = role["label"]
            if ob.get("evidence_pointer"):
                row["evidence_pointer"] = ob["evidence_pointer"]
            if role.get("synthetic") is True:
                row["synthetic"] = True
            if cash:
                row["payment_capability"] = True
                cash_fields = _role_cash_fields(role)
                if cash_fields is not None:
                    row["amount_usd"] = cash_fields["amount_usd"]
                    row["refund"] = cash_fields["refund"]
            rows.append(row)
    rows.sort(key=lambda r: (r["role_id"], r["obligation_id"]))
    if cash_only:
        rows = [r for r in rows if r.get("payment_capability") is True]
    return rows


def export_role_package(role: dict[str, Any]) -> dict[str, Any]:
    """Build a portable package from a normalized role without changing it."""
    package = deepcopy(role)
    # Occupant is runtime binding; export keeps last known next action but
    # clears the live session so the successor must equip/transfer explicitly.
    # Durable access_route session_id / last_run_id stay for G2 recover.
    package["occupant"] = None
    package["export_meta"] = {
        "exported_at": _utc_now(),
        "role_id_stable": True,
        "next_useful_actions": [
            o.get("next_action")
            for o in package.get("obligations") or []
            if o.get("status") == "open"
        ],
    }
    package = _scrub_secrets(package)
    # Stamp after scrub: the key name matches _SECRET_KEY_RE ("secret").
    package.setdefault("export_meta", {})["includes_secrets"] = False
    return package


class RoleStore:
    """On-disk role registry. role_id survives occupant transfer."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, role_id: str) -> Path:
        return self.root / f"{role_storage_key(role_id)}.json"

    def create(self, raw: dict[str, Any], *, role_id: str | None = None) -> dict[str, Any]:
        role = normalize_role(raw, role_id=role_id)
        path = self._path(role["role_id"])
        if path.exists():
            raise RoleError(f"role_id already exists: {role['role_id']}")
        self._write(role)
        return deepcopy(role)

    def get(self, role_id: str) -> dict[str, Any]:
        path = self._path(role_id)
        if not path.exists():
            raise RoleError(f"role not found: {role_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            role_id = data.get("role_id") or role_id
        return normalize_role(data, role_id=role_id)

    def list_ids(self) -> list[str]:
        return sorted(self.get(p.stem)["role_id"] for p in self.root.glob("*.json"))

    def list_open_obligations(self, *, cash_only: bool = False) -> list[dict[str, Any]]:
        """Open obligations across all roles — cash-work / fulfillment queue.

        Rows for roles that route `payment_capability` stamp
        `payment_capability: true` so mixed CRM + paid stores separate cash work.
        When tools resolve cash fields, cash rows also stamp `amount_usd` and
        `refund` (diagnostic
        commercial.diagnostic_usd+refund).
        When cash_only is True, keep only rows with payment_capability is True.
        This marker does not establish that payment has occurred.
        """
        return open_obligation_rows(
            (self.get(path.stem) for path in sorted(self.root.glob("*.json"))),
            cash_only=cash_only,
        )

    def equip(
        self,
        role_id: str,
        *,
        session_id: str,
        harness: str,
        account_pool: str | None = None,
        seat: str | None = None,
    ) -> dict[str, Any]:
        role = self.get(role_id)
        if role.get("occupant"):
            raise RoleError(
                f"role {role_id} already occupied by session "
                f"{role['occupant'].get('session_id')}; transfer or release first"
            )
        occupant: dict[str, Any] = {
            "session_id": _require_str(session_id, "session_id"),
            "harness": _require_str(harness, "harness"),
            "equipped_at": _utc_now(),
        }
        if account_pool:
            occupant["account_pool"] = account_pool.strip()
        if seat:
            occupant["seat"] = seat.strip()
        role["occupant"] = occupant
        role["updated_at"] = _utc_now()
        self._write(role)
        return deepcopy(role)

    def transfer(
        self,
        role_id: str,
        *,
        to_session_id: str,
        to_harness: str,
        from_session_id: str | None = None,
        account_pool: str | None = None,
        seat: str | None = None,
    ) -> dict[str, Any]:
        role = self.get(role_id)
        current = role.get("occupant")
        if not current:
            raise RoleError(f"role {role_id} has no occupant to transfer from")
        if from_session_id and current.get("session_id") != from_session_id:
            raise RoleError(
                f"occupant mismatch: expected {from_session_id}, "
                f"have {current.get('session_id')}"
            )
        if current.get("session_id") == to_session_id:
            raise RoleError("to_session_id must differ from current occupant")
        preserved_purpose = role["purpose"]
        preserved_obligations = deepcopy(role["obligations"])
        role["occupant"] = {
            "session_id": _require_str(to_session_id, "to_session_id"),
            "harness": _require_str(to_harness, "to_harness"),
            "equipped_at": _utc_now(),
            "prior_session_id": current.get("session_id"),
            "prior_harness": current.get("harness"),
        }
        if account_pool:
            role["occupant"]["account_pool"] = account_pool.strip()
        elif current.get("account_pool"):
            role["occupant"]["account_pool"] = current["account_pool"]
        if seat:
            role["occupant"]["seat"] = seat.strip()
        elif current.get("seat"):
            # Seat is occupant identity; successor may keep or replace explicitly.
            role["occupant"]["prior_seat"] = current["seat"]
        role["transfer_count"] = int(role.get("transfer_count") or 0) + 1
        role["updated_at"] = _utc_now()
        # Invariants: role_id, purpose, obligations/next_action survive.
        if role["purpose"] != preserved_purpose:
            raise RoleError("purpose mutated during transfer")
        if role["obligations"] != preserved_obligations:
            raise RoleError("obligations mutated during transfer")
        self._write(role)
        return deepcopy(role)

    def bind_access_route(
        self,
        role_id: str,
        *,
        route_name: str,
        session_id: str | None = None,
        last_run_id: str | None = None,
        pool_id: str | None = None,
    ) -> dict[str, Any]:
        """Stamp durable G2 recover fields onto a named access_route.

        Occupant seat stays on occupant — never copied onto the route here.
        Secrets are scrubbed. purpose / obligations / role_id are unchanged.
        """
        role = self.get(role_id)
        name = _require_str(route_name, "route_name")
        updates = {
            "session_id": session_id,
            "last_run_id": last_run_id,
            "pool_id": pool_id,
        }
        if not any(updates[f] for f in BINDABLE_ROUTE_FIELDS):
            raise RoleError(
                "bind_access_route needs at least one of "
                "session_id, last_run_id, pool_id"
            )
        preserved_purpose = role["purpose"]
        preserved_obligations = deepcopy(role["obligations"])
        found = False
        new_routes: list[dict[str, Any]] = []
        for route in role.get("access_routes") or []:
            item = deepcopy(route)
            if item.get("name") == name:
                found = True
                for field in BINDABLE_ROUTE_FIELDS:
                    value = updates[field]
                    if value:
                        item[field] = _require_str(value, field)
                item = _normalize_access_route(item)
            new_routes.append(item)
        if not found:
            raise RoleError(f"access_route not found: {name}")
        role["access_routes"] = new_routes
        role["updated_at"] = _utc_now()
        if role["purpose"] != preserved_purpose:
            raise RoleError("purpose mutated during bind_access_route")
        if role["obligations"] != preserved_obligations:
            raise RoleError("obligations mutated during bind_access_route")
        self._write(role)
        return deepcopy(role)

    def unbind_access_route(
        self,
        role_id: str,
        *,
        route_name: str,
        fields: tuple[str, ...] | list[str] | None = None,
    ) -> dict[str, Any]:
        """Clear stamped BINDABLE_ROUTE_FIELDS on a named access_route.

        Keeps the route shell (name/kind/urls). Does not touch occupant,
        purpose, or obligations. Default clears DEFAULT_UNBIND_FIELDS
        (session_id, last_run_id — the recover stamps), NOT pool_id.
        Optional fields= subset must be within BINDABLE_ROUTE_FIELDS
        (may include pool_id).
        """
        role = self.get(role_id)
        name = _require_str(route_name, "route_name")
        clear = list(fields) if fields else list(DEFAULT_UNBIND_FIELDS)
        for f in clear:
            if f not in BINDABLE_ROUTE_FIELDS:
                raise RoleError(f"unbind field not bindable: {f}")
        if not clear:
            raise RoleError("unbind_access_route needs at least one field")
        preserved_purpose = role["purpose"]
        preserved_obligations = deepcopy(role["obligations"])
        found = False
        new_routes: list[dict[str, Any]] = []
        for route in role.get("access_routes") or []:
            item = deepcopy(route)
            if item.get("name") == name:
                found = True
                for field in clear:
                    item.pop(field, None)
                item = _normalize_access_route(item)
            new_routes.append(item)
        if not found:
            raise RoleError(f"access_route not found: {name}")
        role["access_routes"] = new_routes
        role["updated_at"] = _utc_now()
        if role["purpose"] != preserved_purpose:
            raise RoleError("purpose mutated during unbind_access_route")
        if role["obligations"] != preserved_obligations:
            raise RoleError("obligations mutated during unbind_access_route")
        self._write(role)
        return deepcopy(role)

    def release(
        self,
        role_id: str,
        *,
        from_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Clear occupant so a later session can equip again.

        Preserves purpose, obligations, tools, and bound access_route fields.
        Does not delete the role. Optional from_session_id guards against a
        stale release from the wrong session.
        """
        role = self.get(role_id)
        current = role.get("occupant")
        if not current:
            raise RoleError(f"role {role_id} has no occupant to release")
        if from_session_id and current.get("session_id") != from_session_id:
            raise RoleError(
                f"occupant mismatch: expected {from_session_id}, "
                f"have {current.get('session_id')}"
            )
        preserved_purpose = role["purpose"]
        preserved_obligations = deepcopy(role["obligations"])
        preserved_routes = deepcopy(role.get("access_routes") or [])
        role["last_released"] = {
            "session_id": current.get("session_id"),
            "harness": current.get("harness"),
            "seat": current.get("seat"),
            "released_at": _utc_now(),
        }
        role["occupant"] = None
        role["updated_at"] = _utc_now()
        if role["purpose"] != preserved_purpose:
            raise RoleError("purpose mutated during release")
        if role["obligations"] != preserved_obligations:
            raise RoleError("obligations mutated during release")
        if role.get("access_routes") != preserved_routes:
            raise RoleError("access_routes mutated during release")
        self._write(role)
        return deepcopy(role)

    def advance_obligation(
        self,
        role_id: str,
        obligation_id: str,
        *,
        status: str | None = None,
        next_action: str | None = None,
        evidence_pointer: str | None = None,
    ) -> dict[str, Any]:
        """Update one obligation in place; other obligations and purpose stay.

        Roles describe responsibility — this never grants credentials.
        """
        role = self.get(role_id)
        oid = _require_str(obligation_id, "obligation_id")
        if not any([status, next_action, evidence_pointer]):
            raise RoleError(
                "advance_obligation needs at least one of "
                "status, next_action, evidence_pointer"
            )
        if status is not None:
            status_s = _require_str(status, "status").lower()
            if status_s not in OBLIGATION_STATUSES:
                raise RoleError(
                    f"status must be one of {sorted(OBLIGATION_STATUSES)}"
                )
            status = status_s
        preserved_purpose = role["purpose"]
        found = False
        new_obligations: list[dict[str, Any]] = []
        for item in role.get("obligations") or []:
            row = deepcopy(item)
            if row.get("id") == oid:
                found = True
                if status is not None:
                    row["status"] = status
                if next_action is not None:
                    row["next_action"] = _require_str(next_action, "next_action")
                if evidence_pointer is not None:
                    row["evidence_pointer"] = _require_str(
                        evidence_pointer, "evidence_pointer"
                    )
                row = _normalize_obligation(row)
            new_obligations.append(row)
        if not found:
            raise RoleError(f"obligation not found: {oid}")
        role["obligations"] = new_obligations
        role["updated_at"] = _utc_now()
        if role["purpose"] != preserved_purpose:
            raise RoleError("purpose mutated during advance_obligation")
        self._write(role)
        return deepcopy(role)

    def import_package(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Adopt an export_package into this store without reminting role_id.

        Occupant must be None (importer equips). export_meta is dropped.
        Fails if role_id already exists.
        """
        if not isinstance(raw, dict):
            raise RoleError("package must be an object")
        package = deepcopy(raw)
        package.pop("export_meta", None)
        package["occupant"] = None
        rid = _require_str(package.get("role_id"), "role_id")
        if self._path(rid).exists():
            raise RoleError(f"role_id already exists: {rid}; refuse remint")
        role = normalize_role(package, role_id=rid)
        role["occupant"] = None
        role["updated_at"] = _utc_now()
        self._write(role)
        return deepcopy(role)

    def inspect(self, role_id: str) -> dict[str, Any]:
        return self.get(role_id)

    def export_package(self, role_id: str) -> dict[str, Any]:
        """Portable package for a successor peer — no secrets, no remint of role_id."""
        return export_role_package(self.get(role_id))

    def _write(self, role: dict[str, Any]) -> None:
        path = self._path(role["role_id"])
        clean = _scrub_secrets(role)
        content = json.dumps(clean, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        created = False
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                created = True
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                mode = path.stat().st_mode
            except FileNotFoundError:
                pass
            else:
                temporary.chmod(mode & 0o7777)
            temporary.replace(path)
        finally:
            if created:
                temporary.unlink(missing_ok=True)

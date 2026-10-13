from __future__ import annotations

import hashlib
import hmac
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import pwd
except ImportError:  # pragma: no cover - non-POSIX fails closed in production
    pwd = None

from .engine import DealEconomicsError, canonical_json, compile_report, digest, now_utc, parse_strict_json

AUTHORITY_SCHEMA = "commons.service-deal-economics.authority/v1"
FLOOR_SCHEMA = "commons.service-deal-economics.authority-floor/v1"
KEY_SCHEMA = "commons.service-deal-economics.authority-key/v1"
CURRENT_SCHEMA = "commons.service-deal-economics.current-report/v2"
CURRENT_VERIFY_SCHEMA = "commons.service-deal-economics.authority-verification/v2"
READY = "READY_FOR_OWNER_QUOTE_REVIEW"
AUTHORITY_HOLD = "HOLD_INPUT_AUTHORITY_UNVERIFIED"
MAX_HOST_BYTES = 128 * 1024


class AuthorityError(DealEconomicsError):
    pass


def _fixed_host_root() -> Path:
    if os.name != "posix" or pwd is None:
        raise AuthorityError("fixed-host authority requires POSIX account semantics")
    try:
        home = pwd.getpwuid(os.getuid()).pw_dir
    except (KeyError, OSError) as exc:
        raise AuthorityError("cannot resolve fixed OS-account home") from exc
    return Path(home) / ".config" / "commons" / "service-deal-economics"


def _host_paths() -> tuple[Path, Path, Path]:
    root = _fixed_host_root()
    return root / "authority-key.json", root / "current-authority.json", root / "authority-floor.json"


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise AuthorityError(f"{label} must be lowercase SHA-256 hex")
    return value


def _generation(value: Any, label: str) -> int:
    if type(value) is not int or not 1 <= value <= 1_000_000_000:
        raise AuthorityError(f"{label} must be a positive bounded integer")
    return value


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not str:
        raise AuthorityError(f"{label} must be canonical UTC")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise AuthorityError(f"{label} must be canonical whole-second UTC") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise AuthorityError(f"{label} must be canonical whole-second UTC")
    return dt


def _utc_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise AuthorityError("trusted current time must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def authority_subject(packet: Any) -> dict[str, str]:
    if type(packet) is not dict or any(type(packet.get(k)) is not dict for k in ("policy", "deal", "capacity")):
        raise AuthorityError("packet must contain policy, deal, and capacity objects")
    deal_basis = dict(packet["deal"])
    if "target_price_cents" not in deal_basis:
        raise AuthorityError("deal.target_price_cents missing")
    deal_basis.pop("target_price_cents")
    return {
        "policy_sha256": digest(packet["policy"]),
        "scope_cost_sha256": digest(deal_basis),
        "capacity_sha256": digest(packet["capacity"]),
    }


def _no_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.parts[0])
    for part in absolute.parts[1:]:
        current /= part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode):
            raise AuthorityError("host trust path contains a symlink")


def _read_host(path: Path, *, private: bool) -> dict[str, Any]:
    _no_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError as exc:
        raise AuthorityError("host authority file missing") from exc
    except OSError as exc:
        raise AuthorityError("cannot open host authority file safely") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 2 <= before.st_size <= MAX_HOST_BYTES:
            raise AuthorityError("host authority file type/size invalid")
        if os.name == "posix" and (before.st_uid != os.getuid() or (private and stat.S_IMODE(before.st_mode) & 0o077)):
            raise AuthorityError("host authority owner/permissions invalid")
        data = bytearray()
        while len(data) <= MAX_HOST_BYTES:
            chunk = os.read(fd, min(65536, MAX_HOST_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_HOST_BYTES:
            raise AuthorityError("host authority file too large")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise AuthorityError("host authority file changed during read")
        try:
            obj = parse_strict_json(bytes(data).decode("utf-8"))
        except (UnicodeDecodeError, DealEconomicsError) as exc:
            raise AuthorityError("host authority JSON invalid") from exc
        if type(obj) is not dict:
            raise AuthorityError("host authority must be an object")
        return obj
    finally:
        os.close(fd)


def _key() -> bytes:
    key_path, _, _ = _host_paths()
    obj = _read_host(key_path, private=True)
    if set(obj) != {"schema", "key_hex"} or obj.get("schema") != KEY_SCHEMA:
        raise AuthorityError("host authority key schema mismatch")
    return bytes.fromhex(_sha(obj.get("key_hex"), "key_hex"))


def _signed_payload(obj: dict[str, Any], *, schema: str, required: set[str]) -> dict[str, Any]:
    if set(obj) != required | {"mac_sha256"} or obj.get("schema") != schema:
        raise AuthorityError("signed authority schema mismatch")
    _sha(obj["mac_sha256"], "mac_sha256")
    return {k: obj[k] for k in sorted(required)}


def _auth_registry(reg: dict[str, Any], key: bytes) -> None:
    required = {"schema", "generation", "issued_at", "expires_at", "policy_sha256", "scope_cost_sha256", "capacity_sha256"}
    payload = _signed_payload(reg, schema=AUTHORITY_SCHEMA, required=required)
    _generation(reg["generation"], "authority generation")
    issued, expires = _utc(reg["issued_at"], "issued_at"), _utc(reg["expires_at"], "expires_at")
    if expires <= issued:
        raise AuthorityError("authority expiry must follow issuance")
    for name in ("policy_sha256", "scope_cost_sha256", "capacity_sha256"):
        _sha(reg[name], name)
    expected = hmac.new(key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, reg["mac_sha256"]):
        raise AuthorityError("authority registry MAC mismatch")


def _auth_floor(floor: dict[str, Any], key: bytes) -> None:
    required = {"schema", "generation", "registry_sha256"}
    payload = _signed_payload(floor, schema=FLOOR_SCHEMA, required=required)
    _generation(floor["generation"], "authority floor generation")
    _sha(floor["registry_sha256"], "registry_sha256")
    expected = hmac.new(key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, floor["mac_sha256"]):
        raise AuthorityError("authority floor MAC mismatch")


def _load_current(key: bytes) -> tuple[dict[str, Any], str]:
    _, reg_path, floor_path = _host_paths()
    reg, floor = _read_host(reg_path, private=False), _read_host(floor_path, private=False)
    _auth_registry(reg, key)
    _auth_floor(floor, key)
    reg_sha = digest(reg)
    if floor["generation"] != reg["generation"] or floor["registry_sha256"] != reg_sha:
        raise AuthorityError("authority floor does not bind current registry")
    return reg, reg_sha


def _unauth() -> dict[str, Any]:
    return {"authenticated": False, "state": "HOST_AUTHORITY_UNAVAILABLE_OR_INVALID", "reasons": ["HOST_AUTHORITY_UNAVAILABLE_OR_INVALID"],
            "generation": None, "registry_sha256": None, "policy_sha256": None, "scope_cost_sha256": None, "capacity_sha256": None, "registry": None}


def _authority_status(packet: Any, as_of: datetime, *, registry: dict[str, Any] | None = None, registry_sha256: str | None = None) -> dict[str, Any]:
    try:
        key = _key()
        if registry is None:
            registry, current_sha = _load_current(key)
        else:
            _auth_registry(registry, key)
            current_sha = digest(registry)
            if registry_sha256 is not None and registry_sha256 != current_sha:
                raise AuthorityError("embedded authority registry digest mismatch")
        subject = authority_subject(packet)
        reasons: list[str] = []
        if _utc(registry["issued_at"], "issued_at") > as_of:
            reasons.append("AUTHORITY_NOT_YET_VALID")
        if as_of > _utc(registry["expires_at"], "expires_at"):
            reasons.append("AUTHORITY_EXPIRED")
        for name, value in subject.items():
            if registry[name] != value:
                reasons.append(f"AUTHORITY_{name.upper()}_MISMATCH")
        ok = not reasons
        return {"authenticated": ok, "state": "AUTHENTICATED_CURRENT_INPUT_BASIS" if ok else "AUTHORITY_SUBJECT_MISMATCH", "reasons": sorted(reasons),
                "generation": registry["generation"], "registry_sha256": current_sha, "policy_sha256": registry["policy_sha256"],
                "scope_cost_sha256": registry["scope_cost_sha256"], "capacity_sha256": registry["capacity_sha256"], "registry": registry}
    except (AuthorityError, DealEconomicsError, OSError, KeyError, TypeError, ValueError):
        return _unauth()


def _external() -> dict[str, bool]:
    return {k: False for k in ("buyer_contact", "quote_sent_or_committed", "buyer_acceptance", "capacity_reserved", "staffing_committed", "contract_signed", "payment_received", "cash_available", "revenue_booked_or_recognized")}


def _projection(candidate: dict[str, Any]) -> dict[str, Any]:
    return {"input_sha256": candidate["input_sha256"], "candidate_disposition": candidate["disposition"], "candidate_reasons": candidate["reasons"],
            "candidate_semantic_sha256": candidate["semantic_sha256"], "candidate_receipt_sha256": candidate["receipt_sha256"],
            "quote_valid_until": candidate["quote_valid_until"], "deal": candidate["deal"], "economics": candidate["economics"], "capacity": candidate["capacity"]}


def _assemble(candidate: dict[str, Any], evaluated: datetime, auth: dict[str, Any]) -> dict[str, Any]:
    reasons = sorted(set(list(candidate["reasons"]) + ([] if auth["authenticated"] else auth["reasons"])))
    report = {"schema": CURRENT_SCHEMA, "evaluated_at": _utc_text(evaluated),
              "state": candidate["disposition"] if auth["authenticated"] else AUTHORITY_HOLD, "reasons": reasons,
              "calculation": _projection(candidate), "input_authority": {k: auth[k] for k in ("authenticated", "state", "generation", "registry_sha256", "policy_sha256", "scope_cost_sha256", "capacity_sha256")},
              "authority_registry": auth["registry"], "external_authority": _external()}
    report["semantic_sha256"] = digest({k: v for k, v in report.items() if k != "authority_registry"})
    report["receipt_sha256"] = digest(report)
    return report


def _compile_current_at(packet: Any, as_of: datetime) -> dict[str, Any]:
    """Current-state helper for tests: time is injectable, authority registry is not."""
    as_of = as_of.astimezone(timezone.utc).replace(microsecond=0)
    candidate = compile_report(packet, _utc_text(as_of))
    return _assemble(candidate, as_of, _authority_status(packet, as_of))


def _replay_historical_at(packet: Any, as_of: datetime, registry: dict[str, Any], registry_sha256: str) -> dict[str, Any]:
    """Reconstruct a historical report from its embedded signed registry; never a current-state API."""
    candidate = compile_report(packet, _utc_text(as_of))
    auth = _authority_status(packet, as_of, registry=registry, registry_sha256=registry_sha256)
    return _assemble(candidate, as_of, auth)


def compile_current(packet: Any) -> dict[str, Any]:
    return _compile_current_at(packet, now_utc())


def _historical_valid(packet: Any, report: Any) -> bool:
    if type(report) is not dict or report.get("schema") != CURRENT_SCHEMA or report.get("receipt_sha256") != digest({k: v for k, v in report.items() if k != "receipt_sha256"}):
        return False
    try:
        evaluated = _utc(report["evaluated_at"], "evaluated_at")
        embedded = report.get("authority_registry")
        if embedded is None:
            expected = _assemble(compile_report(packet, _utc_text(evaluated)), evaluated, _unauth())
        else:
            expected = _replay_historical_at(packet, evaluated, embedded, report["input_authority"]["registry_sha256"])
        return canonical_json(expected) == canonical_json(report)
    except (AuthorityError, DealEconomicsError, OSError, KeyError, TypeError, ValueError):
        return False


def _verify_current_at(packet: Any, report: Any, as_of: datetime) -> dict[str, Any]:
    as_of = as_of.astimezone(timezone.utc).replace(microsecond=0)
    historical_ok = _historical_valid(packet, report)
    current = None
    if not historical_ok:
        state = "INVALID_HISTORICAL_RECEIPT"
    else:
        try:
            evaluated_at = _utc(report["evaluated_at"], "report.evaluated_at")
            quote_valid_until = _utc(
                report["calculation"]["quote_valid_until"],
                "report.calculation.quote_valid_until",
            )
        except (AuthorityError, KeyError, TypeError):
            historical_ok = False
            state = "INVALID_HISTORICAL_RECEIPT"
        else:
            if evaluated_at > as_of:
                state = "FUTURE_RECEIPT"
            else:
                current = _compile_current_at(packet, as_of)
                if not current["input_authority"]["authenticated"]:
                    state = AUTHORITY_HOLD
                elif any(report["input_authority"].get(k) != current["input_authority"].get(k) for k in ("registry_sha256", "generation")):
                    state = "STALE_OR_AUTHORITY_SUPERSEDED"
                elif as_of > quote_valid_until:
                    state = "STALE_OR_DRIFTED"
                elif report["calculation"].get("candidate_semantic_sha256") != current["calculation"].get("candidate_semantic_sha256") or report.get("state") != current["state"]:
                    state = "STALE_OR_DRIFTED"
                else:
                    state = "CURRENT_VERIFIED"
    result = {"schema": CURRENT_VERIFY_SCHEMA, "verified_at": _utc_text(as_of), "historical_receipt_valid": historical_ok, "state": state,
              "report_receipt_sha256": report.get("receipt_sha256") if type(report) is dict else None,
              "current_report_receipt_sha256": None if current is None else current["receipt_sha256"],
              "current_authority_registry_sha256": None if current is None else current["input_authority"]["registry_sha256"], "external_authority": _external()}
    result["receipt_sha256"] = digest(result)
    return result


def render_current_markdown(report: Any) -> str:
    if type(report) is not dict or report.get("schema") != CURRENT_SCHEMA:
        raise AuthorityError("current report schema mismatch")
    calc, auth = report["calculation"], report["input_authority"]
    econ, cap, deal = calc["economics"], calc["capacity"], calc["deal"]
    reasons = ", ".join(report["reasons"]) if report["reasons"] else "none"
    return "\n".join(["# Service Deal Economics Desk — current authority view", "", f"- Current state: **{report['state']}**",
        f"- Candidate arithmetic disposition: `{calc['candidate_disposition']}` (not authority by itself)", f"- Input authority authenticated: `{str(auth['authenticated']).lower()}`",
        f"- Authority generation: `{auth['generation']}`", f"- Deal: `{deal['deal_id']}` / scope `{deal['scope_id']}` rev {deal['scope_revision']}",
        f"- Target price: {deal['target_price_cents']} {deal['currency']} cents", f"- Minimum price: {econ['minimum_price_cents']} cents",
        f"- Loaded delivery cost: {econ['loaded_delivery_cost_cents']} cents", f"- Capacity: {cap['proposed_demand_minutes']} proposed / {cap['available_minutes']} available minutes",
        f"- Reasons: {reasons}", "", "## Authority ceiling", "",
        "READY requires an independently retained, MAC-authenticated fixed-host authority registry binding the exact owner policy, scope/cost basis, and capacity snapshot. Candidate JSON hashes/timestamps cannot mint it. No quote, reservation, staffing commitment, acceptance, payment, cash, or revenue authority is created.",
        "", f"Receipt: `{report['receipt_sha256']}`", ""])

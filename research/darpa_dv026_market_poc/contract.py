from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


SCHEMA = "darpa-dv026-market-poc/v1"
RESULT_SCHEMA = "darpa-dv026-market-poc-result/v1"
RECEIPT_SCHEMA = "darpa-dv026-market-poc-receipt/v1"
MECHANISMS = ("CONTINUOUS_DOUBLE_AUCTION", "UNIFORM_PRICE_CALL_AUCTION")
STATUS_READY = "PHASE_I_TECHNICAL_POC_READY_FOR_OWNER_REVIEW"
STATUS_HOLD = "HOLD_TECHNICAL_POC"
MAX_PRICE = 10**9
MAX_QTY = 10**6
MAX_STR = 96


class ContractError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant: {value}")


def _object_pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError("input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _expect_keys(obj: Any, required: set[str], optional: set[str] = frozenset(), *, where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ContractError(f"{where} must be an object")
    got = set(obj)
    missing = required - got
    extra = got - required - optional
    if missing:
        raise ContractError(f"{where} missing keys: {sorted(missing)}")
    if extra:
        raise ContractError(f"{where} unknown keys: {sorted(extra)}")
    return obj


def _ident(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STR:
        raise ContractError(f"{where} must be a non-empty bounded string")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in value):
        raise ContractError(f"{where} must use printable non-space ASCII")
    if value[0] in ".-" or value[-1] in ".-":
        raise ContractError(f"{where} has invalid edge punctuation")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:.@/-")
    if any(ch not in allowed for ch in value):
        raise ContractError(f"{where} contains unsupported characters")
    return value


def _bounded_int(value: Any, *, where: str, lo: int = 0, hi: int = MAX_PRICE) -> int:
    if not _is_int(value) or value < lo or value > hi:
        raise ContractError(f"{where} must be integer in [{lo}, {hi}]")
    return value


def _sha(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise ContractError(f"{where} must be lowercase SHA-256")
    if any(ch not in "0123456789abcdef" for ch in value):
        raise ContractError(f"{where} must be lowercase SHA-256")
    return value


def _ratio(numerator: int, denominator: int) -> dict[str, int | None]:
    if denominator <= 0:
        return {"numerator": numerator, "denominator": denominator, "basis_points": None}
    bps = (numerator * 10000) // denominator
    return {"numerator": numerator, "denominator": denominator, "basis_points": bps}


@dataclass(frozen=True)
class Trader:
    trader_id: str
    side: str
    private_value: int
    quantity: int
    action_step: int
    strategy: str
    shade: int


@dataclass(frozen=True)
class Order:
    order_id: str
    trader_id: str
    side: str
    price: int
    quantity: int
    action_step: int
    observation_sha256: str
    action_sha256: str


@dataclass(frozen=True)
class Fill:
    fill_id: str
    buyer_id: str
    seller_id: str
    quantity: int
    price: int
    buyer_private_value: int
    seller_private_cost: int

    @property
    def surplus(self) -> int:
        return (self.buyer_private_value - self.seller_private_cost) * self.quantity


def validate_scenario(raw: Any) -> dict[str, Any]:
    s = _expect_keys(
        raw,
        {"schema", "scenario_id", "asset_id", "reference_price", "traders", "news", "panel", "benchmark"},
        where="scenario",
    )
    if s["schema"] != SCHEMA:
        raise ContractError("unsupported scenario schema")
    _ident(s["scenario_id"], where="scenario_id")
    _ident(s["asset_id"], where="asset_id")
    _bounded_int(s["reference_price"], where="reference_price", lo=1)
    if not isinstance(s["traders"], list) or not (2 <= len(s["traders"]) <= 256):
        raise ContractError("traders must contain 2..256 rows")
    traders: list[dict[str, Any]] = []
    seen_trader: set[str] = set()
    seen_step: set[int] = set()
    for i, row in enumerate(s["traders"]):
        t = _expect_keys(
            row,
            {"trader_id", "side", "private_value", "quantity", "action_step", "strategy", "shade"},
            where=f"traders[{i}]",
        )
        tid = _ident(t["trader_id"], where=f"traders[{i}].trader_id")
        if tid in seen_trader:
            raise ContractError(f"duplicate trader_id: {tid}")
        seen_trader.add(tid)
        if t["side"] not in ("BUY", "SELL"):
            raise ContractError("trader side must be BUY or SELL")
        _bounded_int(t["private_value"], where=f"traders[{i}].private_value", lo=1)
        _bounded_int(t["quantity"], where=f"traders[{i}].quantity", lo=1, hi=MAX_QTY)
        step = _bounded_int(t["action_step"], where=f"traders[{i}].action_step", lo=1, hi=10**6)
        if step in seen_step:
            raise ContractError("action_step must be unique across traders")
        seen_step.add(step)
        if t["strategy"] not in ("TRUTHFUL", "NEWS_FOLLOWER", "SHADED"):
            raise ContractError("unsupported synthetic strategy")
        _bounded_int(t["shade"], where=f"traders[{i}].shade", lo=0)
        traders.append(t)
    if not any(t["side"] == "BUY" for t in traders) or not any(t["side"] == "SELL" for t in traders):
        raise ContractError("scenario requires BUY and SELL traders")

    if not isinstance(s["news"], list) or len(s["news"]) > 128:
        raise ContractError("news must be bounded list")
    seen_news: set[str] = set()
    seen_news_step: set[int] = set()
    for i, row in enumerate(s["news"]):
        n = _expect_keys(row, {"news_id", "step", "delta"}, where=f"news[{i}]")
        nid = _ident(n["news_id"], where=f"news[{i}].news_id")
        if nid in seen_news:
            raise ContractError(f"duplicate news_id: {nid}")
        seen_news.add(nid)
        step = _bounded_int(n["step"], where=f"news[{i}].step", lo=0, hi=10**6)
        if step in seen_news_step:
            raise ContractError("news step must be unique")
        seen_news_step.add(step)
        if not _is_int(n["delta"]) or abs(n["delta"]) > MAX_PRICE:
            raise ContractError("news delta must be bounded integer")

    panel = _expect_keys(s["panel"], {"external_execution", "slots"}, where="panel")
    if panel["external_execution"] is not False:
        raise ContractError("checked-in POC panel must not claim external execution")
    if not isinstance(panel["slots"], list) or len(panel["slots"]) != 10:
        raise ContractError("panel must describe exactly 10 logical model slots")
    seen_slot: set[str] = set()
    seen_model: set[tuple[str, str]] = set()
    for i, row in enumerate(panel["slots"]):
        p = _expect_keys(row, {"slot_id", "provider", "model", "adapter"}, where=f"panel.slots[{i}]")
        sid = _ident(p["slot_id"], where=f"panel.slots[{i}].slot_id")
        provider = _ident(p["provider"], where=f"panel.slots[{i}].provider")
        model = _ident(p["model"], where=f"panel.slots[{i}].model")
        _ident(p["adapter"], where=f"panel.slots[{i}].adapter")
        if sid in seen_slot:
            raise ContractError("duplicate panel slot")
        if (provider, model) in seen_model:
            raise ContractError("panel provider/model identities must be unique")
        seen_slot.add(sid)
        seen_model.add((provider, model))

    benchmark = _expect_keys(s["benchmark"], {"kind", "benchmark_id", "source_sha256", "human_subject_collection"}, where="benchmark")
    if benchmark["kind"] not in ("SYNTHETIC", "PUBLIC_PREEXISTING"):
        raise ContractError("benchmark kind must be SYNTHETIC or PUBLIC_PREEXISTING")
    _ident(benchmark["benchmark_id"], where="benchmark.benchmark_id")
    _sha(benchmark["source_sha256"], where="benchmark.source_sha256")
    if benchmark["human_subject_collection"] is not False:
        raise ContractError("new human-subject collection is outside this POC")

    # Normalize list order where order is not semantic so source serialization order cannot change receipts.
    normalized = {
        **s,
        "traders": sorted(s["traders"], key=lambda row: (row["action_step"], row["trader_id"])),
        "news": sorted(s["news"], key=lambda row: (row["step"], row["news_id"])),
        "panel": {
            **s["panel"],
            "slots": sorted(s["panel"]["slots"], key=lambda row: row["slot_id"]),
        },
    }
    # Canonical clone ensures callers cannot mutate the graph after validation.
    return json.loads(canonical_bytes(normalized))



def validate_blackbox_action(raw: Any, trader: Trader, observation_sha256: str, mechanism: str) -> Order:
    if mechanism not in MECHANISMS:
        raise ContractError("unsupported market mechanism")
    _sha(observation_sha256, where="expected observation_sha256")
    a = _expect_keys(
        raw,
        {"schema", "order_id", "trader_id", "side", "price", "quantity", "action_step", "observation_sha256"},
        where="blackbox action",
    )
    if a["schema"] != "darpa-dv026-blackbox-action/v1":
        raise ContractError("unsupported blackbox action schema")
    order_id = _ident(a["order_id"], where="blackbox action.order_id")
    if not order_id.startswith(f"ord:{mechanism}:"):
        raise ContractError("order_id not bound to mechanism")
    if a["trader_id"] != trader.trader_id or a["side"] != trader.side:
        raise ContractError("blackbox action trader/side transplant")
    price = _bounded_int(a["price"], where="blackbox action.price", lo=1)
    quantity = _bounded_int(a["quantity"], where="blackbox action.quantity", lo=1, hi=MAX_QTY)
    if quantity > trader.quantity:
        raise ContractError("blackbox action exceeds trader quantity capacity")
    if a["action_step"] != trader.action_step:
        raise ContractError("blackbox action step is stale/transplanted")
    _sha(a["observation_sha256"], where="blackbox action.observation_sha256")
    if a["observation_sha256"] != observation_sha256:
        raise ContractError("blackbox action observation digest mismatch")
    envelope = {
        "schema": a["schema"],
        "order_id": order_id,
        "trader_id": trader.trader_id,
        "side": trader.side,
        "price": price,
        "quantity": quantity,
        "action_step": trader.action_step,
        "observation_sha256": observation_sha256,
    }
    return Order(
        order_id=order_id,
        trader_id=trader.trader_id,
        side=trader.side,
        price=price,
        quantity=quantity,
        action_step=trader.action_step,
        observation_sha256=observation_sha256,
        action_sha256=sha256_value(envelope),
    )



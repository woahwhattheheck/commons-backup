#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose executable-market-prefix custody after the current LOOM/H3 source stack.

This is the current-native successor to scheduler_action_prefix.py. It does not
activate production. It consumes authenticated source-only postimages and
repairs every current accounting consumer that can otherwise treat engine-capped
market suffix rows as executed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re

SCHEDULER_INPUTS = {
    "b29d1e9887f517506c5b3d858baa9bda5848e73f": "loom4-spindle",
}
FROZEN_INPUTS = {
    "4a5d3d5f4bed04acf73c7339e41fed56badf34c9": "loom4-livepath",
    "712f7334288951bdc5b8dd2a1aa1d7f985cd50dc": "loom4-livepath+h3s420",
}
LEGACY_SCHEDULER_INPUT = "a483b24dd72b580d7d8811636b54d2d44f391575"
LEGACY_SCHEDULER_OUTPUT = "742a200e9a72e303ad18c51c104895013a7f3a4b"

HELPER = (
    "def _engine_market_prefix(action, config):\n"
    "    # Official interpreter: normalize only list-valued market queues, then\n"
    "    # execute q[:max(1, maxMarketOrdersPerTurn)] without compaction.\n"
    "    market=action.get('market',[]) if isinstance(action,dict) else []\n"
    "    q=list(market) if isinstance(market,list) else []\n"
    "    return q[:max(1,int(config.get('maxMarketOrdersPerTurn',10)))]\n\n\n"
)
FORECAST_OLD = """            orders=base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
            for {name} in orders:
"""
FORECAST_NEW = """            market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)
            orders=_engine_market_prefix(market_action,config)
            for {name} in orders:
"""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            return candidate.resolve()
    raise ValueError("repository root unavailable; refuse materialization")


def _validate_external_target(path: Path, repo_root: Path, *, fresh: bool) -> Path:
    """Bind a publication target outside the checkout and reject symlink aliases."""
    target = _lexical(path)
    root = _lexical(repo_root)
    if _inside(target, root):
        raise ValueError(f"publication target is inside repository: {target}")
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink():
            raise ValueError(f"publication target has symlink ancestry: {ancestor}")
    resolved_root = root.resolve()
    resolved_target = target.resolve(strict=False)
    if _inside(resolved_target, resolved_root):
        raise ValueError(f"publication target resolves inside repository: {target}")
    if fresh and (target.exists() or target.is_symlink()):
        raise ValueError(f"publication target must be fresh: {target}")
    return target


def _validate_publish_layout(
    output: Path,
    receipt: Path | None,
    repo_root: Path,
    inputs: tuple[Path, ...],
) -> tuple[Path, Path | None]:
    output = _validate_external_target(output, repo_root, fresh=True)
    if not output.parent.is_dir():
        raise ValueError("output parent must already exist")
    receipt_out = None
    if receipt is not None:
        receipt_out = _validate_external_target(receipt, repo_root, fresh=True)
        if not receipt_out.parent.is_dir():
            raise ValueError("receipt parent must already exist")
        if _inside(receipt_out, output):
            raise ValueError("explicit receipt may not live inside output tree")
        receipt_resolved = receipt_out.resolve(strict=False)
        for source in inputs:
            source_lexical = _lexical(source)
            source_resolved = source_lexical.resolve(strict=False)
            if receipt_out == source_lexical or receipt_resolved == source_resolved:
                raise ValueError("receipt may not alias an input source")
    return output, receipt_out


def _publish_fresh(path: Path, data: bytes, repo_root: Path) -> None:
    """Publish one fresh external file without ever replacing an existing target."""
    target = _validate_external_target(path, repo_root, fresh=True)
    parent = target.parent
    if not parent.is_dir():
        raise ValueError("publication parent must already exist")
    _validate_external_target(parent, repo_root, fresh=False)
    sidecar = target.with_name(f".{target.name}.prefix.tmp")
    _validate_external_target(sidecar, repo_root, fresh=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(sidecar, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Recheck immediately before publication. hard-link creation is
        # exclusive: a raced final target is rejected rather than replaced.
        _validate_external_target(target, repo_root, fresh=True)
        os.link(sidecar, target, follow_symlinks=False)
        if target.read_bytes() != data:
            target.unlink(missing_ok=True)
            raise ValueError(f"publication readback mismatch: {target}")
    finally:
        if sidecar.exists() or sidecar.is_symlink():
            sidecar.unlink()


def _once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one occurrence, got {count}")
    return text.replace(old, new, 1)


def _span(source: str, name: str, *, class_name: str | None = None) -> tuple[int, int]:
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    body = ast.parse(source).body
    if class_name is None:
        nodes = [n for n in body if isinstance(n, ast.FunctionDef) and n.name == name]
    else:
        classes = [n for n in body if isinstance(n, ast.ClassDef) and n.name == class_name]
        if len(classes) != 1:
            raise ValueError(f"{class_name}: missing or ambiguous")
        nodes = [n for n in classes[0].body
                 if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1 or nodes[0].decorator_list:
        label = f"{class_name}.{name}" if class_name else name
        raise ValueError(f"{label}: missing, duplicate, or decorated")
    node = nodes[0]
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def _patch_span(source: str, name: str, patch, *, class_name: str | None = None) -> str:
    start, end = _span(source, name, class_name=class_name)
    old = source[start:end]
    new = patch(old)
    if old == new:
        raise ValueError(f"{class_name + '.' if class_name else ''}{name}: no change")
    return source[:start] + new + source[end:]


def _rewrite_scheduler(source: str) -> str:
    """Port the original six-consumer repair without its obsolete whole-file pin."""
    if "def _engine_market_prefix(" in source:
        raise ValueError("scheduler prefix helper already present or partially applied")
    text = _once(source, "\n\nclass SellScheduler:\n",
                 "\n\n" + HELPER + "class SellScheduler:\n", "shared prefix helper")
    for name in ("order", "o"):
        text = _once(text, FORECAST_OLD.format(name=name),
                     FORECAST_NEW.format(name=name), f"forecast {name}")
    text = _once(text,
                 "        for o in base['market']:\n",
                 "        for o in _engine_market_prefix(base,config):\n",
                 "current baseline quantities")
    text = _once(text,
                 "                for order in route[t].get('market',[]) if t<len(route) else []:\n",
                 "                for order in _engine_market_prefix(route[t] if t<len(route) else parent.PASS,config):\n",
                 "future reference quantities")
    text = _once(
        text,
        "                    orders=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n"
        "                    if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):\n",
        "                    market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)\n"
        "                    orders=_engine_market_prefix(market_action,config)\n"
        "                    if len(orders)>=max(1,int(config.get('maxMarketOrdersPerTurn',10))):\n",
        "executable offered capacity")
    text = _once(
        text,
        "        for raw in out['market']:\n            o=list(raw)\n",
        "        max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))\n"
        "        for index,raw in enumerate(out['market']):\n"
        "            # The engine never parses capped suffix rows. Preserve them\n"
        "            # verbatim; they cannot consume executable stock or plans.\n"
        "            if index>=max_orders:\n"
        "                market.append(raw)\n"
        "                continue\n"
        "            o=list(raw)\n",
        "suffix preservation")
    text = _once(
        text,
        "            if q>0 and len(market)<int(config.get('maxMarketOrdersPerTurn',10)):\n",
        "            if q>0 and len(market)<max_orders:\n",
        "append cap clamp")
    text = _once(
        text,
        "            sold=sum(o[2] for o in out['market'] if o and o[0]=='SELL' and o[1]==item)\n",
        "            sold=sum(o[2] for o in _engine_market_prefix(out,config) if o and o[0]=='SELL' and o[1]==item)\n",
        "pending and planned retirement")
    tree = ast.parse(text)
    helper = [n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "_engine_market_prefix"]
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_engine_market_prefix"]
    if len(helper) != 1 or len(calls) != 6:
        raise ValueError("scheduler: expected one helper and six consumers")
    compile(text, "<scheduler-prefix-current>", "exec")
    return text


def _replace_regex_once(text: str, pattern: str, repl, label: str) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"{label}: expected one regex occurrence, got {count}")
    return out


def _patch_materialize(part: str) -> str:
    part = _once(part,
                 "    market=[];remaining=dict(current);available=dict(shed)\n",
                 "    market=[];remaining=dict(current);available=dict(shed)\n"
                 "    max_orders=max(1,int(max_orders))\n",
                 "materialize max orders")
    part = _once(part,
                 "    for raw in orders:\n        o=list(raw)\n",
                 "    for index,raw in enumerate(orders):\n"
                 "        if index>=max_orders:\n"
                 "            market.append(raw)\n"
                 "            continue\n"
                 "        o=list(raw)\n",
                 "materialize raw suffix")
    part = _once(part, "len(market)<int(max_orders)", "len(market)<max_orders",
                 "materialize append clamp")
    return part


def _patch_funding_trace(part: str) -> str:
    return _once(part,
                 "    max_orders = int(config.get('maxMarketOrdersPerTurn', 10))\n",
                 "    max_orders = max(1, int(config.get('maxMarketOrdersPerTurn', 10)))\n",
                 "funding trace cap")


def _patch_fund_same_turn(part: str) -> str:
    part = _once(part,
                 "    original=copy.deepcopy(orders)\n    if not original:return original,None\n",
                 "    original=copy.deepcopy(orders)\n    if not original:return original,None\n"
                 "    max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))\n",
                 "funding prefix cap init")
    part = _once(part, "rival_quantity,len(original)-1)",
                 "rival_quantity,min(len(original),max_orders)-1)",
                 "funding baseline stop")
    part = _once(part,
                 "    source_limit=barrier if barrier is not None else len(original)\n",
                 "    source_limit=min(barrier if barrier is not None else len(original),max_orders)\n",
                 "funding source cap")
    return part


def _patch_joint_resource(part: str) -> str:
    part = _once(
        part,
        "    now=int(obs['step']);size=len(farm['tiles']);cap=int(config.get('shedCapacity',100))\n",
        "    now=int(obs['step']);size=len(farm['tiles']);cap=int(config.get('shedCapacity',100))\n"
        "    max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))\n",
        "joint resource cap init")
    part = _once(part, "        for order in orders_at(t):\n",
                 "        for order in list(orders_at(t))[:max_orders]:\n",
                 "joint resource executable rows")
    return part


def _patch_joint_queue(part: str) -> str:
    part = _once(part,
                 "    committed={p:list(rows) for p,rows in planned.items()}\n",
                 "    max_orders=max(1,int(max_orders))\n"
                 "    committed={p:list(rows) for p,rows in planned.items()}\n",
                 "joint queue cap init")
    part = _once(part, "        raw=sale_quantities(orders_at(t))\n",
                 "        raw=sale_quantities(list(orders_at(t))[:max_orders])\n",
                 "joint queue raw prefix")
    part = _once(part, "        actual=sale_quantities(market)\n",
                 "        actual=sale_quantities(market[:max_orders])\n",
                 "joint queue actual prefix")
    part = _once(
        part,
        "        if len(market)>max_orders or any(actual.get(p,0)!=q for p,q in wanted.items() if p in targets):return None\n",
        "        if any(actual.get(p,0)!=q for p,q in wanted.items() if p in targets):return None\n",
        "joint queue raw suffix length")
    return part


def _patch_horizon(part: str) -> str:
    part = _once(part,
                 "    max_orders=int(config.get('maxMarketOrdersPerTurn',10))\n",
                 "    max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))\n",
                 "horizon cap clamp")
    part = _once(part,
                 "            orders=route[date].get('market',[]) if date<len(route) else []\n"
                 "            has_slot=len(orders)<max_orders\n",
                 "            orders=route[date].get('market',[]) if date<len(route) else []\n"
                 "            prefix=(orders if isinstance(orders,list) else [])[:max_orders]\n"
                 "            has_slot=len(prefix)<max_orders\n",
                 "horizon prefix")
    part = _once(part, "                for o in orders)\n",
                 "                for o in prefix)\n", "horizon item slot")
    return part


def _patch_represented_market(part: str) -> str:
    part = _once(part,
                 "def apply_represented_market(farm, private, orders, size):\n",
                 "def apply_represented_market(farm, private, orders, size, max_orders):\n",
                 "represented signature")
    part = _once(part, "    for order in orders or ():\n",
                 "    queue=orders if isinstance(orders,list) else []\n"
                 "    for order in queue[:max(1,int(max_orders))]:\n",
                 "represented prefix")
    return part


def _patch_represented_event(part: str) -> str:
    part = _once(part,
                 "    apply_represented_market(f,p,current_market,size)\n",
                 "    apply_represented_market(f,p,current_market,size,"
                 "config.get('maxMarketOrdersPerTurn',10))\n",
                 "represented current market")
    part = _once(part,
                 "        apply_represented_market(f,p,action.get('market',[]),size)\n",
                 "        apply_represented_market(f,p,action.get('market',[]),size,"
                 "config.get('maxMarketOrdersPerTurn',10))\n",
                 "represented future market")
    return part


def _patch_transform(part: str) -> str:
    # H3/S420 indents the optimizer block by four spaces, so all post-budget
    # replacements capture indentation instead of assuming the native column.
    part = _replace_regex_once(
        part,
        r"^([ \t]*)for o in base\['market'\]:$",
        lambda m: m.group(1) + "for o in scheduling._engine_market_prefix(base,config):",
        "frozen baseline quantities")
    part = _replace_regex_once(
        part,
        r"^([ \t]*)for order in route\[t\]\.get\('market',\[\]\) if t<len\(route\) else \[\]:$",
        lambda m: m.group(1) + "for order in scheduling._engine_market_prefix("
                              "route[t] if t<len(route) else parent.PASS,config):",
        "frozen future reference")
    pattern = (
        r"^([ \t]*)orders=base\['market'\] if t==now else route\[t\]\.get\('market',\[\]\) "
        r"if t<len\(route\) else \[\]\n"
        r"\1if len\(orders\)>=int\(config\.get\('maxMarketOrdersPerTurn',10\)\):$"
    )
    def capacity(m):
        i = m.group(1)
        return (i + "market_action=base if t==now else "
                "(route[t] if t<len(route) else parent.PASS)\n"
                + i + "orders=scheduling._engine_market_prefix(market_action,config)\n"
                + i + "if len(orders)>=max(1,int(config.get('maxMarketOrdersPerTurn',10))):")
    part = _replace_regex_once(part, pattern, capacity, "frozen offered capacity")
    part = _replace_regex_once(
        part,
        r"^([ \t]*)sold=sum\(o\[2\] for o in out\['market'\] if o and o\[0\]=='SELL' and o\[1\]==item\)$",
        lambda m: (m.group(1) +
                   "sold=sum(o[2] for o in scheduling._engine_market_prefix(out,config) "
                   "if o and o[0]=='SELL' and o[1]==item)"),
        "frozen pending retirement")
    return part


def _rewrite_frozen(source: str) -> str:
    if "scheduling._engine_market_prefix" in source:
        raise ValueError("frozen prefix repair already present or partly applied")
    text = source
    text = _patch_span(text, "materialize_sales", _patch_materialize)
    text = _patch_span(text, "_funding_trace", _patch_funding_trace)
    text = _patch_span(text, "fund_same_turn_acquisition", _patch_fund_same_turn)
    text = _patch_span(text, "joint_resource_bound", _patch_joint_resource)
    text = _patch_span(text, "joint_queue_ledger", _patch_joint_queue)
    text = _patch_span(text, "event_aware_horizon", _patch_horizon)
    text = _patch_span(text, "apply_represented_market", _patch_represented_market)
    text = _patch_span(text, "represented_shed_event", _patch_represented_event)
    text = _patch_span(text, "transform", _patch_transform, class_name="FrozenSelected")
    if text.count("scheduling._engine_market_prefix") != 4:
        raise ValueError("frozen: expected four scheduler-prefix consumers")
    compile(text, "<frozen-prefix-current>", "exec")
    return text


def compose_pair(scheduler: bytes, frozen: bytes) -> tuple[bytes, bytes, dict]:
    scheduler_git = git_blob(scheduler)
    frozen_git = git_blob(frozen)
    if scheduler_git not in SCHEDULER_INPUTS:
        raise ValueError("scheduler.py is not the authenticated post-SPINDLE preimage")
    if frozen_git not in FROZEN_INPUTS:
        raise ValueError("frozen_selected.py is not the authenticated LIVEPATH/H3 preimage")
    scheduler_out = _rewrite_scheduler(scheduler.decode("utf-8")).encode("utf-8")
    frozen_out = _rewrite_frozen(frozen.decode("utf-8")).encode("utf-8")
    receipt = {
        "schema": "titan-v4-scheduler-prefix-current/v1",
        "release_authorized": False,
        "scheduler": {
            "profile": SCHEDULER_INPUTS[scheduler_git],
            "before_git_blob": scheduler_git,
            "after_git_blob": git_blob(scheduler_out),
            "after_sha256": hashlib.sha256(scheduler_out).hexdigest(),
        },
        "frozen_selected": {
            "profile": FROZEN_INPUTS[frozen_git],
            "before_git_blob": frozen_git,
            "after_git_blob": git_blob(frozen_out),
            "after_sha256": hashlib.sha256(frozen_out).hexdigest(),
        },
        "production_activation": False,
        "graph_registration": False,
    }
    return scheduler_out, frozen_out, receipt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scheduler", required=True, type=Path)
    p.add_argument("--frozen", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--receipt", type=Path)
    args = p.parse_args()
    try:
        repo_root = _repo_root()
        output, receipt_path = _validate_publish_layout(
            args.output, args.receipt, repo_root, (args.scheduler, args.frozen)
        )
    except ValueError as exc:
        p.error(str(exc))
    sb = args.scheduler.read_bytes()
    fb = args.frozen.read_bytes()
    so, fo, receipt = compose_pair(sb, fb)
    output.mkdir(exist_ok=False)
    try:
        _validate_external_target(output, repo_root, fresh=False)
        _publish_fresh(output / "scheduler.py", so, repo_root)
        _publish_fresh(output / "frozen_selected.py", fo, repo_root)
        receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if receipt_path is not None:
            _publish_fresh(receipt_path, receipt_bytes, repo_root)
        else:
            _publish_fresh(output / "CURRENT-PREFIX.json", receipt_bytes, repo_root)
    except ValueError as exc:
        p.error(str(exc))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

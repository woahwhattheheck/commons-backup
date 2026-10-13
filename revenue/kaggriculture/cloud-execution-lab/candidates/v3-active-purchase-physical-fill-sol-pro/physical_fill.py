# SPDX-License-Identifier: Apache-2.0
"""Order-aware repair for TITAN's active market-purchase capacity projection.

The official interpreter commits valid BUY_PRODUCT and BUY_ANIMAL orders one
unit at a time and stops as soon as the real shed reaches ``shedCapacity``.
The selected seller's inherited ``receipt_profile`` instead adds every requested
unit to its oversized planning shed.  That is intentionally conservative for
unit-stage deposits, but it invents market-purchase units the interpreter cannot
commit and can force an unnecessary early SELL.

This patch changes only valid purchase rows inside the official executable
market prefix.  Suffix-row behavior is retained for orthogonality with the
separate market-prefix experiment.  It also preserves the predecessor whenever
a later represented PICKUP/SELL could consume a clipped purchase; those cases
need a fuller item-flow model rather than an unsafe scalar shortcut.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

EXPECTED_SCHEDULER_GIT_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
EXPECTED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXPECTED_FROZEN_SELECTED_GIT_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"

START = b"    def receipt_profile(self, obs, base, farm, private, end, item, config):\n"
END = b"\n    def act(self, obs, config=None):\n"

NEW_METHOD = b'''    def receipt_profile(self, obs, base, farm, private, end, item, config):
        """Capacity callback with physical active-prefix purchase upper bounds.

        Unit-stage arrivals retain the predecessor's oversized projection so
        overflow remains visible before market. Valid BUY_PRODUCT/BUY_ANIMAL
        rows in the official first-N prefix are capped by physical shed room,
        with same-turn target SELL order respected. If a later represented
        PICKUP or SELL could consume those clipped units, fail closed to the
        unchanged predecessor callback instead of guessing item flow.
        """
        now=int(obs['step']);cap=int(config.get('shedCapacity',100))
        route=self.controller.R[self.controller.cur]

        def legacy():
            f,p=post_units(obs,base,config,shed_capacity=10**6)
            profile=[]
            for t in range(now,end+1):
                if t>now:
                    act=route[t] if t<len(route) else parent.PASS
                    acts=[act.get('farmer',['PASS']),*act.get('hands',[])]
                    for i,a in enumerate(acts):
                        m._apply_unit_action(f,p,i,a,len(f['tiles']),t//24,24,10**6)
                profile.append((t,'before',sum(p['shed'].values())))
                orders=base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
                for o in orders:
                    if not o:continue
                    if o[0]=='SELL' and o[1]!=item:
                        p['shed'][o[1]]=max(0,p['shed'].get(o[1],0)-int(o[2]))
                    elif o[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(o)>2:
                        p['shed'][o[1]]=p['shed'].get(o[1],0)+int(o[2])
                    elif o[0]=='HIRE':
                        f['hands'].append(m._spawn_hand(f,len(f['tiles'])));p['inventories'].append({})
                if t%24==23:
                    m._drop_inventories_to_shed(p,10**6)
                    profile.append((t,'after',sum(p['shed'].values())))
                    break
                profile.append((t,'after',sum(p['shed'].values())))
            def feasible(plan):
                sold=0;orders=dict(plan)
                for t,phase,total in profile:
                    if phase=='after':sold+=orders.get(t,0)
                    if t==now and phase=='before':
                        if total>cap:return False
                        continue
                    if total-sold>cap-1:return False
                return True
            return feasible

        max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))
        def orders_at(t):
            return base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
        def physical_purchase(index,o):
            if index>=max_orders or not isinstance(o,list) or len(o)<3:return None
            op=o[0];product=o[1]
            if not ((op=='BUY_PRODUCT' and product in ('WHEAT','FERTILIZER'))
                    or (op=='BUY_ANIMAL' and product in m.ANIMALS)):
                return None
            try:requested=int(o[2])
            except (TypeError,ValueError):return None
            return (product,requested) if requested>0 else None

        active=[]
        for t in range(now,end+1):
            orders=orders_at(t)
            if not isinstance(orders,list):return legacy()
            for index,o in enumerate(orders):
                purchase=physical_purchase(index,o)
                if purchase is not None:active.append((t,index,purchase[0]))
        if not active:return legacy()

        # A clipped unit may affect later state only through shed removal. Keep
        # those dependency cases byte-for-byte on the predecessor until a full
        # item-flow projection owns them.
        for purchase_t,purchase_index,product in active:
            for t in range(purchase_t+1,end+1):
                action=route[t] if t<len(route) else parent.PASS
                acts=[action.get('farmer',['PASS']),*action.get('hands',[])]
                if any(isinstance(a,list) and len(a)>1 and a[0]=='PICKUP' and a[1]==product
                       for a in acts):return legacy()
            for t in range(purchase_t,end+1):
                start=purchase_index+1 if t==purchase_t else 0
                for o in orders_at(t)[start:]:
                    if isinstance(o,list) and len(o)>2 and o[0]=='SELL' and o[1]==product:
                        return legacy()

        f,p=post_units(obs,base,config,shed_capacity=10**6)
        events=[]
        for t in range(now,end+1):
            if t>now:
                act=route[t] if t<len(route) else parent.PASS
                acts=[act.get('farmer',['PASS']),*act.get('hands',[])]
                for i,a in enumerate(acts):
                    m._apply_unit_action(f,p,i,a,len(f['tiles']),t//24,24,10**6)
            events.append(('phase',t,'before',sum(p['shed'].values())))
            orders=orders_at(t)
            for index,o in enumerate(orders):
                if not o:continue
                if o[0]=='SELL' and o[1]!=item:
                    p['shed'][o[1]]=max(0,p['shed'].get(o[1],0)-int(o[2]))
                elif o[0]=='SELL' and o[1]==item and len(o)>2:
                    events.append(('target_sale',t,max(0,int(o[2])),0))
                elif o[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(o)>2:
                    purchase=physical_purchase(index,o)
                    if purchase is None:
                        p['shed'][o[1]]=p['shed'].get(o[1],0)+int(o[2])
                    else:
                        events.append(('purchase',t,purchase[1],sum(p['shed'].values())))
                elif o[0]=='HIRE':
                    f['hands'].append(m._spawn_hand(f,len(f['tiles'])));p['inventories'].append({})
            events.append(('market_end',t,0,0))
            if t%24==23:
                m._drop_inventories_to_shed(p,10**6)
                events.append(('phase',t,'after',sum(p['shed'].values())))
                break
            events.append(('phase',t,'after',sum(p['shed'].values())))

        def feasible(plan):
            wanted={int(t):max(0,int(q)) for t,q in plan}
            remaining=dict(wanted);sold=0;physical_added=0
            for kind,t,value,total in events:
                if kind=='target_sale':
                    take=min(remaining.get(t,0),value)
                    remaining[t]=remaining.get(t,0)-take;sold+=take
                elif kind=='purchase':
                    occupancy=total+physical_added-sold
                    physical_added+=min(value,max(0,cap-occupancy))
                elif kind=='market_end':
                    sold+=remaining.get(t,0);remaining[t]=0
                else:
                    occupancy=total+physical_added-sold
                    if t==now and value=='before':
                        if occupancy>cap:return False
                        continue
                    if occupancy>cap-1:return False
            return True
        return feasible
'''


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def git_blob_sha1(path: Path) -> str:
    return git_blob_sha1_bytes(Path(path).read_bytes())


def patch_scheduler_bytes(
    source: bytes,
    *,
    expected_git_blob: str = EXPECTED_SCHEDULER_GIT_BLOB,
) -> tuple[bytes, dict[str, Any]]:
    """Return exact candidate bytes or fail closed on source/range ambiguity."""
    actual = git_blob_sha1_bytes(source)
    if actual != expected_git_blob:
        raise RuntimeError(
            f"scheduler source drift: expected Git blob {expected_git_blob}, got {actual}"
        )
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError(
            "active-purchase method anchor cardinality drift: "
            f"start={source.count(START)}, end={source.count(END)}"
        )
    start = source.index(START)
    end = source.index(END, start)
    predecessor = source[start:end]
    candidate = source[:start] + NEW_METHOD + source[end:]
    if candidate == source or candidate.count(NEW_METHOD) != 1:
        raise RuntimeError("active-purchase patch did not produce one exact replacement")
    return candidate, {
        "factor": "active_market_purchase_physical_fill",
        "predecessor_git_blob": actual,
        "predecessor_sha256": sha256_bytes(source),
        "candidate_git_blob": git_blob_sha1_bytes(candidate),
        "candidate_sha256": sha256_bytes(candidate),
        "replaced_method_sha256": sha256_bytes(predecessor),
        "replacement_method_sha256": sha256_bytes(NEW_METHOD),
        "changed_bytes": len(candidate) - len(source),
    }


def clip_requested_purchase(total: int, capacity: int, requested: int) -> int:
    """Pure physical upper-bound contract used by focused tests."""
    total = max(0, int(total))
    capacity = int(capacity)
    requested = max(0, int(requested))
    return min(requested, max(0, capacity - total))

# B7 multi-cargo DROP custody successor

## Status

Default-OFF source/evidence only. This is an additive successor inside the existing canonical `repairs/gameplay/b7-shed-overflow/` family. It does **not** alter the preserved `legacy/` donor, wire a runtime hook, change a feature default, edit `COMPOSITION.json`/`INTEGRATION.json`, or make an economics/activation claim.

## Source theorem

The pinned official engine blob is `3c202c7ee921da239356789e266b694635103fc4` (`reference/engine/kaggriculture.py`). Shed-adjacent `DROP` walks the actor inventory in Python insertion order. For each entry it deposits `min(qty, remaining_room)` and then deletes that inventory entry unconditionally. Once room reaches zero, every later entry is therefore destroyed without changing shed contents.

The preserved B7 donor proves the one-positive-product case. `multicargo_drop_guard.py` extends only two state-equivalent cases, and only when every carried key has a strictly positive quantity:

1. **Full shed (`room == 0`)** — rewrite `DROP` to `PASS`. The original DROP cannot change the shed and deletes all carried entries; PASS leaves the same farm/shed state while retaining well-formed canonical cargo.
2. **First positive product saturates room** — when `room > 0`, the first positive carried entry is a canonical PRODUCT, `first_qty >= room`, and total positive cargo exceeds room, rewrite `DROP` to `PLACE(first_item, room)`. The original DROP fills all remaining room from that first entry, so no later entry can reach the shed. PLACE creates the identical shed post-state while retaining the first-item excess plus every later cargo entry. Equality is valid when `first_qty == room`: the value comes entirely from saving later entries.

One command cannot reproduce a DROP that must deposit across two inventory keys. Those cases remain unchanged.

## Fail-closed boundaries

The successor returns the exact parent action object unchanged for malformed/type-poison state or config, over-capacity sheds, unknown carried keys, zero-quantity inventory keys on a candidate DROP (official DROP deletes those keys), non-adjacent actors, partial-room animal-first cargo (because `PLACE animal` may target a matching structure), DROP spans where `first_qty < room`, and any guarded DROP preceded by a shed `PICKUP` whose successful per-item removal would change room. Earlier exact product `PLACE` and `DROP` rows are modeled in actor order and reduce later room exactly.

All accepted carried keys are limited to the engine's PRODUCTS and ANIMALS. The helper deep-copies only when a replacement is actually admitted; disabled/rejected paths preserve parent object identity.

## Evidence

`test_multicargo_drop_guard.py` covers disabled identity, full-shed product and animal-first cargo, first-item `>` room, first-item `==` room with later cargo, multi-key spanning rejection, zero-quantity-key rejection, animal-first partial-room rejection, prior PLACE/DROP room accounting, prior PICKUP fail-close, unknown/over-capacity/type-poison boundaries, adjacency, and parent immutability.

`check_multicargo_drop_engine.py` authenticates the official engine Git blob before executing the real `_apply_unit_action` implementation. It compares parent DROP vs admitted replacements across both seats, main farmer and hand actor, multiple room/quantity cells, product and animal tail cargo, plus actor-order boundary cases. Changed cells must preserve exact farm and shed state while strictly increasing retained carried quantity.

## Promotion boundary

This patch proves mechanics only. Any runtime composition requires a separate current-native returned-action carrier, source/postimage custody, natural-engagement evidence, and economics gate under the sole V4 merge/control plane. Until then it remains unwired and default-OFF.

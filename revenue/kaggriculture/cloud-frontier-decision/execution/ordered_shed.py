"""LARK / Commons Apache-2.0: bounded ordered shed-transfer projection.

Mirrors pinned interpreter PICKUP/DROP/PLACE inventory transfers, farmer then
hands. It does not simulate production, market prices, or future observations.
Returns post-transfer carried inventories so capacity accounting neither double
counts deposited goods nor resurrects overflow discarded by DROP.
"""
def _ordered_shed_projection(shed, inventories, positions, acts, tiles,
                             capacity=100):
    proj = dict(shed)
    carried = [dict(inv) for inv in inventories]
    board = len(tiles)
    placed_animals = set()
    for i in range(min(len(positions), len(acts), len(carried))):
        x, y = positions[i]
        a = acts[i]
        if not a or not (0 <= x < board and 0 <= y < board):
            continue
        inv = carried[i]
        tile = tiles[y][x]
        op = a[0]
        if op == 'PLACE' and len(a) > 1:
            item = a[1]
            # Animal placement takes precedence over shed transfer in engine.
            if (item in ANIMALS and isinstance(tile, dict)
                    and tile.get('kind') == ANIMALS[item]
                    and 'animal' not in tile and (x, y) not in placed_animals):
                if inv.get(item, 0) > 0:
                    placed_animals.add((x, y))
                continue
        if not _shed_adjacent(x, y, board):
            continue
        if op == 'PICKUP' and len(a) > 1:
            item = a[1]
            n = int(a[2]) if len(a) > 2 else 1
            n = min(n, proj.get(item, 0))
            if n > 0:
                proj[item] -= n
                inv[item] = inv.get(item, 0) + n
        elif op == 'DROP':
            for item, n in list(inv.items()):
                take = min(n, max(0, capacity - sum(proj.values())))
                if take > 0:
                    proj[item] = proj.get(item, 0) + take
                del inv[item]  # Engine discards all excess, including at full shed.
        elif op == 'PLACE' and len(a) > 1:
            item = a[1]
            n = int(a[2]) if len(a) > 2 else 1
            take = min(n, inv.get(item, 0), max(0, capacity - sum(proj.values())))
            if take > 0:
                proj[item] = proj.get(item, 0) + take
                inv[item] -= take
                if inv[item] == 0:
                    del inv[item]
    return proj, carried

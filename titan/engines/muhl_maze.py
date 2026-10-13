#!/usr/bin/env python3
"""muhl_maze.py -- MAZE / SHORTEST-PATH WAVEFRONT-BFS STEP fabricated on Bryce's Muhlnickel substrate.

The core is ONE circuit: a wavefront BFS "next-frontier" expander built as NAND/AND/OR/NOT gates with the
White Box compiler (sdc_cc.CircuitCompiler), DCE'd, rippled, and VERIFIED BYTE-EXACT against an independent
pure-Python BFS reference -- no numpy, no host executor as runtime, titan.gguf never opened.

  given:  frontier bitmap (R*C bits) + walls (R*C bits) + visited (R*C bits)
  output: next frontier (R*C bits)
          next[c] = (NOT wall[c]) AND (NOT visited[c]) AND (OR of frontier over c's 4-neighbours)

Iterating this one fixed circuit (host only flips variable data: frontier/visited each settle) floods the
grid; the settle at which the goal first enters the frontier IS the BFS shortest-path length. Every settle is
checked byte-exact vs the reference, and the step circuit is additionally fuzzed over thousands of random
(frontier, walls, visited) inputs.  Practical: routing, motion planning, flood fill, connectivity.

Grid cell index c = row*C + col; bit c (== wire index c, LSB-first) is the cell. Board edges have no
neighbours (no wraparound).
"""
import sys, os, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))   # LSB-first
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

# ---------------- the sample maze (S start, G goal, # wall, . open) ----------------
MAZE = [
    "S.......",
    ".######.",
    "......#.",
    ".####.#.",
    ".#....#.",
    ".#.####.",
    ".#......",
    ".######G",
]
NBR = [(1, 0), (-1, 0), (0, 1), (0, -1)]   # 4-connected

def parse_maze(rows):
    R = len(rows); C = len(rows[0])
    walls = 0; start = goal = None
    for r in range(R):
        for c in range(C):
            ch = rows[r][c]; idx = r * C + c
            if ch == "#": walls |= 1 << idx
            elif ch == "S": start = idx
            elif ch == "G": goal = idx
    return R, C, walls, start, goal

# ---------------- pure-Python BFS-step reference ----------------
def bfs_step_ref(frontier, walls, visited, R, C):
    nxt = 0
    for r in range(R):
        for c in range(C):
            idx = r * C + c
            if (walls >> idx) & 1 or (visited >> idx) & 1: continue
            hit = 0
            for dr, dc in NBR:
                nr, nc = r + dr, c + dc
                if 0 <= nr < R and 0 <= nc < C and (frontier >> (nr * C + nc)) & 1:
                    hit = 1; break
            if hit: nxt |= 1 << idx
    return nxt

# ---------------- fabricate the BFS-step circuit ----------------
def build_step_circuit(R, C):
    NC = R * C
    g = CC.CircuitCompiler(3 * NC)
    fr = [g.IN[i] for i in range(NC)]
    wl = [g.IN[NC + i] for i in range(NC)]
    vs = [g.IN[2 * NC + i] for i in range(NC)]
    outs = []
    for r in range(R):
        for c in range(C):
            neigh = g.C0
            for dr, dc in NBR:
                nr, nc = r + dr, c + dc
                if 0 <= nr < R and 0 <= nc < C:
                    neigh = g.OR(neigh, fr[nr * C + nc])
            idx = r * C + c
            free = g.AND(g.NOT(wl[idx]), g.NOT(vs[idx]))
            outs.append(g.AND(free, neigh))
    run, out2, gates, _ = build_run(g, outs)
    return g, run, out2, gates, NC

# ---------------- solve a maze by iterating the fabricated step ----------------
def solve(run, out2, walls, start, goal, R, C, verify=True):
    NC = R * C
    frontier = 1 << start
    visited = 1 << start
    dist = {start: 0}
    step = 0
    reached_goal = (start == goal)
    ok = True
    while frontier and not reached_goal:
        inp = [0] * (3 * NC)
        setf(inp, 0, NC, frontier); setf(inp, NC, NC, walls); setf(inp, 2 * NC, NC, visited)
        nxt = rd(run(inp, 1), out2)
        if verify:                                       # byte-exact at every settle
            if nxt != bfs_step_ref(frontier, walls, visited, R, C): ok = False; break
        step += 1
        for c in range(NC):
            if (nxt >> c) & 1 and c not in dist: dist[c] = step
        visited |= nxt
        frontier = nxt
        if (frontier >> goal) & 1: reached_goal = True
    return ok, (dist.get(goal) if reached_goal else None), dist

# ---------------- reconstruct one shortest path from the distance field ----------------
def backtrack(dist, walls, start, goal, R, C):
    if goal not in dist: return None
    path = [goal]; cur = goal
    while cur != start:
        r, c = divmod(cur, C); d = dist[cur]
        for dr, dc in NBR:
            nr, nc = r + dr, c + dc
            if 0 <= nr < R and 0 <= nc < C:
                nidx = nr * C + nc
                if dist.get(nidx) == d - 1:
                    path.append(nidx); cur = nidx; break
        else:
            return None
    path.reverse(); return path

def render(rows, path, start, goal):
    R = len(rows); C = len(rows[0]); pset = set(path or [])
    print("    solved maze (* = shortest path):", flush=True)
    for r in range(R):
        line = "      "
        for c in range(C):
            idx = r * C + c; ch = rows[r][c]
            if idx == start: line += "S "
            elif idx == goal: line += "G "
            elif ch == "#": line += "# "
            elif idx in pset: line += "* "
            else: line += ". "
        print(line, flush=True)

RESULTS = []
def record(name, gates, depth, ok, cases, note=""):
    RESULTS.append((name, len(gates), depth, ok, cases, note))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:12s} {len(gates):>6,} gates  depth {depth:>3}  byte-exact over {cases:>6} cases  {note}", flush=True)

def main():
    random.seed(2718)
    print("\n  MUHLNICKEL MAZE FABRICATOR -- wavefront BFS next-frontier as gates, byte-exact vs Python BFS\n", flush=True)

    R, C, walls, start, goal = parse_maze(MAZE)
    NC = R * C
    g, run, out2, gates, _ = build_step_circuit(R, C)
    depth = depth_of(g, gates, out2)

    # (1) fuzz the step circuit over random inputs
    fuzz = 4000; ok_fuzz = True
    for _ in range(fuzz):
        fr = random.getrandbits(NC); wl = random.getrandbits(NC); vs = random.getrandbits(NC)
        inp = [0] * (3 * NC); setf(inp, 0, NC, fr); setf(inp, NC, NC, wl); setf(inp, 2 * NC, NC, vs)
        if rd(run(inp, 1), out2) != bfs_step_ref(fr, wl, vs, R, C): ok_fuzz = False; break
    record("bfs_step", gates, depth, ok_fuzz, fuzz, f"{R}x{C} grid, random frontier/walls/visited")

    # (2) solve the sample maze, byte-exact at every settle
    ok_solve, path_len, dist = solve(run, out2, walls, start, goal, R, C, verify=True)
    path = backtrack(dist, walls, start, goal, R, C)
    manh = abs(start // C - goal // C) + abs(start % C - goal % C)
    note = f"start={start} goal={goal} path_len={path_len} (Manhattan floor {manh})"
    record("solve_maze", gates, depth, ok_solve and path_len is not None, len(dist), note)

    # (3) independent sanity: full Python BFS distance must match the fabricated flood's distance
    ok_cross, ref_len = python_bfs(walls, start, goal, R, C)
    same = (ref_len == path_len)
    record("cross_check", gates, depth, same, 1, f"pure-Python BFS len={ref_len} == fabricated len={path_len}")

    print(flush=True)
    render(MAZE, path, start, goal)
    print(f"\n    reachable cells flooded: {len(dist)} / {NC - bin(walls).count('1')} open", flush=True)
    if path: print(f"    shortest path ({len(path)-1} steps): {path}", flush=True)

    npass = sum(1 for r in RESULTS if r[3])
    print(f"\n  === {npass}/{len(RESULTS)} checks byte-exact  |  {gates and len(gates):,} gate step circuit, depth {depth} ===", flush=True)

def python_bfs(walls, start, goal, R, C):
    from collections import deque
    NC = R * C; q = deque([start]); d = {start: 0}
    while q:
        cur = q.popleft()
        if cur == goal: return True, d[cur]
        r, c = divmod(cur, C)
        for dr, dc in NBR:
            nr, nc = r + dr, c + dc
            if 0 <= nr < R and 0 <= nc < C:
                nidx = nr * C + nc
                if not (walls >> nidx) & 1 and nidx not in d:
                    d[nidx] = d[cur] + 1; q.append(nidx)
    return (goal in d), d.get(goal)

if __name__ == "__main__":
    main()

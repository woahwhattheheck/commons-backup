"""Offline circuit construction for a new ordinary Bitcoin mining Muhlnickel.

Manufacturing only. This module never opens an existing container or starts a
miner. The compiler simplifications derive from sdc_cc.CircuitCompiler; SHA
arithmetic derives from host/fab_genwin_shallow.py (carry-save reduction, one
Kogge-Stone carry propagation, fused round sums, tree comparator). Physical
feedback is emitted separately by fabricate.py.

New design: Bitcoin uint32 nonce serialization, inclusive target comparison,
sticky first-winner state, and inclusive leased-range termination. These are
ordinary proof-of-work inputs, not wallet keys or key-recovery operations.
"""
from __future__ import annotations

H0 = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)
K = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5,
    0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC,
    0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7,
    0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3,
    0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5,
    0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
)
OPCODES = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
PORT_WIDTHS = (
    ("header", 608), ("nonce", 32), ("target", 256),
    ("winner_nonce", 32), ("win", 1), ("receiver", 1),
    ("nonce_end", 32), ("exhausted", 1), ("enabled", 1),
)
N_INPUTS = sum(width for _, width in PORT_WIDTHS)


class Circuit:
    """Typed, constant-folded, hash-consed manufacturing IR."""

    def __init__(self, n_inputs: int):
        self.n_inputs = n_inputs
        self.gates: list[tuple[str, int, int]] = []
        self.cache: dict[tuple[str, int, int], int] = {}
        self.inputs = list(range(2, 2 + n_inputs))
        self.C0, self.C1 = 0, 1

    def emit(self, op: str, a: int, b: int, *, unique: bool = False) -> int:
        if op != "not" and a > b:
            a, b = b, a
        key = (op, a, b)
        if not unique and key in self.cache:
            return self.cache[key]
        out = 2 + self.n_inputs + len(self.gates)
        self.gates.append(key)
        if not unique:
            self.cache[key] = out
        return out

    def NOT(self, a: int) -> int:
        if a < 2:
            return 1 - a
        return self.emit("not", a, a)

    def AND(self, a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        if a == 1 or a == b:
            return b
        if b == 1:
            return a
        return self.emit("and", a, b)

    def OR(self, a: int, b: int) -> int:
        if a == 1 or b == 1:
            return 1
        if a == 0 or a == b:
            return b
        if b == 0:
            return a
        return self.emit("or", a, b)

    def XOR(self, a: int, b: int) -> int:
        if a == b:
            return 0
        if a == 0:
            return b
        if b == 0:
            return a
        if a == 1:
            return self.NOT(b)
        if b == 1:
            return self.NOT(a)
        return self.emit("xor", a, b)

    def mux(self, select: int, yes: int, no: int) -> int:
        return self.OR(self.AND(select, yes), self.AND(self.NOT(select), no))

    def buffer(self, wire: int) -> int:
        # Dedicated terminal writers must not disappear through CSE or identity
        # folding: each shared state address owns exactly one physical writer.
        return self.emit("and", wire, self.C1, unique=True)

    def compact(self, outputs: list[int]):
        base = 2 + self.n_inputs
        live: set[int] = set()
        stack = [wire for wire in outputs if wire >= base]
        while stack:
            wire = stack.pop()
            if wire in live:
                continue
            live.add(wire)
            _, a, b = self.gates[wire - base]
            stack.extend(x for x in (a, b) if x >= base and x not in live)
        ordered = sorted(live)
        remap = {old: base + index for index, old in enumerate(ordered)}
        def mapped(wire):
            return wire if wire < base else remap[wire]
        gates = [(op, mapped(a), mapped(b))
                 for op, a, b in (self.gates[w - base] for w in ordered)]
        return gates, [mapped(w) for w in outputs]


def cword(g: Circuit, value: int) -> list[int]:
    return [(value >> bit) & 1 for bit in range(32)]


def rotr(word: list[int], n: int) -> list[int]:
    return [word[(bit + n) % 32] for bit in range(32)]


def shr(g: Circuit, word: list[int], n: int) -> list[int]:
    return [word[bit + n] if bit + n < 32 else g.C0 for bit in range(32)]


def xor32(g: Circuit, a: list[int], b: list[int]) -> list[int]:
    return [g.XOR(x, y) for x, y in zip(a, b)]


def and32(g: Circuit, a: list[int], b: list[int]) -> list[int]:
    return [g.AND(x, y) for x, y in zip(a, b)]


def not32(g: Circuit, a: list[int]) -> list[int]:
    return [g.NOT(x) for x in a]


def csa(g: Circuit, a, b, c):
    sums = [g.XOR(g.XOR(x, y), z) for x, y, z in zip(a, b, c)]
    carries = [g.OR(g.AND(x, y), g.OR(g.AND(x, z), g.AND(y, z)))
               for x, y, z in zip(a, b, c)]
    return sums, [g.C0] + carries[:-1]


def add32_prefix(g: Circuit, x, y):
    generate = [g.AND(a, b) for a, b in zip(x, y)]
    propagate = [g.XOR(a, b) for a, b in zip(x, y)]
    original = list(propagate)
    distance = 1
    while distance < 32:
        next_g, next_p = list(generate), list(propagate)
        for bit in range(31, distance - 1, -1):
            next_g[bit] = g.OR(generate[bit], g.AND(propagate[bit], generate[bit - distance]))
            next_p[bit] = g.AND(propagate[bit], propagate[bit - distance])
        generate, propagate = next_g, next_p
        distance *= 2
    return [original[0]] + [g.XOR(original[bit], generate[bit - 1]) for bit in range(1, 32)]


def add_multi(g: Circuit, words):
    words = list(words)
    while len(words) > 2:
        reduced = []
        while len(words) >= 3:
            sums, carries = csa(g, words.pop(), words.pop(), words.pop())
            reduced.extend((sums, carries))
        words = reduced + words
    return add32_prefix(g, *words) if len(words) == 2 else words[0]


def sha_block_shallow(g: Circuit, initial, block):
    words = list(block)
    for i in range(16, 64):
        s0 = xor32(g, xor32(g, rotr(words[i - 15], 7), rotr(words[i - 15], 18)), shr(g, words[i - 15], 3))
        s1 = xor32(g, xor32(g, rotr(words[i - 2], 17), rotr(words[i - 2], 19)), shr(g, words[i - 2], 10))
        words.append(add_multi(g, [words[i - 16], s0, words[i - 7], s1]))
    a, b, c, d, e, f, gg, h = initial
    for i in range(64):
        big1 = xor32(g, xor32(g, rotr(e, 6), rotr(e, 11)), rotr(e, 25))
        choice = xor32(g, and32(g, e, f), and32(g, not32(g, e), gg))
        big0 = xor32(g, xor32(g, rotr(a, 2), rotr(a, 13)), rotr(a, 22))
        majority = xor32(g, xor32(g, and32(g, a, b), and32(g, a, c)), and32(g, b, c))
        terms = [h, big1, choice, cword(g, K[i]), words[i]]
        new_e = add_multi(g, [d] + terms)
        new_a = add_multi(g, terms + [big0, majority])
        h, gg, f, e, d, c, b, a = gg, f, e, new_e, c, b, a, new_a
    return [add_multi(g, [initial[i], word])
            for i, word in enumerate((a, b, c, d, e, f, gg, h))]


def compare_tree(g: Circuit, low_first_a, low_first_b):
    """Return (a < b, a == b) with most-significant composition."""
    nodes = [(g.AND(g.NOT(a), b), g.NOT(g.XOR(a, b)))
             for a, b in zip(low_first_a, low_first_b)]
    while len(nodes) > 1:
        next_nodes = []
        for i in range(0, len(nodes), 2):
            if i + 1 == len(nodes):
                next_nodes.append(nodes[i])
                continue
            low_lt, low_eq = nodes[i]
            high_lt, high_eq = nodes[i + 1]
            next_nodes.append((g.OR(high_lt, g.AND(high_eq, low_lt)),
                               g.AND(high_eq, low_eq)))
        nodes = next_nodes
    return nodes[0]


def build_miner():
    """Build one combinational next-state cone; no gate evaluation or file I/O."""
    g = Circuit(N_INPUTS)
    ports, cursor = {}, 0
    for name, width in PORT_WIDTHS:
        ports[name] = g.inputs[cursor:cursor + width]
        cursor += width
    header, nonce, target = ports["header"], ports["nonce"], ports["target"]
    old_latch = ports["winner_nonce"]
    old_win, exhausted = ports["win"][0], ports["exhausted"][0]
    enabled = ports["enabled"][0]
    header_words = [header[i:i + 32] for i in range(0, 608, 32)]
    # Bitcoin serializes nonce uint32 little-endian; SHA parses that final
    # four-byte word big-endian. Reverse byte positions, preserving bit order.
    nonce_word = [nonce[8 * (3 - bit // 8) + bit % 8] for bit in range(32)]
    words = header_words + [nonce_word]
    initial = [cword(g, value) for value in H0]
    mid = sha_block_shallow(g, initial, words[:16])
    second = words[16:] + [cword(g, 0x80000000)] + [cword(g, 0)] * 10 + [cword(g, 640)]
    first_digest = sha_block_shallow(g, mid, second)
    third = first_digest + [cword(g, 0x80000000)] + [cword(g, 0)] * 6 + [cword(g, 256)]
    digest = sha_block_shallow(g, initial, third)
    hash_le = [digest[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)]
               for i in range(256)]
    less, equal = compare_tree(g, hash_le, target)
    meets_target = g.OR(less, equal)
    active = g.AND(enabled, g.AND(g.NOT(old_win), g.NOT(exhausted)))
    below_end, at_end = compare_tree(g, nonce, ports["nonce_end"])
    in_range = g.OR(below_end, at_end)
    range_done = g.NOT(below_end)
    hit = g.AND(active, g.AND(meets_target, in_range))
    advance = g.AND(active, g.AND(g.NOT(meets_target), below_end))
    incremented = add32_prefix(g, nonce, cword(g, 1))
    next_nonce = [g.mux(advance, incremented[i], nonce[i]) for i in range(32)]
    next_latch = [g.mux(hit, nonce[i], old_latch[i]) for i in range(32)]
    next_win = g.OR(old_win, hit)
    next_exhausted = g.OR(exhausted, g.AND(active, g.OR(g.NOT(in_range), g.AND(g.NOT(meets_target), range_done))))
    # Force distinct terminal writers before physical shared-address binding.
    groups = {
        "nonce": [g.buffer(w) for w in next_nonce],
        "winner_nonce": [g.buffer(w) for w in next_latch],
        "win": [g.buffer(next_win)],
        "exhausted": [g.buffer(next_exhausted)],
    }
    flat = [w for values in groups.values() for w in values]
    gates, compacted = g.compact(flat)
    cursor = 0
    for name, values in groups.items():
        groups[name] = compacted[cursor:cursor + len(values)]
        cursor += len(values)
    return {
        "n_inputs": N_INPUTS, "gates": gates,
        "ports": ports, "next_state": groups,
        "n_wires": 2 + N_INPUTS + len(gates),
        "state_semantics": "gate-level NAND master/slave latches sample next state on the rising ring receiver",
    }

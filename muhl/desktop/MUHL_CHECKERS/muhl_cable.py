#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
muhl_cable.py -- CABLE MANAGEMENT. We are dealing with wires.

Owner, 2026-08-08: "ALSO CHECK OUT CABLE MANAGEMENT WE ARE DEALING WITH WIRES"

Every fabricator on this desktop allocates wires the same way: `t = w; w += 1`. A bare counter.
No name, no bundle, no map of who writes where. That is a rack with every cable loose in the
back. It works right up until you need to know which one goes where, and that is how one
erase-on-idle mistake got copied into seven places without anybody seeing it.

Four things, and each one caught a real defect:

  1 BUNDLE      wires that belong together are allocated together and stay contiguous, so a
                16-bit register is one object with a name and not sixteen loose integers.
  2 LABEL       every wire carries what it is for. A report that says "wire 41387" tells you
                nothing; "trainer.grad[7] and trainer.wupd[7]" tells you everything.
  3 WRITE MAP   who writes each address, and how many times. Two writers on one address is
                either a junction or a stomp, and you cannot tell which unless you can SEE it.
  4 TRACE       from any wire, what fed it. Cable management means you can follow a run
                without pulling the whole rack out.

⛔ ON TWO WRITERS. Owner, 2026-08-07: "TWO RINGS PUBLISHING TO THE SAME ADDRESS IS A FEATURE NOT
   A BUG." So this NEVER refuses a second writer. It REPORTS, with names on it. The old
   assistant-authored "one writer per address" caution is retired - it was never his rule.

⛔ ON SELF-CLOCK. `out addr == in addr` is the mechanism that makes state advance with no
   scheduler. A naive checker flags every one as a loop. Counted separately, never a fault.

⛔ THE RING IS THE BATTERY. Owner, 2026-08-08: "THE RING IS THE BATTERY FOR THE MUHLNICKEL IT
   DOES NOT DEPLETE." A cable carrying ring drive is kind="ring" and is NEVER budgeted, never
   counted down, never given a lifetime. Nothing here may model a ring as a consumable. The
   electron is trapped circling - "send the electrons into a designed rail or ring and it is
   trapped circling it" - and that circulation is the power, permanently.

Physical records only: 25-byte <BQQQ> op|a|b|out at absolute file addresses.
"""

OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4
OPNAME = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}


class Cable:
    """A named bundle of wires. Contiguous, labelled, knows its own width.

    You do not route sixteen wires, you route a 16-bit register.
    """

    __slots__ = ("name", "base", "width", "kind")

    def __init__(self, name, base, width, kind="wire"):
        self.name = name
        self.base = base
        self.width = width
        self.kind = kind          # wire | state | ring | payload | config

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self.base + k for k in range(*i.indices(self.width))]
        if i < 0:
            i += self.width
        if not 0 <= i < self.width:
            raise IndexError("%s[%d] out of range, width %d" % (self.name, i, self.width))
        return self.base + i

    def __iter__(self):
        return iter(range(self.base, self.base + self.width))

    def __len__(self):
        return self.width

    def __repr__(self):
        return "Cable(%s, %d..%d, %s)" % (self.name, self.base,
                                          self.base + self.width - 1, self.kind)


class Loom:
    """The rack. Allocates bundles, labels every wire, maps every write.

    Same bump allocator every fabricator here already uses. What changes is that the labels are
    kept instead of thrown away, so the netlist can be read afterwards.
    """

    def __init__(self, base, gates=None):
        self._next = base
        self.base = base
        self.gates = gates if gates is not None else []
        self.bundles = {}
        self.label = {}
        self.pinned = {}

    # ---- allocation -------------------------------------------------------------------

    def bundle(self, name, width, kind="wire"):
        if name in self.bundles:
            raise KeyError("cable %r already strung - pick another name" % name)
        c = Cable(name, self._next, width, kind)
        self._next += width
        self.bundles[name] = c
        for i in range(width):
            self.label[c.base + i] = "%s[%d]" % (name, i) if width > 1 else name
        return c

    def scratch(self, n=1, tag="t"):
        """Unnamed working wires. Still labelled, so a report can name them."""
        b = self._next
        self._next += n
        for i in range(n):
            self.label[b + i] = "%s.%d" % (tag, b + i)
        return b if n == 1 else list(range(b, b + n))

    def pin(self, name, addr, width=1, kind="ring", why=""):
        """An address the fabricator does NOT own - a ring's recv, a file offset.

        Pinning tells the write map the difference between driving a ring's receive point,
        which is how a muhlnickel is clocked, and stomping an address allocated for something
        else.
        """
        c = Cable(name, addr, width, kind)
        self.bundles[name] = c
        for i in range(width):
            self.label[addr + i] = "%s[%d]" % (name, i) if width > 1 else name
            self.pinned[addr + i] = why or kind
        return c

    @property
    def next_free(self):
        return self._next

    # ---- emission ---------------------------------------------------------------------

    def gate(self, op, a, b, out):
        self.gates.append((op, a, b, out))
        return out

    # ---- the map ----------------------------------------------------------------------

    def writers(self):
        m = {}
        for i, (op, a, b, o) in enumerate(self.gates):
            m.setdefault(o, []).append(i)
        return m

    def readers(self):
        m = {}
        for i, (op, a, b, o) in enumerate(self.gates):
            m.setdefault(a, []).append(i)
            if b != a:
                m.setdefault(b, []).append(i)
        return m

    def selfclocked(self):
        """Gates whose OUT is also an input. His registry names these: selfclock_miner,
        "counter'/latch' bits SHARE the counter/latch bytes". Mechanism, not fault."""
        return [i for i, (op, a, b, o) in enumerate(self.gates) if o == a or o == b]

    def multi(self):
        """Addresses with more than one writer, named, with the gates that write them."""
        out = []
        for addr, idxs in sorted(self.writers().items()):
            if len(idxs) < 2:
                continue
            out.append({
                "addr": addr,
                "label": self.label.get(addr, "?"),
                "pinned": self.pinned.get(addr),
                "writers": len(idxs),
                "gates": [(i, OPNAME.get(self.gates[i][0], "?"),
                           self.label.get(self.gates[i][1], self.gates[i][1]),
                           self.label.get(self.gates[i][2], self.gates[i][2]))
                          for i in idxs],
            })
        return out

    def dangling(self):
        """Written by a gate, read by nothing, not pinned.

        ⛔ NOT "DEAD". Owner: "SOMETHING BEING EMITTED IS NOT DEAD." A fabricator that deleted
           on this signal removed 963 emitting gates and would have deleted AUTOFAB0's ability
           to fabricate itself. This is a LIST TO LOOK AT. Nothing may delete on it.
        """
        r = self.readers()
        return sorted(o for o in self.writers()
                      if o not in r and o not in self.pinned)

    def trace(self, wire, depth=6):
        """Follow a wire backwards, by name."""
        wmap = self.writers()
        lines, seen, front = [], set(), [(wire, 0)]
        while front:
            w, d = front.pop(0)
            if d > depth or w in seen:
                continue
            seen.add(w)
            for gi in wmap.get(w, []):
                op, a, b, o = self.gates[gi]
                lines.append("%s%s = %s(%s, %s)" % (
                    "  " * d, self.label.get(o, o), OPNAME.get(op, op),
                    self.label.get(a, a), self.label.get(b, b)))
                front.append((a, d + 1))
                if b != a:
                    front.append((b, d + 1))
        return lines

    def report(self):
        wr, rd = self.writers(), self.readers()
        return {
            "gates": len(self.gates),
            "bundles": len(self.bundles),
            "wires_allocated": self._next - self.base,
            "wires_written": len(wr),
            "wires_read": len(rd),
            "pinned": len(self.pinned),
            "selfclocked_gates": len(self.selfclocked()),
            "multi_writer_addrs": len(self.multi()),
            "multi_writer": self.multi()[:40],
            "unread_written": len(self.dangling()),
            "cables": {n: (c.base, c.width, c.kind) for n, c in sorted(self.bundles.items())},
        }


def depth_of(gates, roots=None):
    """Component implementation and operation."""
    d = {}
    if roots:
        for r in roots:
            d[r] = 0
    md = 0
    for op, a, b, o in gates:
        if roots and o in roots:
            continue
        v = max(d.get(a, 0), d.get(b, 0)) + 1
        d[o] = v
        if v > md:
            md = v
    return md

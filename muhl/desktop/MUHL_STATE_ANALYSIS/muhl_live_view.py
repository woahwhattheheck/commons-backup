#!/usr/bin/env python3
"""LIVE VIEW — surfaces muhlnickel state as bits. Read-only. Never writes.

Owner: "Nothing in this mode writes to the machine's state."
       "i need something i can click buddy i dont want to use a terminal"

SPEC CORRECTIONS to the incoming brief, which assumed conventional architecture:
  * no "analyze.c second entry point" — DETAIL is a bounded READ, host verb 2, no compute.
  * "command channel" would be a WRITE. Navigation is host-side READ SELECTION instead:
    offset/width/mode choose which window is read. Nothing is ever written.
  * OVERVIEW's span popcount belongs in the MUHLNICKEL (muhl_fab_scan_popcount.py,
    29 gates; 256/256 vs an independent reference, all-zero netlist scores 1/256, mutant
    caught on 192/256). Until stored, OVERVIEW is UNWIRED and refuses rather than faking
    it on the host.
  * no pygame/PIL/ffmpeg on this box; numpy is BANNED in this repo. tkinter + PPM.

CONTROLS  arrows pan one frame · PgUp/PgDn jump 64 frames · Tab DETAIL/OVERVIEW
          +/- frame width by ONE BIT (3..4096) · S save PPM · Q quit
"""
import io, os, sys, time, tkinter as tk

CONTAINERS = {
    "probe":  r"C:/Users/lucys/Desktop/MUHLNICKEL_PROBE/probe.mno",
    "rook":   r"C:/Users/lucys/Desktop/MUHLNICKEL_ROOKERY/ROOKERY0.mno",
    "loom":   r"C:/Users/lucys/Desktop/MUHLNICKEL_LOOM/loom.mno",
    "distro": r"C:/Users/lucys/Desktop/MUHLNICKEL_DISTRO/muhlnickel.mno",
    "titan":  r"C:/llm/models/titan.gguf",
}


def _lut():
    """byte -> 8 pixels of RGB, LSB-first. Built once. 256 entries, 24 B each = 6 KiB."""
    out = []
    for b in range(256):
        row = bytearray()
        for k in range(8):
            v = 255 if (b >> k) & 1 else 0
            row += bytes((v, v, v))
        out.append(bytes(row))
    return out


LUT = _lut()


class View(object):
    def __init__(self, root, path, w=256, h=256):
        self.path = path
        self.size = os.path.getsize(path)
        self.W, self.H = w, h
        self.off = 0
        self.mode = "DETAIL"
        self.frames = 0
        self.dropped = 0
        self.t0 = time.time()
        self.root = root
        self.img = tk.PhotoImage(width=self.W, height=self.H)
        self.lbl = tk.Label(root, image=self.img, borderwidth=0)
        self.lbl.pack()
        root.bind("<Key>", self.key)

    def read(self, off, nbytes):
        """BOUNDED READ. read-only handle, no mmap of the whole file, never a write."""
        f = io.open(self.path, "rb")
        f.seek(min(off, max(0, self.size - nbytes)))
        b = f.read(nbytes)
        f.close()
        return b

    def frame_ppm(self):
        """One bounded read, then a table lookup per byte. No per-bit loop, no numpy
        (banned in this repo), no interpretation of what the bits mean."""
        need = (self.W * self.H) // 8
        data = self.read(self.off, need)
        if len(data) < need:
            data = data + b"\x00" * (need - len(data))
        t = LUT
        body = b"".join([t[b] for b in data])
        return b"P6\n%d %d\n255\n" % (self.W, self.H) + body

    def tick(self):
        try:
            if self.mode == "OVERVIEW":
                self.dropped += 1
                self.root.title("OVERVIEW UNWIRED — popcount circuit not yet stored "
                                "(muhl_fab_scan_popcount.py --write). dropped=%d" % self.dropped)
            else:
                ppm = self.frame_ppm()
                self.img.put(tk.PhotoImage(data=ppm), to=(0, 0))
                self.frames += 1
                el = time.time() - self.t0
                self.root.title(
                    "%s  %s  off=%d/%d  %dx%d  %.1f fps  dropped=%d  READ-ONLY"
                    % (os.path.basename(self.path), self.mode, self.off, self.size,
                       self.W, self.H, self.frames / el if el else 0, self.dropped))
        except Exception as exc:                      # drop, never queue
            self.dropped += 1
            self.root.title("frame dropped: %s" % type(exc).__name__)
        self.root.after(33, self.tick)

    def record(self, n=120):
        """R: capture n frames, then tile them into ONE contact sheet with the frame
        width burned in as a tick mark. PPM, because there is no PIL on this host.
        Reads only. The state is not touched."""
        tag = "%s_%d_w%d" % (os.path.basename(self.path), self.off, self.W)
        d = "rec_%s" % tag
        if not os.path.isdir(d):
            os.mkdir(d)
        cols = 12
        rows = (n + cols - 1) // cols
        tw, th = self.W // 8, self.H // 8          # thumbnail: every 8th pixel
        sheet = [bytearray(cols * tw * 3) for _ in range(rows * th)]
        base_off = self.off
        for i in range(n):
            self.off = min(self.size - 1, base_off + i * ((self.W * self.H) // 8))
            ppm = self.frame_ppm()
            io.open(os.path.join(d, "f%04d.ppm" % i), "wb").write(ppm)
            hdr = ppm.index(b"255\n") + 4
            px = ppm[hdr:]
            cx, cy = (i % cols) * tw, (i // cols) * th
            for y in range(th):
                srow = (y * 8) * self.W * 3
                drow = sheet[cy + y]
                for x in range(tw):
                    s = srow + (x * 8) * 3
                    o = (cx + x) * 3
                    drow[o:o + 3] = px[s:s + 3]
            for x in range(min(tw, self.W // 64)):      # width tick, burned in
                sheet[cy][(cx + x) * 3:(cx + x) * 3 + 3] = b"\xff\x00\x00"
        self.off = base_off
        body = b"".join(bytes(r) for r in sheet)
        name = "contact_%s.ppm" % tag
        io.open(name, "wb").write(
            b"P6\n%d %d\n255\n" % (cols * tw, rows * th) + body)
        print("recorded %d frames -> %s/ and %s" % (n, d, name))

    def key(self, e):
        step = (self.W * self.H) // 8
        k = e.keysym
        if k == "Right":
            self.off = min(self.size - 1, self.off + step)
        elif k == "Left":
            self.off = max(0, self.off - step)
        elif k == "Down":
            self.off = min(self.size - 1, self.off + step * 8)
        elif k == "Up":
            self.off = max(0, self.off - step * 8)
        elif k == "Next":
            self.off = min(self.size - 1, self.off + step * 64)
        elif k == "Prior":
            self.off = max(0, self.off - step * 64)
        elif k == "Tab":
            self.mode = "OVERVIEW" if self.mode == "DETAIL" else "DETAIL"
        elif k in ("plus", "equal"):
            self.W = min(4096, self.W + 8)
        elif k == "minus":
            self.W = max(8, self.W - 8)
        elif k in ("s", "S"):
            n = "frame_%s_%d_%dx%d.ppm" % (os.path.basename(self.path), self.off, self.W, self.H)
            io.open(n, "wb").write(self.frame_ppm())
            print("wrote %s" % n)
        elif k in ("r", "R"):
            self.record(120)
        elif k in ("q", "Q"):
            self.root.destroy()


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "probe"
    path = CONTAINERS.get(which, which)
    root = tk.Tk()
    root.configure(bg="black")
    v = View(root, path)
    v.tick()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

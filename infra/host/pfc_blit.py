"""host/pfc_blit.py — reliable framebuffer -> tkinter PhotoImage.

Tk's PhotoImage(data=base64-PPM) is not recognized on some Tk builds ("couldn't recognize image data"), which silently
killed the render loop (black screen). PhotoImage(file=PPM) IS reliable, so we write the frame to a tiny PPM temp file and
load that. Ping-pong two files so a load never races a write. Pure stdlib, no PIL, no numpy.
"""
import os, tkinter as tk

_DIR = os.environ.get("TEMP") or os.environ.get("TMP") or "."
_N = [0]


def photo(w, h, rgb):
    _N[0] ^= 1
    p = os.path.join(_DIR, f"pfc_blit_{_N[0]}.ppm")
    with open(p, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h)); f.write(bytes(rgb))
    return tk.PhotoImage(file=p)

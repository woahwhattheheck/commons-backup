/* 1bpp face at WIDTH-200. Does not change muhl_png.py bits mode.
   The picture is one bit per pixel. Black gutters are headroom. */
(function (g) {
  "use strict";

  function bitAt(bytes, i) {
    var bi = i >> 3;
    if (bi >= bytes.length) return 0;
    return (bytes[bi] >> (7 - (i & 7))) & 1;
  }

  function parseDump(text) {
    var bits = [];
    String(text || "").split(/\n/).forEach(function (ln) {
      var m = /^\s*\d+\s+([01]+)\s*$/.exec(ln);
      if (m) {
        var s = m[1], i;
        for (i = 0; i < s.length; i++) bits.push(s.charCodeAt(i) === 49 ? 1 : 0);
      }
    });
    var bytes = new Uint8Array((bits.length + 7) >> 3);
    var i;
    for (i = 0; i < bits.length; i++) {
      if (bits[i]) bytes[i >> 3] |= (1 << (7 - (i & 7)));
    }
    return { bits: bits.length, bytes: bytes };
  }

  function render(canvas, bytes, opts) {
    var W = (g.WIDTH200 && g.WIDTH200.WIDTH) || 200;
    var scale = (opts && opts.scale) || 2;
    var showGutters = !opts || opts.gutters !== false;
    var total = bytes.length * 8;
    var h = Math.ceil(total / W);
    var src = document.createElement("canvas");
    src.width = W;
    src.height = h;
    var sctx = src.getContext("2d");
    var img = sctx.createImageData(W, h);
    var d = img.data;
    var i, x, y, on, o, field, gutt;
    for (i = 0; i < W * h; i++) {
      x = i % W;
      y = (i / W) | 0;
      on = bitAt(bytes, i);
      o = i * 4;
      gutt = false;
      if (showGutters && g.WIDTH200) {
        for (field = 0; field < g.WIDTH200.FIELDS.length; field++) {
          var f = g.WIDTH200.FIELDS[field];
          if (f.gutterLo != null && x >= f.gutterLo && x <= f.gutterHi) gutt = true;
        }
      }
      if (on) {
        d[o] = 255; d[o + 1] = 255; d[o + 2] = 255; d[o + 3] = 255;
      } else if (gutt) {
        d[o] = 18; d[o + 1] = 28; d[o + 2] = 48; d[o + 3] = 255;
      } else {
        d[o] = 0; d[o + 1] = 0; d[o + 2] = 0; d[o + 3] = 255;
      }
    }
    sctx.putImageData(img, 0, 0);
    canvas.width = W * scale;
    canvas.height = h * scale;
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
    return { w: W, h: h, bits: total, rows: h };
  }

  function bind() {
    var canvas = document.getElementById("face-canvas");
    var status = document.getElementById("face-status");
    var fileIn = document.getElementById("face-file");
    if (!canvas) return;

    function say(t) { if (status) status.textContent = t; }

    function show(bytes, label) {
      var r = render(canvas, bytes, { scale: 2, gutters: true });
      say(label + " · " + r.rows.toLocaleString() + " rows at width " + r.w +
        " · " + r.bits.toLocaleString() + " bits · gutters tinted (headroom)");
    }

    if (fileIn) {
      fileIn.addEventListener("change", function () {
        var f = fileIn.files[0];
        if (!f) return;
        var reader = new FileReader();
        reader.onload = function () { show(new Uint8Array(reader.result), f.name); };
        reader.readAsArrayBuffer(f);
      });
    }

    fetch("./muhl/containers/MUHL_VISIBLE/AUTOFAB0.bits.txt?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (t) {
        var p = parseDump(t);
        if (!p.bits) throw new Error("no bits in dump");
        show(p.bytes, "published AUTOFAB0.bits.txt (" + p.bits.toLocaleString() + " bits)");
      })
      .catch(function (e) {
        say("drop a .mno or a bits dump — published dump not loaded (" + (e && e.message ? e.message : e) + ")");
      });
  }

  g.FACE = { parseDump: parseDump, render: render, bitAt: bitAt, bind: bind };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})(window);

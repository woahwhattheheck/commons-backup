/* ringdelta.js — public XOR-delta / RDV1 door. No auth. No verdict. */
(function () {
  "use strict";

  var WIDTH = 25;
  var HEADER = 48;
  var SEED0 = "./muhl/containers/MUHLNICKEL_DISTRO/SEED0.mno";
  var box = document.getElementById("rd-box");
  var srcBytes = null;
  var lastContainer = null;

  function say(t, empty) {
    box.textContent = t;
    box.setAttribute("data-empty", empty ? "1" : "0");
  }

  function hexSha(buf) {
    return crypto.subtle.digest("SHA-256", buf).then(function (d) {
      var b = new Uint8Array(d);
      var s = "";
      var i;
      for (i = 0; i < b.length; i++) s += (b[i] + 256).toString(16).slice(1);
      return s;
    });
  }

  function u32(n, view, off) {
    view.setUint32(off, n >>> 0, true);
  }

  function ru32(view, off) {
    return view.getUint32(off, true);
  }

  function xorDelta(src) {
    var out = new Uint8Array(src.length);
    var i;
    for (i = 0; i < src.length; i++) {
      out[i] = src[i] ^ (i >= WIDTH ? src[i - WIDTH] : 0);
    }
    return out;
  }

  function xorUndelta(delta) {
    var out = new Uint8Array(delta.length);
    var i;
    for (i = 0; i < delta.length; i++) {
      out[i] = delta[i] ^ (i >= WIDTH ? out[i - WIDTH] : 0);
    }
    return out;
  }

  function encodeRdv1(src) {
    var delta = xorDelta(src);
    var nZero = 0;
    var nNz = 0;
    var i;
    for (i = 0; i < delta.length; i++) {
      if (delta[i] === 0) nZero++;
      else nNz++;
    }
    var maskLen = (src.length + 7) >> 3;
    var out = new Uint8Array(HEADER + maskLen + nNz);
    var view = new DataView(out.buffer);
    out[0] = 82; out[1] = 68; out[2] = 86; out[3] = 49; // RDV1
    u32(1, view, 4);
    u32(src.length, view, 8);
    u32(WIDTH, view, 12);
    u32(nZero, view, 16);
    u32(nNz, view, 20);
    var valuesAt = HEADER + maskLen;
    var vi = 0;
    for (i = 0; i < delta.length; i++) {
      if (delta[i]) {
        out[HEADER + (i >> 3)] |= 1 << (i & 7);
        out[valuesAt + vi] = delta[i];
        vi++;
      }
    }
    return { container: out, nZero: nZero, nNz: nNz, delta: delta };
  }

  function decodeRdv1(blob) {
    if (blob.length < HEADER || blob[0] !== 82 || blob[1] !== 68 || blob[2] !== 86 || blob[3] !== 49) {
      throw new Error("not RDV1");
    }
    var view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
    var version = ru32(view, 4);
    var srcLen = ru32(view, 8);
    var width = ru32(view, 12);
    var nZero = ru32(view, 16);
    var nNz = ru32(view, 20);
    if (version !== 1 || width !== WIDTH) throw new Error("bad RDV1 header");
    var maskLen = (srcLen + 7) >> 3;
    if (blob.length !== HEADER + maskLen + nNz) throw new Error("bad RDV1 size");
    var delta = new Uint8Array(srcLen);
    var vi = 0;
    var i;
    for (i = 0; i < srcLen; i++) {
      if (blob[HEADER + (i >> 3)] & (1 << (i & 7))) {
        delta[i] = blob[HEADER + maskLen + vi];
        vi++;
      }
    }
    if (vi !== nNz) throw new Error("bitmask/value mismatch");
    return xorUndelta(delta);
  }

  function deflateSize(bytes) {
    if (typeof CompressionStream === "undefined") return Promise.resolve(null);
    var cs = new CompressionStream("deflate");
    var w = cs.writable.getWriter();
    w.write(bytes);
    w.close();
    return new Response(cs.readable).arrayBuffer().then(function (buf) {
      return buf.byteLength;
    });
  }

  function report(label, src) {
    var enc = encodeRdv1(src);
    var back = decodeRdv1(enc.container);
    lastContainer = enc.container;
    var same = back.length === src.length;
    var i;
    if (same) {
      for (i = 0; i < src.length; i++) if (back[i] !== src[i]) { same = false; break; }
    }
    srcBytes = src;
    Promise.all([
      hexSha(src),
      hexSha(back),
      deflateSize(src),
      deflateSize(enc.delta)
    ]).then(function (vals) {
      var lines = [
        label + " · " + src.length + " B",
        "source sha256 " + vals[0],
        "stride-25 XOR zeros " + enc.nZero + " (" + (100 * enc.nZero / (src.length || 1)).toFixed(2) + "%)",
        "native RDV1 container " + enc.container.length + " B (" + (100 * enc.container.length / (src.length || 1)).toFixed(2) + "%)",
        vals[2] == null ? "browser deflate(source) unavailable" : "browser deflate(source) " + vals[2] + " (weather, not zlib-9)",
        vals[3] == null ? "browser deflate(delta) unavailable" : "browser deflate(delta) " + vals[3] + " (weather, not zlib-9)",
        same && vals[0] === vals[1]
          ? "decode(encode(src)) == src, exact SHA"
          : "round-trip failed"
      ];
      say(lines.join("\n"), false);
    });
  }

  function loadBytes(bytes, label) {
    report(label, bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes));
  }

  document.getElementById("rd-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    f.arrayBuffer().then(function (buf) { loadBytes(new Uint8Array(buf), f.name); });
  });
  document.getElementById("rd-seed").addEventListener("click", function () {
    say("loading SEED0…", true);
    fetch(SEED0, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
      .then(function (buf) { loadBytes(new Uint8Array(buf), "published SEED0.mno"); })
      .catch(function (e) { say("SEED0 not loaded — drop a file (" + e + ")", true); });
  });
  document.getElementById("rd-download").addEventListener("click", function () {
    if (!lastContainer) { say("encode something first", true); return; }
    var blob = new Blob([lastContainer], { type: "application/octet-stream" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ringdelta.rdv1";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  fetch(SEED0, { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
    .then(function (buf) { loadBytes(new Uint8Array(buf), "published SEED0.mno"); })
    .catch(function () { say("drop a file or load published SEED0.", true); });
})();

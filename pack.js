/* pack.js — browser bit-plane for the compression doors.
   Additive. Does not replace foldpack.py / stackpack.py / evolve.py.
   No conclusion line. Round-trip is "grids match" or "grids differ". */
(function (g) {
  "use strict";

  var W0 = (g.WIDTH200 && g.WIDTH200.WIDTH) || 200;

  var PALETTE = [
    [8, 10, 14], [40, 90, 200], [230, 190, 60], [210, 50, 50],
    [30, 160, 140], [150, 90, 190], [240, 120, 40], [90, 200, 110],
    [200, 200, 210], [120, 60, 40], [60, 120, 200], [200, 80, 140],
    [70, 180, 190], [180, 180, 70], [140, 140, 150], [255, 255, 255]
  ];

  var PROGRAM = ["TRANSPOSE", "REV_COLS", "XOR_COL", "XOR_COL", "REV_COLS", "ROT4"];

  function bitAt(bytes, i) {
    var bi = i >> 3;
    if (bi >= bytes.length) return 0;
    return (bytes[bi] >> (7 - (i & 7))) & 1;
  }

  function bytesToGrid(bytes, W) {
    W = W || W0;
    var total = bytes.length * 8;
    var H = Math.ceil(total / W) || 1;
    var grid = [];
    var y, x, row, i;
    for (y = 0; y < H; y++) {
      row = new Uint8Array(W);
      for (x = 0; x < W; x++) {
        i = y * W + x;
        row[x] = i < total ? bitAt(bytes, i) : 0;
      }
      grid.push(row);
    }
    return grid;
  }

  function gridToBytes(grid) {
    var H = grid.length, W = grid[0] ? grid[0].length : 0;
    var out = new Uint8Array((H * W + 7) >> 3);
    var y, x, i, v;
    i = 0;
    for (y = 0; y < H; y++) {
      for (x = 0; x < W; x++) {
        v = grid[y][x] & 1;
        if (v) out[i >> 3] |= (1 << (7 - (i & 7)));
        i++;
      }
    }
    return out;
  }

  function copyGrid(grid) {
    return grid.map(function (r) { return new Uint8Array(r); });
  }

  function gridsMatch(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    var y, x;
    for (y = 0; y < a.length; y++) {
      if (a[y].length !== b[y].length) return false;
      for (x = 0; x < a[y].length; x++) if (a[y][x] !== b[y][x]) return false;
    }
    return true;
  }

  function parseDump(text) {
    var bits = [];
    String(text || "").split(/\n/).forEach(function (ln) {
      var m = /^\s*\d+\s+([01]+)\s*$/.exec(ln);
      if (!m) return;
      var s = m[1], i;
      for (i = 0; i < s.length; i++) bits.push(s.charCodeAt(i) === 49 ? 1 : 0);
    });
    var bytes = new Uint8Array((bits.length + 7) >> 3);
    var i;
    for (i = 0; i < bits.length; i++) {
      if (bits[i]) bytes[i >> 3] |= (1 << (7 - (i & 7)));
    }
    return { bits: bits.length, bytes: bytes };
  }

  function bitLength(n) {
    if (n <= 1) return 1;
    var b = 0;
    while (n > 0) { b++; n = Math.floor(n / 2); }
    return b;
  }

  function packTight(grid, states) {
    var bits = Math.max(1, bitLength(Math.max(1, states - 1)));
    var H = grid.length, W = grid[0] ? grid[0].length : 0;
    var out = [];
    var acc = 0, nacc = 0, y, x, v;
    for (y = 0; y < H; y++) {
      for (x = 0; x < W; x++) {
        v = grid[y][x] | 0;
        acc = (acc * Math.pow(2, bits)) + v;
        nacc += bits;
        while (nacc >= 8) {
          nacc -= 8;
          out.push(Math.floor(acc / Math.pow(2, nacc)) & 255);
          acc = acc % Math.pow(2, nacc);
        }
      }
    }
    if (nacc) out.push((acc * Math.pow(2, 8 - nacc)) & 255);
    return { bytes: new Uint8Array(out), bits: bits, packed: out.length };
  }

  function pairing(H, mode) {
    var half = H >> 1;
    var pairs = [];
    var left = [];
    var i;
    if (mode === "mirror") {
      for (i = 0; i < half; i++) pairs.push([i, H - 1 - i]);
      if (H % 2) left.push(half);
    } else if (mode === "adjacent" || mode === "accordion") {
      for (i = 0; i < half; i++) pairs.push([2 * i, 2 * i + 1]);
      if (H % 2) left.push(2 * half);
    } else {
      for (i = 0; i < half; i++) pairs.push([i, i + half]);
      if (H % 2) left.push(2 * half);
    }
    return { pairs: pairs, left: left };
  }

  function foldOnce(grid, states, mode) {
    var H = grid.length, W = grid[0].length;
    var p = pairing(H, mode);
    var out = [];
    var k, x, a, b, row;
    for (k = 0; k < p.pairs.length; k++) {
      a = p.pairs[k][0];
      b = p.pairs[k][1];
      row = new Uint32Array(W);
      for (x = 0; x < W; x++) row[x] = (grid[a][x] * states) + grid[b][x];
      out.push(row);
    }
    var odds = p.left.map(function (i) { return [i, grid[i]]; });
    return { grid: out, H: out.length, states: states * states, odds: odds };
  }

  function colorFor(v) {
    if (v < PALETTE.length) return PALETTE[v];
    return [(v * 37) % 256, (v * 91) % 256, (v * 151) % 256];
  }

  function renderFold(canvas, grid, states, scale) {
    scale = scale || 2;
    var H = grid.length, W = grid[0] ? grid[0].length : 0;
    var src = document.createElement("canvas");
    src.width = W;
    src.height = H;
    var sctx = src.getContext("2d");
    var img = sctx.createImageData(W, H);
    var d = img.data;
    var y, x, o, c;
    for (y = 0; y < H; y++) {
      for (x = 0; x < W; x++) {
        c = colorFor(grid[y][x] | 0);
        o = (y * W + x) * 4;
        d[o] = c[0]; d[o + 1] = c[1]; d[o + 2] = c[2]; d[o + 3] = 255;
      }
    }
    sctx.putImageData(img, 0, 0);
    canvas.width = Math.max(1, W * scale);
    canvas.height = Math.max(1, H * scale);
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
    return { w: W, h: H, states: states };
  }

  function renderFace(canvas, grid, scale) {
    scale = scale || 2;
    var H = grid.length, W = grid[0] ? grid[0].length : 0;
    var src = document.createElement("canvas");
    src.width = W;
    src.height = H;
    var sctx = src.getContext("2d");
    var img = sctx.createImageData(W, H);
    var d = img.data;
    var y, x, o, on;
    for (y = 0; y < H; y++) {
      for (x = 0; x < W; x++) {
        on = grid[y][x] & 1;
        o = (y * W + x) * 4;
        if (on) { d[o] = 255; d[o + 1] = 255; d[o + 2] = 255; }
        else { d[o] = 0; d[o + 1] = 0; d[o + 2] = 0; }
        d[o + 3] = 255;
      }
    }
    sctx.putImageData(img, 0, 0);
    canvas.width = Math.max(1, W * scale);
    canvas.height = Math.max(1, H * scale);
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
    return { w: W, h: H };
  }

  function stackpackWx1(grid) {
    var H = grid.length, W = grid[0] ? grid[0].length : 0;
    var table = [];
    var index = {};
    var ids = [];
    var glyphs = [];
    var x, y, key, bits;
    for (x = 0; x < W; x++) {
      bits = [];
      for (y = 0; y < H; y++) bits.push(grid[y][x] & 1);
      key = bits.join("");
      if (index[key] == null) {
        index[key] = table.length;
        table.push(bits);
        glyphs.push(bits);
      }
      ids.push(index[key]);
    }
    var E = table.length;
    var symBits = bitLength(Math.max(1, E - 1));
    var stream = packInts(ids, symBits);
    var tblBits = H;
    var tblVals = [];
    var i, acc, n, b;
    for (i = 0; i < table.length; i++) {
      acc = 0;
      /* keep table as raw bit-columns; packed size is E * K bits */
    }
    var tablePacked = Math.ceil((E * tblBits) / 8);
    return {
      W: W, H: H, K: H, cells: W, distinct: E, glyphs: glyphs, ids: ids,
      symBits: symBits, stream: stream, tablePacked: tablePacked,
      stringPacked: stream.length
    };
  }

  function packInts(vals, bits) {
    var out = [];
    var acc = 0, nacc = 0, i, v;
    for (i = 0; i < vals.length; i++) {
      v = vals[i] | 0;
      acc = (acc * Math.pow(2, bits)) + v;
      nacc += bits;
      while (nacc >= 8) {
        nacc -= 8;
        out.push(Math.floor(acc / Math.pow(2, nacc)) & 255);
        acc = acc % Math.pow(2, nacc);
      }
    }
    if (nacc) out.push((acc * Math.pow(2, 8 - nacc)) & 255);
    return new Uint8Array(out);
  }

  function hexOf(bytes, cap) {
    var n = bytes.length;
    var lim = cap != null ? Math.min(n, cap) : n;
    var s = "";
    var i;
    for (i = 0; i < lim; i++) s += (bytes[i] + 256).toString(16).slice(1);
    if (lim < n) s += "…+" + (n - lim) + "B";
    return s;
  }

  function renderGlyphs(canvas, glyphs, scaleX, scaleY) {
    scaleX = scaleX || 4;
    scaleY = scaleY || 1;
    var n = glyphs.length;
    var H = n ? glyphs[0].length : 0;
    var src = document.createElement("canvas");
    src.width = Math.max(1, n);
    src.height = Math.max(1, H);
    var sctx = src.getContext("2d");
    var img = sctx.createImageData(src.width, src.height);
    var d = img.data;
    var x, y, o, on;
    for (x = 0; x < n; x++) {
      for (y = 0; y < H; y++) {
        on = glyphs[x][y] & 1;
        o = (y * n + x) * 4;
        if (on) { d[o] = 255; d[o + 1] = 255; d[o + 2] = 255; }
        else { d[o] = 8; d[o + 1] = 10; d[o + 2] = 14; }
        d[o + 3] = 255;
      }
    }
    sctx.putImageData(img, 0, 0);
    canvas.width = Math.max(1, n * scaleX);
    canvas.height = Math.max(1, H * scaleY);
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
    return { glyphs: n, depth: H };
  }

  function tXorPrevCol(g) {
    return g.map(function (r) {
      var n = new Uint8Array(r);
      var x;
      for (x = r.length - 1; x > 0; x--) n[x] = r[x] ^ r[x - 1];
      return n;
    });
  }
  function iXorPrevCol(g) {
    return g.map(function (r) {
      var n = new Uint8Array(r);
      var x;
      for (x = 1; x < r.length; x++) n[x] = r[x] ^ n[x - 1];
      return n;
    });
  }
  function tXorPrevRow(g) {
    var o = [new Uint8Array(g[0])];
    var y;
    for (y = 1; y < g.length; y++) {
      o.push(new Uint8Array(g[y].map(function (v, x) { return v ^ g[y - 1][x]; })));
    }
    return o;
  }
  function iXorPrevRow(g) {
    var o = [new Uint8Array(g[0])];
    var y;
    for (y = 1; y < g.length; y++) {
      o.push(new Uint8Array(g[y].map(function (v, x) { return v ^ o[y - 1][x]; })));
    }
    return o;
  }
  function tTranspose(g) {
    var H = g.length, W = g[0].length;
    var o = [];
    var x, y, row;
    for (x = 0; x < W; x++) {
      row = new Uint8Array(H);
      for (y = 0; y < H; y++) row[y] = g[y][x];
      o.push(row);
    }
    return o;
  }
  function tRevRows(g) {
    var o = [];
    var y;
    for (y = g.length - 1; y >= 0; y--) o.push(new Uint8Array(g[y]));
    return o;
  }
  function tRevCols(g) {
    return g.map(function (r) {
      var n = new Uint8Array(r.length);
      var x;
      for (x = 0; x < r.length; x++) n[x] = r[r.length - 1 - x];
      return n;
    });
  }
  function rot(g, k) {
    var W = g[0].length;
    k = ((k % W) + W) % W;
    return g.map(function (r) {
      var n = new Uint8Array(W);
      var x;
      for (x = 0; x < W; x++) n[x] = r[(x + k) % W];
      return n;
    });
  }

  var OPS = {
    IDENT: { f: copyGrid, i: copyGrid },
    XOR_COL: { f: tXorPrevCol, i: iXorPrevCol },
    XOR_ROW: { f: tXorPrevRow, i: iXorPrevRow },
    TRANSPOSE: { f: tTranspose, i: tTranspose },
    REV_ROWS: { f: tRevRows, i: tRevRows },
    REV_COLS: { f: tRevCols, i: tRevCols },
    ROT4: { f: function (g) { return rot(g, 4); }, i: function (g) { return rot(g, -4); } },
    ROT25: { f: function (g) { return rot(g, 25); }, i: function (g) { return rot(g, -25); } }
  };

  function applySeq(grid, seq) {
    var g0 = copyGrid(grid);
    var i, op;
    for (i = 0; i < seq.length; i++) {
      op = OPS[seq[i]];
      if (!op) throw new Error("unknown op " + seq[i]);
      g0 = op.f(g0);
    }
    return g0;
  }

  function invertSeq(grid, seq) {
    var g0 = copyGrid(grid);
    var i, op;
    for (i = seq.length - 1; i >= 0; i--) {
      op = OPS[seq[i]];
      if (!op) throw new Error("unknown op " + seq[i]);
      g0 = op.i(g0);
    }
    return g0;
  }

  function deflateLen(bytes) {
    if (typeof CompressionStream === "undefined") {
      return Promise.resolve(null);
    }
    try {
      var cs = new CompressionStream("deflate");
      var stream = new Blob([bytes]).stream().pipeThrough(cs);
      return new Response(stream).arrayBuffer().then(function (buf) {
        return buf.byteLength;
      });
    } catch (e) {
      return Promise.resolve(null);
    }
  }

  function loadBytes(url) {
    return fetch(url + (url.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now(), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error(String(r.status));
        return r.arrayBuffer();
      })
      .then(function (buf) { return new Uint8Array(buf); });
  }

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onload = function () { resolve(new Uint8Array(fr.result)); };
      fr.onerror = function () { reject(fr.error); };
      fr.readAsArrayBuffer(file);
    });
  }

  g.PACK = {
    WIDTH: W0,
    PALETTE: PALETTE,
    PROGRAM: PROGRAM,
    SEED0: "./muhl/containers/MUHLNICKEL_DISTRO/SEED0.mno",
    GERM: "./muhl/containers/MUHLNICKEL_DISTRO/SEED0_GERM.mno",
    DISTRO: "./muhl/containers/MUHLNICKEL_DISTRO/muhlnickel.mno",
    bitAt: bitAt,
    bytesToGrid: bytesToGrid,
    gridToBytes: gridToBytes,
    copyGrid: copyGrid,
    gridsMatch: gridsMatch,
    parseDump: parseDump,
    packTight: packTight,
    pairing: pairing,
    foldOnce: foldOnce,
    renderFold: renderFold,
    renderFace: renderFace,
    renderGlyphs: renderGlyphs,
    stackpackWx1: stackpackWx1,
    hexOf: hexOf,
    applySeq: applySeq,
    invertSeq: invertSeq,
    deflateLen: deflateLen,
    loadBytes: loadBytes,
    readFile: readFile,
    OPS: OPS
  };
})(window);

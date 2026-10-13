/* Regime flipbook. Owner: the pattern holds then shifts.
   Do not average into one occupancy number. Stack strips. */
(function (g) {
  "use strict";

  function recordsPerStrip() {
    var el = document.getElementById("flip-rows");
    var n = el ? parseInt(el.value, 10) : 64;
    return (n > 0 && n < 4096) ? n : 64;
  }

  function drawStrip(bytes, startBit, bitCount) {
    var W = (g.WIDTH200 && g.WIDTH200.WIDTH) || 200;
    var slice = new Uint8Array((bitCount + 7) >> 3);
    var i;
    for (i = 0; i < bitCount; i++) {
      var src = startBit + i;
      var on = g.FACE && g.FACE.bitAt ? g.FACE.bitAt(bytes, src) : 0;
      if (on) slice[i >> 3] |= (1 << (7 - (i & 7)));
    }
    var c = document.createElement("canvas");
    if (g.FACE && g.FACE.render) g.FACE.render(c, slice, { scale: 2, gutters: true });
    return c;
  }

  function stack(bytes, label) {
    var host = document.getElementById("flip-host");
    var status = document.getElementById("flip-status");
    if (!host) return;
    host.innerHTML = "";
    var W = (g.WIDTH200 && g.WIDTH200.WIDTH) || 200;
    var rows = recordsPerStrip();
    var bitsPer = W * rows;
    var total = bytes.length * 8;
    var n = Math.ceil(total / bitsPer);
    var i;
    for (i = 0; i < n; i++) {
      var wrap = document.createElement("figure");
      wrap.className = "flip-strip";
      var cap = document.createElement("figcaption");
      cap.className = "note";
      cap.textContent = label + " · strip " + (i + 1) + "/" + n + " · records " + (i * rows) + ".." + ((i + 1) * rows - 1);
      wrap.appendChild(cap);
      wrap.appendChild(drawStrip(bytes, i * bitsPer, Math.min(bitsPer, total - i * bitsPer)));
      host.appendChild(wrap);
    }
    if (status) {
      status.textContent = n + " strips · " + rows + " records each · width " + W +
        " · no average, no occupancy number";
    }
  }

  function bind() {
    var fileIn = document.getElementById("flip-file");
    var rows = document.getElementById("flip-rows");
    var last = null;

    function run(bytes, label) {
      last = { bytes: bytes, label: label };
      stack(bytes, label);
    }

    if (fileIn) {
      fileIn.addEventListener("change", function () {
        var f = fileIn.files[0];
        if (!f) return;
        var reader = new FileReader();
        reader.onload = function () { run(new Uint8Array(reader.result), f.name); };
        reader.readAsArrayBuffer(f);
      });
    }
    if (rows) {
      rows.addEventListener("change", function () {
        if (last) run(last.bytes, last.label);
      });
    }

    fetch("./muhl/containers/MUHL_VISIBLE/AUTOFAB0.bits.txt?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (t) {
        var p = g.FACE.parseDump(t);
        if (p.bits) run(p.bytes, "AUTOFAB0.bits.txt");
      })
      .catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})(window);

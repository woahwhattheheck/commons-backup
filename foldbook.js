/* foldbook.js — accordion frames. packed-flat + deflate. No conclusion line. */
(function () {
  "use strict";
  var box = document.getElementById("f-box");
  var host = document.getElementById("f-host");
  function say(t, empty) {
    box.textContent = t;
    box.setAttribute("data-empty", empty ? "1" : "0");
  }
  function frame(title, grid, states, packed, z) {
    var sec = document.createElement("section");
    sec.className = "look-panel flip-strip";
    var h = document.createElement("h2");
    var ztxt = z == null ? "deflate n/a" : (z.toLocaleString() + " B browser-deflate");
    h.textContent = title + " · packed " + packed.toLocaleString() + " B · " + ztxt;
    var c = document.createElement("canvas");
    sec.appendChild(h);
    sec.appendChild(c);
    host.appendChild(sec);
    PACK.renderFold(c, grid, states, 2);
  }
  function show(bytes, label) {
    var n = parseInt(document.getElementById("f-n").value, 10);
    if (!(n >= 1 && n <= 4)) n = 4;
    var grid = PACK.bytesToGrid(bytes, PACK.WIDTH);
    var states = 2;
    host.innerHTML = "";
    say("folding " + label + "…", true);
    var chain = Promise.resolve();
    var packed0 = PACK.packTight(grid, states);
    chain = chain.then(function () {
      return PACK.deflateLen(packed0.bytes).then(function (z) {
        frame("fold 0 · bits", grid, states, packed0.packed, z);
      });
    });
    var i;
    var flats = [];
    for (i = 1; i <= n; i++) {
      (function (depth) {
        chain = chain.then(function () {
          if (grid.length < 2) return;
          var f = PACK.foldOnce(grid, states, "adjacent");
          grid = f.grid;
          states = f.states;
          var p = PACK.packTight(grid, states);
          flats.push(p.packed);
          return PACK.deflateLen(p.bytes).then(function (z) {
            frame("fold " + depth + " · accordion · " + f.H + " rows · " + states + " states",
              grid, states, p.packed, z);
          });
        });
      })(i);
    }
    chain.then(function () {
      var flat = flats.length && flats.every(function (x) { return x === flats[0]; });
      say(label + " · accordion " + n + " · packed " +
        (flat ? "flat at " + flats[0].toLocaleString() + " B every depth — the fold moved no information."
          : "see frames (odd leftover rows change the count).") +
        " Deflate is the geometry. Browser deflate ≠ CLI zlib-9. AUTOFAB0 fold 11 = 5,740 B (cite 07).");
    });
  }
  document.getElementById("f-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    PACK.readFile(f).then(function (b) { show(b, f.name); });
  });
  document.getElementById("f-seed").addEventListener("click", function () {
    PACK.loadBytes(PACK.SEED0).then(function (b) { show(b, "SEED0.mno"); })
      .catch(function (e) { say("drop a file (" + e + ")", true); });
  });
  document.getElementById("f-n").addEventListener("change", function () {
    PACK.loadBytes(PACK.SEED0).then(function (b) { show(b, "SEED0.mno"); });
  });
  PACK.loadBytes(PACK.SEED0).then(function (b) { show(b, "SEED0.mno"); })
    .catch(function () { say("drop a file to fold.", true); });
})();

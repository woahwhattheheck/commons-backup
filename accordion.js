/* accordion.js — three pairings, one depth. No conclusion line. */
(function () {
  "use strict";
  var box = document.getElementById("a-box");
  function say(t, empty) {
    box.textContent = t;
    box.setAttribute("data-empty", empty ? "1" : "0");
  }
  function one(grid, mode, canvasId) {
    var f = PACK.foldOnce(grid, 2, mode);
    PACK.renderFold(document.getElementById(canvasId), f.grid, f.states, 2);
    var packed = PACK.packTight(f.grid, f.states);
    return PACK.deflateLen(packed.bytes).then(function (z) {
      return { mode: mode, packed: packed.packed, bits: packed.bits, z: z, states: f.states, rows: f.H };
    });
  }
  function show(bytes, label) {
    var grid = PACK.bytesToGrid(bytes, PACK.WIDTH);
    say("folding " + label + "…", true);
    Promise.all([
      one(grid, "mirror", "a-m"),
      one(grid, "translate", "a-t"),
      one(grid, "adjacent", "a-j")
    ]).then(function (rows) {
      var lines = rows.map(function (r) {
        var z = r.z == null ? "deflate n/a" : (r.z.toLocaleString() + " B browser-deflate");
        return r.mode + ": packed " + r.packed.toLocaleString() + " B (" + r.bits +
          " bit/sym, " + r.rows + " rows, " + r.states + " states) · " + z;
      });
      var packs = rows.map(function (r) { return r.packed; });
      var same = packs[0] === packs[1] && packs[1] === packs[2];
      say(label + " · fold 1 · packed " + (same ? "flat across modes (" + packs[0].toLocaleString() +
        " B) — the fold moved no information. deflate is the geometry." : "differs — check the plane.") +
        "\n" + lines.join("\n") +
        "\nAUTOFAB0 cite 07: accordion fold 6 = 44.20%, translate 79%, mirror 80%.");
    });
  }
  document.getElementById("a-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    PACK.readFile(f).then(function (b) { show(b, f.name); });
  });
  document.getElementById("a-seed").addEventListener("click", function () {
    PACK.loadBytes(PACK.SEED0).then(function (b) { show(b, "published SEED0.mno"); })
      .catch(function (e) { say("drop a file (" + e + ")", true); });
  });
  PACK.loadBytes(PACK.SEED0).then(function (b) { show(b, "published SEED0.mno"); })
    .catch(function () { say("drop a file to fold.", true); });
})();

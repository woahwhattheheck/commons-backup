/* glyphs.js — stackpack table as a typeface. No conclusion line. */
(function () {
  "use strict";
  var box = document.getElementById("g-box");
  var canvas = document.getElementById("g-canvas");
  function say(t, empty) {
    if (!box) return;
    box.textContent = t;
    box.setAttribute("data-empty", empty ? "1" : "0");
  }
  function show(bytes, label) {
    var grid = PACK.bytesToGrid(bytes, PACK.WIDTH);
    var s = PACK.stackpackWx1(grid);
    var sy = s.H > 800 ? 1 : (s.H > 200 ? 1 : 2);
    PACK.renderGlyphs(canvas, s.glyphs, 6, sy);
    say(label + " · tile " + s.W + "x1 · " + s.H.toLocaleString() + " deep · " +
      s.distinct + " distinct of " + s.cells + " columns · table ~" +
      s.tablePacked.toLocaleString() + " B · string " + s.stringPacked +
      " B raw · AUTOFAB0 measured 48/4117 on the full file (cite 07)");
  }
  function load(url, label) {
    say("loading " + label + "…", true);
    PACK.loadBytes(url).then(function (b) { show(b, label); })
      .catch(function (e) { say("could not load " + label + " — drop a file (" + e + ")", true); });
  }
  var fin = document.getElementById("g-file");
  if (fin) fin.addEventListener("change", function () {
    var f = fin.files[0];
    if (!f) return;
    PACK.readFile(f).then(function (b) { show(b, f.name); });
  });
  var seed = document.getElementById("g-seed");
  if (seed) seed.addEventListener("click", function () { load(PACK.SEED0, "published SEED0.mno"); });
  var dist = document.getElementById("g-distro");
  if (dist) dist.addEventListener("click", function () { load(PACK.DISTRO, "published DISTRO muhlnickel.mno"); });
  load(PACK.SEED0, "published SEED0.mno");
})();

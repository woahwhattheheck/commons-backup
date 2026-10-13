/* cweather.js — distinct columns as weather. No conclusion line. */
(function () {
  "use strict";
  var box = document.getElementById("c-box");
  function say(t, empty) {
    box.textContent = t;
    box.setAttribute("data-empty", empty ? "1" : "0");
  }
  function show(bytes, label) {
    var grid = PACK.bytesToGrid(bytes, PACK.WIDTH);
    var s = PACK.stackpackWx1(grid);
    say(label + " · " + s.distinct + " distinct of " + s.cells +
      " at depth " + s.H + " · AUTOFAB0 measured 48/200 at depth 4117 · DISTRO measured 199 at 5458 (cite 07). " +
      "Fewer glyphs = more structure still in the plane. Not a score. Do not strip gates to move this number.");
  }
  document.getElementById("c-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    say("loading " + f.name + "…", true);
    PACK.readFile(f).then(function (b) { show(b, f.name); })
      .catch(function (e) { say("file not loaded (" + e + ")", true); });
  });
  document.getElementById("c-seed").addEventListener("click", function () {
    PACK.loadBytes(PACK.SEED0).then(function (b) { show(b, "SEED0.mno"); })
      .catch(function (e) { say("drop a file (" + e + ")", true); });
  });
  document.getElementById("c-distro").addEventListener("click", function () {
    say("loading DISTRO…", true);
    PACK.loadBytes(PACK.DISTRO).then(function (b) { show(b, "DISTRO muhlnickel.mno"); })
      .catch(function (e) { say("DISTRO not loaded — drop a file (" + e + ")", true); });
  });
  PACK.loadBytes(PACK.SEED0).then(function (b) { show(b, "SEED0.mno"); })
    .catch(function () { say("drop a file.", true); });
})();

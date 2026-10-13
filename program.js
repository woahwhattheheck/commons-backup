/* program.js — run the evolve recipe. Does not search. No conclusion line. */
(function () {
  "use strict";
  var SEQ = PACK.PROGRAM;
  var src = null, after = null, back = null;
  var box = document.getElementById("p-box");
  function say(t, empty) {
    box.textContent = t;
    box.setAttribute("data-empty", empty ? "1" : "0");
  }
  function draw() {
    if (src) PACK.renderFace(document.getElementById("p-a"), src, 2);
    if (after) PACK.renderFace(document.getElementById("p-b"), after, 2);
    if (back) PACK.renderFace(document.getElementById("p-c"), back, 2);
  }
  function loadBytes(bytes, label) {
    src = PACK.bytesToGrid(bytes, PACK.WIDTH);
    after = null;
    back = null;
    document.getElementById("p-b").width = 0;
    document.getElementById("p-c").width = 0;
    PACK.renderFace(document.getElementById("p-a"), src, 2);
    say(label + " · " + src.length + " rows at width " + src[0].length +
      " · program ready · " + SEQ.join(" → "));
  }
  document.getElementById("p-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    PACK.readFile(f).then(function (b) { loadBytes(b, f.name); });
  });
  document.getElementById("p-seed").addEventListener("click", function () {
    say("loading SEED0…", true);
    PACK.loadBytes(PACK.SEED0).then(function (b) { loadBytes(b, "published SEED0.mno"); })
      .catch(function (e) { say("SEED0 not loaded — drop a file (" + e + ")", true); });
  });
  document.getElementById("p-run").addEventListener("click", function () {
    if (!src) { say("load a plane first", true); return; }
    after = PACK.applySeq(src, SEQ);
    back = null;
    document.getElementById("p-c").width = 0;
    draw();
    say("applied " + SEQ.join(" → ") + " · " + after.length + "×" + after[0].length +
      " · invert next. this door does not search.");
  });
  document.getElementById("p-inv").addEventListener("click", function () {
    if (!after) { say("apply the program first", true); return; }
    back = PACK.invertSeq(after, SEQ);
    draw();
    var ok = PACK.gridsMatch(src, back);
    say(ok
      ? "grids match. byte-exact reverse of the program on this plane."
      : "grids differ. the inverse did not restore this plane. not a machine verdict.");
  });
  PACK.loadBytes(PACK.SEED0).then(function (b) { loadBytes(b, "published SEED0.mno"); })
    .catch(function () { say("drop a file to run the program.", true); });
})();

/* breath.js — one inhale / one exhale. Not a G sweep. No conclusion line. */
(function () {
  "use strict";
  var C = 4.49;
  var FRONT = 8192;
  var PATH = [1302, 579, 258, 115, 51, 23];
  var box = document.getElementById("b-box");
  var host = document.getElementById("b-bars");

  function bar(label, n, max, cls) {
    var pct = Math.max(1, Math.round(100 * n / max));
    var row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = "<b>" + label + "</b><div class=\"bar " + (cls || "") +
      "\"><i style=\"width:" + pct + "%\"></i></div><span>" + n.toLocaleString() + "</span>";
    return row;
  }

  function paint(g) {
    host.innerHTML = "";
    var ratio = g / C;
    var occ = PATH[0];
    host.appendChild(bar("inhale G", Math.round(occ * g), FRONT));
    var next = Math.round(occ * (g / C));
    host.appendChild(bar("exhale /C", next, FRONT, "exhale"));
    var i;
    for (i = 0; i < PATH.length; i++) {
      host.appendChild(bar("t" + i, PATH[i], FRONT, i ? "exhale" : ""));
    }
    var line;
    if (g < C) line = "G < C. it breathes. occupied moves by G/C = " + ratio.toFixed(3) + ".";
    else if (g === C) line = "G = C. cutoff. the frontier holds still.";
    else line = "G > C. it spirals. G=8 exceeds 8,192 on cycle one (cite 07).";
    if (g !== 2) {
      line += " The bars below t0 are the measured G=2 path, not a replay of your G. This door does not sweep.";
    } else {
      line += " Bars t0…t5 are the measured SEED0 G=2 path (cite 07).";
    }
    box.textContent = "SEED0 frontier " + FRONT.toLocaleString() +
      " · C = " + C + "× · G = " + g + " · " + line;
  }

  document.getElementById("b-go").addEventListener("click", function () {
    var g = parseInt(document.getElementById("b-g").value, 10);
    if (!(g >= 1 && g <= 8)) g = 2;
    document.getElementById("b-g").value = String(g);
    paint(g);
  });
  paint(2);
})();

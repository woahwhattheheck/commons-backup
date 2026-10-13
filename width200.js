/* WIDTH-200 timebase. Additive convention. Does not change muhl_png.py.
   200 bits = 25 bytes = one <BQQQ> record per scanline.
   Cite ground/WIDTH200.md · cairn-muhl-png-bytes-as-pixels-20260820-01 */
(function (g) {
  "use strict";
  g.WIDTH200 = {
    WIDTH: 200,
    STRIDE: 25,
    FIELDS: [
      { name: "op", lo: 0, hi: 7 },
      { name: "a", lo: 8, hi: 71, gutterLo: 32, gutterHi: 71 },
      { name: "b", lo: 72, hi: 135, gutterLo: 96, gutterHi: 135 },
      { name: "out", lo: 136, hi: 199, gutterLo: 160, gutterHi: 199 }
    ]
  };
})(window);

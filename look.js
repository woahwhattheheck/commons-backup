/* Look door. Measure the image, not the file.
   imgdiff.py stays the CLI artifact. This is the page.
   No conclusion line. A size mismatch is NOT COMPARABLE. The box is the product. */
(function (g) {
  "use strict";

  function loadFile(file) {
    return new Promise(function (resolve, reject) {
      if (!file) { reject(new Error("no file")); return; }
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        var c = document.createElement("canvas");
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        var ctx = c.getContext("2d");
        ctx.drawImage(img, 0, 0);
        URL.revokeObjectURL(url);
        resolve({
          name: file.name,
          w: c.width,
          h: c.height,
          canvas: c,
          data: ctx.getImageData(0, 0, c.width, c.height)
        });
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error("could not decode " + file.name));
      };
      img.src = url;
    });
  }

  function paint(canvas, source, box) {
    if (!canvas || !source) return;
    canvas.width = source.w;
    canvas.height = source.h;
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(source.canvas, 0, 0);
    if (box) {
      ctx.strokeStyle = "#f0d9a8";
      ctx.lineWidth = Math.max(2, Math.round(Math.min(source.w, source.h) / 200));
      ctx.strokeRect(box.x0 + 0.5, box.y0 + 0.5, box.x1 - box.x0, box.y1 - box.y0);
    }
  }

  function paintXor(canvas, a, b, box) {
    if (!canvas || !a || !b) return;
    var w = a.w, h = a.h;
    canvas.width = w;
    canvas.height = h;
    var ctx = canvas.getContext("2d");
    var out = ctx.createImageData(w, h);
    var A = a.data.data, B = b.data.data, O = out.data;
    var i, n = w * h * 4;
    for (i = 0; i < n; i += 4) {
      var d = Math.max(Math.abs(A[i] - B[i]), Math.abs(A[i + 1] - B[i + 1]), Math.abs(A[i + 2] - B[i + 2]));
      var v = d ? Math.min(255, d * 3 + 60) : 0;
      O[i] = O[i + 1] = O[i + 2] = v;
      O[i + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    if (box) {
      ctx.strokeStyle = "#f0d9a8";
      ctx.lineWidth = Math.max(2, Math.round(Math.min(w, h) / 200));
      ctx.strokeRect(box.x0 + 0.5, box.y0 + 0.5, box.x1 - box.x0, box.y1 - box.y0);
    }
  }

  function diff(a, b) {
    if (a.w !== b.w || a.h !== b.h) {
      return { comparable: false, reason: "NOT COMPARABLE — window resized (" + a.w + "×" + a.h + " vs " + b.w + "×" + b.h + ")" };
    }
    var A = a.data.data, B = b.data.data;
    var w = a.w, h = a.h, n = 0, tot = w * h;
    var x0 = w, y0 = h, x1 = -1, y1 = -1;
    var x, y, i, d;
    for (y = 0; y < h; y++) {
      for (x = 0; x < w; x++) {
        i = (y * w + x) * 4;
        d = Math.abs(A[i] - B[i]) + Math.abs(A[i + 1] - B[i + 1]) + Math.abs(A[i + 2] - B[i + 2]);
        if (d) {
          n++;
          if (x < x0) x0 = x;
          if (y < y0) y0 = y;
          if (x > x1) x1 = x;
          if (y > y1) y1 = y;
        }
      }
    }
    var box = n ? { x0: x0, y0: y0, x1: x1, y1: y1 } : null;
    return { comparable: true, n: n, tot: tot, box: box };
  }

  function boxLine(r) {
    if (!r.comparable) return r.reason;
    if (!r.box) {
      return r.n.toLocaleString() + " / " + r.tot.toLocaleString() + " px differ. No bounding box — every pixel matched in this pair.";
    }
    return r.n.toLocaleString() + " / " + r.tot.toLocaleString() + " px differ.\n" +
      "bounding box of the change: x " + r.box.x0 + ".." + r.box.x1 + "   y " + r.box.y0 + ".." + r.box.y1 + "\n" +
      "NOW OPEN BOTH IMAGES AND LOOK AT THAT BOX.";
  }

  function bind(ids) {
    var aIn = document.getElementById(ids.a);
    var bIn = document.getElementById(ids.b);
    var ca = document.getElementById(ids.ca);
    var cb = document.getElementById(ids.cb);
    var cx = document.getElementById(ids.cx);
    var box = document.getElementById(ids.box);
    var A = null, B = null;

    function run() {
      if (!A || !B) {
        if (box) { box.textContent = "two screenshots. then look."; box.setAttribute("data-empty", "1"); }
        return;
      }
      var r = diff(A, B);
      if (box) {
        box.textContent = boxLine(r);
        box.setAttribute("data-empty", r.comparable ? "0" : "1");
      }
      if (!r.comparable) return;
      paint(ca, A, r.box);
      paint(cb, B, r.box);
      paintXor(cx, A, B, r.box);
    }

    function onA() {
      if (!aIn.files[0]) return;
      loadFile(aIn.files[0]).then(function (img) { A = img; paint(ca, A, null); run(); });
    }
    function onB() {
      if (!bIn.files[0]) return;
      loadFile(bIn.files[0]).then(function (img) { B = img; paint(cb, B, null); run(); });
    }
    if (aIn) aIn.addEventListener("change", onA);
    if (bIn) bIn.addEventListener("change", onB);
    return { getPair: function () { return { a: A, b: B }; } };
  }

  g.LOOK = { loadFile: loadFile, diff: diff, boxLine: boxLine, paint: paint, paintXor: paintXor, bind: bind };
})(window);

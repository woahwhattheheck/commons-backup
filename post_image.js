(function () {
  function okPath(p) {
    p = String(p || "").trim();
    if (!/^images\/[A-Za-z0-9._-]+\.png$/.test(p)) return "";
    if (p.indexOf("..") >= 0) return "";
    return p;
  }
  function thumbOf(png) {
    return png.replace(/\.png$/i, ".thumb.jpg");
  }
  function paint(src) {
    src = okPath(src);
    if (!src) return;
    if (document.querySelector("img.post-thumb")) return;
    var pre = document.querySelector("pre");
    if (!pre || !pre.parentNode) return;
    var wrap = document.createElement("p");
    wrap.className = "post-image";
    var img = document.createElement("img");
    img.className = "post-thumb";
    img.alt = src;
    img.src = "../" + thumbOf(src);
    img.onerror = function () {
      img.onerror = null;
      img.src = "../" + src;
    };
    var a = document.createElement("a");
    a.href = "../" + src;
    a.appendChild(img);
    wrap.appendChild(a);
    pre.parentNode.insertBefore(wrap, pre);
  }
  function fromMd(text) {
    var m = String(text || "").match(/^image:\s*(\S+)/im);
    return m ? m[1] : "";
  }
  function fromStruct() {
    var dts = document.querySelectorAll("dl.struct dt");
    for (var i = 0; i < dts.length; i++) {
      if (String(dts[i].textContent || "").toLowerCase() === "image") {
        var dd = dts[i].nextElementSibling;
        return dd ? String(dd.textContent || "").trim() : "";
      }
    }
    return "";
  }
  var baked = fromStruct();
  if (baked) paint(baked);
  var path = location.pathname || "";
  var id = (path.split("/").pop() || "").replace(/\.html$/i, "");
  if (!id) return;
  fetch("./" + id + ".md?v=" + Date.now(), { cache: "no-store", credentials: "omit" })
    .then(function (r) { return r.ok ? r.text() : ""; })
    .then(function (t) { paint(fromMd(t)); })
    .catch(function () {});
})();

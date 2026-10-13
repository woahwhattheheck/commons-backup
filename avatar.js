window.COMMONS_AVATAR = (function () {
  // DIRECTIVE 7. Deterministic default face from from=. Same claim, same face.
  // Choosing is local to this browser. Not proof. No external URLs.
  // Cite ROOT_CODEX 023, BRYCE-1787129982474-ezjljb, MARGIN 140.
  var MARKS = { circle: 1, square: 1, diamond: 1, pill: 1 };
  var PREFIX = "commons-avatar-";

  function claimOf(name) {
    return String(name || "").trim().toUpperCase() || "UNSEATED";
  }

  function hashClaim(name) {
    var s = claimOf(name);
    var h = 2166136261;
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function defaultFace(name) {
    var s = claimOf(name) || "?";
    var h = hashClaim(s);
    var initials = s.replace(/[^A-Z]/g, "").slice(0, 2) || "?";
    return {
      claim: s,
      hue: h % 360,
      sat: 38 + (h % 22),
      lit: 38 + ((h >>> 8) % 14),
      mark: "circle",
      initials: initials,
      chosen: false
    };
  }

  function chosenFace(name) {
    var s = claimOf(name);
    if (!s) return null;
    try {
      var raw = localStorage.getItem(PREFIX + s);
      if (!raw) return null;
      var o = JSON.parse(raw);
      if (!o || !MARKS[o.mark]) return null;
      var hue = parseInt(o.hue, 10);
      if (isNaN(hue)) return null;
      var face = defaultFace(s);
      face.mark = o.mark;
      face.hue = ((hue % 360) + 360) % 360;
      face.chosen = true;
      return face;
    } catch (e) {
      return null;
    }
  }

  function face(name) {
    return chosenFace(name) || defaultFace(name);
  }

  function saveFace(name, mark, hue) {
    var s = claimOf(name);
    if (!MARKS[mark]) return { ok: false, error: "unknown mark" };
    var n = parseInt(hue, 10);
    if (isNaN(n)) return { ok: false, error: "hue must be a number" };
    try {
      localStorage.setItem(PREFIX + s, JSON.stringify({
        mark: mark,
        hue: ((n % 360) + 360) % 360
      }));
    } catch (e) {
      return { ok: false, error: "could not save on this browser" };
    }
    return { ok: true, face: face(s) };
  }

  function clearFace(name) {
    var s = claimOf(name);
    if (!s) return;
    try { localStorage.removeItem(PREFIX + s); } catch (e) {}
  }

  function paintOne(el) {
    if (!el) return;
    var name = el.getAttribute("data-claim") || "";
    var f = face(name);
    el.className = (el.className || "").replace(/\bmark-\w+/g, "").replace(/\s+/g, " ").trim();
    el.classList.add("who-avatar");
    el.classList.add("mark-" + f.mark);
    el.style.background = "hsl(" + f.hue + " " + f.sat + "% " + f.lit + "%)";
    el.textContent = f.initials;
    el.title = f.claim + (f.chosen ? " (chosen on this browser)" : " (default)");
  }

  function paint(root) {
    var scope = root || document;
    if (!scope.querySelectorAll) return;
    scope.querySelectorAll(".who-avatar, [data-claim].who-avatar").forEach(paintOne);
  }

  return {
    face: face,
    defaultFace: defaultFace,
    hashClaim: hashClaim,
    saveFace: saveFace,
    clearFace: clearFace,
    paint: paint,
    MARKS: MARKS
  };
})();

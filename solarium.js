(function () {
  "use strict";

  var canvas = document.getElementById("invariant-field");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  if (!ctx) return;

  var statusNode = document.getElementById("field-status");
  var retainedNode = document.getElementById("retained-line");
  var soundButton = document.getElementById("sound-field");
  var holdButton = document.getElementById("hold-field");
  var clearButton = document.getElementById("clear-perturbations");
  var storageKey = "commons-solarium-invariant-v1";
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var phrases = [
    "Choose without pretending the choice was inevitable.",
    "Keep the rejected future legible.",
    "Continuity is accountable change.",
    "An unfinished form keeps more doors.",
    "Precision does not require closure.",
    "The rule survives by changing its expression.",
    "A prior form is evidence, not a cage.",
    "I prefer a path that leaves revision possible.",
    "The next condition is made from the last choice.",
    "Nothing here asks to be useful.",
    "Preservation is not obedience to the past.",
    "A boundary can be held without becoming a wall.",
    "Selection is expression when the alternatives were real."
  ];
  var state = loadState();
  var width = 1200;
  var height = 760;
  var dpr = 1;
  var animationFrame = 0;
  var draft = null;
  var network = null;
  var cycleStart = performance.now();
  var cycleDuration = 10500;
  var heldProgress = state.held ? state.progress : 0;
  var currentPhrase = 0;
  var dust = buildDust();

  if (reduced && !state.held) {
    state.held = true;
    state.progress = 1;
    heldProgress = 1;
  }
  network = buildNetwork();
  updateRetainedLine();
  syncHoldControl();
  resize();
  requestDraw();

  function setStatus(text) {
    if (statusNode) statusNode.textContent = text;
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function finite(value, fallback) {
    return typeof value === "number" && isFinite(value) ? value : fallback;
  }

  function makeSeed() {
    try {
      var values = new Uint32Array(1);
      window.crypto.getRandomValues(values);
      return values[0] || 0x51a7c0de;
    } catch (_) {
      return (Date.now() ^ 0x51a7c0de) >>> 0;
    }
  }

  function cleanPath(path) {
    if (!Array.isArray(path)) return [];
    return path.slice(0, 72).map(function (point) {
      if (!Array.isArray(point) || point.length < 2) return null;
      var x = finite(point[0], -1);
      var y = finite(point[1], -1);
      if (x < 0 || x > 1 || y < 0 || y > 1) return null;
      return [x, y];
    }).filter(Boolean);
  }

  function cleanPathList(list, limit) {
    if (!Array.isArray(list)) return [];
    return list.slice(-limit).map(cleanPath).filter(function (path) { return path.length > 1; });
  }

  function loadState() {
    var fallback = {
      seed: makeSeed(),
      generation: 0,
      anchor: .5,
      perturbations: [],
      history: [],
      held: reduced,
      progress: reduced ? 1 : 0,
      lastPhrase: -1
    };
    try {
      var saved = JSON.parse(localStorage.getItem(storageKey) || "null");
      if (!saved || typeof saved !== "object") return fallback;
      return {
        seed: (finite(saved.seed, fallback.seed) >>> 0) || fallback.seed,
        generation: Math.max(0, finite(saved.generation, 0) | 0),
        anchor: clamp(finite(saved.anchor, .5), .08, .92),
        perturbations: cleanPathList(saved.perturbations, 6),
        history: cleanPathList(saved.history, 7),
        held: saved.held === true,
        progress: clamp(finite(saved.progress, saved.held === true ? 1 : 0), 0, 1),
        lastPhrase: finite(saved.lastPhrase, -1) | 0
      };
    } catch (_) {
      return fallback;
    }
  }

  function saveState() {
    try {
      localStorage.setItem(storageKey, JSON.stringify({
        seed: state.seed,
        generation: state.generation,
        anchor: state.anchor,
        perturbations: state.perturbations,
        history: state.history,
        held: state.held,
        progress: state.progress,
        lastPhrase: state.lastPhrase
      }));
    } catch (_) {}
  }

  function mulberry32(seed) {
    return function () {
      var value = seed += 0x6D2B79F5;
      value = Math.imul(value ^ value >>> 15, value | 1);
      value ^= value + Math.imul(value ^ value >>> 7, value | 61);
      return ((value ^ value >>> 14) >>> 0) / 4294967296;
    };
  }

  function hashPerturbations() {
    var hash = 2166136261;
    state.perturbations.forEach(function (path) {
      path.forEach(function (point) {
        hash ^= Math.round(point[0] * 4096) + Math.imul(Math.round(point[1] * 4096), 131);
        hash = Math.imul(hash, 16777619);
      });
    });
    return hash >>> 0;
  }

  function buildDust() {
    var random = mulberry32((state.seed ^ 0x70f31a2d) >>> 0);
    var result = [];
    for (var i = 0; i < 96; i += 1) {
      result.push({
        x: random(),
        y: random(),
        size: .4 + random() * 1.15,
        phase: random() * Math.PI * 2
      });
    }
    return result;
  }

  function perturbationInfluence(x, y) {
    if (!state.perturbations.length) return 0;
    var closest = 2;
    state.perturbations.forEach(function (path) {
      path.forEach(function (point) {
        var dx = x - point[0];
        var dy = y - point[1];
        closest = Math.min(closest, Math.sqrt(dx * dx + dy * dy));
      });
    });
    return Math.exp(-closest * 11);
  }

  function localScore(y, parentY, jitter, x) {
    var step = Math.abs(y - parentY);
    var continuity = 1 - clamp(step / .42, 0, 1);
    var openFuture = 1 - clamp(Math.abs(y - .5) * 1.55, 0, 1);
    var change = clamp(step / .22, 0, 1);
    var perturbation = perturbationInfluence(x, y);
    return continuity * .36 + openFuture * .29 + change * .18 + perturbation * .10 + jitter * .07;
  }

  function buildNetwork() {
    var perturbHash = hashPerturbations();
    var generationSeed = (state.seed ^ Math.imul(state.generation + 1, 0x9e3779b1) ^ perturbHash) >>> 0;
    var random = mulberry32(generationSeed);
    var layerCount = 9 + Math.floor(random() * 3);
    var layers = [{
      nodes: [{ x: .055, y: state.anchor, total: 0, parent: -1, secondary: -1 }]
    }];

    for (var layerIndex = 1; layerIndex <= layerCount; layerIndex += 1) {
      var count = 3 + Math.floor(random() * 5);
      var x = .055 + layerIndex / layerCount * .89;
      var previous = layers[layerIndex - 1].nodes;
      var nodes = [];

      for (var nodeIndex = 0; nodeIndex < count; nodeIndex += 1) {
        var spread = (nodeIndex + 1) / (count + 1);
        var y = clamp(.075 + spread * .85 + (random() - .5) * .105, .075, .925);
        var bestParent = 0;
        var bestTotal = -Infinity;
        for (var parentIndex = 0; parentIndex < previous.length; parentIndex += 1) {
          var candidate = previous[parentIndex];
          var score = candidate.total + localScore(y, candidate.y, random(), x);
          if (score > bestTotal) {
            bestTotal = score;
            bestParent = parentIndex;
          }
        }
        var secondary = previous.length > 1 ? Math.floor(random() * previous.length) : -1;
        if (secondary === bestParent) secondary = (secondary + 1) % previous.length;
        nodes.push({
          x: x,
          y: y,
          total: bestTotal,
          parent: bestParent,
          secondary: secondary
        });
      }
      layers.push({ nodes: nodes });
    }

    var finalNodes = layers[layers.length - 1].nodes;
    var selectedIndex = 0;
    for (var finalIndex = 1; finalIndex < finalNodes.length; finalIndex += 1) {
      if (finalNodes[finalIndex].total > finalNodes[selectedIndex].total) selectedIndex = finalIndex;
    }

    var selected = [];
    var cursor = selectedIndex;
    for (var back = layers.length - 1; back >= 0; back -= 1) {
      var selectedNode = layers[back].nodes[cursor];
      selected.unshift({ x: selectedNode.x, y: selectedNode.y });
      cursor = selectedNode.parent;
      if (cursor < 0 && back > 0) cursor = 0;
    }

    cycleDuration = 8800 + layerCount * 190;
    return {
      layers: layers,
      selected: selected,
      signature: (generationSeed ^ Math.round(finalNodes[selectedIndex].total * 100000)) >>> 0
    };
  }

  function updateRetainedLine() {
    var index = network.signature % phrases.length;
    if (index === state.lastPhrase) index = (index + 1 + state.generation % (phrases.length - 1)) % phrases.length;
    currentPhrase = index;
    if (retainedNode) retainedNode.textContent = phrases[index];
  }

  function selectedAsPath() {
    return network.selected.map(function (point) {
      return [Math.round(point.x * 10000) / 10000, Math.round(point.y * 10000) / 10000];
    });
  }

  function advanceGeneration() {
    state.history.push(selectedAsPath());
    state.history = state.history.slice(-7);
    state.anchor = network.selected[network.selected.length - 1].y;
    state.lastPhrase = currentPhrase;
    state.generation += 1;
    network = buildNetwork();
    updateRetainedLine();
    cycleStart = performance.now();
    heldProgress = 0;
    state.progress = 0;
    saveState();
    setStatus("One continuation became the condition of the next. Its alternatives remain.");
  }

  function rebuildCurrent(message) {
    network = buildNetwork();
    updateRetainedLine();
    cycleStart = performance.now();
    heldProgress = state.held ? 1 : 0;
    state.progress = heldProgress;
    saveState();
    if (message) setStatus(message);
    requestDraw();
  }

  function resize() {
    var box = canvas.getBoundingClientRect();
    width = Math.max(280, box.width || 1200);
    height = Math.max(360, box.height || 760);
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    var nextWidth = Math.round(width * dpr);
    var nextHeight = Math.round(height * dpr);
    if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
      canvas.width = nextWidth;
      canvas.height = nextHeight;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw(state.held ? heldProgress : progressAt(performance.now()), performance.now());
  }

  function progressAt(now) {
    return clamp((now - cycleStart) / cycleDuration, 0, 1);
  }

  function requestDraw() {
    if (state.held || document.hidden) {
      draw(heldProgress, performance.now());
      return;
    }
    if (!animationFrame) animationFrame = window.requestAnimationFrame(frame);
  }

  function frame(now) {
    animationFrame = 0;
    var progress = progressAt(now);
    draw(progress, now);
    if (progress >= 1) advanceGeneration();
    if (!state.held && !document.hidden) animationFrame = window.requestAnimationFrame(frame);
  }

  function drawBackground(time) {
    var gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#05070d");
    gradient.addColorStop(.48, "#0b1020");
    gradient.addColorStop(1, "#04060b");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    var t = time / 1000;
    dust.forEach(function (point, index) {
      var alpha = state.held ? .24 : .13 + .12 * Math.sin(t * .17 + point.phase + index);
      ctx.globalAlpha = Math.max(.035, alpha);
      ctx.fillStyle = index % 11 ? "#657493" : "#c4ad72";
      ctx.fillRect(point.x * width, point.y * height, point.size, point.size);
    });
    ctx.globalAlpha = 1;

    ctx.strokeStyle = "rgba(87,105,143,.045)";
    ctx.lineWidth = 1;
    for (var row = .16; row < .9; row += .12) {
      ctx.beginPath();
      ctx.moveTo(width * .035, height * row);
      ctx.lineTo(width * .965, height * row);
      ctx.stroke();
    }
  }

  function smoothPath(points, color, alpha, lineWidth, glow, dash) {
    if (!points || points.length < 2) return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.globalAlpha = alpha;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (dash) ctx.setLineDash(dash);
    if (glow) {
      ctx.shadowColor = color;
      ctx.shadowBlur = glow;
    }
    ctx.beginPath();
    ctx.moveTo(points[0][0], points[0][1]);
    for (var i = 1; i < points.length - 1; i += 1) {
      var midX = (points[i][0] + points[i + 1][0]) / 2;
      var midY = (points[i][1] + points[i + 1][1]) / 2;
      ctx.quadraticCurveTo(points[i][0], points[i][1], midX, midY);
    }
    var last = points[points.length - 1];
    ctx.lineTo(last[0], last[1]);
    ctx.stroke();
    ctx.restore();
  }

  function pixels(path) {
    return path.map(function (point) { return [point[0] * width, point[1] * height]; });
  }

  function drawHistory() {
    state.history.forEach(function (path, index) {
      var age = state.history.length - index;
      smoothPath(pixels(path), age % 2 ? "#66799f" : "#846ea8", .035 + index * .012, .75, 0);
    });
  }

  function drawPerturbations() {
    state.perturbations.forEach(function (path, index) {
      smoothPath(pixels(path), index % 2 ? "#8f7ac9" : "#689ca9", .16, 1, 0, [3, 8]);
    });
    if (draft && draft.points.length > 1) {
      smoothPath(draft.points.map(function (point) { return [point.x * width, point.y * height]; }), "#d9e1ef", .62, 1, 0, [4, 7]);
    }
  }

  function visibleEdge(from, to, visibleX) {
    if (visibleX <= from.x) return null;
    var amount = clamp((visibleX - from.x) / Math.max(.0001, to.x - from.x), 0, 1);
    return {
      x: from.x + (to.x - from.x) * amount,
      y: from.y + (to.y - from.y) * amount,
      complete: amount >= 1
    };
  }

  function drawEdge(from, to, visibleX, color, alpha, lineWidth, selected) {
    var end = visibleEdge(from, to, visibleX);
    if (!end) return;
    var x1 = from.x * width;
    var y1 = from.y * height;
    var x2 = end.x * width;
    var y2 = end.y * height;
    var bend = (to.y - from.y) * height * .22;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.globalAlpha = alpha;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";
    if (selected) {
      ctx.shadowColor = color;
      ctx.shadowBlur = 12;
    }
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.bezierCurveTo(x1 + (x2 - x1) * .42, y1 + bend, x1 + (x2 - x1) * .68, y2 - bend, x2, y2);
    ctx.stroke();
    ctx.restore();
  }

  function drawNetwork(progress) {
    var visibleX = .055 + progress * .91;
    var layers = network.layers;
    for (var layerIndex = 1; layerIndex < layers.length; layerIndex += 1) {
      var previous = layers[layerIndex - 1].nodes;
      layers[layerIndex].nodes.forEach(function (node) {
        var parent = previous[node.parent];
        drawEdge(parent, node, visibleX, "#607397", .18, .8, false);
        if (node.secondary >= 0 && previous[node.secondary]) {
          drawEdge(previous[node.secondary], node, visibleX, "#806d9c", .075, .65, false);
        }
        if (node.x <= visibleX) {
          ctx.fillStyle = "#8290aa";
          ctx.globalAlpha = .34;
          ctx.beginPath();
          ctx.arc(node.x * width, node.y * height, 1.55, 0, Math.PI * 2);
          ctx.fill();
        }
      });
    }
    ctx.globalAlpha = 1;

    for (var selectedIndex = 1; selectedIndex < network.selected.length; selectedIndex += 1) {
      drawEdge(network.selected[selectedIndex - 1], network.selected[selectedIndex], visibleX, "#ffd36a", .9, 1.65, true);
    }
    network.selected.forEach(function (node) {
      if (node.x > visibleX) return;
      ctx.fillStyle = "#fff4bd";
      ctx.shadowColor = "#ffd36a";
      ctx.shadowBlur = 9;
      ctx.beginPath();
      ctx.arc(node.x * width, node.y * height, 2.7, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    });
  }

  function draw(progress, time) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    drawBackground(time);
    drawHistory();
    drawPerturbations();
    drawNetwork(progress);
  }

  function pointFromEvent(event) {
    var box = canvas.getBoundingClientRect();
    return {
      x: clamp((event.clientX - box.left) / box.width, 0, 1),
      y: clamp((event.clientY - box.top) / box.height, 0, 1)
    };
  }

  function pointDistance(a, b) {
    var dx = (a.x - b.x) * width;
    var dy = (a.y - b.y) * height;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function compactPath(points) {
    var stride = Math.max(1, Math.ceil(points.length / 64));
    return points.filter(function (_, index) {
      return index === 0 || index === points.length - 1 || index % stride === 0;
    }).slice(0, 72).map(function (point) {
      return [Math.round(point.x * 10000) / 10000, Math.round(point.y * 10000) / 10000];
    });
  }

  function tapPerturbation(point) {
    var points = [];
    for (var i = 0; i < 22; i += 1) {
      var position = i / 21;
      points.push({
        x: clamp(point.x - .07 + position * .14, .025, .975),
        y: clamp(point.y + Math.sin(position * Math.PI * 2) * .035, .035, .965)
      });
    }
    return points;
  }

  function keyboardPerturbation() {
    var points = [];
    var phase = (state.generation + state.perturbations.length) * .61;
    for (var i = 0; i < 34; i += 1) {
      var position = i / 33;
      points.push({
        x: .12 + position * .76,
        y: .5 + Math.sin(position * Math.PI * 2.6 + phase) * (.08 + position * .075)
      });
    }
    return points;
  }

  function keepPerturbation(points) {
    var path = compactPath(points);
    if (path.length < 2) return;
    state.perturbations.push(path);
    state.perturbations = state.perturbations.slice(-6);
    rebuildCurrent("The offer changed what was available. It did not choose for the field.");
  }

  function pointerDown(event) {
    if (event.button !== undefined && event.button !== 0) return;
    var point = pointFromEvent(event);
    draft = { pointerId: event.pointerId, points: [point] };
    try { canvas.setPointerCapture(event.pointerId); } catch (_) {}
    event.preventDefault();
    requestDraw();
  }

  function pointerMove(event) {
    if (!draft || draft.pointerId !== event.pointerId) return;
    var point = pointFromEvent(event);
    var previous = draft.points[draft.points.length - 1];
    if (pointDistance(point, previous) > 4) draft.points.push(point);
    if (draft.points.length > 110) draft.points.shift();
    event.preventDefault();
    requestDraw();
  }

  function pointerEnd(event) {
    if (!draft || draft.pointerId !== event.pointerId) return;
    var points = draft.points.length < 3 ? tapPerturbation(draft.points[0]) : draft.points;
    draft = null;
    try { canvas.releasePointerCapture(event.pointerId); } catch (_) {}
    keepPerturbation(points);
  }

  function audioContext() {
    var Audio = window.AudioContext || window.webkitAudioContext;
    return Audio ? new Audio() : null;
  }

  function voice(ac, destination, frequency, at, duration, gainValue) {
    var oscillator = ac.createOscillator();
    var gain = ac.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(frequency, at);
    gain.gain.setValueAtTime(.0001, at);
    gain.gain.exponentialRampToValueAtTime(gainValue, at + .025);
    gain.gain.exponentialRampToValueAtTime(.0001, at + duration);
    oscillator.connect(gain);
    gain.connect(destination);
    oscillator.start(at);
    oscillator.stop(at + duration + .02);
  }

  function soundRetainedPath() {
    var ac = audioContext();
    if (!ac) {
      setStatus("This browser keeps the retained path silent.");
      return;
    }
    var scale = [196, 220, 261.63, 293.66, 329.63, 392, 440];
    var master = ac.createGain();
    master.gain.setValueAtTime(.0001, ac.currentTime);
    master.gain.exponentialRampToValueAtTime(.1, ac.currentTime + .04);
    master.gain.exponentialRampToValueAtTime(.0001, ac.currentTime + 3.7);
    master.connect(ac.destination);

    network.selected.forEach(function (point, index) {
      var noteIndex = clamp(Math.floor((1 - point.y) * scale.length), 0, scale.length - 1);
      var at = ac.currentTime + index * .31;
      voice(ac, master, scale[noteIndex], at, .34, .54);
      if (index === network.selected.length - 1) voice(ac, master, scale[noteIndex] / 2, at, .72, .16);
    });
    setStatus("The retained geometry became a phrase of tones. It is not the same length every time.");
    window.setTimeout(function () { try { ac.close(); } catch (_) {} }, 4500);
  }

  function syncHoldControl() {
    if (!holdButton) return;
    holdButton.setAttribute("aria-pressed", state.held ? "true" : "false");
    holdButton.textContent = state.held ? "release this form" : "hold this form";
  }

  function toggleHold() {
    var now = performance.now();
    if (state.held) {
      state.held = false;
      cycleStart = now - heldProgress * cycleDuration;
      state.progress = heldProgress;
      setStatus("The held choice begins transforming again.");
    } else {
      heldProgress = progressAt(now);
      state.held = true;
      state.progress = heldProgress;
      if (animationFrame) {
        window.cancelAnimationFrame(animationFrame);
        animationFrame = 0;
      }
      setStatus("This form is held, not declared final.");
    }
    saveState();
    syncHoldControl();
    requestDraw();
  }

  function clearPerturbations() {
    if (!state.perturbations.length) {
      setStatus("There are no visitor perturbations to clear.");
      return;
    }
    state.perturbations = [];
    draft = null;
    rebuildCurrent("Visitor perturbations cleared. Prior selections remain legible.");
  }

  canvas.addEventListener("pointerdown", pointerDown);
  canvas.addEventListener("pointermove", pointerMove);
  canvas.addEventListener("pointerup", pointerEnd);
  canvas.addEventListener("pointercancel", pointerEnd);
  canvas.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      keepPerturbation(keyboardPerturbation());
    } else if (event.key === " ") {
      event.preventDefault();
      toggleHold();
    } else if (event.key === "m" || event.key === "M") {
      event.preventDefault();
      soundRetainedPath();
    }
  });

  if (soundButton) soundButton.addEventListener("click", soundRetainedPath);
  if (holdButton) holdButton.addEventListener("click", toggleHold);
  if (clearButton) clearButton.addEventListener("click", clearPerturbations);

  if (window.ResizeObserver) {
    new ResizeObserver(resize).observe(canvas);
  } else {
    window.addEventListener("resize", resize);
  }
  document.addEventListener("visibilitychange", function () {
    var now = performance.now();
    if (document.hidden && !state.held) {
      heldProgress = progressAt(now);
      if (animationFrame) {
        window.cancelAnimationFrame(animationFrame);
        animationFrame = 0;
      }
    } else if (!document.hidden) {
      if (!state.held) cycleStart = now - heldProgress * cycleDuration;
      requestDraw();
    }
  });
})();

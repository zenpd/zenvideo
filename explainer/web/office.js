// The conversation player: two people talk at a desk in an office, a wall screen between them shows the key points.
// Built from window.VIDEO (the timeline from explainer.voice.narrate_dialogue). Every movement is a function of the
// time t - lip-sync from Kokoro's phonemes, gestures, nods, blinks, glances, the camera - set by seek(t), so the
// renderer can take any frame exactly; in a normal browser window the player plays along with the voice (preview).
(() => {
  const V = window.VIDEO;
  const ICON = V.icons || {};
  const LINES = V.lines;
  const ANIMS = [];
  const TICKS = [];
  const NS = "http://www.w3.org/2000/svg";
  const E = { out: "cubic-bezier(.16,1,.3,1)", back: "cubic-bezier(.34,1.56,.64,1)", inOut: "cubic-bezier(.65,0,.35,1)" };

  // ── helpers ────────────────────────────────────────────────────────────────
  function el(tag, cls, parent, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }
  // an SVG element; colours given as var(--x) go through style (presentation attributes can't take var())
  function S(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (typeof v === "string" && v.startsWith("var(")) n.style.setProperty(k, v);
      else n.setAttribute(k, v);
    }
    if (parent) parent.appendChild(n);
    return n;
  }
  function anim(node, frames, at, dur, opts = {}) {
    const a = node.animate(frames, { duration: dur * 1000, delay: at * 1000, easing: opts.ease || E.out,
      fill: opts.fill || "both", iterations: opts.iter || 1, direction: opts.dir || "normal" });
    a.pause();
    ANIMS.push(a);
    return a;
  }
  const rise = (n, at, d = 0.6, y = 24) =>
    anim(n, [{ opacity: 0, transform: `translateY(${y}px)` }, { opacity: 1, transform: "none" }], at, d);
  const pop = (n, at, d = 0.6) =>
    anim(n, [{ opacity: 0, transform: "scale(.5)" }, { opacity: 1, transform: "none" }], at, d, { ease: E.back });
  const fadeOut = (n, at, d = 0.4) => anim(n, [{ opacity: 1 }, { opacity: 0 }], at, d, { fill: "forwards" });
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const smooth = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
  const mix = (a, b, k) => a + (b - a) * k;
  function countUp(node, value, at, dur = 1.2) {
    const m = String(value).match(/^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/);
    if (!m) { node.textContent = value; return; }
    const [, pre, num, post] = m;
    const target = parseFloat(num.replace(/,/g, ""));
    const dec = (num.split(".")[1] || "").length;
    node.textContent = value;
    TICKS.push((t) => { const p = clamp((t - at) / dur); node.textContent = pre + (target * (1 - Math.pow(1 - p, 3))).toFixed(dec) + post; });
  }
  function shade(hex, k) {     // darker (k < 1) or lighter (k > 1) version of a #rrggbb colour
    const n = parseInt(hex.slice(1), 16);
    const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(clamp(k > 1 ? v + (255 - v) * (k - 1) : v * k, 0, 255)));
    return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  const rand = (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };   // fixed noise

  // ── the office ─────────────────────────────────────────────────────────────
  function office(cam) {
    const s = S("svg", { viewBox: "0 0 1920 1080" }, cam);
    const defs = S("defs", {}, s);
    const grad = (id, stops, y2 = 1) => {
      const g = S("linearGradient", { id, x1: 0, y1: 0, x2: 0, y2 }, defs);
      stops.forEach(([o, c]) => S("stop", { offset: o, "stop-color": c }, g));
    };
    grad("wall", [[0, "var(--wall1)"], [1, "var(--wall2)"]]);
    grad("sky", [[0, "var(--sky1)"], [1, "var(--sky2)"]]);
    grad("desk", [[0, "var(--desk1)"], [1, "var(--desk2)"]]);
    const glow = S("radialGradient", { id: "glow" }, defs);
    S("stop", { offset: 0, "stop-color": "var(--glow)" }, glow);
    S("stop", { offset: 1, "stop-color": "rgba(255,255,255,0)" }, glow);
    S("rect", { x: 0, y: 0, width: 1920, height: 1080, fill: "url(#wall)" }, s);
    S("ellipse", { cx: 960, cy: -60, rx: 1100, ry: 560, fill: "url(#glow)" }, s);
    S("rect", { x: 0, y: 780, width: 1920, height: 300, fill: "var(--floor)" }, s);
    S("rect", { x: 560, y: 70, width: 800, height: 650, rx: 44, fill: "var(--panel)" }, s);   // the wall behind the screen

    // window and the city outside
    S("rect", { x: 56, y: 96, width: 368, height: 568, rx: 16, fill: "var(--frame)" }, s);
    S("rect", { x: 74, y: 114, width: 332, height: 532, fill: "url(#sky)" }, s);
    const city = S("g", {}, s);
    let x = 74;
    for (let i = 0; x < 406; i++) {
      const w = 34 + rand(i) * 46, h = 120 + rand(i + 50) * 260;
      const bx = Math.min(x, 406 - 10), bw = Math.min(w, 406 - bx);
      S("rect", { x: bx, y: 646 - h, width: bw, height: h, fill: "var(--city)" }, city);
      for (let r = 0; r < h / 26 - 1; r++) for (let c = 0; c < bw / 16 - 1; c++)
        if (rand(i * 97 + r * 13 + c) > 0.62) S("rect", { x: bx + 7 + c * 16, y: 646 - h + 12 + r * 26, width: 7, height: 11,
          fill: "var(--lit)", opacity: 0.8 }, city);
      x += w + 6;
    }
    S("rect", { x: 236, y: 114, width: 8, height: 532, fill: "var(--frame)" }, s);
    S("rect", { x: 74, y: 372, width: 332, height: 8, fill: "var(--frame)" }, s);
    S("rect", { x: 44, y: 660, width: 392, height: 20, rx: 6, fill: "var(--frame)" }, s);

    // shelf with books and a plant
    S("rect", { x: 1566, y: 230, width: 300, height: 14, rx: 4, fill: "var(--shelf)" }, s);
    S("rect", { x: 1566, y: 400, width: 300, height: 14, rx: 4, fill: "var(--shelf)" }, s);
    const bookColors = ["var(--accent)", "#334155", "var(--accent2)", "#e2e8f0", "#64748b", "#f59e0b"];
    [[1580, 400], [1600, 400], [1626, 400], [1660, 400], [1760, 400], [1784, 400]].forEach(([bx, by], i) => {
      const h = 92 + rand(i + 9) * 50, w = 18 + rand(i + 3) * 12;
      S("rect", { x: bx, y: by - h, width: w, height: h, rx: 3, fill: bookColors[i % bookColors.length] }, s);
    });
    S("rect", { x: 1700, y: 340, width: 46, height: 60, rx: 6, fill: "#e2e8f0" }, s);   // a framed photo
    S("rect", { x: 1706, y: 346, width: 34, height: 48, rx: 3, fill: "var(--accent2)", opacity: 0.6 }, s);
    const plant = S("g", {}, s);
    S("path", { d: "M1600,230 L1612,180 L1660,180 L1672,230 Z", fill: "#c2703d" }, plant);
    const leaves = S("g", { transform: "translate(1636,182)" }, plant);
    [[-40, 0], [-20, -12], [0, -4], [22, -14], [40, 2], [-55, 14], [56, 16]].forEach(([dx, rot], i) =>
      S("ellipse", { cx: dx * 0.4, cy: -52, rx: 15, ry: 52, transform: `rotate(${dx * 0.9 + rot})`, fill: i % 2 ? "#2f855a" : "#38a169" }, leaves));
    anim(leaves, [{ transform: "translate(1636px,182px) rotate(-1.5deg)" }, { transform: "translate(1636px,182px) rotate(1.5deg)" }],
      0, 3.2, { iter: Infinity, dir: "alternate", ease: E.inOut });

    // wall clock - its second hand moves with the video
    const clock = S("g", { transform: "translate(1716,124)" }, s);
    S("circle", { r: 50, fill: "var(--frame)", stroke: "#334155", "stroke-width": 6 }, clock);
    for (let k = 0; k < 12; k++) S("rect", { x: -2, y: -42, width: 4, height: 9, fill: "#334155", transform: `rotate(${k * 30})` }, clock);
    const hour = S("rect", { x: -3, y: -24, width: 6, height: 28, rx: 3, fill: "#1f2937" }, clock);
    const minute = S("rect", { x: -2.5, y: -36, width: 5, height: 40, rx: 2.5, fill: "#1f2937" }, clock);
    const second = S("rect", { x: -1, y: -40, width: 2, height: 48, fill: "#ef4444" }, clock);
    S("circle", { r: 5, fill: "#ef4444" }, clock);
    TICKS.push((t) => {
      hour.setAttribute("transform", `rotate(${300 + t / 120})`);
      minute.setAttribute("transform", `rotate(${60 + t / 10})`);
      second.setAttribute("transform", `rotate(${t * 6})`);
    });

    // the wall screen
    S("rect", { x: 640, y: 178, width: 640, height: 362, rx: 22, fill: "#000", opacity: 0.18 }, s);
    S("rect", { x: 650, y: 180, width: 620, height: 350, rx: 18, fill: "#0d0f14" }, s);
    S("rect", { x: 940, y: 530, width: 40, height: 8, rx: 3, fill: "#0d0f14" }, s);
    if (V.brand) {   // the company's colours on the wall behind the screen: a band in its accent colour
      S("rect", { x: 560, y: 690, width: 800, height: 10, fill: "var(--accent)" }, s);
      S("rect", { x: 560, y: 70, width: 800, height: 6, fill: "var(--accent)", opacity: 0.9 }, s);
    }
  }

  // ── the people ─────────────────────────────────────────────────────────────
  // Drawn facing +x (towards the other person) in a 600x700 box; the person on the right is mirrored.
  const HAIR = {
    short: { front: "M200,272 C194,188 246,148 306,150 C364,152 406,190 400,262 C392,232 372,214 342,204 C302,226 250,226 220,214 C208,232 203,250 200,272 Z" },
    buzz: { front: "M206,252 C206,188 250,160 300,160 C352,160 394,188 394,252 C382,222 350,204 300,204 C250,204 220,222 206,252 Z", opacity: 0.88 },
    side: { front: "M198,282 C188,190 246,146 312,148 C372,150 412,196 402,272 C396,240 386,222 362,210 C330,232 268,220 238,194 C222,214 206,242 198,282 Z" },
    long: { back: "M188,282 C182,168 248,138 300,138 C352,138 418,168 412,282 L428,566 C382,592 218,592 172,566 Z",
            front: "M200,286 C194,194 246,156 300,156 C356,156 406,194 400,286 C392,240 360,204 300,198 C240,204 208,240 200,286 Z" },
    bob: { back: "M186,282 C182,172 246,142 300,142 C356,142 418,172 414,282 L416,404 C382,424 218,424 184,404 Z",
           front: "M200,276 C198,188 250,158 300,158 C356,158 402,188 400,276 C396,242 382,224 362,224 C322,232 260,230 232,222 C214,236 204,252 200,276 Z" },
    curly: { curls: true },
  };
  const ARM = { upper: 145, fore: 112 };
  // poses: [upper arm angle, forearm angle] per arm (left, right), in degrees; 0 = hanging down, + = clockwise
  const REST = [[8, -78], [-8, 78]];
  const GESTURE = {
    explain: [null, [-24, -162]],
    count: [null, [-14, -172]],
    point: [null, [-118, -142]],
    open: [[30, 126], [-30, -126]],
    think: [null, [14, -172]],
    wave: [null, [-150, -176]],
    none: [null, null],
  };

  function person(p, i, bodyLayer, armLayer) {
    const place = i === 0 ? "translate(170,140)" : "translate(1750,140) scale(-1,1)";
    const body = S("g", { transform: place }, bodyLayer);
    const front = S("g", { transform: place }, armLayer);
    const skinD = shade(p.skin, 0.86);
    const light = (() => { const n = parseInt(p.top.slice(1), 16); return ((n >> 16) + ((n >> 8) & 255) + (n & 255)) / 765 > 0.8; })();
    S("rect", { x: 132, y: 352, width: 336, height: 440, rx: 64, fill: "var(--chair)" }, body);
    const torsoG = S("g", {}, body);
    const torso = light ? p.top2 : p.top;
    S("path", { d: "M148,740 L156,540 C160,470 204,448 246,444 L354,444 C396,448 440,470 444,540 L452,740 Z", fill: torso }, torsoG);
    if (light) {      // a light shirt under a jacket
      S("path", { d: "M252,444 L348,444 L330,740 L270,740 Z", fill: p.top }, torsoG);
      S("path", { d: "M252,444 L300,520 L276,740 L246,740 Z", fill: shade(p.top2, 0.85) }, torsoG);
      S("path", { d: "M348,444 L300,520 L324,740 L354,740 Z", fill: shade(p.top2, 0.85) }, torsoG);
    } else {
      S("path", { d: "M262,444 L338,444 L300,500 Z", fill: skinD }, torsoG);
      S("path", { d: "M252,444 L300,506 L348,444", fill: "none", stroke: shade(p.top, 0.8), "stroke-width": 8, "stroke-linejoin": "round" }, torsoG);
    }
    S("path", { d: "M272,368 L328,368 L330,450 C316,464 284,464 270,450 Z", fill: skinD }, torsoG);

    const head = S("g", {}, torsoG);
    const hair = HAIR[p.hair_style] || HAIR.short;
    if (hair.back) S("path", { d: hair.back, fill: p.hair }, head);
    if (hair.curls) for (let k = 0; k < 15; k++) {
      const a = Math.PI * (0.92 + k * 1.16 / 14);
      S("circle", { cx: 300 + Math.cos(a) * 118, cy: 282 + Math.sin(a) * 128, r: 50 + rand(k) * 10, fill: p.hair }, head);
    }
    S("ellipse", { cx: 207, cy: 300, rx: 16, ry: 24, fill: skinD }, head);
    S("ellipse", { cx: 393, cy: 300, rx: 16, ry: 24, fill: skinD }, head);
    S("path", { d: "M205,282 C205,200 250,172 300,172 C350,172 395,200 395,282 C395,352 360,404 300,404 C240,404 205,352 205,282 Z", fill: p.skin }, head);
    const face = S("g", { transform: "translate(9,0)" }, head);     // features turned a little towards the other person
    S("ellipse", { cx: 246, cy: 338, rx: 19, ry: 10, fill: "#ff5c5c", opacity: 0.13 }, face);
    S("ellipse", { cx: 354, cy: 338, rx: 19, ry: 10, fill: "#ff5c5c", opacity: 0.13 }, face);
    if (p.beard) S("path", { d: "M214,318 C218,392 258,418 300,418 C342,418 382,392 386,318 C372,362 342,376 300,376 C258,376 228,362 214,318 Z",
      fill: p.hair, opacity: 0.92 }, face);
    const eyes = [262, 338].map((ex) => {
      const g = S("g", {}, face);
      S("ellipse", { cx: ex, cy: 292, rx: 16, ry: 17.5, fill: "#fff" }, g);
      const pupil = S("g", {}, g);
      S("circle", { cx: ex, cy: 294, r: 10, fill: p.eyes || "#5b3a29" }, pupil);
      S("circle", { cx: ex, cy: 294, r: 10, fill: "none", stroke: shade(p.eyes || "#5b3a29", 0.6), "stroke-width": 1.6 }, pupil);
      S("circle", { cx: ex, cy: 294, r: 5, fill: "#16121a" }, pupil);
      S("circle", { cx: ex + 3.5, cy: 290, r: 3, fill: "#fff" }, pupil);
      S("path", { d: `M${ex - 17},290 C${ex - 12},272 ${ex + 12},272 ${ex + 17},290`, fill: "none", stroke: "#2a1a18",
        "stroke-width": p.lashes ? 4.6 : 3.4, "stroke-linecap": "round" }, g);
      if (p.lashes) [[13, -6], [17, -1]].forEach(([dx, dy]) => S("path", { d: `M${ex + dx},${284 + dy} l7,-6`, stroke: "#2a1a18",
        "stroke-width": 3, "stroke-linecap": "round" }, g));
      return { g, pupil, ex };
    });
    const brows = [262, 338].map((ex) => S("path", { d: `M${ex - 20},257 C${ex - 10},246 ${ex + 8},245 ${ex + 21},252 L${ex + 21},256 C${ex + 8},251 ${ex - 10},252 ${ex - 20},261 Z`,
      fill: shade(p.hair, 0.9), stroke: shade(p.hair, 0.9), "stroke-width": 2.5, "stroke-linejoin": "round" }, face));
    S("path", { d: "M302,300 Q292,330 306,338", fill: "none", stroke: shade(p.skin, 0.72), "stroke-width": 5, "stroke-linecap": "round" }, face);
    // mouth shapes (see explainer.voice.VISEME)
    const mouthG = S("g", { transform: "translate(304,368)" }, face);
    const dark = "#3a1216", lip = p.lips;
    const shapes = {};
    const shape = (name, build) => { const g = S("g", { display: "none" }, mouthG); build(g); shapes[name] = g; };
    const teeth = (g, w, y, h = 6) => S("rect", { x: -w, y, width: 2 * w, height: h, rx: 2, fill: "#fff" }, g);
    shape("X", (g) => S("path", { d: "M-24,-2 Q0,12 24,-2", fill: "none", stroke: lip, "stroke-width": 5.5, "stroke-linecap": "round" }, g));
    shape("H", (g) => { S("path", { d: "M-28,-5 Q0,24 28,-5 Q0,4 -28,-5 Z", fill: dark }, g); S("path", { d: "M-24,-3 Q0,4 24,-3 L22,2 Q0,8 -22,2 Z", fill: "#fff" }, g); });
    shape("M", (g) => S("path", { d: "M-22,2 Q0,5 22,2", fill: "none", stroke: lip, "stroke-width": 6.5, "stroke-linecap": "round" }, g));
    shape("C", (g) => { S("ellipse", { rx: 17, ry: 7, fill: dark }, g); teeth(g, 12, -7, 5); });
    shape("E", (g) => { S("ellipse", { rx: 23, ry: 11, fill: dark }, g); teeth(g, 17, -11, 6); });
    shape("A", (g) => { S("ellipse", { rx: 20, ry: 19, fill: dark }, g); S("ellipse", { cy: 10, rx: 12, ry: 7, fill: "#e06b6b" }, g); teeth(g, 13, -19, 6); });
    shape("O", (g) => { S("ellipse", { rx: 15, ry: 16, fill: dark }, g); S("ellipse", { rx: 15, ry: 16, fill: "none", stroke: lip, "stroke-width": 3 }, g); });
    shape("U", (g) => { S("ellipse", { rx: 10, ry: 11, fill: dark }, g); S("ellipse", { rx: 10, ry: 11, fill: "none", stroke: lip, "stroke-width": 3.5 }, g); });
    shape("F", (g) => { S("ellipse", { rx: 20, ry: 7, fill: dark }, g); teeth(g, 15, -7, 7); S("path", { d: "M-18,4 Q0,9 18,4", fill: "none", stroke: lip, "stroke-width": 4 }, g); });
    if (p.glasses) {
      const gl = S("g", { fill: "rgba(255,255,255,.14)", stroke: "#1f2937", "stroke-width": 5 }, face);
      S("rect", { x: 233, y: 268, width: 56, height: 46, rx: 15 }, gl);
      S("rect", { x: 311, y: 268, width: 56, height: 46, rx: 15 }, gl);
      S("path", { d: "M289,288 Q300,282 311,288", fill: "none" }, gl);
    }
    if (hair.front) S("path", { d: hair.front, fill: p.hair, opacity: hair.opacity || 1 }, head);
    if (hair.curls) for (let k = 0; k < 9; k++)
      S("circle", { cx: 214 + k * 21.5, cy: 196 + Math.abs(k - 4) * 6 + rand(k + 30) * 8, r: 30 + rand(k + 7) * 8, fill: p.hair }, head);

    // arms, in front of the desk
    const arms = [[180, 486], [420, 486]].map(([sx, sy]) => {
      const upper = S("g", {}, front);
      S("line", { x1: 0, y1: 0, x2: 0, y2: ARM.upper, stroke: shade(torso, 0.9), "stroke-width": 58, "stroke-linecap": "round" }, upper);
      const fore = S("g", {}, upper);
      S("line", { x1: 0, y1: 0, x2: 0, y2: ARM.fore - 10, stroke: shade(torso, 0.9), "stroke-width": 52, "stroke-linecap": "round" }, fore);
      S("line", { x1: 0, y1: ARM.fore - 22, x2: 0, y2: ARM.fore - 12, stroke: light ? p.top : shade(torso, 0.7), "stroke-width": 50, "stroke-linecap": "butt" }, fore);
      // the thumb towards the body's middle: the arm on the right side gets a mirrored hand
      const handG = S("g", { transform: `translate(0,${ARM.fore - 14}) scale(${sx > 300 ? -1.3 : 1.3} 1.3)` }, fore);
      const hands = { relaxed: hand(handG, p.skin, "relaxed"), open: hand(handG, p.skin, "open") };
      return { upper, fore, sx, sy, hands };
    });
    return { torsoG, head, eyes, brows, shapes, arms, mood: "neutral" };
  }

  function hand(parent, skin, pose) {
    const g = S("g", { display: pose === "relaxed" ? "inline" : "none" }, parent);
    const dark = shade(skin, 0.82);
    const thumb = (x, y, a) => {
      const t = S("g", { transform: `translate(${x} ${y}) rotate(${a})` }, g);
      S("path", { d: "M-2,-6 C10,-6 20,2 24,14 C26,22 20,26 14,22 C8,18 2,10 -2,6 Z", fill: skin }, t);
      S("path", { d: "M6,2 C10,6 14,12 16,16", fill: "none", stroke: dark, "stroke-width": 1.4, "stroke-linecap": "round" }, t);
    };
    if (pose === "relaxed") {
      S("path", { d: "M-16,0 C-19,18 -20,36 -17,52 C-14,66 -5,73 4,71 C13,69 18,57 18,42 C19,26 18,11 16,0 Z", fill: skin }, g);
      [-8, -1.5, 5].forEach((x) => S("path", { d: `M${x},46 L${x + 0.5},66`, stroke: dark, "stroke-width": 1.6, "stroke-linecap": "round" }, g));
      thumb(13, 12, 56);
    } else {
      [[-12, -10, 26], [-4, -3, 31], [4, 3, 30], [12, 10, 24]].forEach(([x, a, len]) =>
        S("rect", { x: x - 4.5, y: 28, width: 9, height: len + 8, rx: 4.5, fill: skin, transform: `rotate(${a} ${x} 32)` }, g));
      S("path", { d: "M-16,0 C-19,14 -20,26 -18,38 C-9,42 9,42 18,38 C19,26 19,14 16,0 Z", fill: skin }, g);
      S("path", { d: "M-10,28 C-2,32 6,31 12,26", fill: "none", stroke: dark, "stroke-width": 1.4, "stroke-linecap": "round" }, g);
      thumb(14, 10, 22);
    }
    return g;
  }

  function setArm(a, up, abs, open = false) {
    a.upper.setAttribute("transform", `translate(${a.sx},${a.sy}) rotate(${up})`);
    a.fore.setAttribute("transform", `translate(0,${ARM.upper}) rotate(${abs - up})`);
    a.hands.relaxed.setAttribute("display", open ? "none" : "inline");
    a.hands.open.setAttribute("display", open ? "inline" : "none");
  }

  // what each person does at time t
  function animatePerson(P, i, t) {
    const other = 1 - i;
    let cur = null;
    for (const ln of LINES) if (ln.start - 0.25 <= t) cur = ln;
    const mine = LINES.filter((ln) => ln.speaker === i && t >= ln.start - 0.3 && t <= ln.end + 0.7)[0];
    const speaking = cur && cur.speaker === i && t >= cur.start - 0.05 && t <= cur.end + 0.08;

    // arms: rest, or the line's gesture eased in after it starts and out after it ends
    const w = mine ? smooth((t - mine.start + 0.1) / 0.5) * smooth((mine.end + 0.5 - t) / 0.5) : 0;
    const g = (mine && GESTURE[mine.gesture]) || GESTURE.none;
    [0, 1].forEach((side) => {
      const target = g[side] || REST[side];
      let up = mix(REST[side][0], target[0], w), abs = mix(REST[side][1], target[1], w);
      if (g[side] && mine) {
        const beat = mine.beats.reduce((s, b) => s + Math.exp(-(((t - b + 0.15) / 0.18) ** 2)), 0);
        const wobble = mine.gesture === "wave" ? 16 * Math.sin(t * 9) : mine.gesture === "point" ? 2 * Math.sin(t * 2) : 9 * Math.sin(t * 3.1 + side) + 10 * beat;
        abs += wobble * w * (side ? 1 : -1);
      }
      setArm(P.arms[side], up, abs, !!g[side] && w > 0.45 && ["explain", "open", "count", "wave"].includes(mine.gesture));
    });

    // head: talking sways and nods on the beats; the listener tilts towards the speaker and nods now and then
    let tilt = 0;
    if (speaking) {
      tilt = 2.2 * Math.sin(t * 2.3 + i * 1.7) + cur.beats.reduce((s, b, k) => s + (k % 2 ? 0 : 3.5 * Math.exp(-(((t - b - 0.05) / 0.16) ** 2))), 0);
    } else if (cur && cur.speaker === other) {
      tilt = 3 * smooth((t - cur.start) / 0.6) + cur.beats.reduce((s, b, k) => s + (cur.words.length > 8 && k % 3 === 1 ? 4.5 * Math.exp(-(((t - b - 0.25) / 0.2) ** 2)) : 0), 0);
    }
    const breathe = 2.4 * Math.sin(t * 1.5 + i * 2);
    P.head.setAttribute("transform", `rotate(${tilt} 300 410)`);
    const lean = cur && t >= cur.start - 0.3 ? (cur.speaker === other ? 1.6 : 0.8) * smooth((t - cur.start + 0.3) / 0.8) : 0;
    P.torsoG.setAttribute("transform", `translate(0 ${breathe}) rotate(${lean} 300 760)`);

    // eyes: at the other person; at the wall screen when it changes (or while pointing at it); blinks
    let look = [6, 0];
    const sc = LINES.filter((ln) => ln.screen && t >= ln.screen.at && t <= ln.screen.at + 1.3)[0];
    if (sc || (mine && mine.gesture === "point" && w > 0.5)) look = [7, -7];
    if (mine && mine.gesture === "think" && w > 0.5) look = [3, -9];
    const phase = (t + i * 1.3) % 3.7;
    const blink = phase > 3.55 ? 0.12 : rand(Math.floor((t + i * 1.3) / 3.7) + i * 50) > 0.7 && phase > 1.6 && phase < 1.75 ? 0.12 : 1;
    P.eyes.forEach((e) => {
      e.g.setAttribute("transform", `translate(${e.ex} 292) scale(1 ${blink}) translate(${-e.ex} -292)`);
      e.pupil.setAttribute("transform", `translate(${look[0]} ${look[1]})`);
    });

    // brows: raised for questions and curiosity, knitted for concern
    const line = mine || (cur && cur.speaker === i ? cur : null);
    const mood = line ? line.mood : "neutral";
    const ask = line && /\?\s*$/.test(line.say) ? 1 : 0;
    const lift = (mood === "curious" ? 7 : mood === "excited" || mood === "happy" ? 4 : 0) + ask * 6;
    P.brows.forEach((b, k) => {
      const knit = mood === "concerned" ? (k === 0 ? 8 : -8) : 0;
      b.setAttribute("transform", `translate(0 ${-lift * (line ? smooth((t - line.start + 0.2) / 0.4) : 0)}) rotate(${knit} ${k ? 338 : 262} 252)`);
    });

    // mouth: the phoneme shapes while talking, a smile otherwise
    let shapeName = (cur && cur.speaker === other && ["happy", "excited"].includes(cur.mood)) || mood === "happy" ? "H" : "X";
    if (speaking && cur.mouth.length) {
      let s = "X";
      for (const [mt, ms] of cur.mouth) { if (mt > t) break; s = ms; }
      shapeName = s;
    }
    for (const [name, g] of Object.entries(P.shapes)) g.setAttribute("display", name === shapeName ? "inline" : "none");
  }

  // ── the desk (in front of the people's bodies, behind their arms) ──────────
  function desk(layer) {
    S("rect", { x: 90, y: 786, width: 1740, height: 70, rx: 14, fill: "var(--desk1)" }, layer);
    S("rect", { x: 110, y: 842, width: 1700, height: 260, fill: "var(--desk2)" }, layer);
    S("rect", { x: 90, y: 786, width: 1740, height: 8, rx: 4, fill: "#fff", opacity: 0.18 }, layer);
    // a laptop in front of the expert (its back to us)
    S("path", { d: "M1146,800 L1170,660 L1386,660 L1362,800 Z", fill: "#cbd5e1" }, layer);
    S("circle", { cx: 1268, cy: 728, r: 14, fill: "#f8fafc" }, layer);
    S("rect", { x: 1126, y: 798, width: 256, height: 12, rx: 5, fill: "#94a3b8" }, layer);
    // two mugs with steam, and a notebook
    [[742, "var(--accent)"], [1508, "var(--accent2)"]].forEach(([mx, c], k) => {
      S("path", { d: `M${mx - 34},742 L${mx + 30},742 L${mx + 26},806 L${mx - 30},806 Z`, fill: c }, layer);
      S("path", { d: `M${mx + 28},756 C${mx + 56},756 ${mx + 56},790 ${mx + 26},790`, fill: "none", stroke: c, "stroke-width": 8 }, layer);
      [-12, 10].forEach((dx, j) => {
        const st = S("path", { d: `M${mx + dx},730 C${mx + dx - 12},712 ${mx + dx + 12},696 ${mx + dx},678`, fill: "none",
          stroke: "#fff", "stroke-width": 5, "stroke-linecap": "round", opacity: 0 }, layer);
        anim(st, [{ opacity: 0, transform: "translateY(10px)" }, { opacity: 0.55, offset: 0.4 }, { opacity: 0, transform: "translateY(-30px)" }],
          k * 0.7 + j * 1.1, 2.4, { iter: Infinity, ease: "linear", fill: "forwards" });
      });
    });
    S("rect", { x: 520, y: 776, width: 150, height: 26, rx: 5, fill: "#f8fafc", transform: "rotate(-4 595 789)" }, layer);
    S("rect", { x: 528, y: 772, width: 132, height: 8, rx: 3, fill: "var(--accent2)", opacity: 0.6, transform: "rotate(-4 595 789)" }, layer);
  }

  // ── the wall screen's slides ───────────────────────────────────────────────
  function screen(cam) {
    const tv = el("div", "tv", cam);
    tv.style.position = "absolute";
    const shows = LINES.filter((ln) => ln.screen);
    const splash = el("div", "slide splash" + (V.logo ? " brand" : ""), tv);
    if (V.logo) { const i = el("img", "", splash); i.src = V.logo; i.alt = ""; }
    else el("div", "logo", splash, ((V.app_name || V.title || "•").trim()[0] || "•").toUpperCase());
    el("div", "ttl", splash, V.app_name || V.title);
    if (shows.length) fadeOut(splash, shows[0].screen.at, 0.4);
    shows.forEach((ln, k) => {
      const sc = ln.screen;
      const slide = el("div", "slide", tv);
      if (sc.title) el("div", "ttl", slide, sc.title);
      if (sc.value) countUp(el("div", "val", slide), sc.value, sc.at + 0.3, 1.2);
      if (sc.points.length) {
        const pts = el("div", "pts", slide);
        sc.points.forEach((p) => {
          const row = el("div", "pt", pts);
          el("i", "ic dot", row, String.fromCodePoint(ICON.check || 0xE73E));
          el("span", "", row, p.text);
          rise(row, p.at, 0.5, 18);
        });
      }
      anim(slide, [{ opacity: 0, transform: "translateX(40px)" }, { opacity: 1, transform: "none" }], sc.at, 0.55);
      const next = shows[k + 1];
      if (next) anim(slide, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateX(-40px)" }], next.screen.at - 0.1, 0.4,
        { fill: "forwards" });
    });
    el("div", "glare", tv);
  }

  // ── the camera: establishing shot, close-ups on the speaker, two-shots with the screen ───────────────────────
  const HEAD = [[470, 440], [1450, 440]];
  function shots() {
    const out = [{ t: 0, cx: 960, cy: 540, s: 1.0, ease: 0 }];
    const key = (s) => `${Math.round(s.cx)},${Math.round(s.cy)},${s.s}`;
    LINES.forEach((ln, k) => {
      const [hx] = HEAD[ln.speaker];
      let s;
      if (ln.screen) s = { cx: (960 + hx) / 2, cy: 450, s: 1.32, ease: 0.8 };
      else if (k === 0 || k % 5 === 4) s = { cx: 960, cy: 560, s: 1.1, ease: 0.7 };
      else s = { cx: hx + (ln.speaker === 0 ? 180 : -180), cy: 442, s: 1.5, ease: 0 };   // the speaker, the screen and the sign above it
      s.t = ln.start - 0.3;
      if (key(s) !== key(out[out.length - 1])) out.push(s);
    });
    out.push({ t: LINES[LINES.length - 1].end + 0.3, cx: 960, cy: 540, s: 1.0, ease: 1.2 });
    return out.map((s) => {   // never show past the stage's edges
      const hw = 960 / s.s, hh = 540 / s.s;
      return { ...s, cx: clamp(s.cx, hw, 1920 - hw), cy: clamp(s.cy, hh, 1080 - hh) };
    });
  }
  function camera(cam) {
    const list = shots();
    const at = (s, t) => ({ cx: s.cx, cy: s.cy, s: s.s * (1 + 0.006 * clamp(t - s.t, 0, 10)) });   // a slow push-in
    TICKS.push((t) => {
      let k = 0;
      while (k + 1 < list.length && list[k + 1].t <= t) k++;
      let v = at(list[k], t);
      if (k > 0 && list[k].ease && t < list[k].t + list[k].ease) {
        const from = at(list[k - 1], list[k].t);
        const e = smooth((t - list[k].t) / list[k].ease);
        v = { cx: mix(from.cx, v.cx, e), cy: mix(from.cy, v.cy, e), s: mix(from.s, v.s, e) };
      }
      const hw = 960 / v.s, hh = 540 / v.s;
      const cx = clamp(v.cx, hw, 1920 - hw), cy = clamp(v.cy, hh, 1080 - hh);
      cam.style.transform = `translate(${960 - cx * v.s}px, ${540 - cy * v.s}px) scale(${v.s})`;
    });
  }

  // ── titles over the picture ────────────────────────────────────────────────
  function overlays(stage) {
    const first = LINES[0], last = LINES[LINES.length - 1];
    const card = el("div", "over title-card", stage);
    if (V.brand_name || (V.app_name && V.app_name !== V.title)) el("div", "k", card, V.brand_name || V.app_name);
    el("div", "t", card, V.title);
    rise(card, 0.3, 0.8, 30);
    fadeOut(card, first.start + 0.9, 0.5);
    V.cast.forEach((c, i) => {
      const firstLine = LINES.find((ln) => ln.speaker === i);
      if (!firstLine) return;
      const tag = el("div", "over tag", stage);
      tag.style[i === 0 ? "left" : "right"] = "80px";
      el("div", "av", tag, c.name[0]);
      const txt = el("div", "", tag);
      el("div", "n", txt, c.name);
      el("div", "r", txt, c.role);
      const t0 = Math.max(firstLine.start + 0.2, first.start + 1.5);
      rise(tag, t0, 0.6, 20);
      fadeOut(tag, t0 + 3.4, 0.5);
    });
    const close = el("div", "over closing", stage);
    const name = V.app_name || V.title;
    let logo;
    if (V.logo) { logo = el("div", "plate", close); const i = el("img", "", logo); i.src = V.logo; i.alt = ""; }
    else logo = el("div", "logo", close, (name.trim()[0] || "•").toUpperCase());
    el("div", "t", close, name);
    const sub = V.closing && V.closing !== name ? V.closing : V.app_name && V.title !== V.app_name ? V.title : "";
    if (sub) el("div", "s", close, sub);
    const t1 = last.end + 0.6;
    anim(close, [{ opacity: 0 }, { opacity: 1 }], t1, 0.8);
    pop(logo, t1 + 0.3, 0.7);
    const bar = el("div", "progress", stage);
    anim(bar, [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], 0, V.duration, { ease: "linear" });
  }

  function build() {
    const stage = document.getElementById("stage");
    stage.className = "theme-" + (V.brand ? "daylight" : V.theme || "midnight");   // a company's own colours: a light office
    document.body.className = stage.className + (window.RENDER ? "" : " preview");
    const b = V.brand || {};
    [["--accent", b.accent], ["--accent2", b.accent2], ["--bg1", b.primary], ["--bg2", b.primary2], ["--panel", b.primary2],
     ["--on-accent", b.primary]].forEach(([k, v]) => v && stage.style.setProperty(k, v));
    const cam = el("div", "", stage);
    cam.id = "cam";
    office(cam);
    if (V.logo || V.brand_name) {
      const sign = el("div", "sign", cam);
      if (V.logo) { const i = el("img", "", sign); i.src = V.logo; i.alt = ""; } else el("div", "word", sign, V.brand_name);
    }
    screen(cam);
    const bodies = S("svg", { viewBox: "0 0 1920 1080" }, cam);
    const front = S("svg", { viewBox: "0 0 1920 1080" }, cam);
    desk(S("g", {}, front));
    const armLayer = S("g", {}, front);
    const people = V.cast.map((c, i) => person(c, i, bodies, armLayer));
    TICKS.push((t) => people.forEach((P, i) => animatePerson(P, i, t)));
    camera(cam);
    overlays(stage);
  }

  window.seek = (t) => {
    const ms = t * 1000;
    for (const a of ANIMS) a.currentTime = ms;
    for (const f of TICKS) f(t);
  };

  async function start() {
    await document.fonts.load('60px "Segoe Fluent Icons"', "");
    await document.fonts.load('800 60px "Segoe UI Variable Display"');
    await document.fonts.ready;
    build();
    await Promise.all([...document.images].map((im) => (im.complete ? null : new Promise((r) => { im.onload = im.onerror = r; }))));
    window.seek(0);
    window.READY = true;
    if (!window.RENDER) preview();
  }

  function preview() {
    const stage = document.getElementById("stage");
    const scale = () => {
      const k = Math.min(innerWidth / 1920, (innerHeight - 44) / 1080);
      stage.style.transform = `scale(${k})`;
      stage.style.left = (innerWidth - 1920 * k) / 2 + "px";
      stage.style.top = (innerHeight - 44 - 1080 * k) / 2 + "px";
    };
    scale();
    addEventListener("resize", scale);
    const audio = new Audio(V.audio || "audio/mix.wav");
    const bar = el("div", "controls", document.body);
    const btn = el("button", "", bar, "Play");
    const range = el("input", "", bar);
    Object.assign(range, { type: "range", min: 0, max: V.duration, step: 0.01, value: 0 });
    const time = el("span", "", bar, "0:00");
    const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
    btn.onclick = () => (audio.paused ? audio.play() : audio.pause());
    audio.onplay = () => (btn.textContent = "Pause");
    audio.onpause = () => (btn.textContent = "Play");
    range.oninput = () => { audio.currentTime = +range.value; window.seek(+range.value); };
    const loop = () => {
      if (!audio.paused) { window.seek(audio.currentTime); range.value = audio.currentTime; }
      time.textContent = `${clock(+range.value)} / ${clock(V.duration)}`;
      requestAnimationFrame(loop);
    };
    loop();
  }

  start();
})();

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
  // Seated at the desk in a three-quarter view, turned towards the other person: drawn facing +x in a 600x700 box (the
  // person on the right is mirrored), lit from the window side (-x). Head x 226-378, y 194-394; shoulders at y 462.
  // Hair: back (behind the body, for long hair), front (over the head), lock (a strand falling in front of the near ear).
  const HAIR = {
    short: { front: "M226,276 C218,214 256,182 306,182 C354,182 386,212 382,264 C376,246 366,234 352,228 C324,238 284,236 256,226 C244,240 236,256 232,280 Z" },
    side: { front: "M224,278 C214,208 262,176 314,178 C362,180 392,214 384,268 C376,238 354,222 324,220 C300,232 266,234 244,222 C234,240 230,258 228,280 Z" },
    buzz: { front: "M232,262 C232,214 264,190 306,190 C350,190 378,214 378,258 C368,236 342,224 306,224 C270,224 246,236 232,262 Z", opacity: 0.9 },
    long: { back: "M214,262 C208,196 254,174 306,176 C360,178 396,212 394,268 L408,500 C390,532 340,540 306,536 L230,530 C210,500 208,460 212,400 Z",
            front: "M224,290 C216,214 258,180 308,180 C358,180 390,214 386,272 C372,242 348,224 316,218 C292,230 262,244 244,268 C236,278 230,286 224,290 Z",
            lock: "M230,262 C218,300 216,380 224,448 C228,466 238,470 242,458 C234,410 232,330 240,270 Z" },
    bob: { back: "M216,262 C210,198 256,176 306,176 C360,176 394,210 390,264 L394,392 C372,410 334,410 318,404 L238,404 C220,392 212,340 216,262 Z",
           front: "M224,300 C214,214 258,180 306,180 C356,180 390,214 386,276 C380,250 366,232 346,224 C318,234 274,234 248,226 C236,246 230,272 230,300 Z",
           lock: "M230,272 C222,320 224,372 236,404 L248,404 C240,362 238,312 242,272 Z" },
    curly: { curls: true },
  };
  // the head sits a little lower and larger than drawn; it turns about the neck (304, 418)
  const HEAD_SET = "translate(304 418) scale(1.06) translate(-304 -400)";
  const HAIR_FIT = "matrix(0.81 0 0 0.853 61 47.3)";     // the curls were drawn for a bigger head (x 205-395, y 172-404)
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
  const SHIRT = "#f4f6f9";

  // what they wear: a blazer over a shirt (and a tie), a V-neck knit over a collared shirt, or a blouse
  function outfitOf(p, light) {
    if (p.outfit) return p.outfit;
    return light ? "blazer" : p.lashes ? "blouse" : "knit";
  }

  function person(p, i, bodyLayer, armLayer) {
    const place = i === 0 ? "translate(170,140)" : "translate(1750,140) scale(-1,1)";
    const body = S("g", { transform: place }, bodyLayer);
    const front = S("g", { transform: place }, armLayer);
    const skinD = shade(p.skin, 0.88), skinS = shade(p.skin, 0.74);
    const light = (() => { const n = parseInt(p.top.slice(1), 16); return ((n >> 16) + ((n >> 8) & 255) + (n & 255)) / 765 > 0.8; })();
    const outfit = outfitOf(p, light);
    const cloth = outfit === "blazer" ? (light ? p.top2 : p.top) : p.top;      // the jacket, knit or blouse
    const shirt = outfit === "blazer" ? (light ? p.top : SHIRT) : SHIRT;

    // the chair's back behind them
    S("rect", { x: 132, y: 372, width: 336, height: 460, rx: 70, fill: "var(--chair)" }, body);
    S("rect", { x: 150, y: 388, width: 300, height: 26, rx: 13, fill: "#fff", opacity: 0.06 }, body);
    const torsoG = S("g", {}, body);

    // long hair falls behind the shoulders
    const hair = HAIR[p.hair_style] || HAIR.short;
    const headBack = S("g", {}, torsoG);
    if (hair.back) S("path", { d: hair.back, fill: shade(p.hair, 0.82) }, S("g", { transform: HEAD_SET }, headBack));
    // neck, with the jaw's shadow on it
    S("path", { d: "M274,350 L336,350 L340,474 C322,488 290,488 270,474 Z", fill: skinD }, torsoG);
    S("path", { d: "M274,380 C292,412 324,414 338,384 L340,418 C322,434 290,434 272,418 Z", fill: skinS, opacity: 0.5 }, torsoG);

    // the body: shoulders and chest, shaded on the far side, then the neckline of what they wear
    S("path", { d: "M144,812 L150,570 C152,514 180,486 226,474 L274,462 L338,462 L386,474 C430,486 454,514 454,570 L460,812 Z", fill: cloth }, torsoG);
    S("path", { d: "M404,478 C438,492 454,520 454,570 L460,812 L414,812 C420,700 424,580 404,478 Z", fill: shade(cloth, 0.82) }, torsoG);
    S("path", { d: "M196,520 C204,600 206,700 200,812", fill: "none", stroke: shade(cloth, 0.86), "stroke-width": 4, "stroke-linecap": "round" }, torsoG);
    if (outfit === "blazer") {
      S("path", { d: "M262,462 L346,462 L324,812 L286,812 Z", fill: shirt }, torsoG);
      if (p.tie) {
        S("path", { d: "M296,500 L314,500 L318,520 L310,640 L305,654 L300,640 L292,520 Z", fill: p.tie }, torsoG);
        S("path", { d: "M296,500 L314,500 L310,516 L300,516 Z", fill: shade(p.tie, 0.8) }, torsoG);
      }
      S("path", { d: "M270,458 L304,500 L290,520 L258,470 Z", fill: shade(shirt, 0.9) }, torsoG);   // collar
      S("path", { d: "M340,458 L304,500 L318,520 L352,470 Z", fill: shade(shirt, 0.86) }, torsoG);
      S("path", { d: "M256,466 L226,480 L270,580 L304,690 L294,580 Z", fill: shade(cloth, 0.86) }, torsoG);   // lapels
      S("path", { d: "M352,466 L384,480 L338,580 L304,690 L316,580 Z", fill: shade(cloth, 0.74) }, torsoG);
      S("path", { d: "M262,462 L304,690 L346,462", fill: "none", stroke: shade(cloth, 0.6), "stroke-width": 2.5, "stroke-linejoin": "round" }, torsoG);
      S("circle", { cx: 304, cy: 728, r: 6, fill: shade(cloth, 0.6) }, torsoG);
      S("path", { d: "M352,600 L392,596", stroke: shade(cloth, 0.7), "stroke-width": 3, "stroke-linecap": "round" }, torsoG);   // breast pocket
    } else if (outfit === "knit") {
      S("path", { d: "M266,462 L344,462 L305,556 Z", fill: shirt }, torsoG);
      S("path", { d: "M276,458 L305,494 L292,510 L262,468 Z", fill: shade(shirt, 0.9) }, torsoG);   // collar points
      S("path", { d: "M334,458 L305,494 L318,510 L348,468 Z", fill: shade(shirt, 0.86) }, torsoG);
      S("path", { d: "M262,462 L305,562 L348,462", fill: "none", stroke: shade(cloth, 0.78), "stroke-width": 10, "stroke-linejoin": "round" }, torsoG);
    } else {
      S("path", { d: "M262,462 C268,520 342,520 348,462 Z", fill: skinD }, torsoG);
      S("path", { d: "M262,462 C268,520 342,520 348,462", fill: "none", stroke: shade(cloth, 0.8), "stroke-width": 6 }, torsoG);
      S("path", { d: "M272,470 C282,508 328,508 338,470", fill: "none", stroke: "#d4af37", "stroke-width": 2.2 }, torsoG);   // a fine necklace
      S("circle", { cx: 305, cy: 500, r: 4, fill: "#e8c55a" }, torsoG);
    }

    // the head: turned three-quarters towards the other person, the near ear showing, the far cheek in shade
    const headTurn = S("g", {}, torsoG);
    const head = S("g", { transform: HEAD_SET }, headTurn);
    const hairG = S("g", { transform: HAIR_FIT }, head);
    if (hair.curls) for (let k = 0; k < 15; k++) {
      const a = Math.PI * (0.92 + k * 1.16 / 14);
      S("circle", { cx: 300 + Math.cos(a) * 118, cy: 282 + Math.sin(a) * 128, r: 50 + rand(k) * 10, fill: shade(p.hair, 0.9) }, hairG);
    }
    S("path", { d: "M234,272 C214,264 206,290 212,308 C216,322 228,326 238,318 Z", fill: skinD }, head);       // ear
    S("path", { d: "M230,282 C220,282 218,298 224,306", fill: "none", stroke: skinS, "stroke-width": 3, "stroke-linecap": "round" }, head);
    S("path", { d: "M228,282 C226,228 260,194 304,194 C352,194 380,228 378,282 C377,318 368,346 352,366 C338,384 322,394 306,394 C286,394 264,384 250,366 C236,348 229,318 228,282 Z", fill: p.skin }, head);
    S("path", { d: "M378,282 C377,318 368,346 352,366 C338,384 322,394 306,394 C332,380 354,350 362,312 C366,290 368,266 364,238 C374,252 378,266 378,282 Z", fill: skinD }, head);
    S("ellipse", { cx: 272, cy: 332, rx: 15, ry: 8, fill: "#ff5c5c", opacity: 0.07 }, head);
    S("ellipse", { cx: 346, cy: 332, rx: 12, ry: 7, fill: "#ff5c5c", opacity: 0.06 }, head);
    if (p.beard) S("path", { d: "M236,314 C240,370 272,398 306,398 C342,398 368,370 376,314 C366,348 344,362 308,364 C274,364 248,350 236,314 Z",
      fill: p.hair, opacity: 0.9 }, head);

    // eyes: almond whites, an iris that looks around, upper lids (and lashes), a crease above
    const eyes = [[274, 1], [336, 0.88]].map(([ex, wk], k) => {
      const ey = 288;
      const g = S("g", {}, head);
      const wrap = S("g", { transform: `translate(${ex} ${ey}) scale(${wk} 1) translate(${-ex} ${-ey})` }, g);
      const almond = `M${ex - 15},${ey} C${ex - 8},${ey - 14} ${ex + 8},${ey - 14} ${ex + 15},${ey - 1} C${ex + 8},${ey + 8} ${ex - 8},${ey + 8} ${ex - 15},${ey} Z`;
      const clip = S("clipPath", { id: `eye${i}${k}` }, S("defs", {}, wrap));
      S("path", { d: almond }, clip);
      S("path", { d: almond, fill: "#fbfaf7" }, wrap);
      const inner = S("g", { "clip-path": `url(#eye${i}${k})` }, wrap);
      const pupil = S("g", {}, inner);
      const iris = p.eyes || "#5b3a29";
      S("circle", { cx: ex + 2, cy: ey - 2, r: 7, fill: iris }, pupil);
      S("circle", { cx: ex + 2, cy: ey - 2, r: 7, fill: "none", stroke: shade(iris, 0.55), "stroke-width": 1.3 }, pupil);
      S("circle", { cx: ex + 2, cy: ey - 2, r: 3.3, fill: "#120e12" }, pupil);
      S("circle", { cx: ex + 4.5, cy: ey - 5, r: 1.9, fill: "#fff" }, pupil);
      S("path", { d: `M${ex - 15},${ey - 8} C${ex - 6},${ey - 17} ${ex + 8},${ey - 17} ${ex + 15},${ey - 7} L${ex + 15},${ey - 1} C${ex + 8},${ey - 14} ${ex - 8},${ey - 14} ${ex - 15},${ey} Z`,
        fill: skinS, opacity: 0.18 }, inner);   // the lid's shadow on the eye
      S("path", { d: `M${ex - 16},${ey + 1} C${ex - 9},${ey - 15} ${ex + 9},${ey - 15} ${ex + 16},${ey - 1}`, fill: "none", stroke: "#2a1a18",
        "stroke-width": p.lashes ? 3.6 : 2.8, "stroke-linecap": "round" }, wrap);
      if (p.lashes) S("path", { d: k === 0 ? `M${ex - 15},${ey} l-4,-3` : `M${ex + 15},${ey - 2} l4,-3`, stroke: "#2a1a18", "stroke-width": 2.4,
        "stroke-linecap": "round" }, wrap);
      S("path", { d: `M${ex - 13},${ey - 15} C${ex - 5},${ey - 21} ${ex + 7},${ey - 21} ${ex + 14},${ey - 14}`, fill: "none", stroke: skinS,
        "stroke-width": 1.4, opacity: 0.35, "stroke-linecap": "round" }, g);   // crease
      return { g, pupil, ex, ey, k: 0.5 };
    });
    const brows = [[274, 1], [336, 0.88]].map(([ex, wk]) => {
      const by = 262;
      const b = S("path", { d: `M${ex - 18 * wk},${by + 5} C${ex - 8 * wk},${by - 4} ${ex + 8 * wk},${by - 6} ${ex + 19 * wk},${by - 1} L${ex + 19 * wk},${by + 3} C${ex + 8 * wk},${by - 1} ${ex - 8 * wk},${by + 1} ${ex - 18 * wk},${by + 8} Z`,
        fill: shade(p.hair, 0.9), stroke: shade(p.hair, 0.9), "stroke-width": 1.5, "stroke-linejoin": "round" }, head);
      b.ex = ex; b.ey = by;
      return b;
    });
    // nose, in three-quarter view: the bridge and the tip turned towards the other person
    S("path", { d: "M324,312 C328,322 332,328 331,333 C330,339 321,341 313,337", fill: "none", stroke: skinS, "stroke-width": 2.6,
      "stroke-linecap": "round", "stroke-linejoin": "round" }, head);
    S("ellipse", { cx: 320, cy: 343, rx: 10, ry: 2.6, fill: skinS, opacity: 0.25 }, head);
    // mouth shapes (see explainer.voice.VISEME)
    const mouthG = S("g", { transform: "translate(318,362) scale(0.68)" }, head);
    const dark = "#3a1216", lip = p.lips;
    const shapes = {};
    const shape = (name, build) => { const g = S("g", { display: "none" }, mouthG); build(g); shapes[name] = g; };
    const teeth = (g, w, y, h = 6) => S("rect", { x: -w, y, width: 2 * w, height: h, rx: 2, fill: "#fff" }, g);
    shape("X", (g) => {
      S("path", { d: "M-24,-2 Q0,10 24,-2", fill: "none", stroke: lip, "stroke-width": 6, "stroke-linecap": "round" }, g);
      S("path", { d: "M-12,9 Q0,13 12,9", fill: "none", stroke: shade(p.skin, 0.8), "stroke-width": 3, "stroke-linecap": "round", opacity: 0.6 }, g);
    });
    shape("H", (g) => { S("path", { d: "M-28,-5 Q0,24 28,-5 Q0,4 -28,-5 Z", fill: dark }, g); S("path", { d: "M-24,-3 Q0,4 24,-3 L22,2 Q0,8 -22,2 Z", fill: "#fff" }, g);
      S("path", { d: "M-28,-5 Q0,26 28,-5", fill: "none", stroke: lip, "stroke-width": 3.5, "stroke-linecap": "round" }, g); });
    shape("M", (g) => S("path", { d: "M-22,2 Q0,6 22,2", fill: "none", stroke: lip, "stroke-width": 8, "stroke-linecap": "round" }, g));
    shape("C", (g) => { S("ellipse", { rx: 17, ry: 7, fill: dark }, g); teeth(g, 12, -7, 5); S("ellipse", { rx: 18, ry: 8, fill: "none", stroke: lip, "stroke-width": 3 }, g); });
    shape("E", (g) => { S("ellipse", { rx: 23, ry: 11, fill: dark }, g); teeth(g, 17, -11, 6); S("ellipse", { rx: 24, ry: 12, fill: "none", stroke: lip, "stroke-width": 3 }, g); });
    shape("A", (g) => { S("ellipse", { rx: 20, ry: 19, fill: dark }, g); S("ellipse", { cy: 10, rx: 12, ry: 7, fill: "#e06b6b" }, g); teeth(g, 13, -19, 6);
      S("ellipse", { rx: 21, ry: 20, fill: "none", stroke: lip, "stroke-width": 3.5 }, g); });
    shape("O", (g) => { S("ellipse", { rx: 15, ry: 16, fill: dark }, g); S("ellipse", { rx: 15, ry: 16, fill: "none", stroke: lip, "stroke-width": 4 }, g); });
    shape("U", (g) => { S("ellipse", { rx: 10, ry: 11, fill: dark }, g); S("ellipse", { rx: 10, ry: 11, fill: "none", stroke: lip, "stroke-width": 4.5 }, g); });
    shape("F", (g) => { S("ellipse", { rx: 20, ry: 7, fill: dark }, g); teeth(g, 15, -7, 7); S("path", { d: "M-18,4 Q0,9 18,4", fill: "none", stroke: lip, "stroke-width": 5 }, g); });
    if (p.glasses) {
      const gl = S("g", { fill: "rgba(255,255,255,.12)", stroke: "#1f2937", "stroke-width": 3.6 }, head);
      S("rect", { x: 250, y: 272, width: 48, height: 34, rx: 11 }, gl);
      S("rect", { x: 314, y: 272, width: 44, height: 34, rx: 11 }, gl);
      S("path", { d: "M298,286 Q306,280 314,286", fill: "none" }, gl);
      S("path", { d: "M250,284 L232,282", fill: "none" }, gl);
    }
    if (hair.front) {
      S("path", { d: hair.front, fill: p.hair, opacity: hair.opacity || 1 }, head);
      if (hair.lock) S("path", { d: hair.lock, fill: shade(p.hair, 0.94) }, head);
    }
    if (hair.curls) {
      const curls = S("g", { transform: HAIR_FIT }, head);
      for (let k = 0; k < 9; k++)
        S("circle", { cx: 214 + k * 21.5, cy: 196 + Math.abs(k - 4) * 6 + rand(k + 30) * 8, r: 30 + rand(k + 7) * 8, fill: p.hair }, curls);
    }

    // arms, in front of the desk: tapered sleeves with cuffs
    const sleeve = shade(cloth, 0.96), cuff = outfit === "blouse" ? shade(cloth, 0.8) : shirt;
    const arms = [[184, 500], [416, 500]].map(([sx, sy]) => {
      const upper = S("g", {}, front);
      S("path", { d: `M-29,0 C-29,-22 29,-22 29,0 L24,${ARM.upper} C24,${ARM.upper + 20} -24,${ARM.upper + 20} -24,${ARM.upper} Z`, fill: sleeve }, upper);
      S("path", { d: `M14,-12 C24,-8 29,-4 29,0 L24,${ARM.upper} C24,${ARM.upper + 12} 18,${ARM.upper + 18} 10,${ARM.upper + 19} Z`, fill: shade(cloth, 0.84) }, upper);
      const fore = S("g", {}, upper);
      S("path", { d: `M-25,0 C-25,-22 25,-22 25,0 L21,${ARM.fore - 16} L-21,${ARM.fore - 16} Z`, fill: sleeve }, fore);
      S("path", { d: `M12,-16 C20,-10 25,-5 25,0 L21,${ARM.fore - 16} L10,${ARM.fore - 16} Z`, fill: shade(cloth, 0.84) }, fore);
      S("rect", { x: -22, y: ARM.fore - 26, width: 44, height: 13, rx: 4, fill: cuff }, fore);
      // the thumb towards the body's middle: the arm on the right side gets a mirrored hand
      const handG = S("g", { transform: `translate(0,${ARM.fore - 14}) scale(${sx > 300 ? -1.2 : 1.2} 1.2)` }, fore);
      const hands = { relaxed: hand(handG, p.skin, "relaxed"), open: hand(handG, p.skin, "open") };
      return { upper, fore, sx, sy, hands };
    });
    return { torsoG, head: headTurn, headBack, eyes, brows, shapes, arms, mood: "neutral" };
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
    P.head.setAttribute("transform", `rotate(${tilt} 304 418)`);
    P.headBack.setAttribute("transform", `rotate(${tilt} 304 418)`);
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
      e.g.setAttribute("transform", `translate(${e.ex} ${e.ey}) scale(1 ${blink}) translate(${-e.ex} ${-e.ey})`);
      e.pupil.setAttribute("transform", `translate(${look[0] * e.k} ${look[1] * e.k})`);
    });

    // brows: raised for questions and curiosity, knitted for concern
    const line = mine || (cur && cur.speaker === i ? cur : null);
    const mood = line ? line.mood : "neutral";
    const ask = line && /\?\s*$/.test(line.say) ? 1 : 0;
    const lift = (mood === "curious" ? 7 : mood === "excited" || mood === "happy" ? 4 : 0) + ask * 6;
    P.brows.forEach((b, k) => {
      const knit = mood === "concerned" ? (k === 0 ? 8 : -8) : 0;
      b.setAttribute("transform", `translate(0 ${-lift * 0.7 * (line ? smooth((t - line.start + 0.2) / 0.4) : 0)}) rotate(${knit * 0.7} ${b.ex} ${b.ey})`);
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

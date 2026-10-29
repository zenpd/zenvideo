// The presenters player: two co-presenters stand in a branded studio - a slatted feature wall with the company's logo
// sign, a wall display between them - and present to camera. Built from window.VIDEO (the timeline from
// explainer.voice.narrate_dialogue). The people are full-body rigs (head, neck, torso, jointed arms, hands with
// fingers, legs, shoes); every movement - lip-sync from Kokoro's phonemes, gestures, weight shift, nods, blinks,
// glances, the camera - is a function of time, set by seek(t), so any frame can be rendered exactly.
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
  const fadeOut = (n, at, d = 0.4) => anim(n, [{ opacity: 1 }, { opacity: 0 }], at, d, { fill: "forwards" });
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const smooth = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
  const mix = (a, b, k) => a + (b - a) * k;
  const rand = (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  function shade(hex, k) {
    const n = parseInt(hex.slice(1), 16);
    const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(clamp(k > 1 ? v + (255 - v) * (k - 1) : v * k, 0, 255)));
    return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  const logoEl = (parent, cls) => {
    if (V.logo) { const i = el("img", cls || "", parent); i.src = V.logo; i.alt = ""; return i; }
    return el("div", "word", parent, V.brand_name || V.app_name || V.title);
  };

  // ── the studio ─────────────────────────────────────────────────────────────
  const FLOOR_Y = 868;
  const POS = [520, 1400];        // where the two presenters stand
  function studio(cam) {
    const s = S("svg", { viewBox: "0 0 1920 1080" }, cam);
    const defs = S("defs", {}, s);
    const lin = (id, stops, x2 = 0, y2 = 1) => {
      const g = S("linearGradient", { id, x1: 0, y1: 0, x2, y2 }, defs);
      stops.forEach(([o, c, op]) => S("stop", { offset: o, "stop-color": c, "stop-opacity": op ?? 1 }, g));
    };
    const rad = (id, stops) => {
      const g = S("radialGradient", { id }, defs);
      stops.forEach(([o, c, op]) => S("stop", { offset: o, "stop-color": c, "stop-opacity": op ?? 1 }, g));
    };
    lin("wall", [[0, "var(--wall1)"], [1, "var(--wall2)"]]);
    lin("floor", [[0, "var(--floor1)"], [1, "var(--floor2)"]]);
    lin("feature", [[0, "var(--brand2)"], [1, "var(--brand)"]]);
    lin("refl", [[0, "#000", 0.16], [1, "#000", 0]]);
    rad("spot", [[0, "#ffffff", 0.55], [1, "#ffffff", 0]]);
    rad("shadow", [[0, "#000", 0.32], [1, "#000", 0]]);
    rad("leafglow", [[0, "#fff", 0.25], [1, "#fff", 0]]);

    S("rect", { x: 0, y: 0, width: 1920, height: FLOOR_Y, fill: "url(#wall)" }, s);
    // side walls: framed panels
    [[70, 300], [1550, 300]].forEach(([x, w]) => {
      S("rect", { x, y: 140, width: w, height: 560, rx: 6, fill: "#fff", opacity: 0.55 }, s);
      S("rect", { x: x + 18, y: 158, width: w - 36, height: 524, rx: 4, fill: "none", stroke: "#d5dae2", "stroke-width": 2 }, s);
    });
    // feature wall: brand colour with vertical slats, a lit edge in the accent colour
    S("rect", { x: 400, y: 0, width: 1120, height: FLOOR_Y, fill: "url(#feature)" }, s);
    for (let x = 412; x < 1512; x += 34) S("rect", { x, y: 0, width: 16, height: FLOOR_Y, fill: "#fff", opacity: 0.045 }, s);
    S("rect", { x: 400, y: 0, width: 6, height: FLOOR_Y, fill: "var(--accent)" }, s);
    S("rect", { x: 1514, y: 0, width: 6, height: FLOOR_Y, fill: "var(--accent)" }, s);
    S("rect", { x: 400, y: 0, width: 1120, height: 10, fill: "var(--accent)", opacity: 0.85 }, s);
    // light falling on the wall
    S("ellipse", { cx: 960, cy: 120, rx: 520, ry: 300, fill: "url(#spot)", opacity: 0.35 }, s);
    S("ellipse", { cx: 600, cy: 260, rx: 300, ry: 420, fill: "url(#spot)", opacity: 0.18 }, s);
    S("ellipse", { cx: 1320, cy: 260, rx: 300, ry: 420, fill: "url(#spot)", opacity: 0.18 }, s);
    // the wall display's frame (its content is HTML, in front of this)
    S("rect", { x: 728, y: 274, width: 464, height: 284, rx: 14, fill: "#000", opacity: 0.25 }, s);
    S("rect", { x: 736, y: 278, width: 448, height: 276, rx: 12, fill: "#0b0f17" }, s);
    // floor with the wall reflected in it, and a skirting light
    S("rect", { x: 0, y: FLOOR_Y, width: 1920, height: 1080 - FLOOR_Y, fill: "url(#floor)" }, s);
    S("rect", { x: 400, y: FLOOR_Y, width: 1120, height: 120, fill: "var(--brand)", opacity: 0.10 }, s);
    S("rect", { x: 0, y: FLOOR_Y, width: 1920, height: 4, fill: "#fff", opacity: 0.6 }, s);
    // plants in tall planters
    [[240, 1], [1680, -1]].forEach(([px, dir], k) => {
      const g = S("g", { transform: `translate(${px},${FLOOR_Y + 120})` }, s);
      S("ellipse", { cx: 0, cy: 6, rx: 90, ry: 14, fill: "url(#shadow)" }, g);
      S("path", { d: "M-62,-190 L62,-190 L50,0 L-50,0 Z", fill: "#f8fafc" }, g);
      S("path", { d: "M10,-190 L62,-190 L50,0 L18,0 Z", fill: "#e2e8f0" }, g);
      S("rect", { x: -66, y: -200, width: 132, height: 14, rx: 4, fill: "#e5e9f0" }, g);
      const leaves = S("g", { transform: "translate(0,-196)" }, g);
      for (let i = 0; i < 14; i++) {
        const a = -80 + i * 12 + rand(i + k * 20) * 8, len = 150 + rand(i + 9 + k) * 150;
        S("path", { d: `M0,0 C${-18},${-len * 0.45} ${-10},${-len * 0.8} 0,${-len} C${12},${-len * 0.8} ${18},${-len * 0.45} 0,0 Z`,
          fill: i % 3 === 0 ? "#2f855a" : i % 3 === 1 ? "#38a169" : "#276749", transform: `rotate(${a * dir})` }, leaves);
      }
      anim(leaves, [{ transform: "translate(0px,-196px) rotate(-1deg)" }, { transform: "translate(0px,-196px) rotate(1.2deg)" }],
        k * 0.8, 3.4, { iter: Infinity, dir: "alternate", ease: E.inOut });
    });
    return s;
  }

  // ── the people ─────────────────────────────────────────────────────────────
  // Local units: feet at (0,0), up is -y, about 900 tall. A person faces the camera, turned a little towards the
  // other (facing +1: to the right of the picture, -1: to the left).
  const UPPER = 160, FORE = 148;
  // poses per arm: [upper arm angle, forearm angle, hand, forearm length scale (foreshortening), hand angle];
  // angles in degrees from hanging straight down, positive = away from the body
  const POSES = {
    hang: [7, 3, "relaxed", 1, 0],
    clasp: [12, -46, "relaxed", 1, -10],
    explain: [16, -122, "open", 0.72, 28],
    count: [12, -134, "open", 0.7, 14],
    open: [30, 62, "open", 1, 30],
    point: [40, 140, "point", 1, -18],
    wave: [54, 162, "open", 1, -6],
  };
  // which arm does what in each gesture: [outer arm, inner arm (towards the other person and the display)]
  const GESTURES = {
    rest: ["clasp", "clasp"], hang: ["hang", "hang"], explain: ["hang", "explain"], count: ["hang", "count"],
    open: ["open", "open"], point: ["hang", "point"], wave: ["hang", "wave"], think: ["hang", "explain"], none: ["clasp", "clasp"],
  };

  function hand(parent, skin, pose) {
    const g = S("g", { display: "none" }, parent);
    const dark = shade(skin, 0.82);
    const thumb = (x, y, a) => {        // a thumb joined to the side of the palm
      const t = S("g", { transform: `translate(${x} ${y}) rotate(${a})` }, g);
      S("path", { d: "M-2,-6 C10,-6 20,2 24,14 C26,22 20,26 14,22 C8,18 2,10 -2,6 Z", fill: skin }, t);
      S("path", { d: "M6,2 C10,6 14,12 16,16", fill: "none", stroke: dark, "stroke-width": 1.4, "stroke-linecap": "round" }, t);
    };
    if (pose === "relaxed") {
      S("path", { d: "M-14,0 C-17,20 -18,40 -15,58 C-13,72 -5,80 4,78 C12,76 16,62 16,46 C17,28 16,12 14,0 Z", fill: skin }, g);
      [-7, -1, 5].forEach((x) => S("path", { d: `M${x},50 L${x + 0.5},72`, stroke: dark, "stroke-width": 1.6, "stroke-linecap": "round" }, g));
      thumb(12, 14, 58);
    } else if (pose === "open") {
      [[-11.5, -9, 29], [-3.8, -3, 34], [3.8, 3, 33], [11.2, 9, 27]].forEach(([x, a, len]) =>
        S("rect", { x: x - 4.2, y: 30, width: 8.4, height: len + 8, rx: 4.2, fill: skin, transform: `rotate(${a} ${x} 34)` }, g));
      S("path", { d: "M-15,0 C-18,14 -19,28 -17,40 C-8,44 8,44 17,40 C18,28 18,14 15,0 Z", fill: skin }, g);
      S("path", { d: "M-10,30 C-2,34 6,33 12,28", fill: "none", stroke: dark, "stroke-width": 1.4, "stroke-linecap": "round" }, g);
      thumb(13, 12, 22);
    } else {   // point: a fist with the index finger out
      S("rect", { x: -16, y: 0, width: 32, height: 44, rx: 13, fill: skin }, g);
      S("rect", { x: 3, y: 30, width: 10, height: 52, rx: 5, fill: skin }, g);
      S("path", { d: "M-14,28 L2,30", stroke: dark, "stroke-width": 1.6, "stroke-linecap": "round" }, g);
      thumb(12, 10, 70);
    }
    return g;
  }

  function person(p, i, layer) {
    const fem = p.body === "f";
    const facing = i === 0 ? 1 : -1;
    const [X, K] = [POS[i], 0.8];
    const root = S("g", { transform: `translate(${X},1005) scale(${K})` }, layer);
    const skinD = shade(p.skin, 0.84), skinDD = shade(p.skin, 0.72);
    const suit = p.suit, suitD = shade(p.suit, 0.78), suitL = shade(p.suit, 1.12);
    S("ellipse", { cx: 0, cy: 0, rx: 150, ry: 22, fill: "url(#shadow)" }, root);

    // legs and shoes (they stay put; the body above the hips sways)
    const legs = S("g", {}, root);
    if (fem) {
      const tights = p.legs || skinD;
      S("path", { d: "M-58,-250 C-56,-170 -50,-110 -46,-46 L-26,-46 C-24,-110 -18,-180 -10,-250 Z", fill: tights }, legs);
      S("path", { d: "M58,-250 C56,-170 50,-110 46,-46 L26,-46 C24,-110 18,-180 10,-250 Z", fill: shade(tights, 0.9) }, legs);
      [-1, 1].forEach((d) => {
        S("path", { d: `M${d * 48},-50 L${d * 22},-50 C${d * 18},-34 ${d * 18},-14 ${d * 22},0 L${d * 66},0 C${d * 74},0 ${d * 74},-10 ${d * 66},-14 C${d * 56},-20 ${d * 50},-30 ${d * 48},-50 Z`, fill: p.shoes }, legs);
        S("rect", { x: d > 0 ? 22 : -30, y: -16, width: 8, height: 16, fill: shade(p.shoes, 0.7) }, legs);
      });
      S("path", { d: "M-78,-452 C-82,-390 -80,-310 -70,-240 L70,-240 C80,-310 82,-390 78,-452 Z", fill: p.skirt }, legs);
      S("path", { d: "M20,-452 L78,-452 C82,-390 80,-310 70,-240 L32,-240 C40,-320 36,-400 20,-452 Z", fill: shade(p.skirt, 0.85) }, legs);
      S("path", { d: "M6,-300 L6,-240", stroke: shade(p.skirt, 0.7), "stroke-width": 3 }, legs);
    } else {
      S("path", { d: "M-86,-430 C-86,-300 -76,-150 -68,-44 L-24,-44 C-20,-150 -12,-290 -2,-390 Z", fill: p.trousers }, legs);
      S("path", { d: "M86,-430 C86,-300 76,-150 68,-44 L24,-44 C20,-150 12,-290 2,-390 Z", fill: shade(p.trousers, 0.86) }, legs);
      S("path", { d: "M-46,-380 L-46,-50", stroke: shade(p.trousers, 0.8), "stroke-width": 2.5 }, legs);
      S("path", { d: "M46,-380 L46,-50", stroke: shade(p.trousers, 0.72), "stroke-width": 2.5 }, legs);
      [-1, 1].forEach((d) => S("path", { d: `M${d * 72},-46 L${d * 20},-46 C${d * 16},-24 ${d * 14},-8 ${d * 18},0 L${d * 92},0 C${d * 104},0 ${d * 106},-14 ${d * 94},-22 C${d * 84},-28 ${d * 76},-32 ${d * 72},-46 Z`, fill: p.shoes }, legs));
    }

    // everything above the hips moves together (weight shift, breathing)
    const upper = S("g", {}, root);
    const sh = fem ? 78 : 92;              // half the shoulder width
    const shoulders = [[-(sh - 16), -700], [sh - 16, -700]];
    const armBack = S("g", {}, upper);
    const hairBack = S("g", {}, upper);
    const neck = S("g", {}, upper);
    const torso = S("g", {}, upper);
    const headG = S("g", {}, upper);
    const armFront = S("g", {}, upper);

    // upper arms (behind the jacket's shoulders), forearms and hands (in front of the body)
    const arms = shoulders.map(([sx, sy], k) => {
      const side = k === 0 ? -1 : 1;
      const up = S("g", {}, armBack);
      S("path", { d: `M-25,0 C-27,60 -23,120 -19,${UPPER} L19,${UPPER} C23,120 27,60 25,0 C25,-16 -25,-16 -25,0 Z`, fill: suit }, up);
      S("path", { d: `M${side * 6},-8 C${side * 26},40 ${side * 22},120 ${side * 18},${UPPER} L${side * 19},${UPPER} C${side * 23},120 ${side * 27},60 ${side * 25},0 Z`, fill: suitD }, up);
      const fore = S("g", {}, armFront);
      const foreArm = S("g", {}, fore);
      S("circle", { cx: 0, cy: 0, r: 19, fill: suit }, foreArm);
      S("path", { d: `M-19,0 L-16,${FORE - 8} L16,${FORE - 8} L19,0 Z`, fill: suit }, foreArm);
      S("path", { d: `M${side * 4},0 L${side * 7},${FORE - 8} L${side * 16},${FORE - 8} L${side * 19},0 Z`, fill: suitD }, foreArm);
      S("rect", { x: -16, y: FORE - 12, width: 32, height: 12, rx: 3, fill: p.shirt }, foreArm);
      const handG = S("g", {}, fore);
      const hands = Object.fromEntries(["relaxed", "open", "point"].map((h) => [h, hand(handG, p.skin, h)]));
      return { sx, sy, side, up, fore, foreArm, handG, hands };
    });

    // neck
    S("path", { d: "M-19,-790 L19,-790 L21,-700 L-21,-700 Z", fill: skinD }, neck);
    S("path", { d: "M-19,-770 C-8,-752 8,-752 19,-770 L19,-748 C8,-736 -8,-736 -19,-748 Z", fill: skinDD, opacity: 0.6 }, neck);

    // torso: jacket, shirt or blouse, lapels, tie
    if (fem) {
      S("path", { d: `M-${sh},-706 C-${sh + 8},-684 -${sh + 10},-656 -${sh + 6},-636 L-62,-500 C-64,-474 -70,-452 -76,-430 L76,-430 C70,-452 64,-474 62,-500 L${sh + 6},-636 C${sh + 10},-656 ${sh + 8},-684 ${sh},-706 C52,-718 26,-722 0,-722 C-26,-722 -52,-718 -${sh},-706 Z`, fill: suit }, torso);
      S("path", { d: `M24,-718 C52,-716 ${sh - 4},-708 ${sh},-706 C${sh + 8},-684 ${sh + 10},-656 ${sh + 6},-636 L62,-500 C64,-474 70,-452 76,-430 L36,-430 C44,-520 40,-640 24,-718 Z`, fill: suitD, opacity: 0.55 }, torso);
      S("path", { d: "M-30,-720 C-20,-680 -10,-640 0,-596 C10,-640 20,-680 30,-720 Z", fill: p.shirt }, torso);
      S("path", { d: "M-22,-722 C-12,-698 12,-698 22,-722 Z", fill: skinD }, torso);
      S("path", { d: "M-32,-720 L-2,-594 L-14,-556 L-48,-640 L-52,-702 Z", fill: suitL }, torso);
      S("path", { d: "M32,-720 L2,-594 L14,-556 L48,-640 L52,-702 Z", fill: suitD }, torso);
      S("circle", { cx: 0, cy: -540, r: 6, fill: shade(suit, 0.6) }, torso);
      if (p.necklace) S("path", { d: "M-16,-718 C-8,-694 8,-694 16,-718", fill: "none", stroke: p.necklace, "stroke-width": 2.5 }, torso);
    } else {
      S("path", { d: `M-${sh},-712 C-${sh + 8},-690 -${sh + 10},-660 -${sh + 6},-640 L-84,-470 L-88,-400 L88,-400 L84,-470 L${sh + 6},-640 C${sh + 10},-660 ${sh + 8},-690 ${sh},-712 C60,-724 30,-728 0,-728 C-30,-728 -60,-724 -${sh},-712 Z`, fill: suit }, torso);
      S("path", { d: `M26,-726 C60,-722 ${sh - 4},-714 ${sh},-712 C${sh + 8},-690 ${sh + 10},-660 ${sh + 6},-640 L84,-470 L88,-400 L40,-400 C48,-500 44,-640 26,-726 Z`, fill: suitD, opacity: 0.55 }, torso);
      S("path", { d: "M-28,-728 L0,-588 L28,-728 Z", fill: p.shirt }, torso);
      S("path", { d: "M-24,-730 L-4,-700 L-14,-690 L-30,-716 Z", fill: shade(p.shirt, 0.92) }, torso);
      S("path", { d: "M24,-730 L4,-700 L14,-690 L30,-716 Z", fill: shade(p.shirt, 0.88) }, torso);
      S("path", { d: "M-8,-704 L8,-704 L10,-688 L6,-604 L0,-590 L-6,-604 L-10,-688 Z", fill: p.tie }, torso);
      S("path", { d: "M-9,-706 L9,-706 L7,-690 L-7,-690 Z", fill: shade(p.tie, 0.8) }, torso);
      S("path", { d: "M-30,-728 L-4,-592 L-18,-548 L-50,-640 L-56,-708 Z", fill: suitL }, torso);
      S("path", { d: "M30,-728 L4,-592 L18,-548 L50,-640 L56,-708 Z", fill: suitD }, torso);
      S("path", { d: "M-2,-560 L-2,-400", stroke: shade(suit, 0.6), "stroke-width": 2 }, torso);
      [-520, -462].forEach((y) => S("circle", { cx: -8, cy: y, r: 5.5, fill: shade(suit, 0.55) }, torso));
      S("path", { d: "M44,-640 L74,-640 L72,-628 L46,-628 Z", fill: shade(suit, 0.7) }, torso);
      if (p.pocket) S("path", { d: "M50,-640 L56,-652 L62,-644 L68,-652 L70,-640 Z", fill: p.pocket }, torso);
    }

    // head: centre at (0,-822) in body units; features drawn around (0,0)
    const head = S("g", {}, headG);
    const hb = S("g", {}, hairBack);
    if (p.hair_style === "shoulder") {
      S("path", { d: "M-64,-18 C-68,-82 -32,-100 0,-100 C34,-100 68,-80 66,-16 C68,40 74,92 64,120 C46,132 26,124 20,104 L-20,104 C-26,124 -46,132 -64,120 C-74,92 -68,40 -64,-18 Z", fill: p.hair }, hb);
      S("path", { d: "M30,-80 C58,-60 64,10 62,90 C60,108 52,118 44,118 C54,60 52,-20 30,-80 Z", fill: shade(p.hair, 0.8) }, hb);
    } else if (p.hair_style === "bun") {
      S("circle", { cx: 6, cy: -96, r: 30, fill: p.hair }, hb);
    }
    S("ellipse", { cx: -53, cy: -2, rx: 9, ry: 16, fill: skinD }, head);
    S("ellipse", { cx: 53, cy: -2, rx: 9, ry: 16, fill: skinD }, head);
    const jaw = fem ? "C52,24 40,50 22,60 C12,66 -12,66 -22,60 C-40,50 -52,24" : "C52,30 46,52 28,62 C16,68 -16,68 -28,62 C-46,52 -52,30";
    S("path", { d: `M-52,-10 C-52,-64 -28,-80 0,-80 C28,-80 52,-64 52,-10 ${jaw} -52,-10 Z`, fill: p.skin }, head);
    S("path", { d: "M20,-78 C44,-70 54,-48 52,-10 C52,26 42,50 24,60 C36,30 40,-20 20,-78 Z", fill: skinD, opacity: 0.35 }, head);
    if (p.stubble) S("path", { d: "M-50,8 C-50,30 -40,52 -24,62 C-12,68 12,68 24,62 C40,52 50,30 50,8 C34,42 -34,42 -50,8 Z", fill: p.hair, opacity: 0.14 }, head);
    const face = S("g", {}, head);
    // eyes
    const eyes = [-20, 20].map((ex) => {
      const g = S("g", {}, face);
      S("path", { d: `M${ex - 12},-6 C${ex - 8},-13 ${ex + 8},-13 ${ex + 12},-6 C${ex + 8},-1 ${ex - 8},-1 ${ex - 12},-6 Z`, fill: "#fff" }, g);
      const iris = S("g", {}, g);
      S("circle", { cx: ex, cy: -6.5, r: 5.6, fill: p.eyes }, iris);
      S("circle", { cx: ex, cy: -6.5, r: 2.7, fill: "#14121a" }, iris);
      S("circle", { cx: ex + 1.8, cy: -8.4, r: 1.4, fill: "#fff" }, iris);
      S("path", { d: `M${ex - 12.5},-6 C${ex - 8},-14 ${ex + 8},-14 ${ex + 12.5},-6.5`, fill: "none", stroke: "#2a1d1a", "stroke-width": fem ? 2.6 : 2, "stroke-linecap": "round" }, g);
      if (fem) S("path", { d: `M${ex + (ex > 0 ? 11 : -11)},-8 l${ex > 0 ? 5 : -5},-4`, stroke: "#2a1d1a", "stroke-width": 2, "stroke-linecap": "round" }, g);
      return { g, iris, ex };
    });
    const brows = [-21, 21].map((bx) => S("path", {
      d: bx < 0 ? `M${bx - 13},-22 C${bx - 6},-30 ${bx + 6},-31 ${bx + 13},-27 L${bx + 13},-24 C${bx + 6},-27 ${bx - 6},-26 ${bx - 13},-19 Z`
        : `M${bx + 13},-22 C${bx + 6},-30 ${bx - 6},-31 ${bx - 13},-27 L${bx - 13},-24 C${bx - 6},-27 ${bx + 6},-26 ${bx + 13},-19 Z`,
      fill: p.brows || shade(p.hair, 0.85) }, face));
    S("path", { d: "M2,-2 C4,8 7,15 3,20 C1,22 -3,21 -5,19", fill: "none", stroke: skinDD, "stroke-width": 2.2, "stroke-linecap": "round" }, face);
    S("ellipse", { cx: -30, cy: 18, rx: 9, ry: 5, fill: "#ff6b6b", opacity: fem ? 0.16 : 0.08 }, face);
    S("ellipse", { cx: 30, cy: 18, rx: 9, ry: 5, fill: "#ff6b6b", opacity: fem ? 0.16 : 0.08 }, face);
    // mouth shapes (see explainer.voice.VISEME)
    const mouthG = S("g", { transform: "translate(0,36)" }, face);
    const lip = p.lips, dark = "#3b1418";
    const shapes = {};
    const shape = (name, build) => { const g = S("g", { display: "none" }, mouthG); build(g); shapes[name] = g; };
    const lips = (g, open) => {
      S("path", { d: `M-13,${-open / 2} C-6,${-open / 2 - 4} -2,${-open / 2 - 2} 0,${-open / 2 - 1} C2,${-open / 2 - 2} 6,${-open / 2 - 4} 13,${-open / 2} C6,${-open / 2 + 2} -6,${-open / 2 + 2} -13,${-open / 2} Z`, fill: lip }, g);
      S("path", { d: `M-11,${open / 2} C-5,${open / 2 + 6} 5,${open / 2 + 6} 11,${open / 2} C5,${open / 2 + 2} -5,${open / 2 + 2} -11,${open / 2} Z`, fill: shade(lip, 0.92) }, g);
    };
    const hole = (g, rx, ry, teeth = true, tongue = false) => {
      S("ellipse", { rx, ry, fill: dark }, g);
      if (teeth) S("rect", { x: -rx * 0.7, y: -ry, width: rx * 1.4, height: Math.min(4, ry * 0.7), rx: 1.5, fill: "#fff" }, g);
      if (tongue) S("ellipse", { cy: ry * 0.5, rx: rx * 0.6, ry: ry * 0.4, fill: "#d9686b" }, g);
    };
    shape("X", (g) => { lips(g, 0); S("path", { d: "M-13,0 C-6,3 6,3 13,0", fill: "none", stroke: shade(lip, 0.6), "stroke-width": 1.4 }, g); });
    shape("H", (g) => { hole(g, 13, 5); S("path", { d: "M-15,-3 C-6,-6 6,-6 15,-3", fill: "none", stroke: lip, "stroke-width": 3 }, g); S("path", { d: "M-12,3 C-5,8 5,8 12,3", fill: "none", stroke: lip, "stroke-width": 3 }, g); });
    shape("M", (g) => lips(g, -1));
    shape("C", (g) => { hole(g, 9, 4); lips(g, 8); });
    shape("E", (g) => { hole(g, 12, 6); lips(g, 11); });
    shape("A", (g) => { hole(g, 10, 10, true, true); lips(g, 19); });
    shape("O", (g) => { hole(g, 7.5, 9, false); lips(g, 16); });
    shape("U", (g) => { hole(g, 5, 6, false); lips(g, 11); });
    shape("F", (g) => { hole(g, 10, 4); lips(g, 6); });
    // hair in front
    const hf = S("g", {}, head);
    if (p.hair_style === "shoulder") {
      S("path", { d: "M-56,-4 C-60,-68 -24,-94 6,-92 C42,-90 62,-62 58,-6 C52,-40 38,-58 16,-64 C-6,-50 -32,-34 -48,14 Z", fill: p.hair }, hf);
      S("path", { d: "M-30,-74 C-14,-86 14,-86 30,-74 C10,-78 -12,-76 -30,-74 Z", fill: shade(p.hair, 1.35), opacity: 0.7 }, hf);
      S("path", { d: "M-56,-4 C-60,24 -58,60 -50,96 C-62,60 -66,20 -56,-4 Z", fill: p.hair }, hf);
    } else if (p.hair_style === "bun") {
      S("path", { d: "M-54,-10 C-58,-66 -26,-92 2,-92 C34,-92 58,-66 54,-10 C48,-44 32,-62 4,-64 C-22,-62 -46,-44 -54,-10 Z", fill: p.hair }, hf);
    } else {   // a short crop with a side parting
      S("path", { d: "M-55,-16 C-60,-72 -26,-98 6,-96 C40,-94 60,-70 55,-16 C51,-42 44,-56 34,-62 C10,-54 -18,-58 -38,-66 C-48,-52 -53,-36 -55,-16 Z", fill: p.hair }, hf);
      S("path", { d: "M-38,-66 C-20,-84 20,-88 40,-70 C14,-80 -12,-78 -38,-66 Z", fill: shade(p.hair, 1.3), opacity: 0.6 }, hf);
      S("path", { d: "M-55,-16 L-52,10 L-48,-20 Z M55,-16 L52,10 L48,-20 Z", fill: p.hair }, hf);
    }
    return { root, upper, headG, hairBack, head, face, eyes, brows, shapes, arms, facing, fem, X, K };
  }

  function setArm(P, a, poseName, wobble = 0) {
    const pose = POSES[poseName];
    const blend = a.blend;     // [from pose, to pose, k] eased by the caller
    let u = pose[0], f = pose[1], s = pose[3], h = pose[4];
    if (blend) {
      const [p0, k] = blend;
      u = mix(p0[0], u, k); f = mix(p0[1], f, k); s = mix(p0[3], s, k); h = mix(p0[4], h, k);
    }
    f += wobble;
    const sign = -a.side;            // positive angles turn the arm away from the body
    a.up.setAttribute("transform", `translate(${a.sx},${a.sy}) rotate(${u * sign})`);
    a.fore.setAttribute("transform", `translate(${a.sx},${a.sy}) rotate(${u * sign}) translate(0,${UPPER}) rotate(${(f - u) * sign})`);
    a.foreArm.setAttribute("transform", `scale(1 ${s})`);
    const handName = blend && blend[1] < 0.5 ? blend[0][2] : pose[2];
    a.handG.setAttribute("transform", `translate(0,${FORE * s - 4}) rotate(${h * sign}) scale(${a.side > 0 ? -1 : 1} 1)`);
    for (const [n, g] of Object.entries(a.hands)) g.setAttribute("display", n === handName ? "inline" : "none");
  }

  // what each presenter does at time t
  function animatePerson(P, i, t) {
    let cur = null;
    for (const ln of LINES) if (ln.start - 0.25 <= t) cur = ln;
    const mine = LINES.filter((ln) => ln.speaker === i && t >= ln.start - 0.35 && t <= ln.end + 0.6)[0];
    const speaking = cur && cur.speaker === i && t >= cur.start - 0.05 && t <= cur.end + 0.08;
    const restName = P.fem ? "rest" : "hang";

    // arms: the line's gesture eased in and out; the rest pose in between
    const g = GESTURES[mine ? mine.gesture : restName] || GESTURES.rest;
    const rest = GESTURES[restName];
    const w = mine ? smooth((t - mine.start + 0.15) / 0.55) * smooth((mine.end + 0.45 - t) / 0.55) : 0;
    P.arms.forEach((a, k) => {
      const inner = (k === 0 ? -1 : 1) === P.facing ? 1 : 0;      // the arm towards the other person
      const target = g[inner], from = POSES[rest[inner]];
      a.blend = [from, w];
      let wob = 0;
      if (mine && target !== rest[inner]) {
        const beat = mine.beats.reduce((s, b) => s + Math.exp(-(((t - b + 0.12) / 0.18) ** 2)), 0);
        wob = target === "wave" ? 14 * Math.sin(t * 8.5) : target === "point" ? 1.5 * Math.sin(t * 2) : 5 * Math.sin(t * 2.6 + k) + 7 * beat;
        wob *= w;
      }
      setArm(P, a, target, wob);
    });

    // body: weight shift and breathing; head: sways and nods while talking, turned to whoever is talking
    const sway = 1.1 * Math.sin(t * 0.55 + i * 2.1);
    const breathe = 1.8 * Math.sin(t * 1.4 + i);
    P.upper.setAttribute("transform", `rotate(${sway} 0 -430) translate(0 ${breathe})`);
    let tilt = 0, turn = 0;
    if (speaking) {
      tilt = 1.8 * Math.sin(t * 2.2 + i * 1.7) + cur.beats.reduce((s, b, k) => s + (k % 2 ? 0 : 2.6 * Math.exp(-(((t - b - 0.05) / 0.16) ** 2))), 0);
      turn = 0.25 * P.facing;
    } else if (cur && cur.speaker !== i && t >= cur.start - 0.3) {
      turn = P.facing * smooth((t - cur.start + 0.3) / 0.5);
      tilt = 2.5 * P.facing * smooth((t - cur.start) / 0.6) + cur.beats.reduce((s, b, k) => s + (k % 3 === 1 ? 3 * Math.exp(-(((t - b - 0.25) / 0.2) ** 2)) : 0), 0);
    }
    const headT = `rotate(${tilt} 0 -740) translate(0 -822)`;
    P.headG.setAttribute("transform", headT);
    P.hairBack.setAttribute("transform", headT);
    P.face.setAttribute("transform", `translate(${turn * 6} 0)`);

    // eyes: at the camera while talking, at the speaker while listening, at the display when it changes; blinks
    let look = speaking ? [0, 0] : [3.2 * P.facing, 0];
    const sc = LINES.filter((ln) => ln.screen && t >= ln.screen.at && t <= ln.screen.at + 1.2)[0];
    if (sc || (mine && mine.gesture === "point" && w > 0.6)) look = [3.4 * P.facing, -1.2];
    const phase = (t + i * 1.7) % 3.9;
    const blink = phase > 3.76 || (rand(Math.floor((t + i * 1.7) / 3.9) + i * 40) > 0.65 && phase > 1.7 && phase < 1.84) ? 0.1 : 1;
    P.eyes.forEach((e) => {
      e.g.setAttribute("transform", `translate(0 -6) scale(1 ${blink}) translate(0 6)`);
      e.iris.setAttribute("transform", `translate(${look[0]} ${look[1]})`);
    });
    const line = mine || (speaking ? cur : null);
    const mood = line ? line.mood : "neutral";
    const lift = (mood === "curious" ? 4 : mood === "happy" || mood === "excited" ? 2.5 : 0) + (line && /\?\s*$/.test(line.say) ? 4 : 0);
    P.brows.forEach((b) => b.setAttribute("transform", `translate(0 ${-lift * (line ? smooth((t - line.start + 0.2) / 0.4) : 0)})`));

    let shapeName = (cur && cur.speaker !== i && ["happy", "excited"].includes(cur.mood)) ? "H" : "X";
    if (speaking && cur.mouth.length) {
      let s = "X";
      for (const [mt, ms] of cur.mouth) { if (mt > t) break; s = ms; }
      shapeName = s;
    }
    for (const [name, gg] of Object.entries(P.shapes)) gg.setAttribute("display", name === shapeName ? "inline" : "none");
  }

  // ── the wall display ───────────────────────────────────────────────────────
  function display(cam) {
    const tv = el("div", "tv", cam);
    const shows = LINES.filter((ln) => ln.screen);
    const splash = el("div", "slide splash", tv);
    logoEl(splash);
    if (shows.length) fadeOut(splash, shows[0].screen.at, 0.4);
    shows.forEach((ln, k) => {
      const sc = ln.screen;
      const slide = el("div", "slide", tv);
      if (sc.title) { el("div", "ttl", slide, sc.title); el("div", "bar", slide); }
      if (sc.points.length) {
        const pts = el("div", "pts" + (sc.points.length > 3 ? " two" : ""), slide);
        sc.points.forEach((p) => {
          const row = el("div", "pt", pts);
          el("i", "ic dot", row, String.fromCodePoint(ICON.check || 0xE73E));
          el("span", "", row, p.text);
          rise(row, p.at, 0.45, 14);
        });
      }
      anim(slide, [{ opacity: 0, transform: "translateX(30px)" }, { opacity: 1, transform: "none" }], sc.at, 0.5);
      const next = shows[k + 1];
      if (next) anim(slide, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateX(-30px)" }], next.screen.at - 0.1, 0.35, { fill: "forwards" });
    });
    el("div", "glare", tv);
  }

  // ── the camera ─────────────────────────────────────────────────────────────
  function shots() {
    const out = [{ t: 0, cx: 960, cy: 540, s: 1.0, ease: 0 }];
    const key = (s) => `${Math.round(s.cx)},${Math.round(s.cy)},${s.s}`;
    LINES.forEach((ln, k) => {
      const x = POS[ln.speaker], f = ln.speaker === 0 ? 1 : -1;
      let s;
      if (ln.screen) s = { cx: ln.speaker === 0 ? 815 : 1105, cy: 470, s: 2.3, ease: 0 };       // the speaker and the display
      else if (k === 0 || k % 4 === 3) s = { cx: 960, cy: 560, s: 1.12, ease: 0.8 };             // both of them
      else s = { cx: x - f * 100, cy: 425, s: 3.0, ease: 0 };   // head and shoulders, framed clear of the display
      s.t = ln.start - 0.3;
      if (key(s) !== key(out[out.length - 1])) out.push(s);
    });
    out.push({ t: LINES[LINES.length - 1].end + 0.3, cx: 960, cy: 540, s: 1.0, ease: 1.2 });
    return out.map((s) => { const hw = 960 / s.s, hh = 540 / s.s; return { ...s, cx: clamp(s.cx, hw, 1920 - hw), cy: clamp(s.cy, hh, 1080 - hh) }; });
  }
  function camera(cam) {
    const list = shots();
    const at = (s, t) => ({ cx: s.cx, cy: s.cy, s: s.s * (1 + 0.005 * clamp(t - s.t, 0, 10)) });
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
    if (V.brand_name || V.app_name) el("div", "k", card, V.brand_name || V.app_name);
    el("div", "t", card, V.title);
    rise(card, 0.3, 0.8, 30);
    fadeOut(card, first.start + 0.8, 0.5);
    V.cast.forEach((c, i) => {
      const firstLine = LINES.find((ln) => ln.speaker === i);
      if (!firstLine) return;
      const tag = el("div", "over tag", stage);
      tag.style[i === 0 ? "left" : "right"] = "80px";
      el("div", "av", tag);
      const txt = el("div", "", tag);
      el("div", "n", txt, c.name);
      el("div", "r", txt, c.role);
      const t0 = Math.max(firstLine.start + 0.2, first.start + 1.4);
      rise(tag, t0, 0.6, 20);
      fadeOut(tag, t0 + 3.4, 0.5);
    });
    const close = el("div", "over closing", stage);
    const plate = el("div", "plate", close);
    logoEl(plate);
    el("div", "t", close, V.app_name || V.title);
    if (V.closing && V.closing !== V.app_name) el("div", "s", close, V.closing);
    el("div", "line", close);
    const t1 = last.end + 0.5;
    anim(close, [{ opacity: 0 }, { opacity: 1 }], t1, 0.8);
    rise(plate, t1 + 0.3, 0.7, 20);
    const bar = el("div", "progress", stage);
    anim(bar, [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], 0, V.duration, { ease: "linear" });
  }

  function build() {
    const stage = document.getElementById("stage");
    const brand = V.brand || {};
    if (brand.primary) stage.style.setProperty("--brand", brand.primary);
    if (brand.primary2) stage.style.setProperty("--brand2", brand.primary2);
    if (brand.accent) stage.style.setProperty("--accent", brand.accent);
    if (brand.accent2) stage.style.setProperty("--accent2", brand.accent2);
    document.body.className = window.RENDER ? "" : "preview";
    const cam = el("div", "", stage);
    cam.id = "cam";
    studio(cam);
    const sign = el("div", "sign", cam);
    logoEl(sign);
    display(cam);
    const people = S("svg", { viewBox: "0 0 1920 1080" }, cam);
    const cast = V.cast.map((c, i) => person(c, i, people));
    TICKS.push((t) => cast.forEach((P, i) => animatePerson(P, i, t)));
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
    await Promise.all([...document.images].map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));
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

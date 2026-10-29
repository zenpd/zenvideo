// The Hi-tech style's composition: every scene of window.VIDEO (the timeline from explainer.voice.narrate) built as DOM,
// all motion on ONE paused GSAP timeline registered as window.__timelines.main (HyperFrames seeks it frame by frame),
// and WebGL shader transitions between the scenes (@hyperframes/shader-transitions). Items appear at their cue times -
// when their words are spoken.
(() => {
  const V = window.VIDEO;
  const ICON = V.icons || {};
  const D = V.duration;
  const tl = gsap.timeline({ paused: true });
  const SHADERS = ["domain-warp", "cinematic-zoom", "light-leak", "whip-pan", "cross-warp-morph", "sdf-iris",
                   "chromatic-split", "glitch", "gravitational-lens", "ripple-waves"];

  // ── helpers ────────────────────────────────────────────────────────────────
  function el(tag, cls, parent, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }
  const icon = (name, cls, parent) => el("i", "ic " + (cls || ""), parent, String.fromCodePoint(ICON[name] || ICON.check || 0xE73E));
  const F = (n, from, to, at) => tl.fromTo(n, from, Object.assign({ ease: "power3.out" }, to), at);
  const rise = (n, at, d = 0.8, y = 50) => F(n, { opacity: 0, y }, { opacity: 1, y: 0, duration: d }, at);
  const pop = (n, at, d = 0.7) => F(n, { opacity: 0, scale: 0.55 }, { opacity: 1, scale: 1, duration: d, ease: "back.out(1.7)" }, at);
  const slide = (n, at, x, d = 0.8) => F(n, { opacity: 0, x }, { opacity: 1, x: 0, duration: d, ease: "power4.out" }, at);
  const fadeOut = (n, at, d = 0.4) => tl.to(n, { opacity: 0, duration: d, ease: "power2.in" }, at);
  // a headline as one span per word, the highlighted words in the accent gradient
  function words(parent, text, highlight) {
    const hl = (highlight || "").toLowerCase().split(/\s+/).filter(Boolean);
    const list = String(text || "").split(/\s+/).filter(Boolean);
    return list.map((w, i) => {
      const s = el("span", "w", parent, w + (i < list.length - 1 ? " " : ""));
      if (hl.includes(w.toLowerCase().replace(/[^\w%$-]/g, ""))) s.classList.add("grad");
      return s;
    });
  }
  const riseWords = (spans, at, step = 0.07) =>
    spans.length && tl.fromTo(spans, { opacity: 0, y: 80, rotation: 5 },
      { opacity: 1, y: 0, rotation: 0, duration: 0.9, stagger: step, ease: "power4.out" }, at);
  // smaller type for long text (layout is fixed: nothing is measured, so frames never depend on font loading)
  const sized = (n, text, base, chars, floor) => {
    const len = String(text || "").length;
    n.style.fontSize = Math.max(floor, Math.round(len > chars ? base * Math.sqrt(chars / len) : base)) + "px";
  };
  function countUp(n, value, at, dur = 1.3) {
    const m = String(value).match(/^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/);
    if (!m) { n.textContent = value; return; }
    const [, pre, num, post] = m;
    const target = parseFloat(num.replace(/,/g, ""));
    const dec = (num.split(".")[1] || "").length;
    const commas = num.includes(",");
    const fmt = (v) => pre + (commas ? Number(v.toFixed(dec)).toLocaleString("en-US", { minimumFractionDigits: dec })
      : v.toFixed(dec)) + post;
    const o = { v: 0 };
    n.textContent = fmt(0);
    tl.fromTo(o, { v: 0 }, { v: target, duration: dur, ease: "power2.out", onUpdate: () => { n.textContent = fmt(o.v); } }, at);
  }
  function heading(pad, s) {
    if (!s.title) return null;
    const h = el("div", "h", pad);
    sized(h, s.title, 70, 40, 46);
    riseWords(words(h, s.title), s.start + 0.25, 0.06);
    return h;
  }

  // ── the scenes ─────────────────────────────────────────────────────────────
  const SCENES = {
    title(s, pad, scene) {
      pad.classList.add("center");
      [620, 900, 1200].forEach((d, i) => {
        const r = el("div", "ring", scene);
        Object.assign(r.style, { width: d + "px", height: d + "px", marginLeft: -d / 2 + "px", marginTop: -d / 2 + "px" });
        F(r, { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 1.6 }, s.start + 0.1 + i * 0.15);
        tl.fromTo(r, { rotation: 0 }, { rotation: i % 2 ? -25 : 25, duration: Math.max(1, s.end - s.start), ease: "none" }, s.start);
      });
      if (V.logo) {
        const plate = el("div", "logo-plate", pad);
        const im = el("img", "", plate); im.src = V.logo; im.alt = "";
        pop(plate, s.start + 0.2);
      }
      if (s.kicker) rise(el("div", "kicker", pad, s.kicker), s.start + 0.35, 0.7, 20);
      const t = el("div", "title", pad);
      sized(t, s.title, 128, 22, 76);
      riseWords(words(t, s.title), s.start + 0.5, 0.09);
      F(el("div", "bar", pad), { scaleX: 0 }, { scaleX: 1, duration: 1.0, ease: "power2.inOut" }, s.start + 1.1);
      if (s.subtitle) rise(el("div", "subtitle muted", pad, s.subtitle), s.start + 1.3);
    },
    statement(s, pad) {
      pad.classList.add("center");
      if (s.icon) {
        const b = el("div", "chip badge", pad);
        icon(s.icon, "", b);
        pop(b, s.start + 0.2, 0.8);
        tl.fromTo(b, { y: 0 }, { y: -14, duration: 1.6, ease: "sine.inOut", yoyo: true,
          repeat: Math.max(0, Math.floor((s.end - s.start - 1) / 1.6)) }, s.start + 1.0);
      }
      const t = el("div", "text", pad);
      if ((s.text || "").length > 60) t.classList.add("long");
      riseWords(words(t, s.text, s.highlight), s.start + 0.4, 0.07);
    },
    points(s, pad) {
      heading(pad, s);
      const cols = el("div", "cols", pad);
      const list = el("div", "list", cols);
      const hero = el("div", "hero", cols);
      const disc = el("div", "disc", hero);
      const orbit = el("div", "orbit", hero);
      pop(disc, s.start + 0.3, 0.9);
      tl.fromTo(orbit, { rotation: 0 }, { rotation: 120, duration: Math.max(1, s.end - s.start), ease: "none" }, s.start);
      s.items.forEach((it, i) => {
        const row = el("div", "row glass", list);
        const c = el("div", "chip", row);
        icon(it.icon, "", c);
        const txt = el("div", "txt", row, it.text);
        sized(txt, it.text, 44, 30, 30);
        slide(row, it.at, 120);
        pop(c, it.at + 0.12);
        const big = icon(it.icon, "", hero);
        F(big, { opacity: 0, scale: 0.4, rotation: -30 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.7, ease: "back.out(1.6)" }, it.at);
        const next = s.items[i + 1];
        if (next) tl.to(big, { opacity: 0, scale: 1.3, duration: 0.3, ease: "power2.in" }, next.at - 0.05);
      });
    },
    stats(s, pad) {
      heading(pad, s);
      const grid = el("div", "grid", pad);
      s.stats.forEach((st) => {
        const c = el("div", "stat glass", grid);
        const v = el("div", "value grad", c);
        countUp(v, st.value, st.at, 1.4);
        const lb = el("div", "label", c, st.label);
        pop(c, st.at - 0.1, 0.8);
        rise(lb, st.at + 0.4, 0.6, 20);
      });
    },
    steps(s, pad) {
      heading(pad, s);
      const track = el("div", "track", pad);
      const line = el("div", "line", track);
      const fill = el("div", "fill", line);
      const n = s.steps.length;
      s.steps.forEach((st, i) => {
        const step = el("div", "step", track);
        const node = el("div", "node", step);
        icon(st.icon, "", node);
        const on = el("div", "on", node);
        icon(st.icon, "", on);
        el("div", "num", node, String(i + 1));
        const name = el("div", "name", step, st.name);
        const txt = st.text ? el("div", "txt", step, st.text) : null;
        pop(node, s.start + 0.4 + i * 0.12, 0.6);
        F(on, { opacity: 0, scale: 0.3 }, { opacity: 1, scale: 1, duration: 0.6, ease: "back.out(1.8)" }, st.at);
        rise(name, st.at + 0.05, 0.6, 24);
        if (txt) rise(txt, st.at + 0.2, 0.6, 20);
        if (i > 0) tl.fromTo(fill, { scaleX: (i - 1) / (n - 1) }, { scaleX: i / (n - 1), duration: 0.55, ease: "power2.inOut",
          immediateRender: false }, st.at - 0.5);
      });
    },
    compare(s, pad) {
      heading(pad, s);
      const cols = el("div", "cols", pad);
      const before = el("div", "col glass before", cols);
      const after = el("div", "col glass after", cols);
      el("div", "lbl", before, s.before_label);
      el("div", "lbl", after, s.after_label);
      slide(before, s.start + 0.35, -100);
      slide(after, s.start + 0.5, 100);
      s.rows.forEach((r) => {
        const b = el("div", "item", before);
        el("i", "ic", b, String.fromCodePoint(0xE711));
        el("span", "", b, r.before);
        const a = el("div", "item", after);
        el("i", "ic", a, String.fromCodePoint(0xE73E));
        el("span", "", a, r.after);
        slide(b, r.at, -60, 0.6);
        slide(a, r.at + 0.4, 60, 0.6);
      });
    },
    chart(s, pad) {
      heading(pad, s);
      const plot = el("div", "plot", pad);
      const labels = el("div", "labels", pad);
      const max = Math.max(...s.bars.map((b) => b.value)) || 1;
      const unit = s.unit || "";
      s.bars.forEach((b) => {
        const bar = el("div", "bar", plot);
        const num = el("div", "num", bar);
        const col = el("div", "col", bar);
        col.style.height = Math.max(10, (b.value / max) * 520) + "px";
        el("div", "", labels, b.label);
        const txt = (unit === "$" ? "$" : "") + String(b.value) + (unit && unit !== "$" ? (unit === "%" ? "%" : " " + unit) : "");
        countUp(num, txt, b.at, 1.0);
        F(col, { scaleY: 0 }, { scaleY: 1, duration: 1.0, ease: "power3.out" }, b.at);
        F(num, { opacity: 0 }, { opacity: 1, duration: 0.4 }, b.at);
      });
      F(labels, { opacity: 0 }, { opacity: 1, duration: 0.6 }, s.start + 0.5);
      if (s.takeaway) rise(el("div", "takeaway muted", pad, s.takeaway), s.bars[s.bars.length - 1].at + 1.0, 0.7, 20);
    },
    icons(s, pad) {
      heading(pad, s);
      const grid = el("div", "grid", pad);
      const n = s.items.length;
      grid.style.gridTemplateColumns = `repeat(${n === 4 ? 4 : n >= 5 ? 3 : n}, 1fr)`;
      s.items.forEach((it) => {
        const tile = el("div", "tile glass", grid);
        if (n > 4) tile.style.height = "240px";
        const c = el("div", "chip", tile);
        icon(it.icon, "", c);
        const lb = el("div", "lbl", tile, it.label);
        sized(lb, it.label, 36, 18, 26);
        pop(tile, it.at, 0.7);
        F(c, { rotation: -40, scale: 0.5 }, { rotation: 0, scale: 1, duration: 0.8, ease: "back.out(1.7)" }, it.at + 0.1);
      });
    },
    quote(s, pad) {
      pad.classList.add("center");
      pop(el("div", "q grad", pad, "“"), s.start + 0.2, 0.8);
      const t = el("div", "text", pad);
      const spans = words(t, s.text);
      const span = Math.max(1.5, (s.voice_end - s.voice_start) * 0.7);
      riseWords(spans, s.start + 0.5, Math.min(0.12, span / Math.max(1, spans.length)));
      if (s.attribution) rise(el("div", "who", pad, "— " + s.attribution), s.start + 0.6 + span * 0.8);
    },
    closing(s, pad) {
      pad.classList.add("center");
      if (V.logo) {
        const plate = el("div", "logo-plate", pad);
        const im = el("img", "", plate); im.src = V.logo; im.alt = "";
        pop(plate, s.start + 0.25, 0.8);
      }
      const t = el("div", "title", pad);
      sized(t, s.title, 110, 24, 70);
      riseWords(words(t, s.title), s.start + 0.6, 0.08);
      if (s.subtitle) rise(el("div", "subtitle muted", pad, s.subtitle), s.start + 1.1);
      if (s.cta) {
        const cta = el("div", "cta", pad, s.cta);
        pop(cta, s.start + 1.5, 0.7);
        tl.fromTo(cta, { scale: 1 }, { scale: 1.05, duration: 0.8, ease: "sine.inOut", yoyo: true,
          repeat: Math.max(0, Math.floor((s.end - s.start - 2.3) / 0.8)) }, s.start + 2.3);
      }
    },
  };

  // ── the video ──────────────────────────────────────────────────────────────
  const root = document.getElementById("root");
  const stage = el("div", "", root);
  const GLOWS = [["var(--accent)", "18%", "22%"], ["var(--accent2)", "78%", "30%"], ["var(--accent)", "70%", "75%"],
                 ["var(--accent2)", "25%", "70%"]];
  const ids = V.scenes.map((s, k) => {
    const scene = el("div", "scene t-" + s.type, stage);
    scene.id = "sc-" + (k + 1);
    if (k) scene.style.opacity = "0";
    const [c, x, y] = GLOWS[k % GLOWS.length];
    const glow = el("div", "glow", scene);
    Object.assign(glow.style, { left: `calc(${x} - 750px)`, top: `calc(${y} - 750px)`,
      background: `radial-gradient(circle, color-mix(in srgb, ${c} 38%, transparent), transparent 62%)` });
    const dur = Math.max(1, s.end - s.start + 1);
    tl.fromTo(glow, { x: -70, y: -40, scale: 1 }, { x: 70, y: 40, scale: 1.12, duration: dur, ease: "sine.inOut" }, s.start);
    el("div", "dots", scene);
    const floor = el("div", "floor", scene);
    const grid = el("div", "g", floor);
    tl.fromTo(grid, { y: 0 }, { y: 90, duration: 1.6, ease: "none", repeat: Math.ceil(dur / 1.6) }, s.start);
    const pad = el("div", "pad", scene);
    SCENES[s.type](s, pad, scene);
    tl.fromTo(pad, { scale: 1 }, { scale: 1.03, duration: dur, ease: "none" }, s.start);
    return scene.id;
  });

  // the frame around every scene: corner brackets, the brand, a progress line
  const hud = el("div", "hud", root);
  ["tl", "tr", "bl", "br"].forEach((k, i) => F(el("div", "corner " + k, hud), { opacity: 0, scale: 0.6 },
    { opacity: 1, scale: 1, duration: 0.7 }, 0.2 + i * 0.08));
  if (V.scenes.length > 2 && (V.logo || V.brand_name || V.app_name)) {
    const brand = el("div", "brand", hud);
    if (V.logo) { const im = el("img", "", brand); im.src = V.logo; im.alt = ""; }
    else el("span", "", brand, V.brand_name || V.app_name);
    F(brand, { opacity: 0, y: -16 }, { opacity: 1, y: 0, duration: 0.6 }, V.scenes[1].start + 0.4);
    fadeOut(brand, V.scenes[V.scenes.length - 1].start, 0.4);
  }
  tl.fromTo(el("div", "progress", hud), { scaleX: 0 }, { scaleX: 1, duration: D, ease: "none" }, 0);

  // scene to scene through a shader, just before the next scene's voice starts
  const transitions = V.scenes.slice(1).map((s, k) => ({ time: Math.max(0.1, s.start - 0.35),
    shader: SHADERS[k % SHADERS.length], duration: 0.8 }));
  if (window.HyperShader && transitions.length) {
    HyperShader.init({ bgColor: V.bg, accentColor: V.accent, scenes: ids, transitions, timeline: tl });
  }
  window.__timelines = window.__timelines || {};
  window.__timelines.main = tl;
})();

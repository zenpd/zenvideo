// The explainer player: builds every scene of window.VIDEO (the timeline from explainer.voice) as DOM, and every
// movement as a paused Web Animation at its absolute time. seek(t) sets all of them to second t, so the renderer can
// take any frame exactly; in a normal browser window the player plays along with the voice-over (preview).
(() => {
  const V = window.VIDEO;
  const ICON = V.icons || {};
  const ANIMS = [];
  const TICKS = [];
  const E = {
    out: "cubic-bezier(.16,1,.3,1)",        // fast in, long settle
    back: "cubic-bezier(.34,1.56,.64,1)",   // a little overshoot
    inOut: "cubic-bezier(.65,0,.35,1)",
    in: "cubic-bezier(.55,0,1,.45)",
    linear: "linear",
  };

  // ── building blocks ────────────────────────────────────────────────────────
  function el(tag, cls, parent, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }
  function icon(name, cls, parent) {
    const code = ICON[name] || ICON.check;
    return el("i", "ic " + (cls || ""), parent, String.fromCodePoint(code));
  }
  // anim(el, keyframes, at, duration): a paused animation from second `at`; fill both by default, so it holds its
  // first frame before and its last after. Animations created later win on the same property - exits use
  // fill "forwards" so they only take over once they start.
  function anim(node, frames, at, dur, opts = {}) {
    const a = node.animate(frames, {
      duration: dur * 1000, delay: at * 1000, easing: opts.ease || E.out, fill: opts.fill || "both",
      iterations: opts.iter || 1, direction: opts.dir || "normal",
    });
    a.pause();
    ANIMS.push(a);
    return a;
  }
  const rise = (n, at, d = 0.7, y = 40) =>
    anim(n, [{ opacity: 0, transform: `translateY(${y}px)` }, { opacity: 1, transform: "none" }], at, d);
  const pop = (n, at, d = 0.6) =>
    anim(n, [{ opacity: 0, transform: "scale(.5)" }, { opacity: 1, transform: "none" }], at, d, { ease: E.back });
  const fade = (n, at, d = 0.6) => anim(n, [{ opacity: 0 }, { opacity: 1 }], at, d);
  const slide = (n, at, x, d = 0.7) =>
    anim(n, [{ opacity: 0, transform: `translateX(${x}px)` }, { opacity: 1, transform: "none" }], at, d);

  // words: text as one span per word, so they can rise one after another
  function words(parent, text, highlight) {
    const spans = [];
    const hl = (highlight || "").toLowerCase().split(/\s+/).filter(Boolean);
    const list = text.split(/\s+/).filter(Boolean);
    list.forEach((w, i) => {
      const s = el("span", "w", parent, w + (i < list.length - 1 ? " " : ""));
      if (hl.length && hl.includes(w.toLowerCase().replace(/[^\w%$-]/g, ""))) {
        s.classList.add("hl");
        s.textContent = w;
        el("span", "mark", s);
        if (i < list.length - 1) el("span", "w", parent, " ");
      }
      spans.push(s);
    });
    return spans;
  }
  const riseWords = (spans, at, step = 0.06) =>
    spans.forEach((s, i) => anim(s, [{ opacity: 0, transform: "translateY(45%)" }, { opacity: 1, transform: "none" }],
      at + i * step, 0.7));

  // fit: shrink an element's font until it takes at most `lines` lines
  function fit(n, lines, min = 24) {
    let size = parseFloat(getComputedStyle(n).fontSize);
    const lh = () => parseFloat(getComputedStyle(n).lineHeight) || size * 1.15;
    while (size > min && n.getBoundingClientRect().height > lh() * lines + 2) {
      size -= 3;
      n.style.fontSize = size + "px";
    }
  }

  // count-up: "$1.2M" counts 0 -> 1.2 keeping "$" and "M", with the same decimals
  function countUp(node, value, at, dur = 1.3) {
    const m = String(value).match(/^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/);
    if (!m) { node.textContent = value; return; }
    const [, pre, num, post] = m;
    const target = parseFloat(num.replace(/,/g, ""));
    const decimals = (num.split(".")[1] || "").length;
    const commas = num.includes(",");
    const fmt = (v) => {
      let s = v.toFixed(decimals);
      if (commas) s = Number(s).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      return pre + s + post;
    };
    node.textContent = fmt(target);
    TICKS.push((t) => {
      const p = Math.min(1, Math.max(0, (t - at) / dur));
      node.textContent = fmt(target * (1 - Math.pow(1 - p, 3)));
    });
  }

  function heading(pad, s, at) {
    if (!s.title) return null;
    const h = el("div", "h", pad);
    riseWords(words(h, s.title), at);
    return h;
  }

  // ── the scenes ─────────────────────────────────────────────────────────────
  const SCENES = {
    title(s, pad) {
      pad.classList.add("center");
      [560, 820, 1100].forEach((d, i) => {
        const r = el("div", "ring", pad.parentNode);
        Object.assign(r.style, { width: d + "px", height: d + "px", marginLeft: -d / 2 + "px", marginTop: -d / 2 + "px" });
        anim(r, [{ opacity: 0, transform: "scale(.6)" }, { opacity: 1, transform: "none" }], s.start + 0.1 + i * 0.15, 1.4);
      });
      if (s.kicker) pop(el("div", "kicker", pad, s.kicker), s.start + 0.25);
      const t = el("div", "title", pad);
      const spans = words(t, s.title);
      fit(t, 2, 60);
      riseWords(spans, s.start + 0.45, 0.08);
      const u = el("div", "underline", pad);
      anim(u, [{ transform: "scaleX(0)" }, { transform: "none" }], s.start + 1.0, 0.9, { ease: E.inOut });
      if (s.subtitle) {
        const sub = el("div", "subtitle muted", pad, s.subtitle);
        sub.style.marginTop = "34px";
        rise(sub, s.start + 1.2);
      }
    },

    statement(s, pad) {
      pad.classList.add("center");
      if (s.icon) {
        const b = el("div", "badge bigicon", pad);
        icon(s.icon, "", b);
        pop(b, s.start + 0.2, 0.7);
        anim(b, [{ transform: "translateY(0)" }, { transform: "translateY(-14px)" }], s.start + 0.9, 1.8,
          { ease: E.inOut, iter: Infinity, dir: "alternate", fill: "forwards" });
      }
      const t = el("div", "text", pad);
      const spans = words(t, s.text, s.highlight);
      fit(t, 3, 48);
      riseWords(spans, s.start + 0.4, 0.07);
      t.querySelectorAll(".mark").forEach((m) =>
        anim(m, [{ transform: "scaleX(0)" }, { transform: "none" }], s.voice_start + 0.9, 0.7, { ease: E.inOut }));
    },

    points(s, pad) {
      heading(pad, s, s.start + 0.2);
      const cols = el("div", "cols", pad);
      const list = el("div", "list", cols);
      const hero = el("div", "hero", cols);
      const disc = el("div", "disc", hero);
      pop(disc, s.start + 0.3, 0.9);
      anim(disc, [{ transform: "rotate(0deg)" }, { transform: "rotate(360deg)" }], s.start, 40,
        { ease: E.linear, fill: "forwards", iter: Infinity });
      s.items.forEach((it, i) => {
        const row = el("div", "row card", list);
        row.style.position = "relative";
        const b = el("div", "badge", row);
        icon(it.icon, "", b);
        const txt = el("div", "txt", row, it.text);
        fit(txt, 2, 28);
        slide(row, it.at, 90);
        pop(b, it.at + 0.1);
        const glow = el("div", "", row);
        Object.assign(glow.style, { position: "absolute", inset: "-2px", borderRadius: "32px",
          border: "3px solid var(--accent)", pointerEvents: "none" });
        anim(glow, [{ opacity: 0 }, { opacity: 1 }], it.at, 0.4);
        const next = s.items[i + 1];
        if (next) anim(glow, [{ opacity: 1 }, { opacity: 0 }], next.at, 0.4, { fill: "forwards" });
        const big = icon(it.icon, "", hero);
        anim(big, [{ opacity: 0, transform: "scale(.4) rotate(-25deg)" }, { opacity: 1, transform: "none" }], it.at, 0.7,
          { ease: E.back });
        if (next) anim(big, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "scale(1.3)" }], next.at - 0.05, 0.35,
          { fill: "forwards", ease: E.in });
      });
    },

    stats(s, pad) {
      heading(pad, s, s.start + 0.2);
      const grid = el("div", "grid", pad);
      s.stats.forEach((st) => {
        const c = el("div", "stat card", grid);
        const m = String(st.value).match(/(\d+(?:\.\d+)?)\s*%/);
        if (m && parseFloat(m[1]) <= 100) {     // a percentage: a ring fills to it
          const ns = "http://www.w3.org/2000/svg";
          const svg = document.createElementNS(ns, "svg");
          svg.setAttribute("viewBox", "0 0 100 100");
          const mk = (stroke, w) => {
            const ci = document.createElementNS(ns, "circle");
            Object.entries({ cx: 50, cy: 50, r: 46, fill: "none", stroke, "stroke-width": w, "stroke-linecap": "round",
              pathLength: 100, transform: "rotate(-90 50 50)" }).forEach(([k, v]) => ci.setAttribute(k, v));
            svg.appendChild(ci);
            return ci;
          };
          mk("var(--card-line)", 2.5);
          const arc = mk("var(--accent)", 2.5);
          arc.setAttribute("stroke-dasharray", "100 100");
          c.appendChild(svg);
          anim(arc, [{ strokeDashoffset: 100 }, { strokeDashoffset: 100 - parseFloat(m[1]) }], st.at, 1.3);
        }
        const v = el("div", "value grad", c);
        countUp(v, st.value, st.at, 1.3);
        const lb = el("div", "label", c, st.label);
        fit(lb, 3, 24);
        pop(c, st.at - 0.1, 0.7);
        rise(lb, st.at + 0.4, 0.6, 20);
      });
    },

    steps(s, pad) {
      heading(pad, s, s.start + 0.2);
      const track = el("div", "track", pad);
      const line = el("div", "line", track);
      Object.assign(line.style, { left: "150px", right: "150px" });
      const fillBar = el("div", "fill", line);
      const n = s.steps.length;
      anim(fillBar, [{ transform: "scaleX(0)" }, { transform: "scaleX(0)" }], s.start, 0.1);
      s.steps.forEach((st, i) => {
        const step = el("div", "step", track);
        const node = el("div", "node", step);
        icon(st.icon, "", node);
        const on = el("div", "on", node);
        icon(st.icon, "", on);
        el("div", "num", node, String(i + 1));
        const name = el("div", "name", step, st.name);
        const txt = st.text ? el("div", "txt", step, st.text) : null;
        if (txt) fit(txt, 3, 20);
        fit(name, 2, 24);
        pop(node, s.start + 0.4 + i * 0.12, 0.6);
        anim(on, [{ opacity: 0, transform: "scale(.4)" }, { opacity: 1, transform: "none" }], st.at, 0.6, { ease: E.back });
        rise(name, st.at + 0.05, 0.6, 24);
        if (txt) rise(txt, st.at + 0.2, 0.6, 20);
        if (i > 0) {
          const from = (i - 1) / (n - 1), to = i / (n - 1);
          anim(fillBar, [{ transform: `scaleX(${from})` }, { transform: `scaleX(${to})` }], st.at - 0.5, 0.55,
            { fill: "forwards", ease: E.inOut });
        }
      });
    },

    compare(s, pad) {
      heading(pad, s, s.start + 0.2);
      const cols = el("div", "cols", pad);
      const before = el("div", "col card before", cols);
      const after = el("div", "col card after", cols);
      el("div", "lbl", before, s.before_label);
      el("div", "lbl", after, s.after_label);
      const vs = el("div", "badge vs", cols);
      icon("sync", "", vs);
      slide(before, s.start + 0.35, -80);
      slide(after, s.start + 0.5, 80);
      pop(vs, s.start + 0.8);
      s.rows.forEach((r) => {
        const b = el("div", "item", before);
        el("i", "ic", b, String.fromCodePoint(0xE711));          // cross
        el("span", "", b, r.before);
        const a = el("div", "item", after);
        el("i", "ic", a, String.fromCodePoint(0xE73E));          // check mark
        el("span", "", a, r.after);
        slide(b, r.at, -50, 0.6);
        slide(a, r.at + 0.4, 50, 0.6);
      });
    },

    chart(s, pad) {
      heading(pad, s, s.start + 0.2);
      const plot = el("div", "plot", pad);
      const labels = el("div", "labels", pad);
      const take = s.takeaway ? el("div", "takeaway muted", pad, s.takeaway) : null;
      const max = Math.max(...s.bars.map((b) => b.value)) || 1;
      const unit = s.unit || "";
      const h = plot.getBoundingClientRect().height - 80;
      s.bars.forEach((b) => {
        const bar = el("div", "bar", plot);
        const num = el("div", "num", bar);
        const col = el("div", "col", bar);
        col.style.height = Math.max(8, (b.value / max) * h) + "px";
        el("div", "", labels, b.label);
        const txt = (unit === "$" ? "$" : "") + String(b.value) + (unit && unit !== "$" ? (unit === "%" ? "%" : " " + unit) : "");
        countUp(num, txt, b.at, 1.0);
        anim(col, [{ transform: "scaleY(0)" }, { transform: "none" }], b.at, 1.0);
        fade(num, b.at, 0.4);
      });
      fade(labels, s.start + 0.5);
      if (take) rise(take, s.bars[s.bars.length - 1].at + 1.0, 0.7, 20);
    },

    icons(s, pad) {
      heading(pad, s, s.start + 0.2);
      const grid = el("div", "grid", pad);
      const n = s.items.length;
      const cols = n === 4 ? 4 : n === 5 || n === 6 ? 3 : n;
      grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
      s.items.forEach((it) => {
        const tile = el("div", "tile card", grid);
        if (n > 4) tile.style.height = "250px";
        const b = el("div", "badge", tile);
        icon(it.icon, "", b);
        const lb = el("div", "lbl", tile, it.label);
        fit(lb, 2, 24);
        pop(tile, it.at, 0.65);
        anim(b, [{ transform: "rotate(-35deg) scale(.6)" }, { transform: "none" }], it.at + 0.1, 0.7, { ease: E.back });
      });
    },

    quote(s, pad) {
      pad.classList.add("center");
      const q = el("div", "q grad", pad, "“");
      pop(q, s.start + 0.2, 0.8);
      const t = el("div", "text", pad);
      const spans = words(t, s.text);
      fit(t, 4, 40);
      const span = Math.max(1.5, (s.voice_end - s.voice_start) * 0.7);
      riseWords(spans, s.start + 0.5, Math.min(0.12, span / spans.length));
      if (s.attribution) rise(el("div", "who", pad, "— " + s.attribution), s.start + 0.6 + span * 0.8);
    },

    closing(s, pad) {
      pad.classList.add("center");
      const name = V.app_name || s.title || "";
      const logo = el("div", "badge logo", pad, (name.trim()[0] || "•").toUpperCase());
      pop(logo, s.start + 0.25, 0.8);
      const t = el("div", "title", pad);
      const spans = words(t, s.title);
      fit(t, 2, 56);
      riseWords(spans, s.start + 0.6, 0.08);
      if (s.subtitle) rise(el("div", "subtitle muted", pad, s.subtitle), s.start + 1.1);
      if (s.cta) {
        const cta = el("div", "cta", pad, s.cta);
        const glow = el("div", "glow", cta);
        pop(cta, s.start + 1.5, 0.7);
        anim(glow, [{ opacity: 0.9, transform: "none" }, { opacity: 0, transform: "scale(1.25, 1.6)" }], s.start + 2.3, 1.6,
          { iter: Infinity, fill: "forwards", ease: E.out });
      }
    },
  };

  // ── the whole video ────────────────────────────────────────────────────────
  function build() {
    const stage = document.getElementById("stage");
    stage.className = "theme-" + (V.theme || "midnight");
    document.body.className = stage.className + (window.RENDER ? "" : " preview");

    const bg = el("div", "bg", stage);
    const dots = el("div", "dots", bg);
    anim(dots, [{ transform: "translate(0,0)" }, { transform: "translate(44px,44px)" }], 0, 9,
      { ease: E.linear, iter: Infinity });
    [["b1", 120, 70, 17], ["b2", -140, -60, 21], ["b3", -90, 110, 13]].forEach(([c, x, y, d]) =>
      anim(el("div", "blob " + c, bg), [{ transform: "translate(0,0) scale(1)" },
        { transform: `translate(${x}px,${y}px) scale(1.12)` }], 0, d, { ease: E.inOut, iter: Infinity, dir: "alternate" }));

    V.scenes.forEach((s, i) => {
      const root = el("div", "scene t-" + s.type, stage);
      const cam = el("div", "cam", root);
      const pad = el("div", "pad", cam);
      SCENES[s.type](s, pad);
      const last = i === V.scenes.length - 1;
      anim(root, [{ opacity: 0, transform: "translateY(36px) scale(.985)" }, { opacity: 1, transform: "none" }],
        s.start, 0.65);
      if (!last) anim(root, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-30px) scale(1.02)" }],
        s.end - 0.15, 0.5, { fill: "forwards", ease: E.in });
      anim(cam, [{ transform: "scale(1)" }, { transform: "scale(1.035)" }], s.start, Math.max(1, s.end - s.start + 0.5),
        { ease: E.linear });
      TICKS.push((t) => { root.style.visibility = t >= s.start - 0.02 && (last || t <= s.end + 0.4) ? "visible" : "hidden"; });
    });

    if (V.app_name && V.scenes.length > 2) {
      const brand = el("div", "brand", stage);
      el("div", "mark", brand, V.app_name.trim()[0].toUpperCase());
      el("span", "", brand, V.app_name);
      const from = V.scenes[1].start + 0.3, to = V.scenes[V.scenes.length - 1].start;
      anim(brand, [{ opacity: 0, transform: "translateY(-20px)" }, { opacity: 1, transform: "none" }], from, 0.6);
      anim(brand, [{ opacity: 1 }, { opacity: 0 }], to, 0.4, { fill: "forwards" });
    }
    const bar = el("div", "progress", stage);
    anim(bar, [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], 0, V.duration, { ease: E.linear });
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
    window.seek(0);
    window.READY = true;
    if (!window.RENDER) preview();
  }

  // preview: the voice-over plays and the animation follows it
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
      if (!audio.paused) {
        window.seek(audio.currentTime);
        range.value = audio.currentTime;
      }
      time.textContent = `${clock(+range.value)} / ${clock(V.duration)}`;
      requestAnimationFrame(loop);
    };
    loop();
  }

  start();
})();

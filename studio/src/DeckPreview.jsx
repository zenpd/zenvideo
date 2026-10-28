/* Miniature slides for the deck design cards: each design's cover and two content slides, drawn from the same
   geometry (inches) as demo/deck_layouts.py, with the video's title and its poster frame as the screenshot. */

const SERIF = 'Cambria, "Bookman Old Style", Georgia, serif';

// Element builders (inches). Text sizes are points, like the real slides.
const R = (x, y, w, h, fill, o = {}) => ({ k: "box", x, y, w, h, fill, ...o });
const C = (x, y, d, fill, o = {}) => ({ k: "box", x, y, w: d, h: d, fill, round: true, ...o });
const T = (x, y, w, h, text, pt, color, o = {}) => ({ k: "text", x, y, w, h, text, pt, color, ...o });
const L = (x, y, w, n, pt, color, o = {}) => ({ k: "lines", x, y, w, n, pt, color, ...o });   // placeholder lines
const S = (x, y, w, h, o = {}) => ({ k: "shot", x, y, w, h, ...o });

/** Shrink pt (roughly, by character count) until text fits in maxLines lines of w inches. */
function fitPt(text, w, pt, maxLines, floor) {
  let size = pt;
  const lines = (s) => Math.ceil((text.length * s * 0.62) / 72 / w);   // 0.62 em: a wide bold face, to be safe
  while (size > floor && lines(size) > maxLines) size -= 1;
  return size;
}

function zen(title) {
  const ink = "#1A1030", accent = "#6C5CE7", muted = "#c9c4d8";
  const head = (k, t) => [T(0.5, 0.5, 6, 0.32, k, 12.5, accent, { bold: true }), T(0.5, 0.95, 6.4, 1.1, t, 30, ink, { bold: true })];
  return {
    W: 13.333, H: 7.5, panel: ["#F4F2FC", "#6C5CE7"],
    cover: { bg: "linear-gradient(165deg, #1A1030 0%, #2a1b63 58%, #5b45d6 100%)", els: [
      R(6.36, 1.55, 0.62, 0.62, accent, { r: 0.12 }), T(6.36, 1.55, 0.62, 0.62, "▶", 16, "#fff", { align: "center", valign: "middle" }),
      T(0.5, 2.35, 12.33, 1.1, title, fitPt(title, 12.3, 54, 1, 30), "#fff", { bold: true, align: "center" }),
      L(4.2, 3.6, 5, 1, 19, "#8B7FF0", { align: "center" }), L(3.2, 4.4, 7, 2, 13.5, "rgba(216,210,240,.55)", { align: "center" })] },
    pages: [
      { bg: "#fff", els: [...head("THE PROBLEM", "Why it's hard today"),
        ...[0, 1, 2].flatMap((i) => [C(0.5, 2.6 + i * 1.38, 0.46, accent), L(1.15, 2.6 + i * 1.38, 4.4, 2, 13, muted)]),
        S(6.35, 2.55, 6.5, 3.05, { frame: true })] },
      { bg: "#fff", els: [...head("FEATURE · 1 OF 4", "Do it all from one screen"), L(0.5, 2.4, 5.6, 4, 14, muted),
        S(6.9, 2.0, 6.0, 3.38, { frame: true })] },
    ],
  };
}

function consulting(title) {
  const navy = "#0B1F3A", teal = "#1B998B", tint = "#F2F4F7", gray = "#c3c8cf";
  const chrome = (t) => [T(0.5, 0.5, 9, 0.85, t, 20, navy, { bold: true }), L(0.5, 5.2, 2.5, 1, 10, gray)];
  return {
    W: 10, H: 5.625, panel: ["#F2F4F7", "#1B998B"],
    cover: { bg: "#fff", els: [
      R(0, 3.55, 10, 2.075, navy), T(0.6, 0.45, 4, 0.3, "PRODUCT BRIEFING", 11, teal, { bold: true, track: 3 }),
      T(0.6, 0.9, 8.6, 1.6, title, fitPt(title, 8.6, 34, 2, 22), navy, { bold: true, valign: "bottom" }),
      L(0.6, 2.72, 4.5, 1, 16, gray), L(0.6, 3.95, 7.5, 2, 14, "rgba(255,255,255,.5)")] },
    pages: [
      { bg: "#fff", els: [...chrome("Teams lose hours to hand-offs between disconnected systems"),
        ...[0, 1, 2].flatMap((i) => [R(0.5, 1.55 + i * 1.15, 1.75, 1, navy), L(0.75, 1.9 + i * 1.15, 1.25, 1, 13, "rgba(255,255,255,.75)"),
          R(2.35, 1.55 + i * 1.15, 3.55, 1, tint), L(2.55, 1.75 + i * 1.15, 3.1, 3, 12, gray)]),
        S(6.2, 1.55, 3.3, 1.86, { border: "#D1D5DB" }), R(6.2, 3.88, 3.3, 1.12, navy), L(6.4, 4.05, 1.2, 1, 10, teal)] },
      { bg: "#fff", els: [...chrome("Raise a request in one step"), S(0.5, 1.5, 6, 3.375, { border: "#D1D5DB" }),
        R(6.75, 1.5, 2.75, 3.375, navy), L(7.0, 1.75, 1.4, 1, 11, teal), L(7.0, 2.3, 2.25, 6, 13, "rgba(255,255,255,.6)")] },
    ],
  };
}

function pitchDark(title) {
  const bg = "#0E0E12", card = "#1C1C26", orange = "#FF5A36", lav = "#B8B5FF", muted = "#5d5d66";
  const head = (k, t) => [T(0.6, 0.45, 8.8, 0.3, k, 12, orange, { bold: true, track: 3 }), T(0.6, 0.8, 8.8, 1.1, t, 30, "#fff", { bold: true })];
  return {
    W: 10, H: 5.625, panel: ["#1C1C26", "#FF5A36"],
    cover: { bg, els: [
      C(6.0, -1.0, 5.2, orange), C(5.3, 3.5, 1.5, lav),
      T(0.6, 0.5, 5.2, 2.0, title, fitPt(title, 5.2, 66, 2, 34), "#fff", { bold: true, valign: "bottom" }),
      L(0.6, 2.75, 3.6, 2, 20, muted), T(0.6, 4.6, 4.6, 0.4, "PRODUCT DEMO", 12, lav, { bold: true, track: 2 })] },
    pages: [
      { bg, els: [...head("THE PROBLEM", "Why it's hard today"),
        ...[0, 1, 2].flatMap((i) => [T(0.6 + i * 3.05, 2.3, 2.8, 0.9, `0${i + 1}`, 54, i ? "#fff" : orange, { bold: true }),
          L(0.6 + i * 3.05, 3.4, 2.4, 3, 13, muted)])] },
      { bg, els: [...head("FEATURE · 1 / 4", "Do it all from one screen"), L(0.6, 1.95, 3.6, 5, 15, muted),
        S(4.6, 1.9, 4.8, 2.7, { r: 0.12 }), ...[0, 1, 2, 3].map((i) => R(0.6 + i * 2.2, 4.7, 2.1, 0.3, i ? card : orange, { r: 0.15 }))] },
    ],
  };
}

function editorial(title) {
  const ink = "#1D2433", gold = "#C98B2B", gray = "#c5c9d0";
  return {
    W: 10, H: 5.625, panel: ["#F5EFE4", "#C98B2B"],
    cover: { bg: "#fff", els: [
      R(0, 0, 4.6, 5.625, ink), T(0.6, 0.6, 3.6, 0.3, "PRODUCT OVERVIEW", 12, "#fff", { bold: true, track: 4 }),
      T(0.5, 3.3, 4, 1.5, String(new Date().getFullYear()), 96, gold, { serif: true, valign: "bottom" }),
      T(5.1, 0.6, 4.4, 2.4, title, fitPt(title, 4.4, 40, 3, 24), ink, { serif: true, valign: "bottom" }), L(5.1, 3.25, 3.2, 1, 16, gray)] },
    pages: [
      { bg: "#fff", els: [
        R(5.4, 0, 4.6, 5.625, ink), T(5.9, 0.55, 3, 1, "01", 60, gold, { serif: true }),
        T(5.9, 1.65, 3.6, 1.3, "How it works", 28, "#fff", { serif: true }), L(5.9, 2.4, 3.4, 4, 14, "rgba(214,220,229,.45)"),
        T(0.6, 0.4, 4, 0.3, "THE SOLUTION", 11, gold, { bold: true, track: 3 }), S(0.6, 0.9, 4.4, 2.475),
        ...[0, 1, 2].flatMap((i) => [T(0.6, 3.65 + i * 0.42, 0.45, 0.35, `0${i + 1}`, 14, gold, { serif: true }), L(1.1, 3.72 + i * 0.42, 1.8, 1, 13, gray)])] },
      { bg: gold, els: [
        T(0.8, 0.2, 2, 1.8, "“", 160, ink, { serif: true }),
        T(0.8, 1.6, 8.2, 2.4, "One place for every step of the work.", 32, ink, { serif: true, italic: true }),
        L(0.8, 4.25, 2.4, 1, 14, "rgba(29,36,51,.55)")] },
    ],
  };
}

function dashboard(title) {
  const navy = "#233044", canvas = "#EEF1F5", accents = ["#6D28D9", "#14B8A6", "#F59E0B", "#22C55E"], gray = "#c7ccd6";
  const tile = (x, y, w, h) => R(x, y, w, h, "#fff", { r: 0.08, shadow: true });
  const chrome = (t) => [T(0.5, 0.25, 6.5, 0.55, t, 24, navy, { bold: true, valign: "middle" }), L(7.6, 0.45, 1.9, 1, 12, gray)];
  return {
    W: 10, H: 5.625, panel: ["#EEF1F5", "#6D28D9"],
    cover: { bg: navy, els: [
      T(0.6, 0.6, 4.8, 2.2, title, fitPt(title, 4.8, 36, 3, 22), "#fff", { bold: true, valign: "bottom" }),
      L(0.6, 3.0, 3.6, 1, 22, accents[1]), L(0.6, 3.8, 4.4, 2, 12, "rgba(203,213,225,.5)"),
      ...[[5.9, 0.7, 1.7, 1.1], [7.8, 0.7, 1.7, 1.1], [5.9, 2.0, 3.6, 1.6], [5.9, 3.8, 1.7, 1.1], [7.8, 3.8, 1.7, 1.1]]
        .map(([x, y, w, h]) => R(x, y, w, h, "#2E3D55", { r: 0.08 })),
      ...[0.5, 0.75, 0.6, 0.95, 0.8, 1.15, 1.0].map((v, i) => R(6.2 + i * 0.45, 3.35 - v, 0.28, v, i === 6 ? accents[1] : accents[0])),
      ...[[6.15, 0.95, 1], [8.05, 0.95, 2], [6.15, 4.05, 3], [8.05, 4.05, 0]].flatMap(([x, y, c]) =>
        [R(x, y, 0.7, 0.12, accents[c]), R(x, y + 0.3, 1.1, 0.25, "#3B4C68")])] },
    pages: [
      { bg: canvas, els: [...chrome("Why it's hard today"),
        ...[0, 1, 2].flatMap((i) => [tile(0.5, 1.0 + i * 1.38, 2.9, 1.25), R(0.7, 1.14 + i * 1.38, 0.5, 0.07, accents[i]),
          L(0.7, 1.32 + i * 1.38, 1.6, 1, 14, "#9aa3b2"), L(0.7, 1.65 + i * 1.38, 2.4, 2, 11, gray)]),
        tile(3.6, 1.0, 5.9, 4.05), L(3.8, 1.15, 1.6, 1, 13, "#9aa3b2"), S(3.8, 1.5, 5.5, 3.09)] },
      { bg: canvas, els: [...chrome("Why it matters"),
        ...[0, 1, 2].flatMap((i) => [tile(0.5 + i * 3.05, 1.0, 2.9, 4.05), R(0.5 + i * 3.05, 1.0, 2.9, 0.08, accents[i]),
          R(0.75 + i * 3.05, 1.35, 0.6, 0.6, accents[i], { r: 0.12 }), L(0.75 + i * 3.05, 2.2, 1.8, 1, 18, "#8c95a6"),
          L(0.75 + i * 3.05, 2.95, 2.3, 4, 13, gray)])] },
    ],
  };
}

function programme(title) {
  const teal = "#0F4C5C", orange = "#E36414", yellow = "#FFD166", gray = "#c9d0d8";
  const nav = (cur) => [R(0, 0, 2.6, 5.625, teal), L(0.4, 0.5, 1.6, 1, 11, yellow),
    ...[0, 1, 2, 3, 4].flatMap((i) => [
      ...(i === cur ? [C(0.4, 1.33 + i * 0.48, 0.14, orange)] : []),
      L(0.68, 1.3 + i * 0.48, i === cur ? 1.2 : 1.0, 1, 14, i === cur ? "#fff" : "rgba(159,193,199,.6)")])];
  const head = (t) => T(3.0, 0.4, 6.5, 0.75, t, 24, teal, { bold: true, serif: true, valign: "middle" });
  return {
    W: 10, H: 5.625, panel: ["#EEF5F6", "#E36414"],
    cover: { bg: teal, els: [
      T(0.7, 0.5, 5.4, 2.0, title, fitPt(title, 5.4, 44, 3, 24), "#fff", { bold: true, serif: true, valign: "bottom" }),
      L(0.7, 2.75, 3.8, 1, 20, yellow), L(0.7, 3.65, 4.6, 2, 12, "rgba(159,193,199,.55)"),
      ...Array.from({ length: 42 }, (_, n) => {
        const r = Math.floor(n / 6), c = n % 6, hot = [[2, 3], [4, 1], [5, 4]].some(([a, b]) => a === r && b === c);
        return C(6.8 + c * 0.5, 1.0 + r * 0.5, 0.2, hot ? orange : "rgba(95,158,160,.7)");
      })] },
    pages: [
      { bg: "#fff", els: [...nav(0), head("Why it's hard today"),
        ...[0, 1, 2].flatMap((i) => [C(3.0, 1.45 + i * 1.18, 0.55, orange), L(3.8, 1.42 + i * 1.18, 2.4, 1, 16, "#7aa3ad"),
          L(3.8, 1.8 + i * 1.18, 5.4, 2, 13, gray)])] },
      { bg: "#fff", els: [...nav(2), head("Do it all from one screen"), L(3.0, 1.32, 2.0, 1, 11, orange),
        L(3.0, 1.65, 6.4, 2, 13, gray), S(3.0, 2.5, 4.5, 2.53, { border: "#E2E8F0" }), R(7.75, 2.5, 0.5, 0.06, orange),
        L(7.75, 2.7, 1.6, 3, 12, gray)] },
    ],
  };
}

const SPECS = { zen, consulting, "pitch-dark": pitchDark, editorial, dashboard, programme };

function Slide({ spec, slide, shot, textOnly, className }) {
  const { W, H } = spec;
  const pos = (e) => ({ left: `${(e.x / W) * 100}%`, top: `${(e.y / H) * 100}%`, width: `${(e.w / W) * 100}%`, height: `${(e.h / H) * 100}%` });
  const size = (pt) => `${((pt / 72) / W) * 100}cqw`;
  const radius = (e) => (e.round ? "50%" : e.r ? `${((e.r / W) * 100).toFixed(2)}cqw` : undefined);
  return (
    <div className={`dp-slide ${className || ""}`} style={{ aspectRatio: `${W} / ${H}`, background: slide.bg }}>
      {slide.els.map((e, i) => {
        if (e.k === "box") {
          return <i key={i} style={{ ...pos(e), background: e.fill, borderRadius: radius(e),
            boxShadow: e.shadow ? "0 0.4cqw 1.2cqw rgba(0,0,0,.08)" : undefined }} />;
        }
        if (e.k === "lines") {
          const lh = (e.pt * 1.3) / 72;
          return Array.from({ length: e.n }, (_, j) => {
            const w = j === e.n - 1 && e.n > 1 ? e.w * 0.62 : e.w;
            const x = e.align === "center" ? e.x + (e.w - w) / 2 : e.x;
            return <i key={`${i}-${j}`} style={{ ...pos({ x, y: e.y + j * lh, w, h: (e.pt * 0.55) / 72 }), background: e.color, borderRadius: "1cqw" }} />;
          });
        }
        if (e.k === "shot" && textOnly) {   // decks from narration alone: a takeaway panel instead of a screenshot
          return (
            <span key={i} className="dp-panel" style={{ ...pos(e), borderRadius: radius(e), background: spec.panel[0], color: spec.panel[1],
              fontSize: size(Math.min(48, e.h * 20)) }}>{"“"}</span>
          );
        }
        if (e.k === "shot") {
          return (
            <span key={i} className={`dp-shot${e.frame ? " framed" : ""}`}
              style={{ ...pos(e), borderRadius: radius(e), outline: e.border ? `1px solid ${e.border}` : undefined }}>
              {shot && <img src={shot} alt="" loading="lazy" />}
            </span>
          );
        }
        return (
          <span key={i} className="dp-text" style={{
            ...pos(e), fontSize: size(e.pt), color: e.color, fontWeight: e.bold ? 700 : 400, fontStyle: e.italic ? "italic" : undefined,
            fontFamily: e.serif ? SERIF : undefined, textAlign: e.align || "left", letterSpacing: e.track ? size(e.track) : undefined,
            justifyContent: { middle: "center", bottom: "flex-end" }[e.valign] || "flex-start",
          }}>{e.text}</span>
        );
      })}
    </div>
  );
}

/** Cover plus two content slides of one design; textOnly shows the takeaway panels a deck without screenshots has. */
export default function DeckPreview({ template, title, shot, textOnly }) {
  const make = SPECS[template];
  if (!make) return <div className="dp-empty" />;
  const spec = make(title || "Your product");
  return (
    <div className="dp" aria-hidden="true">
      <Slide spec={spec} slide={spec.cover} shot={shot} textOnly={textOnly} className="dp-cover" />
      <div className="dp-side">
        {spec.pages.map((p, i) => <Slide key={i} spec={spec} slide={p} shot={shot} textOnly={textOnly} />)}
      </div>
    </div>
  );
}

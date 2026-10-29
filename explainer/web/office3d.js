// The 3D conversation: two Microsoft Rocketbox avatars (MIT licence; motion-captured animations, facial blendshapes)
// talk in a lit office with the company's logo and a wall screen, rendered with Three.js and driven by ONE GSAP
// timeline that HyperFrames seeks frame by frame (window.__timelines.main). Everything is a function of the time t:
// which motion-capture clip each person plays and how strongly (talking while they speak, listening or idle
// otherwise), the lip-sync visemes from Kokoro's phoneme timings, blinks, the camera shot and the screen's slide.
import * as THREE from "three";
import { FBXLoader } from "three/addons/loaders/FBXLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

window.__hfTimelinesBuilding = true;
const V = window.VIDEO;
const LINES = V.lines;
const D = V.duration;
const W = 1920, H = 1080;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const smooth = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
const lerp = (a, b, k) => a + (b - a) * k;
const rand = (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

// ── renderer, scene, light ──────────────────────────────────────────────────
const canvas = document.getElementById("gl");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
scene.background = new THREE.Color(V.wall || "#dfe4ea");
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
const camera = new THREE.PerspectiveCamera(30, W / H, 0.05, 50);

scene.add(new THREE.HemisphereLight(0xffffff, 0x4a5568, 0.55));
const key = new THREE.DirectionalLight(0xfff4e8, 2.4);
key.position.set(2.2, 4.2, 3.6);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -3, right: 3, top: 3, bottom: -1, near: 0.5, far: 12 });
key.shadow.bias = -0.0004;
key.shadow.radius = 4;
scene.add(key);
const fill = new THREE.DirectionalLight(0xdfe8ff, 0.7);
fill.position.set(-3, 2.5, 2.5);
scene.add(fill);
const rim = new THREE.DirectionalLight(new THREE.Color(V.accent || "#00d0b8"), 1.6);
rim.position.set(0, 3, -3);
scene.add(rim);

// ── the office: floor, walls, the company's wall with its logo and a screen ─────────────────────────────
const tex = new THREE.TextureLoader();
const mat = (color, rough = 0.85, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0, ...extra });
const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), mat("#8d6e55", 0.55));
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);
// floorboards: thin darker lines
for (let i = -15; i <= 15; i++) {
  const l = new THREE.Mesh(new THREE.PlaneGeometry(0.01, 30), mat("#6f5542", 0.8));
  l.rotation.x = -Math.PI / 2; l.position.set(i * 0.22, 0.001, 0); l.receiveShadow = true; scene.add(l);
}
const wall = new THREE.Mesh(new THREE.PlaneGeometry(30, 8), mat(V.wall || "#c9d0d8", 0.95));
wall.position.set(0, 4, -2.6);
wall.receiveShadow = true;
scene.add(wall);
const brand = new THREE.Mesh(new THREE.BoxGeometry(3.6, 3.1, 0.08), mat(V.primary || "#0b2545", 0.6));
brand.position.set(0, 1.75, -2.52);
brand.receiveShadow = true;
scene.add(brand);
const strip = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.03, 0.09),
  new THREE.MeshStandardMaterial({ color: V.accent || "#00d0b8", emissive: V.accent || "#00d0b8", emissiveIntensity: 1.6 }));
strip.position.set(0, 0.22, -2.5);
scene.add(strip);
const strip2 = strip.clone();
strip2.position.y = 3.28;
scene.add(strip2);
// right: a walnut slat wall; left: a tall window with daylight
const walnut = new THREE.Mesh(new THREE.BoxGeometry(2.4, 3.4, 0.04), mat("#4a3426", 0.65));
walnut.position.set(3.25, 1.7, -2.56); scene.add(walnut);
for (let i = 0; i < 16; i++) {
  const s = new THREE.Mesh(new THREE.BoxGeometry(0.07, 3.4, 0.05), mat("#6b4c36", 0.55));
  s.position.set(2.13 + i * 0.15, 1.7, -2.5); s.castShadow = true; s.receiveShadow = true; scene.add(s);
}
const glass = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 3.2), new THREE.MeshBasicMaterial({ color: "#eaf4ff", toneMapped: false }));
glass.position.set(-3.3, 1.75, -2.57); scene.add(glass);
for (let i = 0; i < 4; i++) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(0.05, 3.2, 0.06), mat("#2b3138", 0.5));
  m.position.set(-4.6 + i * 0.87, 1.75, -2.53); scene.add(m);
}
[0.15, 1.75, 3.35].forEach((y) => { const m = new THREE.Mesh(new THREE.BoxGeometry(2.7, 0.05, 0.06), mat("#2b3138", 0.5)); m.position.set(-3.3, y, -2.53); scene.add(m); });
const daylight = new THREE.PointLight(0xdfeeff, 6, 8, 1.6);
daylight.position.set(-3.0, 2.2, -1.6); scene.add(daylight);
// two office plants in the back corners: modest, slim dark leaves so they don't compete with the people
[[-2.55, -2.05], [2.5, -2.1]].forEach(([px, pz], k) => {
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.13, 0.42, 32), mat("#3a3d42", 0.55));
  pot.position.set(px, 0.21, pz); pot.castShadow = true; pot.receiveShadow = true; scene.add(pot);
  const greens = ["#1f4527", "#2a5631", "#173a20", "#33613a"];
  for (let j = 0; j < 34; j++) {
    const a = rand(j + k * 40) * Math.PI * 2, tilt = 0.2 + rand(j + 7 + k * 40) * 0.7, len = 0.32 + rand(j + 3 + k * 40) * 0.42;
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), mat(greens[j % 4], 0.75));
    leaf.scale.set(0.035, len / 2, 0.012);
    leaf.position.set(px + Math.cos(a) * Math.sin(tilt) * len * 0.5, 0.42 + Math.cos(tilt) * len * 0.5, pz + Math.sin(a) * Math.sin(tilt) * len * 0.5);
    leaf.rotation.set(Math.sin(a) * tilt, 0, -Math.cos(a) * tilt);
    leaf.castShadow = true; scene.add(leaf);
  }
});
// the screen between them: a dark bezel and a canvas that shows the slides
const bezel = new THREE.Mesh(new THREE.BoxGeometry(1.78, 1.04, 0.05), mat("#0a0d14", 0.4));
bezel.position.set(0, 1.62, -2.44);
scene.add(bezel);
const slideCanvas = document.createElement("canvas");
slideCanvas.width = 1280; slideCanvas.height = 720;
const slideTex = new THREE.CanvasTexture(slideCanvas);
slideTex.colorSpace = THREE.SRGBColorSpace;
const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.7, 0.956), new THREE.MeshBasicMaterial({ map: slideTex, toneMapped: false }));
screen.position.set(0, 1.62, -2.41);
scene.add(screen);

// ── the people ─────────────────────────────────────────────────────────────
const loader = new FBXLoader();
const VIS = { X: "AA_VI_00_Sil", M: "AA_VI_01_PP", F: "AA_VI_02_FF", C: "AA_VI_04_DD", A: "AA_VI_10_aa", E: "AA_VI_11_E",
  O: "AA_VI_13_O", U: "AA_VI_14_U" };
const PLACES = [{ x: -0.62, ry: 0.62 }, { x: 0.62, ry: -0.62 }];

async function person(c, i) {
  const base = `assets/avatars/${c.model}/`;
  const group = new THREE.Group();
  const model = await loader.loadAsync(base + "avatar.fbx");
  model.scale.setScalar(0.01);              // centimetres -> metres
  group.add(model);
  group.position.set(PLACES[i].x, 0, 0);
  group.rotation.y = PLACES[i].ry;
  scene.add(group);
  const T = (f, srgb = true) => { const t = tex.load(base + f); if (srgb) t.colorSpace = THREE.SRGBColorSpace; return t; };
  const p = c.textures;   // { body, bodyN, head, headN, hair }
  let mesh = null;
  model.traverse((o) => {
    if (!o.isMesh) return;
    mesh = o;
    o.castShadow = true; o.receiveShadow = true; o.frustumCulled = false;
    const mats = [].concat(o.material).map((m) => {
      const n = m.name || "";
      if (/opacity/i.test(n)) return new THREE.MeshStandardMaterial({ map: T(p.hair), transparent: true, alphaTest: 0.35,
        side: THREE.DoubleSide, roughness: 0.7, depthWrite: true });
      if (/head/i.test(n)) return new THREE.MeshStandardMaterial({ map: T(p.head), normalMap: T(p.headN, false), roughness: 0.55 });
      return new THREE.MeshStandardMaterial({ map: T(p.body), normalMap: T(p.bodyN, false), roughness: 0.7 });
    });
    o.material = Array.isArray(o.material) ? mats : mats[0];
  });
  const dict = mesh.morphTargetDictionary || {};
  const morph = (name) => { const k = Object.keys(dict).find((x) => x.endsWith("." + name) || x === name); return k === undefined ? -1 : dict[k]; };
  const mixer = new THREE.AnimationMixer(model);
  const clips = {};
  for (const [role, files] of Object.entries(c.anims)) {
    clips[role] = [];
    for (const f of files) {
      const a = await loader.loadAsync("assets/anims/" + f);
      const clip = a.animations[0];
      clip.tracks = clip.tracks.filter((t) => !/Footsteps|\.scale$/.test(t.name));
      const action = mixer.clipAction(clip);
      action.play();
      action.setEffectiveWeight(0);
      clips[role].push(action);
    }
  }
  return { group, model, mesh, mixer, clips, morph, vis: Object.fromEntries(Object.entries(VIS).map(([k, n]) => [k, morph(n)])),
    blink: [morph("AK_09_EyeBlinkLeft"), morph("AK_10_EyeBlinkRight")], smile: [morph("AK_44_MouthSmileLeft"), morph("AK_45_MouthSmileRight")],
    brow: morph("AK_03_BrowInnerUp"), jaw: morph("AK_25_JawOpen"), look: [morph("AK_13_EyeLookInLeft"), morph("AK_16_EyeLookOutRight")] };
}

// which clip, how strongly: talking while the person speaks, listening while the other does, idle otherwise
function animate(P, i, t) {
  const fade = 0.55;
  let talk = 0, listen = 0, talkLine = -1, listenLine = -1;
  LINES.forEach((ln, k) => {
    const w = smooth((t - ln.start + 0.25) / fade) * smooth((ln.end + 0.35 - t) / fade);
    if (w <= 0) return;
    if (ln.speaker === i && w > talk) { talk = w; talkLine = k; }
    if (ln.speaker !== i && w > listen) { listen = w; listenLine = k; }
  });
  listen = Math.min(listen, 1 - talk);
  const idle = Math.max(0, 1 - talk - listen);
  const set = (list, which, weight, from) => list.forEach((a, k) => {
    const on = k === which ? weight : 0;
    a.setEffectiveWeight(on);
    if (on > 0) a.time = ((t - from) + rand(which * 13 + i) * a.getClip().duration) % a.getClip().duration;
  });
  const talkPick = talkLine >= 0 ? (LINES[talkLine].gesture === "point" && P.clips.point ? -1 : talkLine % P.clips.talk.length) : 0;
  if (talkPick === -1) {
    set(P.clips.talk, -1, 0, 0);
    set(P.clips.point, 0, talk, LINES[talkLine].start);
  } else {
    if (P.clips.point) set(P.clips.point, -1, 0, 0);
    set(P.clips.talk, talkPick, talk, talkLine >= 0 ? LINES[talkLine].start : 0);
  }
  set(P.clips.listen, listenLine >= 0 ? listenLine % P.clips.listen.length : 0, listen, listenLine >= 0 ? LINES[listenLine].start : 0);
  set(P.clips.idle, 0, idle, 0);
  P.mixer.update(0);

  // face: visemes from the phoneme track while talking, blinks, a light smile, raised brows on questions
  const inf = P.mesh.morphTargetInfluences;
  Object.values(P.vis).forEach((k) => { if (k >= 0) inf[k] = 0; });
  let open = 0;
  if (talkLine >= 0 && t >= LINES[talkLine].start - 0.05 && t <= LINES[talkLine].end + 0.1) {
    const m = LINES[talkLine].mouth || [];
    let k = -1;
    for (let j = 0; j < m.length && m[j][0] <= t; j++) k = j;
    if (k >= 0) {
      const into = clamp((t - m[k][0]) / 0.07);
      const cur = P.vis[m[k][1]], prev = k > 0 ? P.vis[m[k - 1][1]] : -1;
      if (cur >= 0) inf[cur] = Math.max(inf[cur], 0.9 * into);
      if (prev >= 0 && prev !== cur) inf[prev] = Math.max(inf[prev], 0.9 * (1 - into));
      open = { A: 0.35, O: 0.25, E: 0.18, U: 0.12, C: 0.1 }[m[k][1]] || 0;
    }
  }
  if (P.jaw >= 0) inf[P.jaw] = open * 0.6;
  const phase = (t + i * 1.9) % 4.1;
  const blink = phase > 3.95 || (rand(Math.floor((t + i * 1.9) / 4.1) + i * 31) > 0.6 && phase > 1.8 && phase < 1.95) ? 1 : 0;
  P.blink.forEach((k) => { if (k >= 0) inf[k] = blink; });
  const happy = talkLine >= 0 ? ["happy", "excited"].includes(LINES[talkLine].mood) : listenLine >= 0;
  P.smile.forEach((k) => { if (k >= 0) inf[k] = happy ? 0.32 : 0.18; });
  const ask = talkLine >= 0 && /\?\s*$/.test(LINES[talkLine].say);
  if (P.brow >= 0) inf[P.brow] = ask ? 0.45 * talk : 0;
}

// ── the camera: a two-shot to open, the speaker in a closer shot, the screen when it changes ────────────
const HEAD = (i) => new THREE.Vector3(PLACES[i].x, 1.52, 0);
function closeUp(i) {                                                                                  // over the other's shoulder
  const s = i === 0 ? 1 : -1, h = HEAD(i);
  return { pos: [h.x + s * 2.05, 1.6, 1.4], look: [h.x + s * 0.12, 1.42, 0], fov: 27 };
}
function shotFor(k) {
  const ln = LINES[k], i = ln.speaker, s = i === 0 ? 1 : -1, h = HEAD(i);
  if (k === 0 || k % 5 === 4) return { pos: [0, 1.45, 4.4], look: [0, 1.22, -0.4], fov: 30 };            // both of them
  if (ln.screen) return { pos: [-s * 0.4, 1.5, 3.3], look: [h.x * 0.35, 1.45, -1.2], fov: 32 };           // speaker and screen
  return closeUp(i);
}
const SHOTS = [{ t: -1, ...shotFor(0) }];
function addShot(sh) {
  const last = SHOTS[SHOTS.length - 1];
  if (JSON.stringify(sh.pos) !== JSON.stringify(last.pos) || JSON.stringify(sh.look) !== JSON.stringify(last.look)) SHOTS.push(sh);
}
LINES.forEach((ln, k) => {
  addShot({ t: ln.start - 0.25, ...shotFor(k) });
  // a long line shows its point on the screen, then cuts in to the speaker's face so nobody is only ever seen wide
  const len = ln.end - ln.start;
  if (len > 4.5 && SHOTS[SHOTS.length - 1].t >= ln.start - 0.3) {
    const pts = ln.screen ? ln.screen.points.map((p) => p.at).filter((a) => a < ln.end) : [];
    const cut = Math.min(ln.end - 1.6, Math.max(ln.start + 2.4, (pts.length ? Math.max(...pts) : ln.start) + 1.8));
    addShot({ t: cut, ...closeUp(ln.speaker) });
  }
});
function placeCamera(t) {
  let k = 0;
  while (k + 1 < SHOTS.length && SHOTS[k + 1].t <= t) k++;
  const sh = SHOTS[k];
  const drift = clamp((t - sh.t) / 8) * 0.04;          // a slow push in
  const pos = new THREE.Vector3(...sh.pos), look = new THREE.Vector3(...sh.look);
  pos.lerp(look, drift);
  camera.position.copy(pos);
  camera.fov = sh.fov;
  camera.updateProjectionMatrix();
  camera.lookAt(look);
}

// ── the wall screen's slides (a canvas texture, redrawn only when what it shows changes) ────────────────
const SHOWS = LINES.filter((ln) => ln.screen);
let shown = "";
function drawSlide(t) {
  let cur = null;
  for (const ln of SHOWS) if (ln.screen.at <= t) cur = ln.screen;
  const pts = cur ? cur.points.filter((p) => p.at <= t) : [];
  const keyNow = cur ? cur.title + "|" + pts.length : "splash";
  if (keyNow === shown) return;
  shown = keyNow;
  const g = slideCanvas.getContext("2d");
  const grd = g.createLinearGradient(0, 0, 1280, 720);
  grd.addColorStop(0, V.primary2 || "#123a6b"); grd.addColorStop(1, V.primary || "#0b2545");
  g.fillStyle = grd; g.fillRect(0, 0, 1280, 720);
  g.fillStyle = V.accent || "#00d0b8"; g.fillRect(0, 0, 1280, 10);
  if (!cur) {
    if (LOGO) { g.fillStyle = "#fff"; g.fillRect(340, 250, 600, 150); const r = Math.min(520 / LOGO.width, 110 / LOGO.height);
      g.drawImage(LOGO, 640 - LOGO.width * r / 2, 325 - LOGO.height * r / 2, LOGO.width * r, LOGO.height * r); }
    g.fillStyle = "#fff"; g.font = "700 64px 'Segoe UI'"; g.textAlign = "center"; g.fillText(V.app_name || V.title || "", 640, 520);
  } else {
    g.textAlign = "left"; g.fillStyle = "#fff"; g.font = "800 72px 'Segoe UI'"; g.fillText(cur.title || "", 90, 170);
    g.fillStyle = V.accent || "#00d0b8"; g.fillRect(90, 200, 120, 10);
    pts.forEach((p, k) => {
      const y = 300 + k * 110;
      g.fillStyle = V.accent || "#00d0b8"; g.beginPath(); g.arc(118, y - 18, 26, 0, Math.PI * 2); g.fill();
      g.strokeStyle = V.primary || "#0b2545"; g.lineWidth = 7; g.beginPath(); g.moveTo(104, y - 18); g.lineTo(115, y - 6); g.lineTo(134, y - 32); g.stroke();
      g.fillStyle = "#fff"; g.font = "600 52px 'Segoe UI'"; g.fillText(p.text, 170, y);
    });
  }
  slideTex.needsUpdate = true;
}
let LOGO = null;
async function loadLogo() {
  if (!V.logo) return;
  LOGO = new Image(); LOGO.src = V.logo;
  await LOGO.decode().catch(() => { LOGO = null; });
  if (!LOGO) return;
  const plate = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.3, 0.03), mat("#ffffff", 0.5));
  plate.position.set(0, 2.62, -2.46); scene.add(plate);
  const lt = new THREE.Texture(LOGO); lt.colorSpace = THREE.SRGBColorSpace; lt.needsUpdate = true;
  const r = Math.min(1.36 / LOGO.width, 0.24 / LOGO.height);
  const lp = new THREE.Mesh(new THREE.PlaneGeometry(LOGO.width * r, LOGO.height * r), new THREE.MeshBasicMaterial({ map: lt, transparent: true, toneMapped: false }));
  lp.position.set(0, 2.62, -2.443); scene.add(lp);
}

// ── titles over the picture (HTML) ──────────────────────────────────────────
function overlays(tl) {
  const el = (cls, parent, text) => { const n = document.createElement("div"); n.className = cls; if (text != null) n.textContent = text; parent.appendChild(n); return n; };
  const root = document.getElementById("over");
  const first = LINES[0], last = LINES[LINES.length - 1];
  const card = el("title-card", root);
  if (V.brand_name) el("k", card, V.brand_name);
  el("t", card, V.title);
  tl.fromTo(card, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.8, ease: "power3.out" }, 0.3);
  tl.to(card, { opacity: 0, duration: 0.5 }, first.start + 0.9);
  V.cast.forEach((c, i) => {
    const ln = LINES.find((x) => x.speaker === i);
    if (!ln) return;
    const tag = el("tag " + (i ? "right" : "left"), root);
    el("n", tag, c.name); el("r", tag, c.role);
    const t0 = Math.max(ln.start + 0.2, first.start + 1.5);
    tl.fromTo(tag, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.6 }, t0);
    tl.to(tag, { opacity: 0, duration: 0.5 }, t0 + 3.4);
  });
  const close = el("closing", root);
  if (V.logo) { const pl = el("plate", close); const im = document.createElement("img"); im.src = V.logo; pl.appendChild(im); }
  el("t", close, V.app_name || V.title);
  if (V.closing && V.closing !== V.app_name) el("s", close, V.closing);
  tl.fromTo(close, { opacity: 0 }, { opacity: 1, duration: 0.8 }, last.end + 0.6);
  tl.fromTo(el("progress", root), { scaleX: 0 }, { scaleX: 1, duration: D, ease: "none" }, 0);
}

// ── build, then hand the timeline to HyperFrames ────────────────────────────
const people = await Promise.all(V.cast.map((c, i) => person(c, i)));
await loadLogo();
function frame(t) {
  people.forEach((P, i) => animate(P, i, t));
  placeCamera(t);
  drawSlide(t);
  renderer.render(scene, camera);
}
const tl = gsap.timeline({ paused: true });
const clock = { t: 0 };
tl.fromTo(clock, { t: 0 }, { t: D, duration: D, ease: "none", onUpdate: () => frame(clock.t) }, 0);
overlays(tl);
frame(0);
window.__timelines = window.__timelines || {};
window.__timelines.main = tl;
window.__seek3d = (t) => { tl.seek(t); frame(t); };     // for checking frames outside HyperFrames
window.__hfTimelinesBuilding = false;
window.dispatchEvent(new Event("hf-timelines-built"));
window.READY3D = true;

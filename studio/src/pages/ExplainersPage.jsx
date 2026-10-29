/* Animated videos from a narration - motion graphics or two people talking in an office: the list, the new-video
   form, and one video's page. */
import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "../icons.jsx";
import { api } from "../api.js";
import { duration as clock, relativeTime } from "../format.js";
import { navigate } from "../router.js";
import { Alert, ConfirmDialog, Empty, Field, LogViewer, PageHead, PanelHead, Progress, Segmented, Spinner, Switch, useToast } from "../ui.jsx";

const STATE = {
  running: ["b-violet", "Making"],
  done: ["b-green", "Ready"],
  failed: ["b-red", "Failed"],
};

function Status({ status }) {
  const [cls, label] = STATE[status] || ["b-blue", status];
  return <span className={`badge ${cls}`}>{label}</span>;
}

// background, deep background, accent, second accent - as in explainer/web/player.css
const SWATCH = {
  midnight: ["#1b1450", "#0b1020", "#22d3ee", "#a78bfa", "#fff"],
  daylight: ["#e3eafc", "#f8fafc", "#2563eb", "#0d9488", "#0f172a"],
  sunrise: ["#4a1638", "#1c0f2e", "#fb923c", "#f472b6", "#fff7ed"],
  forest: ["#0f3b2e", "#06140f", "#4ade80", "#facc15", "#f0fdf4"],
};

const LAYOUT_LABEL = { title: "Title", statement: "Statement", points: "Key points", stats: "Numbers", steps: "Steps",
  compare: "Before / after", chart: "Chart", icons: "Icon grid", quote: "Quote", closing: "Closing" };

const STYLE_LABEL = { explainer: "Explainer", conversation: "Conversation", presenters: "Presenters", hitech: "Hi-tech", conversation3d: "3D conversation" };

const words = (t) => (t.trim() ? t.trim().split(/\s+/).length : 0);

function useOptions() {
  const [options, setOptions] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.explainerOptions().then(setOptions).catch((e) => setError(e.message)); }, []);
  return { options, error };
}

/** One video, polled while it is being made. */
function useExplainer(id) {
  const [video, setVideo] = useState(null);
  const [error, setError] = useState(null);
  const refresh = useCallback(() => api.explainer(id).then((v) => { setVideo(v); setError(null); }).catch((e) => setError(e.message)), [id]);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (video?.status !== "running") return undefined;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [video?.status, refresh]);
  return { video, error, refresh };
}

// ── list ─────────────────────────────────────────────────────────────────────

export default function ExplainersPage() {
  const [videos, setVideos] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    const load = () => api.explainers().then(setVideos).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);
  const add = <button type="button" className="btn btn-primary btn-lg" onClick={() => navigate("/explainers/new")}><Icon name="plus" />New animated video</button>;

  return (
    <>
      <PageHead title="Animated videos"
        subtitle="Animated videos from a narration: motion graphics where every point animates in as it is said, two colleagues talking it through in an office, or two presenters in your branded studio."
        actions={add} />
      {error && <p className="error-text">Couldn't load the videos: {error}</p>}
      {!videos && !error && <div className="cards">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 260 }} />)}</div>}
      {videos?.length === 0 && (
        <section className="panel">
          <Empty icon="sparkles" title="No animated videos yet"
            body="Write or paste a narration of about two minutes, pick a look and a voice, and Zen Studio makes an animated explainer from it."
            action={add} />
        </section>
      )}
      <ul className="cards" style={{ listStyle: "none", margin: 0, padding: 0, gridTemplateColumns: "repeat(auto-fill, minmax(min(340px, 100%), 1fr))" }}
        aria-label="Animated videos">
        {(videos || []).map((v, i) => (
          <li key={v.id} className="rise" style={{ animationDelay: `${Math.min(i, 10) * 40}ms` }}>
            <a className="vcard hoverable" href={`#/explainers/${v.id}`}>
              <span className="vcard-media">
                {v.status === "done" ? <img src={api.explainerFileUrl(v.id, "poster.jpg") + `?v=${encodeURIComponent(v.built || "")}`} alt="" loading="lazy" />
                  : <Icon name="sparkles" size={34} />}
              </span>
              <span className="vcard-body">
                <span style={{ font: "700 16px/22px var(--font)" }}>{v.title}</span>
                <span className="meta">{STYLE_LABEL[v.style] || "Explainer"} · {v.duration ? `${clock(v.duration)} · ` : ""}{relativeTime(v.created)}</span>
                <span className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                  <Status status={v.status} />
                  <span className="row meta" style={{ gap: 6 }}><Icon name="palette" size={15} />{v.style === "presenters" ? (v.brand_name || "Brand") : v.theme}</span>
                </span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}

// ── the look: theme, voice, script, captions, music ─────────────────────────

function ThemePicker({ themes, value, onChange, disabled }) {
  return (
    <div className="ex-themes" role="radiogroup" aria-label="Theme">
      {themes.map((t) => {
        const [bg2, bg1, a1, a2, ink] = SWATCH[t.id] || SWATCH.midnight;
        return (
          <button key={t.id} type="button" role="radio" aria-checked={value === t.id} disabled={disabled}
            className="ex-theme" onClick={() => onChange(t.id)}>
            <span className="ex-swatch" style={{ background: `radial-gradient(120% 120% at 15% 10%, ${bg2}, ${bg1} 60%)`, color: ink }}>
              <span className="ex-swatch-title">Your story</span>
              <span className="ex-swatch-bar" style={{ background: `linear-gradient(90deg, ${a1}, ${a2})` }} />
              <span className="ex-swatch-dot" style={{ background: `linear-gradient(135deg, ${a1}, ${a2})` }} />
            </span>
            <span className="ex-theme-name">{value === t.id && <Icon name="check" size={16} />}{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/** A small portrait of a cast preset, in its own colours (as drawn by explainer/web/office.js). */
function Avatar({ p, size = 56 }) {
  const long = ["long", "bob", "curly"].includes(p.hair_style);
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" style={{ flex: "none" }}>
      <circle cx="50" cy="50" r="50" fill="var(--chip-blue)" />
      {long && <path d={p.hair_style === "curly" ? "M18,52 a32,34 0 1,1 64,0 v10 h-64 Z" : "M20,50 C20,20 80,20 80,50 L82,82 L18,82 Z"} fill={p.hair} />}
      <path d="M20,100 C20,78 34,72 50,72 C66,72 80,78 80,100 Z" fill={p.top} />
      <ellipse cx="50" cy="48" rx="20" ry="23" fill={p.skin} />
      {p.beard && <path d="M31,52 C32,68 42,72 50,72 C58,72 68,68 69,52 C64,62 58,64 50,64 C42,64 36,62 31,52 Z" fill={p.hair} />}
      <path d={p.hair_style === "buzz" ? "M31,42 C31,26 69,26 69,42 C62,34 38,34 31,42 Z" : "M29,46 C27,24 73,22 71,44 C66,36 56,32 46,34 C38,36 32,40 29,46 Z"} fill={p.hair} />
      <circle cx="43" cy="49" r="2.6" fill="#1b1b24" /><circle cx="58" cy="49" r="2.6" fill="#1b1b24" />
      {p.glasses && <g fill="none" stroke="#1f2937" strokeWidth="2"><rect x="36" y="44" width="13" height="10" rx="3" /><rect x="52" y="44" width="13" height="10" rx="3" /></g>}
      <path d="M44,60 Q50,64 56,60" fill="none" stroke="#7a3a2a" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function StylePicker({ styles, value, onChange, disabled }) {
  return (
    <div className="ex-styles" role="radiogroup" aria-label="Style">
      {styles.map((s) => (
        <button key={s.id} type="button" role="radio" aria-checked={value === s.id} disabled={disabled} className="ex-style"
          onClick={() => onChange(s.id)}>
          <Icon name={{ conversation: "user", presenters: "presentation", hitech: "wand", conversation3d: "user" }[s.id] || "sparkles"} size={22} />
          <span><strong>{s.label}</strong><span className="meta">{s.hint}</span></span>
        </button>
      ))}
    </div>
  );
}

function CastPicker({ options, look, set, disabled }) {
  const studio = look.style === "presenters";
  const people = studio ? options.studio_cast : look.style === "conversation3d" ? options.cast3d : options.cast;
  const byId = Object.fromEntries(people.map((p) => [p.id, p]));
  const pick = (i, id) => {
    const cast = [...look.cast];
    cast[i] = id;
    if (cast[1 - i] === id) cast[1 - i] = look.cast[i];     // the two swap rather than become the same person
    set({ cast, voices: ["", ""] });
  };
  const voice = (i, v) => { const voices = [...look.voices]; voices[i] = v; set({ voices }); };
  return (
    <div className="ex-cast">
      {(studio ? ["First presenter", "Second presenter"] : ["Asks the questions", "Explains"]).map((role, i) => {
        const p = byId[look.cast[i]] || people[i];
        return (
          <div key={role} className="ex-person">
            <Avatar p={p} />
            <div className="stack" style={{ gap: 8, flex: 1, minWidth: 0 }}>
              <span className="meta" style={{ fontWeight: 700 }}>{role}</span>
              <select className="select" aria-label={`${role}: person`} value={p.id} disabled={disabled} onChange={(e) => pick(i, e.target.value)}>
                {people.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </select>
              <select className="select" aria-label={`${role}: voice`} value={look.voices[i] || ""} disabled={disabled} onChange={(e) => voice(i, e.target.value)}>
                <option value="">{`Their own voice (${options.voices.find((v) => v.id === p.voice)?.label || p.voice})`}</option>
                {options.voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** The company's logo for the presenters' studio: a picture file, read in the browser and sent as a data: URL. */
function LogoField({ logo, current, onChange, disabled }) {
  const toast = useToast();
  const pick = (file) => {
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) { toast("Choose a PNG, JPG or WebP image", "error"); return; }
    if (file.size > 8e6) { toast("The logo is too large (8 MB at most)", "error"); return; }
    const r = new FileReader();
    r.onload = () => onChange(r.result);
    r.readAsDataURL(file);
  };
  const shown = logo || current;
  return (
    <div className="ex-logo">
      <span className="ex-logo-box">{shown ? <img src={shown} alt="Logo" /> : <span className="meta">No logo</span>}</span>
      <label className="btn btn-sm">
        <Icon name="upload" size={16} />{shown ? "Change logo" : "Upload logo"}
        <input type="file" accept="image/png,image/jpeg,image/webp" hidden disabled={disabled} onChange={(e) => pick(e.target.files[0])} />
      </label>
      {logo && <button type="button" className="btn btn-sm btn-ghost" onClick={() => onChange("")} disabled={disabled}>Remove</button>}
    </div>
  );
}

function LookFields({ options, look, set, disabled, showScript = true, logo, setLogo, currentLogo }) {
  const presenters = look.style === "presenters";
  const talk = look.style === "conversation" || look.style === "conversation3d" || presenters;
  const setStyle = (style) => set({ style, voices: ["", ""],
    cast: style === "presenters" ? options.default_studio : style === "conversation" ? options.default_cast
      : style === "conversation3d" ? options.default_3d : look.cast,
    seconds: style === "presenters" && look.seconds > 90 ? 85 : look.seconds });
  return (
    <div className="stack" style={{ gap: 20 }}>
      <Field label="Style">
        <StylePicker styles={options.styles} value={look.style} onChange={setStyle} disabled={disabled} />
      </Field>
      {talk && <Field label={presenters ? "The two presenters" : "The two people"}
        hint={presenters ? "They stand in a studio and present to camera, taking turns; a display between them shows the key points."
          : "They talk at a desk in an office; a wall screen between them shows the key points."}>
        <CastPicker options={options} look={look} set={set} disabled={disabled} />
      </Field>}
      {(talk || look.style === "hitech") && <div className="deck-form">
        <Field label="Company logo (optional)" hint="On the wall behind them, the screen and the end card. Its colours become the set's colours.">
          <LogoField logo={logo} current={currentLogo} onChange={setLogo} disabled={disabled} />
        </Field>
        <Field label="Company name" htmlFor="ex-brand" hint="Shown above the title, and instead of a logo when there is none.">
          <input id="ex-brand" className="input" value={look.brand_name} disabled={disabled} onChange={(e) => set({ brand_name: e.target.value })}
            placeholder="e.g. Cynergy Bank" />
        </Field>
      </div>}
      {!presenters && !(talk && (logo || currentLogo)) && <Field label="Theme">
        <ThemePicker themes={options.themes} value={look.theme} onChange={(theme) => set({ theme })} disabled={disabled} />
      </Field>}
      <div className="deck-form">
        {!talk && <Field label="Voice" htmlFor="ex-voice" hint="Kokoro voice, generated on this computer">
          <select id="ex-voice" className="select" value={look.voice} disabled={disabled} onChange={(e) => set({ voice: e.target.value })}>
            {options.voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
          </select>
        </Field>}
        {talk && <Field label={`${presenters ? "Video length" : "Conversation length"} · ${presenters ? "under" : "about"} ${clock(look.seconds)}`} htmlFor="ex-seconds"
          hint={presenters ? "A hard limit: the AI condenses your script to fit, keeping its facts." : "The AI writes the dialogue to about this length, keeping your facts."}>
          <input id="ex-seconds" type="range" min={45} max={presenters ? 180 : 300} step={5} value={look.seconds} disabled={disabled}
            onChange={(e) => set({ seconds: +e.target.value })} />
        </Field>}
        <Field label={`Speaking speed · ${look.speed.toFixed(2)}x`} htmlFor="ex-speed">
          <input id="ex-speed" type="range" min={0.8} max={1.3} step={0.05} value={look.speed} disabled={disabled}
            onChange={(e) => set({ speed: +e.target.value })} />
        </Field>
        {showScript && !talk && <Field label="Voice-over">
          <Segmented label="Voice-over" options={options.modes.map((m) => ({ value: m.id, label: m.label }))} value={look.mode}
            onChange={(mode) => set({ mode })} disabled={disabled} />
          <span className="hint">{look.mode === "as_written" ? "Your narration is spoken exactly as written." : "The AI rewrites it into a tight voice-over of about the length below, keeping your facts."}</span>
        </Field>}
        {showScript && !talk && look.mode === "tighten" && <Field label={`Target length · ${clock(look.seconds)}`} htmlFor="ex-seconds">
          <input id="ex-seconds" type="range" min={30} max={300} step={15} value={look.seconds} disabled={disabled}
            onChange={(e) => set({ seconds: +e.target.value })} />
        </Field>}
        <Field label="Captions">
          <Segmented label="Captions" options={options.captions.map((c) => ({ value: c.id, label: c.label }))} value={look.captions}
            onChange={(captions) => set({ captions })} disabled={disabled} />
        </Field>
        <div className="field" style={{ alignSelf: "end" }}>
          <Switch label="Background music" checked={look.music} onChange={(music) => set({ music })} disabled={disabled} />
        </div>
      </div>
    </div>
  );
}

const DEFAULT_LOOK = { style: "explainer", cast: ["maya", "sam"], voices: ["", ""], brand_name: "", theme: "midnight", voice: "af_sky", speed: 1,
  mode: "as_written", seconds: 120, captions: "soft", music: true };
const LOOK_KEYS = Object.keys(DEFAULT_LOOK);
const lookOf = (v) => Object.fromEntries(LOOK_KEYS.map((k) => [k, v[k] ?? DEFAULT_LOOK[k]]));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const NARRATION_HINT = `Every product team needs demo videos for sales, onboarding and training. But making one is still slow and manual...

Here is how it works. First, you write the narration as you would present it. Next, ...`;

// ── new video ────────────────────────────────────────────────────────────────

export function NewExplainerPage() {
  const toast = useToast();
  const { options, error: loadError } = useOptions();
  const [narration, setNarration] = useState("");
  const [title, setTitle] = useState("");
  const [look, setLook] = useState(DEFAULT_LOOK);
  const [logo, setLogo] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const n = words(narration);
  const ok = n >= 20;
  const minutes = n / 160;

  const submit = async (e) => {
    e?.preventDefault();
    setTouched(true);
    if (!ok) return;
    setBusy(true);
    try {
      const v = await api.createExplainer({ narration: narration.trim(), title: title.trim(), ...look,
        logo: look.style !== "explainer" ? logo : "" });
      toast("Planning the scenes…", "info");
      navigate(`/explainers/${v.id}`);
    } catch (err) {
      toast(err.message, "error");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate>
      <PageHead crumbs={[{ label: "Animated videos", to: "/explainers" }, { label: "New animated video" }]}
        title="New animated video"
        subtitle="From your narration: an animated explainer where key points, steps and numbers appear exactly when they are said, two colleagues talking it through in an office, or two presenters in a studio with your logo." />
      <div className="stack">
        <section className="panel rise" aria-labelledby="ex-narration-title">
          <PanelHead icon="mic" tone="violet" title={<span id="ex-narration-title">Narration</span>}
            subtitle="What the voice says. About 300 words make a two-minute video. Figures you mention can appear on screen; the AI never makes them up." />
          <div className="stack" style={{ gap: 16 }}>
            <Field label="Product or topic" htmlFor="ex-title" hint="Optional. Shown on the title and in the corner.">
              <input id="ex-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Zen Studio" />
            </Field>
            <Field label="Narration" required htmlFor="ex-narration"
              error={touched && !ok ? "Write at least a few sentences (20+ words)." : null}
              hint={`${n.toLocaleString()} words · about ${clock(Math.round(minutes * 60))} of speech${minutes > 4 ? " - long: consider “AI tightens it”" : ""}`}>
              <textarea id="ex-narration" className="textarea" rows={12} value={narration} placeholder={NARRATION_HINT}
                aria-invalid={touched && !ok ? "true" : undefined} onChange={(e) => setNarration(e.target.value)} />
            </Field>
          </div>
        </section>

        <section className="panel rise" aria-labelledby="ex-look-title">
          <PanelHead icon="palette" tone="turq" title={<span id="ex-look-title">Style, look and sound</span>}
            subtitle="Theme, voices, speed, captions and music can be changed later for free: the plan is kept." />
          {loadError && <Alert intent="error" title="Couldn't load the options">{loadError}</Alert>}
          {!options && !loadError && <Spinner label="Loading…" />}
          {options && <LookFields options={options} look={look} set={(p) => setLook({ ...look, ...p })} disabled={busy}
            logo={logo} setLogo={setLogo} />}
        </section>

        <section className="panel deck-bar" aria-label="Make the video">
          <div className="deck-bar-main">
            <div className="grow" style={{ minWidth: 220 }}>
              <span className="meta">{{ conversation: "Conversation in an office", presenters: "Presenters in a branded studio" }[look.style] || "Animated explainer"}</span>
              <h2 className="section-title">{title.trim() || "Your video"}</h2>
            </div>
            <span className="meta" style={{ maxWidth: 380 }}>
              {look.style === "explainer" ? "One AI call plans the scenes" : "One AI call writes the script"} (under a cent), then the voices and animation are made on this computer: about 3-4 minutes for a 2-minute video.
            </span>
            <button type="submit" className="btn btn-primary btn-lg" disabled={busy || !options}>
              {busy ? <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} aria-hidden="true" /> : <Icon name="sparkles" size={18} />}
              {busy ? "Starting…" : "Make video"}
            </button>
          </div>
        </section>
      </div>
    </form>
  );
}

// ── one video ────────────────────────────────────────────────────────────────

export function ExplainerPage({ id }) {
  const toast = useToast();
  const { video, error, refresh } = useExplainer(id);
  const { options } = useOptions();
  const [look, setLook] = useState(null);
  const [logo, setLogo] = useState("");
  const [starting, setStarting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const playerRef = useRef(null);
  const status = useRef(null);
  useEffect(() => {
    if (!video) return;
    if (!look) setLook(lookOf(video));
    if (status.current === "running" && video.status === "done") toast("Your animated video is ready", "success");
    if (status.current === "running" && video.status === "failed") toast("The video couldn't be made", "error");
    status.current = video.status;
  }, [video]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <Alert intent="error" title="Couldn't load this video">{error}</Alert>;
  if (!video || !look) return <div style={{ paddingTop: 80 }}><Spinner label="Loading…" /></div>;

  const running = video.status === "running" || starting;
  const saved = lookOf(video);
  const changed = !same(look, saved) || !!logo;
  const talk = look.style !== "explainer";
  // what makes the AI plan again (see explainer.service._plan_key)
  const replans = look.style !== saved.style || (talk ? !same(look.cast, saved.cast) || look.seconds !== saved.seconds
    : look.mode !== saved.mode || (look.mode === "tighten" && look.seconds !== saved.seconds));
  const build = async (body = {}) => {
    setStarting(true);
    try {
      await api.buildExplainer(video.id, { ...look, ...body, logo });
      setLogo("");
      await refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setStarting(false);
    }
  };
  const remove = async () => {
    setConfirm(false);
    try {
      await api.removeExplainer(video.id);
      toast("Video deleted");
      navigate("/explainers");
    } catch (e) {
      toast(e.message, "error");
    }
  };
  const seek = (t) => {
    const p = playerRef.current;
    if (!p) return;
    p.currentTime = t;
    p.play();
  };
  const v = encodeURIComponent(video.built || "");
  const file = (name) => api.explainerFileUrl(video.id, name);
  const stage = video.stage ? video.stage : video.progress > 0 ? `Animating · ${Math.round(video.progress * 100)}%`
    : video.style === "conversation" ? "Writing the conversation and voicing it" : "Planning scenes and voicing them";
  const isTalk = ["conversation", "presenters", "conversation3d"].includes(video.style);

  return (
    <>
      <PageHead
        crumbs={[{ label: "Animated videos", to: "/explainers" }, { label: video.title }]}
        title={<span className="row" style={{ gap: 14, flexWrap: "wrap" }}>{video.title}<Status status={video.status} /></span>}
        subtitle={<>
          created {relativeTime(video.created)}
          {video.duration ? <> · {clock(video.duration)}, {video.scenes_count} {isTalk ? "lines" : "scenes"}</> : null}
          {video.usage?.calls > 0 && <> · {video.usage.calls} Azure call{video.usage.calls === 1 ? "" : "s"}, {(video.usage.input_tokens + video.usage.output_tokens).toLocaleString()} tokens, about ${video.usage.cost_usd.toFixed(4)}</>}
        </>}
        actions={<>
          {video.files?.["final.mp4"] && <a className="btn btn-primary" href={file("final.mp4") + "?download=1"}><Icon name="download" size={18} />Download MP4</a>}
          <button type="button" className="btn btn-danger" disabled={running} onClick={() => setConfirm(true)}><Icon name="trash" size={18} />Delete</button>
        </>}
      />
      <div className="stack">
        {video.status === "failed" && <Alert intent="error" title="The video couldn't be made">{video.error}</Alert>}
        <section className="panel rise" aria-label="Video">
          {running ? (
            <div className="stack" style={{ gap: 12, padding: "40px 8px" }}>
              <Spinner label={stage} />
              <Progress value={video.progress > 0 ? video.progress : null} large label="Progress" />
            </div>
          ) : video.files?.["final.mp4"] ? (
            <video ref={playerRef} className="player" controls preload="metadata" poster={file("poster.jpg") + `?v=${v}`}
              src={file("final.mp4") + `?v=${v}`}>
              <track kind="captions" srcLang="en" label="English" src={file("final.srt") + `?v=${v}`} />
            </video>
          ) : <p className="muted">No video yet.</p>}
          {video.files?.["final.mp4"] && !running && (
            <div className="row" style={{ gap: 10, marginTop: 14, flexWrap: "wrap" }}>
              {video.files?.["player.html"] && <a className="btn btn-sm" href={file("player.html")} target="_blank" rel="noreferrer"><Icon name="open" size={16} />Open the animation in a browser</a>}
              <a className="btn btn-sm btn-ghost" href={file("final.srt") + "?download=1"}><Icon name="captions" size={16} />Captions (.srt)</a>
            </div>
          )}
        </section>

        {video.scenes?.length > 0 && (
          <section className="panel rise" aria-labelledby="ex-scenes-title">
            <PanelHead icon="list" tone="violet" title={<span id="ex-scenes-title">{isTalk ? "Script" : "Scenes"}</span>}
              subtitle={isTalk ? "Who says what, and what the wall screen shows. Click a line to play from there."
                : "What each scene shows, and the words said over it. Click a scene to play from there."} />
            <ol className="ex-scenes">
              {video.scenes.map((s, i) => (
                <li key={i}>
                  <button type="button" className="ex-scene" onClick={() => seek(s.start)} disabled={running || !video.files?.["final.mp4"]}>
                    <span className="ex-scene-time">{clock(Math.floor(s.start))}</span>
                    <span className={`badge ${s.speaker && s.speaker === video.scenes[0].speaker ? "b-violet" : "b-blue"}`}>{s.speaker || LAYOUT_LABEL[s.type] || s.type}</span>
                    <span className="ex-scene-text">
                      {s.title && <strong>{isTalk ? `Screen: ${s.title}` : s.title}</strong>}
                      <span className="meta">{s.say}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        )}

        {options && (
          <section className="panel rise" aria-labelledby="ex-remake-title">
            <PanelHead icon="palette" tone="turq" title={<span id="ex-remake-title">Look and sound</span>}
              subtitle={replans ? (talk ? "A new style, cast or length writes the script again (one AI call)." : "A new style or voice-over mode plans the scenes again (one AI call).")
                : "Remaking with a new look, logo, voice, speed, captions or music reuses the plan: no AI call."} />
            <LookFields options={options} look={look} set={(p) => setLook({ ...look, ...p })} disabled={running}
              logo={logo} setLogo={setLogo} currentLogo={video.files?.["logo.png"] ? file("logo.png") + `?v=${v}` : ""} />
            <div className="row" style={{ gap: 10, marginTop: 20, flexWrap: "wrap" }}>
              <button type="button" className="btn btn-primary" disabled={running || !changed} onClick={() => build()}>
                <Icon name="sparkles" size={18} />Remake video
              </button>
              <button type="button" className="btn" disabled={running} onClick={() => build({ replan: true })}
                title="Ask the AI for a new plan (one call, under a cent)">
                <Icon name="refresh" size={18} />{talk ? "Rewrite the script" : "New scene plan"}
              </button>
              {changed && <button type="button" className="btn btn-ghost" disabled={running}
                onClick={() => setLook(saved)}>Undo changes</button>}
            </div>
          </section>
        )}

        {video.narration && (
          <details className="disclosure panel rise">
            <summary><Icon name="chevronRight" size={16} />Narration · {words(video.narration)} words</summary>
            <p className="muted" style={{ whiteSpace: "pre-wrap", margin: "12px 0 0", maxHeight: 320, overflow: "auto" }}>{video.narration}</p>
          </details>
        )}
        <details className="disclosure panel rise" open={running || video.status === "failed" || undefined}>
          <summary><Icon name="chevronRight" size={16} />Activity</summary>
          <div style={{ marginTop: 12 }}><LogViewer lines={video.logs || []} /></div>
        </details>
      </div>
      <ConfirmDialog open={confirm} title="Delete this video?" confirmLabel="Delete"
        body={`“${video.title}”, its scenes, voice-over and video will be permanently removed.`}
        onConfirm={remove} onClose={() => setConfirm(false)} />
    </>
  );
}

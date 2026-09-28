import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "../icons.jsx";
import { api } from "../api.js";
import { transcriptStats } from "../format.js";
import { navigate } from "../router.js";
import { Alert, Field, PageHead, PanelHead, Switch, useToast } from "../ui.jsx";

const PLACEHOLDER = `This is our procurement assistant…

Click "Agents" and scroll down.
Each stage has its own agent…

---

Click "Chat", then enter: "Create a PR for 500 laptops"…`;

export default function NewVideoPage({ options }) {
  const toast = useToast();
  const fileInput = useRef(null);
  const [url, setUrl] = useState("");
  const [transcript, setTranscript] = useState("");
  const [title, setTitle] = useState("");
  const [voice, setVoice] = useState("af_sky");
  const [speed, setSpeed] = useState(1.1);
  const [music, setMusic] = useState("");
  const [zoom, setZoom] = useState(true);
  const [burn, setBurn] = useState(true);
  const [highlight, setHighlight] = useState(true);
  const [check, setCheck] = useState({ state: "idle" });
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (options?.music?.length && music === "") setMusic(options.music[0].id);
  }, [options]); // eslint-disable-line react-hooks/exhaustive-deps

  const stats = useMemo(() => transcriptStats(transcript), [transcript]);
  const urlValid = /^https?:\/\/(localhost|\[[0-9a-f:]+\]|\S+\.\S+)(:\d+)?(\/\S*)?$/i.test(url.trim());
  const azureReady = options?.azure_configured;
  const canSubmit = urlValid && stats.words >= 5 && !submitting && azureReady;

  const checkApp = async () => {
    setCheck({ state: "loading" });
    try {
      const result = await api.checkUrl(url.trim());
      setCheck({ state: "ok", ...result });
      if (!title && result.title) setTitle(result.title);
      toast(`Connected to ${result.title || "your app"}`);
    } catch (e) {
      setCheck({ state: "error", message: e.message });
    }
  };

  const upload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    file.text().then((t) => {
      setTranscript(t);
      toast(`Loaded ${file.name}`, "info");
    });
    e.target.value = "";
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const job = await api.createJob({
        url: url.trim(), transcript, title, voice, speed, music, zoom, burn_subtitles: burn, highlight_words: highlight,
      });
      toast("Drafting your script…");
      navigate(`/videos/${job.id}`);
    } catch (err) {
      toast(err.message, "error");
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate>
      <PageHead
        title="New video"
        subtitle="Point Zen Studio at your app and paste the narration. You'll review the drafted steps before anything is recorded."
        crumbs={[{ label: "Home", to: "/" }, { label: "New video" }]}
      />

      {options && !azureReady && (
        <div style={{ marginBottom: 24 }}>
          <Alert intent="warn" title="Azure OpenAI isn't configured">
            Add AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT to the server's .env file to enable script drafting.
          </Alert>
        </div>
      )}

      <div className="grid-2">
        <div className="stack">
          <section className="panel rise" aria-labelledby="app-title">
            <PanelHead icon="globe" tone="blue" title={<span id="app-title">App</span>} subtitle="The web app the video will demonstrate" />
            <div className="row" style={{ alignItems: "flex-end" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Field label="App URL" required htmlFor="app-url"
                  error={touched && url && !urlValid ? "Enter a full address, e.g. https://your-app.example.com or http://localhost:3000" : null}>
                  <div className="input-wrap">
                    <Icon name="link" size={18} />
                    <input id="app-url" className="input" type="url" inputMode="url" placeholder="https://your-app.example.com"
                      value={url} aria-invalid={touched && url && !urlValid ? "true" : undefined} required
                      onBlur={() => setTouched(true)}
                      onChange={(e) => { setUrl(e.target.value); setCheck({ state: "idle" }); }} />
                  </div>
                </Field>
              </div>
              <button type="button" className="btn" disabled={!urlValid || check.state === "loading"} onClick={checkApp}>
                {check.state === "loading" ? <><span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />Checking…</> : "Check app"}
              </button>
            </div>
            {check.state === "ok" && (
              <div style={{ marginTop: 16 }}>
                <Alert intent="ok" title={check.title || "App reachable"}>
                  Found {check.pages} page{check.pages === 1 ? "" : "s"} in {check.seconds}s.
                  {check.nav?.length > 0 && (
                    <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 8 }} aria-label="Navigation found">
                      {check.nav.map((n) => <span key={n} className="tag">{n}</span>)}
                    </div>
                  )}
                </Alert>
              </div>
            )}
            {check.state === "error" && (
              <div style={{ marginTop: 16 }}><Alert intent="error" title="Couldn't open the app">{check.message}</Alert></div>
            )}
          </section>

          <section className="panel rise" style={{ animationDelay: "60ms" }} aria-labelledby="transcript-title">
            <PanelHead icon="fileText" tone="violet" title={<span id="transcript-title">Transcript</span>}
              subtitle="Narration plus stage directions such as click “Approve”"
              action={
                <div className="row" style={{ gap: 4 }}>
                  <button type="button" className="btn btn-ghost" onClick={() => fileInput.current?.click()}><Icon name="upload" size={18} />Upload .txt</button>
                  {options?.sample_transcript && (
                    <button type="button" className="btn btn-ghost" onClick={() => setTranscript(options.sample_transcript)}>
                      <Icon name="sparkles" size={18} />Use sample
                    </button>
                  )}
                  <input ref={fileInput} type="file" accept=".txt,text/plain" hidden onChange={upload} />
                </div>
              } />
            <Field label="Narration script" required htmlFor="transcript"
              hint="Separate sections with a line containing ---. Lines like “Click Approve” become actions; everything else is spoken.">
              <textarea id="transcript" className="textarea" value={transcript} placeholder={PLACEHOLDER}
                onChange={(e) => setTranscript(e.target.value)} spellCheck={true} required />
            </Field>
            <div className="stats" style={{ marginTop: 12 }} aria-live="polite">
              <span>{stats.words} words</span>
              <span>≈ {stats.minutes.toFixed(1)} min narration</span>
              {stats.segments > 0 && <span>{stats.segments} sections</span>}
              <span className="row" style={{ gap: 6 }}><Icon name="list" size={16} />{stats.directions} stage directions detected</span>
            </div>
          </section>
        </div>

        <section className="panel rise" style={{ animationDelay: "120ms", position: "sticky", top: "calc(var(--header-h) + 24px)" }}
          aria-labelledby="settings-title">
          <PanelHead icon="settings" tone="turq" title={<span id="settings-title">Video settings</span>} />
          <div className="stack" style={{ gap: 18 }}>
            <Field label="Title" htmlFor="title">
              <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Procure-to-Pay walkthrough" />
            </Field>
            <Field label="Voice" htmlFor="voice">
              <select id="voice" className="select" value={voice} onChange={(e) => setVoice(e.target.value)}>
                {(options?.voices || [{ id: "af_sky", label: "Sky (US, female)" }]).map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            </Field>
            <Field label={`Speaking speed · ${speed.toFixed(2)}×`} htmlFor="speed">
              <input id="speed" className="range" type="range" min="0.8" max="1.4" step="0.05" value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))} aria-valuetext={`${speed.toFixed(2)} times`} />
            </Field>
            <Field label="Background music" htmlFor="music">
              <select id="music" className="select" value={music} onChange={(e) => setMusic(e.target.value)}>
                <option value="">None</option>
                {(options?.music || []).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
            </Field>
            <fieldset style={{ border: 0, padding: 0, margin: 0, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
              <legend className="label" style={{ padding: 0, marginBottom: 4 }}>Effects</legend>
              <Switch checked={zoom} onChange={setZoom} label="Auto-zoom on interactions" />
              <Switch checked={burn} onChange={setBurn} label="Show captions in the video" />
              <Switch checked={highlight} onChange={setHighlight} disabled={!burn} label="Highlight the spoken word" />
              <p className="meta" style={{ marginTop: 6 }}>A subtitle file (.srt) is always included.</p>
            </fieldset>
          </div>
        </section>
      </div>

      <div className="sticky-bar">
        <span className="badge b-violet plain">Step 1 of 3</span>
        <span className="grow">Next: Zen Studio drafts the on-screen steps with Azure OpenAI. You'll review them before recording starts.</span>
        <button type="button" className="btn" onClick={() => navigate("/")}>Cancel</button>
        <button type="submit" className="btn btn-primary btn-lg" disabled={!canSubmit}>
          {submitting ? <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2, borderColor: "rgba(255,255,255,.4)", borderTopColor: "#fff" }} /> : <Icon name="sparkles" />}
          Generate script
        </button>
      </div>
    </form>
  );
}

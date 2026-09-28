import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Field, PageHead, PanelHead, Segmented, Spinner, useToast } from "../ui.jsx";

function Status({ ok, yes, no }) {
  return <span className={`badge ${ok ? "b-green" : "b-yellow"}`}>{ok ? yes : no}</span>;
}

const codeStyle = {
  font: "12.5px/20px var(--mono)", background: "var(--surface-3)", padding: "12px 14px", borderRadius: 11,
  whiteSpace: "pre", overflowX: "auto", margin: "12px 0 8px",
};

export default function SettingsPage({ options, settings, setSettings }) {
  const toast = useToast();
  const [target, setTarget] = useState("");
  const [saving, setSaving] = useState(false);
  const [modeSaving, setModeSaving] = useState(false);
  const mode = settings?.recording_mode || "background";
  const saveMode = async (value) => {
    if (value === mode) return;
    setModeSaving(true);
    try {
      setSettings(await api.saveSettings({ recording_mode: value }));
      toast(value === "background" ? "Videos now record in the background" : "Videos now record full screen");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setModeSaving(false);
    }
  };
  useEffect(() => {
    if (settings) setTarget(String(settings.monthly_minutes_target));
  }, [settings]);

  if (!options) return <Spinner label="Loading settings…" />;

  const valid = /^\d+$/.test(target) && Number(target) >= 1 && Number(target) <= 10000;
  const save = async (e) => {
    e.preventDefault();
    if (!valid) return;
    setSaving(true);
    try {
      const s = await api.saveSettings({ monthly_minutes_target: Number(target) });
      setSettings(s);
      toast("Monthly target saved");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHead title="Settings" subtitle="How this Zen Studio server is configured." />
      <div className="features" style={{ alignItems: "start" }}>
        <section className="panel hoverable rise" aria-labelledby="usage-title">
          <PanelHead icon="gauge" tone="violet" title={<span id="usage-title">Monthly usage target</span>} subtitle="Drives the usage meters" />
          <form onSubmit={save} className="stack" style={{ gap: 12 }}>
            <Field label="Minutes of finished video per month" htmlFor="target" error={target && !valid ? "Enter a whole number from 1 to 10000" : null}
              hint="Usage counts the runtime of videos that finished this month.">
              <input id="target" className="input" inputMode="numeric" value={target} onChange={(e) => setTarget(e.target.value.trim())}
                aria-invalid={target && !valid ? "true" : undefined} />
            </Field>
            <div><button type="submit" className="btn btn-primary" disabled={!valid || saving}>Save</button></div>
          </form>
        </section>

        <section className="panel hoverable rise" style={{ animationDelay: "50ms" }} aria-labelledby="azure-title">
          <PanelHead icon="sparkles" tone="blue" title={<span id="azure-title">Script drafting</span>} subtitle="Azure OpenAI"
            action={<Status ok={options.azure_configured} yes="Connected" no="Not configured" />} />
          <p>Turns your transcript's stage directions into on-screen steps. Drafts are always reviewed before recording.</p>
          <pre style={codeStyle}>{"AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com\nAZURE_OPENAI_API_KEY=<key>\nAZURE_OPENAI_DEPLOYMENT=<deployment>\nAZURE_OPENAI_API_VERSION=2024-08-01-preview"}</pre>
          <p className="meta">Set these in the server's .env file.</p>
        </section>

        <section className="panel hoverable rise" style={{ animationDelay: "100ms" }} aria-labelledby="whisper-title">
          <PanelHead icon="mic" tone="turq" title={<span id="whisper-title">Word-level timing</span>}
            subtitle={options.word_timing === "exact" ? "From the Kokoro voice model" : options.word_timing === "whisper" ? "Whisper" : "Estimated"}
            action={<Status ok={options.word_timing !== "estimated"} yes={options.word_timing === "exact" ? "Exact" : "Whisper"} no="Estimated" />} />
          {options.word_timing === "exact" ? (
            <p>Every word's start and end comes straight from the voice model's own sound durations (25 ms steps), so captions
              and word-timed clicks land exactly on the spoken word. Fully offline, no extra model needed.</p>
          ) : (
            <>
              <p>Word times are estimated from pauses, so captions and word-timed clicks can drift. Install the Python package
                <code> onnx</code> on the server to enable exact timing from the voice model.</p>
              <pre style={codeStyle}>pip install onnx</pre>
            </>
          )}
        </section>

        <section className="panel hoverable rise" style={{ animationDelay: "150ms" }} aria-labelledby="rec-title">
          <PanelHead icon="server" tone="yellow" title={<span id="rec-title">Recording</span>} subtitle="How your app is captured" />
          <Segmented label="Recording mode" value={mode} onChange={saveMode} disabled={modeSaving || !settings}
            options={[{ value: "background", label: "Background", icon: "sparkles" }, { value: "screen", label: "Full screen", icon: "video" }]} />
          <p style={{ marginTop: 12 }}>
            {mode === "background"
              ? "The app runs in a hidden browser and is recorded silently, so you can keep using this computer while a video records."
              : "The app runs full screen on this computer's main display. Don't use the mouse or keyboard while it records; it stops safely if another window takes the screen."}
          </p>
          <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 8 }}>
            <li>Recorded at 1920×1080, constant 30 fps. Nothing plays on the speakers.</li>
            <li>One video records at a time; others wait in the queue.</li>
            <li>{options.voices?.length || 0} voices and {options.music?.length || 0} music track(s) available.</li>
          </ul>
        </section>
      </div>
    </>
  );
}

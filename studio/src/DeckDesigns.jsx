/* The pitch-deck design picker and generate bar, shared by a video's deck page and the link-only deck pages. */
import { useEffect, useMemo, useState } from "react";
import Icon from "./icons.jsx";
import { api } from "./api.js";
import { relativeTime } from "./format.js";
import DeckPreview from "./DeckPreview.jsx";
import { Alert, Field, PanelHead, Progress, Segmented, Switch, useToast } from "./ui.jsx";

export function useDeckTemplates() {
  const [templates, setTemplates] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.deckTemplates().then(setTemplates).catch((e) => setError(e.message));
  }, []);
  return { templates, error };
}

export const DEFAULT_BRIEF = { audience: "auto", length: "standard", focus: "", instructions: "" };
const AUDIENCE_ICON = { auto: "wand", executive: "gauge", investor: "activity", customer: "user", technical: "code",
  internal: "list", custom: "fileText" };
const INSTRUCTIONS_HINT = `e.g.
Slide 1: a pie chart of where managers' time goes - rostering 48 hrs, sick calls 20 hrs, overtime review 12 hrs.
Slide 2: a bar chart of roster time before (48 hrs) and after the pilot (3 hrs).
Then a slide on how it works, and finish with the pilot proposal. Keep it to 6 slides, no jargon.`;

export function useBriefOptions() {
  const [options, setOptions] = useState(null);
  useEffect(() => {
    api.briefOptions().then(setOptions).catch(() => setOptions({ audiences: [], lengths: [] }));
  }, []);
  return options;
}

/** Who the deck is for, how long it is, what it stresses. The story is written for this brief. */
export function BriefPicker({ value, onChange, disabled }) {
  const options = useBriefOptions();
  if (!options) return null;
  const set = (key, v) => onChange({ ...value, [key]: v });
  return (
    <div className="stack" style={{ gap: 18 }}>
      <fieldset className="brief-grid" disabled={disabled}>
        <legend className="label" style={{ marginBottom: 8 }}>Who is it for?</legend>
        {options.audiences.map((a) => (
          <label key={a.id} className={`brief-card${value.audience === a.id ? " selected" : ""}`}>
            <input type="radio" name="deck-audience" className="sr-only" value={a.id} checked={value.audience === a.id}
              onChange={() => set("audience", a.id)} />
            <span className="brief-icon" aria-hidden="true"><Icon name={AUDIENCE_ICON[a.id] || "user"} size={18} /></span>
            <span style={{ minWidth: 0 }}>
              <strong>{a.label}</strong>
              <span className="meta" style={{ display: "block" }}>{a.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {value.audience === "custom" && (
        <Field label="Your instructions" required htmlFor="deck-instructions"
          hint="Anything you want: slide order, charts (pie, bar, column, line, doughnut) with their numbers, tone, what to leave out. Slide 1 is the first slide after the title slide. Charts only use numbers from your text or these instructions.">
          <textarea id="deck-instructions" className="textarea" rows={5} maxLength={1500} disabled={disabled}
            value={value.instructions || ""} placeholder={INSTRUCTIONS_HINT}
            onChange={(e) => set("instructions", e.target.value)} />
        </Field>
      )}
      <div className="deck-form">
        <div>
          <span className="label" id="deck-length-label" style={{ display: "block", marginBottom: 8 }}>Length</span>
          <Segmented label="Deck length" value={value.length} onChange={(v) => set("length", v)} disabled={disabled}
            options={options.lengths.map((l) => ({ value: l.id, label: `${l.label} · ${l.slides.replace("-", "–")} slides` }))} />
          <span className="hint" style={{ display: "block", marginTop: 6 }}>Longer decks need enough material; the AI never pads with made-up content.</span>
        </div>
        <Field label="Focus (optional)" htmlFor="deck-focus" hint="Gets extra weight, e.g. its own slide, when your text covers it.">
          <input id="deck-focus" className="input" value={value.focus} maxLength={200} disabled={disabled}
            onChange={(e) => set("focus", e.target.value)} placeholder="e.g. compliance and audit, ROI, ease of rollout" />
        </Field>
      </div>
    </div>
  );
}

/** How each of the user's own requests (Custom brief) turned out. */
export function RequestReport({ requests }) {
  if (!requests?.length) return null;
  const icon = { done: ["checkCircle", "var(--green)"], not_done: ["alert", "var(--yellow-800)"], not_possible: ["xCircle", "var(--red)"] };
  const done = requests.filter((r) => r.status === "done").length;
  return (
    <section className="panel rise" aria-labelledby="requests-title">
      <PanelHead icon="checkCircle" tone="turq" title={<span id="requests-title">Your instructions</span>}
        subtitle={`${done} of ${requests.length} done`} />
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {requests.map((r, i) => {
          const [name, color] = icon[r.status] || icon.not_possible;
          return (
            <li key={i} className="check-row">
              <span style={{ color, flexShrink: 0 }}><Icon name={name} size={18} /></span>
              <span>
                <strong style={{ font: "650 13px/18px var(--font)", display: "block" }}>
                  {r.slide ? `Slide ${r.slide}: ` : ""}{r.request}
                </strong>
                <span className="meta">{r.status === "done" ? "Done" : r.note || (r.status === "not_possible" ? "Not possible in a deck" : "Not done")}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Toast when a deck the user is watching finishes (not on page load). */
export function useDeckFinishToast(status) {
  const toast = useToast();
  const [last, setLast] = useState(status);
  useEffect(() => {
    if (last === "running" && status === "done") toast("Your pitch deck is ready");
    if (last === "running" && status === "failed") toast("The deck could not be generated", "error");
    setLast(status);
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps
}

function TemplateCard({ t, title, shot, textOnly, selected, onSelect, disabled, delay, slides, downloadUrl }) {
  return (
    <div className={`deck-card rise${selected ? " selected" : ""}`} style={{ animationDelay: `${delay}ms` }}>
      <label className="deck-pick">
        <input type="radio" name="deck-template" className="sr-only" value={t.id} checked={selected} disabled={disabled}
          onChange={() => onSelect(t.id)} />
        <DeckPreview template={t.id} title={title} shot={shot} textOnly={textOnly} />
        <span className="deck-card-head">
          <span className="deck-check" aria-hidden="true"><Icon name="check" size={14} strokeWidth={3} /></span>
          <strong>{t.name}</strong>
          {slides && <span className="badge b-green plain">Generated</span>}
        </span>
        <span className="muted deck-desc">{t.description}</span>
        <span className="deck-tags">
          {t.tags.map((tag) => <span key={tag} className="chip">{tag}</span>)}
          <span className="meta">{t.fonts}</span>
        </span>
      </label>
      {(slides || t.sample) && (
        <div className="deck-card-foot">
          {slides && (
            <a className="btn btn-sm" href={downloadUrl} download>
              <Icon name="download" size={16} />Download · {slides} slides
            </a>
          )}
          {t.sample && (
            <a className="btn btn-sm btn-ghost" href={api.deckSampleUrl(t.id)} download>
              <Icon name="presentation" size={16} />View sample
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/** Radio cards, one per design. slides(id) -> slide count when that design was generated; fileUrl(id) -> its download. */
export function DesignGrid({ templates, choice, onSelect, title, shot, textOnly, slides = () => null, fileUrl, disabled, locked }) {
  return (
    <fieldset className="deck-grid" disabled={locked}>
      <legend className="sr-only">Deck design</legend>
      {templates.map((t, i) => (
        <TemplateCard key={t.id} t={t} title={title} shot={shot} textOnly={textOnly} selected={choice === t.id} onSelect={onSelect}
          disabled={disabled} delay={i * 40} slides={slides(t.id)} downloadUrl={fileUrl?.(t.id)} />
      ))}
    </fieldset>
  );
}

/** Sticky bar: selected design, new-story switch, generate/regenerate, and the status of the last deck.
 *  deck: {status, template, slides, error}; created(id) -> when that design was last generated. */
export function DeckBar({ templates, choice, deck, slides, fileUrl, created, canReuse, running, logs, onGenerate,
  disabled, extra }) {
  const [rewrite, setRewrite] = useState(false);
  const names = useMemo(() => Object.fromEntries(templates.map((t) => [t.id, t.name])), [templates]);
  const last = useMemo(() => {
    const start = logs.map((l) => l.includes("Generating the pitch deck")).lastIndexOf(true);
    return start < 0 ? "" : (logs.at(-1) || "").replace(/^\[[^\]]+\]\s*/, "");
  }, [logs]);
  const made = choice && slides(choice);
  const done = deck.status === "done" && deck.template && slides(deck.template);
  return (
    <section className="panel deck-bar" aria-labelledby="deck-bar-title">
      <div className="deck-bar-main">
        <div className="grow" style={{ minWidth: 220 }}>
          <span className="meta">Selected design</span>
          <h2 id="deck-bar-title" className="section-title">{names[choice] || "None"}</h2>
        </div>
        {canReuse && (
          <div style={{ minWidth: 260, maxWidth: 360 }}>
            <Switch label="Write a new story" checked={rewrite} onChange={setRewrite} disabled={running} />
            <span className="meta">{rewrite ? "Azure OpenAI rewrites the slides' text (about 30 s)." : "Reuses the story from your last deck, so switching design takes seconds."}</span>
          </div>
        )}
        {extra}
        {made && !running && (
          <a className="btn btn-lg" href={fileUrl(choice)} download><Icon name="download" size={18} />Download</a>
        )}
        <button type="button" className="btn btn-primary btn-lg" disabled={disabled || !choice || running}
          onClick={() => onGenerate(rewrite || !canReuse)}>
          {running ? <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} aria-hidden="true" /> : <Icon name={made ? "refresh" : "sparkles"} size={18} />}
          {running ? "Generating…" : made ? "Regenerate" : "Generate deck"}
        </button>
      </div>

      {running && (
        <div role="status" className="stack" style={{ gap: 10, marginTop: 16 }}>
          <span className="muted">Building the {names[deck.template] || names[choice]} deck: {last || "starting…"}</span>
          <Progress value={null} label="Generating the pitch deck" />
        </div>
      )}
      {!running && deck.status === "failed" && (
        <div style={{ marginTop: 16 }}>
          <Alert intent="error" title={`The ${names[deck.template] || ""} deck could not be generated`}>{deck.error}</Alert>
        </div>
      )}
      {!running && done && (
        <div style={{ marginTop: 16 }}>
          <Alert intent="ok" title={`${names[deck.template] || "Your"} deck is ready · ${slides(deck.template)} slides`}
            action={<a className="btn" href={fileUrl(deck.template)} download><Icon name="download" size={18} />Download PPTX</a>}>
            Pick another design to compare. Every design you generate is kept.
            {created(deck.template) && <span className="meta" style={{ display: "block" }}>Last generated: {relativeTime(created(deck.template))}</span>}
          </Alert>
        </div>
      )}
    </section>
  );
}

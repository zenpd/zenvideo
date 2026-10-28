/* Pitch decks from an app's link and/or a narration: the list, the new-deck form, and one deck's page. */
import { useCallback, useEffect, useState } from "react";
import Icon from "../icons.jsx";
import { api, deckFile } from "../api.js";
import { host, relativeTime } from "../format.js";
import { navigate, query } from "../router.js";
import { BriefPicker, DEFAULT_BRIEF, DeckBar, DesignGrid, RequestReport, useDeckFinishToast, useDeckTemplates } from "../DeckDesigns.jsx";
import { Alert, ConfirmDialog, Empty, Field, PageHead, PanelHead, Spinner, Switch, useToast } from "../ui.jsx";

const STATE = {
  running: ["b-violet", "Generating"],
  done: ["b-green", "Ready"],
  failed: ["b-red", "Failed"],
};

function DeckStatus({ status }) {
  const [cls, label] = STATE[status] || ["b-blue", status];
  return <span className={`badge ${cls}`}>{label}</span>;
}

/** One link deck, polled while it is being generated. */
function useLinkDeck(id) {
  const [deck, setDeck] = useState(null);
  const [error, setError] = useState(null);
  const refresh = useCallback(() => api.deck(id).then((d) => { setDeck(d); setError(null); }).catch((e) => setError(e.message)), [id]);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (deck?.status !== "running") return undefined;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [deck?.status, refresh]);
  return { deck, error, refresh };
}

// ── list ─────────────────────────────────────────────────────────────────────

export default function DecksPage() {
  const [decks, setDecks] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    const load = () => api.decks().then(setDecks).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  return (
    <>
      <PageHead
        title="Pitch decks"
        subtitle="Strong pitch decks from your app's link, a narration, call transcript or notes - no video needed. Decks made from a video show here too."
        actions={<button type="button" className="btn btn-primary btn-lg" onClick={() => navigate("/decks/new")}><Icon name="plus" />New deck</button>}
      />
      {error && <p className="error-text">Couldn't load decks: {error}</p>}
      {!decks && !error && <div className="cards">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 260 }} />)}</div>}
      {decks?.length === 0 && (
        <section className="panel">
          <Empty icon="presentation" title="No decks yet"
            body="Give your app's link and/or a narration, pick a design, and Zen Studio writes the slides. With a link, the app is explored page by page and its screens go on the slides."
            action={<button type="button" className="btn btn-primary" onClick={() => navigate("/decks/new")}><Icon name="plus" />New deck</button>} />
        </section>
      )}
      <ul className="cards" style={{ listStyle: "none", margin: 0, padding: 0, gridTemplateColumns: "repeat(auto-fill, minmax(min(340px, 100%), 1fr))" }}
        aria-label="Pitch decks">
        {(decks || []).map((d, i) => (
          <li key={d.id} className="rise" style={{ animationDelay: `${Math.min(i, 10) * 40}ms` }}>
            <a className="vcard hoverable" href={`#/decks/${d.id}`}>
              <span className="vcard-media">
                {d.pages ? <img src={api.deckShotUrl(d.id, "01.png")} alt="" loading="lazy" /> : <Icon name={d.url ? "presentation" : "fileText"} size={34} />}
              </span>
              <span className="vcard-body">
                <span style={{ font: "700 16px/22px var(--font)" }}>{d.title}</span>
                <span className="meta">{d.source_video ? `From video “${d.source_title}”` : d.url ? host(d.url) : "From narration"} · {relativeTime(d.created)}</span>
                <span className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                  <DeckStatus status={d.status} />
                  <span className="row meta" style={{ gap: 6 }}>
                    <Icon name="palette" size={15} />{Object.keys(d.decks || {}).length} design{Object.keys(d.decks || {}).length === 1 ? "" : "s"}
                  </span>
                </span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}

// ── new deck: the app's link and/or a narration ─────────────────────────────

const NARRATION_HINT = `Procure-to-pay is where enterprises quietly lose millions of hours. One purchase crosses a dozen disconnected systems...

---

This is an agentic P2P assistant. You don't need to learn ten different screens, you just chat...

---

Click "Approve". Notice that the assistant now provides the next steps as one-tap buttons...`;

const AUDIENCE_LABEL = { auto: "Auto", executive: "Executives", investor: "Investors", customer: "Customers",
  technical: "Technical team", internal: "Internal team", custom: "Custom instructions" };

const words = (t) => (t.trim() ? t.trim().split(/\s+/).length : 0);

export function NewDeckPage() {
  const toast = useToast();
  const { templates, error: loadError } = useDeckTemplates();
  const [narration, setNarration] = useState("");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [tryForms, setTryForms] = useState(false);
  const [choice, setChoice] = useState(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [brief, setBrief] = useState(DEFAULT_BRIEF);
  const [video] = useState(() => query().video || "");
  const [source, setSource] = useState(null);   // the video the narration comes from
  useEffect(() => { if (!choice && templates?.length) setChoice(templates[0].id); }, [templates, choice]);
  useEffect(() => {
    if (!video) return;
    api.narration(video).then((v) => {
      setSource(v);
      setNarration(v.narration);
      if (!/^untitled/i.test(v.title)) setTitle(v.title);
    }).catch((e) => toast(`Couldn't load the video's narration: ${e.message}`, "error"));
  }, [video]); // eslint-disable-line react-hooks/exhaustive-deps

  const n = words(narration);
  const link = source ? "" : url.trim();
  const urlOk = !link || /^https?:\/\/[^\s/]+/i.test(link);
  const narrationOk = n >= 20 || (!!link && n === 0);   // a link alone is enough
  const submit = async (e) => {
    e?.preventDefault();
    setTouched(true);
    if (!narrationOk || !urlOk || !choice) return;
    if (brief.audience === "custom" && !brief.instructions?.trim()) {
      toast("Write your instructions, or pick another option under “Who is it for?”", "error");
      return;
    }
    setBusy(true);
    try {
      const d = await api.createDeck({ narration: narration.trim(), url: link, try_forms: !!link && tryForms,
        title: title.trim(), template: choice, source_video: source?.id || "", source_title: source?.title || "", ...brief });
      toast(link ? "Exploring your app, then writing the slides…" : "Writing the slides…", "info");
      navigate(`/decks/${d.id}`);
    } catch (err) {
      toast(err.message, "error");
      setBusy(false);
    }
  };
  const names = Object.fromEntries((templates || []).map((t) => [t.id, t.name]));

  return (
    <form onSubmit={submit} noValidate>
      <PageHead
        crumbs={source ? [{ label: "Library", to: "/videos" }, { label: source.title, to: `/videos/${source.id}` }, { label: "Pitch deck" }]
          : [{ label: "Pitch decks", to: "/decks" }, { label: "New deck" }]}
        title={source ? "Create a pitch deck" : "New pitch deck"}
        subtitle="Give your app's link, a narration, call transcript or notes - or both - and pick a design. The AI plans the deck's story and slides in one call; switching design afterwards is free." />
      {video && !source && <div style={{ marginBottom: 16 }}><Spinner label="Loading the video's narration…" /></div>}
      {source && (
        <div style={{ marginBottom: 24 }}>
          <Alert intent="info" title={`From the video “${source.title}”`}>
            The slides are written from what the video says (no screenshots). Edit the text below if you like.
          </Alert>
        </div>
      )}
      <div className="stack">
        <section className="panel rise" aria-labelledby="app-title">
          <PanelHead icon="link" tone="blue" title={<span id="app-title">Your app</span>}
            subtitle={source ? "The deck is about the app this video shows." : "With a link, the app is explored page by page - its pages, tabs, lists and results - and the deck is built from what it shows. Its screens go on the slides."} />
          <div className="deck-form">
            <Field label="Product name" htmlFor="deck-title" hint="Optional. Otherwise it's taken from the app or the narration.">
              <input id="deck-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. PayFlow Orchestrator" />
            </Field>
            {!source && <Field label="App link" htmlFor="deck-url"
              error={touched && !urlOk ? "Enter a full address, e.g. https://your-app.example.com" : null}
              hint={link ? "Explored once (about a minute). It never deletes, saves, pays, sends or logs out." : "Give a link, a narration below, or both (the strongest deck)."}>
              <div className="input-wrap">
                <Icon name="link" size={18} />
                <input id="deck-url" className="input" type="url" inputMode="url" placeholder="https://your-app.example.com"
                  value={url} aria-invalid={touched && !urlOk ? "true" : undefined} onChange={(e) => setUrl(e.target.value)} />
              </div>
            </Field>}
            {link && (
              <div className="deck-form-wide">
                <Switch label="Try the app's forms (demo or test apps only)" checked={tryForms} onChange={setTryForms} disabled={busy} />
                <span className="meta" style={{ display: "block", marginTop: 4 }}>
                  {tryForms ? "Forms that are already filled in are submitted once with their values, to capture the results (e.g. a payment's routing). Nothing is typed, and delete, save, pay, send and similar buttons are never clicked."
                    : "Off: read-only - pages, tabs, lists and details are opened, but no form is submitted."}
                </span>
              </div>
            )}
          </div>
        </section>

        <section className="panel rise" aria-labelledby="narration-title">
          <PanelHead icon="mic" tone="violet" title={<span id="narration-title">Narration{link ? " (optional)" : ""}</span>}
            subtitle="A video narration, a call or meeting transcript (speaker names, timestamps and subtitles are fine), or notes. With a link too, the narration leads the story and the app adds the screens." />
          <Field label="Narration, transcript or notes" required={!link} htmlFor="deck-narration"
            error={touched && !narrationOk ? (link ? "Write at least a few sentences (20+ words), or leave it empty to use the app alone." : "Give your app's link above, or write at least a few sentences about the app (20+ words).") : null}
            hint={`${n.toLocaleString()} words. Click and typing instructions, filler words and small talk are ignored. Figures you mention can appear on the slides; the AI never makes them up.`}>
            <textarea id="deck-narration" className="textarea" rows={link ? 8 : 12} value={narration} placeholder={NARRATION_HINT}
              aria-invalid={touched && !narrationOk ? "true" : undefined} onChange={(e) => setNarration(e.target.value)} />
          </Field>
        </section>

        <section className="panel rise" aria-labelledby="brief-title">
          <PanelHead icon="user" tone="turq" title={<span id="brief-title">Deck brief</span>}
            subtitle="Who the deck is for decides what leads, what's left out and how it's said." />
          <BriefPicker value={brief} onChange={setBrief} disabled={busy} />
        </section>

        <section aria-labelledby="design-title" className="stack" style={{ gap: 14 }}>
          <h2 id="design-title" className="section-title">Choose a design</h2>
          {loadError && <Alert intent="error" title="Couldn't load the designs">{loadError}</Alert>}
          {!templates && !loadError && <Spinner label="Loading designs…" />}
          {templates && <DesignGrid templates={templates} choice={choice} onSelect={setChoice}
            title={title.trim() || "Your product"} textOnly={!link} disabled={busy} />}
        </section>

        <section className="panel deck-bar" aria-label="Generate">
          <div className="deck-bar-main">
            <div className="grow" style={{ minWidth: 220 }}>
              <span className="meta">Selected design</span>
              <h2 className="section-title">{names[choice] || "None"}</h2>
            </div>
            <span className="meta" style={{ maxWidth: 360 }}>
              {link ? "About 1-2 minutes: exploring your app page by page, then one AI call writes the story." : "About 15 seconds: one AI call plans and writes the whole deck."}
            </span>
            <button type="submit" className="btn btn-primary btn-lg" disabled={busy || !choice}>
              {busy ? <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} aria-hidden="true" /> : <Icon name="sparkles" size={18} />}
              {busy ? "Starting…" : "Generate deck"}
            </button>
          </div>
        </section>
      </div>
    </form>
  );
}

// ── one link deck ────────────────────────────────────────────────────────────

export function LinkDeckPage({ id }) {
  const toast = useToast();
  const { deck, error, refresh } = useLinkDeck(id);
  const { templates, error: loadError } = useDeckTemplates();
  const [choice, setChoice] = useState(null);
  const [starting, setStarting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [brief, setBrief] = useState(null);
  useEffect(() => { if (!brief && deck?.brief) setBrief(deck.brief); }, [deck, brief]);
  const briefChanged = !!(brief && deck?.brief && JSON.stringify(brief) !== JSON.stringify(deck.brief));
  useEffect(() => { if (!choice && deck?.template) setChoice(deck.template); }, [deck, choice]);
  useDeckFinishToast(deck?.status);

  if (error) return <Alert intent="error" title="Couldn't load this deck">{error}</Alert>;
  if (!deck || (!templates && !loadError)) return <div style={{ paddingTop: 80 }}><Spinner label="Loading…" /></div>;

  const running = deck.status === "running" || starting;
  const slides = (t) => (deck.files?.[deckFile(t)] && deck.decks?.[t]?.slides) || null;
  const fileUrl = (t) => api.deckDownloadUrl(deck.id, deckFile(t));
  const build = async (body) => {
    setStarting(true);
    try {
      await api.buildDeck(deck.id, { template: choice, ...(briefChanged ? brief : {}), ...body });
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
      await api.removeDeck(deck.id);
      toast("Deck deleted");
      navigate("/decks");
    } catch (e) {
      toast(e.message, "error");
    }
  };
  const first = deck.pages?.[0];

  return (
    <>
      <PageHead
        crumbs={[{ label: "Pitch decks", to: "/decks" }, { label: deck.title }]}
        title={<span className="row" style={{ gap: 14, flexWrap: "wrap" }}>{deck.title}<DeckStatus status={deck.status} /></span>}
        subtitle={<>
          {deck.source_video ? <a href={`#/videos/${deck.source_video}`}>From video “{deck.source_title}”</a>
            : deck.url ? <a href={deck.url} target="_blank" rel="noreferrer">{host(deck.url)}</a> : "From narration"}
          {" · "}created {relativeTime(deck.created)}
          {deck.usage?.calls > 0 && <> · {deck.usage.calls} Azure call{deck.usage.calls === 1 ? "" : "s"}, {(deck.usage.input_tokens + deck.usage.output_tokens).toLocaleString()} tokens, about ${deck.usage.cost_usd.toFixed(4)}</>}
        </>}
        actions={<>
          {deck.url && <button type="button" className="btn" disabled={running} onClick={() => build({ recapture: true })}
            title="Explore the app again for fresh screens, then write a new story">
            <Icon name="refresh" size={18} />Explore again
          </button>}
          <button type="button" className="btn btn-danger" disabled={running} onClick={() => setConfirm(true)}><Icon name="trash" size={18} />Delete</button>
        </>}
      />

      <div className="stack">
        {deck.narration && (
          <details className="disclosure panel rise">
            <summary><Icon name="chevronRight" size={16} />Narration · {deck.narration.trim().split(/\s+/).length} words</summary>
            <p className="muted" style={{ whiteSpace: "pre-wrap", margin: "12px 0 0", maxHeight: 320, overflow: "auto" }}>{deck.narration}</p>
          </details>
        )}
        {deck.url && <section className="panel rise" aria-labelledby="pages-title">
          <PanelHead icon="template" tone="turq" title={<span id="pages-title">Explored screens</span>}
            subtitle={deck.pages?.length ? `${deck.pages.length} screens of your app${deck.try_forms ? " (forms tried)" : ""}: what the deck is built from, and its screenshots` : "Screens appear here as the app is explored"} />
          {deck.pages?.length ? (
            <ul className="shot-strip" aria-label="Captured screens">
              {deck.pages.map((p) => (
                <li key={p.file}>
                  <a href={api.deckShotUrl(deck.id, p.file)} target="_blank" rel="noreferrer">
                    <img src={api.deckShotUrl(deck.id, p.file)} alt={`${p.label} screen`} loading="lazy" />
                  </a>
                  <span className="meta" style={{ display: "block", fontWeight: 650 }}>{p.label}</span>
                  {p.via && <span className="meta shot-via" title={p.via}>{p.via}</span>}
                </li>
              ))}
            </ul>
          ) : running ? <Spinner label="Opening your app…" /> : <p className="muted">No screens could be opened.</p>}
        </section>}

        {brief && (
          <details className="disclosure panel rise" open={briefChanged || undefined}>
            <summary>
              <Icon name="chevronRight" size={16} />Deck brief · {AUDIENCE_LABEL[deck.brief.audience] || "Auto"}, {deck.brief.length}
              {deck.brief.focus ? `, focus: ${deck.brief.focus}` : ""}
            </summary>
            <div style={{ marginTop: 16 }}>
              <BriefPicker value={brief} onChange={setBrief} disabled={running} />
              {briefChanged && (
                <div style={{ marginTop: 14 }}>
                  <Alert intent="info" title="New brief">
                    Generating rewrites the story for this brief (one AI call). <button type="button" className="btn btn-sm btn-ghost"
                      onClick={() => setBrief(deck.brief)}>Undo changes</button>
                  </Alert>
                </div>
              )}
            </div>
          </details>
        )}
        {deck.status !== "running" && <RequestReport requests={deck.requests} />}
        {loadError && <Alert intent="error" title="Couldn't load the designs">{loadError}</Alert>}
        {templates && (
          <>
            <DesignGrid templates={templates} choice={choice} onSelect={setChoice} title={deck.title} textOnly={!deck.pages?.length}
              shot={first ? api.deckShotUrl(deck.id, first.file) : null} slides={slides} fileUrl={fileUrl} disabled={running} />
            <DeckBar templates={templates} choice={choice} deck={deck} slides={slides} fileUrl={fileUrl}
              created={(t) => deck.decks?.[t]?.created} canReuse={deck.story && !briefChanged} running={running} logs={deck.logs || []}
              onGenerate={(rewrite) => build({ rewrite })} />
          </>
        )}
      </div>
      <ConfirmDialog open={confirm} title="Delete this deck?" confirmLabel="Delete"
        body={`“${deck.title}”, its captured screens and every design generated from it will be permanently removed.`}
        onConfirm={remove} onClose={() => setConfirm(false)} />
    </>
  );
}

/* Review a generated deck before it is final: every slide as a picture, comments on single slides or the whole deck,
   "Apply comments" (the AI revises the deck, which is rebuilt and shown again) and "Approve deck". */
import { useEffect, useState } from "react";
import Icon from "./icons.jsx";
import { api, deckFile } from "./api.js";
import { relativeTime } from "./format.js";
import { Alert, PanelHead, Spinner, useToast } from "./ui.jsx";

export default function DeckReview({ deck, running, names, onChanged }) {
  const toast = useToast();
  const [at, setAt] = useState(0);
  const [draft, setDraft] = useState("");
  const [comments, setComments] = useState([]);   // [{ slide: number | null, comment }]
  const [busy, setBusy] = useState(false);
  const pics = deck.preview || [];
  const total = pics.length;
  useEffect(() => { if (at >= total && total) setAt(total - 1); }, [total, at]);
  useEffect(() => {
    const key = (e) => {
      if (e.target.closest("textarea, input")) return;
      if (e.key === "ArrowRight") setAt((i) => Math.min(total - 1, i + 1));
      if (e.key === "ArrowLeft") setAt((i) => Math.max(0, i - 1));
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [total]);
  if (!total) return null;

  const v = encodeURIComponent(deck.updated || "");
  const url = (f) => api.deckPreviewUrl(deck.id, deck.template, f) + `?v=${v}`;
  const thumb = (f) => url(f.replace(".png", ".thumb.jpg"));
  const review = deck.status === "review";
  const approved = deck.status === "done" && deck.approved;
  const slide = at + 1;
  const add = (whole) => {
    const text = draft.trim();
    if (!text) return;
    setComments((c) => [...c, { slide: whole ? null : slide, comment: text }]);
    setDraft("");
  };
  const count = (n) => comments.filter((c) => c.slide === n).length;
  const apply = async () => {
    setBusy(true);
    try {
      await api.reviseDeck(deck.id, { template: deck.template, comments });
      setComments([]);
      toast("Revising the deck with your comments…", "info");
      await onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const approve = async () => {
    setBusy(true);
    try {
      await api.approveDeck(deck.id);
      toast("Deck approved - it's final");
      await onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const rounds = deck.revisions || [];

  return (
    <section className="panel rise review" aria-labelledby="review-title">
      <PanelHead icon="presentation" tone="violet"
        title={<span id="review-title">{approved ? "Your deck" : "Review your deck"}</span>}
        subtitle={approved ? `Approved ${relativeTime(deck.approved_at)} · ${names[deck.template] || ""} · ${total} slides`
          : `${names[deck.template] || ""} · ${total} slides. Click a slide and add comments on what to change, or approve it as it is.`}
        action={<span className={`badge ${approved ? "b-green" : running ? "b-violet" : "b-yellow"}`}>
          {approved ? "Approved" : running ? "Revising" : "Draft"}</span>} />

      <div className="review-stage">
        <button type="button" className="btn btn-ghost review-nav" aria-label="Previous slide" disabled={at === 0} onClick={() => setAt(at - 1)}>
          <Icon name="chevronRight" size={22} style={{ transform: "rotate(180deg)" }} />
        </button>
        <figure className="review-slide">
          <img src={url(pics[at])} alt={`Slide ${slide} of ${total}`} />
          {running && <div className="review-busy"><Spinner label="Revising the deck…" /></div>}
          <figcaption className="meta">Slide {slide} of {total}{count(slide) ? ` · ${count(slide)} comment${count(slide) > 1 ? "s" : ""}` : ""}</figcaption>
        </figure>
        <button type="button" className="btn btn-ghost review-nav" aria-label="Next slide" disabled={at === total - 1} onClick={() => setAt(at + 1)}>
          <Icon name="chevronRight" size={22} />
        </button>
      </div>

      <ol className="review-strip" aria-label="Slides">
        {pics.map((f, i) => (
          <li key={f}>
            <button type="button" className="review-thumb" aria-current={i === at ? "true" : undefined} onClick={() => setAt(i)}
              aria-label={`Slide ${i + 1}${count(i + 1) ? `, ${count(i + 1)} comments` : ""}`}>
              <img src={thumb(f)} alt="" loading="lazy" />
              <span className="review-num">{i + 1}</span>
              {count(i + 1) > 0 && <span className="review-count" aria-label={`${count(i + 1)} comments`}>{count(i + 1)}</span>}
            </button>
          </li>
        ))}
      </ol>

      {!approved && (
        <div className="review-comment">
          <label className="label" htmlFor="review-draft">Comment</label>
          <textarea id="review-draft" className="textarea" rows={3} value={draft} disabled={running || busy}
            placeholder={`What should change? e.g. "Make the title shorter", "Turn this into a chart", "Add a slide on security" or "Use a more formal tone"`}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) add(false); }} />
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn" disabled={!draft.trim() || running || busy} onClick={() => add(false)}>
              <Icon name="plus" size={16} />Add to slide {slide}
            </button>
            <button type="button" className="btn btn-ghost" disabled={!draft.trim() || running || busy} onClick={() => add(true)}>
              <Icon name="plus" size={16} />Add for the whole deck
            </button>
            <span className="meta">Ctrl + Enter adds it to this slide.</span>
          </div>
        </div>
      )}

      {comments.length > 0 && (
        <ul className="review-list" aria-label="Your comments">
          {comments.map((c, i) => (
            <li key={i}>
              <button type="button" className="chip" onClick={() => c.slide && setAt(c.slide - 1)}>{c.slide ? `Slide ${c.slide}` : "Whole deck"}</button>
              <span className="grow">{c.comment}</span>
              <button type="button" className="btn btn-sm btn-ghost" aria-label="Remove comment" disabled={busy}
                onClick={() => setComments(comments.filter((_, j) => j !== i))}><Icon name="x" size={16} /></button>
            </li>
          ))}
        </ul>
      )}

      <div className="review-actions">
        {!approved && (
          <>
            <button type="button" className={`btn btn-lg${comments.length ? " btn-primary" : ""}`} disabled={!comments.length || running || busy} onClick={apply}>
              <Icon name="sparkles" size={18} />{comments.length ? `Apply ${comments.length} comment${comments.length > 1 ? "s" : ""}` : "Apply comments"}
            </button>
            <button type="button" className={`btn btn-lg${comments.length ? "" : " btn-primary"}`} disabled={running || busy || !review} onClick={approve}
              title={comments.length ? "Your comments are not applied yet" : "The deck is final as it is"}>
              <Icon name="check" size={18} />Approve deck
            </button>
            <span className="meta">{comments.length ? "One AI call revises the deck (about 20-40 s); you can review it again." : "Approving makes this the final deck."}</span>
          </>
        )}
        {approved && (
          <a className="btn btn-primary btn-lg" href={api.deckDownloadUrl(deck.id, deckFile(deck.template))} download>
            <Icon name="download" size={18} />Download PPTX
          </a>
        )}
      </div>

      {rounds.length > 0 && (
        <details className="disclosure review-rounds" open={!approved || undefined}>
          <summary><Icon name="chevronRight" size={16} />Review rounds · {rounds.length}</summary>
          {rounds.slice().reverse().map((r) => (
            <div key={r.round} className="review-round">
              <strong>Round {r.round}</strong>
              <span className="meta"> · {relativeTime(r.at)}{r.usage ? ` · about $${r.usage.cost_usd.toFixed(4)}` : ""}</span>
              <ul>
                {(r.changes?.length ? r.changes : r.comments.map((c) => ({ comment: c.comment, slide: c.slide, status: "done", note: "" }))).map((c, i) => (
                  <li key={i} className="check-row">
                    <span style={{ color: c.status === "done" ? "var(--green)" : "var(--red)", flexShrink: 0 }}>
                      <Icon name={c.status === "done" ? "checkCircle" : "xCircle"} size={18} />
                    </span>
                    <span>
                      <strong style={{ font: "650 13px/18px var(--font)", display: "block" }}>{c.slide ? `Slide ${c.slide}: ` : ""}{c.comment}</strong>
                      {c.note && <span className="meta">{c.note}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </details>
      )}
      {deck.status === "failed" && <Alert intent="error" title="The revision failed">{deck.error}</Alert>}
    </section>
  );
}

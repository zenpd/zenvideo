/* Documents as deck material: the upload field on the new-deck form, what was read from them on a deck's page, what
   the brief asked for that they don't cover, and the Word report written from the same material. */
import { useRef, useState } from "react";
import Icon from "./icons.jsx";
import { api, reportFile } from "./api.js";
import { Alert, PanelHead, Spinner, useToast } from "./ui.jsx";

export const MAX_FILES = 5;
export const MAX_MB = 15;
const KINDS = { docx: "Word", pdf: "PDF", xlsx: "Excel" };
const kindOf = (name) => KINDS[(name.split(".").pop() || "").toLowerCase()];
const size = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

/** The files as the API takes them: [{ name, data: a data: URL }]. */
export const readFiles = (files) => Promise.all(files.map((f) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve({ name: f.name, data: r.result });
  r.onerror = () => reject(new Error(`Couldn't read “${f.name}”`));
  r.readAsDataURL(f);
})));

/** Pick or drop Word, PDF and Excel files. */
export function DocumentPicker({ files, onChange, disabled }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const [problem, setProblem] = useState("");
  const add = (list) => {
    const picked = [...list];
    const bad = picked.filter((f) => !kindOf(f.name));
    const big = picked.filter((f) => kindOf(f.name) && f.size > MAX_MB * 1048576);
    const ok = picked.filter((f) => kindOf(f.name) && f.size <= MAX_MB * 1048576 && !files.some((x) => x.name === f.name && x.size === f.size));
    const next = [...files, ...ok].slice(0, MAX_FILES);
    setProblem(bad.length ? `${bad.map((f) => f.name).join(", ")}: only Word (.docx), PDF and Excel (.xlsx) files can be used.`
      : big.length ? `${big.map((f) => f.name).join(", ")}: over ${MAX_MB} MB.`
        : files.length + ok.length > MAX_FILES ? `At most ${MAX_FILES} documents.` : "");
    onChange(next);
  };
  return (
    <div className="stack" style={{ gap: 12 }}>
      <label className={`dropzone${over ? " over" : ""}${disabled ? " disabled" : ""}`}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) add(e.dataTransfer.files); }}>
        <input ref={input} type="file" multiple accept=".docx,.pdf,.xlsx" disabled={disabled} className="sr-only"
          onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
        <Icon name="upload" size={26} />
        <span><strong>Drop files here</strong> or <span className="link-like">choose files</span></span>
        <span className="meta">Word (.docx), PDF and Excel (.xlsx) - up to {MAX_FILES} files, {MAX_MB} MB each</span>
      </label>
      {problem && <span className="error-text" role="alert">{problem}</span>}
      {files.length > 0 && (
        <ul className="file-list" aria-label="Chosen documents">
          {files.map((f, i) => (
            <li key={`${f.name}-${f.size}`}>
              <Icon name="fileText" size={18} />
              <span className="grow file-name" title={f.name}>{f.name}</span>
              <span className="chip">{kindOf(f.name)}</span>
              <span className="meta">{size(f.size)}</span>
              <button type="button" className="btn btn-sm btn-ghost" aria-label={`Remove ${f.name}`} disabled={disabled}
                onClick={() => onChange(files.filter((_, j) => j !== i))}><Icon name="x" size={16} /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** What was read from each uploaded file, and anything that couldn't be. */
export function DocumentsRead({ deck }) {
  const docs = deck.documents || [];
  if (!docs.length) return null;
  const notes = deck.document_notes || [];
  return (
    <details className="disclosure panel rise" open={notes.length > 0 || undefined}>
      <summary><Icon name="chevronRight" size={16} />Documents · {docs.length} file{docs.length === 1 ? "" : "s"}{notes.length ? ` · ${notes.length} note${notes.length === 1 ? "" : "s"}` : ""}</summary>
      <ul className="file-list" style={{ marginTop: 12 }}>
        {docs.map((d) => (
          <li key={d.name}>
            <Icon name="fileText" size={18} />
            <span className="grow file-name" title={d.name}>{d.name}</span>
            <span className="chip">{d.kind}</span>
            <span className="meta">{d.words ? `${d.sections} section${d.sections === 1 ? "" : "s"}, ${d.tables} table${d.tables === 1 ? "" : "s"}, ${d.words.toLocaleString()} words` : "Not read yet"}</span>
          </li>
        ))}
      </ul>
      {notes.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Alert intent="warn" title="Notes on your documents">
            <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </Alert>
        </div>
      )}
    </details>
  );
}

/** What the brief or instructions asked for that the material doesn't cover (deck and report together). */
export function Gaps({ deck }) {
  const all = [...(deck.gaps || []), ...(deck.report?.gaps || [])];
  const seen = new Set();
  const gaps = all.filter((g) => { const k = g.topic.toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; });
  if (!gaps.length || deck.status === "running") return null;
  return (
    <Alert intent="info" title="Not covered by your material">
      Nothing was made up for these - add them to your documents or notes and generate again if you need them.
      <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
        {gaps.map((g) => <li key={g.topic}><strong>{g.topic}</strong>{g.note ? ` - ${g.note}` : ""}</li>)}
      </ul>
    </Alert>
  );
}

export const OUTPUTS = [
  { id: "pptx", label: "PowerPoint deck", icon: "presentation", hint: "Designed slides you review, comment on and approve - plus an optional Word report" },
  { id: "docx", label: "Word document", icon: "fileText", hint: "A full written report: summary, key figures, sections with your tables and charts, next steps" },
  { id: "pdf", label: "PDF document", icon: "download", hint: "The same full report as a ready-to-share A4 PDF, with page numbers" },
];

/** What to make: a deck, a Word document or a PDF. */
export function OutputPicker({ value, onChange, disabled }) {
  return (
    <div className="output-grid" role="radiogroup" aria-label="What to make">
      {OUTPUTS.map((o) => (
        <label key={o.id} className={`brief-card${value === o.id ? " selected" : ""}`}>
          <input type="radio" name="deck-output" className="sr-only" value={o.id} checked={value === o.id}
            disabled={disabled} onChange={() => onChange(o.id)} />
          <span className="brief-icon" aria-hidden="true"><Icon name={o.icon} size={18} /></span>
          <span style={{ minWidth: 0 }}>
            <strong>{o.label}</strong>
            <span className="meta" style={{ display: "block" }}>{o.hint}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

/** The report: write it, read it in the browser, download it. For a Word or PDF job it is the result itself
    (brief: a changed brief to write it again with). */
export function ReportPanel({ deck, running, onChanged, brief = null }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState((deck.output || "pptx") !== "pptx");
  const t = deck.template;
  const doc = (deck.output || "pptx") !== "pptx";
  const pdf = deck.output === "pdf";
  const ready = pdf ? !!deck.pdf_files?.[t] : !!deck.report_files?.[t];
  const r = deck.report;
  const last = (deck.logs?.at(-1) || "").replace(/^\[[^\]]+\]\s*/, "");
  const start = async (rewrite) => {
    setBusy(true);
    try {
      await api.writeReport(deck.id, { template: t, rewrite, ...(brief || {}) });
      toast(rewrite || !r ? `Writing the ${pdf ? "PDF" : "Word"} ${doc ? "document" : "report"}…` : "Building the report in this design…", "info");
      await onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const v = encodeURIComponent(deck.updated || "");
  return (
    <section className="panel rise" aria-labelledby="report-title">
      <PanelHead icon="fileText" tone="blue" title={<span id="report-title">{doc ? `Your ${pdf ? "PDF" : "Word"} document` : "Word report"}</span>}
        subtitle={r ? `${r.title} · ${r.sections} sections, ${r.tables} table${r.tables === 1 ? "" : "s"}, ${r.charts} chart${r.charts === 1 ? "" : "s"}${doc ? "" : " · in the deck's design"}`
          : doc ? "Your material written up in full: executive summary, key figures, sections with tables and charts from your documents, conclusions and next steps, and the sources of every fact."
            : "The same material written up in full: executive summary, key figures, sections with tables and charts from your documents, conclusions and next steps, and the sources of every fact."}
        action={running ? <span className="badge b-violet">Writing</span> : ready ? <span className="badge b-green">Ready</span> : null} />
      {running && doc && <div style={{ marginBottom: 14 }}><Spinner label={last || "Reading your material…"} /></div>}
      <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
        {ready ? (
          <>
            <a className="btn btn-primary" href={api.deckDownloadUrl(deck.id, reportFile(t, pdf ? "pdf" : "docx"))} download>
              <Icon name="download" size={18} />Download {pdf ? "PDF" : "Word"}
            </a>
            {pdf && deck.report_files?.[t] && <a className="btn" href={api.deckDownloadUrl(deck.id, reportFile(t))} download><Icon name="fileText" size={18} />Word version</a>}
            <button type="button" className="btn" onClick={() => setShow(!show)} aria-expanded={show}>
              <Icon name="open" size={18} />{show ? "Hide the report" : "Read it here"}
            </button>
            <a className="btn btn-ghost" href={api.reportPreviewUrl(deck.id, t)} target="_blank" rel="noreferrer"><Icon name="globe" size={18} />Open in a new tab</a>
            <button type="button" className={`btn${brief ? " btn-primary" : " btn-ghost"}`} disabled={running || busy} onClick={() => start(true)}
              title="Write the text again (one AI call)"><Icon name="refresh" size={18} />{brief ? "Write again with the new brief" : "Rewrite"}</button>
          </>
        ) : running ? null : (
          <>
            <button type="button" className="btn btn-primary" disabled={running || busy} onClick={() => start(!!doc)}>
              {busy ? <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} aria-hidden="true" /> : <Icon name="sparkles" size={18} />}
              {doc ? "Write it again" : r ? "Build it in this design" : "Write the Word report"}
            </button>
            <span className="meta">{r ? "Free - the text is already written." : "One AI call (under a cent), about 20-40 seconds."}</span>
          </>
        )}
        {running && !ready && !doc && <Spinner label="Working…" />}
      </div>
      {ready && show && (
        <iframe className="report-frame" title="The Word report" src={`${api.reportPreviewUrl(deck.id, t)}&v=${v}`} />
      )}
    </section>
  );
}

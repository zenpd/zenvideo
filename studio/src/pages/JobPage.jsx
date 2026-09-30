import { useEffect, useState } from "react";
import Icon from "../icons.jsx";
import { api } from "../api.js";
import { STAGES, duration, host, relativeTime } from "../format.js";
import { useJob } from "../hooks.js";
import { navigate } from "../router.js";
import { Alert, ConfirmDialog, LogViewer, PageHead, PanelHead, Progress, Spinner, StageTracker, StatusBadge, Tabs, useToast } from "../ui.jsx";

const ACTION_ICON = {
  click: "click", fill: "keyboard", press: "keyboard", hover: "cursor", scroll: "scroll", scroll_to: "scroll",
  wait_for: "hourglass", wait: "clock", goto: "open", focus: "zoom",
};

function friendly(action) {
  const label = action.label;
  const pick = (key) => (label.match(new RegExp(`${key}='([^']+)'`)) || [])[1];
  const target = pick("name") || pick("text") || pick("placeholder") || pick("label") || pick("testid") || pick("css");
  const value = (label.match(/'value': '([^']+)'/) || [])[1];
  const by = (label.match(/'by': (-?\d+)/) || [])[1];
  switch (action.kind) {
    case "click": return target ? `Click “${target}”` : "Click";
    case "fill": return `Type “${value || "…"}”${target ? ` into ${target}` : ""}`;
    case "press": return `Press ${(label.match(/'key': '([^']+)'/) || [])[1] || "key"}`;
    case "hover": return target ? `Point at “${target}”` : "Point";
    case "scroll": return by ? `Scroll ${Number(by) < 0 ? "up" : "down"} ${Math.abs(by)} px` : "Scroll";
    case "scroll_to": return target ? `Scroll to “${target}”` : "Scroll";
    case "wait_for": return target ? `Wait for “${target}”` : "Wait";
    case "goto": return "Open page";
    default: return label;
  }
}

function Segments({ summary }) {
  if (summary?.error) return <Alert intent="error" title="The script has a problem">{summary.error}</Alert>;
  return (
    <ol style={{ listStyle: "none", margin: 0, padding: 0 }} aria-label="Segments">
      {(summary?.segments || []).map((seg) => (
        <li key={seg.index} className="segment rise" style={{ animationDelay: `${Math.min(seg.index, 12) * 30}ms` }}>
          <div className="seg-head">
            <span className="seg-num" aria-hidden="true">{seg.index}</span>
            <h3 style={{ font: "700 16px/22px var(--font)" }}><span className="sr-only">Segment {seg.index}: </span>{seg.id}</h3>
            {seg.silent && <span className="badge b-blue plain">No narration</span>}
            <span className="meta" style={{ marginLeft: "auto" }}>{seg.actions.length} action{seg.actions.length === 1 ? "" : "s"}</span>
          </div>
          {!seg.silent && (
            <p className="narration"><Icon name="mic" size={18} /><span>{seg.say}</span></p>
          )}
          {seg.actions.length > 0 && (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {seg.actions.map((a, i) => (
                <li key={i} className="action" title={a.label}>
                  <Icon name={ACTION_ICON[a.kind] || "list"} size={18} />
                  <span className="grow">{friendly(a)}</span>
                  {a.at_word && <span className="badge b-violet plain">on “{a.at_word}”{a.until_word ? ` → “${a.until_word}”` : ""}</span>}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

function ReviewPanel({ job, onChanged }) {
  const toast = useToast();
  const [tab, setTab] = useState("steps");
  const [draft, setDraft] = useState(job.script || "");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => setDraft(job.script || ""), [job.script]);

  const dirty = draft !== (job.script || "");
  const minutes = Math.max(1, Math.round(((job.summary?.estimated_seconds || 60) * 1.25) / 60));

  const act = async (kind, fn, ok) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      if (ok) toast(ok);
      onChanged();
    } catch (e) {
      if (kind === "save") setError(e.message);
      else toast(e.message, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="panel rise" aria-labelledby="review-title">
      <PanelHead icon="list" tone="violet" title={<span id="review-title">Review the drafted steps</span>}
        subtitle={`${job.summary?.segments?.length || 0} segments · ${job.summary?.actions || 0} actions · about ${minutes} min to record`} />
      {job.recording_mode === "screen" ? (
        <Alert intent="warn" title="Recording takes over this computer's screen">
          For about {minutes} min the app runs full screen while it's captured. Close notifications and
          don't use the mouse or keyboard until it finishes.
        </Alert>
      ) : (
        <Alert intent="info" title="Records in the background">
          The app runs in a hidden browser for about {minutes} min. You can keep using this computer while it records.
        </Alert>
      )}
      <div style={{ margin: "20px 0 16px" }}>
        <Tabs label="Script view" value={tab} onChange={setTab}
          tabs={[{ value: "steps", label: "Steps", icon: "list" }, { value: "yaml", label: "Script (YAML)", icon: "code" }]} />
      </div>
      {tab === "steps" ? (
        <div role="tabpanel" aria-label="Steps"><Segments summary={job.summary} /></div>
      ) : (
        <div role="tabpanel" aria-label="Script (YAML)" className="stack" style={{ gap: 12 }}>
          <label htmlFor="yaml" className="sr-only">Script YAML</label>
          <textarea id="yaml" className="textarea code" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} />
          {error && <Alert intent="error" title="Not saved">{error}</Alert>}
          <div className="row">
            <button type="button" className="btn" disabled={!dirty || busy} onClick={() => act("save", () => api.saveScript(job.id, draft), "Script saved")}>Save changes</button>
            <button type="button" className="btn btn-ghost" disabled={!dirty} onClick={() => setDraft(job.script || "")}>Discard</button>
          </div>
        </div>
      )}
      <div className="row" style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
        <span className="muted" style={{ flex: 1, minWidth: 220 }}>
          {dirty ? "Save or discard your edits before recording." : "Everything look right? Recording starts immediately."}
        </span>
        <button type="button" className="btn btn-lg" disabled={!!busy} onClick={() => act("redraft", () => api.redraft(job.id), "Redrafting the script…")}>
          <Icon name="refresh" size={18} />Redraft
        </button>
        <button type="button" className="btn btn-primary btn-lg" disabled={dirty || !!busy || !!job.summary?.error}
          onClick={() => act("start", () => api.approve(job.id), "Recording starts now")}>
          <Icon name="play" size={18} />Start recording
        </button>
      </div>
    </section>
  );
}

function WorkingPanel({ job, logs }) {
  const stage = STAGES.find((x) => x.key === job.stage);
  const determinate = ["narration", "recording", "render"].includes(job.stage) && job.status === "producing";
  const text = {
    drafting: "Scanning your app and drafting the steps with Azure OpenAI…",
    queued: "Waiting for another recording to finish…",
    producing: {
      narration: "Generating the voice-over…",
      recording: job.recording_mode === "screen"
        ? "Recording your app. Please don't use this computer's mouse or keyboard."
        : "Recording your app in a hidden browser. You can keep working.",
      render: "Adding zoom, captions and music…",
      check: "Verifying audio/video sync…",
    }[job.stage],
  }[job.status];
  return (
    <section className="panel rise" aria-labelledby="working-title" aria-busy="true">
      <div className="row" style={{ marginBottom: 16 }}>
        <span className="spinner" aria-hidden="true" />
        <div style={{ flex: 1 }}>
          <h2 id="working-title" className="section-title">{stage?.label || "Working"}</h2>
          <p className="muted">{text}</p>
        </div>
        {determinate && <strong style={{ font: "750 20px/28px var(--font)" }}>{Math.round((job.progress || 0) * 100)}%</strong>}
      </div>
      <Progress value={determinate ? job.progress || 0 : null} large label={`${stage?.label || "Job"} progress`} />
      <details className="disclosure" open style={{ marginTop: 16 }}>
        <summary><Icon name="chevronRight" size={16} />Activity</summary>
        <LogViewer lines={logs} />
      </details>
    </section>
  );
}

function CheckResults({ check }) {
  if (!check) return null;
  return (
    <section className="panel" aria-labelledby="check-title">
      <PanelHead icon="checkCircle" tone="turq" title={<span id="check-title">Sync check</span>}
        action={<span className={`badge ${check.passed ? "b-green" : "b-red"}`}>{check.passed ? "Passed" : "Failed"}</span>} />
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {check.results.map((r) => (
          <li key={r.check} className="check-row">
            <span style={{ color: r.ok ? "var(--green)" : r.level === "warn" ? "var(--yellow-800)" : "var(--red)", flexShrink: 0 }}>
              <Icon name={r.ok ? "checkCircle" : r.level === "warn" ? "alert" : "xCircle"} size={18} />
            </span>
            <span>
              <strong style={{ font: "650 13px/18px var(--font)", display: "block" }}>{r.check}</strong>
              <span className="meta">{r.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DonePanel({ job, logs }) {
  return (
    <div className="grid-2">
      <div className="stack">
        <section className="panel rise" aria-label="Video player" style={{ padding: 14 }}>
          <video className="player" controls preload="metadata"
            poster={job.files?.["poster.jpg"] ? api.fileUrl(job.id, "poster.jpg") : undefined} src={api.fileUrl(job.id, "final.mp4")}>
            <track kind="captions" srcLang="en" label="English" src={api.fileUrl(job.id, "final.srt")} />
          </video>
        </section>
        <details className="disclosure panel">
          <summary><Icon name="chevronRight" size={16} />Activity log</summary>
          <LogViewer lines={logs} />
        </details>
      </div>
      <div className="stack">
        <section className="panel rise" aria-labelledby="dl-title">
          <PanelHead icon="download" tone="blue" title={<span id="dl-title">Downloads</span>} />
          <div className="stack" style={{ gap: 8 }}>
            <a className="btn btn-primary" href={api.fileUrl(job.id, "final.mp4")} download><Icon name="download" size={18} />Video (MP4)</a>
            <a className="btn" href={api.fileUrl(job.id, "final.srt")} download><Icon name="captions" size={18} />Captions (SRT)</a>
            <a className="btn" href={api.fileUrl(job.id, "demo.yaml")} download><Icon name="fileText" size={18} />Script (YAML)</a>
          </div>
        </section>
        <section className="panel rise" aria-labelledby="details-title">
          <PanelHead icon="info" tone="violet" title={<span id="details-title">Details</span>} />
          <dl className="facts" style={{ margin: 0 }}>
            <dt className="meta">Length</dt><dd style={{ margin: 0 }}>{duration(job.duration)}</dd>
            <dt className="meta">App</dt><dd style={{ margin: 0 }}><a href={job.url} target="_blank" rel="noreferrer">{host(job.url)}</a></dd>
            <dt className="meta">Voice</dt><dd style={{ margin: 0 }}>{job.options?.voice}</dd>
            <dt className="meta">Created</dt><dd style={{ margin: 0 }}>{relativeTime(job.created)}</dd>
          </dl>
        </section>
        <CheckResults check={job.check} />
      </div>
    </div>
  );
}

export default function JobPage({ id }) {
  const toast = useToast();
  const { job, logs, error, refresh } = useJob(id);
  const [confirm, setConfirm] = useState(false);

  if (error) return <Alert intent="error" title="Couldn't load this video">{error}</Alert>;
  if (!job) return <div style={{ paddingTop: 80 }}><Spinner label="Loading…" /></div>;

  const running = ["drafting", "queued", "producing"].includes(job.status);
  const retry = async () => {
    try {
      await api.retry(job.id);
      toast(job.status === "done" ? "Back to review: check the steps, then record again" : "Retrying…", "info");
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  };
  const remove = async () => {
    setConfirm(false);
    await api.remove(job.id);
    toast("Video deleted");
    navigate("/videos");
  };

  return (
    <>
      <PageHead
        crumbs={[{ label: "Library", to: "/videos" }, { label: job.title }]}
        title={<span className="row" style={{ gap: 14, flexWrap: "wrap" }}>{job.title}<StatusBadge status={job.status} /></span>}
        subtitle={`${host(job.url)} · created ${relativeTime(job.created)}`}
        actions={<>
          {job.status === "failed" && <button type="button" className="btn" onClick={retry}><Icon name="refresh" size={18} />Retry</button>}
          {job.status === "done" && <button type="button" className="btn" onClick={retry}><Icon name="refresh" size={18} />Record again</button>}
          <button type="button" className="btn btn-danger" disabled={running} onClick={() => setConfirm(true)}><Icon name="trash" size={18} />Delete</button>
        </>}
      />
      <StageTracker job={job} />
      <div className="stack" style={{ marginTop: 24 }}>
        {job.status === "failed" && (
          <Alert intent="error" title={`${STAGES.find((x) => x.key === job.stage)?.label || "Job"} failed`}
            action={<button type="button" className="btn" onClick={retry}>Retry</button>}>{job.error}</Alert>
        )}
        {job.status === "review" && <ReviewPanel job={job} onChanged={refresh} />}
        {running && <WorkingPanel job={job} logs={logs} />}
        {(job.status === "done" || (job.status === "failed" && job.files?.["final.mp4"])) && <DonePanel job={job} logs={logs} />}
        {job.status === "failed" && !job.files?.["final.mp4"] && (
          <section className="panel" aria-labelledby="log-title">
            <h2 id="log-title" className="section-title" style={{ marginBottom: 12 }}>Activity log</h2>
            <LogViewer lines={logs} />
          </section>
        )}
      </div>
      <ConfirmDialog open={confirm} title="Delete this video?" confirmLabel="Delete"
        body={`“${job.title}”, its script and all generated files will be permanently removed.`}
        onConfirm={remove} onClose={() => setConfirm(false)} />
    </>
  );
}

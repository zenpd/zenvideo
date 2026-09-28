import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import Icon from "./icons.jsx";
import { STAGES, STATUS } from "./format.js";

/* ── toasts ─────────────────────────────────────────────────────────────── */
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((message, intent = "success") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, intent }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  const icon = { success: "check", error: "x", info: "info" };
  const bg = { success: "var(--green)", error: "var(--red)", info: "var(--blue)" };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            <span className="t-icon" style={{ background: bg[t.intent] }}><Icon name={icon[t.intent]} size={15} strokeWidth={2.6} /></span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ── layout bits ────────────────────────────────────────────────────────── */
export function PageHead({ title, subtitle, crumbs, actions }) {
  return (
    <header className="page-head">
      <div className="titles">
        {crumbs && (
          <nav aria-label="Breadcrumb">
            <ol className="crumbs" style={{ listStyle: "none", padding: 0, margin: "0 0 8px" }}>
              {crumbs.map((c, i) => (
                <li key={c.label} className="row" style={{ gap: 8 }}>
                  {c.to ? <a href={`#${c.to}`}>{c.label}</a> : <span aria-current="page">{c.label}</span>}
                  {i < crumbs.length - 1 && <Icon name="chevronRight" size={14} />}
                </li>
              ))}
            </ol>
          </nav>
        )}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="row" style={{ flexWrap: "wrap" }}>{actions}</div>}
    </header>
  );
}

export function PanelHead({ icon, tone = "blue", title, subtitle, action }) {
  const tones = {
    blue: ["var(--chip-blue)", "var(--chip-blue-text)"],
    violet: ["var(--chip-violet)", "var(--chip-violet-text)"],
    turq: ["var(--chip-turq)", "var(--chip-turq-text)"],
    yellow: ["var(--chip-yellow)", "var(--chip-yellow-text)"],
  };
  const [bg, fg] = tones[tone];
  return (
    <div className="panel-head">
      {icon && <div className="panel-icon" style={{ background: bg, color: fg }}><Icon name={icon} /></div>}
      <div className="grow">
        <h2 className="section-title">{title}</h2>
        {subtitle && <p className="meta" style={{ fontSize: 12 }}>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Alert({ intent = "info", title, children, action }) {
  const icon = { warn: "alert", error: "xCircle", ok: "checkCircle", info: "info" }[intent];
  return (
    <div className={`alert alert-${intent}`} role={intent === "error" ? "alert" : undefined}>
      <Icon name={icon} />
      <div className="grow">
        {title && <strong>{title}</strong>}
        <div>{children}</div>
      </div>
      {action}
    </div>
  );
}

export function StatusBadge({ status }) {
  const meta = STATUS[status] || { label: status, color: "informative" };
  const cls = { success: "b-green", danger: "b-red", warning: "b-yellow", brand: "b-violet", informative: "b-blue" }[meta.color];
  return <span className={`badge ${cls}`}>{meta.label}</span>;
}

export const STATUS_DOT = { done: "var(--green)", failed: "var(--red)", review: "var(--yellow)", producing: "var(--violet)", queued: "var(--blue)", drafting: "var(--blue)" };

export function Spinner({ label }) {
  return (
    <span className="row" role="status">
      <span className="spinner" aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  );
}

export function Empty({ icon = "video", title, body, action }) {
  return (
    <div className="empty">
      <div className="empty-icon"><Icon name={icon} size={30} /></div>
      <h3 className="section-title">{title}</h3>
      <p className="muted" style={{ maxWidth: 440 }}>{body}</p>
      {action}
    </div>
  );
}

/* ── charts ─────────────────────────────────────────────────────────────── */
export function Sparkline({ values, width = 96, height = 36, color = "var(--blue)", label }) {
  const id = useId().replace(/:/g, "");
  const max = Math.max(1, ...values);
  const step = width / Math.max(1, values.length - 1);
  const pts = values.map((v, i) => [i * step, height - 4 - (v / max) * (height - 8)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <defs>
        <linearGradient id={`g${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L${width},${height} L0,${height} Z`} fill={`url(#g${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      {pts.length > 0 && <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="3" fill={color} />}
    </svg>
  );
}

export function Bars({ values, labels, height = 120, label }) {
  const max = Math.max(1, ...values);
  return (
    <div role="img" aria-label={label} style={{ display: "grid", gridTemplateColumns: `repeat(${values.length}, 1fr)`, gap: 8, alignItems: "end", height }}>
      {values.map((v, i) => (
        <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, height: "100%", justifyContent: "flex-end" }}>
          <div
            title={`${labels?.[i] ?? ""}: ${v}`}
            style={{
              width: "100%", maxWidth: 26, borderRadius: 7,
              height: `${Math.max(6, (v / max) * (height - 22))}px`,
              background: v ? "linear-gradient(180deg, var(--violet-400), var(--blue))" : "var(--surface-3)",
              transition: "height 500ms var(--ease)",
            }}
          />
          <span className="meta">{labels?.[i]}</span>
        </div>
      ))}
    </div>
  );
}

export function Gauge({ value, size = 128, label }) {
  const id = useId().replace(/:/g, "");
  const r = size / 2 - 12;
  const c = Math.PI * r;
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <svg width={size} height={size / 2 + 16} viewBox={`0 0 ${size} ${size / 2 + 16}`} role="img" aria-label={label}>
      <defs>
        <linearGradient id={`gg${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--turquoise)" />
          <stop offset="55%" stopColor="var(--blue)" />
          <stop offset="100%" stopColor="var(--violet)" />
        </linearGradient>
      </defs>
      <path d={`M12,${size / 2 + 4} A${r},${r} 0 0 1 ${size - 12},${size / 2 + 4}`} fill="none" stroke="var(--surface-3)" strokeWidth="12" strokeLinecap="round" />
      <path d={`M12,${size / 2 + 4} A${r},${r} 0 0 1 ${size - 12},${size / 2 + 4}`} fill="none" stroke={`url(#gg${id})`} strokeWidth="12"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} style={{ transition: "stroke-dashoffset 800ms var(--ease)" }} />
    </svg>
  );
}

export function Progress({ value, large, label }) {
  const indeterminate = value == null;
  return (
    <div className={`progress${large ? " lg" : ""}${indeterminate ? " indeterminate" : ""}`} role="progressbar"
      aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={indeterminate ? undefined : Math.round(value * 100)}>
      <span style={{ width: `${indeterminate ? 35 : Math.round(value * 100)}%` }} />
    </div>
  );
}

/* ── forms ──────────────────────────────────────────────────────────────── */
export function Field({ label, required, hint, error, htmlFor, children }) {
  return (
    <div className="field">
      {label && <label className="label" htmlFor={htmlFor}>{label}{required && <span className="req" aria-hidden="true">*</span>}</label>}
      {children}
      {error ? <span className="error-text" role="alert">{error}</span> : hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }) {
  return (
    <label className="switch">
      <span>{label}</span>
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" aria-hidden="true" />
    </label>
  );
}

export function Tabs({ tabs, value, onChange, label }) {
  const refs = useRef([]);
  const onKey = (e, i) => {
    const dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (i + dir + tabs.length) % tabs.length;
    onChange(tabs[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button key={t.value} ref={(el) => (refs.current[i] = el)} role="tab" type="button" className="tab"
          aria-selected={value === t.value} tabIndex={value === t.value ? 0 : -1}
          onClick={() => onChange(t.value)} onKeyDown={(e) => onKey(e, i)}>
          {t.icon && <Icon name={t.icon} size={16} />}{t.label}
        </button>
      ))}
    </div>
  );
}

/** Pick one of a few options (radio group styled like Tabs). */
export function Segmented({ options, value, onChange, label, disabled }) {
  const refs = useRef([]);
  const onKey = (e, i) => {
    const dir = ["ArrowRight", "ArrowDown"].includes(e.key) ? 1 : ["ArrowLeft", "ArrowUp"].includes(e.key) ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (i + dir + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div className="tabs" role="radiogroup" aria-label={label}>
      {options.map((o, i) => (
        <button key={o.value} ref={(el) => (refs.current[i] = el)} role="radio" type="button" className="tab"
          aria-checked={value === o.value} tabIndex={value === o.value ? 0 : -1} disabled={disabled}
          onClick={() => onChange(o.value)} onKeyDown={(e) => onKey(e, i)}>
          {o.icon && <Icon name={o.icon} size={16} />}{o.label}
        </button>
      ))}
    </div>
  );
}

/* ── dialogs ────────────────────────────────────────────────────────────── */
export function useEscape(active, onEscape) {
  useEffect(() => {
    if (!active) return undefined;
    const h = (e) => e.key === "Escape" && onEscape();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [active, onEscape]);
}

export function ConfirmDialog({ open, title, body, confirmLabel, onConfirm, onClose }) {
  const ref = useRef(null);
  useEscape(open, onClose);
  useEffect(() => {
    if (open) ref.current?.querySelector("button")?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="dialog" role="alertdialog" aria-modal="true" aria-labelledby="dlg-title" aria-describedby="dlg-body">
        <h2 id="dlg-title" className="section-title" style={{ marginBottom: 8 }}>{title}</h2>
        <p id="dlg-body" className="muted" style={{ marginBottom: 24 }}>{body}</p>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

/* ── pipeline widgets ───────────────────────────────────────────────────── */
export function StageTracker({ job }) {
  return (
    <ol className="tracker panel" aria-label="Pipeline progress" style={{ listStyle: "none", margin: 0 }}>
      {STAGES.map((stage, i) => {
        const st = job.stages?.[stage.key]?.status || "pending";
        const caption = { done: "Completed", running: stage.key === "review" ? "Waiting for you" : "In progress", failed: "Failed", pending: stage.hint }[st];
        return (
          <li key={stage.key} style={{ display: "contents" }}>
            {i > 0 && <span className={`connector${job.stages?.[STAGES[i - 1].key]?.status === "done" ? " done" : ""}`} aria-hidden="true" />}
            <div className={`step ${st}`}>
              <span className="step-dot">
                {st === "done" && <Icon name="check" size={18} strokeWidth={2.6} />}
                {st === "failed" && <Icon name="x" size={18} strokeWidth={2.6} />}
                {st === "running" && <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />}
                {st === "pending" && i + 1}
              </span>
              <span className="step-name">{stage.label}</span>
              <span className="meta">{caption}<span className="sr-only">, {st}</span></span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function LogViewer({ lines }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines.length]);
  return (
    <div ref={ref} className="log" role="log" aria-live="polite" tabIndex={0} aria-label="Activity log">
      {lines.length === 0 && "No activity yet."}
      {lines.map((l, i) => (
        <div key={i} className={/ERROR|FAIL\b/.test(l) ? "err" : /WARNING|WARN\b/.test(l) ? "warn" : undefined}>{l}</div>
      ))}
    </div>
  );
}

export function useCountUp(target, duration = 800) {
  const [value, setValue] = useState(target ?? 0);
  const from = useRef(0);
  useEffect(() => {
    if (target == null) return undefined;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      from.current = target;
      return undefined;
    }
    const start = performance.now();
    const origin = from.current;
    let frame;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      setValue(origin + (target - origin) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) frame = requestAnimationFrame(tick);
      else from.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return value;
}

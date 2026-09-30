import { useEffect, useState } from "react";
import Icon from "../icons.jsx";
import { api } from "../api.js";
import { duration, host, relativeTime } from "../format.js";
import { navigate } from "../router.js";
import { Alert, Bars, Empty, Gauge, PanelHead, Progress, Sparkline, StatusBadge, useCountUp } from "../ui.jsx";

const CAPTION = ["Turn", "a", "transcript", "into", "a", "polished", "demo"];

function HeroPreview({ latestReady }) {
  const [word, setWord] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setWord((w) => (w + 1) % CAPTION.length), 950);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="preview" aria-hidden="false">
      <div className="preview-bar" aria-hidden="true"><i /><i /><i /></div>
      <span className="preview-line" style={{ top: 52, width: "38%" }} aria-hidden="true" />
      <span className="preview-line" style={{ top: 72, width: "52%", opacity: 0.7 }} aria-hidden="true" />
      <span className="preview-line" style={{ top: 92, width: "30%", opacity: 0.5 }} aria-hidden="true" />
      <span className="preview-focus" aria-hidden="true" />
      <button type="button" className="play" aria-label={latestReady ? `Watch ${latestReady.title}` : "Create your first video"}
        onClick={() => navigate(latestReady ? `/videos/${latestReady.id}` : "/new")}>
        <Icon name="play" size={26} />
      </button>
      <div className="caption" aria-hidden="true">
        {CAPTION.map((w, i) => <span key={i} className={i === word ? "on" : undefined}>{w}{i < CAPTION.length - 1 ? " " : ""}</span>)}
      </div>
      <div className="timeline" aria-hidden="true" />
    </div>
  );
}

function Metric({ icon, tone, label, value, format, children, delay }) {
  const shown = useCountUp(value);
  const tones = {
    blue: ["var(--chip-blue)", "var(--chip-blue-text)"],
    violet: ["var(--chip-violet)", "var(--chip-violet-text)"],
    turq: ["var(--chip-turq)", "var(--chip-turq-text)"],
    yellow: ["var(--chip-yellow)", "var(--chip-yellow-text)"],
  };
  const [bg, fg] = tones[tone];
  return (
    <article className="metric hoverable rise" style={{ animationDelay: `${delay}ms` }}>
      <div className="metric-top">
        <span className="metric-icon" style={{ background: bg, color: fg }}><Icon name={icon} /></span>
        <h3 className="metric-label">{label}</h3>
      </div>
      <div className="metric-foot">
        <div>
          <div className="metric-value">{value == null ? "–" : format(shown)}</div>
        </div>
        {children}
      </div>
    </article>
  );
}

const FEATURES = [
  { icon: "sparkles", title: "Creative Copilot", body: "Suggests sharper narration and flags stage directions before you record.", from: "var(--blue)", to: "var(--violet)", glow: "var(--glow-1)" },
  { icon: "palette", title: "Brand Studio", body: "Your colours, logo and intro/outro lines applied to every video automatically.", from: "var(--violet)", to: "#c04bd8", glow: "var(--glow-2)" },
  { icon: "template", title: "Smart Templates", body: "Ready-made transcript structures for tours, launches and onboarding demos.", from: "var(--turquoise)", to: "var(--blue)", glow: "var(--glow-3)" },
];

export default function DashboardPage({ options, jobs, stats, target }) {
  const latestReady = (jobs || []).find((j) => j.status === "done");
  const healthPct = stats.checksTotal ? (stats.checksPassed / stats.checksTotal) * 100 : null;

  return (
    <>
      <h1 className="sr-only">Home</h1>
      {options && !options.error && !options.azure_configured && (
        <div style={{ marginBottom: 24 }}>
          <Alert intent="warn" title="Azure OpenAI isn't configured">
            Scripts can't be drafted until the Azure OpenAI settings are added. <a href="#/settings">View settings</a>
          </Alert>
        </div>
      )}

      <section className="hero rise" aria-labelledby="hero-title">
        <div className="hero-copy">
          <span className="eyebrow"><Icon name="sparkles" size={14} />AI demo video studio</span>
          <h2 id="hero-title" className="hero-title">AI-Powered Demo Creation from <span className="accent">Any Transcript</span></h2>
          <p className="hero-body">
            Paste your app's URL and narration. Zen Studio drafts the on-screen steps, you review them, then it records your
            app with a synced voice-over, auto-zoom and captions.
          </p>
          <div className="hero-actions">
            <button type="button" className="btn btn-lg btn-white" onClick={() => navigate("/new")}><Icon name="plus" />New video</button>
            <button type="button" className="btn btn-lg btn-glass" onClick={() => navigate("/videos")}><Icon name="library" />Open library</button>
          </div>
          <div className="hero-meta">
            <span className="avatar avatar-lg" title="You"><Icon name="user" size={18} strokeWidth={2.4} /></span>
            <span>{stats.total ? `${stats.total} video${stats.total === 1 ? "" : "s"} in your workspace` : "Your workspace is ready"}</span>
          </div>
        </div>
        <HeroPreview latestReady={latestReady} />
      </section>

      <section className="metrics" aria-label="Key metrics">
        <Metric icon="video" tone="blue" label="Videos ready" value={jobs ? stats.ready : null} format={(v) => Math.round(v)} delay={40}>
          <Sparkline values={stats.perDayReady} color="var(--blue)" label="Videos ready per day, last 7 days" />
        </Metric>
        <Metric icon="clock" tone="violet" label="Minutes produced" value={jobs ? stats.minutes : null} format={(v) => v.toFixed(1)} delay={90}>
          <Sparkline values={stats.perDayMinutes} color="var(--violet)" label="Minutes produced per day, last 7 days" />
        </Metric>
        <Metric icon="activity" tone="turq" label="In progress" value={jobs ? stats.active : null} format={(v) => Math.round(v)} delay={140}>
          <span className="meta" style={{ textAlign: "right" }}>{stats.review} need{stats.review === 1 ? "s" : ""} review</span>
        </Metric>
        <Metric icon="checkCircle" tone="yellow" label="Success rate" value={stats.successRate} format={(v) => `${Math.round(v)}%`} delay={190}>
          <div style={{ width: 90 }}>
            <Progress value={(stats.successRate ?? 0) / 100} label="Success rate" />
          </div>
        </Metric>
      </section>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        <section className="panel rise" style={{ animationDelay: "220ms" }} aria-labelledby="recent-title">
          <div className="panel-head">
            <div className="grow"><h2 id="recent-title" className="section-title">Recent videos</h2></div>
            {jobs?.length > 0 && <a className="btn btn-ghost" href="#/videos">View all<Icon name="arrowRight" size={16} /></a>}
          </div>
          {!jobs && [0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 56, marginBottom: 8 }} />)}
          {jobs?.length === 0 && (
            <Empty title="No videos yet" body="Create your first demo: give Zen Studio your app's URL and the transcript you want narrated."
              action={<button type="button" className="btn btn-primary" onClick={() => navigate("/new")}><Icon name="plus" />New video</button>} />
          )}
          {jobs?.length > 0 && (
            <div className="list" role="list">
              {jobs.slice(0, 6).map((j) => (
                <a key={j.id} className="list-row" href={`#/videos/${j.id}`} role="listitem">
                  {j.status === "done"
                    ? <img className="thumb" src={api.fileUrl(j.id, "poster.jpg")} alt="" width="72" height="45" />
                    : <span className="thumb"><Icon name="video" size={18} /></span>}
                  <span style={{ minWidth: 0 }}>
                    <span className="row-title" style={{ display: "block" }}>{j.title}</span>
                    <span className="meta">{host(j.url)} · {relativeTime(j.created)}</span>
                  </span>
                  <span className="meta hide-sm">{duration(j.duration)}</span>
                  <StatusBadge status={j.status} />
                  <span className="avatar hide-sm" title="Created by you"><Icon name="user" size={14} strokeWidth={2.4} /></span>
                </a>
              ))}
            </div>
          )}
        </section>

        <div className="stack">
          <section className="panel rise" style={{ animationDelay: "260ms" }} aria-labelledby="health-title">
            <PanelHead icon="gauge" tone="turq" title="Production health" subtitle="From real sync checks" />
            <div className="gauge-wrap">
              <Gauge value={healthPct} label={healthPct == null ? "No checks yet" : `${Math.round(healthPct)}% of sync checks passed`} />
              <div>
                <div className="gauge-num">{healthPct == null ? "–" : `${Math.round(healthPct)}%`}</div>
                <span className="meta">sync checks passed</span>
              </div>
            </div>
            <div style={{ marginTop: 12 }}>
              <div className="health-row"><span className="muted">Checks passed</span><strong>{stats.checksPassed} / {stats.checksTotal}</strong></div>
              <div className="health-row"><span className="muted">Worst segment offset</span><strong>{stats.worstOnsetMs == null ? "–" : `${stats.worstOnsetMs} ms`}</strong></div>
              <div className="health-row"><span className="muted">Failed runs</span><strong>{stats.failed}</strong></div>
            </div>
          </section>
          <section className="panel rise" style={{ animationDelay: "300ms" }} aria-labelledby="activity-title">
            <PanelHead icon="activity" tone="violet" title="Activity" subtitle="Videos created, last 7 days" />
            <Bars values={stats.perDayCount} labels={stats.dayLabels} label={`Videos created per day: ${stats.perDayCount.join(", ")}`} />
            <div style={{ marginTop: 16 }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ font: "650 13px/18px var(--font)" }}>Monthly usage</span>
                <span className="meta">{stats.monthMinutes.toFixed(1)} of {target} min</span>
              </div>
              <Progress value={Math.min(1, stats.monthMinutes / target)} large label="Minutes produced this month" />
            </div>
          </section>
        </div>
      </div>

      <section aria-labelledby="features-title">
        <h2 id="features-title" className="section-title" style={{ marginBottom: 16 }}>Coming to Zen Studio</h2>
        <div className="features">
          {FEATURES.map((f, i) => (
            <article key={f.title} className="feature hoverable rise" style={{ animationDelay: `${340 + i * 50}ms`, "--feature-glow": f.glow }}>
              <div className="feature-top">
                <span className="feature-icon" style={{ background: `linear-gradient(135deg, ${f.from}, ${f.to})` }}><Icon name={f.icon} size={22} /></span>
                <h3>{f.title}</h3>
                <span className="badge b-yellow plain" style={{ marginLeft: "auto" }}>Coming soon</span>
              </div>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

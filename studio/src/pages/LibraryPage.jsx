import { useMemo, useState } from "react";
import Icon from "../icons.jsx";
import { api } from "../api.js";
import { ACTIVE, duration, host, relativeTime } from "../format.js";
import { useJobs } from "../hooks.js";
import { navigate } from "../router.js";
import { Empty, PageHead, StatusBadge, Tabs } from "../ui.jsx";

const FILTERS = {
  all: () => true,
  ready: (j) => j.status === "done",
  progress: (j) => ACTIVE.has(j.status) || j.status === "review",
  failed: (j) => j.status === "failed",
};

export default function LibraryPage({ search, setSearch }) {
  const { jobs, error } = useJobs();
  const [filter, setFilter] = useState("all");
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (jobs || []).filter(FILTERS[filter]).filter((j) => !q || `${j.title} ${j.url}`.toLowerCase().includes(q));
  }, [jobs, filter, search]);
  const count = (key) => (jobs || []).filter(FILTERS[key]).length;

  return (
    <>
      <PageHead
        title="Library"
        subtitle="Every video you've created, with its script and verification results."
        actions={<button type="button" className="btn btn-primary btn-lg" onClick={() => navigate("/new")}><Icon name="plus" />New video</button>}
      />
      <div className="row" style={{ marginBottom: 20, flexWrap: "wrap", gap: 16 }}>
        <Tabs label="Filter videos" value={filter} onChange={setFilter} tabs={[
          { value: "all", label: `All ${jobs ? count("all") : ""}` },
          { value: "ready", label: `Ready ${jobs ? count("ready") : ""}` },
          { value: "progress", label: `In progress ${jobs ? count("progress") : ""}` },
          { value: "failed", label: `Failed ${jobs ? count("failed") : ""}` },
        ]} />
        <div className="input-wrap" style={{ marginLeft: "auto", width: 320, maxWidth: "100%" }}>
          <Icon name="search" size={18} />
          <label htmlFor="lib-search" className="sr-only">Filter by name or app</label>
          <input id="lib-search" className="input" type="search" placeholder="Filter by name or app" value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>

      {error && <p className="error-text">Couldn't load videos: {error}</p>}
      {!jobs && !error && (
        <div className="cards">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 260 }} />)}</div>
      )}
      {jobs && visible.length === 0 && (
        <section className="panel">
          <Empty title={jobs.length ? "No videos match" : "Your library is empty"}
            body={jobs.length ? "Try a different filter or search." : "Videos you create appear here."}
            action={!jobs.length && <button type="button" className="btn btn-primary" onClick={() => navigate("/new")}><Icon name="plus" />New video</button>} />
        </section>
      )}
      <ul className="cards" style={{ listStyle: "none", margin: 0, padding: 0 }} aria-label="Videos">
        {visible.map((j, i) => (
          <li key={j.id} className="rise" style={{ animationDelay: `${Math.min(i, 10) * 40}ms` }}>
            <a className="vcard hoverable" href={`#/videos/${j.id}`}>
              <span className="vcard-media">
                {j.status === "done" ? <img src={api.fileUrl(j.id, "poster.jpg")} alt="" loading="lazy" /> : <Icon name="video" size={34} />}
              </span>
              <span className="vcard-body">
                <span style={{ font: "700 16px/22px var(--font)" }}>{j.title}</span>
                <span className="meta">{host(j.url)} · {relativeTime(j.created)}</span>
                <span className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                  <StatusBadge status={j.status} />
                  <span className="row meta" style={{ gap: 6 }}><Icon name="clock" size={15} />{duration(j.duration)}</span>
                </span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}

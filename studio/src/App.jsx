import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "./icons.jsx";
import { api } from "./api.js";
import { STATUS, notifications, relativeTime, jobStats } from "./format.js";
import { useJobs } from "./hooks.js";
import { navigate, useRoute } from "./router.js";
import { Progress, STATUS_DOT, ToastProvider, useEscape, useToast } from "./ui.jsx";
import CommandPalette from "./CommandPalette.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import NewVideoPage from "./pages/NewVideoPage.jsx";
import JobPage from "./pages/JobPage.jsx";
import LibraryPage from "./pages/LibraryPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

function initialTheme() {
  try {
    const saved = localStorage.getItem("zen-theme");
    if (saved) return saved;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readSeen() {
  try {
    return localStorage.getItem("zen-notifications-seen") || "";
  } catch {
    return "";
  }
}

function useOutside(ref, open, close) {
  useEffect(() => {
    if (!open) return undefined;
    const h = (e) => ref.current && !ref.current.contains(e.target) && close();
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, open, close]);
}

function Shell() {
  const route = useRoute();
  const toast = useToast();
  const { jobs } = useJobs();
  const [theme, setTheme] = useState(initialTheme);
  const [options, setOptions] = useState(null);
  const [settings, setSettings] = useState(null);
  const [search, setSearch] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [seen, setSeen] = useState(readSeen);
  const notifRef = useRef(null);
  const profileRef = useRef(null);
  const sidebarRef = useRef(null);

  useEffect(() => {
    api.options().then(setOptions).catch(() => setOptions({ error: true }));
    api.settings().then(setSettings).catch(() => setSettings({ monthly_minutes_target: 30 }));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("zen-theme", theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  const firstRoute = useRef(true);
  useEffect(() => {
    setSidebarOpen(false);
    setNotifOpen(false);
    setProfileOpen(false);
    window.scrollTo(0, 0);
    if (firstRoute.current) {
      firstRoute.current = false;
      return;
    }
    // Move focus to the new page so keyboard and screen-reader users land on its content.
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [route.path]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (sidebarOpen) sidebarRef.current?.querySelector("button, a")?.focus();
  }, [sidebarOpen]);

  const closeAll = useCallback(() => {
    setSidebarOpen(false);
    setNotifOpen(false);
    setProfileOpen(false);
  }, []);
  useEscape(sidebarOpen || notifOpen || profileOpen, closeAll);
  useOutside(notifRef, notifOpen, useCallback(() => setNotifOpen(false), []));
  useOutside(profileRef, profileOpen, useCallback(() => setProfileOpen(false), []));

  const stats = useMemo(() => jobStats(jobs), [jobs]);
  const notes = useMemo(() => notifications(jobs), [jobs]);
  const unread = notes.filter((n) => n.at > seen).length;
  const target = settings?.monthly_minutes_target || 30;
  const recent = (jobs || []).slice(0, 5);
  const online = options && !options.error;

  const toggleTheme = () => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
    toast(theme === "dark" ? "Light theme on" : "Dark theme on", "info");
  };
  const openNotifications = () => {
    setNotifOpen((o) => !o);
    setProfileOpen(false);
    const latest = notes[0]?.at || new Date().toISOString();
    setSeen(latest);
    try {
      localStorage.setItem("zen-notifications-seen", latest);
    } catch {
      /* storage unavailable */
    }
  };

  const current = (page) => (route.page === page || (page === "library" && route.page === "job") ? "page" : undefined);

  let page;
  if (route.page === "new") page = <NewVideoPage options={options} />;
  else if (route.page === "job") page = <JobPage id={route.id} />;
  else if (route.page === "library") page = <LibraryPage search={search} setSearch={setSearch} />;
  else if (route.page === "settings") page = <SettingsPage options={options} settings={settings} setSettings={setSettings} />;
  else page = <DashboardPage options={options} jobs={jobs} stats={stats} target={target} />;

  return (
    <>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
      <div className="app-bg" aria-hidden="true" />

      <header className="header on-dark">
        <button type="button" className="icon-btn menu-toggle" aria-label="Open navigation" aria-expanded={sidebarOpen}
          aria-controls="sidebar" onClick={() => setSidebarOpen(true)}>
          <Icon name="menu" />
        </button>
        <a className="brand" href="#/" aria-label="Zen Studio home">
          <span className="brand-mark" aria-hidden="true"><Icon name="play" size={16} /></span>
          <span className="brand-text">Zen Studio</span>
        </a>
        <div className="header-search">
          <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); navigate("/videos"); }}>
            <Icon name="search" size={18} />
            <label htmlFor="global-search" className="sr-only">Search videos</label>
            <input id="global-search" type="search" placeholder="Search videos, apps…" value={search} autoComplete="off"
              onChange={(e) => {
                setSearch(e.target.value);
                if (route.page !== "library") navigate("/videos");
              }} />
            <button type="button" className="kbd" onClick={() => setPaletteOpen(true)} aria-label="Open command palette (Ctrl K)">Ctrl K</button>
          </form>
        </div>
        <div className="header-actions">
          <div ref={notifRef} style={{ position: "relative" }}>
            <button type="button" className="icon-btn" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
              aria-expanded={notifOpen} aria-haspopup="true" onClick={openNotifications}>
              <Icon name="bell" />
              {unread > 0 && <span className="dot-badge" aria-hidden="true">{unread}</span>}
            </button>
            {notifOpen && (
              <div className="popover" role="dialog" aria-label="Notifications" style={{ width: 360 }}>
                <div className="row" style={{ padding: "6px 10px 10px" }}>
                  <h2 className="section-title" style={{ fontSize: 16, flex: 1 }}>Notifications</h2>
                  <span className="meta">Last 7 days</span>
                </div>
                {notes.length === 0 && <p className="muted" style={{ padding: "8px 12px 14px" }}>You're all caught up.</p>}
                {notes.slice(0, 6).map((n) => (
                  <a key={n.id} className="notif" href={`#/videos/${n.id}`}>
                    <span className="status-dot" style={{ background: STATUS_DOT[n.status], marginTop: 6 }} aria-hidden="true" />
                    <span style={{ minWidth: 0 }}>
                      <strong style={{ display: "block", font: "650 14px/20px var(--font)" }}>{n.title}</strong>
                      <span className="muted" style={{ display: "block", fontSize: 13, lineHeight: "18px" }}>{n.text}</span>
                      <span className="meta">{relativeTime(n.at)}</span>
                    </span>
                  </a>
                ))}
              </div>
            )}
          </div>
          <button type="button" className="icon-btn theme-btn" aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={toggleTheme}>
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </button>
          <div ref={profileRef} style={{ position: "relative" }}>
            <button type="button" className="icon-btn" aria-label="Profile menu" aria-expanded={profileOpen} aria-haspopup="menu"
              onClick={() => { setProfileOpen((o) => !o); setNotifOpen(false); }} style={{ width: 44 }}>
              <span className="avatar avatar-lg"><Icon name="user" size={18} strokeWidth={2.4} /></span>
            </button>
            {profileOpen && (
              <div className="popover" role="menu" aria-label="Profile">
                <div className="row" style={{ padding: "8px 10px 12px" }}>
                  <span className="avatar avatar-lg" style={{ borderColor: "var(--border)" }}><Icon name="user" size={18} strokeWidth={2.4} /></span>
                  <span>
                    <strong style={{ display: "block", font: "700 14px/20px var(--font)" }}>You</strong>
                    <span className="meta">Local Zen Studio workspace</span>
                  </span>
                </div>
                <div className="menu-sep" />
                <a role="menuitem" className="menu-item" href="#/settings"><Icon name="settings" size={18} />Settings</a>
                <button role="menuitem" type="button" className="menu-item" onClick={() => { setProfileOpen(false); setPaletteOpen(true); }}>
                  <Icon name="command" size={18} />Command palette<span className="kbd-plain" style={{ marginLeft: "auto" }}>Ctrl K</span>
                </button>
                <button role="menuitem" type="button" className="menu-item" onClick={toggleTheme}>
                  <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />{theme === "dark" ? "Light theme" : "Dark theme"}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} aria-hidden="true" />}
      <aside id="sidebar" ref={sidebarRef} className={`sidebar${sidebarOpen ? " open" : ""}`} aria-label="Primary">
        <button type="button" className="btn-new" onClick={() => navigate("/new")}>
          <Icon name="plus" strokeWidth={2.4} />New video
        </button>
        <nav className="nav" aria-label="Main">
          <a className="nav-item" href="#/" aria-current={current("home")}><Icon name="home" />Home</a>
          <a className="nav-item" href="#/videos" aria-current={current("library")}>
            <Icon name="library" />Library
            {stats.active > 0 && <span className="nav-count" aria-label={`${stats.active} in progress`}>{stats.active}</span>}
          </a>
          <a className="nav-item" href="#/settings" aria-current={current("settings")}><Icon name="settings" />Settings</a>
        </nav>
        <div className="nav-label" id="recent-label">Recent videos</div>
        <nav className="nav" aria-labelledby="recent-label">
          {recent.length === 0 && <p className="meta" style={{ padding: "0 12px" }}>Videos you create appear here.</p>}
          {recent.map((j) => (
            <a key={j.id} className="nav-item nav-recent" href={`#/videos/${j.id}`}
              aria-current={route.page === "job" && route.id === j.id ? "page" : undefined}>
              <span className="status-dot" style={{ background: STATUS_DOT[j.status] }} aria-hidden="true" />
              <span className="name">{j.title}</span>
              <span className="sr-only">, {STATUS[j.status]?.label}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="usage-mini">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ font: "650 13px/18px var(--font)" }}>Monthly usage</span>
              <span className="meta">{stats.monthMinutes.toFixed(1)} / {target} min</span>
            </div>
            <Progress value={Math.min(1, stats.monthMinutes / target)} label="Minutes produced this month" />
          </div>
          <div className="server-status">
            <span className="status-dot" style={{ background: online ? "var(--green)" : options?.error ? "var(--red)" : "var(--muted)", margin: 0 }} aria-hidden="true" />
            {online ? "Studio server connected" : options?.error ? "Server unreachable" : "Connecting…"}
          </div>
        </div>
      </aside>

      <div className="main-area">
        <main id="main" className="content" tabIndex={-1} style={{ outline: "none" }}>
          <div key={route.path} className="page">{page}</div>
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} jobs={jobs}
        actions={{ toggleTheme }} />
    </>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

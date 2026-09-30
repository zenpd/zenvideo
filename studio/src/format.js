export const STAGES = [
  { key: "script", label: "Script", hint: "Drafted from your transcript" },
  { key: "review", label: "Review", hint: "You confirm the steps" },
  { key: "narration", label: "Narration", hint: "Voice-over generated" },
  { key: "recording", label: "Recording", hint: "App is driven and captured" },
  { key: "render", label: "Render", hint: "Zoom, captions, music" },
  { key: "check", label: "Sync check", hint: "Audio/video verified" },
];

export const STATUS = {
  drafting: { label: "Drafting script", color: "informative" },
  review: { label: "Needs review", color: "warning" },
  queued: { label: "Queued", color: "informative" },
  producing: { label: "In progress", color: "brand" },
  done: { label: "Ready", color: "success" },
  failed: { label: "Failed", color: "danger" },
};

export const ACTIVE = new Set(["drafting", "queued", "producing"]);

export function relativeTime(iso) {
  if (!iso) return "";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  if (seconds < 7 * 86400) return `${Math.floor(seconds / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function duration(seconds) {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function host(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

const DIRECTION = /^\s*(click|tap|press|enter|type|send|scroll|select|open|check|hover|navigate|go to)\b/i;

export function transcriptStats(text) {
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const lines = text.split(/\n|(?<=[.,])\s+(?=click|scroll|enter|send)/i);
  const directions = lines.filter((l) => DIRECTION.test(l)).length;
  const segments = text.includes("---") ? text.split(/^\s*---\s*$/m).filter((s) => s.trim()).length : 0;
  return { words, directions, segments, minutes: words / 150 };
}
const dayKey = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

/** Everything the dashboard shows, computed from real jobs only. */
export function jobStats(jobs) {
  const list = jobs || [];
  const now = new Date();
  const days = [...Array(7)].map((_, i) => {
    const d = new Date(now);
    d.setDate(now.getDate() - (6 - i));
    return d;
  });
  const perDay = days.map((d) => list.filter((j) => dayKey(new Date(j.created)) === dayKey(d)));
  const done = list.filter((j) => j.status === "done");
  const finished = list.filter((j) => ["done", "failed"].includes(j.status));
  const thisMonth = done.filter((j) => {
    const c = new Date(j.created);
    return c.getFullYear() === now.getFullYear() && c.getMonth() === now.getMonth();
  });
  const checks = list.filter((j) => j.check?.results);
  const onsetErrors = checks.flatMap((j) =>
    j.check.results.filter((r) => /start$/.test(r.check)).map((r) => Math.abs(parseFloat((r.detail.match(/\(([+-]?\d+) ms\)/) || [])[1] || 0))));
  return {
    total: list.length,
    ready: done.length,
    active: list.filter((j) => ACTIVE.has(j.status) || j.status === "review").length,
    review: list.filter((j) => j.status === "review").length,
    failed: list.filter((j) => j.status === "failed").length,
    minutes: done.reduce((s, j) => s + (j.duration || 0), 0) / 60,
    monthMinutes: thisMonth.reduce((s, j) => s + (j.duration || 0), 0) / 60,
    successRate: finished.length ? (done.length / finished.length) * 100 : null,
    checksPassed: checks.filter((j) => j.check.passed).length,
    checksTotal: checks.length,
    worstOnsetMs: onsetErrors.length ? Math.max(...onsetErrors) : null,
    dayLabels: days.map((d) => d.toLocaleDateString(undefined, { weekday: "narrow" })),
    perDayCount: perDay.map((js) => js.length),
    perDayMinutes: perDay.map((js) => js.reduce((s, j) => s + (j.duration || 0), 0) / 60),
    perDayReady: perDay.map((js) => js.filter((j) => j.status === "done").length),
  };
}

export function notifications(jobs) {
  const week = Date.now() - 7 * 86400 * 1000;
  return (jobs || [])
    .filter((j) => j.status === "review" || (["done", "failed"].includes(j.status) && new Date(j.updated || j.created) > week))
    .map((j) => ({
      id: j.id,
      at: j.updated || j.created,
      title: j.title,
      text: { review: "Script drafted — waiting for your review", done: "Video is ready to watch", failed: j.error || "Something went wrong" }[j.status],
      status: j.status,
    }))
    .sort((a, b) => (a.at < b.at ? 1 : -1));
}

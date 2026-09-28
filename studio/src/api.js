async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.json();
}

const base = "/api/studio";
const post = (path, body) => request(base + path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  options: () => request(`${base}/options`),
  settings: () => request(`${base}/settings`),
  saveSettings: (body) => request(`${base}/settings`, { method: "PUT", body: JSON.stringify(body) }),
  checkUrl: (url) => post("/check-url", { url }),
  jobs: () => request(`${base}/jobs`),
  job: (id) => request(`${base}/jobs/${id}`),
  createJob: (body) => post("/jobs", body),
  saveScript: (id, yaml) => request(`${base}/jobs/${id}/script`, { method: "PUT", body: JSON.stringify({ yaml }) }),
  approve: (id) => post(`/jobs/${id}/approve`),
  retry: (id) => post(`/jobs/${id}/retry`),
  redraft: (id) => post(`/jobs/${id}/redraft`),
  remove: (id) => request(`${base}/jobs/${id}`, { method: "DELETE" }),
  fileUrl: (id, name) => `${base}/jobs/${id}/files/${name}`,
  eventsUrl: (id) => `${base}/jobs/${id}/events`,
};

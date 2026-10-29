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
const ppt = "/api/ppt";   // the PPT skill
const pptPost = (path, body) => request(ppt + path, { method: "POST", body: JSON.stringify(body || {}) });

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
  narration: (id) => request(`${base}/jobs/${id}/narration`),
  remove: (id) => request(`${base}/jobs/${id}`, { method: "DELETE" }),
  // the PPT skill (/api/ppt): decks from a narration, transcript or notes
  deckTemplates: () => request(`${ppt}/templates`),
  briefOptions: () => request(`${ppt}/brief-options`),
  deckSampleUrl: (template) => `${ppt}/templates/${template}/sample`,
  decks: (video) => request(`${ppt}/decks${video ? `?video=${encodeURIComponent(video)}` : ""}`),
  deck: (id) => request(`${ppt}/decks/${id}`),
  createDeck: (body) => pptPost("/decks", body),
  buildDeck: (id, body) => pptPost(`/decks/${id}/build`, body),
  reviseDeck: (id, body) => pptPost(`/decks/${id}/revise`, body),
  approveDeck: (id) => pptPost(`/decks/${id}/approve`, {}),
  deckPreviewUrl: (id, template, file) => `${ppt}/decks/${id}/preview/${template}/${file}`,
  removeDeck: (id) => request(`${ppt}/decks/${id}`, { method: "DELETE" }),
  deckDownloadUrl: (id, name) => `${ppt}/decks/${id}/files/${name}`,
  deckShotUrl: (id, file) => `${ppt}/decks/${id}/pages/${file}`,
  fileUrl: (id, name) => `${base}/jobs/${id}/files/${name}`,
  eventsUrl: (id) => `${base}/jobs/${id}/events`,
};

/** The file a deck design is saved as (the original Zen Studio design keeps the old name). */
export const deckFile = (template) => (template === "zen" ? "deck.pptx" : `deck-${template}.pptx`);

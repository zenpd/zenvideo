import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { ACTIVE } from "./format.js";

export function useJobs() {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(() => {
    api.jobs().then((j) => {
      setJobs(j);
      setError(null);
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const busy = jobs?.some((j) => ACTIVE.has(j.status));
  useEffect(() => {
    if (!busy) return undefined;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [busy, refresh]);

  return { jobs, error, refresh };
}

export function useJob(id) {
  const [job, setJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const lastPhase = useRef("");

  const refresh = useCallback(() => {
    api.job(id).then((j) => {
      setJob(j);
      setError(null);
    }).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    setJob(null);
    setLogs([]);
    lastPhase.current = "";
    refresh();
    const source = new EventSource(api.eventsUrl(id));
    source.addEventListener("log", (e) => setLogs((l) => [...l, e.data]));
    source.addEventListener("job", (e) => {
      const live = JSON.parse(e.data);
      if (!live) return;
      const phase = `${live.status}:${live.stage}:${JSON.stringify(live.stages)}`;
      if (phase !== lastPhase.current) {
        lastPhase.current = phase;
        refresh();
      } else {
        setJob((j) => (j ? { ...j, progress: live.progress } : j));
      }
    });
    return () => source.close();
  }, [id, refresh]);

  return { job, logs, error, refresh, setJob };
}

import { useEffect, useState } from "react";

const read = () => (window.location.hash.replace(/^#/, "") || "/").split("?")[0];

export function navigate(path) {
  window.location.hash = path;
}

export function useRoute() {
  const [path, setPath] = useState(read);
  useEffect(() => {
    const onChange = () => setPath(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const job = path.match(/^\/videos\/([\w-]+)$/);
  if (job) return { page: "job", id: job[1], path };
  const page = { "/": "home", "/new": "new", "/videos": "library", "/settings": "settings",
    "/screen-recorder": "screenRecorder" }[path] || "home";
  return { page, path };
}

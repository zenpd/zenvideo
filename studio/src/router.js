import { useEffect, useState } from "react";

const read = () => (window.location.hash.replace(/^#/, "") || "/").split("?")[0];

/** The ?query of the current hash route, e.g. #/decks/new?video=123 -> { video: "123" }. */
export const query = () => Object.fromEntries(new URLSearchParams(window.location.hash.split("?")[1] || ""));

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
  const deck = path.match(/^\/videos\/([\w-]+)\/deck$/);
  if (deck) return { page: "deck", id: deck[1], path };
  const linkDeck = path.match(/^\/decks\/([\w-]+)$/);
  if (linkDeck && linkDeck[1] !== "new") return { page: "linkdeck", id: linkDeck[1], path };
  const explainer = path.match(/^\/explainers\/([\w-]+)$/);
  if (explainer && explainer[1] !== "new") return { page: "explainer", id: explainer[1], path };
  const page = { "/": "home", "/new": "new", "/videos": "library", "/settings": "settings", "/decks": "decks",
    "/decks/new": "newdeck", "/explainers": "explainers", "/explainers/new": "newexplainer" }[path] || "home";
  return { page, path };
}

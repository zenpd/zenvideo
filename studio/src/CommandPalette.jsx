import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./icons.jsx";
import { STATUS } from "./format.js";
import { navigate } from "./router.js";
import { useEscape } from "./ui.jsx";

export default function CommandPalette({ open, onClose, jobs, actions }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const restoreRef = useRef(null);

  useEscape(open, onClose);
  useEffect(() => {
    if (open) {
      restoreRef.current = document.activeElement;
      setQuery("");
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    } else {
      restoreRef.current?.focus?.();
    }
  }, [open]);

  const items = useMemo(() => {
    const go = (path) => () => navigate(path);
    const base = [
      { group: "Actions", icon: "plus", label: "Create a new video", run: go("/new"), keywords: "new create add" },
      { group: "Actions", icon: "moon", label: "Toggle light / dark theme", run: actions.toggleTheme, keywords: "theme dark light" },
      { group: "Go to", icon: "home", label: "Home", run: go("/"), keywords: "dashboard" },
      { group: "Go to", icon: "library", label: "Library", run: go("/videos"), keywords: "videos all" },
      { group: "Go to", icon: "settings", label: "Settings", run: go("/settings"), keywords: "config azure whisper usage" },
    ];
    const videos = (jobs || []).map((j) => ({
      group: "Videos", icon: "video", label: j.title, hint: STATUS[j.status]?.label, run: go(`/videos/${j.id}`), keywords: j.url,
    }));
    const q = query.trim().toLowerCase();
    return [...base, ...videos].filter((i) => !q || `${i.label} ${i.keywords || ""}`.toLowerCase().includes(q));
  }, [jobs, query, actions]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const run = (item) => {
    onClose();
    item.run();
  };
  const onKey = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(items.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter" && items[active]) {
      e.preventDefault();
      run(items[active]);
    } else if (e.key === "Tab") {
      e.preventDefault();
    }
  };

  let lastGroup = null;
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="palette-input">
          <Icon name="search" />
          <input ref={inputRef} type="text" role="combobox" aria-expanded="true" aria-controls="palette-list"
            aria-activedescendant={items[active] ? `pal-${active}` : undefined} aria-autocomplete="list"
            placeholder="Type a command or search videos…" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} />
          <span className="kbd-plain">Esc</span>
        </div>
        <ul id="palette-list" ref={listRef} className="palette-list" role="listbox" aria-label="Results">
          {items.length === 0 && <li className="muted" style={{ padding: 16 }}>No matches for “{query}”.</li>}
          {items.map((item, i) => {
            const header = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <li key={`${item.group}-${item.label}-${i}`} role="presentation">
                {header && <div className="palette-group" role="presentation">{header}</div>}
                <div id={`pal-${i}`} data-index={i} role="option" aria-selected={i === active} className="palette-item"
                  onMouseMove={() => setActive(i)} onClick={() => run(item)}>
                  <Icon name={item.icon} size={18} />
                  <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.label}</span>
                  {item.hint && <span className="meta">{item.hint}</span>}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="palette-foot" aria-hidden="true">
          <span><kbd>↑</kbd> <kbd>↓</kbd> to move</span>
          <span><kbd>Enter</kbd> to open</span>
          <span><kbd>Esc</kbd> to close</span>
        </div>
      </div>
    </div>
  );
}

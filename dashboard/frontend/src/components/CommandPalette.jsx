import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { Icon, PlaylistChip, StatusChip } from "../ui.jsx";
import { NAV } from "./Sidebar.jsx";

const PAGES = NAV.flatMap((s) => s.items);

/* Ctrl+K: jump to a screen, or find a topic by title or key. */
export default function CommandPalette({ open, onClose, onGo, onTopic }) {
  const [q, setQ] = useState("");
  const [topics, setTopics] = useState([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setActive(0);
    inputRef.current?.focus();
    api("/api/topics").then((r) => setTopics(r.topics || [])).catch(() => {});
  }, [open]);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const pages = PAGES
      .filter((p) => !needle || p.label.toLowerCase().includes(needle))
      .map((p) => ({ kind: "page", id: "p:" + p.id, page: p }));
    if (!needle) return pages;
    const hits = topics
      .filter((t) => t.title.toLowerCase().includes(needle) || t.key.includes(needle))
      .slice(0, 12)
      .map((t) => ({ kind: "topic", id: "t:" + t.key, topic: t }));
    return [...pages, ...hits];
  }, [q, topics]);

  if (!open) return null;

  const pick = (r) => {
    if (!r) return;
    if (r.kind === "page") onGo(r.page.id);
    else onTopic(r.topic);
    onClose();
  };

  const onKey = (e) => {
    if (e.key === "Escape") onClose();
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") pick(results[active]);
  };

  return (
    <div className="modal-back" style={{ placeItems: "start center" }}
         onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal palette" role="dialog" aria-modal="true" aria-label="Search">
        <label className="search">
          <Icon name="search" />
          <input
            ref={inputRef} type="search" value={q} placeholder="Search topics, videos and screens"
            aria-label="Search topics, videos and screens"
            onChange={(e) => { setQ(e.target.value); setActive(0); }} onKeyDown={onKey}
          />
          <span className="kbd">Esc</span>
        </label>
        <ul>
          {results.map((r, i) => (
            <li key={r.id}>
              <button type="button" className={i === active ? "on" : ""}
                      onMouseEnter={() => setActive(i)} onClick={() => pick(r)}>
                {r.kind === "page" ? (
                  <><Icon name={r.page.icon} className="muted" /><span style={{ flex: 1 }}>{r.page.label}</span>
                    <span className="faint" style={{ fontSize: 12 }}>Screen</span></>
                ) : (
                  <>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      {r.topic.title}
                      <span className="num faint" style={{ fontSize: 12, marginLeft: 8 }}>{r.topic.key}</span>
                    </span>
                    <PlaylistChip series={r.topic.series} name={r.topic.playlist} />
                    <StatusChip state={r.topic.phase} />
                  </>
                )}
              </button>
            </li>
          ))}
          {results.length === 0 && <li className="muted" style={{ padding: 16 }}>Nothing matches "{q}".</li>}
        </ul>
      </div>
    </div>
  );
}

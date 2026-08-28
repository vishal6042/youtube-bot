import { useState } from "react";
import EpisodeRow from "./EpisodeRow.jsx";
import PlaylistCover from "./PlaylistCover.jsx";

// Stat cards double as filters — clicking one narrows the list below.
const CARDS = [
  { id: "all", icon: "◈", label: "TOTAL VIDEOS", cls: "c-all" },
  { id: "queue", icon: "🎯", label: "IN QUEUE", cls: "c-queue" },
  { id: "ready", icon: "⏳", label: "READY", cls: "c-ready" },
  { id: "uploaded", icon: "✅", label: "UPLOADED", cls: "c-uploaded" },
  { id: "missing", icon: "⬜", label: "PLANNED", cls: "c-planned" },
];

export default function PlaylistDetail({ s, nextUp, workingKey, onBack, onPlaylistCreated, ...handlers }) {
  const [filter, setFilter] = useState("all");
  const rankOf = new Map(nextUp.map((p, i) => [p.key, i + 1]));

  const countOf = (id) =>
    id === "all" ? s.items.length
      : id === "queue" ? s.items.filter((it) => rankOf.has(it.key)).length
      : s.items.filter((it) => it.state === id).length;

  const items = s.items.filter((it) =>
    filter === "all" ? true
      : filter === "queue" ? rankOf.has(it.key)
      : it.state === filter
  );
  const sorted = filter === "queue"
    ? [...items].sort((a, b) => rankOf.get(a.key) - rankOf.get(b.key))
    : items;

  const pct = s.total ? Math.round((s.uploaded / s.total) * 100) : 0;
  const active = CARDS.find((c) => c.id === filter);

  return (
    <>
      {/* ---- header: cover + description ---- */}
      <section className="panel pd-head-panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">{s.playlist}</div>
            <div className="pl-series">{s.series}</div>
          </div>
        </div>
        <div className="pd-head">
          <div className="pd-cover"><PlaylistCover series={s.series} /></div>
          <div className="pd-info">
            <div className="pd-meta">
              <span>{s.uploaded} of {s.total} uploaded</span>
              {!s.playlist_exists && (
                <span className="pd-warn">
                  ⚠ playlist not created on YouTube yet
                  <button
                    className="btn btn-mini btn-primary pd-created"
                    onClick={() => onPlaylistCreated(s.series, s.playlist)}
                  >
                    ✓ I'VE CREATED IT
                  </button>
                </span>
              )}
              {s.playlist_exists && s.created_manually && (
                <button
                  className="btn btn-mini pd-undo"
                  title="Mark this playlist as not created after all"
                  onClick={() => onPlaylistCreated(s.series, s.playlist, false)}
                >
                  ↩ undo "created"
                </button>
              )}
            </div>
            <div className="pl-bar pd-bar"><div style={{ width: pct + "%" }} /></div>
            {s.description ? (
              <p className="pd-desc">{s.description}</p>
            ) : (
              <p className="pd-desc muted">
                No description yet — add one in Settings so it's ready to paste on YouTube.
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ---- stat cards, acting as filters ---- */}
      <div className="pd-cards">
        {CARDS.map((c) => {
          const n = countOf(c.id);
          return (
            <button
              key={c.id}
              className={`pd-card ${c.cls}` + (filter === c.id ? " active" : "")}
              disabled={n === 0 && c.id !== "all"}
              onClick={() => setFilter(c.id)}
            >
              <span className="pd-card-num">{n}</span>
              <span className="pd-card-label">{c.icon} {c.label}</span>
            </button>
          );
        })}
      </div>

      {/* ---- the videos ---- */}
      <section className="panel">
        <div className="panel-title">
          {active ? `${active.icon} ${active.label}` : "VIDEOS"} · {sorted.length} VIDEO
          {sorted.length === 1 ? "" : "S"}
          {filter !== "all" && (
            <button className="btn btn-mini pd-clear" onClick={() => setFilter("all")}>
              ✕ CLEAR FILTER
            </button>
          )}
        </div>
        <div className="pl-items">
          {!sorted.length && <div className="empty">Nothing matches this filter.</div>}
          {sorted.map((it) => (
            <EpisodeRow
              key={it.key}
              it={it}
              queueRank={rankOf.get(it.key)}
              working={workingKey === it.key}
              {...handlers}
            />
          ))}
        </div>
      </section>
    </>
  );
}

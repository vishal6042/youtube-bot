import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import PlaylistCover from "./PlaylistCover.jsx";
import YouTubeIcon from "./YouTubeIcon.jsx";

function fmtDur(secs) {
  if (secs == null) return "—";
  return secs >= 60 ? `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s` : `${Math.round(secs)}s`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(11, 16);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/* Heading for a day: "Today", "Yesterday", else the full date. */
function fmtDay(dayKey) {
  const d = new Date(dayKey + "T00:00:00");
  if (Number.isNaN(d.getTime())) return dayKey;
  const today = new Date();
  const midnight = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((midnight(today) - midnight(d)) / 86400000);
  const full = d.toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  if (diff === 0) return `Today · ${full}`;
  if (diff === 1) return `Yesterday · ${full}`;
  return full;
}

/* Rows arrive newest-first, so consecutive runs share a day. */
function groupByDay(rows) {
  const out = [];
  for (const r of rows) {
    const key = (r.uploaded_at || "").slice(0, 10) || "unknown";
    const last = out[out.length - 1];
    if (last && last.day === key) last.rows.push(r);
    else out.push({ day: key, rows: [r] });
  }
  return out;
}

function LinkCell({ row, onSave, toast }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(row.url || "");

  if (row.url && !editing) {
    return (
      <span className="uh-link">
        <a
          href={row.url}
          target="_blank"
          rel="noopener noreferrer"
          title="Watch on YouTube"
          aria-label="Watch on YouTube"
          onClick={(e) => e.stopPropagation()}
        >
          <YouTubeIcon />
        </a>
        <button className="btn btn-mini uh-edit-btn" title="Edit link"
                onClick={(e) => { e.stopPropagation(); setVal(row.url); setEditing(true); }}>✎</button>
      </span>
    );
  }

  if (!editing) {
    return (
      <button className="btn btn-mini uh-addlink"
              onClick={(e) => { e.stopPropagation(); setEditing(true); }}>
        + ADD LINK
      </button>
    );
  }

  const save = async () => {
    await onSave(row.key, val.trim());
    setEditing(false);
  };

  return (
    <span className="uh-edit" onClick={(e) => e.stopPropagation()}>
      <input
        type="url" autoFocus placeholder="https://youtu.be/…"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") setEditing(false);
        }}
      />
      <button className="btn btn-mini btn-primary" onClick={save}>SAVE</button>
      <button className="btn btn-mini" onClick={() => setEditing(false)}>✕</button>
    </span>
  );
}

export default function UploadHistory({ onBack, onOpen, onUnmark, onWatch, confirm, toast }) {
  const [data, setData] = useState(null);
  const [series, setSeries] = useState("");
  const [q, setQ] = useState("");
  const [onlyNoLink, setOnlyNoLink] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api("/api/uploads"));
    } catch (e) {
      toast(e.message, true);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const saveLink = async (key, url) => {
    try {
      await api("/api/upload-link", { key, url });
      toast(url ? "✅ Link saved" : "↩ Link removed");
      load();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const playlists = useMemo(() => {
    const m = new Map();
    for (const r of data?.uploads || []) if (!m.has(r.series)) m.set(r.series, r.playlist);
    return [...m.entries()];
  }, [data]);

  if (!data) {
    return (
      <section className="panel detail">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div className="pl-name">UPLOAD HISTORY</div>
        </div>
        <div className="empty">Loading…</div>
      </section>
    );
  }

  const rows = data.uploads.filter((r) =>
    (!series || r.series === series) &&
    (!onlyNoLink || !r.url) &&
    (!q || (r.title + " " + r.key).toLowerCase().includes(q.toLowerCase()))
  );

  return (
    <>
      <section className="panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">UPLOAD HISTORY</div>
            <div className="pl-series">
              everything you've posted · newest first · click a row to open it on YouTube
            </div>
          </div>
          <div className="uq-stats">
            <div className="uq-stat"><b>{data.total}</b><span>Uploaded</span></div>
          </div>
        </div>

        <div className="uh-filters">
          <input
            className="uh-search" type="text" placeholder="Search title or key…"
            value={q} onChange={(e) => setQ(e.target.value)}
          />
          <select value={series} onChange={(e) => setSeries(e.target.value)}>
            <option value="">All playlists</option>
            {playlists.map(([s, name]) => <option key={s} value={s}>{name}</option>)}
          </select>
          {/* Only worth showing when something actually lacks a link. */}
          {data.total > data.with_link && (
            <label className="lc-check">
              <input type="checkbox" checked={onlyNoLink}
                     onChange={(e) => setOnlyNoLink(e.target.checked)} />
              <span>Missing link only ({data.total - data.with_link})</span>
            </label>
          )}
          <span className="uh-count">{rows.length} shown</span>
        </div>
      </section>

      <section className="panel uq-panel">
        <div className="uq-rows">
          {!rows.length && <div className="empty">No uploads match these filters.</div>}
          {groupByDay(rows).map((g) => (
            <div className="uh-day" key={g.day}>
              <div className="uh-day-head">
                <span className="uh-day-label">{fmtDay(g.day)}</span>
                <span className="uh-day-count">
                  {g.rows.length} video{g.rows.length === 1 ? "" : "s"}
                </span>
              </div>
              {g.rows.map((r) => (
            <div
              key={r.key}
              className={"uh-row" + (r.url ? " clickable" : "")}
              onClick={() => r.url && window.open(r.url, "_blank", "noopener")}
              title={r.url ? "Open on YouTube" : undefined}
            >
              {r.has_thumb ? (
                <img className="uq-thumb" src={`/api/thumb/${r.key}`} alt="" loading="lazy" />
              ) : (
                <span className="uq-thumb uq-thumb-art"><PlaylistCover series={r.series} /></span>
              )}

              <span className="uq-main">
                <span className="uq-name">{r.title}</span>
                <span className="uq-why">
                  {r.playlist} · ep {r.episode}
                  {r.subtitle ? ` · ${r.subtitle}` : ""}
                </span>
                <span className="uq-next">
                  {r.source ? `Source: ${r.source}` : ""}
                  {r.rendered_on ? ` · rendered ${r.rendered_on}` : ""}
                </span>
              </span>

              <span className="uh-when">
                <b>{fmtTime(r.uploaded_at)}</b>
                <span>uploaded</span>
              </span>

              <span className="uh-dur">{fmtDur(r.duration_sec)}</span>

              <LinkCell row={r} onSave={saveLink} toast={toast} />

              <span className="uh-row-actions">
                <button className="btn btn-mini" title="Watch here"
                        onClick={(e) => { e.stopPropagation(); onWatch(r); }}>▶</button>
                {r.exported && (
                  <button className="btn btn-mini" title="Open export folder"
                          onClick={(e) => { e.stopPropagation(); onOpen(r.exported); }}>📂</button>
                )}
                {/* Correction path: this is where a wrongly-marked upload gets undone. */}
                <button
                  className="btn btn-mini uh-unmark"
                  title="Not actually uploaded — move back to the queue"
                  onClick={async (e) => {
                    e.stopPropagation();
                    const ok = await confirm({
                      title: "Mark as not uploaded?",
                      message: `"${r.title}" goes back into the upload queue.`,
                      detail: "Use this when a video was marked by mistake — the YouTube video, if any, is untouched.",
                      confirmLabel: "↩ MOVE BACK TO QUEUE", tone: "danger",
                    });
                    if (!ok) return;
                    await onUnmark(r.key, r.title);
                    load();
                  }}
                >↩ NOT UPLOADED</button>
              </span>
            </div>
              ))}
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

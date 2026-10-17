import { useCallback, useEffect, useState } from "react";
import { api } from "../../api.js";
import { Bar, Btn, Chip, Icon, Pager, PlaylistChip, Seg, fmtDuration, usePaged } from "../../ui.jsx";

/* Shorts cut from long-form videos, on the Shorts render page. They render
   through the same queue as the daily Shorts (same live card, steps, history
   and retry); this card only says which ones need rendering and starts them.

   It grows with every video, so each video folds to one summary line and
   opens by default only when it has Shorts to render; an open video lists all
   its Shorts, and the videos themselves are paged. */

const OPEN_KEY = "dim.fromVideos.open";

function stateOf(s, queued) {
  if (queued) return ["In the render queue", "info"];
  if (s.uploaded) return ["Uploaded", "go"];
  if (!s.rendered) return ["Not rendered", "bad"];
  if (!s.current) return ["Changed, render again", "warn"];
  return ["Rendered", "go"];
}

const needsRender = (s) => !s.uploaded && (!s.rendered || !s.current);

function loadOpen() {
  try { return JSON.parse(window.localStorage.getItem(OPEN_KEY) || "{}"); } catch { return {}; }
}

function VideoBlock({ ep, queuedKeys, open, onToggle, onRender }) {
  const shorts = ep.shorts || [];
  const todo = shorts.filter((s) => needsRender(s) && !queuedKeys.has(s.key));
  const rendered = shorts.filter((s) => s.rendered && s.current).length;
  const uploaded = shorts.filter((s) => s.uploaded).length;
  const queued = shorts.filter((s) => queuedKeys.has(s.key)).length;
  const bodyId = `fv-${ep.key}`;

  return (
    <div className="fv-block" data-open={open || undefined}>
      <div className="fv-head">
        <Btn kind="ghost" size="sm" icon={open ? "down" : "right"}
             iconOnly={`${open ? "Hide" : "Show"} the Shorts from ${ep.title}`}
             aria-expanded={open} aria-controls={bodyId} onClick={onToggle} />
        <button type="button" className="fv-title" onClick={onToggle} aria-expanded={open} aria-controls={bodyId}>
          {ep.title}
        </button>
        <PlaylistChip series={ep.series} name={ep.playlist} />
        <div className="fv-progress" title={`${rendered} of ${shorts.length} rendered`}>
          <Bar pct={(rendered / Math.max(1, shorts.length)) * 100} height={5} />
          <span className="num muted">
            {rendered} of {shorts.length} rendered
            {uploaded ? ` · ${uploaded} uploaded` : ""}{queued ? ` · ${queued} queued` : ""}
          </span>
        </div>
        <Btn size="sm" kind={todo.length ? "primary" : ""} icon="play" disabled={!todo.length}
             onClick={() => onRender(todo.map((s) => s.key), `${todo.length} Shorts from ${ep.title}`)}>
          {todo.length ? `Render ${todo.length}` : "Up to date"}
        </Btn>
      </div>

      {open && (
        <div id={bodyId}>
          <ol className="plain-list fv-rows">
            {shorts.map((s) => {
              const isQueued = queuedKeys.has(s.key);
              const [label, tone] = stateOf(s, isQueued);
              return (
                <li key={s.key} className="fv-row">
                  <span className="num faint">{s.n}</span>
                  <span className="fv-name">{s.title}</span>
                  <span className="num muted">{s.duration_sec ? fmtDuration(s.duration_sec) : ""}</span>
                  <Chip tone={tone}>{label}</Chip>
                  <Btn size="sm" kind="ghost" disabled={isQueued || s.uploaded}
                       onClick={() => onRender([s.key], s.title)}>{s.rendered ? "Render again" : "Render"}</Btn>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}

export default function FromVideos({ job, queue, onRender }) {
  const [episodes, setEpisodes] = useState(null);
  const [open, setOpenRaw] = useState(loadOpen);
  const [filter, setFilter] = useState(null);   // null until we know whether anything needs work
  const load = useCallback(async () => {
    try { setEpisodes((await api("/api/longform")).episodes); } catch { /* card stays hidden */ }
  }, []);
  // Refresh whenever the queue moves, so a Short flips to Rendered when its job ends.
  const queueSig = `${job?.id || ""}:${(queue || []).map((j) => j.id).join(",")}`;
  useEffect(() => { load(); }, [load, queueSig]);

  const withShorts = (episodes || []).filter((e) => e.has_video && (e.shorts || []).length);
  const needWork = withShorts.filter((e) => (e.shorts || []).some(needsRender));
  const view = filter || (needWork.length ? "todo" : "all");
  const shown = view === "todo" ? needWork : withShorts;
  const page = usePaged(shown, 5, view);
  if (!withShorts.length) return null;
  const queuedKeys = new Set([...(job ? job.keys || [] : []), ...(queue || []).flatMap((j) => j.keys || [])]);

  // Remembered per video in this browser; a video with nothing to render starts folded.
  const isOpen = (ep) => open[ep.key] ?? (ep.shorts || []).some(needsRender);
  const toggle = (ep) => {
    const next = { ...open, [ep.key]: !isOpen(ep) };
    setOpenRaw(next);
    try { window.localStorage.setItem(OPEN_KEY, JSON.stringify(next)); } catch { /* this visit only */ }
  };

  return (
    <section className="card stack" style={{ gap: 14 }} aria-label="Shorts from your videos">
      <div className="card-head" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2>Shorts from your videos</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          Each chapter upright, with captions and a line pointing to the full video
        </span>
        <span className="spacer" />
        <Seg value={view} onChange={setFilter} label="Which videos" options={[
          { value: "todo", label: "Needs rendering", count: needWork.length },
          { value: "all", label: "All videos", count: withShorts.length },
        ]} />
      </div>
      {!shown.length && (
        <p className="muted" style={{ margin: 0, fontSize: 13.5 }}>
          Every Short from your videos is rendered. <button type="button" className="link" onClick={() => setFilter("all")}>Show all videos</button>
        </p>
      )}
      {page.slice.map((ep) => (
        <VideoBlock key={ep.key} ep={ep} queuedKeys={queuedKeys} open={isOpen(ep)}
                    onToggle={() => toggle(ep)} onRender={onRender} />
      ))}
      {shown.length > 5 && <Pager p={page} noun="videos" sizes={[5, 10, 25]} />}
    </section>
  );
}

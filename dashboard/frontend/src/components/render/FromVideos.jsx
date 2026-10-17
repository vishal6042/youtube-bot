import { useCallback, useEffect, useState } from "react";
import { api } from "../../api.js";
import { Btn, Chip, PlaylistChip, fmtDuration } from "../../ui.jsx";

/* Shorts cut from long-form videos, on the Shorts render page. They render
   through the same queue as the daily Shorts (same live card, steps, history
   and retry); this card only says which ones need rendering and starts them. */

function stateOf(s, queued) {
  if (queued) return ["In the render queue", "info"];
  if (s.uploaded) return ["Uploaded", "go"];
  if (!s.rendered) return ["Not rendered", "bad"];
  if (!s.current) return ["Changed, render again", "warn"];
  return ["Rendered", "go"];
}

function VideoBlock({ ep, queuedKeys, onRender }) {
  const shorts = ep.shorts || [];
  const todo = shorts.filter((s) => !s.uploaded && (!s.rendered || !s.current) && !queuedKeys.has(s.key));
  const rendered = shorts.filter((s) => s.rendered && s.current).length;
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="rowf" style={{ gap: 10 }}>
        <b style={{ fontSize: 15 }}>{ep.title}</b>
        <PlaylistChip series={ep.series} name={ep.playlist} />
        <span className="muted num" style={{ fontSize: 12.5 }}>{rendered} of {shorts.length} rendered</span>
        <span className="spacer" />
        <Btn size="sm" kind={todo.length ? "primary" : ""} icon="play" disabled={!todo.length}
             onClick={() => onRender(todo.map((s) => s.key), `${todo.length} Shorts from ${ep.title}`)}>
          {todo.length ? `Render ${todo.length} that need it` : "All up to date"}
        </Btn>
      </div>
      <ol className="plain-list stack" style={{ gap: 2, margin: 0, padding: 0 }}>
        {shorts.map((s) => {
          const queued = queuedKeys.has(s.key);
          const [label, tone] = stateOf(s, queued);
          return (
            <li key={s.key} className="rowf" style={{ flexWrap: "nowrap", gap: 12, padding: "6px 4px" }}>
              <span className="num faint" style={{ width: 20, fontSize: 12 }}>{s.n}</span>
              <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.title}
              </span>
              {s.duration_sec ? <span className="num muted" style={{ fontSize: 12.5 }}>{fmtDuration(s.duration_sec)}</span> : null}
              <Chip tone={tone}>{label}</Chip>
              <Btn size="sm" kind="ghost" disabled={queued || s.uploaded}
                   onClick={() => onRender([s.key], s.title)}>{s.rendered ? "Render again" : "Render"}</Btn>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function FromVideos({ job, queue, onRender }) {
  const [episodes, setEpisodes] = useState(null);
  const load = useCallback(async () => {
    try { setEpisodes((await api("/api/longform")).episodes); } catch { /* card stays hidden */ }
  }, []);
  // Refresh whenever the queue moves, so a Short flips to Rendered when its job ends.
  const queueSig = `${job?.id || ""}:${(queue || []).map((j) => j.id).join(",")}`;
  useEffect(() => { load(); }, [load, queueSig]);

  const withShorts = (episodes || []).filter((e) => e.has_video && (e.shorts || []).length);
  if (!withShorts.length) return null;
  const queuedKeys = new Set([...(job ? job.keys || [] : []), ...(queue || []).flatMap((j) => j.keys || [])]);

  return (
    <section className="card stack" style={{ gap: 16 }} aria-label="Shorts from your videos">
      <div className="card-head">
        <h2>Shorts from your videos</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          Each chapter of a video, upright, with captions and a line pointing to the full video
        </span>
      </div>
      {withShorts.map((ep) => (
        <VideoBlock key={ep.key} ep={ep} queuedKeys={queuedKeys} onRender={onRender} />
      ))}
    </section>
  );
}

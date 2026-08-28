import { useMemo, useRef, useState } from "react";
import Chip from "./Chip.jsx";
import PlaylistCover from "./PlaylistCover.jsx";
import { api, seriesChip } from "../api.js";

/* Priority is derived purely from position in the recommended order — it is a
   label for rank, not a separate score. */
function priorityOf(rank) {
  if (rank <= 3) return ["HIGH", "prio-high", "🔥"];
  if (rank <= 7) return ["MEDIUM", "prio-med", "⚡"];
  return ["NORMAL", "prio-normal", "○"];
}

/* Length is the channel's strongest measured lever, so surface what the
   runtime implies rather than inventing a score. */
function lengthHint(secs) {
  if (secs == null) return null;
  if (secs <= 12) return ["loops well", "good"];
  if (secs <= 29) return ["mid-length", "ok"];
  return ["long — retention drops", "warn"];
}

function fmtDur(secs) {
  if (secs == null) return "—";
  return secs >= 60 ? `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s` : `${Math.round(secs)}s`;
}

function Thumb({ item }) {
  return item.has_thumb ? (
    <img className="uq-thumb" src={`/api/thumb/${item.key}`} alt="" loading="lazy" />
  ) : (
    <span className="uq-thumb uq-thumb-art"><PlaylistCover series={item.series} /></span>
  );
}

export default function UploadQueue({ items, discarded = [], staged = {}, customOrder,
                                      onMark, onOpen, onRender, onWatch, onDiscard, onRestore,
                                      onUpload, onUnstage, onOpenUploads,
                                      onPlaylistCreated, toast, refresh }) {
  const [tab, setTab] = useState("recommended");
  const [selected, setSelected] = useState(null);
  const [order, setOrder] = useState(null); // local override while dragging
  const dragKey = useRef(null);

  const list = order
    ? order.map((k) => items.find((i) => i.key === k)).filter(Boolean)
    : items;

  const playlists = useMemo(() => {
    const seen = new Map();
    for (const i of items) if (!seen.has(i.series)) seen.set(i.series, i.playlist);
    return [...seen.entries()];
  }, [items]);

  const isBin = tab === "discarded";
  const shown = isBin ? []
    : tab === "recommended" ? list.slice(0, 10)
    : tab === "all" ? list
    : list.filter((i) => i.series === tab);

  const blocked = items.filter((i) => i.blocked).length;
  const sel = selected ? items.find((i) => i.key === selected) : null;
  const selRank = sel ? list.findIndex((i) => i.key === sel.key) + 1 : 0;

  const persist = async (keys) => {
    try {
      await api("/api/queue-order", { keys });
      toast("✅ Upload order saved");
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const onDrop = (targetKey) => {
    const from = dragKey.current;
    dragKey.current = null;
    if (!from || from === targetKey) return;
    const keys = list.map((i) => i.key);
    const a = keys.indexOf(from), b = keys.indexOf(targetKey);
    if (a < 0 || b < 0) return;
    keys.splice(b, 0, keys.splice(a, 1)[0]);
    setOrder(keys);
    persist(keys);
  };

  const resetOrder = async () => {
    try {
      await api("/api/queue-order/reset", {});
      setOrder(null);
      toast("↩ Restored recommended order");
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
  };

  return (
    <div className={"uq-wrap" + (sel ? " with-detail" : "")}>
      <section className="panel uq-panel">
        {/* ---- header ---- */}
        <div className="uq-head">
          <div>
            <div className="uq-title">UPLOAD QUEUE</div>
            <div className="uq-sub">{items.length} videos staged and ready to post</div>
          </div>
          <div className="uq-stats">
            <div className="uq-stat"><b>{items.length}</b><span>Ready</span></div>
            <div className="uq-stat"><b>{playlists.length}</b><span>Playlists</span></div>
            <div className={"uq-stat" + (blocked ? " bad" : "")}>
              <b>{blocked}</b><span>Blocked</span>
            </div>
          </div>
        </div>

        {/* ---- tabs ---- */}
        <div className="uq-tabs">
          <button className={"uq-tab" + (tab === "recommended" ? " active" : "")}
                  onClick={() => setTab("recommended")}>★ Recommended</button>
          <button className={"uq-tab" + (tab === "all" ? " active" : "")}
                  onClick={() => setTab("all")}>All {items.length}</button>
          {playlists.map(([series, name]) => (
            <button key={series}
                    className={"uq-tab" + (tab === series ? " active" : "")}
                    onClick={() => setTab(series)}>
              {name}
            </button>
          ))}
          {discarded.length > 0 && (
            <button className={"uq-tab" + (isBin ? " active" : "")}
                    onClick={() => setTab("discarded")}>🗑 Discarded {discarded.length}</button>
          )}
          {customOrder && (
            <button className="btn btn-mini uq-reset" onClick={resetOrder}>↩ RESET ORDER</button>
          )}
        </div>

        {/* ---- rows ---- */}
        <div className="uq-rows">
          {isBin && discarded.map((it) => (
            <div key={it.key} className="uq-row uq-row-binned">
              <span className="uq-rank">🗑</span>
              <Thumb item={it} />
              <span className="uq-main">
                <span className="uq-name">{it.title}</span>
                <span className="uq-why">
                  Discarded {(it.discarded_at || "").slice(0, 16).replace("T", " ")}
                  {it.discard_reason ? ` — ${it.discard_reason}` : ""}
                </span>
              </span>
              <span className="uq-pl">
                <Chip cls={seriesChip(it.series)}>{it.playlist}</Chip>
              </span>
              <span className="uq-len"><b>{fmtDur(it.duration_sec)}</b></span>
              <button className="btn btn-mini uq-cta"
                      onClick={() => onRestore(it.key, it.title)}>↩ RESTORE</button>
            </div>
          ))}
          {isBin && !discarded.length && <div className="empty">Nothing discarded.</div>}
          {!isBin && !shown.length && <div className="empty">Nothing staged in this view.</div>}
          {shown.map((it) => {
            const rank = list.findIndex((x) => x.key === it.key) + 1;
            const [pLabel, pCls, pIcon] = priorityOf(rank);
            const hint = lengthHint(it.duration_sec);
            return (
              <div
                key={it.key}
                className={"uq-row" + (selected === it.key ? " selected" : "")}
                draggable
                onDragStart={() => { dragKey.current = it.key; }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(it.key)}
                onClick={() => setSelected(selected === it.key ? null : it.key)}
              >
                <span className="uq-grip" title="Drag to reorder">⠿</span>
                <span className="uq-rank">{String(rank).padStart(2, "0")}</span>
                <span className={"uq-prio " + pCls}>{pIcon} {pLabel}</span>
                <Thumb item={it} />
                <span className="uq-main">
                  <span className="uq-name">{it.title}</span>
                  <span className="uq-why">{it.reason}</span>
                  {it.next_in_playlist && (
                    <span className="uq-next">Then in this playlist: {it.next_in_playlist}</span>
                  )}
                </span>
                <span className="uq-pl">
                  <Chip cls={seriesChip(it.series) + (it.blocked ? " blocked" : "")}>
                    {it.blocked ? `⚠ ${it.playlist}` : it.playlist}
                  </Chip>
                </span>
                <span className="uq-len">
                  <b>{fmtDur(it.duration_sec)}</b>
                  {hint && <span className={"uq-hint " + hint[1]}>{hint[0]}</span>}
                </span>
                <button
                  className="btn btn-mini btn-primary uq-cta"
                  onClick={(e) => { e.stopPropagation(); onMark(it.key, it.title); }}
                >
                  ✅ MARK UPLOADED
                </button>
                <button
                  className="btn btn-mini uq-more"
                  title="Watch here"
                  onClick={(e) => { e.stopPropagation(); onWatch(it); }}
                >
                  ▶
                </button>
                <button
                  className="btn btn-mini uq-more uq-bin"
                  title="Discard — take this out of the queue without marking it uploaded"
                  onClick={(e) => { e.stopPropagation(); onDiscard(it.key, it.title); }}
                >
                  🗑
                </button>
                {(() => {
                  const st = staged[it.key];
                  if (st) {
                    return (
                      <button
                        className={"btn btn-mini uq-more uq-staged " + st.state}
                        title={st.state === "running"
                          ? `uploading — ${st.stage} ${st.pct}%`
                          : "staged for upload — click to remove"}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (st.state !== "running") onUnstage(it);
                        }}
                      >
                        {st.state === "running" ? `${st.pct}%` : "✓"}
                      </button>
                    );
                  }
                  return (
                    <button
                      className="btn btn-mini uq-more uq-up"
                      title="Stage for upload (goes to Upload Control)"
                      onClick={(e) => { e.stopPropagation(); onUpload(it); }}
                    >
                      ⬆
                    </button>
                  );
                })()}
              </div>
            );
          })}
        </div>

        <div className="uq-foot">
          <span>
            {isBin
              ? "Discarded videos keep their files in export/_discarded/ — restore puts them back."
              : (customOrder ? "Showing your custom order. Drag a row to reorder."
                             : "Showing recommended order. Drag a row to reorder.")}
          </span>
          {blocked > 0 && (
            <span className="uq-foot-warn">
              ⚠ {blocked} blocked — their playlist doesn't exist on YouTube yet
            </span>
          )}
        </div>
      </section>

      {/* ---- detail ---- */}
      {sel && (
        <aside className="panel uq-detail">
          <button className="uq-close" onClick={() => setSelected(null)}>✕</button>
          <div className="uq-d-head">
            <Thumb item={sel} />
            <div>
              <span className={"uq-prio " + priorityOf(selRank)[1]}>
                {priorityOf(selRank)[2]} {priorityOf(selRank)[0]} PRIORITY
              </span>
              <div className="uq-d-title">{sel.title}</div>
              <div className="uq-d-sub">{sel.reason}</div>
            </div>
          </div>

          <div className="uq-d-grid">
            <div><span>Playlist</span><b>{sel.playlist}</b></div>
            <div><span>Episode</span><b>{sel.episode} of {sel.series_total}</b></div>
            <div><span>Queue position</span><b>#{selRank} of {items.length}</b></div>
            <div><span>Length</span><b>{fmtDur(sel.duration_sec)}</b></div>
          </div>

          {sel.blocked && (
            <div className="uq-d-warn">
              ⚠ The “{sel.playlist}” playlist does not exist on YouTube yet — create it
              before uploading this video.
              <button
                className="btn btn-mini btn-primary uq-d-created"
                onClick={() => onPlaylistCreated(sel.series, sel.playlist)}
              >
                ✓ I'VE CREATED IT
              </button>
            </div>
          )}

          <div className="uq-d-block">
            <div className="uq-d-label">WHY THIS ONE</div>
            <p>{sel.reason}</p>
            {lengthHint(sel.duration_sec) && (
              <p className="muted">
                At {fmtDur(sel.duration_sec)} it reads as{" "}
                <b>{lengthHint(sel.duration_sec)[0]}</b> against your analytics — short
                videos loop and retain best.
              </p>
            )}
          </div>

          <div className="uq-d-block">
            <div className="uq-d-label">SOURCE FILE</div>
            <div className="uq-d-path">
              <code>{sel.exported}</code>
              <button
                className="btn btn-mini"
                title="Copy path"
                onClick={() => {
                  navigator.clipboard?.writeText(sel.exported);
                  toast("📋 Path copied");
                }}
              >⧉</button>
            </div>
            {sel.source && <div className="uq-d-src">Data source: {sel.source}</div>}
            {sel.rendered_on && <div className="uq-d-src">Rendered {sel.rendered_on}</div>}
          </div>

          {(sel.prev_uploaded || sel.next_in_playlist) && (
            <div className="uq-d-block">
              <div className="uq-d-label">IN THIS PLAYLIST</div>
              {sel.prev_uploaded && (
                <div className="uq-d-nav">▲ Last uploaded: <b>{sel.prev_uploaded}</b></div>
              )}
              {sel.next_in_playlist && (
                <div className="uq-d-nav">▼ Next queued: <b>{sel.next_in_playlist}</b></div>
              )}
            </div>
          )}

          <div className="uq-d-actions">
            <button className="btn btn-primary" onClick={() => onMark(sel.key, sel.title)}>
              ✅ MARK AS UPLOADED
            </button>
            <button className="btn" onClick={() => onWatch(sel)}>▶ WATCH VIDEO</button>
            <button className="btn" onClick={() => onOpen(sel.exported)}>📂 OPEN FOLDER</button>
            <button className="btn" onClick={() => onRender(sel.key, sel.title)}>⟳ RE-RENDER</button>
            <button className="btn btn-danger" onClick={() => onDiscard(sel.key, sel.title)}>
              🗑 DISCARD
            </button>
            {staged[sel.key] ? (
              <button className="btn" onClick={() => onOpenUploads()}>
                ✓ STAGED — OPEN UPLOAD CONTROL
              </button>
            ) : (
              <button className="btn btn-primary" onClick={() => onUpload(sel)}>
                ⬆ STAGE FOR UPLOAD
              </button>
            )}
          </div>
          <p className="uq-d-hint muted">
            Discarding keeps this out of the queue without recording it as uploaded.
            The files move to <code>export/_discarded/</code> and can be restored.
          </p>
          <p className="uq-d-hint muted">
            Staging adds this to the upload batch — nothing is sent until you run it from
            Upload Control. Videos arrive on YouTube as <b>Private</b>; visibility is the
            one step that stays manual.
          </p>
          {staged[sel.key]?.error && (
            <div className="lc-note lc-note-warn">⚠ {staged[sel.key].error}</div>
          )}
        </aside>
      )}
    </div>
  );
}

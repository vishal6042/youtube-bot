import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Btn, Chip, Empty, PageHeader, Pager, PlaylistChip, Tabs, Thumb, fmtDuration, fmtNum, fmtWhen, usePaged,
} from "../ui.jsx";
import MoreMenu from "./upload/MoreMenu.jsx";
import Transmission, { StoppedBanner, mb } from "./upload/Transmission.jsx";
import { BatchCard, ChecksCard, LimitCard } from "./upload/BatchRail.jsx";
import "../screens/publish.css";

const PAGE = 8;
const VERDICT = { move_up: "Move up", move_down: "Move down", hold: "Hold back" };

function stagedLabel(st) {
  if (st.state === "running") return [`Uploading ${st.pct ?? 0}%`, "go"];
  if (st.state === "failed") return ["Upload failed", "bad"];
  if (st.state === "done") return ["Uploaded", "go"];
  return ["In today's batch", "go"];
}

const DISMISS_KEY = "dim.upload.dismissedStop";

function QueueCard({ it, rank, st, primary, drag, menu, onWatch, onUpload, onUnstage, onPlaylistCreated }) {
  const meta = [
    it.episode != null && `episode ${it.episode}${it.series_total ? ` of ${it.series_total}` : ""}`,
    !/\d+s$/.test(it.reason || "") && fmtDuration(it.duration_sec),
  ].filter(Boolean).join(" · ");
  const [label, tone] = st ? stagedLabel(st) : [];
  return (
    <article className={"card lift rowf q-card" + (st ? " staged" : "") + (drag.cls ? " " + drag.cls : "")}
             draggable {...drag.handlers}>
      <span className="num q-rank" aria-label={`Position ${rank}`}>{rank}</span>
      <div className="q-thumb"><Thumb item={it} /></div>
      <div className="q-body">
        <div className="rowf">
          <h2>{it.title}</h2>
          {st && <Chip tone={tone} plain>{label}</Chip>}
        </div>
        <div className="rowf" style={{ marginTop: 6 }}>
          <PlaylistChip series={it.series} name={it.playlist} />
          {meta && <span className="muted num" style={{ fontSize: 12.5 }}>{meta}</span>}
          {it.blocked && <Chip tone="warn">Playlist not on YouTube yet</Chip>}
        </div>
        {it.reason && <p className="muted">{it.reason}</p>}
        {(it.prev_uploaded || it.next_in_playlist) && (
          <p className="faint q-note" style={{ marginTop: 4 }}>
            {[it.prev_uploaded && `Last posted in this playlist: ${it.prev_uploaded}`,
              it.next_in_playlist && `Next after this: ${it.next_in_playlist}`].filter(Boolean).join(" · ")}
          </p>
        )}
        {it.blocked && (
          <div className="rowf" style={{ marginTop: 10 }}>
            <span className="muted" style={{ fontSize: 13, flex: "1 1 200px" }}>
              Create the {it.playlist} playlist on YouTube before sending this video.
            </span>
            <Btn size="sm" icon="check" onClick={() => onPlaylistCreated(it.series, it.playlist, true)}>
              I have created it
            </Btn>
          </div>
        )}
        {st?.error && <p style={{ color: "var(--bad)", overflowWrap: "anywhere" }}>Last attempt failed: {st.error}</p>}
      </div>
      <div className="rowf q-acts">
        <Btn kind="ghost" size="sm" icon="play" iconOnly={`Play preview of ${it.title}`} onClick={() => onWatch(it)} />
        <MoreMenu label={`More actions for ${it.title}`} items={menu} />
        {st ? (
          <Btn size="sm" disabled={st.state === "running"} onClick={() => onUnstage(it)}>Remove</Btn>
        ) : (
          <Btn size="sm" kind={primary ? "primary" : ""} onClick={() => onUpload(it)}>Add to batch</Btn>
        )}
      </div>
    </article>
  );
}

function ReviewCard({ review, titleOf, onApply, onClose }) {
  const notes = review.items.filter((n) => n.verdict !== "keep");
  return (
    <section className="card" aria-label="Order review">
      <div className="card-head">
        <h2>Order review</h2>
        <span className="faint" style={{ fontSize: 12.5 }}>
          {review.model === "rules"
            ? "Rule checks, run on this machine"
            : `${review.model}${review.usage
              ? ` · ${fmtNum(review.usage.input_tokens)} in, ${fmtNum(review.usage.output_tokens)} out tokens` : ""}`}
        </span>
        <span className="spacer" />
        <Btn kind="ghost" size="sm" icon="close" iconOnly="Close the review" onClick={onClose} />
      </div>
      <p>{review.summary}</p>
      {notes.length > 0 ? (
        <ul className="stack" style={{ margin: "12px 0 0", padding: 0, listStyle: "none", gap: 10 }}>
          {notes.map((n) => (
            <li key={n.key} className="rowf" style={{ alignItems: "baseline" }}>
              <Chip plain tone={n.verdict === "hold" ? "warn" : "info"}>{VERDICT[n.verdict] || "Note"}</Chip>
              <span style={{ flex: "1 1 240px", minWidth: 0 }}>
                <b style={{ fontWeight: 550 }}>{titleOf(n.key)}</b>
                <span className="muted"> {n.note}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>Every pick is fine where it is.</p>
      )}
      {review.changed && (
        <Btn kind="primary" size="sm" icon="check" style={{ marginTop: 14 }} onClick={onApply}>
          Use the suggested order
        </Btn>
      )}
    </section>
  );
}

export default function UploadPage({
  items = [], discarded = [], customOrder, staged = {}, batch = [], run = {}, quota = {},
  onMark, onOpen, onRender, onWatch, onDiscard, onRestore, onUpload, onUnstage, onClearBatch,
  onPlaylistCreated, confirm, toast, refresh,
}) {
  // ---- batch, checks and the live run ----
  const [data, setData] = useState(null);     // /api/upload/batch: rows with title, size, thumbnail
  const [pre, setPre] = useState(undefined);  // undefined = checking, null = could not check
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissedRaw] = useState(() => {
    try { return window.localStorage.getItem(DISMISS_KEY); } catch { return null; }
  });
  // Remembered in this browser, because the server keeps reporting the last
  // run's stop reason until another run starts.
  const setDismissed = (reason) => {
    setDismissedRaw(reason);
    try {
      if (reason) window.localStorage.setItem(DISMISS_KEY, reason);
      else window.localStorage.removeItem(DISMISS_KEY);
    } catch { /* storage unavailable: the dismissal lasts for this visit only */ }
  };

  const load = useCallback(async () => {
    try { setData(await api("/api/upload/batch")); } catch { /* app state still drives the page */ }
  }, []);
  const loadPreflight = useCallback(async () => {
    setPre(undefined);
    try { setPre(await api("/api/upload/preflight")); } catch { setPre(null); }
  }, []);

  // App state is polled every few seconds; during a run this page polls the
  // batch itself so the progress bar moves, and trusts that fresher copy.
  const live = data && (data.run?.running || run.running) ? data : null;
  const liveRun = live ? live.run : run;
  const liveQuota = live?.quota || quota;
  const running = !!liveRun.running;

  const sig = batch.map((b) => `${b.key}:${b.state}`).join("|");
  const pendingSig = batch.filter((b) => b.state === "queued" || b.state === "failed").map((b) => b.key).join("|");
  useEffect(() => { load(); }, [sig, load]);
  useEffect(() => { if (!running) loadPreflight(); }, [pendingSig, running, loadPreflight]);
  useEffect(() => {
    if (!running && !run.running) return undefined;
    const t = setInterval(load, 900);
    return () => clearInterval(t);
  }, [running, run.running, load]);

  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) refresh();
    wasRunning.current = running;
  }, [running, refresh]);

  const detail = useMemo(
    () => Object.fromEntries((data?.batch || []).map((b) => [b.key, b])), [data]);
  const rows = (live ? live.batch : batch).map((b) => {
    const it = items.find((i) => i.key === b.key);
    const row = {
      ...(it && { title: it.title, series: it.series, playlist: it.playlist, has_thumb: it.has_thumb }),
      ...detail[b.key], ...b,
    };
    return { ...row, title: row.title || b.key };
  });
  const rowByKey = Object.fromEntries(rows.map((b) => [b.key, b]));
  const pending = rows.filter((b) => b.state === "queued" || b.state === "failed");

  const send = async () => {
    const n = pending.length;
    const ok = await confirm({
      title: `Send ${n} video${n === 1 ? "" : "s"} to YouTube?`,
      message: "Each one goes to Data in Motion with its title, description, thumbnail "
             + "and playlist set automatically.",
      items: pending.map((b) => ({ title: b.title, meta: [b.playlist, mb(b.bytes)].filter(Boolean).join(" · ") })),
      detail: "They arrive as Private, and you switch them to Public in YouTube Studio. This uses "
            + `${fmtNum(n * (liveQuota.per_upload || 1702))} of your ${fmtNum(liveQuota.units_left)} `
            + "remaining API units today.",
      confirmLabel: "Start uploading",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api("/api/upload/batch/run", {});
      setDismissed(null);
      toast("Upload run started");
      await load();
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  // ---- queue ----
  const [tab, setTab] = useState("recommended");
  const [order, setOrder] = useState(null); // optimistic order until the server's copy arrives
  const [review, setReview] = useState(null);
  const [reviewing, setReviewing] = useState(false);
  const [dragKey, setDragKey] = useState(null);
  const [overKey, setOverKey] = useState(null);

  const list = useMemo(() => {
    if (!order) return items;
    const known = order.map((k) => items.find((i) => i.key === k)).filter(Boolean);
    return [...known, ...items.filter((i) => !order.includes(i.key))];
  }, [order, items]);

  const playlists = useMemo(() => {
    const seen = new Map();
    for (const i of items) {
      const p = seen.get(i.series) || { name: i.playlist, count: 0 };
      p.count += 1;
      seen.set(i.series, p);
    }
    return [...seen.entries()];
  }, [items]);

  const view = tab === "discarded" ? (discarded.length ? tab : "recommended")
    : tab === "recommended" || playlists.some(([s]) => s === tab) ? tab : "recommended";
  const isBin = view === "discarded";
  const shown = isBin ? discarded : view === "recommended" ? list : list.filter((i) => i.series === view);
  const p = usePaged(shown, PAGE, view);
  const titleOf = (key) => items.find((i) => i.key === key)?.title || detail[key]?.title || key;
  const firstOpen = list.find((i) => !rowByKey[i.key] && !staged[i.key] && !i.blocked)?.key;

  const persist = async (keys) => {
    setOrder(keys);
    try {
      await api("/api/queue-order", { keys });
      toast("Upload order saved");
      await refresh();
    } catch (e) {
      toast(e.message, true);
    }
    setOrder(null);
  };

  // Puts `from` where `target` is, in the full queue (the same move for a drop
  // and for the menu's Move up / Move down).
  const moveTo = (from, target) => {
    if (!from || !target || from === target) return;
    const keys = list.map((i) => i.key);
    const a = keys.indexOf(from), b = keys.indexOf(target);
    if (a < 0 || b < 0) return;
    keys.splice(b, 0, keys.splice(a, 1)[0]);
    persist(keys);
  };

  const resetOrder = async () => {
    try {
      await api("/api/queue-order/reset", {});
      setOrder(null);
      toast("Recommended order restored");
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
  };

  // Rule checks plus local-model judgment over the top picks. Runs only on
  // this click because the local model can take a minute.
  const runReview = async () => {
    setReviewing(true);
    try {
      setReview(await api("/api/queue/ai-review", {}));
    } catch (e) {
      toast(e.message, true);
    }
    setReviewing(false);
  };

  const applyReview = async () => {
    const suggested = review.suggested_order || [];
    const rest = list.map((i) => i.key).filter((k) => !suggested.includes(k));
    setReview(null);
    await persist([...suggested, ...rest]);
  };

  const copyPath = (it) => {
    navigator.clipboard?.writeText(it.exported);
    toast("File path copied");
  };

  const dragProps = (key) => ({
    cls: dragKey === key ? "dragging" : overKey === key && dragKey ? "over" : "",
    handlers: {
      onDragStart: (e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", key);
        setDragKey(key);
      },
      onDragOver: (e) => { e.preventDefault(); if (overKey !== key) setOverKey(key); },
      onDrop: (e) => { e.preventDefault(); moveTo(dragKey, key); setDragKey(null); setOverKey(null); },
      onDragEnd: () => { setDragKey(null); setOverKey(null); },
    },
  });

  const menuFor = (it) => {
    const i = shown.findIndex((x) => x.key === it.key);
    return [
      { label: "Mark as uploaded", icon: "check", onClick: () => onMark(it.key, it.title) },
      it.exported && { label: "Open folder", icon: "folder", onClick: () => onOpen(it.exported) },
      it.exported && { label: "Copy file path", onClick: () => copyPath(it) },
      { label: "Re-render", icon: "refresh", onClick: () => onRender(it.key, it.title) },
      i > 0 && { label: "Move up", onClick: () => moveTo(it.key, shown[i - 1].key) },
      i < shown.length - 1 && { label: "Move down", onClick: () => moveTo(it.key, shown[i + 1].key) },
      { label: "Discard", icon: "trash", tone: "bad", onClick: () => onDiscard(it.key, it.title) },
    ];
  };

  const tabs = [
    { value: "recommended", label: "Recommended", count: items.length },
    ...playlists.map(([series, pl]) => ({ value: series, label: pl.name || series, count: pl.count })),
    ...(discarded.length ? [{ value: "discarded", label: "Discarded", count: discarded.length }] : []),
  ];

  const stopped = liveRun.stopped_reason && liveRun.stopped_reason !== dismissed ? liveRun.stopped_reason : null;

  return (
    <>
      <PageHeader title="Upload" sub="Pick from the queue on the left, check and send on the right">
        <Btn disabled={reviewing || !items.length} onClick={runReview}
             title="Rule checks plus a local model's judgment over the top picks. Free, and it can take a minute.">
          {reviewing ? <><span className="spin" /> Reviewing the order</> : "Review the order"}
        </Btn>
      </PageHeader>

      {stopped && (
        <StoppedBanner reason={stopped} rows={rows} titleOf={titleOf} onDismiss={() => setDismissed(stopped)} />
      )}

      <Transmission rows={rows} run={liveRun} />

      {/* Tabs sit above both columns so the queue and today's batch start level. */}
      <Tabs value={view} onChange={setTab} options={tabs} label="Queue view" />

      <div className="split">
        <section className="wide stack" aria-label="Upload queue">

          {review && !isBin && (
            <ReviewCard review={review} titleOf={titleOf} onApply={applyReview} onClose={() => setReview(null)} />
          )}

          {!shown.length && (
            <div className="card">
              <Empty icon="upload" title="Nothing is ready to post">
                Videos show up here once they have been rendered and approved.
              </Empty>
            </div>
          )}

          {isBin && p.slice.map((it) => (
            <article key={it.key} className="card rowf q-card" style={{ cursor: "default" }}>
              <Thumb item={it} />
              <div className="q-body">
                <h2>{it.title}</h2>
                <div className="rowf" style={{ marginTop: 6 }}>
                  <PlaylistChip series={it.series} name={it.playlist} />
                  {it.duration_sec != null && (
                    <span className="muted num" style={{ fontSize: 12.5 }}>{fmtDuration(it.duration_sec)}</span>
                  )}
                </div>
                <p className="muted">
                  Discarded {fmtWhen(it.discarded_at)}{it.discard_reason ? `: ${it.discard_reason}` : ""}
                </p>
              </div>
              <div className="rowf q-acts">
                <Btn kind="ghost" size="sm" icon="play" iconOnly={`Play preview of ${it.title}`}
                     onClick={() => onWatch(it)} />
                <Btn size="sm" icon="undo" onClick={() => onRestore(it.key, it.title)}>Restore</Btn>
              </div>
            </article>
          ))}

          {!isBin && p.slice.map((it) => (
            <QueueCard
              key={it.key}
              it={it}
              rank={list.findIndex((x) => x.key === it.key) + 1}
              st={rowByKey[it.key] || staged[it.key]}
              primary={it.key === firstOpen}
              drag={dragProps(it.key)}
              menu={menuFor(it)}
              onWatch={onWatch}
              onUpload={onUpload}
              onUnstage={onUnstage}
              onPlaylistCreated={onPlaylistCreated}
            />
          ))}

          {p.total > PAGE && <Pager p={p} noun="videos" sizes={null} style={{ paddingTop: 2 }} />}

          {shown.length > 0 && (
            <p className="faint q-note">
              {isBin ? (
                "Discarded videos keep their files in export/_discarded. Restore puts them back in the queue."
              ) : (
                <>
                  {customOrder ? "This is your own order. " : "This is the recommended order. "}
                  Drag a card to change it. The More menu holds Mark as uploaded, Open folder,
                  Re-render and Discard.{" "}
                  {customOrder && (
                    <button type="button" className="link" onClick={resetOrder}>
                      Go back to the recommended order
                    </button>
                  )}
                </>
              )}
            </p>
          )}
        </section>

        <aside className="rail" aria-label="Today's batch" style={{ position: "sticky", top: 24 }}>
          <BatchCard rows={rows} pending={pending} run={liveRun} pre={pre} busy={busy}
                     onSend={send} onRemove={onUnstage} onClear={onClearBatch} />
          <LimitCard quota={liveQuota} />
        </aside>
      </div>

      <ChecksCard pre={pre} onRecheck={loadPreflight} />
    </>
  );
}

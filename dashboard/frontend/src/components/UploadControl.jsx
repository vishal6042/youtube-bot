import { useCallback, useEffect, useState } from "react";
import Chip from "./Chip.jsx";
import TransmissionArc, { mb } from "./TransmissionArc.jsx";
import { api, seriesChip } from "../api.js";

/* Upload Control — stage a batch, preflight it, send it.
 *
 * The render orchestrator is drawn as a network because renders run several
 * agents at once. Uploading is the opposite shape: strictly one video at a time,
 * with one step (the transfer) taking almost all the wall clock. So this is a
 * transmission arc — your file on the left, the channel on the right, and the
 * five real stages the uploader reports as gates along the beam.
 */

export default function UploadControl({ onBack, onStarted, toast, confirm }) {
  const [data, setData] = useState(null);
  const [pre, setPre] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api("/api/upload/batch"));
    } catch (e) {
      setData({ error: e.message });
    }
  }, []);

  const loadPreflight = useCallback(async () => {
    try { setPre(await api("/api/upload/preflight")); } catch { setPre(null); }
  }, []);

  useEffect(() => { load(); loadPreflight(); }, [load, loadPreflight]);

  // Poll while a run is in flight so the arc animates.
  useEffect(() => {
    if (!data?.run?.running) return undefined;
    const t = setInterval(load, 900);
    return () => clearInterval(t);
  }, [data?.run?.running, load]);

  if (!data) return <section className="panel"><div className="empty">Loading…</div></section>;
  if (data.error) return <section className="panel"><div className="empty">{data.error}</div></section>;

  const batch = data.batch || [];
  const q = data.quota || {};
  const run = data.run || {};
  const pending = batch.filter((b) => b.state === "queued" || b.state === "failed");
  const current = batch.find((b) => b.key === run.current) || pending[0] || batch[0];

  const remove = async (key) => {
    try { await api("/api/upload/batch/remove", { key }); await load(); await loadPreflight(); }
    catch (e) { toast(e.message, true); }
  };

  const clearDone = async () => {
    try {
      const r = await api("/api/upload/batch/clear", {});
      toast(`Cleared ${r.removed} finished`);
      await load();
    } catch (e) { toast(e.message, true); }
  };

  const start = async () => {
    const ok = await confirm({
      title: `Upload ${pending.length} video${pending.length === 1 ? "" : "s"}?`,
      message: "Each one goes to Data in Motion with its title, description, thumbnail "
             + "and playlist set automatically.",
      items: pending.map((b) => ({ title: b.title, meta: `${b.playlist} · ${mb(b.bytes)}` })),
      detail: `They arrive PRIVATE — you flip them to Public in Studio. Uses `
            + `${pending.length * (q.per_upload || 1702)} of your ${q.units_left} remaining `
            + `API units today.`,
      confirmLabel: "▶ START UPLOADING",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api("/api/upload/batch/run", {});
      toast("⬆ Upload run started");
      await load();
      // The live view lives on Mission, so go and watch it rather than leaving
      // the user on a screen that now only mirrors it.
      if (onStarted) onStarted();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const pctOfQuota = q.slots_total ? (q.uploads_today / q.slots_total) * 100 : 0;

  return (
    <div className="uc">
      <section className="panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">UPLOAD CONTROL</div>
            <div className="pl-series">stage a batch, check it, send it to YouTube</div>
          </div>
          <div className={"lcp-runway " + (q.slots_left > 2 ? "ok" : q.slots_left > 0 ? "warn" : "low")}>
            <b>{q.slots_left ?? "—"}</b>
            <span>upload slot{q.slots_left === 1 ? "" : "s"} left today</span>
          </div>
        </div>
      </section>

      {(run.running || run.stopped_reason) && (
        <section className="panel">
          <div className="jobs-head">
            <span className="panel-title">TRANSMISSION</span>
            <span className="ul-meta">
              {run.running ? `${current?.title || run.current} — ${run.stage}` : "stopped"}
            </span>
          </div>
          <TransmissionArc item={current} run={run} />
          {run.stopped_reason && (
            <div className="lc-note lc-note-warn">
              ⚠ Run stopped: {run.stopped_reason}. Nothing further was attempted — a failure
              here is usually systemic, and each attempt costs {q.per_upload} quota units.
            </div>
          )}
        </section>
      )}

      {/* ---- 1 · what is staged ---- */}
      <section className="panel lcp-step">
        <div className="lcp-step-head">
          <span className="lcp-num">1</span>
          <span className="panel-title">BATCH</span>
          <span className="lcp-step-hint">
            {batch.length} staged · add more with ⬆ in the queue below
          </span>
        </div>

        {batch.length === 0 ? (
          <div className="empty">
            Nothing staged. Press ⬆ on any video in the queue below.
          </div>
        ) : (
          <div className="uc-list">
            {batch.map((b, i) => (
              <div className={"uc-row " + b.state} key={b.key}>
                <span className="uc-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="uc-thumb">
                  {b.has_thumb && <img src={`/api/thumb/${b.key}`} alt="" loading="lazy" />}
                </span>
                <span className="uc-main">
                  <span className="uc-title">{b.title}</span>
                  <span className="uc-meta">
                    {b.series && <Chip cls={seriesChip(b.series)}>{b.playlist}</Chip>}
                    <span className="uc-size">{mb(b.bytes)}</span>
                  </span>
                </span>
                <span className="uc-state">
                  {b.state === "running" && (
                    <>
                      <span className="uc-prog"><i style={{ width: `${b.pct}%` }} /></span>
                      <em>{b.stage} {b.pct}%</em>
                    </>
                  )}
                  {b.state === "queued" && <em className="muted">queued</em>}
                  {b.state === "done" && (
                    <a href={b.url} target="_blank" rel="noreferrer" className="uc-link">
                      ✅ private on YouTube ↗
                    </a>
                  )}
                  {b.state === "failed" && <em className="bad">✕ {b.error}</em>}
                </span>
                <span className="uc-act">
                  {b.state !== "running" && (
                    <button className="btn btn-mini" title="Remove from the batch"
                            onClick={() => remove(b.key)}>✕</button>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="uc-actions">
          <button
            className="btn btn-primary uc-run"
            disabled={busy || run.running || !pending.length || !pre?.ok}
            onClick={start}
          >
            {run.running
              ? `⬆ UPLOADING — ${run.stage} ${run.pct}%`
              : pending.length
                ? `▶ UPLOAD ${pending.length} VIDEO${pending.length === 1 ? "" : "S"}`
                : "NOTHING STAGED"}
          </button>
          {batch.some((b) => b.state === "done") && (
            <button className="btn" onClick={clearDone}>CLEAR FINISHED</button>
          )}
        </div>
        {!pre?.ok && pending.length > 0 && (
          <p className="an-note">Preflight has to pass before a run can start.</p>
        )}
      </section>
      {/* ---- 2 · preflight ---- */}
      <section className="panel lcp-step">
        <div className="lcp-step-head">
          <span className="lcp-num">2</span>
          <span className="panel-title">PREFLIGHT</span>
          <span className="lcp-step-hint">checked before any quota is spent</span>
        </div>
        <div className="uc-checks">
          {(pre?.checks || []).map((c) => (
            <div className={"uc-check" + (c.ok ? " ok" : " bad")} key={c.name}>
              <span>{c.ok ? "✓" : "✕"}</span>
              <b>{c.name}</b>
              <em>{c.detail}</em>
            </div>
          ))}
          {!pre && <div className="empty">Checking…</div>}
        </div>
        <button className="btn btn-mini" onClick={loadPreflight}>⟳ RE-CHECK</button>
      </section>

      {/* ---- 3 · quota ---- */}
      <section className="panel lcp-step">
        <div className="lcp-step-head">
          <span className="lcp-num">3</span>
          <span className="panel-title">DAILY QUOTA</span>
          <span className="lcp-step-hint">resets at midnight US Pacific ({q.day})</span>
        </div>
        <div className="uc-quota">
          <div className="uc-quota-bar">
            {Array.from({ length: q.slots_total || 5 }, (_, i) => (
              <span key={i} className={"uc-slot" + (i < (q.uploads_today || 0) ? " used" : "")} />
            ))}
          </div>
          <div className="uc-quota-text">
            <b>{q.uploads_today}</b> of {q.slots_total} used ·{" "}
            <b>{q.units_used?.toLocaleString()}</b> / {q.daily_units?.toLocaleString()} units ·{" "}
            {q.per_upload} per upload
          </div>
        </div>
      </section>

    </div>
  );
}

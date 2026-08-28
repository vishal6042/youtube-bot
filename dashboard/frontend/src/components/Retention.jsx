import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

/* Disk retention, on the Settings screen: edit the policy, preview exactly what
   a purge would delete, and run it.
   The preview is always a dry run — the server only deletes on an explicit
   POST to /api/retention/apply, which this confirms first with the real list. */

const FIELDS = [
  { key: "output_days_after_export", label: "DELETE output/ AFTER",
    unit: "days from export",
    hint: "Working copies. Only counted once the topic has actually been exported — an unexported render is the only copy there is." },
  { key: "export_days_after_upload", label: "DELETE export/ AFTER",
    unit: "days from upload",
    hint: "Finished videos. Counted from the day it went live on YouTube, never from the day it was made." },
  { key: "stale_warn_days", label: "WARN ABOUT BACKLOG AFTER",
    unit: "days staged",
    hint: "Just a warning. Nothing unposted is ever deleted, however old it gets." },
];

function mb(bytes) {
  if (!bytes) return "0 MB";
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

export default function Retention({ toast, confirm }) {
  const [data, setData] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api("/api/retention");
      setData(r);
      if (r.policy) { setPolicy(r.policy); setDirty(false); }
    } catch (e) {
      setData({ available: false, reason: e.message });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!data) {
    return (
      <section className="panel">
        <div className="panel-title">DISK RETENTION</div>
        <div className="empty">Loading…</div>
      </section>
    );
  }

  if (!data.available) {
    return (
      <section className="panel">
        <div className="panel-title">DISK RETENTION</div>
        <div className="empty">Unavailable — {data.reason}</div>
      </section>
    );
  }

  const savePolicy = async () => {
    setBusy(true);
    try {
      await api("/api/retention/policy", policy);
      toast("✅ Retention policy saved");
      await load();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const runPurge = async () => {
    const items = [...data.output, ...data.export];
    const ok = await confirm({
      title: `Delete ${folders} folder${folders === 1 ? "" : "s"}?`,
      message: `${items.length} video${items.length === 1 ? "" : "s"} across ${folders} `
             + `folder${folders === 1 ? "" : "s"}. Frees ${mb(data.bytes)} and cannot be `
             + `undone — the videos stay on YouTube, only local files go.`,
      items: items.slice(0, 8).map((i) => ({
        title: i.title + (i.copies > 1 ? `  ×${i.copies}` : ""), meta: i.reason,
      })),
      detail: items.length > 8
        ? `…and ${items.length - 8} more. ${data.kept_unposted} unposted export(s) are kept.`
        : `${data.kept_unposted} unposted export(s) are kept, whatever their age.`,
      confirmLabel: "🗑 DELETE THEM",
      tone: "danger",
    });
    if (!ok) return;
    setBusy(true);
    try {
      const r = await api("/api/retention/apply", {});
      toast(`🗑 Deleted ${r.deleted} folder(s), freed ${mb(r.freed)}`);
      await load();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const items = [...data.output.map((i) => ({ ...i, kind: "output" })),
                 ...data.export.map((i) => ({ ...i, kind: "export" }))];
  // A topic rendered on several days has one folder per day; the rows are
  // grouped per video, so the folder count is reported separately.
  const folders = items.reduce((a, i) => a + (i.copies || 1), 0);
  const shown = showAll ? items : items.slice(0, 6);

  return (
    <section className="panel">
      <div className="an-head">
        <span className="panel-title">DISK RETENTION</span>
        <span className="an-head-meta">
          durations run from the lifecycle event, not the folder date
        </span>
      </div>

      {/* ---- policy ---- */}
      <div className="ret-policy">
        {FIELDS.map((f) => (
          <label className="ret-field" key={f.key}>
            <span className="set-label">{f.label}</span>
            <span className="ret-input">
              <input
                type="number" min="0" max="3650"
                value={policy?.[f.key] ?? ""}
                onChange={(e) => {
                  setPolicy((p) => ({ ...p, [f.key]: Number(e.target.value) }));
                  setDirty(true);
                }}
              />
              <span>{f.unit}</span>
            </span>
            <span className="ret-hint">{f.hint}</span>
          </label>
        ))}
      </div>
      <div className="ret-actions">
        <button className="btn btn-primary" disabled={!dirty || busy} onClick={savePolicy}>
          {dirty ? "💾 SAVE POLICY" : "✓ SAVED"}
        </button>
        <button className="btn" disabled={busy} onClick={load}>⟳ RECALCULATE</button>
      </div>

      {/* ---- what would go ---- */}
      <div className="ret-summary">
        <div className="ret-stat">
          <span>RECLAIMABLE NOW</span><b>{mb(data.bytes)}</b>
          <em>
            {items.length} video{items.length === 1 ? "" : "s"} · {folders} folder
            {folders === 1 ? "" : "s"}
          </em>
        </div>
        <div className="ret-stat">
          <span>WORKING COPIES</span><b>{data.output.length}</b>
          <em>output/ · exported {data.policy.output_days_after_export}d+ ago</em>
        </div>
        <div className="ret-stat">
          <span>PUBLISHED EXPORTS</span><b>{data.export.length}</b>
          <em>export/ · live {data.policy.export_days_after_upload}d+ ago</em>
        </div>
        <div className="ret-stat safe">
          <span>KEPT — NOT POSTED</span><b>{data.kept_unposted}</b>
          <em>never deleted, at any age</em>
        </div>
      </div>

      {items.length > 0 ? (
        <>
          <div className="ret-list">
            {shown.map((i) => (
              <div className="ret-row" key={i.kind + i.key}>
                <span className={"ret-kind " + i.kind}>{i.kind}</span>
                <span className="ret-title">
                  {i.title}
                  {i.copies > 1 && (
                    <span className="ret-copies" title={i.paths.join(", ")}>
                      ×{i.copies}
                    </span>
                  )}
                </span>
                <span className="ret-reason">{i.reason}</span>
                <span className="ret-size">{mb(i.bytes)}</span>
              </div>
            ))}
          </div>
          {items.length > 6 && (
            <button className="btn btn-mini ret-more" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "▴ SHOW LESS" : `▾ SHOW ALL ${items.length} VIDEOS`}
            </button>
          )}
          <button className="btn btn-danger ret-run" disabled={busy} onClick={runPurge}>
            🗑 RUN RETENTION — FREE {mb(data.bytes)}
          </button>
        </>
      ) : (
        <div className="empty">Nothing is due for deletion right now.</div>
      )}

      {data.stale?.length > 0 && (
        <div className="lc-note lc-note-warn">
          ⚠ {data.stale.length} video{data.stale.length === 1 ? "" : "s"} staged for{" "}
          {data.policy.stale_warn_days}+ days without being posted:{" "}
          {data.stale.map((s) => s.title).join(", ")}. These are never deleted — but a
          long backlog is worth a look.
        </div>
      )}

      {data.orphans?.length > 0 && (
        <div className="lc-note">
          {data.orphans.length} export folder{data.orphans.length === 1 ? "" : "s"} (
          {mb(data.orphans.reduce((a, o) => a + o.bytes, 0))}) don't match any configured
          topic — leftovers of an older export layout. They are left alone, because the
          policy can't reason about them; delete by hand if you know they're stale.
        </div>
      )}

      {data.runs?.length > 0 && (
        <div className="ret-runs">
          <div className="set-label">RECENT RUNS</div>
          {data.runs.map((r) => (
            <div className="ret-run-row" key={r.id}>
              <span>{r.ran_at.replace("T", " ").slice(0, 16)}</span>
              <span>{r.dry_run ? "dry run" : `${r.output_purged + r.export_purged} deleted`}</span>
              <span>{r.dry_run ? "—" : mb(r.bytes_freed)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

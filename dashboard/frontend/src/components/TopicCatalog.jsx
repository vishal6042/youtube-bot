import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import Chip from "./Chip.jsx";

const PHASES = [
  ["all", "ALL"],
  ["planned", "⬜ PLANNED"],
  ["draft", "📝 IN REVIEW"],
  ["approved", "✅ APPROVED"],
  ["ready", "⏳ READY"],
  ["uploaded", "📤 UPLOADED"],
  ["rejected", "✕ REJECTED"],
];

const PHASE_CHIP = {
  planned: ["chip-missing", "⬜ PLANNED"],
  draft: ["chip-draft", "📝 IN REVIEW"],
  approved: ["chip-rendered", "✅ APPROVED"],
  ready: ["chip-ready", "⏳ READY"],
  uploaded: ["chip-uploaded", "📤 UPLOADED"],
  rejected: ["chip-failed", "✕ REJECTED"],
};

export default function TopicCatalog({ onBack, workingKey, onRender, onOpen, onWatch, promptText, toast }) {
  const [topics, setTopics] = useState(null);
  const [phase, setPhase] = useState("all");
  const [series, setSeries] = useState("");

  const refetch = useCallback(async () => {
    try {
      const r = await api("/api/topics");
      setTopics(r.topics);
    } catch (e) {
      toast(e.message, true);
    }
  }, [toast]);

  useEffect(() => { refetch(); }, [refetch]);

  const act = async (fn, okMsg) => {
    try {
      await fn();
      if (okMsg) toast(okMsg);
      refetch();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const review = (key, action, note) =>
    act(() => api("/api/review", { key, action, note }),
        `${action === "approve" ? "✅ Approved" : "✕ Rejected"} ${key}`);

  const doExport = (key) =>
    act(() => api("/api/export", { key }), `📦 Exported ${key}`);

  const preview = (video) => act(() => api("/api/open", { path: video }), null);

  if (!topics) {
    return (
      <section className="panel detail">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div className="pl-name">TOPIC CATALOG</div>
        </div>
        <div className="empty">Loading…</div>
      </section>
    );
  }

  const allSeries = [...new Set(topics.map((t) => t.series))];
  const countOf = (p) =>
    p === "all" ? topics.length : topics.filter((t) => t.phase === p).length;

  const rows = topics.filter(
    (t) => (phase === "all" || t.phase === phase) && (!series || t.series === series)
  );

  return (
    <section className="panel detail">
      <div className="detail-head">
        <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
        <div>
          <div className="pl-name">TOPIC CATALOG</div>
          <div className="pl-series">
            every configured topic and where it is in the pipeline: planned → in review → approved → ready → uploaded
          </div>
        </div>
      </div>

      <div className="filters">
        {PHASES.map(([p, label]) => {
          const n = countOf(p);
          return (
            <button
              key={p}
              className={"fchip" + (phase === p ? " active" : "")}
              disabled={n === 0 && p !== "all"}
              onClick={() => setPhase(p)}
            >
              {label} <span className="fcount">{n}</span>
            </button>
          );
        })}
        <select value={series} onChange={(e) => setSeries(e.target.value)} className="series-filter">
          <option value="">all playlists</option>
          {allSeries.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="pl-items">
        {!rows.length && <div className="empty">Nothing matches this filter.</div>}
        {rows.map((t) => {
          const [cls, label] = PHASE_CHIP[t.phase];
          const working = workingKey === t.key;
          return (
            <div className="pl-row cat-row" key={t.key}>
              <span className="ep">{String(t.episode).padStart(2, "0")}</span>
              <span className="cat-main">
                <span className="title" title={t.key}>
                  {t.url ? (
                    <a href={t.url} target="_blank" rel="noopener noreferrer">{t.title}</a>
                  ) : (
                    t.title
                  )}
                </span>
                <span className="cat-meta">
                  {t.series}
                  {t.render_date ? ` · rendered ${t.render_date}` : " · never rendered"}
                  {t.duration_sec ? ` · ${t.duration_sec}s` : ""}
                  {t.note ? ` · “${t.note}”` : ""}
                </span>
              </span>
              <span className="pl-row-side">
                <Chip cls={cls}>{label}</Chip>
                {working ? (
                  <span className="working">◉ IN PROGRESS</span>
                ) : (
                  <>
                    {t.video && t.phase !== "planned" && (
                      <button className="btn btn-mini" title="Watch here"
                              onClick={() => onWatch(t)}>▶ WATCH</button>
                    )}
                    {t.phase === "draft" && (
                      <>
                        <button className="btn btn-mini btn-primary"
                                onClick={() => review(t.key, "approve")}>✅ APPROVE</button>
                        <button className="btn btn-mini btn-danger-mini"
                                onClick={async () => {
                                  const note = await promptText({
                                    title: "Reject this draft?",
                                    message: `"${t.title}" will be marked rejected.`,
                                    input: { label: "REASON (optional)",
                                             placeholder: "e.g. data looks wrong" },
                                    confirmLabel: "✕ REJECT", tone: "danger",
                                  });
                                  if (note === null) return;
                                  review(t.key, "reject", note || null);
                                }}>✕ REJECT</button>
                      </>
                    )}
                    {t.phase === "approved" && (
                      <button className="btn btn-mini btn-primary"
                              onClick={() => doExport(t.key)}>📦 EXPORT</button>
                    )}
                    {t.phase === "ready" && t.exported && (
                      <button className="btn btn-mini" title="Open export folder"
                              onClick={() => onOpen(t.exported)}>📂</button>
                    )}
                    {(t.phase === "planned" || t.phase === "rejected") && (
                      <button className="btn btn-mini"
                              onClick={() => onRender(t.key, t.title)}>▶ RENDER</button>
                    )}
                  </>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

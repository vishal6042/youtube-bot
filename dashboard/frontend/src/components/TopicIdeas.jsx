import { useCallback, useEffect, useState } from "react";
import { api, seriesChip } from "../api.js";
import Chip from "./Chip.jsx";
import PlaylistCover from "./PlaylistCover.jsx";

const MODE_LABEL = {
  bar_race: "📊 bar race",
  bump_race: "📈 rank race",
  line_grow: "📉 growing line",
  line_multi: "⚖️ head-to-head",
  waffle_grow: "▦ 100 dots",
};

/* What to build next, decided for you, grouped by playlist. Every card is a
   complete topic — accepting it stages the config for Launch Control. */
export default function TopicIdeas({ onBack, toast, refresh }) {
  const [data, setData] = useState(null);
  const [checks, setChecks] = useState({});   // id -> verify result
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await api("/api/ideas"));
    } catch (e) {
      toast(e.message, true);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const verify = async (id) => {
    setBusy(id);
    try {
      const r = await api("/api/ideas/verify", { id });
      setChecks((c) => ({ ...c, [id]: r }));
      toast(r.ok
        ? `✅ Source OK — ${r.rows.toLocaleString()} rows, ${r.years}`
        : `✕ Source failed: ${r.error}`, !r.ok);
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(null);
  };

  // Accepting only adds the topic to the catalog. It then waits in Launch
  // Control, where it can be reverted or rendered.
  const stage = async (idea) => {
    setBusy(idea.id);
    try {
      await api("/api/ideas/accept", { id: idea.id, render: false });
      toast(`✓ "${idea.title}" staged — render it from Launch Control`);
      await load();
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(null);
  };

  if (!data) {
    return (
      <section className="panel detail">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div className="pl-name">WHAT TO BUILD NEXT</div>
        </div>
        <div className="empty">Loading ideas…</div>
      </section>
    );
  }

  const ready = data.ideas.filter((i) => i.state === "ready");
  const added = data.ideas.filter((i) => i.state === "exists");
  const groups = (data.groups || []).filter((g) => g.ready > 0);

  return (
    <>
      <section className="panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">WHAT TO BUILD NEXT</div>
            <div className="pl-series">
              suggested topics, fully configured — add one, then render it from Launch Control
            </div>
          </div>
          <div className="uq-stats">
            <div className="uq-stat"><b>{ready.length}</b><span>Suggested</span></div>
            <div className="uq-stat"><b>{data.catalog_size}</b><span>In catalog</span></div>
          </div>
        </div>
      </section>

      {groups.map((g) => (
        <section className="idea-group" key={g.series}>
          <div className="idea-group-head">
            <span className={"idea-group-name chip-pl pl-" + g.series}>{g.playlist}</span>
            <span className="idea-group-meta">
              {g.ready} suggestion{g.ready === 1 ? "" : "s"} · {g.in_catalog} already in the catalog
            </span>
            {!g.playlist_exists && (
              <span className="chip chip-ready">⚠ playlist not on YouTube</span>
            )}
          </div>
          <div className="idea-grid">
            {g.ideas.filter((i) => i.state === "ready").map((idea) => {
          const check = checks[idea.id];
          const working = busy === idea.id;
          return (
            <div className="idea-card" key={idea.id}>
              <div className="idea-cover"><PlaylistCover series={idea.series} /></div>
              <div className="idea-body">
                <div className="idea-title">{idea.title}</div>
                <div className="idea-sub">{idea.subtitle}</div>
                <p className="idea-reason">{idea.reason}</p>

                <div className="idea-meta">
                  <Chip cls={seriesChip(idea.series)}>{idea.playlist}</Chip>
                  <span className="idea-src" title={idea.code}>
                    {idea.source}
                  </span>
                  <span className="idea-mode" title="Chart style">
                    {MODE_LABEL[idea.mode] || idea.mode}
                  </span>
                </div>

                {check && (
                  <div className={"idea-check " + (check.ok ? "ok" : "bad")}>
                    {check.ok
                      ? `✅ source verified — ${check.rows.toLocaleString()} rows, ${check.years}`
                      : `✕ ${check.error}`}
                  </div>
                )}

                <div className="idea-actions">
                  <button className="btn btn-mini" disabled={working}
                          onClick={() => verify(idea.id)}>
                    {working ? "…" : "⌕ CHECK SOURCE"}
                  </button>
                  <button className="btn btn-mini btn-primary" disabled={working}
                          onClick={() => stage(idea)}>
                    ＋ ADD TO QUEUE
                  </button>
                </div>
              </div>
            </div>
          );
            })}
          </div>
        </section>
      ))}

      {added.length > 0 && (
        <section className="panel">
          <div className="panel-title">ALREADY IN YOUR CATALOG</div>
          <div className="idea-added">
            {added.map((i) => (
              <span className="chip chip-uploaded" key={i.id}>✓ {i.title}</span>
            ))}
          </div>
          <div className="lc-hint idea-auth-foot">
            Anything not yet rendered is waiting in Launch Control under
            <b> NEW TOPICS</b>, where it can still be reverted.
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-title">PLANNED SERIES <span className="muted">— need a scene written first</span></div>
        <div className="idea-authored">
          {data.authored.map((s) => (
            <div className="idea-auth-row" key={s.name}>
              <span className="idea-auth-name">{s.name}</span>
              <span className="idea-auth-eps">{s.episodes} episodes</span>
              <span className="idea-auth-note">{s.note}</span>
              <code>{s.doc}</code>
            </div>
          ))}
        </div>
        <div className="lc-hint idea-auth-foot">
          These are narrated animations rather than data charts, so each episode needs
          its scene authored in code before it can be rendered — they can't be
          one-click built like the data topics above.
        </div>
      </section>
    </>
  );
}
